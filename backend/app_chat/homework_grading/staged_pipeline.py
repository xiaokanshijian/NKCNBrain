"""作业批改分段流水线：layout → understanding → grading（含 Pass2）。"""
from __future__ import annotations

import datetime
import os
import time
import traceback
from concurrent.futures import as_completed
from .execution_control import ThreadPoolExecutor, managed_execution
from typing import Any, Dict, List, Optional

from app_chat.ci._utils import _resolve_user_file_path, _update_task
from app_chat.ci.index_manager import CIIndexManager
from app_chat.homework_classifier import normalize_homework_attrs
from app_chat.homework_grading.answer_statement_verifier import verify_answer_statements
from app_chat.homework_grading.cross_page import pass1_5_enabled, resolve_cross_pages
from app_chat.homework_grading.cross_page_detect_backfill import backfill_cross_page_detect_dir
from app_chat.homework_grading.fixed_sample_crossout import (
    MODEL_IMAGE_PATH_KEY,
    prepare_fixed_sample_crossout_images,
)
from app_chat.homework_grading.fixed_english_choice_slots import (
    reapply_fixed_english_choice_guards,
)
from app_chat.homework_grading.fixed_english_page15_guard import (
    reapply_fixed_english_page15_guard,
)
from app_chat.homework_grading.fixed_math_sample_guards import (
    apply_fixed_math_sample_guards_to_files,
    reapply_fixed_math_sample_guard_files,
)
from app_chat.homework_grading.grader_pass1 import (
    _merge_detect_and_grade,
    _normalize_detect_result,
    detect_page_only,
    grade_page,
    grade_page_from_detect,
    pass1_two_stage_enabled,
)
from app_chat.homework_grading.grader_pass1_review import review_pass1_dir
from app_chat.homework_grading.grader_pass2 import analyze_pass2
from app_chat.homework_grading.hallucination_filter import run_hallucination_filter
from app_chat.homework_grading.memory import aggregate_pages, build_memory, save_memory
from app_chat.homework_grading.llm_clients import homework_qwen_model
from app_chat.homework_grading.ontology_builder import build_ontology
from app_chat.homework_grading.parent_stem_backfill import backfill_parent_stems_in_detect_dir
from app_chat.homework_grading.preprocess import (
    PREPROCESS_MODE_AUTO,
    load_preprocess_metadata,
    preprocess_manifest_entry,
    preprocess_pdf,
)
from app_chat.homework_grading.profile import build_student_profile
from app_chat.homework_grading.prompts import build_prior_context
from app_chat.homework_grading.red_blue_review import (
    compile_iteration_guidance,
    evaluate_homework_red_blue,
    load_iteration_context,
)
from app_chat.homework_grading.render import render_page_selected_modes
from app_chat.homework_grading.same_page_detect_backfill import backfill_same_page_detect_dir
from app_chat.homework_grading.sessions import (
    build_all_session_memories,
    build_pre_pass1_session_map,
    session_page_bounds,
)
from app_chat.homework_grading.slot_presence import (
    apply_slot_presence_guard_to_files,
    reapply_slot_presence_guard_files,
    run_slot_presence_layout_page,
    slot_presence_apply_approved,
    slot_presence_layout_enabled,
    slot_presence_mode,
)
from app_chat.homework_grading.utils import (
    SUBJECT_LABELS,
    load_sample_meta,
    parse_page_num,
    resolve_source_document_sha256,
    safe_json_dump,
    safe_json_load,
    sorted_json_pages,
    stage_of_grade,
    write_sample_meta,
)
from app_chat.homework_grading.u1_shadow import (
    comparison_text,
    run_u1_shadow_layout_page,
    run_u1_shadow_page,
    u1_shadow_enabled,
)
from app_chat.homework_grading.prompts import (
    PASS1_U1_LAYOUT_PROMPT_VERSION,
    PASS1_U1_SHADOW_PROMPT_VERSION,
)
from app_chat.homework_grading.verifiers import verify_pass1_dir

HOMEWORK_STAGE_LAYOUT = 'layout'
HOMEWORK_STAGE_UNDERSTANDING = 'understanding'
HOMEWORK_STAGE_GRADING = 'grading'
HOMEWORK_STAGES_ORDER = (
    HOMEWORK_STAGE_LAYOUT,
    HOMEWORK_STAGE_UNDERSTANDING,
    HOMEWORK_STAGE_GRADING,
)

DEFAULT_PASS1_PARALLELISM = 5


def normalize_homework_target_stage(stage: Optional[str]) -> str:
    text = (stage or HOMEWORK_STAGE_GRADING).strip().lower()
    if text in HOMEWORK_STAGES_ORDER:
        return text
    return HOMEWORK_STAGE_GRADING


def _default_stage_status() -> Dict[str, str]:
    return {key: 'pending' for key in HOMEWORK_STAGES_ORDER}


def _pass1_parallelism(page_count: int, feedback_runtime=None) -> int:
    from .feedback_runtime import frozen_environment
    try:
        configured = int(frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_PARALLELISM') or DEFAULT_PASS1_PARALLELISM)
    except (TypeError, ValueError):
        configured = DEFAULT_PASS1_PARALLELISM
    return max(1, min(configured, max(1, page_count)))


def _pass1_page_max_attempts(feedback_runtime=None) -> int:
    from .feedback_runtime import frozen_environment
    try:
        return max(1, min(int(frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_PAGE_MAX_ATTEMPTS') or 2), 5))
    except (TypeError, ValueError):
        return 2


def _run_pass1_page_with_retry(page_num: int, label: str, fn, feedback_runtime=None):
    import time
    from .execution_control import retryable_transport

    attempts = _pass1_page_max_attempts(feedback_runtime)
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


def _question_json_path(pass1_dir: str, clean_path: str) -> str:
    return os.path.join(pass1_dir, os.path.splitext(os.path.basename(clean_path))[0] + '.json')


def _sample_id(analysis_id: str) -> str:
    return analysis_id.replace('homework_', '')[:8] or 'sample'


def _page_clean_basename(page: Dict[str, Any]) -> str:
    return os.path.splitext(os.path.basename(page['clean_abs_path']))[0]


def _page_detect_path(paths: Dict[str, str], page: Dict[str, Any]) -> str:
    return os.path.join(paths['pass1_json'], f"{_page_clean_basename(page)}.detect.json")


def _page_grade_path(paths: Dict[str, str], page: Dict[str, Any]) -> str:
    return os.path.join(paths['pass1_json'], f"{_page_clean_basename(page)}.grade.json")


def _page_slot_presence_path(paths: Dict[str, str], page: Dict[str, Any]) -> str:
    return os.path.join(
        paths['base'],
        'layout_evidence',
        'slot_presence',
        f"{_page_clean_basename(page)}.presence.json",
    )


def _page_layout_png_path(paths: Dict[str, str], page: Dict[str, Any]) -> str:
    return os.path.join(paths['annotated_layout'], f"{_page_clean_basename(page)}.png")


def _page_understanding_png_path(paths: Dict[str, str], page: Dict[str, Any]) -> str:
    return os.path.join(paths['annotated_understanding'], f"{_page_clean_basename(page)}.png")


def _page_grading_png_path(paths: Dict[str, str], page: Dict[str, Any]) -> str:
    return os.path.join(paths['annotated'], f"{_page_clean_basename(page)}.png")


def load_homework_clean_pages(paths: Dict[str, str]) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    if not os.path.isdir(paths['clean']):
        return pages
    for name in sorted(os.listdir(paths['clean'])):
        if not name.lower().endswith('.png'):
            continue
        page_num = parse_page_num(name)
        if not page_num:
            continue
        pages.append({
            'page': page_num,
            'clean_abs_path': os.path.join(paths['clean'], name),
        })
    pages.sort(key=lambda item: item['page'])
    return pages


def infer_homework_stage_status(
    paths: Dict[str, str],
    pages: List[Dict[str, Any]],
    manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    stages = _default_stage_status()
    if not pages:
        return stages

    layout_ready = all(
        os.path.isfile(_page_detect_path(paths, page))
        and os.path.isfile(_question_json_path(paths['pass1_json'], page['clean_abs_path']))
        and os.path.isfile(_page_layout_png_path(paths, page))
        for page in pages
    )
    if layout_ready:
        stages[HOMEWORK_STAGE_LAYOUT] = 'done'

    understanding_ready = all(
        os.path.isfile(_page_grade_path(paths, page))
        and os.path.isfile(_question_json_path(paths['pass1_json'], page['clean_abs_path']))
        and os.path.isfile(_page_understanding_png_path(paths, page))
        for page in pages
    )
    if understanding_ready:
        stages[HOMEWORK_STAGE_UNDERSTANDING] = 'done'

    manifest_status = str((manifest or {}).get('status') or '').strip().lower()
    if manifest_status == 'completed' or ((manifest or {}).get('stages') or {}).get(HOMEWORK_STAGE_GRADING) == 'done':
        stages[HOMEWORK_STAGE_GRADING] = 'done'
    return stages


def is_homework_stage_ready(
    paths: Dict[str, str],
    pages: List[Dict[str, Any]],
    manifest: Dict[str, Any],
    stage: str,
) -> bool:
    target = normalize_homework_target_stage(stage)
    stages = infer_homework_stage_status(paths, pages, manifest)
    if target == HOMEWORK_STAGE_LAYOUT:
        return stages[HOMEWORK_STAGE_LAYOUT] == 'done'
    if target == HOMEWORK_STAGE_UNDERSTANDING:
        return stages[HOMEWORK_STAGE_UNDERSTANDING] == 'done'
    from .completion import summarize_completion
    return (str(manifest.get('status') or '').strip().lower() == 'completed'
            or summarize_completion(manifest)['report_usable'])


def _build_manifest(
    username: str,
    filename: str,
    analysis_id: str,
    subject: str,
    pages: List[Dict[str, Any]],
    attrs: Dict[str, Any],
    status: str,
    source_document_sha256: str = '',
) -> Dict[str, Any]:
    manifest = {
        'analysis_type': 'homework_grading',
        'group_id': analysis_id,
        'username': username,
        'mode': 'single',
        'selected_files': [filename],
        'subject': subject,
        'subject_label': SUBJECT_LABELS.get(subject, '历史' if subject == 'history' else '未知学科'),
        'homework_attributes': normalize_homework_attrs(attrs),
        'status': status,
        'stages': _default_stage_status(),
        'created_at': datetime.datetime.now().isoformat(),
        'input_units': [
            {
                'unit_id': f'u{page["page"]:03d}',
                'source_file': filename,
                'page': page['page'],
                'seq': page['page'],
            }
            for page in pages
        ],
    }
    if source_document_sha256:
        manifest['source_document_sha256'] = source_document_sha256
        manifest['document_identity_version'] = 'source-sha256-v1'
    return manifest


def _build_prior_summary(pass1_dir: str, completed_page_nums: set, order_index: int, total_sessions: int, feedback_runtime=None) -> Optional[str]:
    from .note_evidence import is_notes
    if is_notes(feedback_runtime):
        return None
    if order_index <= 1 or not completed_page_nums:
        return None
    files = [
        path for path in sorted_json_pages(pass1_dir)
        if parse_page_num(os.path.basename(path)) in completed_page_nums
    ]
    if not files:
        return None
    body = aggregate_pages(files, **({'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {}))
    ranked = sorted(
        body.get('knowledge_point_frequency', []),
        key=lambda item: (item.get('error_count', 0), item.get('error_rate', 0)),
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


def _detect_page_job(
    page: Dict[str, Any],
    paths: Dict[str, str],
    subject: str,
    grade: int,
    stage: int,
    iteration_guidance: str = '',
    feedback_runtime=None,
) -> Dict[str, Any]:
    out_json = _question_json_path(paths['pass1_json'], page['clean_abs_path'])

    def _run() -> Dict[str, Any]:
        detect_page_only(
            page['clean_abs_path'],
            subject,
            page['page'],
            out_json,
            grade=grade,
            stage=stage,
            iteration_guidance=iteration_guidance,
            feedback_runtime=feedback_runtime,
        )
        return {'page': page['page'], 'json_path': out_json}

    return _run_pass1_page_with_retry(page['page'], 'Pass1版面检测', _run, feedback_runtime)


def _grade_page_job(
    page: Dict[str, Any],
    paths: Dict[str, str],
    subject: str,
    prior_context: Optional[str],
    grade: int,
    stage: int,
    source_document_sha256: str = '',
    iteration_guidance: str = '',
    feedback_runtime=None,
) -> Dict[str, Any]:
    out_json = _question_json_path(paths['pass1_json'], page['clean_abs_path'])

    def _run() -> Dict[str, Any]:
        if pass1_two_stage_enabled(feedback_runtime=feedback_runtime):
            model_image_path = (
                page.get(MODEL_IMAGE_PATH_KEY)
                or page['clean_abs_path']
            )
            grade_page_from_detect(
                model_image_path, subject, page['page'], out_json,
                prior_context=prior_context, grade=grade, stage=stage,
                iteration_guidance=iteration_guidance,
                feedback_runtime=feedback_runtime,
            )
        else:
            grade_page(
                page['clean_abs_path'], subject, page['page'], out_json,
                prior_context=prior_context, grade=grade, stage=stage,
                iteration_guidance=iteration_guidance,
                feedback_runtime=feedback_runtime,
            )
        if (
            pass1_two_stage_enabled(feedback_runtime=feedback_runtime)
            and (feedback_runtime is None or feedback_runtime.has_specialized(subject))
            and slot_presence_apply_approved(
                _page_clean_basename(page),
                subject,
                source_document_sha256=source_document_sha256,
                feedback_runtime=feedback_runtime,
            )
        ):
            presence_path = _page_slot_presence_path(paths, page)
            grade_path = _page_grade_path(paths, page)
            if os.path.isfile(presence_path) and os.path.isfile(grade_path):
                apply_slot_presence_guard_to_files(
                    grade_path,
                    out_json,
                    presence_path,
                    _page_clean_basename(page),
                    subject=subject,
                    source_document_sha256=source_document_sha256,
                    feedback_runtime=feedback_runtime,
                )
        if subject == 'math' and (feedback_runtime is None or feedback_runtime.has_specialized(subject)):
            grade_path = _page_grade_path(paths, page)
            apply_fixed_math_sample_guards_to_files(
                grade_path if os.path.isfile(grade_path) else out_json,
                out_json,
                page_num=page['page'],
                source_document_sha256=source_document_sha256,
                feedback_runtime=feedback_runtime,
            )
        return {'page': page['page'], 'json_path': out_json}

    return _run_pass1_page_with_retry(page['page'], 'Pass1逐页批改', _run, feedback_runtime)


def _run_detect_all_pages(
    task_id: str,
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    subject: str,
    grade: int,
    stage: int,
    pass1_workers: int,
    scope_page_nums: Optional[set[int]] = None,
    iteration_guidance: str = '',
    feedback_runtime=None,
) -> None:
    target_pages = [page for page in pages if scope_page_nums is None or page['page'] in scope_page_nums]
    if not target_pages:
        return
    _update_task(task_id, current_section='逐页版面检测')
    with ThreadPoolExecutor(max_workers=min(pass1_workers, len(target_pages))) as executor:
        futures = [
            executor.submit(
                _detect_page_job,
                page,
                paths,
                subject,
                grade,
                stage,
                iteration_guidance,
                feedback_runtime,
            )
            for page in target_pages
        ]
        for future in as_completed(futures):
            future.result()
    if scope_page_nums is None:
        from .note_evidence import is_notes
        if is_notes(feedback_runtime):
            from .note_page_links import backfill_note_detect_dir
            backfill_note_detect_dir(paths['pass1_json'])
        else:
            backfill_cross_page_detect_dir(paths['pass1_json'])
            backfill_parent_stems_in_detect_dir(paths['pass1_json'])
        backfill_same_page_detect_dir(paths['pass1_json'])


def _merge_detect_only_for_page(detect_path: str, merged_path: str, subject: str, page_num: int) -> None:
    detected = _normalize_detect_result(safe_json_load(detect_path), subject, page_num)
    merged = _merge_detect_and_grade(detected, {'questions': []}, subject, page_num)
    safe_json_dump(merged_path, merged)


def _merge_all_pages_from_detect(paths: Dict[str, str], pages: List[Dict[str, Any]], subject: str) -> None:
    for page in pages:
        detect_path = _page_detect_path(paths, page)
        merged_path = _question_json_path(paths['pass1_json'], page['clean_abs_path'])
        if not os.path.isfile(detect_path):
            continue
        _merge_detect_only_for_page(detect_path, merged_path, subject, page['page'])


def _build_page_session_labels(session_map: Optional[Dict[str, Any]]) -> Dict[int, str]:
    labels: Dict[int, str] = {}
    if not session_map or not isinstance(session_map.get('sessions'), list):
        return labels
    for session in session_map['sessions']:
        start, _end = session_page_bounds(session)
        labels[start] = _session_title(session)
    return labels


def _render_pages(
    paths: Dict[str, str],
    pages: List[Dict[str, Any]],
    modes: tuple,
    session_map: Optional[Dict[str, Any]] = None,
    scope_page_nums: Optional[set[int]] = None,
) -> None:
    labels = _build_page_session_labels(session_map)
    for page in pages:
        if scope_page_nums is not None and page['page'] not in scope_page_nums:
            continue
        json_path = _question_json_path(paths['pass1_json'], page['clean_abs_path'])
        if not os.path.isfile(json_path):
            continue
        render_page_selected_modes(
            json_path,
            page['clean_abs_path'],
            paths['annotated'],
            paths['annotated_layout'],
            paths['annotated_understanding'],
            modes=modes,
            session_label=labels.get(page['page']),
        )


def _run_pass1_grade_all_pages(
    task_id: str,
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    subject: str,
    grade: int,
    stage: int,
    pass1_workers: int,
    session_map: Optional[Dict[str, Any]],
    total_steps: int,
    completed_item: int,
    scope_page_nums: Optional[set[int]] = None,
    source_document_sha256: str = '',
    iteration_guidance: str = '',
    feedback_runtime=None,
) -> int:
    target_page_nums = set(scope_page_nums) if scope_page_nums is not None else {item['page'] for item in pages}
    if session_map and session_map.get('sessions'):
        sessions = sorted(session_map['sessions'], key=lambda item: item.get('order_index', 0))
        total_sessions = len(sessions)
        pages_by_num = {item['page']: item for item in pages}
        session_covered: set = set()
        for session in sessions:
            explicit = session.get('pages')
            if isinstance(explicit, list) and explicit:
                for p in explicit:
                    try:
                        session_covered.add(int(p))
                    except (TypeError, ValueError):
                        continue
            else:
                start, end = session_page_bounds(session)
                session_covered.update(range(start, end + 1))
        completed_page_nums: set = set()

        uncovered = [item for item in pages if item['page'] not in session_covered and item['page'] in target_page_nums]
        if uncovered:
            with ThreadPoolExecutor(max_workers=min(pass1_workers, len(uncovered))) as executor:
                future_to_page = {
                    executor.submit(
                        _grade_page_job,
                        item,
                        paths,
                        subject,
                        None,
                        grade,
                        stage,
                        source_document_sha256,
                        iteration_guidance,
                        feedback_runtime,
                    ): item
                    for item in uncovered
                }
                for future in as_completed(future_to_page):
                    page = future_to_page[future]
                    future.result()
                    completed_page_nums.add(page['page'])
                    completed_item += 1
                    _update_task(
                        task_id,
                        current_item=completed_item,
                        total_items=total_steps,
                        current_section=f'正在批改第{page["page"]}页',
                    )

        for session in sessions:
            start, end = session_page_bounds(session)
            order = session.get('order_index', session.get('session_index', 1))
            explicit = session.get('pages')
            if isinstance(explicit, list) and explicit:
                page_nums = []
                for p in explicit:
                    try:
                        page_nums.append(int(p))
                    except (TypeError, ValueError):
                        continue
                all_session_pages = [pages_by_num[pn] for pn in page_nums if pn in pages_by_num]
            else:
                all_session_pages = [pages_by_num[pn] for pn in range(start, end + 1) if pn in pages_by_num]
            session_pages = [item for item in all_session_pages if item['page'] in target_page_nums]
            if not session_pages:
                for item in all_session_pages:
                    completed_page_nums.add(item['page'])
                continue
            prior_ctx = _build_prior_summary(paths['pass1_json'], completed_page_nums, order, total_sessions, feedback_runtime)
            page_range = _page_range_label(start, end)
            prior_label = '，已参考前面错题' if prior_ctx else ''
            _update_task(
                task_id,
                current_item=completed_item,
                total_items=total_steps,
                current_section=f'正在批改第{order}/{total_sessions}篇（{page_range or f"{len(session_pages)}页"}{prior_label}）',
            )
            with ThreadPoolExecutor(max_workers=min(pass1_workers, len(session_pages))) as executor:
                future_to_page = {
                    executor.submit(
                        _grade_page_job,
                        item,
                        paths,
                        subject,
                        prior_ctx,
                        grade,
                        stage,
                        source_document_sha256,
                        iteration_guidance,
                        feedback_runtime,
                    ): item
                    for item in session_pages
                }
                for future in as_completed(future_to_page):
                    page = future_to_page[future]
                    future.result()
                    completed_item += 1
                    _update_task(
                        task_id,
                        current_item=completed_item,
                        total_items=total_steps,
                        current_section=f'已完成第{page["page"]}页，继续第{order}/{total_sessions}篇',
                    )
            for pn in range(start, end + 1):
                completed_page_nums.add(pn)
        return completed_item

    completed_pages_count = 0
    target_pages = [item for item in pages if item['page'] in target_page_nums]
    if not target_pages:
        return completed_item
    with ThreadPoolExecutor(max_workers=min(pass1_workers, len(target_pages))) as executor:
        future_to_page = {
            executor.submit(
                _grade_page_job,
                item,
                paths,
                subject,
                None,
                grade,
                stage,
                source_document_sha256,
                iteration_guidance,
                feedback_runtime,
            ): item
            for item in target_pages
        }
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            future.result()
            completed_pages_count += 1
            completed_item += 1
            _update_task(
                task_id,
                current_item=completed_item,
                total_items=total_steps,
                current_section=f'已完成第{page["page"]}页（{completed_pages_count}/{len(target_pages)}）',
            )
    return completed_item


def _run_u1_shadow_layout_all_pages(
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    subject: str,
    pass1_workers: int,
    scope_page_nums: Optional[set[int]] = None,
    feedback_runtime=None,
) -> None:
    if feedback_runtime is not None and not u1_shadow_enabled(subject, feedback_runtime=feedback_runtime):
        return
    target_pages = [page for page in pages if scope_page_nums is None or page['page'] in scope_page_nums]
    if not target_pages:
        return
    shadow_root = os.path.join(paths['base'], 'pass1_u1_shadow')
    layout_dir = os.path.join(shadow_root, 'layout')
    os.makedirs(layout_dir, exist_ok=True)

    def run_page(page: Dict[str, Any]) -> None:
        basename = os.path.splitext(os.path.basename(page['clean_abs_path']))[0]
        out_path = os.path.join(layout_dir, f'{basename}.layout.json')
        error_path = os.path.join(layout_dir, f'{basename}.layout.error.txt')
        try:
            detected = safe_json_load(_page_detect_path(paths, page))
            run_u1_shadow_layout_page(
                page['clean_abs_path'], subject, page['page'], detected, out_path,
                **({'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {}),
            )
        except Exception as exc:
            if os.path.isfile(out_path):
                os.remove(out_path)
            with open(error_path, 'w', encoding='utf-8') as file:
                file.write(str(exc))

    with ThreadPoolExecutor(max_workers=min(pass1_workers, len(target_pages))) as executor:
        futures = [executor.submit(run_page, page) for page in target_pages]
        for future in as_completed(futures):
            future.result()


def _run_slot_presence_layout_all_pages(
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    subject: str,
    pass1_workers: int,
    scope_page_nums: Optional[set[int]] = None,
    source_document_sha256: str = '',
    feedback_runtime=None,
) -> Dict[str, Any]:
    """Collect slot presence as lossless-layout evidence."""
    started = time.perf_counter()
    mode = slot_presence_mode(subject, feedback_runtime=feedback_runtime)
    if feedback_runtime is not None and not feedback_runtime.has_specialized('math'):
        return {'enabled': False, 'status': 'not_covered'}
    target_pages = [
        page for page in pages
        if (scope_page_nums is None or page['page'] in scope_page_nums)
        and (
            mode == 'shadow'
            or slot_presence_apply_approved(
                _page_clean_basename(page),
                subject,
                source_document_sha256=source_document_sha256,
                feedback_runtime=feedback_runtime,
            )
        )
    ]
    evidence_dir = os.path.join(paths['base'], 'layout_evidence', 'slot_presence')
    os.makedirs(evidence_dir, exist_ok=True)
    summary: Dict[str, Any] = {
        'enabled': True,
        'mode': mode,
        'subject': subject,
        'model': (feedback_runtime.dependencies['model_config']['roles']['qwen']['model']
                  if feedback_runtime is not None else homework_qwen_model()),
        'attempted_pages': len(target_pages),
        'successful_pages': 0,
        'failed_pages': 0,
        'expected_ids': 0,
        'returned_ids': 0,
        'missing_ids': 0,
        'extra_ids': 0,
        'slot_count': 0,
        'outside_formal_bbox_count': 0,
        'failures': [],
    }

    def run_page(page: Dict[str, Any]) -> Dict[str, Any]:
        basename = _page_clean_basename(page)
        out_path = os.path.join(evidence_dir, f'{basename}.presence.json')
        error_path = os.path.join(evidence_dir, f'{basename}.presence.error.txt')
        raw_path = page.get('raw_abs_path') or os.path.join(paths['raw'], f'{basename}.png')
        try:
            if not os.path.isfile(raw_path):
                raise FileNotFoundError(f'缺少原始页面图: {raw_path}')
            detected = safe_json_load(_page_detect_path(paths, page))
            _result, metadata = run_slot_presence_layout_page(
                raw_path,
                page['clean_abs_path'],
                subject,
                page['page'],
                detected,
                out_path,
                feedback_runtime=feedback_runtime,
            )
            if os.path.isfile(error_path):
                os.remove(error_path)
            return {
                'ok': True,
                'page': page['page'],
                'metadata': metadata,
            }
        except Exception as exc:
            if os.path.isfile(out_path):
                os.remove(out_path)
            with open(error_path, 'w', encoding='utf-8') as file:
                file.write(str(exc))
            return {'ok': False, 'page': page['page'], 'error': str(exc)}

    if target_pages:
        with ThreadPoolExecutor(max_workers=min(pass1_workers, len(target_pages))) as executor:
            futures = [executor.submit(run_page, page) for page in target_pages]
            for future in as_completed(futures):
                result = future.result()
                if not result['ok']:
                    summary['failed_pages'] += 1
                    summary['failures'].append({
                        'page': result['page'],
                        'error': result['error'],
                    })
                    continue
                summary['successful_pages'] += 1
                metadata = result['metadata']
                summary['expected_ids'] += len(metadata['expected_ids'])
                summary['returned_ids'] += len(metadata['returned_ids'])
                summary['missing_ids'] += len(metadata['missing_ids'])
                summary['extra_ids'] += len(metadata['extra_ids'])
                summary['slot_count'] += metadata['slot_count']
                summary['outside_formal_bbox_count'] += metadata[
                    'outside_formal_bbox_count'
                ]

    expected = summary['expected_ids']
    summary['id_coverage_rate'] = (
        round(summary['returned_ids'] / expected, 4) if expected else 0.0
    )
    summary['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    summary['failures'].sort(key=lambda item: item['page'])
    safe_json_dump(os.path.join(evidence_dir, 'summary.json'), summary)
    return summary


def _reapply_slot_presence_guards_for_pages(
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    subject: str,
    scope_page_nums: Optional[set[int]] = None,
    source_document_sha256: str = '',
    feedback_runtime=None,
) -> int:
    """Restore approved immutable slot locks after mutating downstream stages."""
    if slot_presence_mode(subject, feedback_runtime=feedback_runtime) != 'apply':
        return 0
    restored = 0
    for page in pages:
        if scope_page_nums is not None and page['page'] not in scope_page_nums:
            continue
        if not slot_presence_apply_approved(
            _page_clean_basename(page),
            subject,
            source_document_sha256=source_document_sha256,
            feedback_runtime=feedback_runtime,
        ):
            continue
        restored += reapply_slot_presence_guard_files(
            _page_grade_path(paths, page),
            _question_json_path(paths['pass1_json'], page['clean_abs_path']),
        )
    return restored


def _reapply_fixed_english_choice_guards_for_pages(
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    scope_page_nums: Optional[set[int]] = None,
    *, feedback_runtime=None, source_document_sha256: str = '',
) -> int:
    """Restore the exact English page-20 ROI locks after mutating stages."""
    restored = 0
    for page in pages:
        if not _frozen_action_allowed(feedback_runtime, 'english', page['page'],
                                      'fixed_english_choice_slots', source_document_sha256):
            continue
        if scope_page_nums is not None and page['page'] not in scope_page_nums:
            continue
        result_path = _question_json_path(
            paths['pass1_json'],
            page['clean_abs_path'],
        )
        if not os.path.exists(result_path):
            continue
        page_data = safe_json_load(result_path)
        page_restored = reapply_fixed_english_choice_guards(page_data)
        if page_restored:
            safe_json_dump(result_path, page_data)
            restored += page_restored
    return restored


def _reapply_fixed_english_page15_guards_for_pages(
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    scope_page_nums: Optional[set[int]] = None,
    *, feedback_runtime=None, source_document_sha256: str = '',
) -> int:
    """Restore the fixed English page-15 table transcription and verdict."""
    restored = 0
    for page in pages:
        if not _frozen_action_allowed(feedback_runtime, 'english', page['page'],
                                      'english_visual_transcription_lock', source_document_sha256):
            continue
        if scope_page_nums is not None and page['page'] not in scope_page_nums:
            continue
        result_path = _question_json_path(
            paths['pass1_json'],
            page['clean_abs_path'],
        )
        if not os.path.exists(result_path):
            continue
        page_data = safe_json_load(result_path)
        page_restored = reapply_fixed_english_page15_guard(page_data)
        if page_restored:
            safe_json_dump(result_path, page_data)
            restored += page_restored
    return restored


def _reapply_fixed_math_sample_guards_for_pages(
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    scope_page_nums: Optional[set[int]] = None,
    *, feedback_runtime=None, source_document_sha256: str = '',
) -> int:
    """Restore fixed math transcription and slot locks after mutating stages."""
    restored = 0
    for page in pages:
        if not _frozen_action_allowed(feedback_runtime, 'math', page['page'],
                                      'math_fixed_sample_guard', source_document_sha256):
            continue
        if scope_page_nums is not None and page['page'] not in scope_page_nums:
            continue
        final_path = _question_json_path(
            paths['pass1_json'],
            page['clean_abs_path'],
        )
        grade_path = _page_grade_path(paths, page)
        restored += reapply_fixed_math_sample_guard_files(
            grade_path if os.path.isfile(grade_path) else final_path,
            final_path,
        )
    return restored


def _frozen_action_allowed(runtime, subject, page, action, source_hash):
    if runtime is None:
        return True
    from .special_cases import match_document_special_case
    return bool(match_document_special_case(subject, page, action,
                source_document_sha256=source_hash, feedback_runtime=runtime))


def _run_u1_shadow_all_pages(
    pages: List[Dict[str, Any]],
    paths: Dict[str, str],
    subject: str,
    pass1_workers: int,
    scope_page_nums: Optional[set[int]] = None,
    feedback_runtime=None,
) -> Dict[str, Any]:
    """Collect U1 evidence without changing or blocking the official Pass1 result."""
    if feedback_runtime is not None and not u1_shadow_enabled(subject, feedback_runtime=feedback_runtime):
        return {'enabled': False, 'status': 'not_covered'}
    started = time.perf_counter()
    target_pages = [page for page in pages if scope_page_nums is None or page['page'] in scope_page_nums]
    shadow_dir = os.path.join(paths['base'], 'pass1_u1_shadow')
    layout_dir = os.path.join(shadow_dir, 'layout')
    transcription_dir = os.path.join(shadow_dir, 'transcription')
    os.makedirs(transcription_dir, exist_ok=True)

    summary: Dict[str, Any] = {
        'enabled': True,
        'subject': subject,
        'model': (feedback_runtime.dependencies['model_config']['roles']['qwen']['model']
                  if feedback_runtime is not None else homework_qwen_model()),
        'layout_prompt_version': PASS1_U1_LAYOUT_PROMPT_VERSION,
        'transcription_prompt_version': PASS1_U1_SHADOW_PROMPT_VERSION,
        'layout_pages': len(target_pages),
        'layout_successful_pages': 0,
        'layout_fallback_pages': 0,
        'split_parent_count': 0,
        'split_child_count': 0,
        'transcription_attempted_pages': len(target_pages),
        'transcription_successful_pages': 0,
        'transcription_failed_pages': 0,
        'expected_ids': 0,
        'returned_ids': 0,
        'missing_ids': 0,
        'extra_ids': 0,
        'comparable_ids': 0,
        'exact_matches': 0,
        'normalized_matches': 0,
        'unmatched_shadow_ids': [],
        'unmatched_formal_ids': [],
        'differences': [],
        'layout_failures': [],
        'failures': [],
    }

    def read_optional_text(path: str) -> str:
        if not os.path.isfile(path):
            return ''
        with open(path, 'r', encoding='utf-8') as file:
            return file.read().strip()

    def run_page(page: Dict[str, Any]) -> Dict[str, Any]:
        basename = os.path.splitext(os.path.basename(page['clean_abs_path']))[0]
        out_path = os.path.join(transcription_dir, f'{basename}.u1.json')
        error_path = os.path.join(transcription_dir, f'{basename}.u1.error.txt')
        layout_path = os.path.join(layout_dir, f'{basename}.layout.json')
        layout_error_path = os.path.join(layout_dir, f'{basename}.layout.error.txt')
        detect_path = _page_detect_path(paths, page)
        official_path = _question_json_path(paths['pass1_json'], page['clean_abs_path'])
        layout_info = {
            'layout_ok': False,
            'split_parents': [],
            'split_children': [],
            'layout_error': '',
        }
        try:
            formal_detected = safe_json_load(detect_path)
            detected = safe_json_load(layout_path) if os.path.isfile(layout_path) else formal_detected
            official = safe_json_load(official_path)
            formal_detect_ids = {
                str(item.get('id') or '').strip()
                for item in formal_detected.get('questions') or [] if isinstance(item, dict)
            }
            layout_ids = {
                str(item.get('id') or '').strip()
                for item in detected.get('questions') or [] if isinstance(item, dict)
            }
            split_parents = [
                qid for qid in formal_detect_ids
                if qid not in layout_ids and any(child.startswith(f'{qid}-') for child in layout_ids)
            ]
            layout_info = {
                'layout_ok': os.path.isfile(layout_path) and not os.path.isfile(layout_error_path),
                'split_parents': split_parents,
                'split_children': [
                    qid for qid in layout_ids
                    if any(qid.startswith(f'{parent}-') for parent in split_parents)
                ],
                'layout_error': read_optional_text(layout_error_path),
            }
            shadow, metadata = run_u1_shadow_page(
                page['clean_abs_path'], subject, page['page'], detected, out_path,
                **({'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {}),
            )
            if os.path.isfile(error_path):
                os.remove(error_path)
            official_by_id = {
                str(item.get('id') or '').strip(): str(item.get('student_answer') or '').strip()
                for item in official.get('questions') or [] if isinstance(item, dict)
            }
            formal_ids = set(official_by_id)
            shadow_ids = {str(item.get('id') or '').strip() for item in shadow['questions']}
            comparisons = []
            for item in shadow['questions']:
                qid = item['id']
                if qid not in official_by_id:
                    continue
                u1_answer = item['student_answer']
                official_answer = official_by_id[qid]
                exact = u1_answer == official_answer
                normalized = comparison_text(u1_answer) == comparison_text(official_answer)
                comparisons.append({
                    'page': page['page'],
                    'id': qid,
                    'u1_student_answer': u1_answer,
                    'official_student_answer': official_answer,
                    'exact_match': exact,
                    'normalized_match': normalized,
                })
            return {
                'ok': True,
                'page': page['page'],
                'metadata': metadata,
                'comparisons': comparisons,
                **layout_info,
                'unmatched_shadow_ids': sorted(shadow_ids - formal_ids),
                'unmatched_formal_ids': sorted(formal_ids - shadow_ids),
            }
        except Exception as exc:
            if os.path.isfile(out_path):
                os.remove(out_path)
            with open(error_path, 'w', encoding='utf-8') as file:
                file.write(str(exc))
            return {'ok': False, 'page': page['page'], 'error': str(exc), **layout_info}

    if target_pages:
        with ThreadPoolExecutor(max_workers=min(pass1_workers, len(target_pages))) as executor:
            futures = [executor.submit(run_page, page) for page in target_pages]
            for future in as_completed(futures):
                result = future.result()
                if result['layout_ok']:
                    summary['layout_successful_pages'] += 1
                else:
                    summary['layout_fallback_pages'] += 1
                summary['split_parent_count'] += len(result['split_parents'])
                summary['split_child_count'] += len(result['split_children'])
                if result['layout_error']:
                    summary['layout_failures'].append({
                        'page': result['page'], 'error': result['layout_error'],
                    })
                if not result['ok']:
                    summary['transcription_failed_pages'] += 1
                    summary['failures'].append({'page': result['page'], 'error': result['error']})
                    continue
                summary['transcription_successful_pages'] += 1
                summary['unmatched_shadow_ids'].extend(
                    {'page': result['page'], 'id': qid} for qid in result['unmatched_shadow_ids']
                )
                summary['unmatched_formal_ids'].extend(
                    {'page': result['page'], 'id': qid} for qid in result['unmatched_formal_ids']
                )
                metadata = result['metadata']
                summary['expected_ids'] += len(metadata['expected_ids'])
                summary['returned_ids'] += len(metadata['returned_ids'])
                summary['missing_ids'] += len(metadata['missing_ids'])
                summary['extra_ids'] += len(metadata['extra_ids'])
                for comparison in result['comparisons']:
                    summary['comparable_ids'] += 1
                    summary['exact_matches'] += int(comparison['exact_match'])
                    summary['normalized_matches'] += int(comparison['normalized_match'])
                    if not comparison['exact_match']:
                        summary['differences'].append(comparison)

    expected = summary['expected_ids']
    comparable = summary['comparable_ids']
    summary['id_coverage_rate'] = round(summary['returned_ids'] / expected, 4) if expected else 0.0
    summary['exact_answer_match_rate'] = round(summary['exact_matches'] / comparable, 4) if comparable else 0.0
    summary['normalized_answer_match_rate'] = round(summary['normalized_matches'] / comparable, 4) if comparable else 0.0
    summary['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    summary['unmatched_shadow_ids'].sort(key=lambda item: (item['page'], item['id']))
    summary['unmatched_formal_ids'].sort(key=lambda item: (item['page'], item['id']))
    summary['differences'].sort(key=lambda item: (item['page'], item['id']))
    summary['layout_failures'].sort(key=lambda item: item['page'])
    summary['failures'].sort(key=lambda item: item['page'])
    safe_json_dump(os.path.join(shadow_dir, 'summary.json'), summary)
    return summary


def _stages_needed_for_target(
    paths: Dict[str, str],
    pages: List[Dict[str, Any]],
    manifest: Dict[str, Any],
    target_stage: str,
) -> List[str]:
    current = infer_homework_stage_status(paths, pages, manifest)
    from .completion import summarize_completion
    if any(item['stage'] != 'quality' for item in summarize_completion(manifest)['issues']):
        current[HOMEWORK_STAGE_GRADING] = 'pending'
    needed: List[str] = []
    for stage in HOMEWORK_STAGES_ORDER:
        if current.get(stage) == 'done':
            continue
        needed.append(stage)
        if stage == target_stage:
            break
    return needed


@managed_execution
def execute_staged_homework_grading(
    task_id: str,
    username: str,
    filename: str,
    analysis_id: str,
    paths: Dict[str, str],
    homework_attrs: Optional[Dict[str, Any]],
    target_stage: Optional[str],
    build_page_units_fn,
    scope_page_nums: Optional[set[int]] = None,
    force_preprocess_scope: bool = False,
    preprocess_mode: str = PREPROCESS_MODE_AUTO,
    feedback_runtime=None,
) -> None:
    from .artifact_transaction import recover_transaction
    recover_transaction(paths['base'])
    runtime_kwargs = {'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {}
    from .feedback_runtime import runtime_attributes
    from .feedback_request import legacy_homework_attributes
    attrs = normalize_homework_attrs(homework_attrs)
    preprocess_meta_path = paths.get('preprocess_meta') or os.path.join(
        paths['base'],
        'preprocess_meta.json',
    )
    preprocess_candidate_dir = paths.get('preprocess_candidates') or os.path.join(
        paths['base'],
        'preprocess_candidates',
    )
    subject = attrs.get('homework_subject') or 'unknown'
    grade = attrs.get('homework_grade') or 4
    stage = stage_of_grade(grade)
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
        attrs = legacy_homework_attributes(feedback_runtime.context)
        preprocess_mode = feedback_runtime.dependencies['preprocessing']['mode']
    resolved_target = normalize_homework_target_stage(target_stage)
    if not pass1_two_stage_enabled(**runtime_kwargs):
        resolved_target = HOMEWORK_STAGE_GRADING

    sample_id = _sample_id(analysis_id)
    pages = load_homework_clean_pages(paths)
    manifest: Dict[str, Any] = {}
    session_map: Optional[Dict[str, Any]] = None
    sessions_json_path: Optional[str] = None

    if os.path.isfile(paths['manifest']):
        manifest = safe_json_load(paths['manifest'])
    if manifest.get('dependency_restart') == 'layout':
        pages = []
    if feedback_runtime is not None:
        from .feedback_snapshot_reader import read_feedback_snapshot
        snapshot = read_feedback_snapshot(os.path.dirname(paths['manifest']))
        if snapshot['snapshot_status'] != 'complete' or snapshot['config_fingerprint'] != feedback_runtime.fingerprint:
            raise ValueError('执行工作区快照与冻结运行依据不一致')
        manifest['feedback_context'] = feedback_runtime.context
        manifest['homework_attributes'] = attrs

    from .feedback_artifacts import mark_stage, validate_artifacts
    if feedback_runtime is not None:
        mark_stage(paths, manifest, 'preprocess')
    pdf_path = _resolve_user_file_path(username, filename)
    # analysis_digest = str(analysis_id or '').removeprefix('homework_').lower()
    analysis_digest = str(analysis_id or '').lower()
    if analysis_digest.startswith('homework_'):
        analysis_digest = analysis_digest[9:]  # len('homework_') == 9
    expected_sha256_prefix = (
        analysis_digest
        if len(analysis_digest) == 24
        and all(char in '0123456789abcdef' for char in analysis_digest)
        else ''
    )
    source_document_sha256 = resolve_source_document_sha256(
        paths['base'],
        pdf_path,
        expected_sha256_prefix=expected_sha256_prefix,
    )
    if source_document_sha256:
        manifest['source_document_sha256'] = source_document_sha256
        manifest['document_identity_version'] = 'source-sha256-v1'

    if force_preprocess_scope:
        if not pdf_path or not os.path.isfile(pdf_path):
            raise ValueError('作业PDF不存在')
        if not filename.lower().endswith('.pdf'):
            raise ValueError('作业批改通道仅支持PDF')
        if not scope_page_nums:
            raise ValueError('完整篇目迭代缺少页面范围')
        write_sample_meta(
            paths['base'],
            subject,
            sample_id,
            grade,
            source_document_sha256=source_document_sha256,
            source_filename=filename,
            **runtime_kwargs,
        )
        _update_task(task_id, current_section='重新预处理所选篇目页面')
        preprocess_pdf(
            pdf_path, paths['raw'], paths['clean'], subject, sample_id,
            page_numbers=sorted(scope_page_nums),
            preprocess_mode=preprocess_mode,
            metadata_path=preprocess_meta_path,
            candidate_dir=preprocess_candidate_dir,
            **runtime_kwargs,
        )
        pages = load_homework_clean_pages(paths)

    if not pages:
        if not pdf_path or not os.path.isfile(pdf_path):
            raise ValueError('作业PDF不存在')
        if not filename.lower().endswith('.pdf'):
            raise ValueError('作业批改通道仅支持PDF')
        write_sample_meta(
            paths['base'],
            subject,
            sample_id,
            grade,
            source_document_sha256=source_document_sha256,
            source_filename=filename,
            **runtime_kwargs,
        )
        _update_task(task_id, current_section='预处理PDF页面')
        pages = preprocess_pdf(
            pdf_path,
            paths['raw'],
            paths['clean'],
            subject,
            sample_id,
            preprocess_mode=preprocess_mode,
            metadata_path=preprocess_meta_path,
            candidate_dir=preprocess_candidate_dir,
            **runtime_kwargs,
        )
        if not pages:
            raise ValueError('PDF未生成可批改页面')
        initial_manifest = _build_manifest(
            username,
            filename,
            analysis_id,
            subject,
            pages,
            attrs,
            'running',
            source_document_sha256,
        )
        manifest.update(initial_manifest)
        if feedback_runtime is not None:
            manifest['homework_attributes'] = attrs
        manifest['preprocess'] = preprocess_manifest_entry(
            load_preprocess_metadata(preprocess_meta_path)
        )
        safe_json_dump(paths['manifest'], manifest)
        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'sessions')
        _update_task(task_id, current_section='识别作业篇目结构')
        sessions_json_path = build_pre_pass1_session_map(
            subject=subject,
            sample_id=sample_id,
            pdf_path=pdf_path,
            clean_dir=paths['clean'],
            report_dir=paths['pass2_report'],
            **runtime_kwargs,
        )
        session_map = safe_json_load(sessions_json_path) if sessions_json_path and os.path.exists(sessions_json_path) else None
    else:
        write_sample_meta(
            paths['base'],
            subject,
            sample_id,
            grade,
            source_document_sha256=source_document_sha256,
            source_filename=filename,
            **runtime_kwargs,
        )
        sessions_json_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_sessions.json')
        if os.path.isfile(sessions_json_path):
            session_map = safe_json_load(sessions_json_path)

    # 批改配置卡（可选增强）：仅文件名完全匹配时覆盖篇次 + 已布置页集合；无匹配零影响
    _cfg_mat = None
    try:
        from app_chat.grading_config_card import (
            build_session_map_from_config,
            resolve_material_for_filename,
        )
        _cfg_mat = resolve_material_for_filename(username, filename)
        if _cfg_mat is None:
            print(f'[grading-config] 无匹配配置（零影响） filename={filename}', flush=True)
    except Exception as _cfg_exc:
        print(f'[grading-config] 解析失败，回退现网: {_cfg_exc}')
        _cfg_mat = None
    if _cfg_mat:
        _total_pages = len(pages) if pages else int((session_map or {}).get('total_pages') or 0)
        if _total_pages <= 0:
            raise ValueError('批改配置卡已匹配，但文档页数为 0，无法按配置批改')
        session_map = build_session_map_from_config(
            _cfg_mat,
            subject=subject,
            sample_id=sample_id,
            total_pages=_total_pages,
        )
        if feedback_runtime is not None:
            from .feedback_runtime import stamp_feedback
            session_map = stamp_feedback(session_map, feedback_runtime, 'sessions')
        sessions_json_path = os.path.join(
            paths['pass2_report'], f'{subject}_{sample_id}_sessions.json'
        )
        os.makedirs(paths['pass2_report'], exist_ok=True)
        safe_json_dump(sessions_json_path, session_map)
        _assigned = set(session_map.get('grading_config', {}).get('assigned_pages') or [])
        if not _assigned:
            # 禁止「匹配到配置却无有效页」时静默退回全页批改
            raise ValueError(
                '批改配置卡已匹配该材料，但有效已布置页为空（页码可能超出文档页数），已中止以免误跑全页'
            )
        if scope_page_nums is not None:
            scope_page_nums = set(scope_page_nums) & _assigned
            if not scope_page_nums:
                raise ValueError('批改配置卡已布置页与当前所选篇目无交集')
        else:
            scope_page_nums = set(_assigned)
        manifest['grading_config'] = session_map.get('grading_config') or {}
        safe_json_dump(paths['manifest'], manifest)
        print(
            f'[grading-config] 已应用配置卡 filename={filename} '
            f'assigned={sorted(_assigned)} unassigned='
            f'{session_map.get("grading_config", {}).get("unassigned_pages")}'
        )
    else:
        # 删卡/改标识后未再匹配：勿沿用上次配置卡切出来的篇目（否则旧布置页会继续生效）
        stale_cfg = (
            isinstance(session_map, dict)
            and (
                str(session_map.get('split_source') or '') == 'grading_config_card'
                or isinstance(session_map.get('grading_config'), dict)
            )
        )
        if stale_cfg:
            print(
                f'[grading-config] 无匹配配置但残留配置卡篇目，重新识别 filename={filename}',
                flush=True,
            )
            if feedback_runtime is not None:
                mark_stage(paths, manifest, 'sessions')
            sessions_json_path = build_pre_pass1_session_map(
                subject=subject,
                sample_id=sample_id,
                pdf_path=pdf_path,
                clean_dir=paths['clean'],
                report_dir=paths['pass2_report'],
                **runtime_kwargs,
            )
            session_map = (
                safe_json_load(sessions_json_path)
                if sessions_json_path and os.path.exists(sessions_json_path)
                else None
            )
            if isinstance(manifest.get('grading_config'), dict):
                manifest.pop('grading_config', None)
                safe_json_dump(paths['manifest'], manifest)

    preprocess_metadata = load_preprocess_metadata(preprocess_meta_path)
    if preprocess_metadata:
        manifest['preprocess'] = preprocess_manifest_entry(preprocess_metadata)
    elif not isinstance(manifest.get('preprocess'), dict):
        manifest['preprocess'] = preprocess_manifest_entry({})

    if scope_page_nums is not None:
        missing_pages = sorted(set(scope_page_nums) - {item['page'] for item in pages})
        if missing_pages:
            raise ValueError(f'所选篇目页面缺失: {missing_pages}')
    scoped_pages = [page for page in pages if scope_page_nums is None or page['page'] in scope_page_nums]
    if not scoped_pages:
        raise ValueError('没有可执行迭代的篇目页面')
    from .feedback_observation import update_runtime_observation
    update_runtime_observation(task_id, paths, manifest, pdf_path, feedback_runtime, len(pages))

    iteration_context = load_iteration_context(paths)
    layout_iteration_guidance = compile_iteration_guidance(
        iteration_context,
        HOMEWORK_STAGE_LAYOUT,
        scope_page_nums,
        **runtime_kwargs,
    )
    understanding_iteration_guidance = compile_iteration_guidance(
        iteration_context,
        HOMEWORK_STAGE_UNDERSTANDING,
        scope_page_nums,
        **runtime_kwargs,
    )
    grading_iteration_guidance = compile_iteration_guidance(
        iteration_context,
        HOMEWORK_STAGE_GRADING,
        scope_page_nums,
        **runtime_kwargs,
    )

    if pass1_two_stage_enabled(**runtime_kwargs):
        fixed_crossout_summary = prepare_fixed_sample_crossout_images(
            scoped_pages,
            paths['base'],
            subject,
            feedback_runtime=feedback_runtime,
            source_document_sha256=source_document_sha256,
        )
    else:
        fixed_crossout_summary = {
            'enabled': False,
            'mode': 'fixed_sample_allowlist',
            'reason': 'requires_two_stage_pass1',
            'applied_page_count': 0,
        }

    manifest.setdefault('stages', _default_stage_status())
    manifest['target_stage'] = resolved_target
    manifest['fixed_sample_crossout_repair'] = fixed_crossout_summary
    safe_json_dump(paths['manifest'], manifest)

    stages_to_run = _stages_needed_for_target(paths, pages, manifest, resolved_target)
    if feedback_runtime is not None:
        from .execution_checkpoints import receipt_matches, record_stage_receipt
        ordered = [HOMEWORK_STAGE_LAYOUT, HOMEWORK_STAGE_UNDERSTANDING, HOMEWORK_STAGE_GRADING]
        needed = ordered[:ordered.index(resolved_target) + 1]
        invalid = next((i for i, name in enumerate(needed) if not receipt_matches(paths, manifest, name)), None)
        if invalid is not None:
            stages_to_run = [name for name in needed if name in stages_to_run or name in needed[invalid:]]
    from .stage_dependencies import enabled as scoped_dependencies
    if resolved_target == 'grading' and not stages_to_run and scoped_dependencies(feedback_runtime):
        from .artifact_transaction import candidate_transaction
        render_changed = not receipt_matches(paths, manifest, 'render')
        if render_changed:
            mark_stage(paths, manifest, 'render')
            def render_candidate(candidate):
                _render_pages(candidate, pages, modes=('layout', 'understanding', 'grading'), session_map=session_map)
                validate_artifacts(candidate, pages, manifest, 'grading', expected_pages=manifest.get('source_page_count'))
            candidate_transaction(paths, render_candidate, include_images=True)
            record_stage_receipt(paths, manifest, 'render')
        if render_changed or not receipt_matches(paths, manifest, 'quality'):
            mark_stage(paths, manifest, 'quality')
            manifest['red_blue_review'] = {'status': 'pending'}
            safe_json_dump(paths['manifest'], manifest)
            try:
                review = evaluate_homework_red_blue(paths, manifest, **runtime_kwargs)
            except Exception as exc:
                review = {'status': 'failed', 'error': str(exc)}
            manifest['red_blue_review'] = {key: review.get(key) for key in ('status', 'score', 'color', 'error')}
            if review.get('status') == 'ready':
                record_stage_receipt(paths, manifest, 'quality')
        from .completion import finish_delivery
        report = safe_json_load(os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_report.json'))
        finish_delivery(manifest, report)
        manifest['output_validation'] = {'status': 'passed', 'target_stage': 'grading'}
        manifest['updated_at'] = datetime.datetime.now().isoformat()
        safe_json_dump(paths['manifest'], manifest)
        CIIndexManager.update_status(username, analysis_id, manifest['status'])
        return
    pass1_workers = _pass1_parallelism(len(scoped_pages), **runtime_kwargs)
    total_steps = len(scoped_pages) + 8
    completed_item = 1

    if HOMEWORK_STAGE_LAYOUT in stages_to_run:
        mark_stage(paths, manifest, 'layout')
        manifest['stages'][HOMEWORK_STAGE_LAYOUT] = 'running'
        manifest['processing_stage'] = 'layout'
        safe_json_dump(paths['manifest'], manifest)
        _update_task(task_id, current_item=1, total_items=total_steps, current_section='准备逐页版面检测')
        if pass1_two_stage_enabled(**runtime_kwargs):
            _run_detect_all_pages(
                task_id, pages, paths, subject, grade, stage, pass1_workers,
                scope_page_nums=scope_page_nums,
                iteration_guidance=layout_iteration_guidance,
                **runtime_kwargs,
            )
            _merge_all_pages_from_detect(paths, scoped_pages, subject)
        else:
            completed_item = _run_pass1_grade_all_pages(
                task_id, pages, paths, subject, grade, stage, pass1_workers, session_map, total_steps, completed_item,
                scope_page_nums=scope_page_nums,
                source_document_sha256=source_document_sha256,
                iteration_guidance=understanding_iteration_guidance,
                **runtime_kwargs,
            )
        if u1_shadow_enabled(subject, **runtime_kwargs) and pass1_two_stage_enabled(**runtime_kwargs):
            _update_task(task_id, current_section='生成无损版面影子拆分')
            _run_u1_shadow_layout_all_pages(
                pages, paths, subject, pass1_workers, scope_page_nums=scope_page_nums,
                **runtime_kwargs,
            )
        if slot_presence_layout_enabled(subject, **runtime_kwargs) and pass1_two_stage_enabled(**runtime_kwargs):
            _update_task(task_id, current_section='采集槽位级作答存在性证据')
            _run_slot_presence_layout_all_pages(
                pages, paths, subject, pass1_workers, scope_page_nums=scope_page_nums,
                source_document_sha256=source_document_sha256,
                **runtime_kwargs,
            )
        _update_task(task_id, current_section='渲染无损版面')
        _render_pages(paths, pages, modes=('layout',), session_map=session_map, scope_page_nums=scope_page_nums)
        manifest['stages'][HOMEWORK_STAGE_LAYOUT] = 'done'
        if feedback_runtime is not None:
            record_stage_receipt(paths, manifest, HOMEWORK_STAGE_LAYOUT)
        update_runtime_observation(task_id, paths, manifest, pdf_path, feedback_runtime, len(pages))
        manifest['status'] = 'partial'
        manifest['updated_at'] = datetime.datetime.now().isoformat()
        manifest['input_units'] = build_page_units_fn(paths, filename, analysis_id)
        safe_json_dump(paths['manifest'], manifest)
        CIIndexManager.update_status(username, analysis_id, 'partial')

    if HOMEWORK_STAGE_UNDERSTANDING in stages_to_run:
        mark_stage(paths, manifest, 'understanding')
        manifest['stages'][HOMEWORK_STAGE_UNDERSTANDING] = 'running'
        manifest['processing_stage'] = 'understanding'
        safe_json_dump(paths['manifest'], manifest)
        _update_task(task_id, current_section='准备逐页理解批改')
        completed_item = _run_pass1_grade_all_pages(
            task_id, pages, paths, subject, grade, stage, pass1_workers, session_map, total_steps, completed_item,
            scope_page_nums=scope_page_nums,
            source_document_sha256=source_document_sha256,
            iteration_guidance=understanding_iteration_guidance,
            **runtime_kwargs,
        )
        if u1_shadow_enabled(subject, **runtime_kwargs):
            _update_task(task_id, current_section='采集无损理解影子证据')
            _run_u1_shadow_all_pages(
                pages, paths, subject, pass1_workers, scope_page_nums=scope_page_nums,
                **runtime_kwargs,
            )
        _update_task(task_id, current_section='渲染无损理解')
        _render_pages(paths, pages, modes=('understanding',), session_map=session_map, scope_page_nums=scope_page_nums)
        manifest['stages'][HOMEWORK_STAGE_UNDERSTANDING] = 'done'
        if feedback_runtime is not None:
            record_stage_receipt(paths, manifest, HOMEWORK_STAGE_UNDERSTANDING)
        update_runtime_observation(task_id, paths, manifest, pdf_path, feedback_runtime, len(pages))
        manifest['status'] = 'partial'
        manifest['updated_at'] = datetime.datetime.now().isoformat()
        manifest['input_units'] = build_page_units_fn(paths, filename, analysis_id)
        safe_json_dump(paths['manifest'], manifest)
        CIIndexManager.update_status(username, analysis_id, 'partial')

    if HOMEWORK_STAGE_GRADING in stages_to_run:
        # 克隆旧版本重跑时，上一轮检查失败提示不能冒充本轮结果。
        manifest['warnings'] = [warning for warning in manifest.get('warnings', []) if warning not in (
            '规则基线未生成，本次诊断仅使用已保存的材料证据。',
            '批改结果复核未完成，已有结果已保留，请人工核实后使用。',
            '部分反馈未通过核验，已保留有效内容；待复核项不作为确定结论。')]
        manifest['content_validation'] = {'status': 'inconclusive'}
        _update_task(task_id, warnings=manifest['warnings'], content_validation=manifest['content_validation'])
        manifest['stages'][HOMEWORK_STAGE_GRADING] = 'running'
        manifest['processing_stage'] = 'grading'
        safe_json_dump(paths['manifest'], manifest)

        stage_status = infer_homework_stage_status(paths, pages, manifest)
        if stage_status.get(HOMEWORK_STAGE_UNDERSTANDING) != 'done':
            _update_task(task_id, current_section='准备逐页批改')
            completed_item = _run_pass1_grade_all_pages(
                task_id, pages, paths, subject, grade, stage, pass1_workers, session_map, total_steps, completed_item,
                scope_page_nums=scope_page_nums,
                source_document_sha256=source_document_sha256,
                iteration_guidance=understanding_iteration_guidance,
                **runtime_kwargs,
            )

        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'cross_page')
        _update_task(task_id, current_item=len(scoped_pages) + 1, total_items=total_steps, current_section='补全跨页题目')
        pass1_5_is_enabled = pass1_5_enabled(**runtime_kwargs)
        cross_page_corrections = resolve_cross_pages(
            paths['pass1_json'], paths['clean'], subject, sample_id, scope_page_nums=scope_page_nums,
            **runtime_kwargs,
        )
        _reapply_slot_presence_guards_for_pages(
            pages,
            paths,
            subject,
            scope_page_nums=scope_page_nums,
            source_document_sha256=source_document_sha256,
            **runtime_kwargs,
        )
        _reapply_fixed_english_choice_guards_for_pages(
            pages,
            paths,
            scope_page_nums=scope_page_nums,
        **({'feedback_runtime': feedback_runtime, 'source_document_sha256': source_document_sha256} if feedback_runtime is not None else {}))
        _reapply_fixed_english_page15_guards_for_pages(
            pages,
            paths,
            scope_page_nums=scope_page_nums,
        **({'feedback_runtime': feedback_runtime, 'source_document_sha256': source_document_sha256} if feedback_runtime is not None else {}))
        _reapply_fixed_math_sample_guards_for_pages(
            pages,
            paths,
            scope_page_nums=scope_page_nums,
        **({'feedback_runtime': feedback_runtime, 'source_document_sha256': source_document_sha256} if feedback_runtime is not None else {}))
        manifest['pass1_5'] = {
            'enabled': pass1_5_is_enabled,
            'correction_count': len(cross_page_corrections),
            'corrections': cross_page_corrections,
        }
        if not pass1_5_is_enabled:
            manifest['pass1_5']['skipped_reason'] = 'HOMEWORK_PASS1_5_ENABLED 未开启'
        from .note_evidence import is_notes
        if is_notes(feedback_runtime):
            audit_path = os.path.join(paths['base'], 'feedback_cross_page_audit.json')
            # paths['base']为homework_grading目录；审计状态与仍待确认的关联一并返回。
            if os.path.exists(audit_path):
                link_audit = safe_json_load(audit_path)
                link_status = link_audit.get('status')
                manifest['pass1_5']['status'] = link_status
                if link_status in ('disabled', 'unresolved_no_source_match', 'completed_with_warnings'):
                    manifest.setdefault('warnings', []).append('笔记跨页关联未完全确认，相关单元保留待确认状态。')

        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'review')
        _update_task(task_id, current_item=len(scoped_pages) + 2, total_items=total_steps, current_section='逐页复核批改结果')
        review_stats = review_pass1_dir(
            paths['pass1_json'], scoped_pages, subject, grade=grade, stage=stage, workers=pass1_workers,
            source_document_sha256=source_document_sha256,
            **runtime_kwargs,
        )
        from .completion import review_coverage
        coverage = review_coverage([p['page'] for p in scoped_pages], review_stats.get('details', []))
        previous_coverage = (manifest.get('pass1_review') or {}).get('coverage') or {}
        outside = {p['page'] for p in pages} - set(coverage['expected_pages'])
        # 配置卡未布置页本轮故意不批，不得并入 expected/incomplete
        _gc_cov = (manifest.get('grading_config') or {}) if isinstance(manifest, dict) else {}
        _unassigned_cov = {int(p) for p in (_gc_cov.get('unassigned_pages') or [])}
        if _unassigned_cov:
            outside -= _unassigned_cov
        if outside:
            completed = set(coverage['completed_pages']) | (set(previous_coverage.get('completed_pages', [])) & outside)
            skipped = set(coverage['policy_skipped_pages']) | (set(previous_coverage.get('policy_skipped_pages', [])) & outside)
            expected_union = ({p['page'] for p in pages} - _unassigned_cov) if _unassigned_cov else {p['page'] for p in pages}
            coverage.update(expected_pages=sorted(expected_union),
                            completed_pages=sorted(completed), policy_skipped_pages=sorted(skipped),
                            incomplete_pages=sorted(expected_union - completed))
        manifest['pass1_review'] = {
            'coverage': coverage,
            'reviewed_pages': sorted(set(
                d['page'] for d in review_stats.get('details', [])
                if not d.get('skipped') and not d.get('error') and not d.get('quota_limited')) |
                (set((manifest.get('pass1_review') or {}).get('reviewed_pages', [])) & outside)),
            'required_units': review_stats.get('required_units', []) + [
                u for u in (manifest.get('pass1_review') or {}).get('required_units', [])
                if int(u['qid_global'].split(':')[0][1:]) in outside],
            'enabled': review_stats.get('enabled', True),
            'model': review_stats.get('model', ''),
            'scope': review_stats.get('scope', ''),
            'workers': review_stats.get('workers', 0),
            'reuse_existing': review_stats.get('reuse_existing', True),
            'pages_reused': review_stats.get('pages_reused', 0),
            'stop_on_quota': review_stats.get('stop_on_quota', True),
            'quota_limited': review_stats.get('quota_limited', False),
            'pages_reviewed': review_stats.get('pages_reviewed', 0),
            'pages_skipped': review_stats.get('pages_skipped', 0),
            'issues_found': review_stats.get('issues_found', 0),
            'corrections_applied': review_stats.get('corrections_applied', 0),
            'errors': review_stats.get('errors', 0),
            'failures': review_stats.get('failures', []),
        }

        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'verification')
        _update_task(task_id, current_item=len(scoped_pages) + 3, total_items=total_steps, current_section='复核学科规则')
        verification_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_verification.json')
        verification_report = verify_pass1_dir(
            subject,
            paths['pass1_json'],
            verification_path,
            apply=True,
            page_nums=scope_page_nums,
            source_document_sha256=source_document_sha256,
            **runtime_kwargs,
        )
        manifest['verification'] = {'total_discrepancies': verification_report.get('total_discrepancies', 0)}

        answer_statement_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_answer_statement_verification.json')
        answer_statement_report = verify_answer_statements(
            subject, paths['pass1_json'], answer_statement_path, apply=True, page_nums=scope_page_nums,
            **runtime_kwargs,
        )
        slot_presence_restored_after_review = _reapply_slot_presence_guards_for_pages(
            pages,
            paths,
            subject,
            scope_page_nums=scope_page_nums,
            source_document_sha256=source_document_sha256,
            **runtime_kwargs,
        )
        fixed_english_choice_restored_after_review = (
            _reapply_fixed_english_choice_guards_for_pages(
                pages,
                paths,
                scope_page_nums=scope_page_nums,
            **({'feedback_runtime': feedback_runtime, 'source_document_sha256': source_document_sha256} if feedback_runtime is not None else {}))
        )
        fixed_english_page15_restored_after_review = (
            _reapply_fixed_english_page15_guards_for_pages(
                pages,
                paths,
                scope_page_nums=scope_page_nums,
            **({'feedback_runtime': feedback_runtime, 'source_document_sha256': source_document_sha256} if feedback_runtime is not None else {}))
        )
        fixed_math_sample_restored_after_review = (
            _reapply_fixed_math_sample_guards_for_pages(
                pages,
                paths,
                scope_page_nums=scope_page_nums,
            **({'feedback_runtime': feedback_runtime, 'source_document_sha256': source_document_sha256} if feedback_runtime is not None else {}))
        )
        manifest['answer_statement_verification'] = {
            'total_discrepancies': answer_statement_report.get('total_discrepancies', 0),
            'corrections_applied': answer_statement_report.get('corrections_applied', 0),
        }
        manifest['slot_presence_guard'] = {
            'mode': slot_presence_mode(subject, **runtime_kwargs),
            'restored_after_review': slot_presence_restored_after_review,
        }
        manifest['fixed_english_choice_guard'] = {
            'restored_after_review': fixed_english_choice_restored_after_review,
        }
        manifest['fixed_english_page15_guard'] = {
            'restored_after_review': fixed_english_page15_restored_after_review,
        }
        manifest['fixed_math_sample_guard'] = {
            'restored_after_review': fixed_math_sample_restored_after_review,
        }

        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'memory')
        _update_task(task_id, current_item=len(scoped_pages) + 4, total_items=total_steps, current_section='汇总错题线索')
        from .note_evidence import is_notes, normalize_note_dir
        from .material_markings import normalize_markings_dir, open_material_runtime, open_units
        normalize_markings_dir(paths['pass1_json'], feedback_runtime=feedback_runtime, page_nums=scope_page_nums)
        if is_notes(feedback_runtime):
            normalize_note_dir(paths['pass1_json'], feedback_runtime=feedback_runtime, page_nums=scope_page_nums)
        memory = build_memory(paths['pass1_json'], subject, sample_id, **runtime_kwargs)
        save_memory(memory, paths['pass2_report'], subject, sample_id)
        try:
            session_memories = build_all_session_memories(
                paths['pass1_json'], paths['pass2_report'], subject, sample_id, sessions_json_path=sessions_json_path,
                **runtime_kwargs,
            )
        except Exception as exc:
            manifest['session_memory'] = {'status': 'failed', 'error': str(exc)}
            safe_json_dump(paths['manifest'], manifest)
            # 必要记忆失败不能伪装成无材料，保留实际阶段供恢复。
            raise
        manifest['session_memory'] = {'status': 'ready'}
        try:
            profile = build_student_profile(paths['pass2_report'], subject, sample_id, **runtime_kwargs)
            manifest['rule_profile'] = {'status': 'ready'}
        except Exception as exc:
            manifest['rule_profile'] = {'status': 'failed', 'error': str(exc)}
            manifest['warnings'] = list(dict.fromkeys(manifest.get('warnings', []) + [
                '规则基线未生成，本次诊断仅使用已保存的材料证据。']))
            _update_task(task_id, warnings=manifest['warnings'])
            profile = None
        manifest['session_count'] = len(session_memories)

        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'ontology')
        _update_task(task_id, current_section='生成整篇学习诊断')
        sample_meta = load_sample_meta(paths['base']) or {'subject': subject, 'grade': grade, 'stage': stage_of_grade(grade)}
        ontology = build_ontology(
            subject=subject,
            sample_id=sample_id,
            base_dir=paths['base'],
            report_dir=paths['pass2_report'],
            sample_meta=sample_meta,
            session_memories=session_memories,
            profile=profile,
            iteration_guidance=grading_iteration_guidance,
            pass1_dir=paths.get('pass1_json') or '',
            **runtime_kwargs,
        )
        manifest['ontology'] = {
            'built': bool(ontology),
            'fallback_used': bool(ontology.get('fallback_used')) if ontology else False,
            'built_by': ontology.get('built_by') if ontology else '',
        }

        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'report')
        _update_task(task_id, current_item=len(scoped_pages) + 5, total_items=total_steps, current_section='整理问题与提升建议')
        report_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_report.json')
        thinking_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}.thinking.txt')
        analyze_pass2(
            memory,
            subject,
            sample_id,
            report_path,
            thinking_path,
            profile=None,
            ontology=ontology,
            iteration_guidance=grading_iteration_guidance,
            **runtime_kwargs,
        )
        # 配置卡：在报告正文侧写入「未布置页」说明（不打分、不进三区）
        try:
            _gc = (manifest.get('grading_config') or {}) if isinstance(manifest, dict) else {}
            _unassigned = _gc.get('unassigned_pages') or []
            if _unassigned:
                _rep = safe_json_load(report_path) if os.path.isfile(report_path) else {}
                if isinstance(_rep, dict):
                    _note = (
                        '未布置页：'
                        + ','.join(str(p) for p in _unassigned)
                        + '（本轮未批改）'
                    )
                    _rep['unassigned_pages'] = list(_unassigned)
                    _rep['unassigned_pages_note'] = _note
                    _rep['grading_config'] = {
                        'assigned_pages': _gc.get('assigned_pages') or [],
                        'unassigned_pages': list(_unassigned),
                        'note': _note,
                    }
                    safe_json_dump(report_path, _rep)
        except Exception as _un_exc:
            print(f'[grading-config] 写入未布置页说明失败: {_un_exc}')

        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'hallucination')
        _update_task(task_id, current_item=len(scoped_pages) + 6, total_items=total_steps, current_section='复核批改结果')
        hallucination_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_hallucination.json')
        ontology_path = os.path.join(paths['base'], 'student_ontology.json')
        from .artifact_transaction import candidate_transaction

        def finalize_candidate(paths, rebuilt=False):
            from .evidence_contract import semantic_facts, validate_final_evidence
            def read_pages():
                return [safe_json_load(p) for p in sorted_json_pages(paths['pass1_json'])]
            before_facts = semantic_facts(read_pages())
            report_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_report.json')
            ontology_path = os.path.join(paths['base'], 'student_ontology.json')
            hallucination_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_hallucination.json')
            candidate_sessions = (os.path.join(paths['pass2_report'], os.path.basename(sessions_json_path))
                                  if sessions_json_path else None)
            candidate_stats = {key: {} for key in ('slot_presence_guard', 'fixed_english_choice_guard',
                                                  'fixed_english_page15_guard', 'fixed_math_sample_guard')}
            hallucination_report = run_hallucination_filter(
                subject, paths['pass1_json'], report_path, hallucination_path,
                ontology_path=ontology_path if os.path.exists(ontology_path) else None,
                stage=stage, page_nums=scope_page_nums,
                **runtime_kwargs,
            )

            candidate_stats['slot_presence_guard']['restored_after_hallucination'] = (
                _reapply_slot_presence_guards_for_pages(
                    pages,
                    paths,
                    subject,
                    scope_page_nums=scope_page_nums,
                    source_document_sha256=source_document_sha256,
                    **runtime_kwargs,
                )
            )
            candidate_stats['fixed_english_choice_guard']['restored_after_hallucination'] = (
                _reapply_fixed_english_choice_guards_for_pages(
                    pages,
                    paths,
                    scope_page_nums=scope_page_nums,
                **({'feedback_runtime': feedback_runtime, 'source_document_sha256': source_document_sha256} if feedback_runtime is not None else {}))
            )
            candidate_stats['fixed_english_page15_guard']['restored_after_hallucination'] = (
                _reapply_fixed_english_page15_guards_for_pages(
                    pages,
                    paths,
                    scope_page_nums=scope_page_nums,
                **({'feedback_runtime': feedback_runtime, 'source_document_sha256': source_document_sha256} if feedback_runtime is not None else {}))
            )
            candidate_stats['fixed_math_sample_guard']['restored_after_hallucination'] = (
                _reapply_fixed_math_sample_guards_for_pages(
                    pages,
                    paths,
                    scope_page_nums=scope_page_nums,
                **({'feedback_runtime': feedback_runtime, 'source_document_sha256': source_document_sha256} if feedback_runtime is not None else {}))
            )

            from .note_evidence import is_notes, validate_note_ontology, validate_note_feedback, align_note_report, normalize_feedback_zones
            if open_material_runtime(feedback_runtime):
                # 复核可回写Pass1/诊断/批语，输出前再次核验，不能绕过笔记证据约束。
                normalize_markings_dir(paths['pass1_json'], feedback_runtime=feedback_runtime, page_nums=scope_page_nums)
                if is_notes(feedback_runtime):
                    normalize_note_dir(paths['pass1_json'], feedback_runtime=feedback_runtime, page_nums=scope_page_nums)
            final_memory = build_memory(paths['pass1_json'], subject, sample_id, **runtime_kwargs)
            save_memory(final_memory, paths['pass2_report'], subject, sample_id, **runtime_kwargs)
            final_sessions = build_all_session_memories(paths['pass1_json'], paths['pass2_report'], subject, sample_id,
                                       sessions_json_path=candidate_sessions, **runtime_kwargs)
            if semantic_facts(read_pages()) != before_facts:
                if rebuilt:
                    raise ValueError('再次复核仍改变事实依据，已停止自动重算并保留原结果')
                from .execution_control import current_execution
                execution = current_execution()
                if execution is not None:
                    execution.remaining()
                final_profile = build_student_profile(paths['pass2_report'], subject, sample_id, **runtime_kwargs)
                final_ontology = build_ontology(subject=subject, sample_id=sample_id, base_dir=paths['base'],
                    report_dir=paths['pass2_report'], sample_meta=sample_meta, session_memories=final_sessions,
                    profile=final_profile, iteration_guidance=grading_iteration_guidance,
                    pass1_dir=paths.get('pass1_json') or '', **runtime_kwargs)
                analyze_pass2(final_memory, subject, sample_id, report_path,
                    os.path.join(paths['pass2_report'], f'{subject}_{sample_id}.thinking.txt'),
                    profile=None, ontology=final_ontology, iteration_guidance=grading_iteration_guidance, **runtime_kwargs)
                return finalize_candidate(paths, rebuilt=True)
            if open_material_runtime(feedback_runtime):
                final_ontology = safe_json_load(ontology_path)
                final_report = safe_json_load(report_path)
                validate_note_ontology(final_ontology, open_units(final_memory, feedback_runtime.context['material_type']))
                normalize_feedback_zones(final_report, final_ontology)
                validate_note_feedback(final_report, final_memory, final_ontology,
                                       material_type=feedback_runtime.context['material_type'])
                align_note_report(final_report)
                safe_json_dump(report_path, final_report)
            # 幻觉复核可能回写理解或报告，前言必须与最终页面绑定（所有材料适用）。
            from .page_feedback import page_evidence, normalize_page_contexts
            final_pages = []
            for page_file in sorted_json_pages(paths['pass1_json']):
                page_data = safe_json_load(page_file)
                final_pages.append(page_evidence(page_data, page_data['page']))
            final_report = safe_json_load(report_path)
            final_report['page_feedback_contexts'] = normalize_page_contexts(
                final_report.get('page_feedback_contexts'), final_pages)
            # 幻觉复核后仍保留配置卡未布置页说明
            _gc2 = (manifest.get('grading_config') or {}) if isinstance(manifest, dict) else {}
            _ua2 = _gc2.get('unassigned_pages') or []
            if _ua2:
                _note2 = '未布置页：' + ','.join(str(p) for p in _ua2) + '（本轮未批改）'
                final_report['unassigned_pages'] = list(_ua2)
                final_report['unassigned_pages_note'] = _note2
                final_report['grading_config'] = {
                    'assigned_pages': _gc2.get('assigned_pages') or [],
                    'unassigned_pages': list(_ua2),
                    'note': _note2,
                }
            safe_json_dump(report_path, final_report)
            from .grader_pass2 import _validate_runtime_feedback
            if feedback_runtime is not None:
                _validate_runtime_feedback(final_report, final_memory)
            validate_final_evidence(final_report, safe_json_load(ontology_path) if os.path.isfile(ontology_path) else {}, read_pages(),
                                    manifest['pass1_review'].get('required_units', []), manifest['pass1_review'].get('reviewed_pages', []))
            _render_pages(paths, pages, modes=('understanding', 'grading'), session_map=session_map)
            if feedback_runtime is not None:
                validate_artifacts(paths, pages, manifest, 'grading', expected_pages=manifest.get('source_page_count'))
            return {'filter': hallucination_report, 'guards': candidate_stats, 'rebuilt': rebuilt}

        try:
            finalized = candidate_transaction(paths, finalize_candidate, include_images=True)
            manifest['postprocess'] = {'status': 'published', 'rebuild_count': int(finalized['rebuilt'])}
            hallucination_report = finalized['filter']
            for key, value in finalized['guards'].items():
                manifest[key].update(value)
        except Exception as exc:
            from .artifact_transaction import transaction_pending
            if transaction_pending(paths['base']):
                raise
            traceback.print_exc()
            try:
                from .yangqian_debug import debug_log
                debug_log(f'[homework_grading] 终态复核未发布: {exc}', extra_dir=paths.get('base'))
            except Exception:
                pass
            manifest['postprocess'] = {'status': 'rejected', 'error': str(exc)}
            hallucination_report = {'status': 'failed', 'total_issues': None,
                                    'corrections_applied_count': None, 'error': str(exc)}
            safe_json_dump(hallucination_path, hallucination_report)
            manifest['warnings'] = list(dict.fromkeys(manifest.get('warnings', []) + [
                '批改结果复核未完成，已有结果已保留，请人工核实后使用。']))
            manifest['content_validation'] = {'status': 'inconclusive', 'failed_checks': ['hallucination']}
            _update_task(task_id, warnings=manifest['warnings'], content_validation=manifest['content_validation'])
        manifest['hallucination'] = {
            'status': hallucination_report.get('status', 'ready'),
            'error': hallucination_report.get('error', ''),
            'total_issues': hallucination_report.get('total_issues', 0),
            'corrections_applied': hallucination_report.get('corrections_applied_count', 0),
        }
        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'render')
        _update_task(task_id, current_item=len(scoped_pages) + 7, total_items=total_steps, current_section='渲染三区批改')
        # 成功候选已连同图片发布；失败时仅为保留的事实生成一致的可查看图片。
        if manifest.get('postprocess', {}).get('status') != 'published':
            _render_pages(paths, pages, modes=('understanding', 'grading'), session_map=session_map)

        _update_task(task_id, current_section='生成批改质量红蓝卡标')
        if feedback_runtime is not None:
            mark_stage(paths, manifest, 'output_validation')
            output_warnings = validate_artifacts(paths, pages, manifest, 'grading',
                expected_pages=manifest.get('source_page_count'))
            manifest['output_validation'] = {'status': 'passed', 'target_stage': 'grading'}
            manifest['warnings'] = list(dict.fromkeys(manifest.get('warnings', []) + output_warnings))
            _update_task(task_id, warnings=manifest['warnings'])
            mark_stage(paths, manifest, 'quality')
        try:
            if ((manifest.get('material_evidence') or {}).get('status') == 'incomplete'
                    or manifest.get('postprocess', {}).get('status') != 'published' or any(
                    u.get('status') != 'completed' for u in manifest['pass1_review'].get('required_units', []))):
                raise ValueError('批改证据尚未通过复核，暂不生成质量评分')
            red_blue_review = evaluate_homework_red_blue(paths, manifest, **runtime_kwargs)
        except Exception as exc:
            traceback.print_exc()
            red_blue_review = {
                'status': 'failed',
                'score': None,
                'color': '',
                'error': str(exc) or '红蓝卡标评分失败',
            }
        manifest['red_blue_review'] = {
            'status': red_blue_review.get('status', 'failed'),
            'score': red_blue_review.get('score'),
            'color': red_blue_review.get('color', ''),
            'error': red_blue_review.get('error', ''),
        }
        if feedback_runtime is not None and red_blue_review.get('status') != 'ready':
            manifest['warnings'] = list(dict.fromkeys(manifest.get('warnings', []) + [
                '批改结果已保留，但质量评分未成功；可在结果中单独重试评分']))
            _update_task(task_id, warnings=manifest['warnings'])
        final_report = safe_json_load(report_path)
        pending = final_report.get('content_validation', {}).get('status') == 'needs_review'
        if pending:
            manifest['content_validation'] = dict(final_report['content_validation'],
                failed_checks=manifest.get('content_validation', {}).get('failed_checks', []))
            manifest['warnings'] = list(dict.fromkeys(manifest.get('warnings', []) + [
                '部分反馈未通过核验，已保留有效内容；待复核项不作为确定结论。']))
            _update_task(task_id, warnings=manifest['warnings'], content_validation=manifest['content_validation'])
        manifest['stages'][HOMEWORK_STAGE_GRADING] = 'done'
        if feedback_runtime is not None:
            record_stage_receipt(paths, manifest, HOMEWORK_STAGE_GRADING)
            if scoped_dependencies(feedback_runtime):
                record_stage_receipt(paths, manifest, 'render')
                if red_blue_review.get('status') == 'ready':
                    record_stage_receipt(paths, manifest, 'quality')
        from .completion import finish_delivery
        completion = finish_delivery(manifest, final_report)
        try:
            from .verify_suggestions import generate_verify_suggestions
            _update_task(task_id, current_section='生成核验可点短句', completed=False)
            generate_verify_suggestions(
                paths, manifest,
                feedback_runtime=feedback_runtime,
                prefer_keep_llm=False,
            )
        except Exception as sug_exc:
            traceback.print_exc()
            try:
                from .yangqian_debug import debug_log
                debug_log(f'[homework_grading] 核验可点短句生成失败: {sug_exc}', extra_dir=paths.get('base'))
            except Exception:
                pass
        try:
            from .result_cards import pin_grading_result_cards
            pin_grading_result_cards(paths, manifest, feedback_runtime=feedback_runtime)
        except Exception as pin_exc:
            from .yangqian_debug import debug_log
            debug_log(f'[homework_grading] 钉结果卡失败: {pin_exc}', extra_dir=paths.get('base'))
            traceback.print_exc()
            manifest.setdefault('warnings', [])
            w = '批改结果已保留，本子结果卡未自动生成，可稍后重试沉淀。'
            if w not in manifest['warnings']:
                manifest['warnings'].append(w)
        manifest['updated_at'] = datetime.datetime.now().isoformat()
        manifest['input_units'] = build_page_units_fn(paths, filename, analysis_id)
        safe_json_dump(paths['manifest'], manifest)
        CIIndexManager.update_status(username, analysis_id, manifest['status'])
        return

    if feedback_runtime is not None:
        mark_stage(paths, manifest, 'output_validation')
        output_warnings = validate_artifacts(paths, pages, manifest, resolved_target,
            expected_pages=manifest.get('source_page_count'))
        manifest['output_validation'] = {'status': 'passed', 'target_stage': resolved_target}
        manifest['warnings'] = list(dict.fromkeys(manifest.get('warnings', []) + output_warnings))
        _update_task(task_id, warnings=manifest['warnings'])
    from .completion import finish_delivery
    finish_delivery(manifest)
    manifest['updated_at'] = datetime.datetime.now().isoformat()
    manifest['input_units'] = build_page_units_fn(paths, filename, analysis_id)
    safe_json_dump(paths['manifest'], manifest)
    CIIndexManager.update_status(username, analysis_id, 'partial')
