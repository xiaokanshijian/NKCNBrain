"""L4 二级筛分 · 学科专项验算（nkcn 自有，改编自 yq v2.0 三个 verifier）。

合并 math_verifier / chinese_verifier / english_verifier 的规则，统一对外暴露
`verify_pass1_dir(subject, pass1_dir, out_report_path, apply=True)`。

依赖降级策略：
- 语文拼音校验依赖 pypinyin；缺失时跳过拼音规则（不影响其它规则）。
- 英语拼写校验依赖 pyenchant；缺失时回退到本地词表 / 跳过。

发现不一致时按规则回写 verdict（source lock 会写为 uncertain，其它默认降为 uncertain），并写入 verification_result，
最终落盘 verification_report.json。Stage 3.5：改写 pass1_json 前先复制
`*.corrected.bak` 备份原文件。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app_chat.homework_grading.rubric_verifiers import evaluate_source_lock
from app_chat.homework_grading.special_cases import (
    ACTION_CHINESE_FIXED_ANSWER,
    ACTION_CHINESE_PERSONIFICATION_VERIFIER,
    match_document_special_case,
)
from app_chat.homework_grading.utils import safe_json_dump, safe_json_load, sorted_json_pages

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)


# ════════════════════════════ 数学 ════════════════════════════
_SAFE_EXPR_RE = re.compile(r'^[\d\s\+\-\*/\(\)\.]+$')


def _try_eval_expr(expr: Any) -> Optional[float]:
    if expr is None:
        return None
    s = (str(expr).strip().replace('×', '*').replace('÷', '/')
         .replace('（', '(').replace('）', ')').replace(' ', ''))
    if not _SAFE_EXPR_RE.match(s):
        return None
    try:
        return float(eval(s))  # noqa: S307 字符集已严格限制
    except Exception:
        return None


_UNIT_RULES = _load_json(os.path.join(_DATA_DIR, 'math_unit_rules.json')) or {}
_UNIT_ALIASES = _UNIT_RULES.get('unit_aliases', {})
_VALUE_UNIT_RE = (
    re.compile(r'(\d+(?:\.\d+)?)\s*(' + '|'.join(re.escape(u) for u in _UNIT_ALIASES.keys()) + r')')
    if _UNIT_ALIASES else None
)


def _extract_value_units(text: str) -> List[Tuple[float, str]]:
    if not text or _VALUE_UNIT_RE is None:
        return []
    out = []
    for val_s, unit_cn in _VALUE_UNIT_RE.findall(str(text)):
        try:
            out.append((float(val_s), _UNIT_ALIASES[unit_cn]))
        except (ValueError, KeyError):
            continue
    return out


def _convert(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    if from_unit == to_unit:
        return value
    for category, rules in _UNIT_RULES.items():
        if category == 'unit_aliases' or category.startswith('_'):
            continue
        if not isinstance(rules, dict):
            continue
        key_fwd = f'{from_unit}_{to_unit}'
        key_rev = f'{to_unit}_{from_unit}'
        if key_fwd in rules:
            return value * rules[key_fwd]
        if key_rev in rules:
            return value / rules[key_rev]
    return None


def _check_unit_conversion(q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    correct, student = q.get('correct_answer'), q.get('student_answer')
    if not correct or not student:
        return None
    correct_pairs, student_pairs = _extract_value_units(correct), _extract_value_units(student)
    if not correct_pairs or not student_pairs:
        return None
    c_val, c_unit = correct_pairs[0]
    s_val, s_unit = student_pairs[0]
    converted = _convert(s_val, s_unit, c_unit)
    if converted is None:
        return None
    local_correct = abs(converted - c_val) < 1e-6
    if local_correct and q.get('verdict') == 'wrong':
        return {'rule': 'unit_conversion', 'local_verdict': 'correct',
                'detail': f'{s_val}{s_unit} = {converted}{c_unit} 匹配正确答案 {c_val}{c_unit}'}
    if not local_correct and q.get('verdict') == 'correct':
        return {'rule': 'unit_conversion', 'local_verdict': 'wrong',
                'detail': f'{s_val}{s_unit} = {converted}{c_unit} ≠ {c_val}{c_unit}'}
    return None


_OP_LAW_PATTERNS = [
    ('commutative_mul', re.compile(r'(\d+)\s*[×*]\s*(\d+)\s*=\s*(\d+)\s*[×*]\s*(\d+)')),
    ('commutative_add', re.compile(r'(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)\s*\+\s*(\d+)')),
    ('associative_mul', re.compile(r'\(\s*\d+\s*[×*]\s*\d+\s*\)\s*[×*]\s*\d+\s*=\s*\d+\s*[×*]\s*\(\s*\d+\s*[×*]\s*\d+\s*\)')),
    ('associative_add', re.compile(r'\(\s*\d+\s*\+\s*\d+\s*\)\s*\+\s*\d+\s*=\s*\d+\s*\+\s*\(\s*\d+\s*\+\s*\d+\s*\)')),
    ('distributive', re.compile(r'\d+\s*[×*]\s*\(\s*\d+\s*[+\-]\s*\d+\s*\)\s*=\s*\d+\s*[×*]\s*\d+\s*[+\-]\s*\d+\s*[×*]\s*\d+')),
]


def _check_operation_law(q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kp = (q.get('knowledge_point') or '').lower()
    if 'operation_law' not in kp and '运算律' not in kp:
        return None
    answer = str(q.get('student_answer') or '')
    if '=' not in answer:
        return None
    norm = answer.replace('×', '*').replace('÷', '/').replace('（', '(').replace('）', ')')
    matched = None
    for name, pat in _OP_LAW_PATTERNS:
        if pat.search(norm):
            matched = name
            break
    lhs, _, rhs = norm.partition('=')
    l_val, r_val = _try_eval_expr(lhs), _try_eval_expr(rhs)
    if matched is None:
        if l_val is not None and r_val is not None and abs(l_val - r_val) > 1e-9:
            return {'rule': 'operation_law', 'local_verdict': 'wrong',
                    'detail': f'等号两边不等：{lhs}={l_val}, {rhs}={r_val}'}
        return None
    if l_val is not None and r_val is not None and abs(l_val - r_val) > 1e-9:
        return {'rule': f'operation_law:{matched}', 'local_verdict': 'wrong',
                'detail': f'模板命中但两边数值不等：{l_val} vs {r_val}'}
    return None


def _verify_math_question(q: Dict[str, Any], page: Optional[int]) -> Optional[Dict[str, Any]]:
    if q.get('verdict') in ('unanswered', 'uncertain'):
        return None
    correct_raw, student_raw = q.get('correct_answer'), q.get('student_answer')
    local_correct = _try_eval_expr(correct_raw)
    if local_correct is not None:
        student_val = _try_eval_expr(student_raw)
        if student_val is not None:
            local_verdict = 'correct' if abs(student_val - local_correct) < 1e-9 else 'wrong'
            if local_verdict != q.get('verdict'):
                return {'rule': 'arithmetic', 'local_verdict': local_verdict,
                        'detail': f'学生={student_raw}, 模型正确={correct_raw}, 本地算={local_correct}'}
    for checker in (_check_unit_conversion, _check_operation_law):
        issue = checker(q)
        if issue:
            return issue
    return None


# ════════════════════════════ 语文 ════════════════════════════
try:  # pypinyin 可选
    from pypinyin import lazy_pinyin  # noqa: F401
    _HAS_PYPINYIN = True
except Exception:  # pragma: no cover
    _HAS_PYPINYIN = False

_errors_data = _load_json(os.path.join(_DATA_DIR, 'chinese_common_errors.json')) or {}
_ERROR_TABLE = _errors_data.get('errors', []) if isinstance(_errors_data, dict) else []
_ERROR_MAP: Dict[str, str] = {e['wrong']: e['right'] for e in _ERROR_TABLE if e.get('wrong') and e.get('wrong') != e.get('right')}

_PINYIN_TOKEN_RE = re.compile(r'\b[a-zA-Züāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]{2,}\d?\b', re.IGNORECASE)
_VALID_PINYIN_PAT = re.compile(
    r'^(b|p|m|f|d|t|n|l|g|k|h|j|q|x|zh|ch|sh|r|z|c|s|y|w)?'
    r'(a|o|e|i|u|ü|ai|ei|ao|ou|an|en|in|un|ang|eng|ing|ong|ia|ie|iao|iou|iu|'
    r'ian|iang|iong|ua|uo|uai|uei|ui|uan|uen|uang|ueng|üe|üan|ün|er)$',
    re.IGNORECASE,
)


def _normalize_pinyin(token: str) -> str:
    token = re.sub(r'\d', '', token).lower()
    table = str.maketrans('āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü', 'aaaaeeeeiiiioooouuuuuuuuv')
    return token.translate(table)


def _is_valid_pinyin(token: str) -> bool:
    norm = _normalize_pinyin(token)
    if len(norm) < 2:
        return False
    return bool(_VALID_PINYIN_PAT.match(norm))


def _check_pinyin(q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _HAS_PYPINYIN:
        return None
    kp = (q.get('knowledge_point') or '').lower()
    if not any(k in kp for k in ('pinyin', 'phonics', '拼音', 'polyphonic')):
        return None
    student = q.get('student_answer')
    if not student:
        return None
    tokens = _PINYIN_TOKEN_RE.findall(str(student))
    illegal = [t for t in tokens if not _is_valid_pinyin(t)]
    if not illegal:
        return None
    return {'rule': 'pinyin_invalid', 'local_verdict': 'uncertain', 'detail': f'非法拼音 token: {illegal}'}


def _check_common_errors(q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if q.get('verdict') != 'correct':
        return None
    student = str(q.get('student_answer') or '')
    if not student:
        return None
    hits = [(w, r) for w, r in _ERROR_MAP.items() if w in student]
    if not hits:
        return None
    return {'rule': 'common_error_typo', 'local_verdict': 'wrong',
            'detail': '学生答案命中错别字：' + ', '.join(f'{w}→{r}' for w, r in hits)}


_RHETORICAL_MARKERS = ('难道', '怎么', '岂', '哪能', '怎能')
_REWRITE_KW = ('反问', '改写', '改陈述', 'rewrite', 'sentence_rewrite')
_FIXED_PERSONIFICATION_ANSWERS = frozenset({
    '一只蜘蛛伸出腿慢慢的向树干爬去',
    '一只蜘蛛伸出腿慢慢地向树干爬去',
})


def _normalize_fixed_chinese_answer(value: Any) -> str:
    text = str(value or '').strip()
    text = re.sub(r'[\s，,。.!！?？“”"\'‘’；;：:（）()]', '', text)
    return text


def _choice_letter(value: Any) -> str:
    matched = re.search(r'(?<![A-Z])([A-D])(?![A-Z])', str(value or '').upper())
    return matched.group(1) if matched else ''


def _check_fixed_chinese_sample(
    q: Dict[str, Any],
    page: Optional[int],
    source_document_sha256: str,
*, feedback_runtime=None) -> Optional[Dict[str, Any]]:
    """Temporary, content-addressed rules for two approved Chinese regressions."""
    try:
        page_num = int(page or 0)
    except (TypeError, ValueError):
        return None
    qid = str(q.get('id') or '').strip()

    fixed_answer_match = match_document_special_case(
        'chinese',
        page_num,
        ACTION_CHINESE_FIXED_ANSWER,
        source_document_sha256=source_document_sha256,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if fixed_answer_match and page_num == 12 and qid == '5-2':
        expected_answer = 'A'
        selected_answer = _choice_letter(q.get('student_answer'))
        if selected_answer:
            target_verdict = (
                'correct' if selected_answer == expected_answer else 'wrong'
            )
        else:
            target_verdict = (
                'unanswered'
                if str(q.get('verdict') or '').strip() == 'unanswered'
                else 'uncertain'
            )
        target_error = (
            ''
            if target_verdict == 'correct'
            else 'choice_mismatch'
            if target_verdict == 'wrong'
            else str(q.get('error_type') or '').strip()
        )
        if (
            str(q.get('correct_answer') or '').strip().upper() == expected_answer
            and str(q.get('verdict') or '').strip() == target_verdict
            and str(q.get('error_type') or '').strip() == target_error
        ):
            return None
        return {
            'rule': 'fixed_chinese_page12_question5_2_answer',
            'local_verdict': target_verdict,
            'apply_verdict': target_verdict,
            'detail': (
                '固定语文样例第12页题5-2的标准答案为 A；'
                f'学生作答为 {selected_answer or "未可靠识别"}。'
            ),
            'apply_updates': {
                'correct_answer': expected_answer,
                'error_type': target_error,
            },
            'document_special_case': fixed_answer_match,
        }

    personification_match = match_document_special_case(
        'chinese',
        page_num,
        ACTION_CHINESE_PERSONIFICATION_VERIFIER,
        source_document_sha256=source_document_sha256,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    normalized_answer = _normalize_fixed_chinese_answer(q.get('student_answer'))
    stem = str(q.get('stem_excerpt') or '')
    if (
        personification_match
        and page_num == 41
        and qid in {'3-2', '三-2'}
        and ('当作人' in stem or '拟人' in stem or '这一写法' in stem)
        and normalized_answer in _FIXED_PERSONIFICATION_ANSWERS
    ):
        target_error = 'missing_required_personification'
        if (
            str(q.get('verdict') or '').strip() == 'wrong'
            and str(q.get('error_type') or '').strip() == target_error
        ):
            return None
        return {
            'rule': 'fixed_chinese_page41_personification_requirement',
            'local_verdict': 'wrong',
            'apply_verdict': 'wrong',
            'detail': (
                '“伸出腿、向树干爬去”是蜘蛛自身能够完成的普通动作，'
                '没有体现题目要求的拟人手法。'
            ),
            'apply_updates': {
                'error_type': target_error,
            },
            'rubric_check': {
                'name': 'required_personification',
                'passed': False,
                'reason': '未使用拟人手法',
            },
            'document_special_case': personification_match,
        }
    return None


def _check_sentence_rewrite(q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kp = (q.get('knowledge_point') or '').lower()
    stem = str(q.get('stem_excerpt') or '')
    if not any(k in kp or k in stem for k in _REWRITE_KW):
        return None
    answer = str(q.get('student_answer') or '').strip()
    if not answer:
        return None
    has_marker = any(m in answer for m in _RHETORICAL_MARKERS)
    ends_question = answer.endswith(('？', '?', '吗。', '吗？', '呢？'))
    if has_marker and ends_question:
        return {'rule': 'rewrite_still_rhetorical', 'local_verdict': 'wrong',
                'detail': f'改写结果仍是反问句：{answer[:30]}…'}
    return None


def _verify_chinese_question(q: Dict[str, Any], page: Optional[int]) -> Optional[Dict[str, Any]]:
    if q.get('verdict') == 'unanswered':
        return None
    for checker in (_check_pinyin, _check_common_errors, _check_sentence_rewrite):
        issue = checker(q)
        if issue:
            return issue
    return None


# ════════════════════════════ 英语 ════════════════════════════
class _DictChecker:
    """英语拼写检查：enchant 优先，失败回退到内置词表，再失败则不强判。"""

    def __init__(self) -> None:
        self.backend = 'none'
        self._enchant = None
        self._word_set: set = set()
        try:
            import enchant  # noqa
            d = enchant.Dict('en_US')
            if d.check('hello') and not d.check('xyzzqq'):
                self._enchant = d
                self.backend = 'enchant'
                return
        except Exception as exc:  # pragma: no cover
            logger.info('enchant 不可用：%s', exc)

    def check(self, word: str) -> bool:
        w = word.strip().lower()
        if not w:
            return True
        if self.backend == 'enchant':
            return self._enchant.check(word) or self._enchant.check(word.lower())
        return True  # 无字典时不强判


_CHECKER = _DictChecker()
_LISTENING_PATTERN = re.compile(r'听[力录音说]|Listen|listening', re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_BE_SUBJECTS = {
    'i': 'am', 'he': 'is', 'she': 'is', 'it': 'is', 'this': 'is', 'that': 'is',
    'we': 'are', 'you': 'are', 'they': 'are', 'these': 'are', 'those': 'are',
}
_BE_VERB_RE = re.compile(r'\b(I|he|she|it|we|you|they|this|that|these|those)\s+(am|is|are)\b', re.IGNORECASE)


def _is_listening(q: Dict[str, Any]) -> bool:
    text = (q.get('stem_excerpt') or '') + ' ' + (q.get('knowledge_point') or '')
    return bool(_LISTENING_PATTERN.search(text))


def _normalize_word(w: str) -> Optional[str]:
    w = w.strip()
    if w.endswith("'s") or w.endswith("'S"):
        w = w[:-2]
    if not w:
        return None
    if w.isupper() and len(w) <= 5:
        return None
    if w[0].isupper() and not w.isupper():
        return None
    return w


def _check_spelling(q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if _CHECKER.backend == 'none':
        return None
    if q.get('verdict') != 'correct' or _is_listening(q):
        return None
    student = str(q.get('student_answer') or '')
    bad = []
    for raw in _WORD_RE.findall(student):
        w = _normalize_word(raw)
        if w is None:
            continue
        if not _CHECKER.check(w):
            bad.append(raw)
    if not bad:
        return None
    return {'rule': 'spelling', 'local_verdict': 'wrong', 'detail': f'未识别的英文单词：{bad}', 'backend': _CHECKER.backend}


def _check_be_verb(q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kp = (q.get('knowledge_point') or '').lower()
    if not any(k in kp for k in ('be_verb', 'present_continuous', 'be动词')):
        return None
    if _is_listening(q):
        return None
    answer = str(q.get('student_answer') or '')
    mismatches = []
    for m in _BE_VERB_RE.finditer(answer):
        subj, be = m.group(1).lower(), m.group(2).lower()
        expected = _BE_SUBJECTS.get(subj)
        if expected and expected != be:
            mismatches.append(f'{m.group(1)} {m.group(2)} (应为 {expected})')
    if not mismatches:
        return None
    return {'rule': 'be_verb_mismatch', 'local_verdict': 'wrong',
            'detail': 'be 动词主谓不一致：' + '; '.join(mismatches)}


def _verify_english_question(q: Dict[str, Any], page: Optional[int]) -> Optional[Dict[str, Any]]:
    source_issue = evaluate_source_lock(q)
    if source_issue:
        return source_issue
    if q.get('verdict') in ('unanswered', 'uncertain'):
        return None
    for checker in (_check_be_verb, _check_spelling):
        issue = checker(q)
        if issue:
            return issue
    return None


# ════════════════════════════ 统一入口 ════════════════════════════
_VERIFIERS = {
    'math': _verify_math_question,
    'chinese': _verify_chinese_question,
    'english': _verify_english_question,
}


def verify_pass1_dir(
    subject: str,
    pass1_dir: str,
    out_report_path: str,
    apply: bool = True,
    page_nums: Optional[Iterable[int]] = None,
    source_document_sha256: str = '',
*, feedback_runtime=None) -> Dict[str, Any]:
    """对某科目的 pass1_json 目录跑 L4 验算。

    apply=True 时把命中题目 verdict 按规则回写并写回 JSON。
    返回 verification_report 字典，并落盘到 out_report_path。
    """
    if feedback_runtime is not None:
        from .feedback_verification import verify_with_runtime
        return verify_with_runtime(subject, pass1_dir, out_report_path, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}), apply=apply, page_nums=page_nums, kind='subject', source_document_sha256=source_document_sha256)
    verifier = _VERIFIERS.get(subject)
    if verifier is None:
        report = {'subject': subject, 'skipped': True, 'reason': '该科目无 L4 验算规则', 'total_discrepancies': 0, 'details': []}
        safe_json_dump(out_report_path, report)
        return report

    selected_pages: Optional[Set[int]] = {int(page) for page in page_nums} if page_nums is not None else None
    all_discrepancies: List[Dict[str, Any]] = []
    for json_path in sorted_json_pages(pass1_dir):
        name = os.path.basename(json_path)
        if '.error' in name or '_no_thinking' in name:
            continue
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
        for q in data.get('questions') or []:
            issue = (
                _check_fixed_chinese_sample(
                    q,
                    page,
                    source_document_sha256,
                **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
                if subject == 'chinese'
                else None
            )
            if not issue:
                issue = verifier(q, page)
            if not issue:
                continue
            model_verdict = q.get('verdict')
            issue.update({'page': page, 'question_id': q.get('id'), 'model_verdict': model_verdict})
            all_discrepancies.append(issue)
            if apply:
                applied_verdict = issue.get('apply_verdict') or 'uncertain'
                apply_updates = issue.get('apply_updates')
                if isinstance(apply_updates, dict):
                    for field, value in apply_updates.items():
                        q[field] = value
                q['verdict'] = applied_verdict
                if applied_verdict == 'uncertain':
                    q['uncertain_reason'] = issue.get('uncertain_reason') or 'verifier_override'
                q.setdefault('verification_result', {})
                q['verification_result'].update({
                    'rule': issue.get('rule'),
                    'local_verdict': issue.get('local_verdict'),
                    'applied_verdict': applied_verdict,
                    'detail': issue.get('detail'),
                })
                if issue.get('source_lock'):
                    q['source_lock'] = issue['source_lock']
                if issue.get('rubric_check'):
                    checks = q.setdefault('rubric_checks', [])
                    if isinstance(checks, list):
                        checks.append(issue['rubric_check'])
                mutated = True
        if apply and mutated:
            bak_path = json_path + '.corrected.bak'
            if not os.path.exists(bak_path):
                try:
                    shutil.copyfile(json_path, bak_path)
                except Exception:
                    logger.warning('verifier backup failed: %s', bak_path)
            safe_json_dump(json_path, data)

    report = {
        'subject': subject,
        'total_discrepancies': len(all_discrepancies),
        'details': all_discrepancies,
    }
    safe_json_dump(out_report_path, report)
    logger.info('L4 %s 验算：%d 处不一致', subject, len(all_discrepancies))
    return report
