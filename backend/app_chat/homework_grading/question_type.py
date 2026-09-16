"""Question type helpers shared by Pass1 normalization and post-review guards."""
from __future__ import annotations

import re
from typing import Any, Dict

_APPLICATION_FLAG_KEYS = (
    'is_application_major_problem',
    'application_major_problem',
    'is_application_problem',
    'is_word_problem',
)

_TRUE_TEXTS = {'1', 'true', 'yes', 'y', '是', '应用题', '应用题大题'}
_FILL_BLANK_HINTS = (
    '填空',
    '填写',
    '填表',
    '填上',
    '填入',
    '在括号里填',
    '在（）里填',
    '在()里填',
    '表格填空',
    '公式填空',
    '看图填空',
    '根据数量关系填写',
)
_BLANK_PLACEHOLDER_RE = re.compile(r'(?:[（(]\s*[）)]|_{2,}|＿{2,}|□{1,}|▢{1,})')
_FINAL_UNIT_REQUIREMENTS = {'required', 'forbidden', 'optional'}
_LETTER_VALUE_CONDITION_RE = re.compile(
    r'(?:当|若|如果)[^，。！？?]{0,30}'
    r'[A-Za-z]\s*=\s*-?\d+(?:\.\d+)?'
    r'(?:\s*[,\uFF0C、]\s*[A-Za-z]\s*=\s*-?\d+(?:\.\d+)?)*\s*时'
)


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or '').strip().lower()
    return text in _TRUE_TEXTS


def _question_type_text(question: Dict[str, Any]) -> str:
    return ' '.join(
        str(question.get(key) or '')
        for key in ('parent_stem_excerpt', 'stem_excerpt')
    )


def is_math_fill_blank_style_question(question: Dict[str, Any]) -> bool:
    """Return True for math questions whose answer form is a blank/table fill."""
    text = _question_type_text(question)
    compact = re.sub(r'\s+', '', text)
    if any(hint in compact for hint in _FILL_BLANK_HINTS):
        return True
    return bool(_BLANK_PLACEHOLDER_RE.search(compact))


def is_chinese_pronunciation_selection_question(
    question: Dict[str, Any],
    subject: str = 'chinese',
) -> bool:
    """Return True for Chinese items that select a pronunciation for dotted chars."""
    if str(subject or '').strip().lower() != 'chinese':
        return False
    compact = re.sub(r'\s+', '', _question_type_text(question))
    dotted_char = '加点字' in compact or '加点的字' in compact
    return dotted_char and '选择' in compact and '正确' in compact and '读音' in compact


def normalize_application_major_problem(question: Dict[str, Any], subject: str) -> bool:
    """Normalize the model's application-problem flag with fill-blank exclusions."""
    if subject != 'math':
        return False
    if is_math_fill_blank_style_question(question):
        return False
    for key in _APPLICATION_FLAG_KEYS:
        if key in question:
            return coerce_bool(question.get(key))
    return False


def is_math_letter_substitution_value_question(question: Dict[str, Any]) -> bool:
    """Return True for an application subquestion that substitutes letter values.

    In the project's elementary-school rubric these ``当 x=... 时`` follow-up
    questions ask for the value of the expression formed in the preceding part.
    The final value in the calculation process is written as a pure number;
    the separate ``答`` sentence still carries the real-world unit/classifier.
    """
    qid = str(question.get('id') or '').strip()
    parent_group_id = str(question.get('parent_group_id') or '').strip()
    if not parent_group_id or not re.match(r'^\d+-\d+$', qid):
        return False
    stem = str(question.get('stem_excerpt') or '').strip()
    return bool(_LETTER_VALUE_CONDITION_RE.search(stem))


def normalize_final_unit_requirement(question: Dict[str, Any], subject: str) -> str:
    """Normalize the per-question final-answer unit policy.

    For the letter-substitution subtype, ``forbidden`` applies only to the last
    value in the calculation process. It never forbids a unit in the separate
    final answer sentence. The inference keeps old detect JSON compatible.
    """
    if subject != 'math':
        return 'optional'
    if is_math_letter_substitution_value_question(question):
        return 'forbidden'
    raw = str(question.get('final_unit_requirement') or '').strip().lower()
    if raw in _FINAL_UNIT_REQUIREMENTS:
        return raw
    return 'optional'
