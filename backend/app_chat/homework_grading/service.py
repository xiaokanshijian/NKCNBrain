import datetime
import hashlib
import os
import re
import time
import traceback
from concurrent.futures import as_completed
from .execution_control import ThreadPoolExecutor, retryable_transport
from typing import Any, Dict, List, Optional, Set

from llm_langchain import global_var

from app_chat.ci._utils import _ci_dmt_root, _resolve_user_file_path, _update_task
from app_chat.ci.index_manager import CIIndexManager
from app_chat.homework_classifier import normalize_homework_attrs
from app_chat.homework_grading.feedback_snapshot_reader import read_feedback_snapshot
from app_chat.homework_grading.grader_pass1 import (
    _is_empty_auto_layout_artifact,
    _merge_detect_and_grade,
    _normalize_detect_result,
    detect_page_only,
    grade_page,
    grade_page_from_detect,
    pass1_two_stage_enabled,
)
from app_chat.homework_grading.cross_page_detect_backfill import backfill_cross_page_detect_dir
from app_chat.homework_grading.parent_stem_backfill import backfill_parent_stems_in_detect_dir
from app_chat.homework_grading.same_page_detect_backfill import backfill_same_page_detect_dir
from app_chat.homework_grading.grader_pass2 import analyze_pass2
from app_chat.homework_grading.prompts import build_prior_context
from app_chat.homework_grading.memory import aggregate_pages, build_memory, save_memory
from app_chat.homework_grading.ontology_builder import build_ontology
from app_chat.homework_grading.sessions import build_all_session_memories, build_pre_pass1_session_map, session_page_bounds
from app_chat.homework_grading.profile import build_student_profile
from app_chat.homework_grading.grader_pass1_review import review_pass1_dir
from app_chat.homework_grading.verifiers import verify_pass1_dir
from app_chat.homework_grading.hallucination_filter import run_hallucination_filter
from app_chat.homework_grading.curriculum import label_to_cn_map, label_to_domain_map
from app_chat.homework_grading.preprocess import (
    PREPROCESS_MODE_AUTO,
    preprocess_mode_matches_manifest,
    preprocess_pdf,
)
from app_chat.homework_grading.render import render_all_page_modes, render_page_selected_modes
from app_chat.homework_grading.red_blue_review import (
    evaluate_homework_red_blue,
    load_iteration_context,
    load_red_blue_review,
    red_blue_feedback_policy,
)
from app_chat.homework_grading.cross_page import resolve_cross_pages
from app_chat.homework_grading.semantic_config import importance_of
from app_chat.homework_grading.utils import (
    SUBJECT_LABELS,
    load_sample_meta,
    normalize_position,
    parse_page_num,
    position_to_bbox,
    relpath_under,
    safe_json_dump,
    safe_json_load,
    sha256_file,
    sorted_json_pages,
    stage_of_grade,
    write_sample_meta,
)


from app_chat.homework_grading.homework_versions import (
    CURRENT_RUN_ID,
    complete_homework_session_rerun,
    get_homework_rerun_sessions,
    resolve_homework_run_root,
)
from app_chat.homework_grading.staged_pipeline import (
    execute_staged_homework_grading,
    infer_homework_stage_status,
    is_homework_stage_ready,
    load_homework_clean_pages,
    normalize_homework_target_stage,
)
from .completion import summarize_completion, finish_delivery, available_actions, saved_report_ready

ANALYSIS_TYPE = 'homework_grading'
DEFAULT_PASS1_PARALLELISM = 5

HOMEWORK_STAGE_LAYOUT = 'layout'
HOMEWORK_STAGE_UNDERSTANDING = 'understanding'
HOMEWORK_STAGE_GRADING = 'grading'
HOMEWORK_STAGES_ORDER = (
    HOMEWORK_STAGE_LAYOUT,
    HOMEWORK_STAGE_UNDERSTANDING,
    HOMEWORK_STAGE_GRADING,
)


def _pass1_page_max_attempts() -> int:
    try:
        return max(1, min(int(os.environ.get('HOMEWORK_PASS1_PAGE_MAX_ATTEMPTS') or 2), 5))
    except (TypeError, ValueError):
        return 2


def _run_pass1_page_with_retry(page_num: int, label: str, fn):
    attempts = _pass1_page_max_attempts()
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            traceback.print_exc()
            if not retryable_transport(exc):
                raise
            if attempt + 1 >= attempts:
                break
            time.sleep(min(2 ** attempt, 6))
    raise last_exc or RuntimeError(f'{label} 第{page_num}页失败')


def is_homework_analysis_id(analysis_id: str) -> bool:
    return str(analysis_id or '').startswith('homework_')


def build_homework_analysis_id(username: str, filename: str) -> str:
    abs_path = _resolve_user_file_path(username, filename)
    if abs_path and os.path.exists(abs_path):
        digest = sha256_file(abs_path)[:24]
        return f'homework_{digest}'
    # Missing files still receive a deterministic placeholder so the caller can
    # report the normal "PDF不存在" error without restoring metadata identity.
    digest = hashlib.sha256(f'homework-missing|{filename}'.encode('utf-8')).hexdigest()[:24]
    return f'homework_{digest}'


def prepare_homework_workspace(username: str, analysis_id: str, run_id: Optional[str] = None, *, create=True) -> Dict[str, str]:
    root = resolve_homework_run_root(username, analysis_id, run_id)
    base = os.path.join(root, 'homework_grading')
    paths = {
        'root': root,
        'base': base,
        'raw': os.path.join(base, 'raw'),
        'clean': os.path.join(base, 'clean'),
        'preprocess_candidates': os.path.join(base, 'preprocess_candidates'),
        'preprocess_meta': os.path.join(base, 'preprocess_meta.json'),
        'pass1_json': os.path.join(base, 'pass1_json'),
        'pass2_report': os.path.join(base, 'pass2_report'),
        'annotated': os.path.join(base, 'annotated'),
        'annotated_layout': os.path.join(base, 'annotated_layout'),
        'annotated_understanding': os.path.join(base, 'annotated_understanding'),
        'manifest': os.path.join(root, 'manifest.json'),
    }
    if create:
        for key in ('root', 'base', 'raw', 'clean', 'preprocess_candidates', 'pass1_json',
                    'pass2_report', 'annotated', 'annotated_layout', 'annotated_understanding'):
            os.makedirs(paths[key], exist_ok=True)
    return paths


def _sample_id(analysis_id: str) -> str:
    return analysis_id.replace('homework_', '')[:8] or 'sample'


def _question_json_path(pass1_dir: str, clean_path: str) -> str:
    return os.path.join(pass1_dir, os.path.splitext(os.path.basename(clean_path))[0] + '.json')


def _pass1_parallelism(page_count: int) -> int:
    try:
        configured = int(os.environ.get('HOMEWORK_PASS1_PARALLELISM') or DEFAULT_PASS1_PARALLELISM)
    except (TypeError, ValueError):
        configured = DEFAULT_PASS1_PARALLELISM
    return max(1, min(configured, max(1, page_count)))


def _detect_page_job(page: Dict[str, Any], paths: Dict[str, str], subject: str, grade: int = 4, stage: int = 2) -> Dict[str, Any]:
    out_json = _question_json_path(paths['pass1_json'], page['clean_abs_path'])

    def _run() -> Dict[str, Any]:
        detect_page_only(page['clean_abs_path'], subject, page['page'], out_json, grade=grade, stage=stage)
        return {'page': page['page'], 'json_path': out_json}

    return _run_pass1_page_with_retry(page['page'], 'Pass1版面检测', _run)


def _grade_page_job(page: Dict[str, Any], paths: Dict[str, str], subject: str, prior_context: Optional[str] = None, grade: int = 4, stage: int = 2) -> Dict[str, Any]:
    out_json = _question_json_path(paths['pass1_json'], page['clean_abs_path'])

    def _run() -> Dict[str, Any]:
        if pass1_two_stage_enabled():
            grade_page_from_detect(page['clean_abs_path'], subject, page['page'], out_json, prior_context=prior_context, grade=grade, stage=stage)
        else:
            grade_page(page['clean_abs_path'], subject, page['page'], out_json, prior_context=prior_context, grade=grade, stage=stage)
        return {'page': page['page'], 'json_path': out_json}

    return _run_pass1_page_with_retry(page['page'], 'Pass1逐页批改', _run)


def _run_detect_all_pages(
    task_id: str,
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    subject: str,
    grade: int,
    stage: int,
    pass1_workers: int,
) -> None:
    _update_task(task_id, current_section='逐页版面检测')
    with ThreadPoolExecutor(max_workers=min(pass1_workers, len(pages))) as executor:
        futures = [
            executor.submit(_detect_page_job, page, paths, subject, grade, stage)
            for page in pages
        ]
        for future in as_completed(futures):
            future.result()
    cross_page_stats = backfill_cross_page_detect_dir(paths['pass1_json'])
    parent_stem_patched = backfill_parent_stems_in_detect_dir(paths['pass1_json'])
    same_page_stats = backfill_same_page_detect_dir(paths['pass1_json'])
    print(
        f'[homework] cross-page detect backfill: {cross_page_stats}, '
        f'parent_stem_patched={parent_stem_patched}, '
        f'same_page_backfill={same_page_stats}'
    )


def _build_prior_summary(pass1_dir: str, completed_page_nums: set, order_index: int, total_sessions: int) -> Optional[str]:
    """从已完成页的 Pass1 JSON 聚合 Top-3 高频错误 KP，构建前序时序摘要（改编自 yq grader_pass1._build_prior_summary）。

    order_index=1（首个 session）或 completed_page_nums 为空时返回 None。
    error_count>=2 且 error_rate>=0.4 才进入 Top-3（同 yq 阈值）。
    """
    if order_index <= 1 or not completed_page_nums:
        return None
    files = [
        p for p in sorted_json_pages(pass1_dir)
        if parse_page_num(os.path.basename(p)) in completed_page_nums
    ]
    if not files:
        return None
    body = aggregate_pages(files)
    ranked = sorted(
        body.get('knowledge_point_frequency', []),
        key=lambda x: (x.get('error_count', 0), x.get('error_rate', 0)),
        reverse=True,
    )
    top_kps = [
        item['point'] for item in ranked
        if item.get('error_count', 0) >= 2 and item.get('error_rate', 0) >= 0.4
    ][:3]
    return build_prior_context(order_index, total_sessions, top_kps)


def _session_title(session: Dict[str, Any]) -> str:
    return (
        session.get('session_title')
        or session.get('module_title')
        or session.get('unit_title')
        or f"第{session.get('order_index', 1)}次练习"
    )


def _page_range_label(start: int, end: int) -> str:
    if start and end:
        return f'第{start}页' if start == end else f'第{start}-{end}页'
    return ''


def _build_manifest(username: str, filename: str, analysis_id: str, subject: str, pages: List[Dict[str, Any]], attrs: Dict[str, Any], status: str) -> Dict[str, Any]:
    return {
        'analysis_type': ANALYSIS_TYPE,
        'group_id': analysis_id,
        'username': username,
        'mode': 'single',
        'selected_files': [filename],
        'subject': subject,
        'subject_label': SUBJECT_LABELS.get(subject, '未知学科'),
        'homework_attributes': normalize_homework_attrs(attrs),
        'status': status,
        'created_at': datetime.datetime.now().isoformat(),
        'input_units': [
            {
                'unit_id': f'u{page["page"]:03d}',
                'source_file': filename,
                'page': page['page'],
                'seq': page['page'],
                'raw_image_path': '',
                'clean_image_path': '',
                'annotated_image_path': '',
            }
            for page in pages
        ],
    }


def check_homework_stage_ready(
    username: str,
    analysis_id: str,
    stage: Optional[str] = None,
    preprocess_mode: Optional[str] = None,
) -> bool:
    paths = prepare_homework_workspace(username, analysis_id)
    if not os.path.isfile(paths['manifest']):
        return False
    manifest = safe_json_load(paths['manifest'])
    from .artifact_transaction import transaction_pending
    if transaction_pending(paths['base']):
        return False
    if manifest.get('content_validation', {}).get('status') == 'needs_review':
        return False
    if (stage or HOMEWORK_STAGE_GRADING) == HOMEWORK_STAGE_GRADING:
        if any(item['stage'] != 'quality' for item in summarize_completion(manifest)['issues']):
            return False
    if preprocess_mode is not None and not preprocess_mode_matches_manifest(manifest, preprocess_mode):
        return False
    pages = load_homework_clean_pages(paths)
    if not pages:
        return False
    if manifest.get('config_fingerprint'):
        from .execution_checkpoints import receipt_matches
        if not receipt_matches(paths, manifest, stage or HOMEWORK_STAGE_GRADING):
            return False
        from .feedback_artifacts import validate_artifacts
        try:
            validate_artifacts(paths, pages, manifest, stage or HOMEWORK_STAGE_GRADING,
                               expected_pages=manifest.get('source_page_count'))
        except (ValueError, OSError, KeyError):
            return False
    return is_homework_stage_ready(paths, pages, manifest, stage or HOMEWORK_STAGE_GRADING)


def run_homework_grading(
    task_id: str,
    username: str,
    filename: str,
    analysis_id: str,
    homework_attrs: Optional[Dict[str, Any]] = None,
    target_stage: Optional[str] = None,
    scope_page_nums: Optional[Set[int]] = None,
    force_preprocess_scope: bool = False,
    preprocess_mode: str = PREPROCESS_MODE_AUTO,
    feedback_runtime=None,
) -> None:
    paths = prepare_homework_workspace(username, analysis_id)
    try:
        _update_task(task_id, current_item=0, total_items=1, current_section='准备作业批改', completed=False, error='')
        execute_staged_homework_grading(
            task_id=task_id,
            username=username,
            filename=filename,
            analysis_id=analysis_id,
            paths=paths,
            homework_attrs=homework_attrs,
            target_stage=target_stage,
            build_page_units_fn=_build_page_units,
            scope_page_nums=scope_page_nums,
            force_preprocess_scope=force_preprocess_scope,
            preprocess_mode=preprocess_mode,
            **({'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {}),
        )
        if scope_page_nums is not None:
            complete_homework_session_rerun(username, analysis_id)
        final_manifest = safe_json_load(paths['manifest'])
        completion = summarize_completion(final_manifest)
        _update_task(task_id, current_section=completion['message'], completed=True, error='', completion=completion)
        from .grading_rag import schedule_index
        schedule_index(username, filename)
    except Exception as exc:
        traceback.print_exc()
        failure_stage = 'startup'
        if feedback_runtime is not None:
            from .feedback_artifacts import record_failure
            try:
                failure_stage = record_failure(paths, exc)
            except (ValueError, OSError):
                failure_stage = 'artifact_read'
        _update_task(task_id, current_section='失败', completed=True, error=str(exc), failure_stage=failure_stage)
        CIIndexManager.update_status(username, analysis_id, 'failed')


def run_homework_red_blue_review(task_id: str, username: str, analysis_id: str, *, feedback_runtime=None, run_id=None) -> None:
    """仅重评当前版本卡标，不触发 OCR、判分或渲染。"""
    paths = prepare_homework_workspace(username, analysis_id, run_id=run_id)
    manifest = None
    try:
        if not os.path.isfile(paths['manifest']):
            raise ValueError('当前作业批改结果不存在')
        manifest = safe_json_load(paths['manifest'])
        stages = infer_homework_stage_status(
            paths,
            load_homework_clean_pages(paths),
            manifest,
        )
        if stages.get(HOMEWORK_STAGE_GRADING) != 'done':
            raise ValueError('完整批改尚未完成，暂不能生成红蓝卡标')
        if not saved_report_ready(paths, manifest):
            raise ValueError('批改复核或原产物尚未核验通过，暂不能重新评分')
        _update_task(
            task_id,
            current_item=0,
            total_items=1,
            current_section='重新生成批改质量红蓝卡标',
            completed=False,
            error='',
        )
        from .stage_dependencies import enabled as scoped_dependencies
        if scoped_dependencies(feedback_runtime):
            from .execution_control import Execution, execution_scope
            from .execution_checkpoints import record_stage_receipt
            execution = Execution(feedback_runtime, paths['base'], False)
            execution.mark('quality')
            with execution_scope(execution):
                review = evaluate_homework_red_blue(paths, manifest, feedback_runtime=feedback_runtime)
                if review.get('status') == 'ready':
                    record_stage_receipt(paths, manifest, 'quality')
        else:
            review = evaluate_homework_red_blue(paths, manifest, feedback_runtime=feedback_runtime)
        manifest['red_blue_review'] = {
            'status': review.get('status', 'failed'),
            'score': review.get('score'),
            'color': review.get('color', ''),
            'error': review.get('error', ''),
        }
        manifest['updated_at'] = datetime.datetime.now().isoformat()
        completion = finish_delivery(manifest)
        safe_json_dump(paths['manifest'], manifest)
        CIIndexManager.update_status(username, analysis_id, manifest['status'])
        if review.get('status') != 'ready':
            raise ValueError(review.get('error') or '批改质量评分未成功，请查看原运行记录')
        _update_task(task_id, current_item=1, total_items=1, current_section=completion['message'],
                     completed=True, error='', completion=completion)
    except Exception as exc:
        traceback.print_exc()
        completion = None
        if manifest is not None:
            manifest['red_blue_review'] = {'status': 'failed', 'score': None, 'color': '', 'error': str(exc)}
            completion = finish_delivery(manifest)
            safe_json_dump(paths['manifest'], manifest)
            CIIndexManager.update_status(username, analysis_id, manifest['status'])
        _update_task(task_id, current_section='质量评分未完成', completed=True, error=str(exc),
                     failure_stage='quality', completion=completion)


def _load_report(paths: Dict[str, str], manifest: Dict[str, Any]) -> Dict[str, Any]:
    subject = manifest.get('subject') or 'unknown'
    sample_id = _sample_id(manifest.get('group_id') or '')
    report_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_report.json')
    if os.path.exists(report_path):
        return safe_json_load(report_path)
    return {'diagnosis': {}, 'zone_classification': {}, 'per_question_feedback': []}


def _load_pass1_questions(json_path: str, page_num: int) -> List[Dict[str, Any]]:
    if not os.path.exists(json_path):
        return []
    data = safe_json_load(json_path)
    questions = []
    for index, question in enumerate(data.get('questions') or [], start=1):
        if _is_empty_auto_layout_artifact(question):
            continue
        position = normalize_position(question.get('position'))
        verdict = question.get('verdict', 'uncertain')
        error_type = question.get('error_type', '')
        cross_page = bool(question.get('cross_page'))
        cross_page_resolved = bool(question.get('cross_page_resolved'))
        uncertain_reason = ''
        if verdict == 'uncertain':
            uncertain_reason = question.get('uncertain_reason') or (
                'cross_page_attempted' if cross_page_resolved
                else 'cross_page_unresolved' if cross_page
                else 'single_page'
            )
        questions.append({
            'page': page_num,
            'id': question.get('id') or str(index),
            'parent_group_id': question.get('parent_group_id', ''),
            'parent_stem_excerpt': question.get('parent_stem_excerpt', ''),
            'stem_excerpt': question.get('stem_excerpt', ''),
            'student_answer': question.get('student_answer', ''),
            'understanding': question.get('understanding', ''),
            'correct_answer': question.get('correct_answer', ''),
            'verdict': verdict,
            'error_type': error_type,
            'knowledge_point': question.get('knowledge_point', ''),
            'is_application_major_problem': bool(question.get('is_application_major_problem')),
            'importance': importance_of(error_type) if verdict in ('wrong', 'partial', 'uncertain') else '',
            'uncertain_reason': uncertain_reason,
            'verification_result': question.get('verification_result') or {},
            'post_review_guard': question.get('post_review_guard') or {},
            'source_lock': question.get('source_lock') or {},
            'rubric_checks': question.get('rubric_checks') or [],
            'self_review': question.get('self_review') or {},
            'position': position,
            'bbox': position_to_bbox(position),
            'cross_page': cross_page,
            'cross_page_note': question.get('cross_page_note') or '',
            'cross_page_resolved': cross_page_resolved,
            'layout_confidence': question.get('layout_confidence'),
            'recognition_confidence': question.get('recognition_confidence'),
            'understanding_confidence': question.get('understanding_confidence'),
            'grading_confidence': question.get('grading_confidence'),
        })
        from .material_markings import MARKING_FIELDS, normalize_markings
        questions[-1].update({key: question[key] for key in MARKING_FIELDS if key in question})
        normalize_markings(questions[-1], layout='student_answer' not in question)
    return questions


def _load_pass1_boundary(json_path: str) -> Dict[str, Any]:
    if not os.path.exists(json_path):
        return {}
    data = safe_json_load(json_path)
    boundary = data.get('boundary') or {}
    return boundary if isinstance(boundary, dict) else {}


def _build_page_units(paths: Dict[str, str], filename: str, analysis_id: str) -> List[Dict[str, Any]]:
    root = paths['root']
    if not os.path.isdir(paths['clean']):
        return []
    clean_files = sorted(
        [name for name in os.listdir(paths['clean']) if name.lower().endswith('.png')],
        key=lambda name: (parse_page_num(name), name),
    )
    def _mtime(path: str) -> int:
        try:
            return int(os.path.getmtime(path)) if path and os.path.isfile(path) else 0
        except OSError:
            return 0

    units = []
    for name in clean_files:
        page_num = parse_page_num(name)
        raw_path = os.path.join(paths['raw'], name)
        clean_path = os.path.join(paths['clean'], name)
        annotated_path = os.path.join(paths['annotated'], name)
        layout_path = os.path.join(paths['annotated_layout'], name)
        understanding_path = os.path.join(paths['annotated_understanding'], name)
        json_path = os.path.join(paths['pass1_json'], os.path.splitext(name)[0] + '.json')
        stem = os.path.splitext(name)[0]
        preview_path = os.path.join(paths['annotated'], f'.preview_w1600_{stem}.jpg')
        asset_mtime = max(
            _mtime(annotated_path),
            _mtime(layout_path),
            _mtime(understanding_path),
            _mtime(preview_path),
            _mtime(json_path),
        )
        units.append({
            'unit_id': f'u{page_num:03d}',
            'source_file': filename,
            'page': page_num,
            'seq': page_num,
            'raw_image_path': relpath_under(raw_path, root),
            'clean_image_path': relpath_under(clean_path, root),
            'annotated_image_path': relpath_under(annotated_path, root) if os.path.exists(annotated_path) else '',
            'annotated_layout_image_path': relpath_under(layout_path, root) if os.path.exists(layout_path) else '',
            'annotated_understanding_image_path': relpath_under(understanding_path, root) if os.path.exists(understanding_path) else '',
            'pass1_json_path': relpath_under(json_path, root) if os.path.exists(json_path) else '',
            'asset_mtime': asset_mtime or None,
        })
    return units


def _feedback_key(page: Any, question_id: Any) -> str:
    return f'page:{str(page or "").strip()}|id:{str(question_id or "").strip()}'


def _clean_feedback_value(value: Any) -> str:
    text = str(value or '').strip()
    invalid = (
        '信息不足，建议人工确认',
        '信息不足，建议人工确认。',
        '信息不足，建议人工复核',
        '信息不足，建议人工复核。',
        '信息不足',
        '建议人工确认',
        '建议人工复核',
        'null',
        'None',
        '无',
    )
    if not text or text in invalid:
        return ''
    return text


def _build_feedback_map(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    zone_labels = {'blind_spot': '盲区', 'friction_zone': '内耗区', 'zpd': '最近发展区', '': ''}
    for item in report.get('per_question_feedback') or []:
        page = item.get('page') or ''
        question_id = str(item.get('id') or '').strip()
        if not page or not question_id:
            continue
        zone = str(item.get('zone') or '')
        cleaned = {
            'page': page,
            'id': question_id,
            'zone': zone,
            'zone_label': zone_labels.get(zone, ''),
            'comment': _clean_feedback_value(item.get('comment')),
        }
        result[_feedback_key(page, question_id)] = cleaned
        # Pass2 常把题号写成 "<page>-<原始题号>"（如 page2 的 "2-6" 对应 Pass1 题号 6），
        # 而结果里的题目沿用 Pass1 原始题号，需去掉 "<page>-" 前缀后再登记一个别名键以便匹配。
        prefix = f'{str(page).strip()}-'
        if question_id.startswith(prefix):
            stripped = question_id[len(prefix):].strip()
            if stripped:
                result.setdefault(_feedback_key(page, stripped), cleaned)
    return result


def _safe_load_or_default(path: str, default: Any) -> Any:
    if path:
        try:
            return safe_json_load(path)
        except Exception:
            return default
    return default


def _report_paths(paths: Dict[str, str], subject: str, sample_id: str) -> Dict[str, str]:
    base = paths['pass2_report']
    return {
        'memory': os.path.join(base, f'{subject}_{sample_id}_memory.json'),
        'rule_baseline_profile': os.path.join(base, f'{subject}_{sample_id}_rule_baseline_profile.json'),
        'verification': os.path.join(base, f'{subject}_{sample_id}_verification.json'),
        'answer_statement_verification': os.path.join(base, f'{subject}_{sample_id}_answer_statement_verification.json'),
        'hallucination': os.path.join(base, f'{subject}_{sample_id}_hallucination.json'),
    }


def _load_session_memories(paths: Dict[str, str], subject: str, sample_id: str) -> List[Dict[str, Any]]:
    base = paths['pass2_report']
    if not os.path.isdir(base):
        return []
    files = []
    for name in os.listdir(base):
        m = re.match(rf'^{re.escape(subject)}_{re.escape(sample_id)}_s(\d+)_memory\.json$', name)
        if m:
            files.append((int(m.group(1)), os.path.join(base, name)))
    files.sort(key=lambda x: x[0])
    return [safe_json_load(path) for _, path in files]


def _build_session_trends(session_memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    trends = []
    for sm in session_memories:
        acc = (sm.get('accuracy') or {}).get('overall', 0.0)
        try:
            page_start, page_end = session_page_bounds(sm)
        except Exception:
            page_start, page_end = None, None
        trends.append({
            'session_index': sm.get('session_index'),
            'session_id': sm.get('session_id'),
            'session_title': sm.get('session_title', ''),
            'module_title': sm.get('module_title', ''),
            'page_start': page_start,
            'page_end': page_end,
            'submodules': sm.get('submodules', []),
            'accuracy': acc,
            'question_count': sm.get('question_count', 0),
            'uncertain_count': sm.get('uncertain_count', 0),
        })
    return trends


def _build_page_kp_trend(session_memories: List[Dict[str, Any]]) -> Dict[int, Dict[str, str]]:
    """page_number → kp_trend，使每道题只取自己所在 session 的趋势。"""
    result: Dict[int, Dict[str, str]] = {}
    for sm in session_memories:
        kp_trend = sm.get('kp_trend') or {}
        if kp_trend:
            try:
                start, end = session_page_bounds(sm)
            except Exception:
                continue
            for page in range(start, end + 1):
                result[page] = kp_trend
    return result


def _build_curriculum_mastery(memory: Dict[str, Any], subject: str, domain_map=None) -> Dict[str, Any]:
    """按课标领域聚合 correct/total 正确率。"""
    if domain_map is None:
        domain_map = label_to_domain_map(subject)
    domains: Dict[str, Dict[str, Any]] = {}
    kp_items: List[Dict[str, Any]] = []
    for entry in memory.get('knowledge_point_frequency') or []:
        point = entry.get('point', '')
        total = entry.get('total_count', 0)
        error = entry.get('error_count', 0)
        correct = total - error
        domain = domain_map.get(point, '其他')
        bucket = domains.setdefault(domain, {'domain': domain, 'correct': 0, 'total': 0, 'points': []})
        bucket['correct'] += correct
        bucket['total'] += total
        bucket['points'].append(point)
        kp_items.append({
            'knowledge_point': point,
            'domain': domain,
            'total': total,
            'correct': correct,
            'correct_rate': entry.get('correct_rate', round(1 - error / total, 4) if total else 0.0),
        })
    by_domain = []
    for bucket in domains.values():
        total = bucket['total']
        by_domain.append({
            'domain': bucket['domain'],
            'correct': bucket['correct'],
            'total': total,
            'correct_rate': round(bucket['correct'] / total, 4) if total else 0.0,
            'point_count': len(bucket['points']),
        })
    by_domain.sort(key=lambda x: x['correct_rate'])
    return {'by_domain': by_domain, 'by_knowledge_point': kp_items}


def get_homework_grading_result(username: str, analysis_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    active_run_id = (run_id or '').strip() or CURRENT_RUN_ID
    try:
        paths = prepare_homework_workspace(username, analysis_id, run_id=active_run_id, create=False)
    except (ValueError, OSError):
        if active_run_id != CURRENT_RUN_ID:
            raise
        from .homework_versions import list_homework_versions
        history = list_homework_versions(username, analysis_id)
        if not any(not item['is_current'] for item in history):
            raise
        message = '当前结果不可读取，请选择历史版本查看；原目录已保留。'
        return {'error_num': 0, 'analysis_type': 'homework_grading', 'analysis_id': analysis_id,
                'run_id': CURRENT_RUN_ID, 'username': username, 'current_unavailable': True,
                'manifest': {}, 'pages': [], 'snapshot_status': 'invalid',
                'completion': {'status': 'unverified', 'report_usable': False, 'message': message, 'issues': []},
                'available_actions': {key: {'enabled': False, 'reason': message}
                                      for key in ('resume', 'rerun_grading', 'retry_quality')}}
    if not os.path.exists(paths['manifest']):
        return {'error_num': 1, 'msg': f'作业批改结果 {analysis_id} 不存在'}
    from .artifact_transaction import transaction_pending
    if transaction_pending(paths['base']):
        return {'error_num': 1, 'msg': '结果正在发布，请稍后重试'}
    manifest = safe_json_load(paths['manifest'])
    from .feedback_result_basis import result_basis
    basis, feedback_runtime, kp_names, kp_domains = result_basis(paths['root'], manifest)
    manifest['stages'] = infer_homework_stage_status(
        paths,
        load_homework_clean_pages(paths),
        manifest,
    )
    subject = manifest.get('subject') or 'unknown'
    sample_id = _sample_id(manifest.get('group_id') or analysis_id)
    rpaths = _report_paths(paths, subject, sample_id)
    memory = _safe_load_or_default(rpaths['memory'], {})
    verification = _safe_load_or_default(rpaths['verification'], {})
    answer_statement_verification = _safe_load_or_default(rpaths['answer_statement_verification'], {})
    hallucination = _safe_load_or_default(rpaths['hallucination'], {})
    ontology = _safe_load_or_default(os.path.join(paths['base'], 'student_ontology.json'), {})
    sample_meta = load_sample_meta(paths['base'])
    session_memories = _load_session_memories(paths, subject, sample_id)
    rerun_sessions = get_homework_rerun_sessions(username, analysis_id) if active_run_id == CURRENT_RUN_ID else []
    session_rerun = manifest.get('session_rerun') if isinstance(manifest.get('session_rerun'), dict) else {}
    red_blue_review = load_red_blue_review(paths)
    manifest_review = (
        manifest.get('red_blue_review')
        if isinstance(manifest.get('red_blue_review'), dict)
        else {}
    )
    if manifest_review.get('status') in ('failed', 'pending', 'running', 'blocked'):
        red_blue_review = {
            'status': manifest_review['status'],
            'schema_version': 'homework-red-blue-v1',
            'error': manifest_review.get('error') or '评分待补充',
        }
    iteration_context = load_iteration_context(paths)
    session_trends = _build_session_trends(session_memories)
    kp_trend_by_page = _build_page_kp_trend(session_memories)
    curriculum_mastery = _build_curriculum_mastery(memory, subject, kp_domains) if memory else {'by_domain': [], 'by_knowledge_point': []}
    filename = (manifest.get('selected_files') or [''])[0]
    report = _load_report(paths, manifest)
    feedback_map = _build_feedback_map(report)
    pages = []
    assets_version = 0
    for unit in _build_page_units(paths, filename, analysis_id):
        json_abs = os.path.join(paths['root'], unit.get('pass1_json_path', '')) if unit.get('pass1_json_path') else ''
        questions = _load_pass1_questions(json_abs, unit['page']) if json_abs else []
        boundary = _load_pass1_boundary(json_abs) if json_abs else {}
        for question in questions:
            feedback = feedback_map.get(_feedback_key(question['page'], question['id'])) or {}
            question['feedback'] = feedback
            question['trend'] = kp_trend_by_page.get(question['page'], {}).get(question.get('knowledge_point', ''), '')
        from .page_feedback import display_context
        try:
            assets_version = max(assets_version, int(unit.get('asset_mtime') or 0))
        except (TypeError, ValueError):
            pass
        pages.append({**unit, 'boundary': boundary, 'questions': questions,
                      'feedback_context': display_context(unit['page'], report, basis.get('feedback_context'), manifest)})
    from .feedback_task_recovery import task_reference
    task, task_error = task_reference(username, analysis_id, manifest, paths['root']) if active_run_id == CURRENT_RUN_ID else (None, '')
    from .completion import final_material_evidence
    manifest['material_evidence'] = final_material_evidence(paths)
    completion = summarize_completion(manifest, report)
    artifacts_ok = saved_report_ready(paths, manifest) if completion['report_usable'] else False
    if completion['status'] == 'complete' and completion['report_usable'] and not artifacts_ok:
        completion = summarize_completion(manifest, report, artifacts_valid=False)
    actions = available_actions(manifest, completion, snapshot_ok=basis.get('snapshot_status') == 'complete',
                                current=active_run_id == CURRENT_RUN_ID, task=task,
                                artifacts_ok=artifacts_ok,
                                task_error=task_error)
    from .notebook_skills import usage_summary
    return {
        'error_num': 0,
        'analysis_id': analysis_id,
        'run_id': active_run_id,
        'analysis_type': ANALYSIS_TYPE,
        'manifest': manifest,
        'completion': completion,
        'available_actions': actions,
        'notebook_skill_usage': usage_summary(feedback_runtime, paths['base']),
        'task': task,
        'task_lookup_error': task_error,
        'pages': pages,
        'assets_version': assets_version or None,
        'report': report,
        'feedback_by_page_question': feedback_map,
        'student_profile': {},
        'ontology': ontology or {},
        'sample_meta': sample_meta or {},
        **basis,
        'content_validation': manifest.get('content_validation', {'status': 'inconclusive'}),
        'warnings': manifest.get('warnings', []),
        'failure_stage': manifest.get('failure_stage', ''),
        'session_count': len(session_memories),
        'session_trends': session_trends,
        'rerun_sessions': rerun_sessions,
        'session_rerun': session_rerun,
        'red_blue_review': red_blue_review,
        'red_blue_feedback_policy': red_blue_feedback_policy(feedback_runtime=feedback_runtime),
        'iteration_context': iteration_context,
        'curriculum_mastery': curriculum_mastery,
        'kp_name_map': kp_names,
        'quality': {
            'verification_discrepancies': verification.get('total_discrepancies', 0),
            'answer_statement_discrepancies': answer_statement_verification.get('total_discrepancies', 0),
            'answer_statement_corrections': answer_statement_verification.get('corrections_applied', 0),
            'hallucination_issues': hallucination.get('total_issues', 0),
            'hallucination_type_counts': hallucination.get('type_counts', {}),
        },
        'homework_grading': {
            'subject': subject,
            'subject_label': manifest.get('subject_label') or SUBJECT_LABELS.get(subject, '未知学科'),
            'status': manifest.get('status') or 'completed',
        },
        'd_layer': {},
        'm_layer': {},
        't_layer': {},
        'r_layer': {'layer': 'R', 'total_units': 0, 'items': []},
        'overlay_layer': {'items': []},
        'has_layout_visual': False,
    }
