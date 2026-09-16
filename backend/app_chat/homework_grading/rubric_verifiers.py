"""Deterministic source-lock checks for homework grading."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app_chat.homework_grading.rubric_rules import (
    LISTENING_PATTERN,
    SOURCE_MISSING_PATTERN,
    SOURCE_PRESENT_PATTERN,
)

DETERMINISTIC_VERDICTS = {'correct', 'wrong', 'partial'}


def _text(*values: Any) -> str:
    return ' '.join(str(value or '') for value in values if value is not None)


def _question_context(question: Dict[str, Any]) -> str:
    return _text(
        question.get('parent_stem_excerpt'),
        question.get('stem_excerpt'),
        question.get('knowledge_point'),
        question.get('understanding'),
        question.get('error_type'),
        question.get('cross_page_note'),
        question.get('transcript'),
        question.get('audio'),
    )


def _issue(
    *,
    rule: str,
    local_verdict: str,
    apply_verdict: str,
    detail: str,
    check_name: str,
    severity: str = 'hard',
    uncertain_reason: str = '',
    source_lock: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    issue: Dict[str, Any] = {
        'rule': rule,
        'local_verdict': local_verdict,
        'apply_verdict': apply_verdict,
        'detail': detail,
        'rubric_check': {
            'name': check_name,
            'result': 'fail',
            'severity': severity,
            'evidence': detail,
        },
    }
    if uncertain_reason:
        issue['uncertain_reason'] = uncertain_reason
    if source_lock:
        issue['source_lock'] = source_lock
    return issue


def _has_source_material(question: Dict[str, Any]) -> bool:
    context = _question_context(question)
    if SOURCE_MISSING_PATTERN.search(context):
        return False
    return bool(SOURCE_PRESENT_PATTERN.search(context))


def evaluate_source_lock(question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a source-lock issue for audio/material-missing listening items."""
    if str(question.get('verdict') or '').strip() == 'unanswered':
        return None
    context = _question_context(question)
    if not LISTENING_PATTERN.search(context):
        return None
    if _has_source_material(question):
        return None
    existing = question.get('source_lock') if isinstance(question.get('source_lock'), dict) else {}
    if (
        existing.get('locked')
        and existing.get('reason_code') == 'no_audio_source'
        and str(question.get('verdict') or '').strip() == 'uncertain'
        and str(question.get('uncertain_reason') or '').strip() == 'no_audio_source'
    ):
        return None
    lock = {
        'locked': True,
        'reason_code': 'no_audio_source',
        'reason': '听力题缺少音频或听力原文，系统不强判正误',
    }
    return _issue(
        rule='source_lock:no_audio_source',
        local_verdict='uncertain',
        apply_verdict='uncertain',
        uncertain_reason='no_audio_source',
        detail=lock['reason'],
        check_name='source_lock',
        severity='hard',
        source_lock=lock,
    )


def source_lock_blocks_review(question: Dict[str, Any], new_verdict: str) -> Optional[Dict[str, Any]]:
    """Return a source lock when review tries to turn a locked question deterministic."""
    target = str(new_verdict or '').strip()
    existing = question.get('source_lock') if isinstance(question.get('source_lock'), dict) else {}
    if existing.get('locked') and target in DETERMINISTIC_VERDICTS:
        return {
            'locked': True,
            'reason_code': existing.get('reason_code') or 'source_locked',
            'reason': existing.get('reason') or '题目缺少必要来源，复核不得强判正误',
        }
    issue = evaluate_source_lock(question)
    if issue and target in DETERMINISTIC_VERDICTS:
        return issue['source_lock']
    return None
