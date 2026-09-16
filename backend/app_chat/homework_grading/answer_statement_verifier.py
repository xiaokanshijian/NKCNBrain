"""Post-review guards for math application-problem answer-form requirements."""
from __future__ import annotations

import logging
import os
import re
import shutil
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app_chat.homework_grading.question_type import (
    is_math_letter_substitution_value_question,
    normalize_application_major_problem,
    normalize_final_unit_requirement,
)
from app_chat.homework_grading.utils import safe_json_dump, safe_json_load, sorted_json_pages

logger = logging.getLogger(__name__)

_ANSWER_MARKER_RE = re.compile(
    r'(?:^|[\s\n。；;]|(?<=[0-9０-９）)\]]))答\s*[:：]?',
    re.IGNORECASE,
)
_FORMULA_CHARS_RE = re.compile(r'[\dA-Za-z０-９ａ-ｚＡ-Ｚ\s=≈≠<>≤≥+\-*/×÷·•.:：,，;；!?！？()[\]{}（）【】《》、。~～_^%]+')
_MATH_UNITS = (
    '平方厘米', '平方分米', '平方米', '平方千米', '立方厘米', '立方分米', '立方米',
    '千米', '公里', '米', '分米', '厘米', '毫米',
    '千克', '公斤', '克', '吨',
    '小时', '分钟', '秒', '年', '月', '日', '天',
    '元', '角', '分',
    '升', '毫升', '摄氏度', '度',
    '个', '只', '支', '枝', '本', '张', '条', '块', '根', '辆', '盒', '瓶',
    '杯', '套', '组', '排', '页', '题', '人', '棵', '朵', '颗', '枚', '件',
    '次', '倍', '份', '岁', '面',
)
_UNIT_RE = re.compile('|'.join(re.escape(unit) for unit in sorted(_MATH_UNITS, key=len, reverse=True)))
_FINAL_UNIT_RE = re.compile(
    r'[0-9０-９]\s*(?:[（(]\s*)?(?:'
    + '|'.join(re.escape(unit) for unit in sorted(_MATH_UNITS, key=len, reverse=True))
    + r')(?:\s*[）)])?'
)
_LATIN_AREA_VOLUME_UNIT_RE = re.compile(
    r'(?<![A-Za-z])(?:km|cm|mm|dm|m)\s*(?:\^?[23]|[²³])(?![A-Za-z])',
    re.IGNORECASE,
)
_CHINESE_NUMERAL_RE = re.compile(r'[零〇一二三四五六七八九十百千万亿两]+')


def has_final_answer_statement(student_answer: Any) -> bool:
    """Return True when the answer contains an explicit or sentence-like final response."""
    text = str(student_answer or '').strip()
    if not text:
        return False
    marker = _ANSWER_MARKER_RE.search(text)
    if marker:
        return bool(text[marker.end():].strip())

    # Strip symbols, numbers, algebra letters, and common units. If meaningful
    # Chinese wording remains, treat it as an answer statement and do not hard-fix.
    residue = _FORMULA_CHARS_RE.sub('', text)
    residue = _UNIT_RE.sub('', residue)
    residue = _CHINESE_NUMERAL_RE.sub('', residue)
    residue = re.sub(r'[\s\u3000]+', '', residue)
    return bool(residue)


def missing_answer_statement_issue(question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if str(question.get('verdict') or '').strip() != 'correct':
        return None
    if not normalize_application_major_problem(question, 'math'):
        return None
    if has_final_answer_statement(question.get('student_answer')):
        return None
    return {
        'rule': 'math_application_missing_answer_statement',
        'local_verdict': 'partial',
        'apply_verdict': 'partial',
        'detail': '应用题大题缺少最终答话，不能继续判为完全正确',
        'rubric_check': {
            'name': 'missing_answer_statement',
            'result': 'fail',
            'severity': 'post_review_guard',
            'evidence': str(question.get('student_answer') or '').strip(),
        },
    }


def has_final_unit(student_answer: Any) -> bool:
    """Return True when the handwritten answer contains a unit/classifier."""
    text = str(student_answer or '').strip()
    if not text:
        return False
    return bool(_FINAL_UNIT_RE.search(text) or _LATIN_AREA_VOLUME_UNIT_RE.search(text))


def split_solution_and_answer_statement(student_answer: Any) -> Tuple[str, str]:
    """Split handwritten work at the explicit ``答`` marker.

    The unit rubric intentionally treats the calculation process and the final
    answer sentence as two different regions. Without an explicit marker we
    conservatively keep the text in the process region; the existing
    sentence-like answer detector remains responsible for marker-less answers.
    """
    text = str(student_answer or '').strip()
    if not text:
        return '', ''
    marker = _ANSWER_MARKER_RE.search(text)
    if not marker:
        return text, ''
    return text[:marker.start()].strip(), text[marker.end():].strip()


def _solution_final_fragment(solution_process: Any) -> str:
    """Return the fragment containing the last completed calculation value."""
    text = str(solution_process or '').strip()
    if not text:
        return ''
    equals_parts = re.split(r'[=＝≈]', text)
    if len(equals_parts) > 1:
        return equals_parts[-1].strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else text


def has_solution_final_unit(student_answer: Any) -> bool:
    """Return True only when the calculation's last value carries a unit."""
    solution_process, _ = split_solution_and_answer_statement(student_answer)
    return has_final_unit(_solution_final_fragment(solution_process))


def has_answer_statement_unit(student_answer: Any) -> bool:
    """Return True when the explicit final answer sentence carries a unit."""
    _, answer_statement = split_solution_and_answer_statement(student_answer)
    return has_final_unit(answer_statement)


def forbidden_final_unit_issue(question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Flag a unit attached to the process result of a substitution problem."""
    if str(question.get('verdict') or '').strip() != 'correct':
        return None
    if not is_math_letter_substitution_value_question(question):
        return None
    if normalize_final_unit_requirement(question, 'math') != 'forbidden':
        return None
    if not has_solution_final_unit(question.get('student_answer')):
        return None
    return {
        'rule': 'math_substitution_process_final_unit',
        'local_verdict': 'partial',
        'apply_verdict': 'partial',
        'detail': '含字母式子代入求值时，计算过程末值应写纯数；答话中的最终数量仍应保留单位',
        'error_type': '代入求值的计算过程末值不应加单位',
        'rubric_check': {
            'name': 'substitution_process_final_unit',
            'result': 'fail',
            'severity': 'post_review_guard',
            'evidence': _solution_final_fragment(
                split_solution_and_answer_statement(question.get('student_answer'))[0]
            ),
        },
    }


def missing_substitution_answer_unit_issue(question: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Require a unit/classifier in the answer sentence of substitution problems."""
    if str(question.get('verdict') or '').strip() != 'correct':
        return None
    if not is_math_letter_substitution_value_question(question):
        return None
    if not has_final_answer_statement(question.get('student_answer')):
        return None
    _, answer_statement = split_solution_and_answer_statement(question.get('student_answer'))
    # Marker-less natural-language answers are left to the model because their
    # process/answer boundary cannot be recovered safely from plain text.
    if not answer_statement or has_answer_statement_unit(question.get('student_answer')):
        return None
    return {
        'rule': 'math_substitution_answer_statement_missing_unit',
        'local_verdict': 'partial',
        'apply_verdict': 'partial',
        'detail': '代入求值的计算过程末值不写单位，但最终答话中的数量需要写相应单位或计量词',
        'error_type': '代入求值的答话缺少单位',
        'rubric_check': {
            'name': 'substitution_answer_statement_unit',
            'result': 'fail',
            'severity': 'post_review_guard',
            'evidence': answer_statement,
        },
    }


def verify_answer_statements(
    subject: str,
    pass1_dir: str,
    out_report_path: str,
    apply: bool = True,
    page_nums: Optional[Iterable[int]] = None,
*, feedback_runtime=None) -> Dict[str, Any]:
    """Scan final Pass1 JSON after review/verifier and downgrade missed answer statements."""
    if feedback_runtime is not None:
        from .feedback_verification import verify_with_runtime
        return verify_with_runtime(subject, pass1_dir, out_report_path, feedback_runtime=feedback_runtime, apply=apply, page_nums=page_nums, kind='answer_statement')
    if subject != 'math':
        report = {
            'subject': subject,
            'skipped': True,
            'reason': 'answer statement guard only applies to math',
            'total_discrepancies': 0,
            'corrections_applied': 0,
            'details': [],
        }
        safe_json_dump(out_report_path, report)
        return report

    selected_pages: Optional[Set[int]] = {int(page) for page in page_nums} if page_nums is not None else None
    details: List[Dict[str, Any]] = []
    applied = 0
    for json_path in sorted_json_pages(pass1_dir):
        try:
            data = safe_json_load(json_path)
        except Exception:
            continue
        page = data.get('page')
        if selected_pages is not None:
            try:
                if int(page) not in selected_pages:
                    continue
            except (TypeError, ValueError):
                continue
        mutated = False
        for question in data.get('questions') or []:
            if not isinstance(question, dict):
                continue
            # Keep the calculation result and final answer sentence as separate
            # rubric regions. A process-unit failure remains the most specific
            # correction when multiple answer-form problems coexist.
            issue = (
                forbidden_final_unit_issue(question)
                or missing_answer_statement_issue(question)
                or missing_substitution_answer_unit_issue(question)
            )
            if not issue:
                continue
            issue = {
                **issue,
                'page': page,
                'question_id': question.get('id'),
                'model_verdict': question.get('verdict'),
                'student_answer': question.get('student_answer'),
            }
            details.append(issue)
            if not apply:
                continue

            previous = {
                'verdict': question.get('verdict'),
                'error_type': question.get('error_type', ''),
            }
            question['verdict'] = issue['apply_verdict']
            question['error_type'] = (
                str(question.get('error_type') or '').strip()
                or issue.get('error_type')
                or '缺少最终答话'
            )
            question.setdefault('post_review_guard', {})
            question['post_review_guard'].update({
                'rule': issue['rule'],
                'previous': previous,
                'applied_verdict': issue['apply_verdict'],
                'detail': issue['detail'],
            })
            checks = question.setdefault('rubric_checks', [])
            if isinstance(checks, list):
                checks.append(issue['rubric_check'])
            mutated = True
            applied += 1
        if apply and mutated:
            bak_path = json_path + '.corrected.bak'
            if not os.path.exists(bak_path):
                try:
                    shutil.copyfile(json_path, bak_path)
                except Exception:
                    logger.warning('answer statement backup failed: %s', bak_path)
            safe_json_dump(json_path, data)

    report = {
        'subject': subject,
        'total_discrepancies': len(details),
        'corrections_applied': applied,
        'details': details,
    }
    safe_json_dump(out_report_path, report)
    return report
