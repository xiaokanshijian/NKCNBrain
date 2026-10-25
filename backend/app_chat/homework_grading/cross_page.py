from .stage_dependencies import artifact_compatible
from .feedback_runtime import frozen_environment
import logging
from .evidence_contract import material_dependency, material_groups, valid_material_quotes, combine_material_groups
from .feedback_runtime import stamp_feedback

import os
import copy
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app_chat.homework_grading.grader_pass1_5 import grade_cross_page_group
from app_chat.homework_grading.utils import sorted_json_pages, parse_page_num, safe_json_dump, safe_json_load


logger = logging.getLogger(__name__)

MAX_PAGES_PER_GROUP = 3


def pass1_5_enabled(*, feedback_runtime=None) -> bool:
    from .note_evidence import is_notes
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_5_ENABLED', '1' if is_notes(feedback_runtime) else '0').strip().lower()
    return raw in ('1', 'true', 'yes', 'y', 'on')


def _iter_page_json_files(pass1_dir: str) -> List[str]:
    return sorted_json_pages(pass1_dir)


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


def merge_corrections(all_jsons: Dict[int, Dict[str, Any]], result: Dict[str, Any], *, feedback_runtime=None,
                      group=None, scope_page_nums=None) -> List[Dict[str, Any]]:
    from .note_evidence import is_notes
    notes = is_notes(feedback_runtime)
    if notes:
        return _merge_note_checks(all_jsons, result, group or [], scope_page_nums)[0]
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
            from .material_markings import MARKING_FIELDS, normalize_markings, open_material_runtime
            if open_material_runtime(feedback_runtime):
                for field in MARKING_FIELDS:
                    if field in correction:
                        question[field] = copy.deepcopy(correction[field])
                normalize_markings(question)
            modified.append({
                'page': page_num,
                'id': question_id,
                'old': old_verdict,
                'new': question.get('verdict'),
            })
            break
    return modified


def _note_check_target(question):
    from .note_evidence import NON_ASSESSED_ROLES
    role = question.get('note_role', 'unknown')
    if role in NON_ASSESSED_ROLES:
        return False
    if material_dependency(question)['required']:
        return True
    if role == 'unknown' and not str(question.get('student_answer') or '').strip():
        return False  # 只有材料开头的未知块作为来源，不当作漏答送审。
    return (role not in NON_ASSESSED_ROLES and bool(
        question.get('cross_page') or role == 'written_answer'
        or (role == 'unknown' and str(question.get('student_answer') or '').strip())))


def _material_labels(text):
    return set(re.findall(r'材料\s*([一二三四五六七八九十\d]+)', str(text or '')))


def _merge_note_checks(all_jsons, result, group, scope_page_nums=None, failure_reason=''):
    """逐单元核对；失败只阻断存在材料依赖的评价，不抹掉同页独立题。"""
    from .note_evidence import normalize_note_fields
    units = {f"p{page}:{q['id']}": (page, q) for page in group
             for q in all_jsons[page].get('questions', []) if isinstance(q, dict) and q.get('id')}
    returned = {}
    for item in result.get('corrections') or []:
        if isinstance(item, dict):
            key = f"p{item.get('page')}:{item.get('id')}"
            returned.setdefault(key, []).append(item)
    modified, checks = [], []
    for own, (page, question) in units.items():
        if not _note_check_target(question) or (scope_page_nums is not None and page not in scope_page_nums):
            continue
        before = {key: copy.deepcopy(question.get(key)) for key in (
            'student_answer', 'verdict', 'correct_answer', 'error_type', 'understanding',
            'cross_page', 'cross_page_resolved')}
        candidates = returned.get(own, [])
        item = candidates[0] if len(candidates) == 1 else {}
        status = item.get('material_status')
        reason = str(item.get('reason') or '').strip()
        evidence = item.get('material_evidence')
        dependency = material_dependency(question)
        required = set(dependency['labels'])
        valid = status in ('resolved', 'not_required') and bool(reason)
        if status == 'resolved':
            refs = item.get('supporting_qids')
            valid = valid and (isinstance(refs, list) and all(isinstance(ref, str) for ref in refs)
                               and own in refs and all(ref in units for ref in refs)
                               and any(units[ref][0] != page for ref in refs)
                               and item.get('cross_page_resolved') is True
                               and isinstance(evidence, list) and bool(evidence))
            labels = set()
            other_page_evidence = False
            if valid:
                for entry in evidence:
                    if not isinstance(entry, dict):
                        valid = False
                        break
                    ref = entry.get('qid_global')
                    label = str(entry.get('material_label') or '').strip()
                    if (not isinstance(ref, str) or ref not in refs
                            or not str(entry.get('quote') or '').strip()
                            or not str(entry.get('relation') or '').strip()):
                        valid = False
                        break
                    labels.update(_material_labels(label))
                    other_page_evidence |= units[ref][0] != page
                valid = valid and other_page_evidence and (not required or labels == required)
        elif status == 'not_required' and dependency['required']:
            # 材料题声称“本页足够”也必须交代本页来源，不能靠换状态绕过证据。
            labels = set()
            valid = valid and isinstance(evidence, list) and bool(evidence)
            if valid:
                for entry in evidence:
                    if not isinstance(entry, dict):
                        valid = False
                        break
                    ref = entry.get('qid_global')
                    if (not isinstance(ref, str) or ref not in units or units[ref][0] != page
                            or not str(entry.get('quote') or '').strip()
                            or not str(entry.get('relation') or '').strip()):
                        valid = False
                        break
                    labels.update(_material_labels(entry.get('material_label')))
                valid = valid and labels == required
        if valid and dependency['required']:
            valid = valid_material_quotes(evidence, units, dependency)
        # 核对通过也必须提供完整的新评价，避免沿用已经错误的初判。
        valid = valid and (item.get('verdict') in ('correct', 'partial', 'wrong')
                           and 'correct_answer' in item and 'error_type' in item
                           and bool(str(item.get('understanding') or '').strip())
                           and (item['verdict'] == 'correct' or bool(str(item.get('error_type') or '').strip())))
        if valid:
            for key in ('verdict', 'correct_answer', 'error_type', 'understanding'):
                question[key] = copy.deepcopy(item[key])
            if isinstance(item.get('student_answer'), str) and item['student_answer'].strip():
                question['student_answer'] = item['student_answer'].strip()
            question['cross_page'] = status == 'resolved'
            question['cross_page_resolved'] = status == 'resolved'
            question['supporting_qids'] = list(dict.fromkeys(item['supporting_qids'])) if status == 'resolved' else []
            question['material_check'] = {'status': status, 'reason': reason,
                                          'evidence': copy.deepcopy(evidence) if isinstance(evidence, list) else [],
                                          'blocks_assessment': False}
            if question['verdict'] == 'correct':
                question['error_type'] = ''
        else:
            # 未返回的独立选择题不能仅因邻题跨页就被改判；但其核对仍记为未完成。
            dependent = bool(question.get('cross_page') or dependency['required']
                             or not str(question.get('stem_excerpt') or '').strip()
                             or status == 'unresolved')
            reason = (failure_reason or (reason if status == 'unresolved' else '')
                      or ('未返回该单元的材料核对结果。' if not candidates
                          else '材料核对返回缺少有效来源、对应材料或完整评价。'))
            question['material_check'] = {'status': 'unresolved', 'reason': reason,
                                          'evidence': [], 'blocks_assessment': dependent}
            if dependent:
                question.update(verdict='uncertain', correct_answer=None, error_type='',
                                cross_page_resolved=False)
                question['understanding'] = ('已识别的书写：' + str(question.get('student_answer') or '')
                                             + '；材料依据待确认：' + reason)
        if valid:
            from .material_markings import MARKING_FIELDS
            for field in MARKING_FIELDS:
                if field in item:
                    question[field] = copy.deepcopy(item[field])
        normalize_note_fields(question)
        after = {key: copy.deepcopy(question.get(key)) for key in before}
        checks.append({'qid_global': own, **copy.deepcopy(question['material_check']),
                       'before': before, 'after': after})
        if valid:
            modified.append({'page': page, 'id': question['id'], 'old': before['verdict'],
                             'new': question['verdict']})
    return modified, checks


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
            if not artifact_compatible(page, feedback_runtime):
                finish([], 'configuration_mismatch')
                raise ValueError('跨页输入与本轮配置不一致，必须重新生成')
    boundaries = scan_boundaries(pass1_dir)
    dependency_groups, blocked_pages = material_groups(all_jsons, MAX_PAGES_PER_GROUP)
    if not boundaries and not dependency_groups:
        logger.info('[%s-%s] 无跨页标记，Pass 1.5 跳过', subject, sample_id)
        return finish([], 'no_cross_page')

    max_pages = MAX_PAGES_PER_GROUP
    if feedback_runtime is not None:
        from .feedback_material_kinds import cross_page_max_pages
        max_pages = cross_page_max_pages((feedback_runtime.context or {}).get('material_type'))
    from .note_evidence import is_notes
    dependency_groups, blocked_pages = material_groups(all_jsons, max_pages)
    notes = is_notes(feedback_runtime)
    if notes:
        from .note_page_links import candidate_note_page_pairs
        groups = candidate_note_page_pairs(all_jsons)
        if not groups and not dependency_groups:
            return finish([], 'unresolved_no_source_match')
    else:
        groups = build_cross_page_groups(
            boundaries, sorted(all_jsons.keys()), max_pages_per_group=max_pages,
        )
    groups, combined_blocked = combine_material_groups(dependency_groups, groups, max_pages)
    blocked_pages.update(combined_blocked)
    logger.info('[%s-%s] 检测到跨页页面 %s，跨页组 %s', subject, sample_id, sorted(boundaries.keys()), groups)

    all_corrections: List[Dict[str, Any]] = []
    for group in groups:
        if scope_page_nums is not None and not (set(group) & set(scope_page_nums)):
            continue
        material_group = notes or bool(set(group) & blocked_pages) or any(set(group) & set(d) for d in dependency_groups)
        if material_group:
            targets = [q for p in group for q in all_jsons[p].get('questions', [])
                       if _note_check_target(q) and (scope_page_nums is None or p in scope_page_nums)]
            if not targets:
                audit.append({'group': group, 'status': 'not_required', 'units': []})
                continue
        elif not group_needs_resolution(group, all_jsons):
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
        if material_group:
            failure_reason = ''
            result = {}
            if set(group) & blocked_pages:
                failure_reason = '材料候选超出本轮核对范围，尚未确认来源。'
            elif not image_paths:
                failure_reason = '候选页图片缺失，尚未核对材料。'
            else:
                evidence_fields = ('id', 'stem_excerpt', 'parent_stem_excerpt', 'student_answer',
                                   'position', 'note_role', 'cross_page', 'cross_page_note')
                visible_units = [dict({key: q[key] for key in evidence_fields if key in q},
                                      page=p, qid_global=f"p{p}:{q['id']}",
                                      requires_material_check=_note_check_target(q),
                                      page_origin=all_jsons[p].get('page_origin', {}))
                                 for p in group for q in all_jsons[p].get('questions', [])]
                try:
                    result = grade_cross_page_group(image_paths, subject, group, boundaries,
                        pending_questions=visible_units, feedback_runtime=feedback_runtime,
                        audit_path=os.path.join(pass1_dir, "cross_" + "_".join(map(str, group)) + ".responses.json"))
                except Exception as exc:
                    logger.warning('笔记材料核对失败 %s: %s', group, exc)
                    failure_reason = '材料核对调用失败，尚未确认对应关系。'
            corrections, unit_checks = _merge_note_checks(
                all_jsons, result, group, scope_page_nums, failure_reason)
            unresolved = any(item['status'] == 'unresolved' for item in unit_checks)
            audit.append({'group': group,
                          'status': 'missing_image' if not image_paths else 'failed' if failure_reason
                                    else 'unresolved' if unresolved else 'completed',
                          'reason': failure_reason, 'correction_count': len(corrections), 'units': unit_checks})
            all_corrections.extend(corrections)
            for page_num in group:
                if scope_page_nums is None or page_num in scope_page_nums:
                    safe_json_dump(path_by_page[page_num], stamp_feedback(
                        all_jsons[page_num], feedback_runtime, 'cross_page'))
            continue
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
                audit_path=os.path.join(pass1_dir, "cross_" + "_".join(map(str, group)) + ".responses.json"),
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        except Exception as exc:
            logger.warning('跨页组 %s 修补失败，保留原 Pass1 结果: %s', group, exc)
            audit.append({'group': group, 'status': 'failed', 'error': str(exc)})
            continue
        corrections = merge_corrections(all_jsons, result, feedback_runtime=feedback_runtime,
                                        group=group, scope_page_nums=scope_page_nums)
        audit.append({'group': group, 'status': 'completed',
                      'correction_count': len(corrections)})
        all_corrections.extend(corrections)
        for page_num in group:
            json_path = path_by_page.get(page_num)
            if json_path and page_num in all_jsons:
                safe_json_dump(json_path, stamp_feedback(all_jsons[page_num], feedback_runtime, 'cross_page'))

    if all_corrections:
        logger.info('[%s-%s] Pass 1.5 完成，修正 %d 道题', subject, sample_id, len(all_corrections))
    else:
        logger.info('[%s-%s] Pass 1.5 完成，无题目被修正', subject, sample_id)
    return finish(all_corrections, 'completed_with_warnings' if any(
        x['status'] not in ('completed', 'not_required') for x in audit) else 'completed')
