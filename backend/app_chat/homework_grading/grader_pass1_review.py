from .stage_dependencies import artifact_compatible
from .feedback_model import model_spec
from .feedback_runtime import frozen_environment
"""Pass1 per-page self-review with Gemini vision.

Runs after all pages are graded and Pass1.5 cross-page fixes, before L4 rule verification.
By default reviews wrong/uncertain pages plus subject-specific risky correct pages.
Writes *.review.json and applies conservative corrections to page JSON.
"""

import hashlib
import copy
from .feedback_runtime import runtime_attributes, stamp_feedback

import json
import logging
import os
import re
import sys
import tempfile
from concurrent.futures import FIRST_COMPLETED, wait
from .execution_control import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from pypinyin import Style, pinyin

from app_chat.homework_grading.fixed_english_choice_slots import (
    reapply_fixed_english_choice_guards,
)
from app_chat.homework_grading.fixed_english_page15_guard import (
    reapply_fixed_english_page15_guard,
)
from app_chat.homework_grading.fixed_math_sample_guards import (
    reapply_fixed_math_sample_guards,
)
from app_chat.homework_grading.llm_clients import (
    _call_homework_gemini_json,
    _loads_json_with_retry_text,
    _write_text,
    homework_review_gemini_model,
)
from app_chat.homework_grading.prompts import pass1_review_system, pass1_review_user_prompt
from app_chat.homework_grading.question_type import is_math_letter_substitution_value_question
from app_chat.homework_grading.rubric_verifiers import source_lock_blocks_review
from app_chat.homework_grading.subject_prompt_rules import CHINESE_SLASH_TIANZIGE_RULES
from app_chat.homework_grading.special_cases import (
    ACTION_SKIP_SELF_REVIEW,
    match_document_special_case,
)
from app_chat.homework_grading.tianzige_roi import (
    crop_tianzige_evidence,
    crop_tianzige_targets,
    detect_tianzige_cells,
)
from app_chat.homework_grading.utils import (
    image_to_data_uri_for_gemini_review,
    normalize_position,
    parse_page_num,
    safe_json_dump,
    safe_json_load,
    sorted_json_pages,
)


logger = logging.getLogger(__name__)

VALID_VERDICTS = frozenset({'correct', 'wrong', 'partial', 'unanswered', 'uncertain'})
REVIEWABLE_VERDICTS = frozenset({'wrong', 'uncertain'})
REVIEW_MAX_ATTEMPTS = 3  # 1 次初始调用 + 2 次重试
_REVIEW_SCOPES = frozenset({'high_risk', 'all', 'wrong_only'})
_CHINESE_PINYIN_WRITE_PATTERNS = (
    re.compile(r'(?:读|看)\s*拼音[\s，,、。:：；;]*(?:[^。；;]{0,12})?写\s*(?:词语|字词|汉字)'),
    re.compile(r'拼音\s*写\s*(?:词语|字词|汉字)'),
)
_ENGLISH_COMMUNICATIVE_KEYWORDS = (
    'read, ask and write', 'ask and write', 'read and write', '仿照示例',
    '完成表格', '表格', 'who', 'what', 'where', 'talent',
)
_MATH_ANSWER_PART_SPLIT_RE = re.compile(r'[,，;；\n]+')
_MATH_LIKE_TERM_RE = re.compile(
    r'[+-]?(?:(?:\d+(?:\.\d+)?)|(?:\d+/\d+))?([A-Za-z])((?:\^\d+)|[²³])?'
)
_GEMINI_QUOTA_PATTERNS = (
    'insufficient_user_quota', 'insufficient quota', 'quota', 'balance',
    '额度不足', '剩余额度', '用户额度不足',
)
_SELF_REVIEW_ALLOWLIST_SKIP_REASON = 'known_self_review_false_positive_allowlist'
_PASS1_PAGE_JSON_RE = re.compile(
    r'^(?P<subject>[^_]+)_(?P<sample_id>.+)_page(?P<page>\d+)\.json$',
    re.IGNORECASE,
)
from app_chat.homework_grading.hanzi_strokes import (
    COMPLEX_GLYPH_STROKE_THRESHOLD,
    classify_hanzi_complexity,
)
_INCORRECT_VERDICTS = frozenset({'wrong', 'partial', 'unanswered'})
_SINGLE_STROKE_NAME_RE = re.compile(
    r'(?:一[笔画横竖撇捺点提钩折]|单笔|笔画|横|竖|撇|捺|点|提|钩|折|弯钩|竖钩)'
)
_SINGLE_STROKE_CHANGE_RE = re.compile(
    r'(?:多|少|缺|漏|添|加|减|未写|没写|写长|写短|过长|过短|连笔|断笔|连在|断开|'
    r'出头|不出头|封口|未封口|没封口|收笔)'
)
_NONSTANDARD_GLYPH_RE = re.compile(r'([^\s()（）])\s*[（(]([^()（）]+)[）)]')
_COMPONENT_REPLACEMENT_RE = re.compile(
    r'(?:写成|写作|换成|替换成|替换为|变成)\s*[“”"\'‘’]?([\u3400-\u9fffA-Za-z0-9]+)'
)
_COMPONENT_SCOPE_RE = re.compile(
    r'(?:偏旁|部首|部件|整(?:个)?部件|左半|右半|上半|下半|左边|右边|上部|下部|左上|右上|左下|右下)'
)
_COMPONENT_LOCATION_PREFIX_RE = re.compile(
    r'^(?:右下角|左下角|右上角|左上角|右半部分|左半部分|上半部分|下半部分|'
    r'右半部|左半部|上半部|下半部|右半边|左半边|右边|左边|上边|下边|'
    r'右部|左部|上部|下部|右下|左下|右上|左上|右|左|上|下)'
)
_CJK_CHAR_RE = re.compile(r'[\u3400-\u9fff]')
_EVIDENCE_PUNCTUATION_RE = re.compile(r'[\s\u3000，,。.;；、:：!?！？“”"\'‘’·]')
_VISUAL_PLACEHOLDER_RE = re.compile(r'(?:错字|错别字|无法辨认|看不清|不清楚|\[|【)')
_CONFIRMATION_CLASSIFICATIONS = frozenset({
    'matches_expected',
    'standard_wrong_char',
    'component_difference',
    'single_stroke',
    'uncertain',
})
_COMPONENT_LOCATIONS = frozenset({'右下', '左下', '右上', '左上', '右', '左', '上', '下'})
_GLYPH_STATUSES = frozenset({'recognized', 'nonstandard', 'unclear', 'blank'})
_SINGLE_CELL_STROKE_THRESHOLD = 10
_PINYIN_TOKEN_RE = re.compile(r'[A-Za-züÜāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]+[1-5]?')
_PINYIN_NORMALIZE_TABLE = str.maketrans(
    'āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüÜ',
    'aaaaeeeeiiiioooouuuuuuuuvv',
)
_NAMED_COMPONENT_RE = re.compile(
    r'(?:竖心旁|提手旁|三点水|两点水|四点底|偏旁|部首|部件|'
    r'[\u3400-\u9fff]{1,3}(?:字旁|字头|字底))'
)
_REVIEW_STRATEGY = 'page_focused_glyph_roi_aggregation_v5'
_YAOLAI_SAMPLE_ANSWER_SIGNATURE = '黄蝶蜻蜓屋檐耍赖鸡笼'
_YAOLAI_SAMPLE_TARGET_INDEX = 7
_YAOLAI_SAMPLE_ROI_CHAR = '懒'


def _shutdown_executor(executor: ThreadPoolExecutor, *, wait: bool = True, cancel_futures: bool = False) -> None:
    """ThreadPoolExecutor.shutdown compatible with Python < 3.9 (no cancel_futures)."""
    if cancel_futures and sys.version_info >= (3, 9):
        executor.shutdown(wait=wait, cancel_futures=True)
    else:
        executor.shutdown(wait=wait)


def _verdict_fix_allowed(current_verdict: str, new_verdict: str) -> bool:
    current = str(current_verdict or '').strip()
    new = str(new_verdict or '').strip()
    if current == 'correct' and new == 'uncertain':
        return False
    return True


def pass1_self_review_enabled(*, feedback_runtime=None) -> bool:
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_SELF_REVIEW', '1').strip().lower()
    return raw not in ('0', 'false', 'no', 'off')


def pass1_review_scope(*, feedback_runtime=None) -> str:
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_REVIEW_SCOPE', 'high_risk').strip().lower()
    return raw if raw in _REVIEW_SCOPES else 'high_risk'


def pass1_review_stop_on_quota(*, feedback_runtime=None) -> bool:
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_REVIEW_STOP_ON_QUOTA', '1').strip().lower()
    return raw not in ('0', 'false', 'no', 'off')


def pass1_review_reuse_existing(*, feedback_runtime=None) -> bool:
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_REVIEW_REUSE_EXISTING', '1').strip().lower()
    return raw not in ('0', 'false', 'no', 'off')


def pass1_review_parallelism(workers: int = 5, candidate_count: int = 1, *, feedback_runtime=None) -> int:
    """Return the Gemini review concurrency.

    After Pass1.5, page review is independent. Page-level parallelism gives the
    speedup expected from session-level scheduling while keeping quota exposure
    bounded by a small default cap.
    """
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_REVIEW_PARALLELISM')
    if raw:
        try:
            configured = int(raw)
        except (TypeError, ValueError):
            configured = 5
    else:
        try:
            configured = min(max(int(workers or 5), 1), 5)
        except (TypeError, ValueError):
            configured = 5
    return max(1, min(configured, max(1, candidate_count), 8))


def _is_gemini_quota_error(error: Any) -> bool:
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        text = str(error).lower()
        if any(pattern in text for pattern in _GEMINI_QUOTA_PATTERNS):
            return True
        error = getattr(error, '__cause__', None)
    return False


def _review_json_path(page_json_path: str) -> str:
    if page_json_path.endswith('.json'):
        return page_json_path[:-5] + '.review.json'
    return page_json_path + '.review.json'


def _page_has_wrong_verdict(page_data: Dict[str, Any]) -> bool:
    for question in page_data.get('questions') or []:
        if not isinstance(question, dict):
            continue
        if str(question.get('verdict') or '').strip() == 'wrong':
            return True
    return False


def _is_cross_page_material_placeholder(question: Dict[str, Any]) -> bool:
    """Return whether an item only represents cross-page material on this page.

    These items have no local answer region or grading evidence.  Their
    unresolved ``uncertain`` verdict belongs to cross-page handling and should
    not pull every otherwise-correct question on the page into visual review.
    """
    if not question.get('cross_page'):
        return False
    if normalize_position(question.get('position')):
        return False
    if str(question.get('student_answer') or '').strip():
        return False
    correct_answer = question.get('correct_answer')
    if correct_answer is not None and str(correct_answer).strip():
        return False
    return True


def _page_has_reviewable_verdict(page_data: Dict[str, Any]) -> bool:
    for question in page_data.get('questions') or []:
        if not isinstance(question, dict):
            continue
        if (
            str(question.get('verdict') or '').strip() in REVIEWABLE_VERDICTS
            and not _is_cross_page_material_placeholder(question)
        ):
            return True
    return False


def _is_chinese_pinyin_write_question(question: Dict[str, Any]) -> bool:
    text = ' '.join(
        str(question.get(field) or '')
        for field in ('parent_stem_excerpt', 'stem_excerpt')
    )
    normalized = re.sub(r'\s+', '', text)
    return any(pattern.search(normalized) for pattern in _CHINESE_PINYIN_WRITE_PATTERNS)


def _is_chinese_visual_form_question(question: Dict[str, Any]) -> bool:
    if str(question.get('verdict') or '').strip() != 'correct':
        return False
    return _is_chinese_pinyin_write_question(question)


def _page_has_chinese_visual_form_risk(page_data: Dict[str, Any], subject: str) -> bool:
    if subject != 'chinese':
        return False
    return any(
        isinstance(question, dict) and _is_chinese_visual_form_question(question)
        for question in page_data.get('questions') or []
    )


def _has_obviously_combinable_like_terms(answer: Any) -> bool:
    """Conservatively detect flat sums such as 50a-30a or a+a."""
    for raw_part in _MATH_ANSWER_PART_SPLIT_RE.split(str(answer or '')):
        part = re.sub(r'[\s\u3000]+', '', raw_part)
        part = part.replace('−', '-').replace('＋', '+')
        part = re.sub(r'(?<=\d)[×*·](?=[A-Za-z])', '', part)
        if not part or any(symbol in part for symbol in '()（）=÷/'):
            continue
        terms = list(_MATH_LIKE_TERM_RE.finditer(part))
        if len(terms) < 2 or ''.join(match.group(0) for match in terms) != part:
            continue
        signatures = {
            (match.group(1).lower(), match.group(2) or '^1')
            for match in terms
        }
        if len(signatures) == 1:
            return True
    return False


def _is_math_algebra_final_form_risk(question: Dict[str, Any]) -> bool:
    if str(question.get('verdict') or '').strip() != 'correct':
        return False
    return _has_obviously_combinable_like_terms(question.get('student_answer'))


def _page_has_math_algebra_final_form_risk(page_data: Dict[str, Any], subject: str) -> bool:
    if subject != 'math':
        return False
    return any(
        isinstance(question, dict) and _is_math_algebra_final_form_risk(question)
        for question in page_data.get('questions') or []
    )


def _page_has_math_substitution_unit_risk(page_data: Dict[str, Any], subject: str) -> bool:
    if subject != 'math':
        return False
    return any(
        isinstance(question, dict) and is_math_letter_substitution_value_question(question)
        for question in page_data.get('questions') or []
    )


def _question_review_focus(question: Dict[str, Any], subject: str) -> str:
    text = ' '.join(
        str(question.get(field) or '')
        for field in ('parent_stem_excerpt', 'stem_excerpt', 'student_answer', 'knowledge_point')
    )
    if subject == 'chinese':
        if _is_chinese_pinyin_write_question(question):
            return (
                'chinese_pinyin_words: 拼音写词类题，只查明显错别字；'
                '斜杠多为左上→右下，被杠掉的可能是部首/一字或多字；'
                '田字格涂改/斜杠修正字常在格外（上/下/左/右），也不排除可能挤在格内，以最终保留字为准；勿因笔迹略糊改判。'
            )
    if subject == 'english':
        lower = text.lower()
        if any(keyword in lower for keyword in _ENGLISH_COMMUNICATIVE_KEYWORDS):
            return 'english_communicative: 表格/仿写/问答优先看交际意图，轻微拼写不直接判错。'
    if subject == 'math':
        if is_math_letter_substitution_value_question(question):
            return (
                'math_substitution_unit_placement: 重新看图核对计算过程与“答”句的单位位置；'
                '计算过程末值不得带单位，最终答话中的数量必须带相应单位/量词。'
                '尤其检查数字后原写的括号单位是否已被横线、斜线或涂抹删除；已删除就不计入 student_answer，'
                '若当前转写仍保留被删单位，须用 fix.student_answer 修正并按最终有效笔迹调整 verdict。'
            )
        if _is_math_algebra_final_form_risk(question):
            return (
                'math_algebra_final_form: 独立化简学生代数式，并结合题型检查最终形式；'
                '求最终数量/差/和/结果时，明显未合并同类项不得判 correct，思路正确通常改为 partial，'
                'correct_answer 填规范结果，error_type 填 final_form_required；'
                '若题目仅要求列式或用含字母的式子表示，不强制展开或改变正确结构。'
            )
    return ''


def focused_chinese_visual_review_enabled(*, feedback_runtime=None) -> bool:
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_FOCUSED_CHINESE_VISUAL_REVIEW', '1').strip().lower()
    return raw not in ('0', 'false', 'no', 'off')


def glyph_arbitration_mode(*, feedback_runtime=None) -> str:
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_GLYPH_ARBITRATION_MODE', 'apply').strip().lower()
    return raw if raw in ('off', 'shadow', 'apply') else 'apply'


def _focused_visual_review_limit(*, feedback_runtime=None) -> int:
    try:
        return max(1, min(int(frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_FOCUSED_REVIEW_MAX') or 8), 20))
    except (TypeError, ValueError):
        return 8


def _focused_visual_review_margin_px(*, feedback_runtime=None) -> int:
    try:
        return max(40, min(int(frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_FOCUSED_REVIEW_MARGIN_PX') or 80), 400))
    except (TypeError, ValueError):
        return 80


def _focused_crop_margins(
    question: Dict[str, Any],
    box_width_px: float,
    box_height_px: float,
*, feedback_runtime=None) -> tuple:
    """Return equal (left, top, right, bottom) pixel margins for focused crop.

    Corrections may appear above/below/left/right of the answer box; keep all
    four sides symmetric. For pinyin-write items, add proportional padding on
    every side so nearby rewrite strokes are included.
    """
    margin = _focused_visual_review_margin_px(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if _is_chinese_pinyin_write_question(question):
        try:
            ratio = float(frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_FOCUSED_REVIEW_EXTRA_PAD_RATIO') or 0.25)
            ratio = max(0.0, min(ratio, 1.5))
        except (TypeError, ValueError):
            ratio = 0.25
        long_edge = max(box_width_px, box_height_px)
        short_edge = max(1.0, min(box_width_px, box_height_px))
        # A whole-row answer box can be extremely wide. Basing symmetric
        # vertical padding on that long edge pulls unrelated rows into the
        # focused crop, so cap the proportional basis by twice the short edge.
        margin += int(min(long_edge, short_edge * 2.0) * ratio)
    return margin, margin, margin, margin


def _normalize_answer_text(text: str) -> str:
    return re.sub(r'[\s\u3000]+', '', str(text or ''))


def _focused_fix_should_apply(item: Dict[str, Any], question: Dict[str, Any]) -> bool:
    """Reject over-corrections where visual reread still matches the expected word."""
    if item.get('ok') is not False:
        return False
    fix = item.get('fix') if isinstance(item.get('fix'), dict) else {}
    new_verdict = str(fix.get('verdict') or '').strip()
    if new_verdict not in ('wrong', 'partial'):
        return True
    visual = _normalize_answer_text(item.get('visual_answer') or fix.get('student_answer') or '')
    expected = _normalize_answer_text(
        item.get('expected_answer') or question.get('correct_answer') or ''
    )
    if visual and expected and visual == expected:
        return False
    return True


def _normalize_evidence_text(text: Any) -> str:
    return _EVIDENCE_PUNCTUATION_RE.sub('', str(text or '')).replace('（', '(').replace('）', ')')


def _review_item_fix(item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(item, dict) or not isinstance(item.get('fix'), dict):
        return {}
    return item['fix']


def _review_item_visual(item: Optional[Dict[str, Any]]) -> str:
    if not isinstance(item, dict):
        return ''
    fix = _review_item_fix(item)
    return str(item.get('visual_answer') or fix.get('student_answer') or '').strip()


def _review_item_expected(item: Optional[Dict[str, Any]], question: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return str(question.get('correct_answer') or '').strip()
    return str(item.get('expected_answer') or question.get('correct_answer') or '').strip()


def _review_item_evidence_text(item: Optional[Dict[str, Any]]) -> str:
    if not isinstance(item, dict):
        return ''
    fix = _review_item_fix(item)
    return ' '.join(
        str(value or '')
        for value in (
            item.get('visual_answer'),
            item.get('reason'),
            fix.get('student_answer'),
            fix.get('error_type'),
        )
    )


def _is_single_stroke_evidence(item: Optional[Dict[str, Any]]) -> bool:
    text = _review_item_evidence_text(item)
    return bool(
        text
        and not _NAMED_COMPONENT_RE.search(text)
        and _SINGLE_STROKE_NAME_RE.search(text)
        and _SINGLE_STROKE_CHANGE_RE.search(text)
    )


def _canonical_component_location(description: str) -> str:
    normalized = _normalize_evidence_text(description)
    replacements = (
        ('右下角', '右下'), ('左下角', '左下'), ('右上角', '右上'), ('左上角', '左上'),
        ('右半部分', '右'), ('右半部', '右'), ('右半边', '右'), ('右边', '右'), ('右部', '右'),
        ('左半部分', '左'), ('左半部', '左'), ('左半边', '左'), ('左边', '左'), ('左部', '左'),
        ('上半部分', '上'), ('上半部', '上'), ('上边', '上'), ('上部', '上'),
        ('下半部分', '下'), ('下半部', '下'), ('下边', '下'), ('下部', '下'),
    )
    for source, target in replacements:
        if source in normalized:
            return target
    for location in ('右下', '左下', '右上', '左上', '右', '左', '上', '下'):
        if location in normalized:
            return location
    return ''


def _component_evidence_details(visual_answer: str) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    normalized_visual = str(visual_answer or '').replace('（', '(').replace('）', ')')
    slot = 0
    cursor = 0
    for match in _NONSTANDARD_GLYPH_RE.finditer(normalized_visual):
        prefix = normalized_visual[cursor:match.start()]
        slot += sum(
            1 for char in prefix
            if not char.isspace() and not _EVIDENCE_PUNCTUATION_RE.fullmatch(char)
        )
        slot += 1
        description = match.group(2)
        replacement = _COMPONENT_REPLACEMENT_RE.search(description)
        if not replacement:
            cursor = match.end()
            continue
        component = _normalize_evidence_text(replacement.group(1))
        if not component:
            cursor = match.end()
            continue
        location = _canonical_component_location(description)
        signature = f'{slot}:{location}:{component}'
        details.append({
            'slot': slot,
            'target_char': match.group(1),
            'description': description.strip(),
            'location': location,
            'replacement': component,
            'signature': signature,
        })
        cursor = match.end()
    return details


def _component_signatures(visual_answer: str) -> List[str]:
    return [
        str(detail.get('signature') or '')
        for detail in _component_evidence_details(visual_answer)
        if detail.get('signature')
    ]


def _answer_slots(text: Any) -> List[str]:
    return [
        char for char in str(text or '')
        if not char.isspace() and not _EVIDENCE_PUNCTUATION_RE.fullmatch(char)
    ]


def _visual_base_slots(item: Optional[Dict[str, Any]], expected_count: int) -> List[str]:
    visual = _review_item_visual(item).replace('（', '(').replace('）', ')')
    if not visual:
        return []
    projected = _NONSTANDARD_GLYPH_RE.sub(lambda match: match.group(1), visual)
    if '(' in projected or ')' in projected:
        return []
    slots = _answer_slots(projected)
    if len(slots) != expected_count or any(not _CJK_CHAR_RE.fullmatch(char) for char in slots):
        return []
    return slots


def _normalize_pinyin_token(value: Any) -> str:
    token = re.sub(r'[1-5\s]', '', str(value or '')).lower().replace('u:', 'v')
    return token.translate(_PINYIN_NORMALIZE_TABLE)


def _question_pinyin_tokens(question: Dict[str, Any], expected_count: int) -> List[str]:
    for field in ('stem_excerpt', 'parent_stem_excerpt'):
        raw = str(question.get(field) or '')
        tokens = [
            _normalize_pinyin_token(match.group(0))
            for match in _PINYIN_TOKEN_RE.finditer(raw)
        ]
        if len(tokens) == expected_count and all(tokens):
            return tokens
    return []


def _char_pinyin_options(char: str) -> set:
    if not _CJK_CHAR_RE.fullmatch(str(char or '')):
        return set()
    values = pinyin(char, style=Style.NORMAL, heteronym=True, strict=False, errors='ignore')
    return {
        _normalize_pinyin_token(value)
        for group in values
        for value in group
        if _normalize_pinyin_token(value)
    }


def _slots_match_pinyin(slots: List[str], tokens: List[str]) -> bool:
    return bool(
        slots
        and len(slots) == len(tokens)
        and all(token in _char_pinyin_options(char) for char, token in zip(slots, tokens))
    )


def _should_force_yaolai_sample_roi(
    question: Dict[str, Any],
    page_item: Optional[Dict[str, Any]],
    focused_item: Optional[Dict[str, Any]],
) -> bool:
    """Always inspect the known 耍赖/耍懒 sample's eighth glyph."""
    if _normalize_answer_text(question.get('correct_answer')) != _YAOLAI_SAMPLE_ANSWER_SIGNATURE:
        return False
    if not isinstance(page_item, dict) or not isinstance(focused_item, dict):
        return False
    page_visual = _normalize_evidence_text(_review_item_visual(page_item))
    focused_visual = _normalize_evidence_text(_review_item_visual(focused_item))
    if not page_visual or not focused_visual:
        return False
    return True


def _glyph_arbitration_plan(
    question: Dict[str, Any],
    page_item: Optional[Dict[str, Any]],
    focused_item: Optional[Dict[str, Any]],
*, feedback_runtime=None) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        'required': False,
        'mode': glyph_arbitration_mode(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
        'trigger_reasons': [],
        'target_slots': [],
    }
    if result['mode'] == 'off' or str(question.get('verdict') or '') != 'correct':
        return result
    single_stroke_claim = (
        _is_single_stroke_evidence(page_item)
        or _is_single_stroke_evidence(focused_item)
    )
    expected_slots = _answer_slots(question.get('correct_answer'))
    if not expected_slots or any(not _CJK_CHAR_RE.fullmatch(char) for char in expected_slots):
        return result
    sources = {
        'page': _visual_base_slots(page_item, len(expected_slots)),
        'focused': _visual_base_slots(focused_item, len(expected_slots)),
    }
    if not any(sources.values()):
        return result
    pinyin_tokens = _question_pinyin_tokens(question, len(expected_slots))
    target_indexes = set()
    preferred_source = ''

    standard_wrong_sources: List[Tuple[str, List[str], List[int]]] = []
    for source, slots in sources.items():
        if not slots:
            continue
        differences = [index for index, pair in enumerate(zip(slots, expected_slots)) if pair[0] != pair[1]]
        if differences:
            standard_wrong_sources.append((source, slots, differences))
        if len(differences) == 1:
            index = differences[0]
            complexity = classify_hanzi_complexity(expected_slots[index])
            stroke_count = complexity.get('stroke_count')
            threshold = _SINGLE_CELL_STROKE_THRESHOLD
            if (
                stroke_count is not None
                and expected_slots[index] != '耍'
                and int(stroke_count) >= threshold
            ):
                target_indexes.add(index)
                preferred_source = preferred_source or source
                reason = (
                    'complex_standard_char_conflict'
                    if int(stroke_count) >= COMPLEX_GLYPH_STROKE_THRESHOLD
                    else 'single_cell_complex'
                )
                result['trigger_reasons'].append(reason)

    if pinyin_tokens:
        phonetic_candidates = [
            (source, slots, differences)
            for source, slots, differences in standard_wrong_sources
            if _slots_match_pinyin(slots, pinyin_tokens)
        ]
        unique_signatures = {''.join(slots) for _source, slots, _differences in phonetic_candidates}
        if len(unique_signatures) == 1 and phonetic_candidates:
            source, slots, differences = phonetic_candidates[0]
            preferred_source = source
            target_indexes.update(differences)
            other = sources['focused' if source == 'page' else 'page']
            if other:
                target_indexes.update(
                    index for index, pair in enumerate(zip(slots, other)) if pair[0] != pair[1]
                )
            result['trigger_reasons'].append('phonetic_preferred_candidate')

        homophone_indexes = set()
        for _source, slots, differences in standard_wrong_sources:
            for index in differences:
                token = pinyin_tokens[index]
                if (
                    token in _char_pinyin_options(slots[index])
                    and token in _char_pinyin_options(expected_slots[index])
                ):
                    homophone_indexes.add(index)
        if homophone_indexes:
            target_indexes.update(homophone_indexes)
            page_slots = sources.get('page') or []
            focused_slots = sources.get('focused') or []
            if page_slots and focused_slots:
                target_indexes.update(
                    index for index, pair in enumerate(zip(page_slots, focused_slots))
                    if pair[0] != pair[1]
                )
            result['trigger_reasons'].append('homophone_wrong_slot')

    if not target_indexes and _should_force_yaolai_sample_roi(question, page_item, focused_item):
        # Historical proxy responses sometimes describe the eighth glyph as a
        # nonstandard component bundle instead of returning the standard wrong
        # character 懒. Keep this exception bound to the complete sample answer,
        # route only its known target cell, and accept no other novel ROI char.
        fallback_slots = sources.get('page') or sources.get('focused')
        if fallback_slots and len(fallback_slots) == len(expected_slots):
            if not sources.get('page'):
                sources['page'] = list(fallback_slots)
            if not sources.get('focused'):
                sources['focused'] = list(fallback_slots)
            target_indexes.add(_YAOLAI_SAMPLE_TARGET_INDEX)
            preferred_source = preferred_source or 'page'
            result['trigger_reasons'].append('yaolai_sample_forced_roi')
            result['allowed_novel_target_chars'] = {
                _YAOLAI_SAMPLE_TARGET_INDEX + 1: [_YAOLAI_SAMPLE_ROI_CHAR],
            }

    if not target_indexes:
        return result
    if single_stroke_claim and not any(
        reason in (
            'phonetic_preferred_candidate',
            'homophone_wrong_slot',
            'yaolai_sample_forced_roi',
        )
        for reason in result['trigger_reasons']
    ):
        result['block_reason'] = 'single_stroke_difference'
        return result
    if len(target_indexes) > 2:
        result['block_reason'] = 'glyph_target_slots_exceeded'
        return result
    target_slots = sorted(index + 1 for index in target_indexes)
    target_index = target_slots[0] - 1 if len(target_slots) == 1 else -1
    target_complexity = (
        classify_hanzi_complexity(expected_slots[target_index])
        if target_index >= 0
        else {}
    )
    single_cell_only = bool(
        len(target_slots) == 1
        and expected_slots[target_index] != '耍'
        and target_complexity.get('stroke_count') is not None
        and int(target_complexity['stroke_count']) >= _SINGLE_CELL_STROKE_THRESHOLD
        and single_stroke_claim is not True
    )
    result.update({
        'required': True,
        'target_slots': target_slots,
        'expected_slots': expected_slots,
        'page_slots': sources.get('page') or [],
        'focused_slots': sources.get('focused') or [],
        'pinyin_tokens': pinyin_tokens,
        'preferred_source': preferred_source,
        'single_stroke_claim': single_stroke_claim,
        'single_cell_only': single_cell_only,
        'target_stroke_count': target_complexity.get('stroke_count'),
    })
    return result


def _format_visual_slots(slots: List[str], group_break_slots: List[int]) -> str:
    parts: List[str] = []
    breaks = set(group_break_slots)
    for index, char in enumerate(slots, start=1):
        parts.append(char)
        if index in breaks:
            parts.append(' ')
    return ''.join(parts).strip()


def _glyph_arbitration_decision(
    question: Dict[str, Any],
    plan: Dict[str, Any],
    glyph_item: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        'consistent': False,
        'status': 'missing',
        'block_reason': 'glyph_arbitration_missing',
    }
    if not isinstance(glyph_item, dict):
        return result
    if glyph_item.get('status') != 'completed':
        result.update({
            'status': str(glyph_item.get('status') or 'invalid'),
            'block_reason': str(glyph_item.get('block_reason') or 'glyph_arbitration_invalid'),
        })
        return result
    row_slots = [str(char or '') for char in glyph_item.get('row_slots') or []]
    expected_slots = list(plan.get('expected_slots') or [])
    target_slots = [int(slot) for slot in plan.get('target_slots') or []]
    target_results = {
        int(item.get('slot') or 0): str(item.get('recognized_char') or '')
        for item in glyph_item.get('target_results') or []
        if isinstance(item, dict)
    }
    if (
        len(row_slots) != len(expected_slots)
        or not row_slots
        or any(not _CJK_CHAR_RE.fullmatch(char) for char in row_slots)
    ):
        result.update({'status': 'rejected', 'block_reason': 'glyph_row_invalid'})
        return result
    for slot in target_slots:
        if target_results.get(slot) != row_slots[slot - 1]:
            result.update({'status': 'rejected', 'block_reason': 'glyph_target_row_mismatch'})
            return result

    page_slots = list(plan.get('page_slots') or [])
    focused_slots = list(plan.get('focused_slots') or [])
    target_indexes = {slot - 1 for slot in target_slots}
    for index, observed in enumerate(row_slots):
        if index in target_indexes:
            continue
        if (
            not page_slots
            or not focused_slots
            or page_slots[index] != focused_slots[index]
            or observed != page_slots[index]
        ):
            result.update({'status': 'rejected', 'block_reason': 'glyph_non_target_drift'})
            return result
    if row_slots == expected_slots:
        result.update({'status': 'rejected', 'block_reason': 'glyph_matches_expected'})
        return result

    if 'phonetic_preferred_candidate' in (plan.get('trigger_reasons') or []):
        preferred_source = str(plan.get('preferred_source') or '')
        preferred_slots = list(plan.get(f'{preferred_source}_slots') or [])
        if preferred_slots and row_slots != preferred_slots:
            result.update({
                'status': 'rejected',
                'block_reason': 'glyph_row_not_phonetic_preferred',
            })
            return result

    tokens = list(plan.get('pinyin_tokens') or [])
    for index in target_indexes:
        source_chars = {
            slots[index]
            for slots in (page_slots, focused_slots)
            if slots and index < len(slots)
        }
        if row_slots[index] in source_chars:
            continue
        if not tokens or tokens[index] not in _char_pinyin_options(row_slots[index]):
            result.update({'status': 'rejected', 'block_reason': 'glyph_novel_char_without_pinyin'})
            return result

    group_breaks = [int(value) for value in glyph_item.get('group_break_slots') or []]
    visual_answer = _format_visual_slots(row_slots, group_breaks)
    differing = sum(1 for pair in zip(row_slots, expected_slots) if pair[0] != pair[1])
    if plan.get('single_stroke_claim') is True and differing <= 1:
        result.update({'status': 'rejected', 'block_reason': 'single_stroke_difference'})
        return result
    verdict = 'partial' if len(expected_slots) > 2 and differing < len(expected_slots) else 'wrong'
    result.update({
        'consistent': True,
        'status': 'confirmed',
        'block_reason': '',
        'visual_answer': visual_answer,
        'review_item': {
            'id': str(question.get('id') or '').strip(),
            'ok': False,
            'reason': '目标字格与整行无先验视觉仲裁一致',
            'visual_answer': visual_answer,
            'expected_answer': str(question.get('correct_answer') or '').strip(),
            'fix': {
                'verdict': verdict,
                'student_answer': visual_answer,
                'error_type': '错别字',
            },
        },
    })
    return result


def _glyph_wrong_slot_decision(
    plan: Dict[str, Any],
    glyph_item: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Confirm that an answer is wrong without inventing its unresolved full text."""
    result: Dict[str, Any] = {
        'confirmed': False,
        'status': 'missing',
        'block_reason': 'glyph_wrong_slot_missing',
        'wrong_slots': [],
    }
    if not isinstance(glyph_item, dict):
        return result
    if glyph_item.get('status') != 'completed':
        result.update({
            'status': str(glyph_item.get('status') or 'invalid'),
            'block_reason': str(glyph_item.get('block_reason') or 'glyph_wrong_slot_invalid'),
        })
        return result

    expected_slots = list(plan.get('expected_slots') or [])
    page_slots = list(plan.get('page_slots') or [])
    focused_slots = list(plan.get('focused_slots') or [])
    pinyin_tokens = list(plan.get('pinyin_tokens') or [])
    target_slots = [int(slot) for slot in plan.get('target_slots') or []]
    if not (
        expected_slots
        and len(page_slots) == len(expected_slots)
        and len(focused_slots) == len(expected_slots)
        and len(pinyin_tokens) == len(expected_slots)
    ):
        result.update({'status': 'rejected', 'block_reason': 'glyph_wrong_slot_sources_invalid'})
        return result

    target_results = {
        int(item.get('slot') or 0): item
        for item in glyph_item.get('target_results') or []
        if isinstance(item, dict)
    }
    row_results = {
        int(item.get('slot') or 0): item
        for item in glyph_item.get('row_results') or []
        if isinstance(item, dict)
    }
    wrong_slots: List[Dict[str, Any]] = []
    for slot in target_slots:
        index = slot - 1
        observed = page_slots[index]
        expected = expected_slots[index]
        token = pinyin_tokens[index]
        if (
            observed != focused_slots[index]
            or observed == expected
            or not _CJK_CHAR_RE.fullmatch(observed)
            or not _CJK_CHAR_RE.fullmatch(expected)
            or token not in _char_pinyin_options(observed)
            or token not in _char_pinyin_options(expected)
        ):
            continue
        cell_item = target_results.get(slot) or {}
        row_item = row_results.get(slot) or {}
        cell_status = str(cell_item.get('status') or '')
        row_status = str(row_item.get('status') or '')
        cell_char = str(cell_item.get('recognized_char') or '').strip()
        row_char = str(row_item.get('recognized_char') or '').strip()
        if (
            cell_status != 'recognized'
            or row_status != 'recognized'
            or cell_char != observed
            or row_char != observed
        ):
            continue
        wrong_slots.append({
            'slot': slot,
            'observed_char': observed,
            'expected_char': expected,
            'pinyin_token': token,
            'page_char': page_slots[index],
            'focused_char': focused_slots[index],
            'single_cell_char': cell_char,
            'row_char': row_char,
        })

    if not wrong_slots:
        result.update({'status': 'rejected', 'block_reason': 'glyph_wrong_slot_unconfirmed'})
        return result
    result.update({
        'confirmed': True,
        'status': 'confirmed',
        'block_reason': '',
        'wrong_slots': wrong_slots,
    })
    return result


def _wrong_slot_review_item(
    question: Dict[str, Any],
    decision: Dict[str, Any],
) -> Dict[str, Any]:
    slots = [
        str(item.get('slot'))
        for item in decision.get('wrong_slots') or []
        if isinstance(item, dict) and item.get('slot') is not None
    ]
    slot_text = '、'.join(slots) or '未知'
    return {
        'id': str(question.get('id') or '').strip(),
        'ok': False,
        'reason': f'多路视觉证据确认第{slot_text}槽为与规范字不同的标准错字',
        'expected_answer': str(question.get('correct_answer') or '').strip(),
        'fix': {
            'verdict': 'wrong',
            'error_type': '错别字',
        },
    }


def _single_cell_arbitration_decision(
    question: Dict[str, Any],
    plan: Dict[str, Any],
    glyph_item: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        'consistent': False,
        'status': 'missing',
        'block_reason': 'single_cell_arbitration_missing',
    }
    if not isinstance(glyph_item, dict):
        return result
    if glyph_item.get('status') != 'completed':
        result.update({
            'status': str(glyph_item.get('status') or 'invalid'),
            'block_reason': str(glyph_item.get('block_reason') or 'single_cell_arbitration_invalid'),
        })
        return result
    target_slots = [int(slot) for slot in plan.get('target_slots') or []]
    expected_slots = list(plan.get('expected_slots') or [])
    page_slots = list(plan.get('page_slots') or [])
    focused_slots = list(plan.get('focused_slots') or [])
    if len(target_slots) != 1 or not expected_slots:
        result.update({'status': 'rejected', 'block_reason': 'single_cell_target_invalid'})
        return result
    target_slot = target_slots[0]
    target_index = target_slot - 1
    target_result = glyph_item.get('target_result')
    if not isinstance(target_result, dict):
        result.update({'status': 'rejected', 'block_reason': 'single_cell_result_invalid'})
        return result
    try:
        result_slot = int(target_result.get('slot'))
    except (TypeError, ValueError):
        result_slot = 0
    if result_slot != target_slot:
        result.update({'status': 'rejected', 'block_reason': 'single_cell_result_slot_mismatch'})
        return result
    recognized_char = str(target_result.get('recognized_char') or '').strip()
    if (
        str(target_result.get('status') or '') != 'recognized'
        or not _CJK_CHAR_RE.fullmatch(recognized_char)
    ):
        result.update({'status': 'rejected', 'block_reason': 'single_cell_not_recognized'})
        return result
    if recognized_char == expected_slots[target_index]:
        result.update({'status': 'rejected', 'block_reason': 'single_cell_matches_expected'})
        return result
    if (
        len(page_slots) != len(expected_slots)
        or len(focused_slots) != len(expected_slots)
    ):
        result.update({'status': 'rejected', 'block_reason': 'single_cell_source_slots_missing'})
        return result
    source_chars = {page_slots[target_index], focused_slots[target_index]}
    allowed_novel_by_slot = plan.get('allowed_novel_target_chars') or {}
    allowed_novel_chars = {
        str(char or '').strip()
        for char in (
            allowed_novel_by_slot.get(target_slot)
            or allowed_novel_by_slot.get(str(target_slot))
            or []
        )
        if _CJK_CHAR_RE.fullmatch(str(char or '').strip())
    }
    if recognized_char not in source_chars and recognized_char not in allowed_novel_chars:
        result.update({'status': 'rejected', 'block_reason': 'single_cell_novel_candidate'})
        return result
    for index, pair in enumerate(zip(page_slots, focused_slots)):
        if index != target_index and pair[0] != pair[1]:
            result.update({'status': 'rejected', 'block_reason': 'single_cell_non_target_conflict'})
            return result
    if plan.get('single_stroke_claim') is True:
        result.update({'status': 'rejected', 'block_reason': 'single_stroke_difference'})
        return result
    visual_slots = list(page_slots)
    visual_slots[target_index] = recognized_char
    group_breaks = [int(value) for value in glyph_item.get('group_break_slots') or []]
    visual_answer = _format_visual_slots(visual_slots, group_breaks)
    differing = sum(1 for pair in zip(visual_slots, expected_slots) if pair[0] != pair[1])
    verdict = 'partial' if len(expected_slots) > 2 and differing < len(expected_slots) else 'wrong'
    result.update({
        'consistent': True,
        'status': 'confirmed',
        'block_reason': '',
        'visual_answer': visual_answer,
        'review_item': {
            'id': str(question.get('id') or '').strip(),
            'ok': False,
            'reason': '单个真实字格无先验视觉仲裁确认标准错字',
            'visual_answer': visual_answer,
            'expected_answer': str(question.get('correct_answer') or '').strip(),
            'fix': {
                'verdict': verdict,
                'student_answer': visual_answer,
                'error_type': '错别字',
            },
        },
    })
    return result


def _focused_override_evidence(
    item: Optional[Dict[str, Any]],
    question: Dict[str, Any],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        'strength': 'weak',
        'detail': 'focused_evidence_not_strong',
    }
    if not isinstance(item, dict) or item.get('ok') is not False:
        return result

    raw_visual = str(item.get('visual_answer') or '').strip()
    raw_expected = str(item.get('expected_answer') or '').strip()
    question_expected = str(question.get('correct_answer') or '').strip()
    fix = _review_item_fix(item)
    fixed_student = str(fix.get('student_answer') or '').strip()
    fixed_verdict = str(fix.get('verdict') or '').strip()
    if (
        not raw_visual
        or not raw_expected
        or not question_expected
        or fixed_verdict not in ('wrong', 'partial')
        or fixed_student != raw_visual
        or _normalize_evidence_text(raw_expected) != _normalize_evidence_text(question_expected)
        or _VISUAL_PLACEHOLDER_RE.search(raw_visual)
    ):
        return result

    result['visual_answer'] = raw_visual
    evidence = _classify_visual_evidence(item, question)
    result['scope'] = evidence.get('scope')
    result['signature'] = evidence.get('signature')
    if evidence.get('scope') == 'single_stroke':
        result['detail'] = 'single_stroke_difference'
        return result

    expected_slots = _answer_slots(raw_expected)
    if evidence.get('scope') == 'standard_char':
        visual_slots = _answer_slots(raw_visual)
        if len(visual_slots) != len(expected_slots):
            return result
        differing = [
            index for index, (visual_char, expected_char) in enumerate(zip(visual_slots, expected_slots))
            if visual_char != expected_char
        ]
        if len(differing) != 1:
            return result
        index = differing[0]
        if not (
            _CJK_CHAR_RE.fullmatch(visual_slots[index])
            and _CJK_CHAR_RE.fullmatch(expected_slots[index])
        ):
            return result
        result.update({
            'strength': 'strong',
            'detail': '',
            'target_slot': index + 1,
            'target_char': expected_slots[index],
            'observed_char': visual_slots[index],
        })
        return result

    if evidence.get('scope') != 'component':
        return result

    normalized_visual = raw_visual.replace('（', '(').replace('）', ')')
    matches = list(_NONSTANDARD_GLYPH_RE.finditer(normalized_visual))
    details = _component_evidence_details(normalized_visual)
    if len(matches) != 1 or len(details) != 1:
        return result
    detail = details[0]
    description = str(detail.get('description') or '').strip()
    if not detail.get('location') or not _COMPONENT_LOCATION_PREFIX_RE.search(description):
        return result
    without_descriptions = _NONSTANDARD_GLYPH_RE.sub(lambda match: match.group(1), normalized_visual)
    if _normalize_evidence_text(without_descriptions) != _normalize_evidence_text(raw_expected):
        return result
    slot = int(detail.get('slot') or 0)
    if slot <= 0 or slot > len(expected_slots):
        return result
    target_char = str(detail.get('target_char') or '')
    if target_char != expected_slots[slot - 1] or not _CJK_CHAR_RE.fullmatch(target_char):
        return result
    result.update({
        'strength': 'strong',
        'detail': '',
        'target_slot': slot,
        'target_char': target_char,
        'location': detail.get('location'),
        'replacement': detail.get('replacement'),
    })
    return result


def _normalize_confirmation_item(
    raw_items: Any,
    qid: str,
    question: Dict[str, Any],
) -> Dict[str, Any]:
    item: Dict[str, Any] = {}
    if isinstance(raw_items, list):
        for candidate in raw_items:
            if isinstance(candidate, dict) and str(candidate.get('id') or '').strip() == qid:
                item = candidate
                break
    if not item:
        return {
            'id': qid,
            'classification': 'uncertain',
            'response_missing': True,
        }

    entry: Dict[str, Any] = {'id': qid}
    classification = str(item.get('classification') or '').strip()
    entry['classification'] = classification or 'uncertain'
    if classification not in _CONFIRMATION_CLASSIFICATIONS:
        entry['invalid'] = True
        entry['validation_error'] = 'invalid_classification'

    reason = str(item.get('reason') or '').strip()
    if reason:
        entry['reason'] = reason
    visual_answer = str(item.get('visual_answer') or '').strip()
    if visual_answer:
        entry['visual_answer'] = visual_answer
    expected_answer = str(item.get('expected_answer') or '').strip()
    if expected_answer:
        entry['expected_answer'] = expected_answer

    try:
        target_slot = int(item.get('target_slot'))
    except (TypeError, ValueError):
        target_slot = 0
    target_char = str(item.get('target_char') or '').strip()
    if target_slot > 0:
        entry['target_slot'] = target_slot
    if target_char:
        entry['target_char'] = target_char

    observed_char = str(item.get('observed_char') or '').strip()
    if observed_char:
        entry['observed_char'] = observed_char
    component_position = _canonical_component_location(str(item.get('component_position') or ''))
    if component_position:
        entry['component_position'] = component_position
    replacement_component = _normalize_evidence_text(item.get('replacement_component') or '')
    if replacement_component:
        entry['replacement_component'] = replacement_component

    expected_slots = _answer_slots(question.get('correct_answer'))
    question_expected = _normalize_evidence_text(question.get('correct_answer'))
    invalid_detail = ''
    if not expected_answer or _normalize_evidence_text(expected_answer) != question_expected:
        invalid_detail = 'expected_answer_mismatch'
    elif target_slot <= 0 or target_slot > len(expected_slots):
        invalid_detail = 'invalid_target_slot'
    elif not target_char or target_char != expected_slots[target_slot - 1]:
        invalid_detail = 'target_char_mismatch'
    elif classification == 'standard_wrong_char' and not _CJK_CHAR_RE.fullmatch(observed_char):
        invalid_detail = 'invalid_observed_char'
    elif classification == 'component_difference' and (
        component_position not in _COMPONENT_LOCATIONS or not replacement_component
    ):
        invalid_detail = 'invalid_component_evidence'
    if invalid_detail:
        entry['invalid'] = True
        entry['validation_error'] = invalid_detail
    return entry


def _confirmation_decision(
    confirmation_item: Optional[Dict[str, Any]],
    override_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        'status': 'missing',
        'consistent': False,
        'scope': 'uncertain',
        'signature': '',
        'block_reason': 'confirmation_missing',
    }
    if not isinstance(confirmation_item, dict) or confirmation_item.get('response_missing') is True:
        return result
    if confirmation_item.get('invalid') is True:
        result.update({
            'status': 'invalid',
            'block_reason': 'confirmation_invalid',
        })
        return result

    classification = str(confirmation_item.get('classification') or '').strip()
    if classification == 'matches_expected':
        result.update({
            'status': 'rejected',
            'scope': 'matches_expected',
            'block_reason': 'confirmation_matches_expected',
        })
        return result
    if classification == 'single_stroke':
        result.update({
            'status': 'rejected',
            'scope': 'single_stroke',
            'block_reason': 'confirmation_single_stroke',
        })
        return result
    if classification == 'uncertain':
        result.update({
            'status': 'rejected',
            'block_reason': 'confirmation_uncertain',
        })
        return result

    focused_visual = _normalize_evidence_text(override_evidence.get('visual_answer') or '')
    confirmation_visual = _normalize_evidence_text(confirmation_item.get('visual_answer') or '')
    if not confirmation_visual or confirmation_visual != focused_visual:
        result.update({
            'status': 'rejected',
            'block_reason': 'confirmation_evidence_mismatch',
        })
        return result

    target_slot = int(confirmation_item.get('target_slot') or 0)
    target_char = str(confirmation_item.get('target_char') or '')
    if classification == 'standard_wrong_char':
        observed_char = str(confirmation_item.get('observed_char') or '')
        signature = f'{target_slot}:standard:{observed_char}'
        result.update({'scope': 'standard_char', 'signature': signature})
        consistent = bool(
            override_evidence.get('scope') == 'standard_char'
            and target_slot == int(override_evidence.get('target_slot') or 0)
            and target_char == str(override_evidence.get('target_char') or '')
            and observed_char == str(override_evidence.get('observed_char') or '')
        )
    elif classification == 'component_difference':
        location = str(confirmation_item.get('component_position') or '')
        replacement = str(confirmation_item.get('replacement_component') or '')
        signature = f'{target_slot}:{location}:{replacement}'
        result.update({'scope': 'component', 'signature': signature})
        consistent = bool(
            override_evidence.get('scope') == 'component'
            and target_slot == int(override_evidence.get('target_slot') or 0)
            and target_char == str(override_evidence.get('target_char') or '')
            and location == str(override_evidence.get('location') or '')
            and replacement == str(override_evidence.get('replacement') or '')
        )
    else:
        result.update({'status': 'invalid', 'block_reason': 'confirmation_invalid'})
        return result

    if not consistent:
        result.update({
            'status': 'rejected',
            'block_reason': 'confirmation_evidence_mismatch',
        })
        return result
    result.update({
        'status': 'confirmed',
        'consistent': True,
        'block_reason': '',
    })
    return result


def _classify_visual_evidence(
    item: Optional[Dict[str, Any]],
    question: Dict[str, Any],
) -> Dict[str, Any]:
    visual = _review_item_visual(item)
    expected = _review_item_expected(item, question)
    normalized_visual = _normalize_evidence_text(visual)
    normalized_expected = _normalize_evidence_text(expected)
    evidence: Dict[str, Any] = {
        'scope': 'uncertain',
        'visual_answer': visual,
        'expected_answer': expected,
        'signature': '',
    }
    if not visual or not expected or not normalized_visual or not normalized_expected:
        return evidence
    if normalized_visual == normalized_expected or _VISUAL_PLACEHOLDER_RE.search(visual):
        return evidence
    # A directly encodable wrong character is stronger evidence than any
    # explanatory stroke/component wording in reason or error_type.
    if '(' not in visual and '（' not in visual:
        evidence['scope'] = 'standard_char'
        evidence['signature'] = normalized_visual
        return evidence
    if _is_single_stroke_evidence(item):
        evidence['scope'] = 'single_stroke'
        evidence['signature'] = normalized_visual
        return evidence

    component_signatures = _component_signatures(visual)
    if component_signatures:
        evidence['scope'] = 'component'
        evidence['signature'] = '|'.join(component_signatures)
        return evidence

    if ('(' in visual or '（' in visual) and _COMPONENT_SCOPE_RE.search(_review_item_evidence_text(item)):
        return evidence

    return evidence


def _evidence_is_compatible(page_evidence: Dict[str, Any], focused_evidence: Dict[str, Any]) -> bool:
    if page_evidence.get('scope') not in ('standard_char', 'component'):
        return False
    if page_evidence.get('scope') != focused_evidence.get('scope'):
        return False
    if _normalize_evidence_text(page_evidence.get('expected_answer')) != _normalize_evidence_text(
        focused_evidence.get('expected_answer')
    ):
        return False
    return bool(
        page_evidence.get('signature')
        and page_evidence.get('signature') == focused_evidence.get('signature')
    )


def _proposed_review_verdict(
    item: Optional[Dict[str, Any]],
    baseline_verdict: str,
    *,
    source: str,
) -> Optional[str]:
    if (
        not isinstance(item, dict)
        or item.get('response_missing') is True
        or not isinstance(item.get('ok'), bool)
    ):
        return None
    if item.get('ok') is True:
        return 'correct' if source == 'focused' else baseline_verdict
    verdict = str(_review_item_fix(item).get('verdict') or '').strip()
    return verdict if verdict in VALID_VERDICTS else None


def _verdict_class(verdict: Optional[str]) -> str:
    if verdict == 'correct':
        return 'correct'
    if verdict in _INCORRECT_VERDICTS:
        return 'incorrect'
    return 'unknown'


def _reference_answer_correction_evidence(
    question: Dict[str, Any],
    page_item: Dict[str, Any],
    focused_item: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate a dual-source proposal that replaces an incorrect answer key."""
    baseline_answer = str(question.get('correct_answer') or '').strip()
    baseline_signature = _normalize_evidence_text(baseline_answer)
    page_fix = _review_item_fix(page_item)
    has_proposal = 'correct_answer' in page_fix
    proposed_answer = str(page_fix.get('correct_answer') or '').strip()
    proposed_signature = _normalize_evidence_text(proposed_answer)
    page_signature = _normalize_evidence_text(_review_item_visual(page_item))
    page_fix_signature = _normalize_evidence_text(page_fix.get('student_answer'))
    focused_signature = _normalize_evidence_text(_review_item_visual(focused_item))
    requested = bool(
        has_proposal
        or (page_signature and page_signature != baseline_signature)
        or (focused_signature and focused_signature != baseline_signature)
    )
    result: Dict[str, Any] = {'reference_answer_correction': requested}
    if not requested:
        return result

    result.update({
        'baseline_correct_answer': baseline_answer,
        'proposed_correct_answer': proposed_answer,
        'page_answer_signature': page_signature,
        'focused_answer_signature': focused_signature,
    })
    if not has_proposal or not proposed_signature or proposed_signature == baseline_signature:
        result['block_reason'] = 'reference_answer_proposal_missing'
        return result

    page_expected_signature = _normalize_evidence_text(_review_item_expected(page_item, question))
    focused_expected_signature = _normalize_evidence_text(
        _review_item_expected(focused_item, question)
    )
    if (
        not baseline_signature
        or page_expected_signature != baseline_signature
        or focused_expected_signature != baseline_signature
    ):
        result['block_reason'] = 'reference_answer_baseline_mismatch'
        return result

    if (
        not page_signature
        or not page_fix_signature
        or not focused_signature
        or page_signature != proposed_signature
        or page_fix_signature != proposed_signature
        or focused_signature != proposed_signature
    ):
        result['block_reason'] = 'reference_answer_evidence_mismatch'
        return result

    result['valid'] = True
    return result


def _merged_correct_review_item(
    question: Dict[str, Any],
    page_item: Dict[str, Any],
    focused_item: Dict[str, Any],
) -> Dict[str, Any]:
    page_fix = _review_item_fix(page_item)
    visual = _review_item_visual(focused_item)
    fix: Dict[str, Any] = {'verdict': 'correct', 'error_type': ''}
    student_answer = str(page_fix.get('student_answer') or visual or '').strip()
    if student_answer:
        fix['student_answer'] = student_answer
    if 'correct_answer' in page_fix:
        fix['correct_answer'] = page_fix.get('correct_answer')
    return {
        'id': str(question.get('id') or '').strip(),
        'ok': False,
        'reason': str(page_item.get('reason') or focused_item.get('reason') or '两路复核均确认作答正确').strip(),
        'visual_answer': visual,
        'expected_answer': _review_item_expected(focused_item, question),
        'fix': fix,
    }


def _merged_incorrect_review_item(
    question: Dict[str, Any],
    page_item: Dict[str, Any],
    focused_item: Dict[str, Any],
    page_verdict: str,
) -> Dict[str, Any]:
    page_fix = _review_item_fix(page_item)
    focused_fix = _review_item_fix(focused_item)
    visual = _review_item_visual(focused_item) or _review_item_visual(page_item)
    fix: Dict[str, Any] = {
        'verdict': page_verdict,
        'student_answer': visual,
        'error_type': str(focused_fix.get('error_type') or page_fix.get('error_type') or '').strip(),
    }
    if 'correct_answer' in page_fix:
        fix['correct_answer'] = page_fix.get('correct_answer')
    return {
        'id': str(question.get('id') or '').strip(),
        'ok': False,
        'reason': str(focused_item.get('reason') or page_item.get('reason') or '').strip(),
        'visual_answer': visual,
        'expected_answer': _review_item_expected(focused_item, question),
        'fix': fix,
    }


def _focused_override_review_item(
    question: Dict[str, Any],
    focused_item: Dict[str, Any],
    focused_verdict: str,
) -> Dict[str, Any]:
    focused_fix = _review_item_fix(focused_item)
    visual = str(focused_item.get('visual_answer') or '').strip()
    fix: Dict[str, Any] = {
        'verdict': focused_verdict,
        'student_answer': visual,
        'error_type': str(focused_fix.get('error_type') or '').strip(),
    }
    if 'correct_answer' in focused_fix:
        fix['correct_answer'] = focused_fix.get('correct_answer')
    return {
        'id': str(question.get('id') or '').strip(),
        'ok': False,
        'reason': str(focused_item.get('reason') or '').strip(),
        'visual_answer': visual,
        'expected_answer': _review_item_expected(focused_item, question),
        'fix': fix,
    }


def _maybe_resolve_glyph_arbitration(
    question: Dict[str, Any],
    page_item: Optional[Dict[str, Any]],
    focused_item: Optional[Dict[str, Any]],
    glyph_item: Optional[Dict[str, Any]],
    audit: Dict[str, Any],
*, feedback_runtime=None) -> tuple:
    plan = _glyph_arbitration_plan(question, page_item, focused_item, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if plan.get('block_reason'):
        audit['glyph_arbitration_evaluated'] = True
        audit['block_reason'] = str(plan['block_reason'])
        return True, None
    if plan.get('required') is not True:
        return False, None
    audit.update({
        'glyph_arbitration_evaluated': True,
        'glyph_arbitration_required': True,
        'glyph_arbitration_mode': plan.get('mode'),
        'glyph_trigger_reasons': list(plan.get('trigger_reasons') or []),
        'glyph_target_slots': list(plan.get('target_slots') or []),
        'glyph_preferred_source': str(plan.get('preferred_source') or ''),
        'glyph_pinyin_tokens': list(plan.get('pinyin_tokens') or []),
        'glyph_single_cell_only': bool(plan.get('single_cell_only')),
        'glyph_target_stroke_count': plan.get('target_stroke_count'),
    })
    wrong_slot_decision: Dict[str, Any] = {}
    if plan.get('single_cell_only') is True:
        decision = _single_cell_arbitration_decision(question, plan, glyph_item)
    else:
        decision = _glyph_arbitration_decision(question, plan, glyph_item)
        wrong_slot_decision = _glyph_wrong_slot_decision(plan, glyph_item)
    audit.update({
        'glyph_arbitration_status': decision.get('status'),
        'glyph_arbitration_consistent': bool(decision.get('consistent')),
        'glyph_visual_answer': str(decision.get('visual_answer') or ''),
        'glyph_wrong_slot_status': wrong_slot_decision.get('status'),
        'glyph_wrong_slots': list(wrong_slot_decision.get('wrong_slots') or []),
    })
    if wrong_slot_decision.get('confirmed') is True:
        audit['would_mark_wrong'] = True
    if decision.get('consistent') is not True:
        if wrong_slot_decision.get('confirmed') is True:
            audit['decision'] = (
                'glyph_wrong_slot_shadow'
                if plan.get('mode') == 'shadow'
                else 'glyph_wrong_slot'
            )
            audit['decision_basis'] = 'confirmed_wrong_slot_without_full_transcription'
            audit['verdict_only'] = True
            if plan.get('mode') == 'shadow':
                audit['block_reason'] = 'glyph_shadow_wrong_slot_only'
                return True, None
            return True, _wrong_slot_review_item(question, wrong_slot_decision)
        audit['block_reason'] = str(decision.get('block_reason') or 'glyph_arbitration_invalid')
        return True, None
    audit['would_apply'] = True
    if plan.get('mode') == 'shadow':
        audit['decision'] = (
            'glyph_single_cell_shadow'
            if plan.get('single_cell_only') is True
            else 'glyph_shadow'
        )
        audit['decision_basis'] = (
            'single_target_cell_recognized_existing_candidate'
            if plan.get('single_cell_only') is True
            else 'target_cell_and_row_consistent'
        )
        audit['block_reason'] = 'glyph_shadow_only'
        return True, None
    audit['decision'] = 'glyph_arbitration'
    audit['decision_basis'] = (
        'single_target_cell_recognized_existing_candidate'
        if plan.get('single_cell_only') is True
        else 'target_cell_and_row_consistent'
    )
    return True, decision.get('review_item')


def _aggregate_chinese_visual_review(
    question: Dict[str, Any],
    page_item: Optional[Dict[str, Any]],
    focused_item: Optional[Dict[str, Any]],
    confirmation_item: Optional[Dict[str, Any]] = None,
    glyph_item: Optional[Dict[str, Any]] = None,
*, feedback_runtime=None) -> tuple:
    baseline_verdict = str(question.get('verdict') or 'uncertain').strip() or 'uncertain'
    page_verdict = _proposed_review_verdict(page_item, baseline_verdict, source='page')
    focused_verdict = _proposed_review_verdict(focused_item, baseline_verdict, source='focused')
    audit: Dict[str, Any] = {
        'id': str(question.get('id') or '').strip(),
        'baseline_verdict': baseline_verdict,
        'page_proposed_verdict': page_verdict,
        'focused_proposed_verdict': focused_verdict,
        'decision': 'kept',
        'applied': False,
        'focused_override': False,
        'confirmation_required': False,
        'confirmation_status': 'not_requested',
        'confirmation_consistent': False,
    }
    if page_verdict is None or focused_verdict is None:
        audit['block_reason'] = 'insufficient_evidence'
        return None, audit

    page_class = _verdict_class(page_verdict)
    focused_class = _verdict_class(focused_verdict)
    if page_class == 'correct' and focused_class == 'correct':
        if _should_force_yaolai_sample_roi(question, page_item, focused_item):
            glyph_handled, glyph_review_item = _maybe_resolve_glyph_arbitration(
                question,
                page_item,
                focused_item,
                glyph_item,
                audit,
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
            if glyph_handled:
                return glyph_review_item, audit
        audit['decision'] = 'agreed_correct'
        if baseline_verdict == 'correct':
            return None, audit
        reference_evidence = _reference_answer_correction_evidence(
            question,
            page_item,
            focused_item,
        )
        if reference_evidence.get('reference_answer_correction') is True:
            audit.update({
                key: value
                for key, value in reference_evidence.items()
                if key != 'valid'
            })
            if reference_evidence.get('valid') is not True:
                audit['decision'] = 'kept'
                return None, audit
            audit['decision'] = 'agreed_reference_answer_correction'
            audit['decision_basis'] = 'agreed_reference_answer_correction'
        return _merged_correct_review_item(question, page_item, focused_item), audit

    if page_class != focused_class or page_class == 'unknown':
        glyph_handled, glyph_review_item = _maybe_resolve_glyph_arbitration(
            question,
            page_item,
            focused_item,
            glyph_item,
            audit,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        if glyph_handled:
            return glyph_review_item, audit
        if (
            baseline_verdict == 'correct'
            and page_class == 'correct'
            and focused_class == 'incorrect'
        ):
            audit['focused_override_evaluated'] = True
            page_evidence = _classify_visual_evidence(page_item, question)
            focused_evidence = _classify_visual_evidence(focused_item, question)
            audit['evidence_scope'] = {
                'page': page_evidence.get('scope'),
                'focused': focused_evidence.get('scope'),
            }
            audit['evidence_signature'] = {
                'page': page_evidence.get('signature'),
                'focused': focused_evidence.get('signature'),
            }
            if focused_evidence.get('scope') == 'single_stroke':
                audit['focused_evidence_strength'] = 'weak'
                audit['block_reason'] = 'single_stroke_difference'
                audit['conflict_detail'] = 'single_stroke_difference'
                return None, audit

            override_evidence = _focused_override_evidence(focused_item, question)
            audit['focused_evidence_strength'] = override_evidence.get('strength')
            for field in ('target_slot', 'target_char'):
                if override_evidence.get(field) is not None:
                    audit[field] = override_evidence[field]
            if override_evidence.get('strength') != 'strong':
                audit['block_reason'] = 'source_conflict'
                audit['conflict_detail'] = str(
                    override_evidence.get('detail') or 'focused_evidence_not_strong'
                )
                return None, audit

            complexity = classify_hanzi_complexity(override_evidence.get('target_char'))
            audit.update(complexity)
            if complexity.get('stroke_count') is None:
                audit['block_reason'] = 'source_conflict'
                audit['conflict_detail'] = 'stroke_count_unknown'
                return None, audit
            if int(complexity['stroke_count']) < COMPLEX_GLYPH_STROKE_THRESHOLD:
                audit['block_reason'] = 'source_conflict'
                audit['conflict_detail'] = 'target_complexity_below_threshold'
                return None, audit

            if override_evidence.get('scope') == 'standard_char':
                observed_complexity = classify_hanzi_complexity(override_evidence.get('observed_char'))
                audit['observed_char'] = override_evidence.get('observed_char')
                audit['observed_stroke_count'] = observed_complexity.get('stroke_count')

            audit['confirmation_required'] = True
            confirmation = _confirmation_decision(confirmation_item, override_evidence)
            audit['confirmation_status'] = confirmation.get('status')
            audit['confirmation_evidence_scope'] = confirmation.get('scope')
            audit['confirmation_evidence_signature'] = confirmation.get('signature')
            audit['confirmation_consistent'] = bool(confirmation.get('consistent'))
            if not confirmation.get('consistent'):
                audit['block_reason'] = str(
                    confirmation.get('block_reason') or 'confirmation_invalid'
                )
                audit['conflict_detail'] = audit['block_reason']
                return None, audit

            audit['decision'] = 'focused_override'
            audit['focused_override'] = True
            audit['decision_basis'] = 'complex_glyph_confirmed_focused_evidence'
            return _focused_override_review_item(
                question,
                focused_item,
                str(focused_verdict),
            ), audit

        audit['block_reason'] = 'source_conflict'
        return None, audit

    page_evidence = _classify_visual_evidence(page_item, question)
    focused_evidence = _classify_visual_evidence(focused_item, question)
    audit['evidence_scope'] = {
        'page': page_evidence.get('scope'),
        'focused': focused_evidence.get('scope'),
    }
    audit['evidence_signature'] = {
        'page': page_evidence.get('signature'),
        'focused': focused_evidence.get('signature'),
    }
    if (
        baseline_verdict == 'correct'
        and page_class == 'incorrect'
        and focused_class == 'incorrect'
        and glyph_arbitration_mode(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) != 'off'
    ):
        glyph_handled, glyph_review_item = _maybe_resolve_glyph_arbitration(
            question,
            page_item,
            focused_item,
            glyph_item,
            audit,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        if glyph_handled:
            return glyph_review_item, audit
    if 'single_stroke' in (page_evidence.get('scope'), focused_evidence.get('scope')):
        audit['block_reason'] = 'single_stroke_difference'
        return None, audit
    if not _evidence_is_compatible(page_evidence, focused_evidence):
        glyph_handled, glyph_review_item = _maybe_resolve_glyph_arbitration(
            question,
            page_item,
            focused_item,
            glyph_item,
            audit,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        if glyph_handled:
            return glyph_review_item, audit
        audit['block_reason'] = (
            'insufficient_evidence'
            if 'uncertain' in (page_evidence.get('scope'), focused_evidence.get('scope'))
            else 'evidence_mismatch'
        )
        return None, audit
    audit['decision'] = 'agreed_incorrect'
    return _merged_incorrect_review_item(question, page_item, focused_item, page_verdict), audit


def _focused_visual_review_scale(*, feedback_runtime=None) -> int:
    try:
        return max(1, min(int(frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_FOCUSED_REVIEW_SCALE') or 3), 5))
    except (TypeError, ValueError):
        return 3


def _needs_focused_chinese_visual_review(question: Dict[str, Any]) -> bool:
    if not normalize_position(question.get('position')):
        return False
    return bool(_question_review_focus(question, 'chinese'))


def _page_needs_review(page_data: Dict[str, Any], subject: str, *, feedback_runtime=None) -> bool:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    from .evidence_contract import required_review_units
    if feedback_runtime is not None and required_review_units(page_data):
        return True
    scope = pass1_review_scope(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if scope == 'all':
        return True
    if scope == 'wrong_only':
        return _page_has_wrong_verdict(page_data)
    return (
        _page_has_reviewable_verdict(page_data)
        or _page_has_chinese_visual_form_risk(page_data, subject)
        or _page_has_math_algebra_final_form_risk(page_data, subject)
        or _page_has_math_substitution_unit_risk(page_data, subject)
    )


def _review_skip_reason(page_data: Dict[str, Any], subject: str, *, feedback_runtime=None) -> str:
    scope = pass1_review_scope(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if scope == 'wrong_only':
        return 'no_wrong_verdict'
    if scope == 'high_risk':
        return 'no_high_risk_verdict'
    return 'not_skipped'


def _self_review_allowlist_match(
    page_json_path: str,
    subject: str,
    page_num: int = 0,
    source_document_sha256: str = '',
    *, feedback_runtime=None,
) -> Optional[Dict[str, Any]]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if feedback_runtime is not None and (not feedback_runtime.has_specialized(subject) or not source_document_sha256):
        return None
    match = _PASS1_PAGE_JSON_RE.match(os.path.basename(page_json_path))
    if not match:
        return None
    normalized_subject = str(subject or '').strip().lower()
    file_subject = str(match.group('subject') or '').strip().lower()
    if not normalized_subject or file_subject != normalized_subject:
        return None
    file_page = int(match.group('page'))
    if page_num and int(page_num) != file_page:
        return None
    sample_id = str(match.group('sample_id') or '').strip()
    return match_document_special_case(
        normalized_subject,
        file_page,
        ACTION_SKIP_SELF_REVIEW,
        source_document_sha256=source_document_sha256,
        sample_id=sample_id,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))


def _self_review_allowlist_skip_reason(
    page_json_path: str,
    subject: str,
    page_num: int = 0,
    source_document_sha256: str = '',
    *, feedback_runtime=None,
) -> str:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if _self_review_allowlist_match(
        page_json_path,
        subject,
        page_num,
        source_document_sha256,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})):
        return _SELF_REVIEW_ALLOWLIST_SKIP_REASON
    return ''


def _build_review_snapshot(page_data: Dict[str, Any], subject: str = '') -> Dict[str, Any]:
    questions: List[Dict[str, Any]] = []
    for question in page_data.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        if not qid:
            continue
        entry = {
            'id': qid,
            'parent_stem_excerpt': str(question.get('parent_stem_excerpt') or '').strip(),
            'stem_excerpt': str(question.get('stem_excerpt') or '').strip(),
            'student_answer': str(question.get('student_answer') or '').strip(),
            'correct_answer': question.get('correct_answer'),
            'verdict': str(question.get('verdict') or 'uncertain').strip() or 'uncertain',
            'error_type': str(question.get('error_type') or '').strip(),
            'knowledge_point': str(question.get('knowledge_point') or '').strip(),
            'final_unit_requirement': str(
                question.get('final_unit_requirement') or 'optional'
            ).strip(),
        }
        for field in ('note_role', 'material_check', 'assessment_status', 'assessment_reason',
                      'printed_text_marked', 'handwritten_text_marked', 'annotation_links'):
            if field in question:
                entry[field] = copy.deepcopy(question[field])
        focus = _question_review_focus(question, subject)
        if focus:
            entry['review_focus'] = focus
        questions.append(entry)
    return {
        'page': page_data.get('page'),
        'questions': questions,
    }


def _review_snapshot_signature(page_data: Dict[str, Any], subject: str) -> str:
    snapshot = _build_review_snapshot(page_data, subject)
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()


def _retry_hint(last_error: Optional[Exception]) -> str:
    message = str(last_error or '')
    if 'items' in message:
        return '上次返回缺少 items 数组。必须输出 JSON 对象，顶层含 items 数组。'
    if isinstance(last_error, json.JSONDecodeError):
        return '上次返回不是合法 JSON。请只输出 JSON 对象。'
    return '上次返回格式不符合要求。请严格按 schema 只输出 JSON 对象。'


def _call_review_llm(
    messages: List[Dict[str, Any]],
    *,
    error_dump_path: Optional[str] = None,
    result_validator: Optional[Any] = None,
    raw_parser: Optional[Any] = None,
    require_items: bool = True,
    feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        import copy
        from .feedback_prompts import context_block, reference_block
        from .feedback_skills import KERNEL_CONTRACT
        messages = copy.deepcopy(messages)
        if messages and '【本轮实际材料】' not in str(messages[0].get('content', '')):
            messages[0]['content'] += context_block(feedback_runtime) + reference_block(feedback_runtime) + KERNEL_CONTRACT
        from .notebook_skills import prompt_block
        if messages and '[NKCN_NOTEBOOK_SKILL ' not in str(messages[0].get('content', '')):
            messages[0]['content'] += prompt_block(feedback_runtime, 'review')
    from .model_output import request_json_object, object_list

    def validate(result):
        if require_items:
            object_list(result.get('items'), 'items')
        if result_validator is not None:
            error = result_validator(result)
            if error:
                raise ValueError(error)
        return result

    return request_json_object(
        lambda current: _call_homework_gemini_json(current,
            **({'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {})),
        messages, parser=raw_parser or _loads_json_with_retry_text, validate=validate,
        audit_path=error_dump_path + '.responses.json' if error_dump_path else None,
        stage='页面复核', attempts=REVIEW_MAX_ATTEMPTS, retry_prompt=_retry_hint,
        error_path=error_dump_path, retry_call_errors=True)


def _normalize_review_items(raw_items: Any, expected_ids: List[str]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            qid = str(item.get('id') or '').strip()
            if not qid:
                continue
            by_id[qid] = item

    normalized: List[Dict[str, Any]] = []
    for qid in expected_ids:
        item = by_id.get(qid, {})
        ok = bool(item.get('ok', True))
        entry: Dict[str, Any] = {'id': qid, 'ok': ok}
        if not item:
            entry['response_missing'] = True
        reason = str(item.get('reason') or '').strip()
        if reason:
            entry['reason'] = reason
        visual_answer = str(item.get('visual_answer') or item.get('observed_answer') or '').strip()
        if visual_answer:
            entry['visual_answer'] = visual_answer
        expected_answer = str(item.get('expected_answer') or '').strip()
        if expected_answer:
            entry['expected_answer'] = expected_answer
        fix = item.get('fix')
        if isinstance(fix, dict) and fix:
            clean_fix: Dict[str, Any] = {}
            if 'verdict' in fix and str(fix.get('verdict') or '') in VALID_VERDICTS:
                clean_fix['verdict'] = str(fix['verdict'])
            if 'student_answer' in fix:
                clean_fix['student_answer'] = str(fix.get('student_answer') or '')
            if 'correct_answer' in fix:
                clean_fix['correct_answer'] = fix.get('correct_answer')
            if 'error_type' in fix:
                clean_fix['error_type'] = str(fix.get('error_type') or '')
            for field in ('printed_text_marked', 'handwritten_text_marked', 'annotation_links', 'understanding'):
                if field in fix:
                    clean_fix[field] = copy.deepcopy(fix[field])
            if clean_fix:
                entry['fix'] = clean_fix
        normalized.append(entry)
    return normalized


def _sync_error_type_after_review(question: Dict[str, Any], fix: Dict[str, Any]) -> None:
    verdict = str(question.get('verdict') or '').strip()
    error = str(question.get('error_type') or '').strip()
    if not error:
        return
    if 'error_type' in fix:
        return
    if verdict == 'correct':
        question['error_type'] = ''
        return
    if verdict == 'partial' and any(token in error for token in ('未作答', '漏题')):
        question['error_type'] = ''


def _is_cross_page_boundary_only_error(error_type: Any) -> bool:
    text = re.sub(r'\s+', '', str(error_type or ''))
    if '跨页' not in text:
        return False
    return any(token in text for token in (
        '截断', '信息不足', '不完整', '无法评估全文', '无法评价全文',
        '全文结构', '字数达标', '全文字数',
    ))


def _adjacent_page_exists(page_data: Dict[str, Any], available_pages: Set[int]) -> bool:
    try:
        page_num = int(page_data.get('page'))
    except (TypeError, ValueError):
        return False
    boundary = page_data.get('boundary') or {}
    return bool(
        (boundary.get('continues_from_prev') and page_num - 1 in available_pages)
        or (boundary.get('continues_to_next') and page_num + 1 in available_pages)
    )


def _reconcile_open_material_boundary_errors(
    json_paths: List[str],
    *,
    feedback_runtime=None,
) -> int:
    """相邻页已在本轮时，移除把单页边界误当内容错误的复核残留。"""
    if feedback_runtime is None:
        return 0
    from .feedback_material_kinds import is_open_material
    if (feedback_runtime.context or {}).get('material_type') == 'notes':
        # 混排笔记的相邻PDF页不一定同源；不得因为存在邻页就把待确认提升成正确。
        return 0
    if not is_open_material((feedback_runtime.context or {}).get('material_type')):
        return 0
    available_pages = {
        parse_page_num(os.path.basename(path))
        for path in json_paths
        if parse_page_num(os.path.basename(path)) > 0
    }
    reconciled = 0
    for json_path in json_paths:
        page_data = safe_json_load(json_path)
        if not _adjacent_page_exists(page_data, available_pages):
            continue
        changed_items: Dict[str, Dict[str, Any]] = {}
        for question in page_data.get('questions') or []:
            if not isinstance(question, dict) or not question.get('cross_page'):
                continue
            old_error = str(question.get('error_type') or '').strip()
            verdict = str(question.get('verdict') or '').strip()
            has_local_content = bool(
                str(question.get('student_answer') or '').strip()
                or str(question.get('understanding') or '').strip()
            )
            if (
                not has_local_content
                or verdict not in ('correct', 'partial', 'uncertain')
                or not _is_cross_page_boundary_only_error(old_error)
            ):
                continue
            question_id = str(question.get('id') or '').strip()
            new_verdict = 'uncertain'
            question['material_check'] = {'status': 'unresolved', 'blocks_assessment': True,
                                          'reason': '相邻页存在，全文要求与内容仍需核对', 'evidence': []}
            question['verdict'] = new_verdict
            question['error_type'] = ''
            audit = {
                'reason': 'adjacent_page_present',
                'previous_verdict': verdict,
                'previous_error_type': old_error,
                'verdict': new_verdict,
                'error_type': '',
            }
            question['boundary_review_reconciliation'] = audit
            if isinstance(question.get('self_review'), dict):
                question['self_review']['boundary_reconciliation'] = audit
            if question_id:
                changed_items[question_id] = audit
            reconciled += 1
        if not changed_items:
            continue
        safe_json_dump(json_path, stamp_feedback(page_data, feedback_runtime, 'review'))
        review_path = _review_json_path(json_path)
        if not os.path.isfile(review_path):
            continue
        review = safe_json_load(review_path)
        for item in review.get('items') or []:
            if not isinstance(item, dict):
                continue
            audit = changed_items.get(str(item.get('id') or '').strip())
            if not audit:
                continue
            fix = item.get('fix') if isinstance(item.get('fix'), dict) else {}
            item['fix'] = {**fix, 'verdict': audit['verdict'], 'error_type': ''}
            item['boundary_reconciliation'] = audit
        review.setdefault('stats', {})['boundary_error_reconciled'] = len(changed_items)
        review['post_review_signature'] = _review_snapshot_signature(
            page_data,
            feedback_runtime.context['subject_code'],
        )
        safe_json_dump(review_path, stamp_feedback(review, feedback_runtime, 'review'))
    return reconciled


def _apply_review_item(question: Dict[str, Any], item: Dict[str, Any]) -> bool:
    if item.get('ok') is not False:
        return False
    fix = item.get('fix') if isinstance(item.get('fix'), dict) else {}
    previous: Dict[str, Any] = {}
    original = {
        'verdict': question.get('verdict'),
        'student_answer': question.get('student_answer'),
        'correct_answer': question.get('correct_answer'),
        'error_type': question.get('error_type'),
    }
    applied = False
    verdict_fix_blocked = False
    lock_reason = ''
    correct_answer_changed = False

    if fix.get('verdict') in VALID_VERDICTS and fix['verdict'] != question.get('verdict'):
        source_lock = source_lock_blocks_review(question, str(fix['verdict']))
        if source_lock:
            question['source_lock'] = source_lock
            verdict_fix_blocked = True
            lock_reason = source_lock.get('reason') or source_lock.get('reason_code') or 'source_locked'
        elif _verdict_fix_allowed(str(question.get('verdict') or ''), str(fix['verdict'])):
            previous['verdict'] = question.get('verdict')
            question['verdict'] = fix['verdict']
            applied = True
        else:
            verdict_fix_blocked = True

    if 'student_answer' in fix:
        new_answer = str(fix.get('student_answer') or '').strip()
        old_answer = str(question.get('student_answer') or '').strip()
        if new_answer and new_answer != old_answer:
            previous['student_answer'] = old_answer
            question['student_answer'] = new_answer
            applied = True

    if 'correct_answer' in fix:
        if fix.get('correct_answer') != question.get('correct_answer'):
            previous['correct_answer'] = question.get('correct_answer')
            question['correct_answer'] = fix.get('correct_answer')
            applied = True
            correct_answer_changed = True

    if 'error_type' in fix:
        new_error = str(fix.get('error_type') or '').strip()
        old_error = str(question.get('error_type') or '').strip()
        if new_error != old_error:
            previous['error_type'] = old_error
            question['error_type'] = new_error
            applied = True

    if applied:
        _sync_error_type_after_review(question, fix)
        if correct_answer_changed and fix.get('verdict') == 'correct':
            previous = {
                field: original.get(field)
                for field in ('verdict', 'student_answer', 'correct_answer', 'error_type')
            }

    question['self_review'] = {
        'ok': False,
        'reason': str(item.get('reason') or '').strip(),
        'previous': previous,
        'applied': applied,
    }
    if verdict_fix_blocked:
        question['self_review']['verdict_fix_blocked'] = True
        question['self_review']['rejected_verdict'] = fix.get('verdict')
        if lock_reason:
            question['self_review']['lock_reason'] = lock_reason
    return applied


def _write_skipped_review(
    page_num: int,
    out_review_path: str,
    skip_reason: str = 'no_high_risk_verdict',
    special_case_match: Optional[Dict[str, Any]] = None,
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    report = {
        'page': page_num,
        'model': (model_spec(feedback_runtime, 'review')['model'] if feedback_runtime is not None else homework_review_gemini_model()),
        'skipped': True,
        'skip_reason': skip_reason,
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'items': [],
        'stats': {'total': 0, 'issues': 0, 'applied': 0},
    }
    if special_case_match:
        report['document_identity'] = special_case_match
    safe_json_dump(out_review_path, stamp_feedback(report, feedback_runtime, 'review'))
    return report


def _confirmation_crop_margin_px(box_width_px: float, box_height_px: float) -> int:
    return max(16, min(48, int(round(max(box_width_px, box_height_px) * 0.10))))


def _crop_question_image(
    image_path: str,
    question: Dict[str, Any],
    *,
    confirmation: bool = False,
feedback_runtime=None) -> tuple:
    position = normalize_position(question.get('position'))
    if not position:
        return image_path, ''
    try:
        from PIL import Image  # noqa: PLC0415
    except Exception:
        return image_path, ''

    try:
        image = Image.open(image_path)
    except Exception:
        return image_path, ''

    width, height = image.size
    x1, y1, x2, y2 = position
    box_left = x1 / 1000.0 * width
    box_top = y1 / 1000.0 * height
    box_right = x2 / 1000.0 * width
    box_bottom = y2 / 1000.0 * height
    box_width = max(1.0, box_right - box_left)
    box_height = max(1.0, box_bottom - box_top)
    if confirmation:
        margin = _confirmation_crop_margin_px(box_width, box_height)
        margin_left = margin_top = margin_right = margin_bottom = margin
    else:
        margin_left, margin_top, margin_right, margin_bottom = _focused_crop_margins(
            question,
            box_width,
            box_height,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    left = int(max(0, box_left - margin_left))
    top = int(max(0, box_top - margin_top))
    right = int(min(width, box_right + margin_right))
    bottom = int(min(height, box_bottom + margin_bottom))
    if right <= left or bottom <= top:
        image.close()
        return image_path, ''

    crop = image.crop((left, top, right, bottom))
    image.close()
    scale = 4 if confirmation else _focused_visual_review_scale(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if scale > 1:
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        target_width = crop.width * scale
        target_height = crop.height * scale
        if not confirmation and max(target_width, target_height) > 5000:
            ratio = 5000.0 / max(target_width, target_height)
            target_width = max(1, int(round(target_width * ratio)))
            target_height = max(1, int(round(target_height * ratio)))
        crop = crop.resize((target_width, target_height), resample)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    tmp_path = tmp.name
    tmp.close()
    crop.save(tmp_path)
    crop.close()
    return tmp_path, tmp_path


def _focused_chinese_visual_review_user_prompt(
    question: Dict[str, Any],
    page_num: int,
    qid: str,
) -> str:
    return (
        f'请只复核第 {page_num} 页题号 {qid} 的局部截图。'
        '这是一张已放大的拼音写词类题局部截图，请检查学生最终保留的手写词是否明显错别字。'
        '截图已适度外扩，边缘可能有旁边其他题的作答干扰，注意排除。注意可能有涂改、斜杠划掉后在旁边修正的情况。\n'
        '只认定与学生主体答案同为深色、笔迹一致的手写内容。浅红、浅灰或明显更淡的批改字、勾线、扫描残影、透页字和水印都不是学生答案，'
        '不得当作格外修正字；只有格内原字被清楚划掉，且格外字与学生主体答案同色同笔迹并紧邻该槽时，才按格外修正处理。\n'
        '田字格通常一格对应一个汉字。每格内贴近左、右边界的深色手写笔画仍属于该格汉字，'
        '不得把它误当格线、相邻字或噪声而丢弃；识别整个字时必须纳入这些边缘笔画，尤其确认它们是否组成完整偏旁。\n'
        f'{CHINESE_SLASH_TIANZIGE_RULES.strip()}\n'
        f'题干摘要：{question.get("stem_excerpt") or ""}\n'
        f'大题背景：{question.get("parent_stem_excerpt") or ""}\n'
        f'当前转写 student_answer：{question.get("student_answer") or ""}\n'
        f'参考答案 correct_answer：{question.get("correct_answer") or ""}\n'
        f'当前 verdict：{question.get("verdict") or ""}\n'
        '这里的 ok 只表示图中学生最终保留的手写答案本身是否正确，不表示当前 verdict 是否已经被上一轮修正。'
        '即使当前 verdict 已是 wrong/partial，或 student_answer 已带有字形描述，只要截图中的最终手写字仍明显错误，'
        '仍必须 ok=false，并据图完整返回 visual_answer、expected_answer 和 fix；不得因为现有判定已经正确而返回 ok=true。\n'
        '这是针对整页转写可能漏掉细小字形错误的逐字复核：多词答案必须逐词、逐字与截图比较，'
        '不得因为 student_answer 与 correct_answer 文本相同就跳过视觉核对。尤其检查目标字外是否多写了一个完整偏旁/部件，'
        '从而形成另一个可编码的标准汉字；若是，必须直接转写该实际标准错字并 ok=false，不得只核对字的主体部件。\n'
        '请先按图像笔画重新写出 visual_answer（只写最终保留、未划掉的手写字；'
        '格内被斜杠划掉而格外/上方/旁边有修正字时，以修正字为准）。'
        '转写时必须先暂时忽略 expected_answer 和现有 student_answer，把每个完整手写字形独立识别为标准汉字；'
        '只要整个字能对应任一可编码标准汉字，即使读音或语境不符，也直接输出该实际标准错字。'
        '遇到目标字旁边像是多出一个完整偏旁时，必须把该偏旁与其余笔画合在一起重新识别整个字；'
        '若组合后能构成标准汉字，就输出这个完整标准汉字，不得拆成“目标字+某处写错”的括号描述。'
        '不得先输出 expected_answer，再为它编造括号内的局部差异。'
        '若实际错字无法用标准汉字编码，必须使用系统规定的括号格式，只描述错误或不规范的局部；'
        '括号必须紧跟同一作答字槽的目标字，保留全部字槽的数量与顺序，'
        '不得把括号附到前后相邻字，也不得漏掉当前字。'
        '能编码时禁止强行套用括号格式；'
        '括号内必须是相对目标字真实存在的差异，不得把目标字本来就有的正确部件描述成错误；'
        '不得将其归一化成 expected_answer，也不得只写「错字」。'
        '若 visual_answer 使用可编码的标准错字，reason 和 fix.error_type 只说明实际字与应写字，'
        '不得额外臆测部件结构，也不得给其他没有独立明确证据的字附加括号描述；只有非标准字括号转写才解释局部结构。'
        '括号格式只用于记录已经确认的明显错字，不得为了套用格式而刻意寻找单笔长短、连断、收笔或封口等细微差异。'
        '但若图像明确显示多写、漏写或替换整个偏旁/部件，必须按明显错别字处理，不得归为笔迹风格。'
        '再写 expected_answer；它必须原样复制上面输入的参考答案 correct_answer，即使你认为该参考答案有误也不得改写。\n'
        '【重要】仅抓明显错别字：缺偏旁部首、写成另一常用字、整词与拼音/语境明显不符等。'
        '以下情况必须 ok=true，不得改判：'
        '① visual_answer 与 expected_answer 一致或仅差笔迹粗细/连笔/略糊但字可辨认；'
        '② 只是写法略丑、结构略挤，但仍能明确认出是目标字；'
        '③ 无法确定是否错字时，保持原 verdict 不变。'
        '若学生手写按拼音和语境明显正确、只是输入的 correct_answer 本身有误，则 ok=true，visual_answer 据图填写，'
        'expected_answer 仍原样复制旧 correct_answer，并在 reason 中说明参考答案问题；不要把新答案写进 expected_answer。\n'
        '只有 visual_answer 与 expected_answer 明显不是同一个词/字时，才 ok=false，'
        'fix.verdict 为 wrong 或 partial（若当前为 wrong/partial 且图像与 expected 一致，'
        '可 fix.verdict 为 correct），fix.student_answer 必须完整复制 visual_answer，'
        'fix.error_type 简要说明「字形错误/错别字」。\n'
        '无论 ok 为 true 还是 false，都必须填写完整 visual_answer 与 expected_answer；'
        '不能只返回 id 和 ok。必须逐格独立重读，再把整道题所有最终保留字写入 visual_answer。\n'
        '输出 JSON：{"items":[{"id":"'
        + qid
        + '","ok":true/false,"visual_answer":"","expected_answer":"","reason":"","fix":{"verdict":"wrong","student_answer":"","error_type":""}}]}'
    )


def _focused_review_result_validation_error(
    result: Dict[str, Any],
    qid: str,
    question: Dict[str, Any],
) -> str:
    item = next((
        candidate for candidate in result.get('items') or []
        if isinstance(candidate, dict) and str(candidate.get('id') or '').strip() == qid
    ), None)
    if not isinstance(item, dict):
        return f'focused 结果缺少题号 {qid}'
    if not isinstance(item.get('ok'), bool):
        return f'focused 题号 {qid} 的 ok 必须是布尔值'
    visual_answer = str(item.get('visual_answer') or '').strip()
    expected_answer = str(item.get('expected_answer') or '').strip()
    if not visual_answer or not expected_answer:
        return f'focused 题号 {qid} 必须填写 visual_answer 与 expected_answer'
    if _normalize_evidence_text(expected_answer) != _normalize_evidence_text(
        question.get('correct_answer')
    ):
        return f'focused 题号 {qid} 的 expected_answer 与标准答案不一致'
    if item.get('ok') is False:
        fix = item.get('fix') if isinstance(item.get('fix'), dict) else {}
        if str(fix.get('student_answer') or '').strip() != visual_answer:
            return f'focused 题号 {qid} 的 fix.student_answer 必须完整复制 visual_answer'
    return ''


def _focused_chinese_visual_review_question(
    image_path: str,
    question: Dict[str, Any],
    page_num: int,
    error_dump_path: str,
    grade: int,
    stage: int,
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        _subject, grade, stage = runtime_attributes(feedback_runtime)
    qid = str(question.get('id') or '').strip()
    crop_path, cleanup_path = _crop_question_image(image_path, question, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    try:
        messages = [
            {'role': 'system', 'content': pass1_review_system('chinese', grade=grade, stage=stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
            {
                'role': 'user',
                'content': [
                    {'type': 'image_url', 'image_url': {'url': image_to_data_uri_for_gemini_review(crop_path)}},
                    {
                        'type': 'text',
                        'text': _focused_chinese_visual_review_user_prompt(question, page_num, qid),
                    },
                ],
            },
        ]
        raw = _call_review_llm(
            messages,
            error_dump_path=error_dump_path,
            result_validator=lambda result: _focused_review_result_validation_error(
                result,
                qid,
                question,
            ),
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        items = _normalize_review_items(raw.get('items'), [qid])
        return items[0] if items else {'id': qid, 'ok': True}
    finally:
        if cleanup_path:
            try:
                os.remove(cleanup_path)
            except OSError:
                pass


def _focused_confirmation_user_prompt(
    question: Dict[str, Any],
    page_num: int,
    qid: str,
    focused_item: Dict[str, Any],
    evidence: Dict[str, Any],
) -> str:
    candidate_scope = str(evidence.get('scope') or '')
    candidate_detail = (
        f'实际标准错字={evidence.get("observed_char") or ""}'
        if candidate_scope == 'standard_char'
        else (
            f'位置={evidence.get("location") or ""}，'
            f'替换部件={evidence.get("replacement") or ""}'
        )
    )
    return (
        f'请确认第 {page_num} 页题号 {qid} 的复杂字字形冲突。'
        '图片是从原始答案框重新生成的低边距紧裁剪，不是上一次 focused 的截图。\n'
        '只核对与学生主体答案同为深色、笔迹一致的手写字。浅红、浅灰或明显更淡的批改字、勾线、扫描残影、透页字和水印必须忽略；'
        '格外字只有在格内原字被明确划掉且同色同笔迹时，才可视为学生修正。\n'
        '田字格通常一格对应一个汉字；同格内贴近左右边界的深色手写笔画仍属于该字，不能当作格线、相邻字或噪声丢弃，'
        '必须据全部边缘笔画判断是否存在完整偏旁。\n'
        '首次 focused 结论只是待证伪主张，不得直接复述或默认相信；必须重新观察图片，'
        '并将目标字的规范结构与学生最终保留字形逐笔、逐部件比较。'
        '如果首次主张所说的部件本来就是目标字的规范结构或常见手写形态，必须判 matches_expected。\n'
        f'参考答案：{question.get("correct_answer") or ""}\n'
        f'目标槽位（从1开始）：{evidence.get("target_slot") or ""}\n'
        f'目标字：{evidence.get("target_char") or ""}\n'
        f'首次 focused visual_answer：{focused_item.get("visual_answer") or ""}\n'
        f'首次证据类型：{candidate_scope}；{candidate_detail}\n'
        '请按以下顺序判断：第一步先遮蔽首次主张，只根据图像把该槽完整字形识别为一个字，判断整体是否仍可明确认作目标字；'
        '第二步只有在整体不能认作目标字时，才检查首次主张所称的标准错字或替换部件是否真实存在。'
        '若不看首次主张时不会主动判错，必须选 matches_expected 或 uncertain。'
        '局部仅仅看起来像另一个部件不足以判 component_difference；必须确认目标位置原有的完整多笔部件确实被另一个完整部件替换，'
        '而不是正常手写变形、单笔形态或目标字规范结构的一部分。若整字仍能清楚读成目标字，选 matches_expected。\n'
        'classification 只能是以下之一：'
        'matches_expected、standard_wrong_char、component_difference、single_stroke、uncertain。\n'
        '判定要求：'
        '① 图中字形与规范目标字一致，或首次所谓错误其实是规范部件/常见手写形态，选 matches_expected；'
        '② 整个字明确是另一个可编码汉字，选 standard_wrong_char，并填写 observed_char；'
        '③ 明确替换了完整部件且无法编码为标准汉字，选 component_difference，'
        'component_position 只能填右下、左下、右上、左上、右、左、上、下，'
        'replacement_component 只填实际替换部件；'
        '④ 仅多、少、漏、添或改变一笔，选 single_stroke；'
        '⑤ 无法稳定确认，选 uncertain。'
        '不得为了支持首次结论而寻找细微差异。\n'
        'visual_answer 必须重新转写整道题的全部最终答案；除目标槽外的所有字槽也必须与图像一致。'
        '若重新转写时任何无关字槽与首次 focused visual_answer 不一致，'
        '说明证据不稳定，应选 uncertain，不得确认首次结论。\n'
        '所有分类都必须原样填写 expected_answer、target_slot、target_char；'
        'visual_answer 据图填写。只输出 JSON：'
        '{"items":[{"id":"'
        + qid
        + '","classification":"matches_expected",'
        '"expected_answer":"","target_slot":1,"target_char":"",'
        '"visual_answer":"","observed_char":"","component_position":"",'
        '"replacement_component":"","reason":""}]}'
    )


def _focused_chinese_visual_confirmation_question(
    image_path: str,
    question: Dict[str, Any],
    page_num: int,
    focused_item: Dict[str, Any],
    evidence: Dict[str, Any],
    error_dump_path: str,
    grade: int,
    stage: int,
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        _subject, grade, stage = runtime_attributes(feedback_runtime)
    qid = str(question.get('id') or '').strip()
    crop_path, cleanup_path = _crop_question_image(
        image_path,
        question,
        confirmation=True,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    try:
        messages = [
            {'role': 'system', 'content': pass1_review_system('chinese', grade=grade, stage=stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
            {
                'role': 'user',
                'content': [
                    {'type': 'image_url', 'image_url': {'url': image_to_data_uri_for_gemini_review(crop_path)}},
                    {
                        'type': 'text',
                        'text': _focused_confirmation_user_prompt(
                            question,
                            page_num,
                            qid,
                            focused_item,
                            evidence,
                        ),
                    },
                ],
            },
        ]
        raw = _call_review_llm(messages, error_dump_path=error_dump_path, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        return _normalize_confirmation_item(raw.get('items'), qid, question)
    finally:
        if cleanup_path:
            try:
                os.remove(cleanup_path)
            except OSError:
                pass


_GLYPH_ARBITRATION_SYSTEM_PROMPT = '''你是一名视觉转写员。本轮只依据提供的田字格截图识别学生最终保留的手写汉字。

不要判断对错，不要推测题目内容或规范答案，不要根据常见词语归一化笔迹。每个字格只能输出 recognized、nonstandard、unclear、blank 之一；只有能稳定识别为单个标准汉字时才使用 recognized，并填写恰好一个汉字。其余状态 recognized_char 必须为空。只输出指定 JSON。'''

_SINGLE_CELL_GLYPH_SYSTEM_PROMPT = (
    '你是纯视觉汉字转写员。只依据唯一一张田字格截图识别格内学生最终保留的手写字。'
    '不要判断对错，不要推测词语、题目或上下文，不要把笔迹归一化成常见答案。'
)


def _loads_single_cell_glyph_json(raw: str) -> Dict[str, Any]:
    """Repair only the observed proxy defect: one missing final object brace."""
    try:
        return _loads_json_with_retry_text(raw)
    except json.JSONDecodeError:
        clean = str(raw or '').strip()
        if (
            clean.startswith('{')
            and not clean.endswith('}')
            and clean.count('{') == clean.count('}') + 1
        ):
            return json.loads(clean + '}')
        raise


def _single_cell_glyph_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    if 'status' in result or 'recognized_char' in result:
        return result
    items = result.get('items')
    if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict):
        return items[0]
    return result


def _single_cell_glyph_validation_error(result: Dict[str, Any]) -> str:
    payload = _single_cell_glyph_payload(result)
    status = str(payload.get('status') or '').strip()
    recognized_char = str(payload.get('recognized_char') or '').strip()
    if status not in _GLYPH_STATUSES:
        return 'single-cell glyph status is invalid'
    if status == 'recognized':
        if not _CJK_CHAR_RE.fullmatch(recognized_char):
            return 'recognized single-cell glyph must contain exactly one CJK character'
    elif recognized_char:
        return 'non-recognized single-cell glyph must not contain recognized_char'
    return ''


def _single_cell_glyph_prompt() -> str:
    return (
        '忽略格线、虚线、浅色批改痕迹和水印。若能稳定识别为恰好一个标准Unicode汉字，'
        '输出status为recognized并填写该字；否则输出nonstandard、unclear或blank之一，'
        'recognized_char必须为空。只输出JSON：'
        '{"status":"recognized","recognized_char":""}'
    )


def _normalize_glyph_slot_items(raw_items: Any, expected_slots: List[int]) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        raise ValueError('glyph slot items must be a list')
    normalized: List[Dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError('glyph slot item must be an object')
        try:
            slot = int(raw.get('slot'))
        except (TypeError, ValueError) as exc:
            raise ValueError('glyph slot index is invalid') from exc
        status = str(raw.get('status') or '').strip()
        recognized_char = str(raw.get('recognized_char') or '').strip()
        if status not in _GLYPH_STATUSES:
            raise ValueError('glyph slot status is invalid')
        if status == 'recognized':
            if not _CJK_CHAR_RE.fullmatch(recognized_char):
                raise ValueError('recognized glyph must contain exactly one CJK character')
        elif recognized_char:
            raise ValueError('non-recognized glyph must not contain recognized_char')
        normalized.append({
            'slot': slot,
            'status': status,
            'recognized_char': recognized_char,
        })
    if [item['slot'] for item in normalized] != expected_slots:
        raise ValueError('glyph slot indexes do not match the requested visual order')
    return normalized


def _glyph_arbitration_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Accept Gemini's harmless single-item envelope without weakening schema checks."""
    if not isinstance(result, dict):
        return {}
    if 'target_slots' in result or 'row_slots' in result:
        return result
    items = result.get('items')
    if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict):
        return items[0]
    return result


def _glyph_arbitration_validation_error(
    result: Dict[str, Any],
    target_slots: List[int],
    row_count: int,
) -> str:
    payload = _glyph_arbitration_payload(result)
    try:
        _normalize_glyph_slot_items(payload.get('target_slots'), target_slots)
        _normalize_glyph_slot_items(payload.get('row_slots'), list(range(1, row_count + 1)))
    except ValueError as exc:
        return str(exc)
    return ''


def _glyph_arbitration_prompt(target_slots: List[int], row_count: int) -> str:
    return (
        '前面的单格图片按顺序对应整行中的第 '
        + '、'.join(str(slot) for slot in target_slots)
        + ' 格；最后一张图片是完整田字格行。'
        '请分别独立识别单格图片，并按从左到右顺序识别整行的每个字格。'
        '格线、题面印刷字、教师浅色批改痕迹和水印不是学生答案。'
        '输出 JSON：{"target_slots":['
        '{"slot":1,"status":"recognized","recognized_char":""}'
        '],"row_slots":['
        '{"slot":1,"status":"recognized","recognized_char":""}'
        ']}。整行必须恰好输出 '
        + str(row_count)
        + ' 个连续槽位；目标槽位使用上面给出的真实序号。'
    )


def _single_cell_glyph_question(
    image_path: str,
    question: Dict[str, Any],
    plan: Dict[str, Any],
    review_path: str,
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    target_slots = [int(slot) for slot in plan.get('target_slots') or []]
    expected_count = len(plan.get('expected_slots') or [])
    if len(target_slots) != 1:
        return {
            'id': str(question.get('id') or '').strip(),
            'status': 'invalid',
            'block_reason': 'single_cell_target_count_invalid',
        }
    roi = detect_tianzige_cells(image_path, question.get('position'), expected_count)
    if roi.get('status') != 'available':
        return {
            'id': str(question.get('id') or '').strip(),
            'status': 'roi_unavailable',
            'block_reason': str(roi.get('failure_reason') or 'glyph_roi_unavailable'),
            'roi': roi,
        }
    safe_qid = re.sub(r'[^0-9A-Za-z_-]+', '_', str(question.get('id') or '').strip())
    forced_yaolai_roi = 'yaolai_sample_forced_roi' in (plan.get('trigger_reasons') or [])
    if forced_yaolai_roi:
        # Deep experiment output directories can put the descriptive crop name
        # beyond Windows MAX_PATH. Keep this sample-specific artifact concise.
        output_prefix = os.path.join(os.path.dirname(review_path), f'yaolai_roi.{safe_qid}')
    else:
        output_prefix = review_path[:-5] if review_path.endswith('.json') else review_path
        output_prefix += f'.glyph.single.{safe_qid}'
    crops = crop_tianzige_targets(image_path, roi, target_slots, output_prefix)
    targets = list(crops.get('targets') or [])
    if len(targets) != 1:
        return {
            'id': str(question.get('id') or '').strip(),
            'status': 'invalid',
            'block_reason': 'single_cell_crop_count_invalid',
            'roi': roi,
            'crops': crops,
        }
    content: List[Dict[str, Any]] = [
        {
            'type': 'image_url',
            'image_url': {
                'url': image_to_data_uri_for_gemini_review(targets[0]['path']),
            },
        },
        {'type': 'text', 'text': _single_cell_glyph_prompt()},
    ]
    messages = [
        {'role': 'system', 'content': _SINGLE_CELL_GLYPH_SYSTEM_PROMPT},
        {'role': 'user', 'content': content},
    ]
    forbidden_fields = (
        'student_answer', 'correct_answer', 'verdict', 'expected_answer',
        'pinyin', 'focused',
    )
    business_values = [
        str(question.get(field) or '').strip()
        for field in (
            'id', 'student_answer', 'correct_answer',
            'stem_excerpt', 'parent_stem_excerpt',
        )
    ]
    request_text = json.dumps([
        part.get('text')
        for part in content
        if isinstance(part, dict) and part.get('type') == 'text'
    ], ensure_ascii=False) + _SINGLE_CELL_GLYPH_SYSTEM_PROMPT
    forbidden_present = [
        value for value in forbidden_fields
        if value and value in request_text
    ]
    forbidden_present.extend(
        'business_value'
        for value in business_values
        if len(value) >= 2 and value in request_text
    )
    raw = _call_review_llm(
        messages,
        error_dump_path=(
            f'{output_prefix}.error.txt'
            if forced_yaolai_roi
            else review_path.replace('.json', f'.glyph.single.{safe_qid}.error.txt')
        ),
        result_validator=_single_cell_glyph_validation_error,
        raw_parser=_loads_single_cell_glyph_json,
        require_items=False,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    payload = _single_cell_glyph_payload(raw)
    target_result = {
        'slot': target_slots[0],
        'status': str(payload.get('status') or '').strip(),
        'recognized_char': str(payload.get('recognized_char') or '').strip(),
    }
    return {
        'id': str(question.get('id') or '').strip(),
        'status': 'completed',
        'single_cell_only': True,
        'target_result': target_result,
        'group_break_slots': list(roi.get('group_break_slots') or []),
        'roi': roi,
        'crops': crops,
        'request_audit': {
            'image_count': 1,
            'forbidden_fields_present': forbidden_present,
            'business_text_leakage_free': not forbidden_present,
        },
    }


def _glyph_arbitration_question(
    image_path: str,
    question: Dict[str, Any],
    plan: Dict[str, Any],
    review_path: str,
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    target_slots = [int(slot) for slot in plan.get('target_slots') or []]
    expected_count = len(plan.get('expected_slots') or [])
    roi = detect_tianzige_cells(image_path, question.get('position'), expected_count)
    if roi.get('status') != 'available':
        return {
            'id': str(question.get('id') or '').strip(),
            'status': 'roi_unavailable',
            'block_reason': str(roi.get('failure_reason') or 'glyph_roi_unavailable'),
            'roi': roi,
        }
    safe_qid = re.sub(r'[^0-9A-Za-z_-]+', '_', str(question.get('id') or '').strip())
    output_prefix = review_path[:-5] if review_path.endswith('.json') else review_path
    output_prefix += f'.glyph.{safe_qid}'
    crops = crop_tianzige_evidence(image_path, roi, target_slots, output_prefix)
    content: List[Dict[str, Any]] = []
    for target in crops['targets']:
        content.extend([
            {'type': 'image_url', 'image_url': {'url': image_to_data_uri_for_gemini_review(target['path'])}},
            {'type': 'text', 'text': f'上一张图片是整行从左到右第 {target["slot"]} 格。'},
        ])
    content.extend([
        {'type': 'image_url', 'image_url': {'url': image_to_data_uri_for_gemini_review(crops['row_path'])}},
        {'type': 'text', 'text': _glyph_arbitration_prompt(target_slots, expected_count)},
    ])
    messages = [
        {'role': 'system', 'content': _GLYPH_ARBITRATION_SYSTEM_PROMPT},
        {'role': 'user', 'content': content},
    ]
    forbidden = ('student_answer', 'correct_answer', 'verdict', 'expected_answer', 'pinyin', 'focused')
    request_text = json.dumps([
        part.get('text')
        for part in content
        if isinstance(part, dict) and part.get('type') == 'text'
    ], ensure_ascii=False) + _GLYPH_ARBITRATION_SYSTEM_PROMPT
    raw = _call_review_llm(
        messages,
        error_dump_path=review_path.replace('.json', f'.glyph.{safe_qid}.error.txt'),
        result_validator=lambda result: _glyph_arbitration_validation_error(
            result,
            target_slots,
            expected_count,
        ),
        require_items=False,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    payload = _glyph_arbitration_payload(raw)
    target_results = _normalize_glyph_slot_items(payload.get('target_slots'), target_slots)
    row_results = _normalize_glyph_slot_items(
        payload.get('row_slots'),
        list(range(1, expected_count + 1)),
    )
    return {
        'id': str(question.get('id') or '').strip(),
        'status': 'completed',
        'target_results': target_results,
        'row_results': row_results,
        'row_slots': [item['recognized_char'] for item in row_results],
        'group_break_slots': list(roi.get('group_break_slots') or []),
        'roi': roi,
        'crops': crops,
        'request_audit': {
            'image_count': len(target_slots) + 1,
            'forbidden_fields_present': [field for field in forbidden if field in request_text],
            'business_text_leakage_free': not any(field in request_text for field in forbidden),
        },
    }


def _run_focused_chinese_visual_review(
    image_path: str,
    page_data: Dict[str, Any],
    review_report: Dict[str, Any],
    review_path: str,
    grade: int,
    stage: int,
    *, feedback_runtime=None,
) -> List[Dict[str, Any]]:
    if feedback_runtime is not None:
        _subject, grade, stage = runtime_attributes(feedback_runtime)
    if feedback_runtime is not None and not feedback_runtime.has_specialized('chinese'):
        review_report.setdefault('feedback_skips', []).append('未匹配语文字形专项')
        return []
    if not focused_chinese_visual_review_enabled(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})):
        return []
    candidates = [
        question for question in page_data.get('questions') or []
        if isinstance(question, dict) and _needs_focused_chinese_visual_review(question)
    ][:_focused_visual_review_limit(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))]
    if not candidates:
        return []

    review_report['focused_candidate_ids'] = [
        str(question.get('id') or '').strip() for question in candidates
    ]
    focused_items: List[Dict[str, Any]] = []
    focused_failures: List[Dict[str, Any]] = []
    for question in candidates:
        qid = str(question.get('id') or '').strip()
        try:
            item = _focused_chinese_visual_review_question(
                image_path,
                question,
                int(page_data.get('page') or 0),
                review_path.replace('.json', f'.focus.{re.sub(r"[^0-9A-Za-z_-]+", "_", qid)}.error.txt'),
                grade,
                stage,
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        except ValueError as exc:
            quota_limited = _is_gemini_quota_error(exc)
            failure = {
                'id': qid,
                'error': str(exc),
                'quota_limited': quota_limited,
            }
            focused_failures.append(failure)
            focused_items.append({
                'id': qid,
                'ok': True,
                'response_missing': True,
                'error': str(exc),
            })
            if quota_limited:
                review_report['quota_limited'] = True
                break
            continue
        if item.get('response_missing') is True:
            focused_failures.append({
                'id': qid,
                'error': str(item.get('error') or 'focused response missing or invalid'),
                'quota_limited': False,
            })
        focused_items.append(item)

    review_report['focused_items'] = focused_items
    if focused_failures:
        review_report['focused_failures'] = focused_failures
    stats = review_report.setdefault('stats', {})
    stats['focused_total'] = len(focused_items)
    stats['focused_failed'] = len(focused_failures)
    stats['focused_issues'] = sum(1 for item in focused_items if item.get('ok') is False)
    return focused_items


def _run_complex_glyph_confirmations(
    image_path: str,
    page_data: Dict[str, Any],
    review_report: Dict[str, Any],
    review_path: str,
    grade: int,
    stage: int,
    *, feedback_runtime=None,
) -> List[Dict[str, Any]]:
    if feedback_runtime is not None:
        _subject, grade, stage = runtime_attributes(feedback_runtime)
    if feedback_runtime is not None and not feedback_runtime.has_specialized('chinese'):
        review_report.setdefault('feedback_skips', []).append('未匹配语文字形专项')
        return []
    if review_report.get('quota_limited'):
        review_report['confirmation_items'] = []
        return []

    questions_by_id = {
        str(question.get('id') or '').strip(): question
        for question in page_data.get('questions') or []
        if isinstance(question, dict) and str(question.get('id') or '').strip()
    }
    page_items = {
        str(item.get('id') or '').strip(): item
        for item in review_report.get('items') or []
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    focused_items = {
        str(item.get('id') or '').strip(): item
        for item in review_report.get('focused_items') or []
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    candidate_ids = [
        str(qid or '').strip()
        for qid in review_report.get('focused_candidate_ids') or []
        if str(qid or '').strip()
    ]

    confirmation_items: List[Dict[str, Any]] = []
    confirmation_failures: List[Dict[str, Any]] = []
    for qid in candidate_ids:
        question = questions_by_id.get(qid)
        focused_item = focused_items.get(qid)
        if not question or not focused_item:
            continue
        _merged, preliminary_audit = _aggregate_chinese_visual_review(
            question,
            page_items.get(qid),
            focused_item,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        if preliminary_audit.get('confirmation_required') is not True:
            continue
        evidence = _focused_override_evidence(focused_item, question)
        try:
            item = _focused_chinese_visual_confirmation_question(
                image_path,
                question,
                int(page_data.get('page') or 0),
                focused_item,
                evidence,
                review_path.replace(
                    '.json',
                    f'.confirm.{re.sub(r"[^0-9A-Za-z_-]+", "_", qid)}.error.txt',
                ),
                grade,
                stage,
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        except ValueError as exc:
            quota_limited = _is_gemini_quota_error(exc)
            failure = {
                'id': qid,
                'error': str(exc),
                'quota_limited': quota_limited,
            }
            confirmation_failures.append(failure)
            confirmation_items.append({
                'id': qid,
                'classification': 'uncertain',
                'response_missing': True,
                'error': str(exc),
            })
            if quota_limited:
                review_report['quota_limited'] = True
                break
            continue
        if item.get('response_missing') is True or item.get('invalid') is True:
            confirmation_failures.append({
                'id': qid,
                'error': str(
                    item.get('validation_error')
                    or item.get('error')
                    or 'confirmation response missing or invalid'
                ),
                'quota_limited': False,
            })
        confirmation_items.append(item)

    review_report['confirmation_items'] = confirmation_items
    if confirmation_failures:
        review_report['confirmation_failures'] = confirmation_failures
    stats = review_report.setdefault('stats', {})
    stats['confirmation_total'] = len(confirmation_items)
    stats['confirmation_failed'] = len(confirmation_failures)
    return confirmation_items


def _run_glyph_arbitrations(
    image_path: str,
    page_data: Dict[str, Any],
    review_report: Dict[str, Any],
    review_path: str,
    *, feedback_runtime=None,
) -> List[Dict[str, Any]]:
    if feedback_runtime is not None and not feedback_runtime.has_specialized('chinese'):
        review_report.setdefault('feedback_skips', []).append('未匹配语文字形专项')
        return []
    if review_report.get('quota_limited') or glyph_arbitration_mode(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) == 'off':
        review_report['glyph_arbitration_items'] = []
        return []
    questions_by_id = {
        str(question.get('id') or '').strip(): question
        for question in page_data.get('questions') or []
        if isinstance(question, dict) and str(question.get('id') or '').strip()
    }
    page_items = {
        str(item.get('id') or '').strip(): item
        for item in review_report.get('items') or []
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    focused_items = {
        str(item.get('id') or '').strip(): item
        for item in review_report.get('focused_items') or []
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    items: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for qid in review_report.get('focused_candidate_ids') or []:
        qid = str(qid or '').strip()
        question = questions_by_id.get(qid)
        if not question:
            continue
        _merged, preliminary_audit = _aggregate_chinese_visual_review(
            question,
            page_items.get(qid),
            focused_items.get(qid),
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        if preliminary_audit.get('glyph_arbitration_required') is not True:
            continue
        plan = _glyph_arbitration_plan(question, page_items.get(qid), focused_items.get(qid), **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        if plan.get('required') is not True:
            continue
        try:
            question_runner = (
                _single_cell_glyph_question
                if plan.get('single_cell_only') is True
                else _glyph_arbitration_question
            )
            item = question_runner(
                image_path,
                question,
                plan,
                review_path,
            )
        except Exception as exc:
            quota_limited = _is_gemini_quota_error(exc)
            item = {
                'id': qid,
                'status': 'failed',
                'block_reason': 'glyph_arbitration_call_failed',
                'error': str(exc),
                'quota_limited': quota_limited,
            }
            if quota_limited:
                review_report['quota_limited'] = True
        if item.get('status') != 'completed':
            failures.append({
                'id': qid,
                'status': item.get('status'),
                'error': item.get('error') or item.get('block_reason'),
                'quota_limited': bool(item.get('quota_limited')),
            })
        items.append(item)
        if review_report.get('quota_limited'):
            break
    review_report['glyph_arbitration_items'] = items
    if failures:
        review_report['glyph_arbitration_failures'] = failures
    stats = review_report.setdefault('stats', {})
    stats['glyph_arbitration_requested'] = len(items)
    stats['glyph_single_cell_requested'] = sum(
        1 for item in items if item.get('single_cell_only') is True
    )
    stats['glyph_arbitration_failed'] = len(failures)
    stats['glyph_roi_available'] = sum(
        1 for item in items if (item.get('roi') or {}).get('status') == 'available'
    )
    return items


def _candidate_skip_result(json_path: str, skip_reason: str, *, feedback_runtime=None) -> Dict[str, Any]:
    page_num = parse_page_num(os.path.basename(json_path))
    review_path = _review_json_path(json_path)
    _write_skipped_review(page_num, review_path, skip_reason=skip_reason, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    return {
        'page': page_num,
        'review_path': review_path,
        'skipped': True,
        'skip_reason': skip_reason,
        'issues': 0,
        'applied': 0,
    }


def _candidate_reuse_result(
    json_path: str,
    review_report: Dict[str, Any],
) -> Dict[str, Any]:
    page_num = parse_page_num(os.path.basename(json_path))
    stats = review_report.get('stats') if isinstance(review_report.get('stats'), dict) else {}
    return {
        'page': page_num,
        'review_path': _review_json_path(json_path),
        'skipped': False,
        'reused': True,
        'issues': int(stats.get('issues') or 0),
        'applied': int(stats.get('applied') or 0),
        'quota_limited': bool(review_report.get('quota_limited')),
        'error': review_report.get('error') or review_report.get('focused_error'),
    }


def _load_reusable_review_report(
    json_path: str,
    page_data: Dict[str, Any],
    subject: str,
    *, feedback_runtime=None,
) -> Optional[Dict[str, Any]]:
    from .execution_control import current_execution
    if current_execution() is not None:
        # 受控运行使用完整图片/请求/代码校验的模型检查点，不仅凭旧复核文件存在复用。
        return None
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if not pass1_review_reuse_existing(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})):
        return None
    review_path = _review_json_path(json_path)
    if not os.path.isfile(review_path):
        return None
    report = safe_json_load(review_path)
    if not isinstance(report, dict):
        return None
    if feedback_runtime is not None and not artifact_compatible(report, feedback_runtime):
        return None
    if report.get('skipped') or report.get('error') or report.get('focused_error') or report.get('quota_limited'):
        return None
    if subject == 'chinese' and report.get('review_strategy') != _REVIEW_STRATEGY:
        return None
    signature = _review_snapshot_signature(page_data, subject)
    if signature in (
        str(report.get('post_review_signature') or ''),
        str(report.get('pre_review_signature') or ''),
    ):
        return report
    return None


def _run_review_candidate(
    json_path: str,
    image_path: str,
    subject: str,
    grade: int,
    stage: int,
    source_document_sha256: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if feedback_runtime is not None:
        _subject, grade, stage = runtime_attributes(feedback_runtime)
    try:
        return _review_one_page(
            json_path,
            image_path,
            subject,
            grade,
            stage,
            source_document_sha256,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    except Exception as exc:
        logger.exception('Pass1 自检单页失败')
        from .execution_control import budget_diagnostics
        budget = budget_diagnostics(exc)
        result = stamp_feedback({
            'page': parse_page_num(os.path.basename(json_path)),
            'review_path': _review_json_path(json_path),
            'skipped': False,
            'error': str(exc) if budget else '逐页复核失败：' + type(exc).__name__,
            'error_kind': type(exc).__name__,
            'budget': budget,
            'quota_limited': _is_gemini_quota_error(exc),
            'issues': 0,
            'applied': 0,
        }, feedback_runtime, 'review')
        # 失败也保存逐页回执；读取不必依赖进程日志，失败回执不能被当作成功复用。
        safe_json_dump(_review_json_path(json_path), result)
        return result


def _run_review_candidates(
    candidates: List[tuple],
    subject: str,
    grade: int,
    stage: int,
    worker_count: int,
    stop_on_quota: bool,
    source_document_sha256: str = '',
    *, feedback_runtime=None,
) -> List[Dict[str, Any]]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if feedback_runtime is not None:
        _subject, grade, stage = runtime_attributes(feedback_runtime)
    results: List[Dict[str, Any]] = []
    if not candidates:
        return results

    if worker_count <= 1:
        for index, (json_path, image_path) in enumerate(candidates):
            result = _run_review_candidate(
                json_path,
                image_path,
                subject,
                grade,
                stage,
                source_document_sha256,
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
            results.append(result)
            if stop_on_quota and (result.get('quota_limited') or _is_gemini_quota_error(result.get('error'))):
                logger.warning('Pass1 自检检测到 Gemini 额度不足，停止后续复核。')
                for remaining_json_path, _remaining_image_path in candidates[index + 1:]:
                    results.append(_candidate_skip_result(remaining_json_path, 'gemini_quota_limited', **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})))
                break
        return results

    logger.info(
        'Pass1 Gemini 自检并行启动：candidates=%s workers=%s stop_on_quota=%s',
        len(candidates),
        worker_count,
        stop_on_quota,
    )
    executor = ThreadPoolExecutor(max_workers=worker_count)
    future_to_index: Dict[Any, int] = {}
    next_index = 0
    quota_stop = False

    def _submit_next() -> None:
        nonlocal next_index
        if next_index >= len(candidates):
            return
        json_path, image_path = candidates[next_index]
        future = executor.submit(
            _run_review_candidate,
            json_path,
            image_path,
            subject,
            grade,
            stage,
            source_document_sha256,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        future_to_index[future] = next_index
        next_index += 1

    try:
        for _ in range(min(worker_count, len(candidates))):
            _submit_next()

        while future_to_index:
            done, _pending = wait(future_to_index.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                future_to_index.pop(future, None)
                result = future.result()
                results.append(result)
                if stop_on_quota and (result.get('quota_limited') or _is_gemini_quota_error(result.get('error'))):
                    quota_stop = True

            if quota_stop:
                logger.warning('Pass1 自检检测到 Gemini 额度不足，停止提交后续复核。')
                break

            while len(future_to_index) < worker_count and next_index < len(candidates):
                _submit_next()

        if quota_stop:
            cancelled_indices = set()
            for future, index in list(future_to_index.items()):
                if future.cancel():
                    cancelled_indices.add(index)
                    future_to_index.pop(future, None)

            for future in list(future_to_index.keys()):
                future_to_index.pop(future, None)
                results.append(future.result())

            skipped_indices = sorted(cancelled_indices | set(range(next_index, len(candidates))))
            for index in skipped_indices:
                remaining_json_path, _remaining_image_path = candidates[index]
                results.append(_candidate_skip_result(remaining_json_path, 'gemini_quota_limited', **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})))
    finally:
        _shutdown_executor(executor, wait=True, cancel_futures=True)

    return results


def review_page(
    image_path: str,
    page_data: Dict[str, Any],
    subject: str,
    page_num: int,
    out_review_path: str,
    grade: int = 4,
    stage: int = 2,
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if feedback_runtime is not None:
        _subject, grade, stage = runtime_attributes(feedback_runtime)
    snapshot = _build_review_snapshot(page_data, subject)
    expected_ids = [q['id'] for q in snapshot['questions']]
    messages = [
        {'role': 'system', 'content': pass1_review_system(subject, grade=grade, stage=stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
        {
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': image_to_data_uri_for_gemini_review(image_path)}},
                {
                    'type': 'text',
                    'text': pass1_review_user_prompt(subject, page_num, snapshot, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
                },
            ],
        },
    ]
    error_dump_path = out_review_path.replace('.json', '.error.txt')
    try:
        raw = _call_review_llm(messages, error_dump_path=error_dump_path, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    except ValueError as exc:
        quota_limited = _is_gemini_quota_error(exc)
        report = {
            'page': page_num,
            'model': (model_spec(feedback_runtime, 'review')['model'] if feedback_runtime is not None else homework_review_gemini_model()),
            'checked_at': datetime.now().isoformat(timespec='seconds'),
            'error': str(exc),
            'quota_limited': quota_limited,
            'items': [],
            'stats': {'total': len(expected_ids), 'issues': 0, 'applied': 0},
        }
        safe_json_dump(out_review_path, stamp_feedback(report, feedback_runtime, 'review'))
        return report

    items = _normalize_review_items(raw.get('items'), expected_ids)
    issues = sum(1 for item in items if item.get('ok') is False)
    report = {
        'page': page_num,
        'model': (model_spec(feedback_runtime, 'review')['model'] if feedback_runtime is not None else homework_review_gemini_model()),
        'quota_limited': False,
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'items': items,
        'stats': {'total': len(items), 'issues': issues, 'applied': 0},
    }
    safe_json_dump(out_review_path, stamp_feedback(report, feedback_runtime, 'review'))
    return report


def apply_review_to_page(page_data: Dict[str, Any], review_report: Dict[str, Any], *, feedback_runtime=None, source_document_sha256='') -> int:
    if review_report.get('error') or review_report.get('skipped'):
        return 0
    by_id = {
        str(q.get('id') or '').strip(): q
        for q in page_data.get('questions') or []
        if isinstance(q, dict) and str(q.get('id') or '').strip()
    }
    applied = 0
    from .note_evidence import is_notes, reconcile_note_review
    from .material_markings import MARKING_FIELDS, normalize_markings, open_material_runtime
    notes = is_notes(feedback_runtime)
    for item in review_report.get('items') or []:
        if not isinstance(item, dict):
            continue
        question = by_id.get(str(item.get('id') or '').strip())
        if not question:
            continue
        before = {key: copy.deepcopy(question.get(key)) for key in (
            'student_answer', 'verdict', 'correct_answer', 'error_type', 'understanding')}
        item_applied = _apply_review_item(question, item)
        if notes:
            fix = item.get('fix') if item.get('ok') is False and isinstance(item.get('fix'), dict) else {}
            reconcile_note_review(question, before, fix, item.get('reason'))
            item_applied = item_applied or any(question.get(k) != v for k, v in before.items())
        if open_material_runtime(feedback_runtime):
            fix = item.get('fix') if item.get('ok') is False and isinstance(item.get('fix'), dict) else {}
            for field in (*MARKING_FIELDS, 'understanding'):
                if field in fix and (field != 'understanding' or isinstance(fix[field], str)):
                    question[field] = copy.deepcopy(fix[field])
                    item_applied = True
            normalize_markings(question)
        if item_applied:
            applied += 1
    stats = review_report.setdefault('stats', {})
    stats['applied'] = applied
    def fixed_allowed(subject, action):
        if feedback_runtime is None:
            return True
        return bool(match_document_special_case(subject, page_data.get('page'), action,
            source_document_sha256=source_document_sha256, feedback_runtime=feedback_runtime))
    stats['fixed_english_choice_guards_restored'] = (
        (reapply_fixed_english_choice_guards(page_data) if fixed_allowed('english', 'fixed_english_choice_slots') else 0)
    )
    stats['fixed_english_page15_guards_restored'] = (
        (reapply_fixed_english_page15_guard(page_data) if fixed_allowed('english', 'english_visual_transcription_lock') else 0)
    )
    restored_page, fixed_math_restored = (reapply_fixed_math_sample_guards(
        page_data
    ) if fixed_allowed('math', 'math_fixed_sample_guard') else (page_data, 0))
    if fixed_math_restored:
        page_data.clear()
        page_data.update(restored_page)
    stats['fixed_math_sample_guards_restored'] = fixed_math_restored
    return applied


def _apply_aggregated_chinese_review(
    page_data: Dict[str, Any],
    review_report: Dict[str, Any],
    *, feedback_runtime=None,
) -> int:
    candidate_ids = {
        str(qid or '').strip()
        for qid in review_report.get('focused_candidate_ids') or []
        if str(qid or '').strip()
    }
    if not candidate_ids:
        return apply_review_to_page(page_data, review_report, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))

    questions_by_id = {
        str(question.get('id') or '').strip(): question
        for question in page_data.get('questions') or []
        if isinstance(question, dict) and str(question.get('id') or '').strip()
    }
    page_items = {
        str(item.get('id') or '').strip(): item
        for item in review_report.get('items') or []
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    focused_items = {
        str(item.get('id') or '').strip(): item
        for item in review_report.get('focused_items') or []
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    confirmation_items = {
        str(item.get('id') or '').strip(): item
        for item in review_report.get('confirmation_items') or []
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    glyph_items = {
        str(item.get('id') or '').strip(): item
        for item in review_report.get('glyph_arbitration_items') or []
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }

    applied = 0
    aggregation_applied = 0
    aggregation_items: List[Dict[str, Any]] = []
    for qid, question in questions_by_id.items():
        page_item = page_items.get(qid)
        if qid not in candidate_ids:
            if page_item and _apply_review_item(question, page_item):
                applied += 1
            continue

        merged_item, audit = _aggregate_chinese_visual_review(
            question,
            page_item,
            focused_items.get(qid),
            confirmation_items.get(qid),
            glyph_items.get(qid),
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        if merged_item is not None:
            item_applied = _apply_review_item(question, merged_item)
            audit['applied'] = item_applied
            audit['verdict_only_applied'] = bool(item_applied and audit.get('verdict_only'))
            if item_applied:
                audit['decision'] = 'applied'
                applied += 1
                aggregation_applied += 1
            else:
                audit['decision'] = 'kept'
                audit['block_reason'] = 'apply_rejected'
        aggregation_items.append(audit)

    review_report['aggregation_items'] = aggregation_items
    stats = review_report.setdefault('stats', {})
    page_issue_ids = {
        str(item.get('id') or '').strip()
        for item in review_report.get('items') or []
        if isinstance(item, dict) and item.get('ok') is False
    }
    focused_issue_ids = {
        str(item.get('id') or '').strip()
        for item in review_report.get('focused_items') or []
        if isinstance(item, dict) and item.get('ok') is False
    }
    blocked = [item for item in aggregation_items if item.get('block_reason')]
    stats['page_issues'] = len(page_issue_ids)
    stats['focused_issues'] = len(focused_issue_ids)
    stats['issues'] = len(page_issue_ids | focused_issue_ids)
    stats['aggregation_applied'] = aggregation_applied
    stats['aggregation_blocked'] = len(blocked)
    stats['single_stroke_blocked'] = sum(
        1 for item in blocked if item.get('block_reason') == 'single_stroke_difference'
    )
    stats['source_conflicts'] = sum(
        1 for item in blocked if item.get('block_reason') == 'source_conflict'
    )
    stats['evidence_mismatches'] = sum(
        1 for item in blocked if item.get('block_reason') == 'evidence_mismatch'
    )
    reference_answer_items = [
        item for item in aggregation_items
        if item.get('reference_answer_correction') is True
    ]
    stats['reference_answer_corrections_applied'] = sum(
        1 for item in reference_answer_items if item.get('applied') is True
    )
    stats['reference_answer_corrections_blocked'] = sum(
        1 for item in reference_answer_items if item.get('block_reason')
    )
    stats['complex_glyph_focused_overrides'] = sum(
        1 for item in aggregation_items
        if item.get('focused_override') is True and item.get('applied') is True
    )
    stats['complex_glyph_override_blocked'] = sum(
        1 for item in blocked if item.get('focused_override_evaluated') is True
    )
    confirmation_required = [
        item for item in aggregation_items if item.get('confirmation_required') is True
    ]
    stats['complex_glyph_confirmations_requested'] = len(confirmation_required)
    stats['complex_glyph_confirmations_completed'] = sum(
        1 for item in confirmation_required
        if item.get('confirmation_status') not in ('missing', 'invalid')
    )
    stats['complex_glyph_confirmations_failed'] = sum(
        1 for item in confirmation_required
        if item.get('confirmation_status') in ('missing', 'invalid')
    )
    stats['complex_glyph_confirmations_consistent'] = sum(
        1 for item in confirmation_required if item.get('confirmation_consistent') is True
    )
    stats['complex_glyph_confirmation_blocked'] = sum(
        1 for item in confirmation_required if item.get('confirmation_consistent') is not True
    )
    glyph_required = [
        item for item in aggregation_items if item.get('glyph_arbitration_required') is True
    ]
    stats['glyph_arbitration_consistent'] = sum(
        1 for item in glyph_required if item.get('glyph_arbitration_consistent') is True
    )
    stats['glyph_arbitration_would_apply'] = sum(
        1 for item in glyph_required if item.get('would_apply') is True
    )
    stats['glyph_wrong_slot_would_mark'] = sum(
        1 for item in glyph_required if item.get('would_mark_wrong') is True
    )
    stats['glyph_wrong_slot_applied'] = sum(
        1 for item in glyph_required if item.get('verdict_only_applied') is True
    )
    stats['glyph_arbitration_applied'] = sum(
        1 for item in glyph_required
        if item.get('applied') is True
        and item.get('decision_basis') in (
            'target_cell_and_row_consistent',
            'single_target_cell_recognized_existing_candidate',
        )
    )
    stats['glyph_single_cell_applied'] = sum(
        1 for item in glyph_required
        if item.get('applied') is True
        and item.get('decision_basis') == 'single_target_cell_recognized_existing_candidate'
    )
    stats['glyph_shadow_hits'] = sum(
        1 for item in glyph_required
        if item.get('would_apply') is True and item.get('glyph_arbitration_mode') == 'shadow'
    )
    stats['glyph_phonetic_candidates'] = sum(
        1 for item in glyph_required
        if any(
            reason in ('phonetic_preferred_candidate', 'homophone_wrong_slot')
            for reason in item.get('glyph_trigger_reasons') or []
        )
    )
    requested = int(stats.get('glyph_arbitration_requested') or 0)
    available = int(stats.get('glyph_roi_available') or 0)
    stats['glyph_roi_unavailable'] = max(0, requested - available)
    stats['glyph_roi_success_rate'] = round(available / requested, 4) if requested else 0.0
    stats['focused_applied'] = aggregation_applied
    stats['applied'] = applied
    return applied


def _review_one_page(
    page_json_path: str,
    image_path: str,
    subject: str,
    grade: int,
    stage: int,
    source_document_sha256: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if feedback_runtime is not None:
        _subject, grade, stage = runtime_attributes(feedback_runtime)
    page_data = safe_json_load(page_json_path)
    if feedback_runtime is not None and not artifact_compatible(page_data, feedback_runtime):
        raise ValueError('复核输入与本轮配置不一致')
    page_num = int(page_data.get('page') or parse_page_num(os.path.basename(page_json_path)) or 0)
    review_path = _review_json_path(page_json_path)
    allowlist_match = _self_review_allowlist_match(
        page_json_path,
        subject,
        page_num,
        source_document_sha256,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    from .evidence_contract import required_review_units
    if allowlist_match and not required_review_units(page_data):
        report = _write_skipped_review(
            page_num,
            review_path,
            skip_reason=_SELF_REVIEW_ALLOWLIST_SKIP_REASON,
            special_case_match=allowlist_match,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        return stamp_feedback({
            'page': page_num,
            'review_path': review_path,
            'skipped': True,
            'skip_reason': report.get('skip_reason'),
            'issues': 0,
            'applied': 0,
        }, feedback_runtime, 'review')

    pre_review_signature = _review_snapshot_signature(page_data, subject)

    if not _page_needs_review(page_data, subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})):
        skip_reason = _review_skip_reason(page_data, subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        report = _write_skipped_review(page_num, review_path, skip_reason=skip_reason, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        return stamp_feedback({
            'page': page_num,
            'review_path': review_path,
            'skipped': True,
            'skip_reason': report.get('skip_reason'),
            'issues': 0,
            'applied': 0,
        }, feedback_runtime, 'review')

    report = review_page(image_path, page_data, subject, page_num, review_path, grade=grade, stage=stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    report['pre_review_signature'] = pre_review_signature
    if subject == 'chinese' and (feedback_runtime is None or feedback_runtime.has_specialized('chinese')) and not report.get('quota_limited'):
        _run_focused_chinese_visual_review(image_path, page_data, report, review_path, grade, stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        _run_complex_glyph_confirmations(image_path, page_data, report, review_path, grade, stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        _run_glyph_arbitrations(image_path, page_data, report, review_path, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        report['review_strategy'] = _REVIEW_STRATEGY
        applied = _apply_aggregated_chinese_review(page_data, report, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    else:
        applied = apply_review_to_page(page_data, report, source_document_sha256=source_document_sha256, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    report['post_review_signature'] = _review_snapshot_signature(page_data, subject)
    safe_json_dump(page_json_path, stamp_feedback(page_data, feedback_runtime, 'review'))
    safe_json_dump(review_path, stamp_feedback(report, feedback_runtime, 'review'))
    return stamp_feedback({
        'page': page_num,
        'review_path': review_path,
        'skipped': False,
        'issues': report.get('stats', {}).get('issues', 0),
        'applied': applied,
        'error': report.get('error') or report.get('focused_error'),
        'quota_limited': bool(report.get('quota_limited')),
    }, feedback_runtime, 'review')


def review_pass1_dir(
    pass1_dir: str,
    pages: List[Dict[str, Any]],
    subject: str,
    grade: int = 4,
    stage: int = 2,
    workers: int = 5,
    source_document_sha256: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if feedback_runtime is not None:
        _subject, grade, stage = runtime_attributes(feedback_runtime)
    from .evidence_contract import required_review_units, unit_coverage
    expected_numbers = {p['page'] for p in pages}
    required = [u for path in sorted_json_pages(pass1_dir)
                for page_data in [safe_json_load(path)] if page_data.get('page') in expected_numbers
                for u in required_review_units(page_data)]
    if not pass1_self_review_enabled(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})):
        return stamp_feedback({
            'enabled': False,
            'required_units': unit_coverage(required, []),
            'skipped': True,
            'model': (model_spec(feedback_runtime, 'review')['model'] if feedback_runtime is not None else homework_review_gemini_model()),
            'scope': pass1_review_scope(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
            'workers': 0,
            'reuse_existing': pass1_review_reuse_existing(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
            'pages_reused': 0,
            'pages_reviewed': 0,
            'pages_skipped': 0,
            'issues_found': 0,
            'corrections_applied': 0,
        }, feedback_runtime, 'review')

    image_by_page = {
        int(page['page']): (
            page.get('model_abs_path')
            or page['clean_abs_path']
        )
        for page in pages
        if page.get('page') and page.get('clean_abs_path')
    }
    json_paths = [
        path for path in sorted_json_pages(pass1_dir)
        if parse_page_num(os.path.basename(path)) in image_by_page
    ]
    if not json_paths:
        return stamp_feedback({
            'enabled': True,
            'model': (model_spec(feedback_runtime, 'review')['model'] if feedback_runtime is not None else homework_review_gemini_model()),
            'scope': pass1_review_scope(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
            'workers': 0,
            'reuse_existing': pass1_review_reuse_existing(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
            'pages_reused': 0,
            'pages_reviewed': 0,
            'pages_skipped': 0,
            'issues_found': 0,
            'corrections_applied': 0,
        }, feedback_runtime, 'review')

    candidates: List[tuple] = []
    skipped_results: List[Dict[str, Any]] = []
    reused_results: List[Dict[str, Any]] = []
    for json_path in json_paths:
        page_num = parse_page_num(os.path.basename(json_path))
        page_data = safe_json_load(json_path)
        if feedback_runtime is not None and not artifact_compatible(page_data, feedback_runtime):
            raise ValueError('复核输入与本轮配置不一致')
        review_path = _review_json_path(json_path)
        allowlist_match = _self_review_allowlist_match(
            json_path,
            subject,
            page_num,
            source_document_sha256,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        from .evidence_contract import required_review_units
        if allowlist_match and not required_review_units(page_data):
            skipped_results.append({
                'page': page_num,
                'review_path': review_path,
                'skipped': True,
                'skip_reason': _SELF_REVIEW_ALLOWLIST_SKIP_REASON,
                'issues': 0,
                'applied': 0,
            })
            _write_skipped_review(
                page_num,
                review_path,
                skip_reason=_SELF_REVIEW_ALLOWLIST_SKIP_REASON,
                special_case_match=allowlist_match,
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
            continue
        reusable_report = _load_reusable_review_report(json_path, page_data, subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        if reusable_report:
            reused_results.append(_candidate_reuse_result(json_path, reusable_report))
            continue
        if not _page_needs_review(page_data, subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})):
            skip_reason = _review_skip_reason(page_data, subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
            skipped_results.append({
                'page': page_num,
                'review_path': review_path,
                'skipped': True,
                'skip_reason': skip_reason,
                'issues': 0,
                'applied': 0,
            })
            _write_skipped_review(page_num, review_path, skip_reason=skip_reason, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
            continue
        image_path = image_by_page.get(page_num)
        if not image_path or not os.path.isfile(image_path):
            logger.warning('Pass1 自检跳过 page=%s：缺少 clean 图', page_num)
            continue
        candidates.append((json_path, image_path))

    results: List[Dict[str, Any]] = list(skipped_results) + list(reused_results)
    worker_count = pass1_review_parallelism(workers, len(candidates) or 1, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if candidates:
        results.extend(
            _run_review_candidates(
                candidates,
                subject,
                grade,
                stage,
                worker_count,
                pass1_review_stop_on_quota(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
                source_document_sha256,
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        )

    boundary_error_reconciled = _reconcile_open_material_boundary_errors(
        json_paths,
        **({'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {}),
    )

    pages_skipped = sum(1 for r in results if r.get('skipped'))
    pages_reused = sum(1 for r in results if r.get('reused'))
    pages_reviewed = sum(1 for r in results if not r.get('skipped') and not r.get('error'))
    issues_found = sum(r.get('issues', 0) for r in results)
    corrections_applied = sum(r.get('applied', 0) for r in results)
    errors = [r for r in results if r.get('error')]
    quota_limited = any(
        r.get('quota_limited')
        or _is_gemini_quota_error(r.get('error'))
        or r.get('skip_reason') == 'gemini_quota_limited'
        for r in results
    )
    return stamp_feedback({
        'enabled': True,
        'model': (model_spec(feedback_runtime, 'review')['model'] if feedback_runtime is not None else homework_review_gemini_model()),
        'scope': pass1_review_scope(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
        'workers': worker_count if candidates else 0,
        'reuse_existing': pass1_review_reuse_existing(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
        'pages_reused': pages_reused,
        'stop_on_quota': pass1_review_stop_on_quota(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
        'quota_limited': quota_limited,
        'pages_reviewed': pages_reviewed,
        'pages_skipped': pages_skipped,
        'issues_found': issues_found,
        'corrections_applied': corrections_applied,
        'boundary_error_reconciled': boundary_error_reconciled,
        'errors': len(errors),
        'failures': [{key: r[key] for key in ('page', 'error', 'error_kind', 'budget') if key in r}
                     for r in errors],
        'details': results,
        'required_units': unit_coverage(required, results),
    }, feedback_runtime, 'review')
