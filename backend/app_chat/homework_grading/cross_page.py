from .feedback_runtime import frozen_environment
import logging
from .feedback_runtime import stamp_feedback

import os
from typing import Any, Dict, List, Optional, Set, Tuple

from app_chat.homework_grading.grader_pass1_5 import grade_cross_page_group
from app_chat.homework_grading.utils import is_final_pass1_page_json, parse_page_num, safe_json_dump, safe_json_load


logger = logging.getLogger(__name__)

MAX_PAGES_PER_GROUP = 3


def pass1_5_enabled(*, feedback_runtime=None) -> bool:
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_5_ENABLED', '0').strip().lower()
    return raw in ('1', 'true', 'yes', 'y', 'on')


def _iter_page_json_files(pass1_dir: str) -> List[str]:
    if not os.path.isdir(pass1_dir):
        return []
    paths = []
    for name in os.listdir(pass1_dir):
        if not is_final_pass1_page_json(name):
            continue
        page_num = parse_page_num(name)
        if page_num <= 0:
            continue
        paths.append(os.path.join(pass1_dir, name))
    return sorted(paths, key=lambda path: (parse_page_num(os.path.basename(path)), os.path.basename(path)))


def _load_all_page_jsons(pass1_dir: str) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, str]]:
    all_jsons: Dict[int, Dict[str, Any]] = {}
    path_by_page: Dict[int, str] = {}
    for json_path in _iter_page_json_files(pass1_dir):
        try:
            data = safe_json_load(json_path)
        except Exception as exc:
            logger.warning('跳过无法读取的 Pass1 JSON %s: %s', json_path, exc)
            continue
        page_num = int(data.get('page') or parse_page_num(os.path.basename(json_path)))
        if page_num <= 0:
            continue
        all_jsons[page_num] = data
        path_by_page[page_num] = json_path
    return all_jsons, path_by_page


def scan_boundaries(pass1_dir: str) -> Dict[int, Dict[str, Any]]:
    boundaries: Dict[int, Dict[str, Any]] = {}
    all_jsons, _ = _load_all_page_jsons(pass1_dir)
    for page_num, data in all_jsons.items():
        boundary = data.get('boundary') or {}
        if not isinstance(boundary, dict):
            continue
        if boundary.get('continues_from_prev') or boundary.get('continues_to_next'):
            boundaries[page_num] = boundary
    return boundaries


def build_cross_page_groups(
    boundaries: Dict[int, Dict[str, Any]],
    all_page_nums: List[int],
    *,
    max_pages_per_group: Optional[int] = None,
) -> List[List[int]]:
    if not boundaries:
        return []

    limit = MAX_PAGES_PER_GROUP if max_pages_per_group is None else int(max_pages_per_group)
    if limit < 2:
        limit = 2

    all_page_set = set(all_page_nums)
    candidate_pages = set()
    for page_num, boundary in boundaries.items():
        candidate_pages.add(page_num)
        if boundary.get('continues_from_prev') and (page_num - 1) in all_page_set:
            candidate_pages.add(page_num - 1)
        if boundary.get('continues_to_next') and (page_num + 1) in all_page_set:
            candidate_pages.add(page_num + 1)

    pages = sorted(candidate_pages)
    if not pages:
        return []

    groups: List[List[int]] = []
    current_group = [pages[0]]
    for page_num in pages[1:]:
        if page_num == current_group[-1] + 1:
            current_group.append(page_num)
        else:
            groups.append(current_group)
            current_group = [page_num]
    groups.append(current_group)

    final_groups: List[List[int]] = []
    for group in groups:
        if len(group) <= limit:
            final_groups.append(group)
            continue
        start = 0
        while start < len(group):
            window = group[start:start + limit]
            if len(window) >= 2:
                final_groups.append(window)
            if start + limit >= len(group):
                break
            start += limit - 1
    return final_groups


def _is_uncertain_cross_page_error(question: Dict[str, Any], page_data: Dict[str, Any]) -> bool:
    if str(question.get('verdict') or '').strip() != 'uncertain':
        return False
    if '跨页' not in str(question.get('error_type') or ''):
        return False
    boundary = page_data.get('boundary') or {}
    return bool(boundary.get('continues_from_prev'))


def _question_needs_resolution(question: Dict[str, Any], page_data: Dict[str, Any]) -> bool:
    if question.get('cross_page') and not question.get('cross_page_resolved'):
        return True
    return _is_uncertain_cross_page_error(question, page_data)


def _can_apply_correction(question: Dict[str, Any], page_data: Dict[str, Any]) -> bool:
    if question.get('cross_page'):
        return True
    if str(question.get('verdict') or '').strip() == 'uncertain':
        return True
    return _is_uncertain_cross_page_error(question, page_data)


def _collect_pending_questions(
    group: List[int],
    all_jsons: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    pending: List[Dict[str, Any]] = []
    for page_num in group:
        page_data = all_jsons.get(page_num, {})
        for question in page_data.get('questions') or []:
            if not isinstance(question, dict):
                continue
            if not _question_needs_resolution(question, page_data):
                continue
            pending.append({
                'page': page_num,
                'id': str(question.get('id') or '').strip(),
                'stem_excerpt': str(question.get('stem_excerpt') or '').strip(),
                'student_answer': str(question.get('student_answer') or '').strip(),
                'verdict': str(question.get('verdict') or '').strip(),
                'error_type': str(question.get('error_type') or '').strip(),
                'cross_page': bool(question.get('cross_page')),
            })
    return pending


def group_needs_resolution(group: List[int], all_jsons: Dict[int, Dict[str, Any]]) -> bool:
    for page_num in group:
        page_data = all_jsons.get(page_num, {})
        for question in page_data.get('questions') or []:
            if isinstance(question, dict) and _question_needs_resolution(question, page_data):
                return True
    return False


def merge_corrections(all_jsons: Dict[int, Dict[str, Any]], result: Dict[str, Any]) -> List[Dict[str, Any]]:
    modified: List[Dict[str, Any]] = []
    for correction in result.get('corrections') or []:
        try:
            page_num = int(correction.get('page'))
        except (TypeError, ValueError):
            continue
        question_id = str(correction.get('id') or '').strip()
        new_verdict = correction.get('verdict')
        if page_num not in all_jsons or not question_id:
            continue
        for question in all_jsons[page_num].get('questions') or []:
            if str(question.get('id') or '').strip() != question_id:
                continue
            page_data = all_jsons[page_num]
            if not _can_apply_correction(question, page_data):
                break
            old_verdict = question.get('verdict')
            question.update({
                'verdict': new_verdict or old_verdict,
                'correct_answer': correction.get('correct_answer', question.get('correct_answer')),
                'error_type': correction.get('error_type', question.get('error_type', '')),
                'knowledge_point': correction.get('knowledge_point', question.get('knowledge_point', '')),
                'cross_page': correction.get('cross_page', question.get('cross_page', True)),
                'cross_page_resolved': correction.get('cross_page_resolved', bool(new_verdict and new_verdict != 'uncertain')),
            })
            modified.append({
                'page': page_num,
                'id': question_id,
                'old': old_verdict,
                'new': question.get('verdict'),
            })
            break
    return modified


def _find_clean_image(clean_dir: str, page_num: int) -> str:
    if not os.path.isdir(clean_dir):
        return ''
    for name in sorted(os.listdir(clean_dir)):
        if not name.lower().endswith('.png'):
            continue
        if parse_page_num(name) == page_num:
            return os.path.join(clean_dir, name)
    return ''


def resolve_cross_pages(
    pass1_dir: str,
    clean_dir: str,
    subject: str,
    sample_id: str,
    scope_page_nums: Optional[Set[int]] = None,
*, feedback_runtime=None) -> List[Dict[str, Any]]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    audit = []
    def finish(value, status):
        if feedback_runtime is not None:
            safe_json_dump(os.path.join(os.path.dirname(os.path.abspath(pass1_dir)), 'feedback_cross_page_audit.json'),
                           stamp_feedback({'status': status, 'groups': audit}, feedback_runtime, 'cross_page'))
        return value
    if not pass1_5_enabled(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})):
        logger.info(
            '[%s-%s] Pass 1.5 跳过：HOMEWORK_PASS1_5_ENABLED 未开启',
            subject,
            sample_id,
        )
        return finish([], 'disabled')

    all_jsons, path_by_page = _load_all_page_jsons(pass1_dir)
    if not all_jsons:
        logger.info('[%s-%s] Pass 1.5 跳过：没有可读取的 Pass1 JSON', subject, sample_id)
        return finish([], 'no_pages')

    if feedback_runtime is not None:
        for page in all_jsons.values():
            if page.get('feedback_execution', {}).get('config_fingerprint') != feedback_runtime.fingerprint:
                finish([], 'configuration_mismatch')
                raise ValueError('跨页输入与本轮配置不一致，必须重新生成')
    boundaries = scan_boundaries(pass1_dir)
    if not boundaries:
        logger.info('[%s-%s] 无跨页标记，Pass 1.5 跳过', subject, sample_id)
        return finish([], 'no_cross_page')

    max_pages = MAX_PAGES_PER_GROUP
    if feedback_runtime is not None:
        from .feedback_material_kinds import cross_page_max_pages
        max_pages = cross_page_max_pages((feedback_runtime.context or {}).get('material_type'))
    groups = build_cross_page_groups(
        boundaries, sorted(all_jsons.keys()), max_pages_per_group=max_pages,
    )
    logger.info('[%s-%s] 检测到跨页页面 %s，跨页组 %s', subject, sample_id, sorted(boundaries.keys()), groups)

    all_corrections: List[Dict[str, Any]] = []
    for group in groups:
        if scope_page_nums is not None and not (set(group) & set(scope_page_nums)):
            continue
        if not group_needs_resolution(group, all_jsons):
            logger.info('跨页组 %s 内无待修补跨页题，跳过', group)
            continue

        image_paths = []
        for page_num in group:
            image_path = _find_clean_image(clean_dir, page_num)
            if not image_path:
                logger.warning('找不到第 %d 页清洁图片，跳过跨页组 %s', page_num, group)
                image_paths = []
                break
            image_paths.append(image_path)
        if not image_paths:
            audit.append({'group': group, 'status': 'missing_image'})
            continue

        try:
            pending_questions = _collect_pending_questions(group, all_jsons)
            result = grade_cross_page_group(
                image_paths,
                subject,
                group,
                boundaries,
                pending_questions=pending_questions,
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        except Exception as exc:
            logger.warning('跨页组 %s 修补失败，保留原 Pass1 结果: %s', group, exc)
            audit.append({'group': group, 'status': 'failed', 'error': str(exc)})
            continue
        audit.append({'group': group, 'status': 'completed'})
        corrections = merge_corrections(all_jsons, result)
        all_corrections.extend(corrections)
        for page_num in group:
            json_path = path_by_page.get(page_num)
            if json_path and page_num in all_jsons:
                safe_json_dump(json_path, stamp_feedback(all_jsons[page_num], feedback_runtime, 'cross_page'))

    if all_corrections:
        logger.info('[%s-%s] Pass 1.5 完成，修正 %d 道题', subject, sample_id, len(all_corrections))
    else:
        logger.info('[%s-%s] Pass 1.5 完成，无题目被修正', subject, sample_id)
    return finish(all_corrections, 'completed_with_warnings' if any(x['status']!='completed' for x in audit) else 'completed')
