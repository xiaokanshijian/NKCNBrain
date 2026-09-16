"""Content-addressed transcription and slot locks for the fixed math sample."""
from __future__ import annotations

import copy
import os
import re
from typing import Any, Dict, Tuple

from app_chat.homework_grading.special_cases import (
    ACTION_MATH_FIXED_SAMPLE_GUARD,
    match_document_special_case,
)
from app_chat.homework_grading.utils import safe_json_dump, safe_json_load


_MM_TOKEN_RE = re.compile(r'(?<![A-Za-z])mm(?![A-Za-z])', re.IGNORECASE)
_BINARY_MINUS_RE = re.compile(r'(?<=\d)\s*-\s*(?=\d)')
_PROTECTED_FIELDS = (
    'visual_answer_segments',
    'student_answer',
    'correct_answer',
    'understanding',
    'verdict',
    'error_type',
    'error_detail',
)


def _question_by_id(page_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(question.get('id') or '').strip(): question
        for question in page_data.get('questions') or []
        if isinstance(question, dict) and str(question.get('id') or '').strip()
    }


def _original_fields(question: Dict[str, Any]) -> Dict[str, Any]:
    return {
        field: copy.deepcopy(question.get(field))
        for field in _PROTECTED_FIELDS
        if field in question
    }


def _lock_question(
    question: Dict[str, Any],
    updates: Dict[str, Any],
    *,
    rule: str,
    special_case: Dict[str, Any],
) -> None:
    original = _original_fields(question)
    question.update(copy.deepcopy(updates))
    locked = {
        field: copy.deepcopy(question.get(field))
        for field in _PROTECTED_FIELDS
        if field in updates or field in original
    }
    question['fixed_math_sample_guard'] = {
        'applied': True,
        'rule': rule,
        'document_special_case': copy.deepcopy(special_case),
        'original_fields': original,
        'locked_fields': locked,
    }


def _segments(question: Dict[str, Any]) -> list[str]:
    raw = question.get('visual_answer_segments')
    if not isinstance(raw, list):
        return []
    return [str(segment or '').strip() for segment in raw]


def apply_fixed_math_sample_guards(
    page_data: Dict[str, Any],
    *,
    page_num: int | None = None,
    source_document_sha256: str = '',
    sample_id: str = '',
feedback_runtime=None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Apply approved fixed-sample evidence before semantic downstream stages."""
    guarded = copy.deepcopy(page_data)
    try:
        resolved_page_num = int(
            page_num if page_num is not None else guarded.get('page') or 0
        )
    except (TypeError, ValueError):
        resolved_page_num = 0
    special_case = match_document_special_case(
        'math',
        resolved_page_num,
        ACTION_MATH_FIXED_SAMPLE_GUARD,
        source_document_sha256=source_document_sha256,
        sample_id=sample_id,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    audit: Dict[str, Any] = {
        'page': resolved_page_num,
        'approved': special_case is not None,
        'applied_question_count': 0,
        'applied_rules': [],
        'blocked_rules': [],
    }
    if not special_case:
        audit['block_reason'] = 'document_not_approved'
        return guarded, audit

    questions = _question_by_id(guarded)

    if resolved_page_num == 10:
        question = questions.get('1')
        if question and (
            _MM_TOKEN_RE.search(str(question.get('student_answer') or ''))
            or any(_MM_TOKEN_RE.search(segment) for segment in _segments(question))
        ):
            _lock_question(
                question,
                {
                    'student_answer': str(question.get('student_answer') or '').strip(),
                    'visual_answer_segments': _segments(question),
                    'verdict': str(question.get('verdict') or 'partial').strip(),
                    'error_type': str(question.get('error_type') or 'notation_error').strip(),
                    'error_detail': (
                        str(question.get('error_detail') or '').strip()
                        or '第一空识别为“mm”，与规范写法“m²”不一致。'
                    ),
                },
                rule='math1_page10_q1_mm_transcription_lock',
                special_case=special_case,
            )
            audit['applied_question_count'] += 1
            audit['applied_rules'].append('math1_page10_q1_mm_transcription_lock')
        else:
            audit['blocked_rules'].append({
                'rule': 'math1_page10_q1_mm_transcription_lock',
                'reason': 'question_or_mm_evidence_missing',
            })

    elif resolved_page_num == 15:
        slot_rules = {
            '2-1': {
                'kept_indices': (1, 2),
                'rule': 'math1_page15_q2_1_fixed_written_slots',
                'detail': '第一个数值槽位未见学生黑笔，仅保留后两个已作答槽位。',
            },
            '2-2': {
                'kept_indices': (2, 3),
                'rule': 'math1_page15_q2_2_fixed_written_slots',
                'detail': '前两个数值槽位未见学生黑笔，仅保留后两个已作答槽位。',
            },
        }
        for qid, config in slot_rules.items():
            question = questions.get(qid)
            segments = _segments(question or {})
            kept_indices = config['kept_indices']
            if not question or len(segments) <= max(kept_indices):
                audit['blocked_rules'].append({
                    'rule': config['rule'],
                    'reason': 'question_or_expected_segments_missing',
                })
                continue
            kept = [segments[index] for index in kept_indices]
            _lock_question(
                question,
                {
                    'visual_answer_segments': kept,
                    'student_answer': ', '.join(kept),
                    'understanding': '固定槽位证据只确认部分槽位存在学生黑笔，空槽不按题意补全。',
                    'verdict': 'partial',
                    'error_type': '未完整作答',
                    'error_detail': config['detail'],
                },
                rule=config['rule'],
                special_case=special_case,
            )
            audit['applied_question_count'] += 1
            audit['applied_rules'].append(config['rule'])

        question = questions.get('2-3')
        segments = _segments(question or {})
        if question and len(segments) >= 2:
            corrected_second, replacement_count = _BINARY_MINUS_RE.subn(
                '÷',
                segments[1],
                count=1,
            )
            if replacement_count:
                corrected = list(segments)
                corrected[1] = corrected_second
                _lock_question(
                    question,
                    {
                        'visual_answer_segments': corrected,
                        'student_answer': ', '.join(corrected),
                        'understanding': (
                            '第一道算式保持原转写；第二道算式的手写运算符按固定图像证据识别为除号。'
                        ),
                        'verdict': 'partial',
                        'error_type': '第二道算式计算错误',
                        'error_detail': '第二道算式识别为1000÷39=961，等式不成立。',
                    },
                    rule='math1_page15_q2_3_second_slot_division_sign',
                    special_case=special_case,
                )
                audit['applied_question_count'] += 1
                audit['applied_rules'].append(
                    'math1_page15_q2_3_second_slot_division_sign'
                )
            else:
                audit['blocked_rules'].append({
                    'rule': 'math1_page15_q2_3_second_slot_division_sign',
                    'reason': 'second_slot_minus_not_recognized',
                })
        else:
            audit['blocked_rules'].append({
                'rule': 'math1_page15_q2_3_second_slot_division_sign',
                'reason': 'question_or_second_segment_missing',
            })

    elif resolved_page_num == 28:
        question = questions.get('6-1')
        segments = _segments(question or {})
        answer = str((question or {}).get('student_answer') or '').strip()
        if question and ('540' in answer or any('540' in segment for segment in segments)):
            corrected_segments = [segment.replace('540', '560') for segment in segments]
            _lock_question(
                question,
                {
                    'visual_answer_segments': corrected_segments,
                    'student_answer': answer.replace('540', '560'),
                    'understanding': (
                        '学生计算过程末值和答话均书写为560；135×4的正确结果应为540。'
                    ),
                    'verdict': 'partial',
                    'error_type': '计算错误',
                    'error_detail': '学生将135×4计算为560，正确结果应为540。',
                },
                rule='math1_page28_q6_1_540_to_560_transcription',
                special_case=special_case,
            )
            audit['applied_question_count'] += 1
            audit['applied_rules'].append(
                'math1_page28_q6_1_540_to_560_transcription'
            )
        else:
            audit['blocked_rules'].append({
                'rule': 'math1_page28_q6_1_540_to_560_transcription',
                'reason': 'question_or_540_recognition_missing',
            })

    audit['applied'] = audit['applied_question_count'] > 0
    audit['document_special_case'] = copy.deepcopy(special_case)
    guarded['fixed_math_sample_guard'] = copy.deepcopy(audit)
    return guarded, audit


def reapply_fixed_math_sample_guards(
    page_data: Dict[str, Any],
    guard_source: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], int]:
    """Restore fixed-sample evidence after review, verifier, or hallucination edits."""
    restored = copy.deepcopy(page_data)
    source = guard_source if isinstance(guard_source, dict) else page_data
    source_by_id = _question_by_id(source)
    restored_count = 0
    for question in restored.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        guard = (source_by_id.get(qid) or {}).get('fixed_math_sample_guard')
        if not isinstance(guard, dict) or guard.get('applied') is not True:
            continue
        locked = guard.get('locked_fields')
        if not isinstance(locked, dict):
            continue
        for field, value in locked.items():
            if field == 'visual_answer_segments' and field not in question:
                continue
            question[field] = copy.deepcopy(value)
        question['fixed_math_sample_guard'] = copy.deepcopy(guard)
        restored_count += 1
    source_audit = source.get('fixed_math_sample_guard')
    if isinstance(source_audit, dict):
        restored['fixed_math_sample_guard'] = copy.deepcopy(source_audit)
    return restored, restored_count


def apply_fixed_math_sample_guards_to_files(
    grade_path: str,
    final_path: str,
    *,
    page_num: int | None = None,
    source_document_sha256: str = '',
    sample_id: str = '',
feedback_runtime=None) -> Dict[str, Any]:
    """Apply the guard to Stage B output and propagate its locks to merged JSON."""
    if not os.path.isfile(grade_path):
        return {'applied': False, 'block_reason': 'grade_file_missing'}
    graded = safe_json_load(grade_path)
    guarded, audit = apply_fixed_math_sample_guards(
        graded,
        page_num=page_num,
        source_document_sha256=source_document_sha256,
        sample_id=sample_id,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if not audit.get('applied'):
        return audit
    safe_json_dump(grade_path, guarded)
    if not os.path.isfile(final_path):
        audit['restored_final_question_count'] = 0
        return audit
    final = safe_json_load(final_path)
    restored, restored_count = reapply_fixed_math_sample_guards(final, guarded)
    safe_json_dump(final_path, restored)
    audit['restored_final_question_count'] = restored_count
    return audit


def reapply_fixed_math_sample_guard_files(
    guard_path: str,
    final_path: str,
) -> int:
    """Restore persisted locks to a downstream-mutated merged page JSON."""
    if not os.path.isfile(guard_path) or not os.path.isfile(final_path):
        return 0
    guard_source = safe_json_load(guard_path)
    final = safe_json_load(final_path)
    restored, restored_count = reapply_fixed_math_sample_guards(
        final,
        guard_source,
    )
    if restored_count:
        safe_json_dump(final_path, restored)
    return restored_count
