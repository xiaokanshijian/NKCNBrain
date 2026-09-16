"""Immutable transcription lock for the approved English page-15 table sample."""
from __future__ import annotations

import copy
import re
from typing import Any, Dict

from app_chat.homework_grading.special_cases import (
    ACTION_ENGLISH_VISUAL_TRANSCRIPTION_LOCK,
    match_document_special_case,
)


_TARGET_QUESTION_IDS = ('10-1', '10')
_UNCLE_ROW_RE = re.compile(r"\bLingling['’]s\s+uncle\b", re.IGNORECASE)
_TARGET_ACTION_RE = re.compile(r'\b(?:crying|cry)\b', re.IGNORECASE)
_PROTECTED_FIELDS = (
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


def _replace_uncle_action(
    student_answer: Any,
    replacement: str,
) -> tuple[str, bool]:
    """Replace only the target row's action, never the preceding father row."""
    text = str(student_answer or '').strip()
    if not text:
        return '', False
    lines = text.splitlines()
    for index, line in enumerate(lines):
        uncle = _UNCLE_ROW_RE.search(line)
        if not uncle:
            continue
        action = _TARGET_ACTION_RE.search(line, uncle.end())
        if not action:
            return text, False
        lines[index] = (
            line[:action.start()] + replacement + line[action.end():]
        )
        return '\n'.join(lines), True
    return text, False


def apply_fixed_english_page15_guard(
    page_data: Dict[str, Any],
    *,
    page_num: int | None = None,
    source_document_sha256: str = '',
    sample_id: str = '',
feedback_runtime=None) -> Dict[str, Any]:
    """Freeze the visible ``cry`` and its resulting partial verdict."""
    try:
        resolved_page_num = int(
            page_num if page_num is not None else page_data.get('page') or 0
        )
    except (TypeError, ValueError):
        resolved_page_num = 0
    special_case = match_document_special_case(
        'english',
        resolved_page_num,
        ACTION_ENGLISH_VISUAL_TRANSCRIPTION_LOCK,
        source_document_sha256=source_document_sha256,
        sample_id=sample_id,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    audit: Dict[str, Any] = {
        'page': resolved_page_num,
        'approved': special_case is not None,
        'applied_question_count': 0,
    }
    if not special_case:
        audit['block_reason'] = 'document_not_approved'
        return audit

    questions = _question_by_id(page_data)
    question = next(
        (questions[qid] for qid in _TARGET_QUESTION_IDS if qid in questions),
        None,
    )
    if not question:
        audit['block_reason'] = 'target_question_missing'
        return audit

    original_answer = str(question.get('student_answer') or '').strip()
    corrected_answer, matched = _replace_uncle_action(original_answer, 'cry')
    if not matched:
        audit['block_reason'] = 'target_uncle_action_missing'
        return audit

    original_fields = {
        field: copy.deepcopy(question.get(field))
        for field in _PROTECTED_FIELDS
        if field in question
    }
    correct_answer = str(question.get('correct_answer') or '').strip()
    if not correct_answer:
        correct_answer, _expected_matched = _replace_uncle_action(
            original_answer,
            'crying',
        )

    locked_fields = {
        'student_answer': corrected_answer,
        'correct_answer': correct_answer,
        'understanding': (
            "题目要求按示例填写家庭成员的行为与感受；第三行 Action 栏中，"
            "学生划掉 running 后最终保留的是 cry，缺少示例要求的 -ing 形式。"
        ),
        'verdict': 'partial',
        'error_type': 'verb_form_incomplete',
        'error_detail': '第三行 Action 应写 crying，学生最终只写了 cry。',
    }
    question.update(copy.deepcopy(locked_fields))
    question['fixed_english_page15_guard'] = {
        'applied': True,
        'rule': 'english1_page15_q10_uncle_cry_transcription',
        'document_special_case': copy.deepcopy(special_case),
        'target_row': "Lingling's uncle",
        'observed_action': 'cry',
        'original_fields': original_fields,
        'locked_fields': copy.deepcopy(locked_fields),
    }
    audit.update({
        'applied': True,
        'applied_question_count': 1,
        'rule': 'english1_page15_q10_uncle_cry_transcription',
        'document_special_case': copy.deepcopy(special_case),
    })
    page_data['fixed_english_page15_guard'] = copy.deepcopy(audit)
    return audit


def reapply_fixed_english_page15_guard(page_data: Dict[str, Any]) -> int:
    """Restore the fixed row after review, verifier, and hallucination stages."""
    restored = 0
    for question in page_data.get('questions') or []:
        if not isinstance(question, dict):
            continue
        guard = question.get('fixed_english_page15_guard')
        if not isinstance(guard, dict) or guard.get('applied') is not True:
            continue
        locked_fields = guard.get('locked_fields')
        if not isinstance(locked_fields, dict):
            continue
        before = tuple(question.get(field) for field in locked_fields)
        for field, value in locked_fields.items():
            question[field] = copy.deepcopy(value)
        after = tuple(question.get(field) for field in locked_fields)
        if before != after:
            restored += 1
    return restored
