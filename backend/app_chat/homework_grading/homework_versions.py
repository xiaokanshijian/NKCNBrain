"""Archive, invalidate, and list homework grading runs for the same PDF."""

import datetime
import json
import os
import re
import shutil
import tempfile
import uuid
from functools import wraps
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from app_chat.ci._utils import _ci_dmt_root
from app_chat.homework_grading.grader_pass1 import _merge_detect_and_grade, _normalize_detect_result
from app_chat.homework_grading.utils import load_sample_meta, parse_page_num, safe_json_dump, safe_json_load, windows_io_path
from app_chat.homework_grading.feedback_snapshot_reader import SNAPSHOT_FILES, feedback_version_summary, read_feedback_snapshot


ARCHIVES_DIR = '_archives'
ARCHIVES_INDEX = 'index.json'
CURRENT_RUN_ID = 'current'
MAX_KEY_HOMEWORK_VERSIONS = 3
HOMEWORK_RERUN_STAGE_ALL = 'all'
HOMEWORK_RERUN_STAGES = {'all', 'layout', 'understanding', 'grading'}
HOMEWORK_STAGE_ORDER = ('layout', 'understanding', 'grading')


def _archive_transaction(function):
    @wraps(function)
    def wrapped(username, analysis_id, *args, **kwargs):
        from app_chat.ci.file_io import FileLock
        with FileLock(os.path.join(_container_root(username, analysis_id), '.archive.lock'), timeout=15):
            return function(username, analysis_id, *args, **kwargs)
    return wrapped

# 历史版本只保存正式批改链路会读取或需要审计的目录。工作区内的
# gemini_*/golden_eval_runs 等回归实验目录既不属于当前版本，也可能
# 因名称过长导致复制到 _archives 后触发 Windows MAX_PATH。
HOMEWORK_VERSION_DIRS = (
    'raw',
    'clean',
    'preprocess_candidates',
    'pass1_json',
    'pass2_report',
    'annotated',
    'annotated_layout',
    'annotated_understanding',
    'pass1_u1_shadow',
    'layout_evidence',
)

_GRADING_MANIFEST_KEYS = (
    'pass1_5',
    'pass1_review',
    'verification',
    'session_count',
    'ontology',
    'hallucination',
    'slot_presence_guard',
    'red_blue_review',
)
_BASE_DOWNSTREAM_FILES = (
    'student_ontology.json',
    'student_ontology_evidence.json',
    'student_profile.json',
    'hallucination_report.json',
    'corrections_applied.json',
)


def _container_root(username: str, analysis_id: str) -> str:
    return os.path.join(_ci_dmt_root(username), analysis_id)


def _analysis_root(username: str, analysis_id: str) -> str:
    from .feedback_workspaces import current_directory
    return str(current_directory(_container_root(username, analysis_id)))


def _archives_root(username: str, analysis_id: str) -> str:
    return os.path.join(_container_root(username, analysis_id), ARCHIVES_DIR)


def _archives_index_path(username: str, analysis_id: str) -> str:
    return os.path.join(_archives_root(username, analysis_id), ARCHIVES_INDEX)


def _load_archives_index(username: str, analysis_id: str) -> Dict[str, Any]:
    index_path = _archives_index_path(username, analysis_id)
    if os.path.isfile(index_path):
        data = safe_json_load(index_path)
        if isinstance(data.get('versions'), list):
            return data
    return {'versions': []}


def _save_archives_index(username: str, analysis_id: str, data: Dict[str, Any]) -> None:
    if not isinstance(data, dict) or not isinstance(data.get('versions'), list):
        raise ValueError('历史版本索引格式无效')
    index_path = _archives_index_path(username, analysis_id)
    parent = os.path.dirname(index_path)
    os.makedirs(parent, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         prefix='.index-', suffix='.tmp', dir=parent, delete=False) as handle:
            temporary_path = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        validated = safe_json_load(temporary_path)
        if not isinstance(validated, dict) or validated != data:
            raise ValueError('历史版本索引写入校验失败')
        os.replace(temporary_path, index_path)
    finally:
        if temporary_path and os.path.isfile(temporary_path):
            os.remove(temporary_path)


def normalize_homework_run_id(run_id: Optional[str]) -> str:
    text = str(run_id or '').strip()
    if not text:
        return ''
    if text == CURRENT_RUN_ID:
        return CURRENT_RUN_ID
    if os.path.isabs(text) or text in ('.', '..') or '/' in text or '\\' in text:
        raise ValueError('非法历史版本 ID')
    return text


def normalize_homework_rerun_stage(stage: Optional[str]) -> str:
    text = (stage or HOMEWORK_RERUN_STAGE_ALL).strip().lower()
    return text if text in HOMEWORK_RERUN_STAGES else ''


def _sample_id(analysis_id: str) -> str:
    return analysis_id.replace('homework_', '')[:8] or 'sample'


def _red_blue_summary(run_root: str) -> Dict[str, Any]:
    path = os.path.join(
        run_root,
        'homework_grading',
        'pass2_report',
        'red_blue_review.json',
    )
    if not os.path.isfile(path):
        return {
            'red_blue_status': 'missing',
            'red_blue_score': None,
            'red_blue_color': '',
            'red_blue_color_label': '',
        }
    try:
        review = safe_json_load(path)
    except Exception:
        review = {'status': 'failed'}
    return {
        'red_blue_status': review.get('status') or 'failed',
        'red_blue_score': review.get('score'),
        'red_blue_color': review.get('color') or '',
        'red_blue_color_label': review.get('color_label') or '',
    }


def _session_page_bounds(session: Dict[str, Any]) -> Tuple[int, int]:
    try:
        start = int(session.get('page_start') or 0)
        end = int(session.get('page_end') or 0)
    except (TypeError, ValueError):
        return 0, 0
    return (start, end) if start > 0 and end >= start else (0, 0)


def _load_current_sessions(username: str, analysis_id: str, *, workspace_root=None) -> List[Dict[str, Any]]:
    """Return stable Session choices without requiring a completed grading run.

    Older workspaces occasionally predate the Session map.  They remain
    rerunnable through one conservative whole-document Session instead of
    exposing an unusable selector.
    """
    root = str(workspace_root) if workspace_root is not None else _analysis_root(username, analysis_id)
    base = os.path.join(root, 'homework_grading')
    manifest = _load_manifest(os.path.join(root, 'manifest.json'))
    subject = _sample_subject(base, manifest)
    session_path = os.path.join(base, 'pass2_report', f'{subject}_{_sample_id(analysis_id)}_sessions.json')
    source_sessions: List[Any] = []
    if os.path.isfile(session_path):
        try:
            source_sessions = safe_json_load(session_path).get('sessions') or []
        except Exception:
            source_sessions = []

    sessions: List[Dict[str, Any]] = []
    for index, raw in enumerate(source_sessions, start=1):
        if not isinstance(raw, dict):
            continue
        start, end = _session_page_bounds(raw)
        if not start:
            continue
        session_id = str(raw.get('session_id') or f'{_sample_id(analysis_id)}_s{index:02d}').strip()
        if not session_id:
            continue
        title = str(raw.get('session_title') or raw.get('module_title') or raw.get('unit_title') or f'第{index}篇').strip()
        sessions.append({
            'session_id': session_id,
            'session_index': int(raw.get('session_index') or index),
            'order_index': int(raw.get('order_index') or raw.get('session_index') or index),
            'session_title': title or f'第{index}篇',
            'page_start': start,
            'page_end': end,
        })
    if sessions:
        return sorted(sessions, key=lambda item: (item['order_index'], item['page_start']))

    clean_dir = os.path.join(base, 'clean')
    page_nums = []
    if os.path.isdir(clean_dir):
        page_nums = sorted({parse_page_num(name) for name in os.listdir(clean_dir) if parse_page_num(name) > 0})
    if not page_nums:
        return []
    return [{
        'session_id': f'{_sample_id(analysis_id)}_s01',
        'session_index': 1,
        'order_index': 1,
        'session_title': '整份作业',
        'page_start': min(page_nums),
        'page_end': max(page_nums),
    }]


def get_homework_rerun_sessions(username: str, analysis_id: str) -> List[Dict[str, Any]]:
    """Public, UI-safe list of rerunnable Sessions for the current run."""
    return _load_current_sessions(username, analysis_id)


def _validate_session_ids(session_ids: Any, sessions: List[Dict[str, Any]]) -> List[str]:
    if not isinstance(session_ids, list) or not session_ids:
        raise ValueError('session_ids 至少选择一个篇目')
    allowed = {item['session_id'] for item in sessions}
    result: List[str] = []
    seen: Set[str] = set()
    for raw in session_ids:
        session_id = str(raw or '').strip()
        if not session_id:
            raise ValueError('session_ids 不能包含空篇目 ID')
        if session_id in seen:
            raise ValueError('session_ids 不能包含重复篇目 ID')
        if session_id not in allowed:
            raise ValueError(f'未知篇目 ID: {session_id}')
        seen.add(session_id)
        result.append(session_id)
    return result


def _expand_session_ids_for_cross_pages(
    base: str,
    session_ids: Iterable[str],
    sessions: List[Dict[str, Any]],
) -> List[str]:
    """Include Sessions sharing an existing cross-page question with the selection."""
    selected = set(session_ids)
    selected_pages: Set[int] = set()
    page_to_session: Dict[int, str] = {}
    for session in sessions:
        start, end = _session_page_bounds(session)
        for page_num in range(start, end + 1):
            page_to_session[page_num] = session['session_id']
            if session['session_id'] in selected:
                selected_pages.add(page_num)
    if not selected_pages:
        return list(session_ids)
    try:
        from app_chat.homework_grading.cross_page import build_cross_page_groups, scan_boundaries

        pass1_dir = os.path.join(base, 'pass1_json')
        boundaries = scan_boundaries(pass1_dir)
        all_pages = sorted(page_to_session)
        for group in build_cross_page_groups(boundaries, all_pages):
            if set(group) & selected_pages:
                selected.update(page_to_session[page] for page in group if page in page_to_session)
    except Exception:
        # A damaged or incomplete Pass1 workspace must still be rerunnable.
        pass
    return [item['session_id'] for item in sessions if item['session_id'] in selected]


def _pages_for_session_ids(session_ids: Iterable[str], sessions: List[Dict[str, Any]]) -> Set[int]:
    selected = set(session_ids)
    pages: Set[int] = set()
    for session in sessions:
        if session['session_id'] not in selected:
            continue
        start, end = _session_page_bounds(session)
        pages.update(range(start, end + 1))
    return pages


def prepare_homework_session_rerun(
    username: str,
    analysis_id: str,
    rerun_stage: str,
    session_ids: Optional[List[str]] = None,
    resume: bool = False,
    archived_run_id: str = '',
    *, workspace_root=None,
) -> Dict[str, Any]:
    """Create or resume a Session rerun plan and invalidate only its pages.

    The caller archives before a new plan is prepared.  Resume deliberately
    reuses the stored plan and therefore never creates another archive.
    """
    stage = normalize_homework_rerun_stage(rerun_stage)
    if not stage:
        raise ValueError('rerun_stage 必须是 all、layout、understanding 或 grading')
    root = str(workspace_root) if workspace_root is not None else _analysis_root(username, analysis_id)
    manifest_path = os.path.join(root, 'manifest.json')
    manifest = _load_manifest(manifest_path)
    sessions = _load_current_sessions(username, analysis_id, workspace_root=workspace_root)
    if not sessions:
        raise ValueError('当前作业尚未生成可迭代的篇目')

    if resume:
        if session_ids is not None:
            raise ValueError('续跑时不能同时传 session_ids')
        plan = manifest.get('session_rerun') if isinstance(manifest.get('session_rerun'), dict) else {}
        if not plan.get('resume_available'):
            raise ValueError('当前没有可继续完成的篇目迭代')
        if plan.get('rerun_stage') != stage:
            raise ValueError('续跑阶段必须与上次篇目迭代一致')
        requested_ids = _validate_session_ids(plan.get('remaining_session_ids'), sessions)
        completed_ids = [str(item) for item in plan.get('completed_session_ids') or []]
        archived_run_id = str(plan.get('archived_run_id') or '')
    else:
        requested_ids = _validate_session_ids(session_ids, sessions)
        completed_ids = []
        archived_run_id = str(archived_run_id or '')

    effective_ids = _expand_session_ids_for_cross_pages(
        os.path.join(root, 'homework_grading'), requested_ids, sessions,
    )
    scope_pages = _pages_for_session_ids(effective_ids, sessions)
    if not scope_pages:
        raise ValueError('所选篇目没有可迭代页面')

    invalidate_stage = 'layout' if stage == HOMEWORK_RERUN_STAGE_ALL else stage
    invalidate_homework_stage_for_rerun(
        username,
        analysis_id,
        invalidate_stage,
        page_nums=scope_pages,
        clear_source_pages=(stage == HOMEWORK_RERUN_STAGE_ALL),
        workspace_root=workspace_root,
    )

    all_ids = [item['session_id'] for item in sessions]
    newly_completed = [item for item in completed_ids if item in all_ids and item not in effective_ids]
    remaining_ids = [item for item in all_ids if item not in set(newly_completed) | set(effective_ids)]
    fresh_manifest = _load_manifest(manifest_path)
    fresh_manifest['session_rerun'] = {
        'rerun_stage': stage,
        'requested_session_ids': requested_ids,
        'effective_session_ids': effective_ids,
        'completed_session_ids': newly_completed,
        'active_session_ids': effective_ids,
        'remaining_session_ids': remaining_ids,
        'resume_available': bool(remaining_ids),
        'status': 'running',
        'archived_run_id': archived_run_id,
        'updated_at': datetime.datetime.now().isoformat(),
    }
    safe_json_dump(manifest_path, fresh_manifest)
    return {
        'rerun_stage': stage,
        'sessions': sessions,
        'effective_session_ids': effective_ids,
        'scope_page_nums': sorted(scope_pages),
        'remaining_session_ids': remaining_ids,
        'resume_available': bool(remaining_ids),
        'is_resume': resume,
    }


def complete_homework_session_rerun(username: str, analysis_id: str) -> Dict[str, Any]:
    """Mark the active portion of a Session rerun plan as completed."""
    manifest_path = os.path.join(_analysis_root(username, analysis_id), 'manifest.json')
    manifest = _load_manifest(manifest_path)
    plan = manifest.get('session_rerun') if isinstance(manifest.get('session_rerun'), dict) else None
    if not plan:
        return {}
    completed = []
    for item in list(plan.get('completed_session_ids') or []) + list(plan.get('active_session_ids') or []):
        text = str(item or '').strip()
        if text and text not in completed:
            completed.append(text)
    all_sessions = _load_current_sessions(username, analysis_id)
    all_ids = [item['session_id'] for item in all_sessions]
    remaining = [item for item in all_ids if item not in completed]
    plan.update({
        'completed_session_ids': completed,
        'active_session_ids': [],
        'remaining_session_ids': remaining,
        'resume_available': bool(remaining),
        'status': 'awaiting_resume' if remaining else 'completed',
        'updated_at': datetime.datetime.now().isoformat(),
    })
    manifest['session_rerun'] = plan
    safe_json_dump(manifest_path, manifest)
    return plan


def resolve_homework_run_root(username: str, analysis_id: str, run_id: Optional[str] = None) -> str:
    root = _analysis_root(username, analysis_id)
    clean_run_id = normalize_homework_run_id(run_id)
    if clean_run_id.startswith('p03_'):
        from .feedback_workspaces import run_directory
        directory = run_directory(_container_root(username, analysis_id), clean_run_id)
        if not (directory / 'manifest.json').is_file():
            raise ValueError('批改运行不存在')
        return str(directory)
    if clean_run_id and clean_run_id != CURRENT_RUN_ID:
        return os.path.join(_archives_root(username, analysis_id), clean_run_id)
    return root


def _valid_archived_versions(root: str, versions: List[Any]) -> List[Dict[str, Any]]:
    valid: List[Dict[str, Any]] = []
    for item in versions:
        if not isinstance(item, dict):
            continue
        try:
            run_id = normalize_homework_run_id(item.get('run_id'))
        except ValueError:
            continue
        if not run_id or run_id == CURRENT_RUN_ID:
            continue
        if not os.path.isdir(os.path.join(root, ARCHIVES_DIR, run_id)):
            continue
        item['run_id'] = run_id
        valid.append(item)
    return valid


def _delete_archive_dir(root: str, run_id: str) -> None:
    archive_parent = os.path.join(root, ARCHIVES_DIR)
    archive_root = os.path.join(archive_parent, run_id)
    _assert_inside(archive_parent, archive_root)
    if os.path.isdir(archive_root):
        shutil.rmtree(windows_io_path(archive_root), ignore_errors=True)


def _copy_homework_version_workspace(source: str, destination: str) -> None:
    """Copy only formal version artifacts, plus direct workspace metadata files."""
    source = windows_io_path(source)
    destination = windows_io_path(destination)
    os.makedirs(destination, exist_ok=False)
    for item in os.scandir(source):
        target = os.path.join(destination, item.name)
        if item.is_file(follow_symlinks=False):
            shutil.copy2(item.path, target)
        elif item.is_dir(follow_symlinks=False) and item.name in HOMEWORK_VERSION_DIRS:
            shutil.copytree(item.path, target)


@_archive_transaction
def archive_homework_run_if_exists(username: str, analysis_id: str, *, preserve_unrestorable=False) -> Optional[str]:
    """Snapshot the current formal workspace into _archives/. Returns run_id or None."""
    root = _analysis_root(username, analysis_id)
    manifest_path = os.path.join(root, 'manifest.json')
    workspace_dir = os.path.join(root, 'homework_grading')
    if not os.path.isfile(manifest_path) or not os.path.isdir(workspace_dir):
        return None

    manifest = safe_json_load(manifest_path)
    snapshot_state = read_feedback_snapshot(root, manifest)
    if snapshot_state['snapshot_status'] not in ('complete', 'legacy_missing') and not preserve_unrestorable:
        raise ValueError('当前材料配置快照不完整或损坏，已保留原版本，未归档')
    run_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_parent = _archives_root(username, analysis_id)
    archive_root = os.path.join(archive_parent, run_id)
    while os.path.exists(archive_root):
        run_id = f"{run_id}_{uuid.uuid4().hex[:8]}"
        archive_root = os.path.join(archive_parent, run_id)
    promoted = False

    os.makedirs(archive_parent, exist_ok=True)
    temp_root = tempfile.mkdtemp(prefix=f'.{run_id}.', suffix='.tmp', dir=archive_parent)
    try:
        shutil.copy2(manifest_path, os.path.join(temp_root, 'manifest.json'))
        if snapshot_state['snapshot_status'] == 'complete' or preserve_unrestorable:
            for name in SNAPSHOT_FILES.values():
                source = os.path.join(root, name)
                if os.path.islink(source):
                    raise ValueError('历史快照路径异常，拒绝跟随外部链接')
                if os.path.isfile(source):
                    shutil.copy2(source, os.path.join(temp_root, name))
        _copy_homework_version_workspace(
            workspace_dir,
            os.path.join(temp_root, 'homework_grading'),
        )
        if safe_json_load(os.path.join(temp_root, 'manifest.json')) != manifest:
            raise ValueError('归档期间运行记录发生变化，未发布新版本')
        archived_state = read_feedback_snapshot(temp_root)
        if archived_state != snapshot_state:
            raise ValueError('归档快照完整性校验失败，原版本保持不变')
        if os.path.exists(archive_root):
            raise FileExistsError('目标历史版本已存在，拒绝覆盖')
        os.rename(temp_root, archive_root)
        promoted = True

        index_data = _load_archives_index(username, analysis_id)
        versions = index_data.get('versions') if isinstance(index_data.get('versions'), list) else []
        versions.append({
            'run_id': run_id,
            'label': f'历史版本 {len(versions) + 1}',
            'archived_at': datetime.datetime.now().isoformat(),
            'source_created_at': manifest.get('created_at') or '',
            'status': manifest.get('status') or 'completed',
            'is_key_version': False,
        })
        index_data['versions'] = versions
        _save_archives_index(username, analysis_id, index_data)
        return run_id
    except Exception:
        if os.path.isdir(temp_root):
            _assert_inside(archive_parent, temp_root)
            shutil.rmtree(windows_io_path(temp_root), ignore_errors=True)
        if promoted:
            _delete_archive_dir(_container_root(username, analysis_id), run_id)
        raise


def clear_homework_workspace_for_rerun(username: str, analysis_id: str) -> None:
    root = _analysis_root(username, analysis_id)
    workspace_dir = os.path.join(root, 'homework_grading')
    manifest_path = os.path.join(root, 'manifest.json')
    if os.path.isdir(workspace_dir):
        shutil.rmtree(workspace_dir, ignore_errors=True)
    if os.path.isfile(manifest_path):
        os.remove(manifest_path)


def _assert_inside(root: str, path: str) -> None:
    root_abs = os.path.abspath(root)
    path_abs = os.path.abspath(path)
    if os.path.commonpath([root_abs, path_abs]) != root_abs:
        raise ValueError(f'拒绝清理工作区外路径: {path}')


def _remove_file(root: str, path: str) -> None:
    _assert_inside(root, path)
    if os.path.isfile(path):
        os.remove(path)


def _clear_dir(root: str, path: str, keep: Optional[Callable[[str, str], bool]] = None) -> None:
    _assert_inside(root, path)
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)
        return
    for name in os.listdir(path):
        item = os.path.join(path, name)
        if keep and keep(name, item):
            continue
        if os.path.isdir(item):
            shutil.rmtree(item, ignore_errors=True)
        elif os.path.exists(item):
            os.remove(item)


def _remove_matching(root: str, path: str, predicate: Callable[[str], bool]) -> None:
    _assert_inside(root, path)
    if not os.path.isdir(path):
        return
    for name in os.listdir(path):
        item = os.path.join(path, name)
        if predicate(name) and os.path.exists(item):
            if os.path.isdir(item):
                shutil.rmtree(item, ignore_errors=True)
            else:
                os.remove(item)


def _is_selected_page_file(name: str, page_nums: Optional[Set[int]]) -> bool:
    if page_nums is None:
        return True
    page_num = parse_page_num(name)
    if not page_num:
        match = re.search(r'_page(\d+)(?:\.[^.]+)*$', name)
        page_num = int(match.group(1)) if match else 0
    return page_num in page_nums


def _keep_session_map(name: str, _path: str) -> bool:
    return name.endswith('_sessions.json')


def _load_manifest(manifest_path: str) -> Dict[str, Any]:
    if not os.path.isfile(manifest_path):
        return {}
    try:
        return safe_json_load(manifest_path)
    except Exception:
        return {}


def _sample_subject(base_dir: str, manifest: Dict[str, Any]) -> str:
    sample_meta = load_sample_meta(base_dir) or {}
    return manifest.get('subject') or sample_meta.get('subject') or 'unknown'


def _reset_final_jsons_to_detect_only(
    root: str,
    pass1_dir: str,
    subject: str,
    page_nums: Optional[Set[int]] = None,
) -> None:
    _assert_inside(root, pass1_dir)
    if not os.path.isdir(pass1_dir):
        return
    for name in sorted(os.listdir(pass1_dir)):
        if not name.endswith('.detect.json'):
            continue
        detect_path = os.path.join(pass1_dir, name)
        final_name = name.replace('.detect.json', '.json')
        final_path = os.path.join(pass1_dir, final_name)
        try:
            page_num = parse_page_num(final_name)
            if page_nums is not None and page_num not in page_nums:
                continue
            detected = _normalize_detect_result(safe_json_load(detect_path), subject, page_num)
            merged = _merge_detect_and_grade(detected, {'questions': []}, subject, page_num)
            safe_json_dump(final_path, merged)
        except Exception:
            continue


def _reset_manifest_for_stage(manifest_path: str, manifest: Dict[str, Any], rerun_stage: str) -> None:
    stages = manifest.get('stages') if isinstance(manifest.get('stages'), dict) else {}
    for stage in HOMEWORK_STAGE_ORDER:
        stages.setdefault(stage, 'pending')
    if rerun_stage in HOMEWORK_STAGE_ORDER:
        invalidate = False
        for stage in HOMEWORK_STAGE_ORDER:
            if stage == rerun_stage:
                invalidate = True
            if invalidate:
                stages[stage] = 'pending'
    manifest['stages'] = stages
    manifest['status'] = 'running'
    manifest['target_stage'] = rerun_stage
    manifest['updated_at'] = datetime.datetime.now().isoformat()
    for key in _GRADING_MANIFEST_KEYS:
        manifest.pop(key, None)
    safe_json_dump(manifest_path, manifest)


def invalidate_homework_stage_for_rerun(
    username: str,
    analysis_id: str,
    rerun_stage: str,
    page_nums: Optional[Iterable[int]] = None,
    clear_source_pages: bool = False,
    *, workspace_root=None,
) -> None:
    """Clear rerun target and downstream artifacts while preserving reusable upstream work."""
    stage = normalize_homework_rerun_stage(rerun_stage)
    if stage not in HOMEWORK_STAGE_ORDER:
        raise ValueError('rerun_stage 必须是 layout、understanding 或 grading')

    selected_pages = {int(page) for page in page_nums} if page_nums is not None else None
    root = str(workspace_root) if workspace_root is not None else _analysis_root(username, analysis_id)
    base = os.path.join(root, 'homework_grading')
    paths = {
        'pass1_json': os.path.join(base, 'pass1_json'),
        'pass2_report': os.path.join(base, 'pass2_report'),
        'annotated': os.path.join(base, 'annotated'),
        'annotated_layout': os.path.join(base, 'annotated_layout'),
        'annotated_understanding': os.path.join(base, 'annotated_understanding'),
        'raw': os.path.join(base, 'raw'),
        'clean': os.path.join(base, 'clean'),
        'pass1_u1_shadow': os.path.join(base, 'pass1_u1_shadow'),
        'layout_evidence': os.path.join(base, 'layout_evidence'),
        'manifest': os.path.join(root, 'manifest.json'),
    }
    manifest = _load_manifest(paths['manifest'])
    subject = _sample_subject(base, manifest)

    def clear_u1_shadow_stage(stage_name: str) -> None:
        _remove_matching(
            root,
            os.path.join(paths['pass1_u1_shadow'], stage_name),
            lambda name: _is_selected_page_file(name, selected_pages),
        )

    def clear_u1_summary_and_legacy() -> None:
        _remove_file(root, os.path.join(paths['pass1_u1_shadow'], 'summary.json'))
        _remove_matching(
            root,
            paths['pass1_u1_shadow'],
            lambda name: name != 'layout' and name != 'transcription'
            and _is_selected_page_file(name, selected_pages),
        )

    def clear_slot_presence_shadow() -> None:
        slot_dir = os.path.join(paths['layout_evidence'], 'slot_presence')
        _remove_file(root, os.path.join(slot_dir, 'summary.json'))
        _remove_matching(
            root,
            slot_dir,
            lambda name: _is_selected_page_file(name, selected_pages),
        )

    if stage == 'layout':
        clear_u1_shadow_stage('layout')
        clear_u1_shadow_stage('transcription')
        clear_u1_summary_and_legacy()
        clear_slot_presence_shadow()
        if selected_pages is None:
            _clear_dir(root, paths['pass1_json'])
            _clear_dir(root, paths['annotated_layout'])
            _clear_dir(root, paths['annotated_understanding'])
            _clear_dir(root, paths['annotated'])
        else:
            for directory in ('pass1_json', 'annotated_layout', 'annotated_understanding', 'annotated'):
                _remove_matching(root, paths[directory], lambda name: _is_selected_page_file(name, selected_pages))
            if clear_source_pages:
                _remove_matching(root, paths['raw'], lambda name: _is_selected_page_file(name, selected_pages))
                _remove_matching(root, paths['clean'], lambda name: _is_selected_page_file(name, selected_pages))
    elif stage == 'understanding':
        clear_u1_shadow_stage('transcription')
        clear_u1_summary_and_legacy()
        _remove_matching(
            root,
            paths['pass1_json'],
            lambda name: _is_selected_page_file(name, selected_pages) and (
                name.endswith('.grade.json')
                or name.endswith('.review.json')
                or name.endswith('.thinking.txt')
                or name.endswith('.error.txt')
                or name.endswith('.corrected.bak')
                or (name.endswith('.json') and not name.endswith('.detect.json'))
            ),
        )
        if selected_pages is None:
            _reset_final_jsons_to_detect_only(root, paths['pass1_json'], subject)
            _clear_dir(root, paths['annotated_understanding'])
            _clear_dir(root, paths['annotated'])
        else:
            _reset_final_jsons_to_detect_only(root, paths['pass1_json'], subject, page_nums=selected_pages)
            _remove_matching(root, paths['annotated_understanding'], lambda name: _is_selected_page_file(name, selected_pages))
            _remove_matching(root, paths['annotated'], lambda name: _is_selected_page_file(name, selected_pages))
    elif stage == 'grading':
        _remove_matching(
            root,
            paths['pass1_json'],
            lambda name: _is_selected_page_file(name, selected_pages) and (
                name.endswith('.review.json')
                or name.endswith('.review.error.txt')
                or name.endswith('.review.thinking.txt')
                or name.endswith('.corrected.bak')
            ),
        )
        if selected_pages is None:
            _clear_dir(root, paths['annotated'])
        else:
            _remove_matching(root, paths['annotated'], lambda name: _is_selected_page_file(name, selected_pages))

    _clear_dir(root, paths['pass2_report'], keep=_keep_session_map)
    for name in _BASE_DOWNSTREAM_FILES:
        _remove_file(root, os.path.join(base, name))
    _reset_manifest_for_stage(paths['manifest'], manifest, stage)


def list_homework_versions(username: str, analysis_id: str) -> List[Dict[str, Any]]:
    root = _analysis_root(username, analysis_id)
    versions: List[Dict[str, Any]] = []
    manifest_path = os.path.join(root, 'manifest.json')
    if os.path.isfile(manifest_path):
        manifest = safe_json_load(manifest_path)
        versions.append({
            'run_id': CURRENT_RUN_ID,
            'label': '当前版本',
            'is_current': True,
            'is_key_version': False,
            # Version labels represent when that version was last generated,
            # not when the analysis workspace was first created.  A rerun
            # intentionally keeps created_at, so using it here can make the
            # current version appear older than the snapshot just archived.
            'created_at': manifest.get('updated_at') or manifest.get('created_at') or '',
            'status': manifest.get('status') or 'completed',
            **_red_blue_summary(root),
            **feedback_version_summary(root, manifest),
        })

    archived: List[Dict[str, Any]] = []
    index_data = _load_archives_index(username, analysis_id)

    for item in index_data.get('versions') or []:
        if not isinstance(item, dict):
            continue
        try:
            run_id = normalize_homework_run_id(item.get('run_id'))
        except ValueError:
            continue
        if not run_id or not os.path.isdir(os.path.join(_archives_root(username, analysis_id), run_id)):
            continue
        archive_root = os.path.join(_archives_root(username, analysis_id), run_id)
        archived.append({
            'run_id': run_id,
            'label': item.get('label') or run_id,
            'is_current': False,
            'is_key_version': bool(item.get('is_key_version')),
            'key_marked_at': item.get('key_marked_at') or '',
            'created_at': item.get('archived_at') or item.get('source_created_at') or '',
            'status': item.get('status') or 'completed',
            **_red_blue_summary(archive_root),
            **feedback_version_summary(archive_root),
        })
    archived.reverse()
    versions.extend(archived)
    return versions


@_archive_transaction
def set_homework_version_key(username: str, analysis_id: str, run_id: str, is_key: bool) -> Dict[str, Any]:
    clean_run_id = normalize_homework_run_id(run_id)
    if not clean_run_id:
        raise ValueError('缺少 run_id')
    if clean_run_id == CURRENT_RUN_ID:
        raise ValueError('当前版本不是历史版本，不能设为关键历史版本')

    root = _analysis_root(username, analysis_id)
    archive_root = os.path.join(_archives_root(username, analysis_id), clean_run_id)
    if not os.path.isdir(archive_root):
        raise ValueError('历史版本不存在')

    index_data = _load_archives_index(username, analysis_id)
    versions = index_data.get('versions') if isinstance(index_data.get('versions'), list) else []
    target: Optional[Dict[str, Any]] = None
    for item in versions:
        if isinstance(item, dict) and str(item.get('run_id') or '').strip() == clean_run_id:
            target = item
            break
    if target is None:
        raise ValueError('历史版本索引不存在')

    if is_key:
        key_count = sum(
            1 for item in versions
            if isinstance(item, dict)
            and bool(item.get('is_key_version'))
            and str(item.get('run_id') or '').strip() != clean_run_id
        )
        if key_count >= MAX_KEY_HOMEWORK_VERSIONS:
            raise ValueError(f'关键历史版本最多只能设置 {MAX_KEY_HOMEWORK_VERSIONS} 个')
        target['is_key_version'] = True
        target['key_marked_at'] = datetime.datetime.now().isoformat()
    else:
        target['is_key_version'] = False
        target.pop('key_marked_at', None)

    index_data['versions'] = versions
    _save_archives_index(username, analysis_id, index_data)
    return target
