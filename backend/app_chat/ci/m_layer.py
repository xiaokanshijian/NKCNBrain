"""
ci/m_layer.py — M 层模块：版面分析全流程（门控、规范化、多候选合并、验证、编排）

迁移来源：
  Phase 4.1 — 门控逻辑         continuous_image_service.py L2007-2315
  Phase 4.2 — 规范化/格式化    continuous_image_service.py L2405-2654
  Phase 4.3 — 多候选合并       continuous_image_service.py L2657-2912
  Phase 4.4 — 验证/补洞        continuous_image_service.py L2914-3134
"""

import os
import re
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from llm_langchain import util
from llm_langchain.pdf_ocr_utils import generate_layout_pdf, extract_layout_elements_from_txt, _draw_layout_on_image
from PIL import Image

from app_chat.ci.d_layer import _TAG_PATTERNS
from app_chat.ci._llm import (
    _call_m_layer_llm, _parse_llm_json,
    _call_qwen35_plus_m_layer_llm, _call_qwen35_m_layer_llm, _call_qwen_vl_flash_fast,
    _image_path_to_base64_url,
)
from app_chat.ci._context import _extract_ci_context_terms, _format_m_layer_context, _text_match_score
from app_chat.ci._utils import _safe_json_dump, _update_task
from app_chat.ci_prompts import (
    CI_M_LAYER_STRUCTURE_SYSTEM_PROMPT,
    CI_M_LAYER_STRUCTURE_USER_PROMPT_TEMPLATE,
    CI_M_LAYER_STRUCTURE_MERGE_SYSTEM_PROMPT,
    CI_M_LAYER_STRUCTURE_MERGE_USER_PROMPT_TEMPLATE,
    CI_M_LAYER_SUMMARY_SYSTEM_PROMPT,
    CI_M_LAYER_SUMMARY_USER_PROMPT_TEMPLATE,
    CI_M_LAYER_VERIFY_SYSTEM_PROMPT,
    CI_M_LAYER_VERIFY_USER_PROMPT_TEMPLATE,
    CI_M_LAYER_PATCH_SYSTEM_PROMPT,
    CI_M_LAYER_PATCH_USER_PROMPT_TEMPLATE,
)

# ── M 层超时与输入限制常量（from continuous_image_service.py L95-98）──────────────
_D_OCR_GATE_TIMEOUT = 8
_D_OCR_GATE_MAX_OCR_CHARS = 700
_D_OCR_GATE_MAX_CONTEXT_CHARS = 1200
_M_LAYER_FLAGGED_TIMEOUT = 75

# ── M 层规范化常量（from continuous_image_service.py L2406-2409）─────────────────
_M_CONTINUITY_TYPES = {'顺承', '延续', '补充', '修正', '批注', '主题跳转', '中断', '首图', '未知'}
_M_GENERIC_REGION_CONTENT = ('存在手写', '有手写', '内容待确认', '字迹不清', '信息不足', '无法识别')
_M_GENERIC_MAIN_CONTENT = ('存在手写内容', '图片主要包含', '信息不足', '无法准确判断')
_M_TEXT_ANCHOR_REGION_TYPES = ('标题区', '列表区', '图示区', '流程区', '主体区')


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4.1 — M 层门控逻辑
# from continuous_image_service.py L2007-2315
# ══════════════════════════════════════════════════════════════════════════════

def _build_m_context_probe_text(notebook_ctx: Optional[Dict[str, Any]]) -> str:
    # from continuous_image_service.py L2007-2046
    if not notebook_ctx:
        return ''

    parts: List[str] = []
    scene_name = (notebook_ctx.get('scene_name') or '').strip()
    sub_scene_name = (notebook_ctx.get('sub_scene_name') or '').strip()
    notebook_description = (notebook_ctx.get('notebook_description') or '').strip()
    scene_summary = (notebook_ctx.get('scene_summary') or '').strip()

    if scene_name:
        parts.append(f'场景: {scene_name}')
    if sub_scene_name:
        parts.append(f'子场景: {sub_scene_name}')
    if notebook_description:
        parts.append(f'本子说明: {notebook_description[:220]}')
    if scene_summary:
        parts.append(f'场景摘要: {scene_summary[:260]}')

    doc_lines: List[str] = []
    for doc in (notebook_ctx.get('doc_summaries') or [])[:3]:
        file_name = (doc.get('file_name') or '').strip()
        summary = (doc.get('summary') or '').strip()
        if file_name or summary:
            doc_lines.append(f'- {file_name}: {summary[:180]}')
    if doc_lines:
        parts.append('文档摘要:\n' + '\n'.join(doc_lines))

    card_lines: List[str] = []
    for card in (notebook_ctx.get('card_summaries') or [])[:5]:
        title = (card.get('title') or '').strip()
        keywords = (card.get('keywords') or '').strip()
        preview = (card.get('preview') or '').strip()
        merged = ' | '.join([part for part in [title, f'关键词:{keywords}' if keywords else '', preview[:120]] if part])
        if merged:
            card_lines.append(f'- {merged}')
    if card_lines:
        parts.append('卡片摘要:\n' + '\n'.join(card_lines))

    return '\n\n'.join(parts)[:_D_OCR_GATE_MAX_CONTEXT_CHARS]


def _normalize_ocr_text_for_gate(text: str) -> str:
    # from continuous_image_service.py L2049-2055
    if not text:
        return ''
    cleaned = _TAG_PATTERNS.sub(' ', text)
    cleaned = re.sub(r'<\|.*?\|>', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def _extract_gate_terms(text: str, limit: int = 24) -> List[str]:
    # from continuous_image_service.py L2058-2067
    if not text:
        return []
    terms: List[str] = []
    for tok in re.findall(r'[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}', text.lower()):
        if tok not in terms:
            terms.append(tok)
        if len(terms) >= limit:
            break
    return terms


def _extract_gate_terms_with_duplicates(text: str, limit: int = 80) -> List[str]:
    # from continuous_image_service.py L2070-2073
    if not text:
        return []
    return re.findall(r'[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}', text.lower())[:limit]


def _build_gate_context_terms(notebook_ctx: Optional[Dict[str, Any]]) -> List[str]:
    # from continuous_image_service.py L2076-2104
    if not notebook_ctx:
        return []

    terms = _extract_ci_context_terms(None, notebook_ctx)
    for card in (notebook_ctx.get('card_summaries') or [])[:8]:
        card_text = ' '.join([
            card.get('title', '') or '',
            card.get('keywords', '') or '',
            (card.get('preview', '') or '')[:120],
        ])
        for tok in _extract_gate_terms(card_text, limit=12):
            if tok not in terms:
                terms.append(tok)
            if len(terms) >= 30:
                return terms[:30]

    for doc in (notebook_ctx.get('doc_summaries') or [])[:4]:
        doc_text = ' '.join([
            doc.get('file_name', '') or '',
            (doc.get('summary', '') or '')[:180],
        ])
        for tok in _extract_gate_terms(doc_text, limit=12):
            if tok not in terms:
                terms.append(tok)
            if len(terms) >= 30:
                return terms[:30]

    return terms[:30]


def _heuristic_meaningless_ocr(normalized_ocr: str) -> Tuple[bool, str]:
    # from continuous_image_service.py L2107-2141
    if not normalized_ocr:
        return False, 'empty_ocr'

    info_tokens = _extract_gate_terms(normalized_ocr, limit=20)
    repeated_tokens = _extract_gate_terms_with_duplicates(normalized_ocr, limit=80)
    semantic_chars = len(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]', normalized_ocr))
    garbled_chars = len(re.findall(r'[□◆◇■△▽○●\ufffd]', normalized_ocr))
    garble_ratio = garbled_chars / max(len(normalized_ocr), 1)
    token_counter = Counter(repeated_tokens)
    unique_token_count = len(token_counter)
    total_token_count = len(repeated_tokens)
    top_token_ratio = (max(token_counter.values()) / total_token_count) if total_token_count else 0.0
    diversity_ratio = (unique_token_count / total_token_count) if total_token_count else 1.0

    if semantic_chars < 8 or not info_tokens:
        return True, 'heuristic_semantic_too_short'
    if garble_ratio >= 0.35:
        return True, 'heuristic_garbled_text'
    if len(info_tokens) <= 1 and semantic_chars < 20:
        return True, 'heuristic_sparse_tokens'
    if total_token_count >= 6 and top_token_ratio >= 0.65:
        return True, 'heuristic_repetitive_tokens'
    if total_token_count >= 8 and unique_token_count <= 2:
        return True, 'heuristic_extreme_low_diversity'
    if total_token_count >= 10 and diversity_ratio <= 0.35:
        return True, 'heuristic_low_diversity_text'
    repeated_phrase = re.search(r'([\u4e00-\u9fffA-Za-z0-9_]{2,8})(?:\s*\1){3,}', normalized_ocr)
    if repeated_phrase:
        return True, 'heuristic_repeated_phrase'
    clauses = [seg.strip() for seg in re.split(r'[，,。；;、\n]+', normalized_ocr) if seg.strip()]
    short_clause_ratio = (sum(1 for seg in clauses if len(seg) <= 3) / len(clauses)) if clauses else 0.0
    if len(clauses) >= 5 and short_clause_ratio >= 0.6 and diversity_ratio <= 0.45:
        return True, 'heuristic_fragmented_babble'
    return False, 'heuristic_ocr_has_signal'


def _heuristic_unrelated_to_context(normalized_ocr: str, notebook_ctx: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    # from continuous_image_service.py L2144-2156
    context_terms = _build_gate_context_terms(notebook_ctx)
    if not context_terms:
        return False, 'no_context_terms'

    match_score = _text_match_score(normalized_ocr, context_terms)
    if match_score > 0:
        return False, 'heuristic_context_overlap'

    ocr_terms = _extract_gate_terms(normalized_ocr, limit=12)
    if len(ocr_terms) <= 3:
        return True, 'heuristic_no_context_overlap'
    return False, 'heuristic_need_llm_for_relevance'


def _llm_gate_judge(normalized_ocr: str, context_probe: str,
                    need_meaningless: bool, need_unrelated: bool) -> Dict[str, Any]:
    # from continuous_image_service.py L2159-2195
    if not need_meaningless and not need_unrelated:
        return {}

    system_prompt = (
        '你是连续图片理解框架中的OCR输入门控器。\n'
        '任务：快速判断OCR最终文本是否"完全无意义"，以及/或者是否与将注入M层的上下文"完全不相关"。\n'
        '判定必须极其保守：只有当该条件明确成立时才返回 true，否则返回 false。\n'
        '当判断"完全无意义"时，要特别留意这些情形：整段几乎都在重复同一词汇或短语、文本像乱码或拼接残片、句子前后颠倒混乱、虽然有字词但整体不知所云、像胡言乱语或无语义堆砌。\n'
        '即使表面上有不少字，只要整体无法稳定传达可理解信息，也可以判为 meaningless_ocr=true。\n'
        '但如果文本虽有噪声，仍能看出明确主题、对象、动作、术语或可用片段，则必须判 false。\n'
        '只输出JSON，不要输出额外说明。'
    )
    requested_fields = []
    if need_meaningless:
        requested_fields.append('  "meaningless_ocr": true/false')
    if need_unrelated:
        requested_fields.append('  "unrelated_to_context": true/false')
    requested_fields.append('  "reason": "不超过40字的简短原因"')

    user_text = (
        '请基于以下信息返回JSON：\n{\n'
        + ',\n'.join(requested_fields)
        + '\n}\n\n'
        f'【待判断OCR】\n{normalized_ocr[:_D_OCR_GATE_MAX_OCR_CHARS]}\n\n'
        f'【M层上下文摘要】\n{context_probe}'
    )

    raw = _call_m_layer_llm(
        system_prompt,
        [{'type': 'text', 'text': user_text}],
        timeout=_D_OCR_GATE_TIMEOUT,
        primary_attempts=1,
        fallback_attempts=0,
    )
    return _parse_llm_json(raw or '', {}) if raw else {}


def _build_m_layer_input_policy(gate_result: Dict[str, Any], has_context: bool) -> Dict[str, Any]:
    # from continuous_image_service.py L2198-2224
    meaningless_ocr = bool(gate_result.get('meaningless_ocr', False))
    unrelated_to_context = bool(gate_result.get('unrelated_to_context', False))
    prefer_qwen35_plus_for_m = meaningless_ocr or unrelated_to_context
    ocr_char_limit = 600
    input_hint = ''

    if meaningless_ocr and unrelated_to_context:
        ocr_char_limit = 0
        input_hint = '当前D层OCR已被判定为既无意义又与上下文无关，本轮不要依赖OCR文本，请以图片视觉内容和上下文为准。'
    elif meaningless_ocr and not unrelated_to_context:
        ocr_char_limit = 50
        if has_context:
            input_hint = '当前D层OCR与上下文可能相关，但文本本身疑似重复、混乱或缺乏稳定语义。仅提供最多50字符OCR片段作为弱线索，请优先结合图片视觉与上下文，自主判断应以OCR还是上下文为准。'
        else:
            input_hint = '当前D层OCR疑似重复、混乱或缺乏稳定语义。仅提供最多50字符OCR片段作为弱线索，请优先依据图片视觉判断是否采信OCR。'
    elif unrelated_to_context:
        if has_context:
            input_hint = '当前D层OCR文本有一定可读性，但与本子上下文疑似不一致。请结合图片视觉，自主判断应以OCR还是上下文为准；若两者冲突，以更符合图片实际内容的一侧为准。'
        else:
            input_hint = '当前D层OCR虽可读，但缺乏可参照上下文。请结合图片视觉判断OCR是否可信。'

    return {
        'prefer_qwen35_plus_for_m': prefer_qwen35_plus_for_m,
        'ocr_char_limit': ocr_char_limit,
        'input_hint': input_hint,
    }


def _should_skip_d_text_for_m(ocr_text_for_m: str, notebook_ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    # from continuous_image_service.py L2227-2315
    result = {
        'skip_d_text': False,
        'meaningless_ocr': False,
        'unrelated_to_context': False,
        'reason': '',
        'judge_model': 'qwen3.5-flash',
        'prefer_qwen35_plus_for_m': False,
        'ocr_char_limit': 600,
        'input_hint': '',
    }

    normalized_ocr = _normalize_ocr_text_for_gate(ocr_text_for_m)
    if not normalized_ocr:
        result['reason'] = 'OCR为空，跳过门控。'
        return result

    context_probe = _build_m_context_probe_text(notebook_ctx)
    has_context = bool(context_probe)

    heuristic_meaningless, meaningless_reason = _heuristic_meaningless_ocr(normalized_ocr)
    if has_context:
        heuristic_unrelated, unrelated_reason = _heuristic_unrelated_to_context(normalized_ocr, notebook_ctx)
    else:
        heuristic_unrelated, unrelated_reason = False, 'no_context'
    need_llm_meaningless = not heuristic_meaningless
    need_llm_unrelated = has_context and not heuristic_unrelated

    llm_reason = ''
    llm_parsed = _llm_gate_judge(
        normalized_ocr,
        context_probe,
        need_meaningless=need_llm_meaningless,
        need_unrelated=need_llm_unrelated,
    ) if (need_llm_meaningless or need_llm_unrelated) else {}

    if need_llm_meaningless:
        if 'meaningless_ocr' in llm_parsed:
            meaningless_ocr = bool(llm_parsed.get('meaningless_ocr', False))
        else:
            meaningless_ocr = False
        meaningless_reason_final = 'llm_meaningless_true' if meaningless_ocr else 'llm_meaningless_false'
    else:
        meaningless_ocr = True
        meaningless_reason_final = meaningless_reason

    if need_llm_unrelated:
        if 'unrelated_to_context' in llm_parsed:
            unrelated_to_context = bool(llm_parsed.get('unrelated_to_context', False))
        else:
            unrelated_to_context = False
        unrelated_reason_final = 'llm_unrelated_true' if unrelated_to_context else 'llm_unrelated_false'
    else:
        unrelated_to_context = True
        unrelated_reason_final = unrelated_reason

    if llm_parsed:
        llm_reason = str(llm_parsed.get('reason', '') or '').strip()[:40]

    judge_parts: List[str] = []
    judge_parts.append('heuristic:meaningless' if not need_llm_meaningless else 'llm:meaningless')
    if has_context:
        judge_parts.append('heuristic:unrelated' if not need_llm_unrelated else 'llm:unrelated')
    else:
        judge_parts.append('skip:unrelated(no_context)')
    combined_reason_parts = [meaningless_reason_final, unrelated_reason_final]
    if llm_reason:
        combined_reason_parts.append(llm_reason)

    input_policy = _build_m_layer_input_policy(
        {
            'meaningless_ocr': meaningless_ocr,
            'unrelated_to_context': unrelated_to_context,
        },
        has_context=has_context,
    )

    result.update({
        'skip_d_text': input_policy['ocr_char_limit'] <= 0,
        'meaningless_ocr': meaningless_ocr,
        'unrelated_to_context': unrelated_to_context,
        'reason': '; '.join(part for part in combined_reason_parts if part)[:120]
                  or ('OCR无意义且与上下文无关，已跳过。' if meaningless_ocr and unrelated_to_context else 'OCR保留用于M层。'),
        'judge_model': ' + '.join(judge_parts),
        'prefer_qwen35_plus_for_m': input_policy['prefer_qwen35_plus_for_m'],
        'ocr_char_limit': input_policy['ocr_char_limit'],
        'input_hint': input_policy['input_hint'],
    })
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4.2 — M 层规范化/格式化
# from continuous_image_service.py L2423-2654
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_region_text(value: Any, limit: int) -> str:
    # from continuous_image_service.py L2423-2424
    return str(value or '').strip()[:limit]


def _normalize_region_list(value: Any, item_limit: int = 6, text_limit: int = 80) -> List[str]:
    # from continuous_image_service.py L2427-2442
    items: List[str] = []
    raw_items: List[Any]
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = re.split(r'[；;\n]+', value)
    else:
        raw_items = []
    for item in raw_items:
        text = _normalize_region_text(item, text_limit)
        if text:
            items.append(text)
        if len(items) >= item_limit:
            break
    return items


def _normalize_layout_regions(raw_regions: Any) -> List[Dict[str, Any]]:
    # from continuous_image_service.py L2445-2489
    normalized: List[Dict[str, Any]] = []
    if not isinstance(raw_regions, list):
        return normalized
    for item in raw_regions:
        if isinstance(item, dict):
            region = {
                'type': _normalize_region_text(item.get('type', ''), 20),
                'position': _normalize_region_text(item.get('position', ''), 20),
                'spatial_anchor': _normalize_region_text(item.get('spatial_anchor', ''), 20),
                'content': _normalize_region_text(item.get('content', ''), 120),
                'key_elements': _normalize_region_list(item.get('key_elements', []), item_limit=8, text_limit=60),
                'visual_relations': _normalize_region_list(item.get('visual_relations', []), item_limit=6, text_limit=80),
                'direction_notes': _normalize_region_text(item.get('direction_notes', ''), 120),
                'relative_layout': _normalize_region_text(item.get('relative_layout', ''), 120),
                'size_notes': _normalize_region_text(item.get('size_notes', ''), 80),
                'shape_notes': _normalize_region_text(item.get('shape_notes', ''), 80),
                'uncertain_details': _normalize_region_list(item.get('uncertain_details', []), item_limit=6, text_limit=80),
                'evidence_level': _normalize_region_text(item.get('evidence_level', ''), 10).lower(),
            }
        elif isinstance(item, str):
            region = {
                'type': '其它',
                'position': '',
                'spatial_anchor': '',
                'content': item.strip()[:120],
                'key_elements': [],
                'visual_relations': [],
                'direction_notes': '',
                'relative_layout': '',
                'size_notes': '',
                'shape_notes': '',
                'uncertain_details': [],
                'evidence_level': 'low',
            }
        else:
            continue
        if not region['content']:
            continue
        if not region['type']:
            region['type'] = '其它'
        if not region['evidence_level']:
            region['evidence_level'] = 'medium'
        normalized.append(region)
    return normalized


def _normalize_continuity_with_prev(raw_value: Any, is_first: bool) -> Dict[str, str]:
    # from continuous_image_service.py L2492-2504
    default_type = '首图' if is_first else '未知'
    default = {'type': default_type, 'reason': '', 'key_bridge': ''}
    if not isinstance(raw_value, dict):
        return default
    relation_type = str(raw_value.get('type', '') or '').strip()
    if relation_type not in _M_CONTINUITY_TYPES:
        relation_type = default_type
    return {
        'type': relation_type,
        'reason': str(raw_value.get('reason', '') or '').strip()[:40],
        'key_bridge': str(raw_value.get('key_bridge', '') or '').strip()[:60],
    }


def _format_layout_regions_for_prompt(layout_regions: List[Dict[str, Any]]) -> str:
    # from continuous_image_service.py L2507-2540
    if not layout_regions:
        return '- （无可靠区域结果）'
    lines: List[str] = []
    for idx, region in enumerate(layout_regions, start=1):
        detail_parts: List[str] = []
        key_elements = region.get('key_elements', []) if isinstance(region.get('key_elements', []), list) else []
        visual_relations = region.get('visual_relations', []) if isinstance(region.get('visual_relations', []), list) else []
        uncertain_details = region.get('uncertain_details', []) if isinstance(region.get('uncertain_details', []), list) else []
        if key_elements:
            detail_parts.append(f"elements={','.join(key_elements[:6])}")
        if visual_relations:
            detail_parts.append(f"relations={';'.join(visual_relations[:4])}")
        if region.get('direction_notes'):
            detail_parts.append(f"direction={region.get('direction_notes')}")
        if region.get('relative_layout'):
            detail_parts.append(f"layout={region.get('relative_layout')}")
        if region.get('size_notes'):
            detail_parts.append(f"size={region.get('size_notes')}")
        if region.get('shape_notes'):
            detail_parts.append(f"shape={region.get('shape_notes')}")
        if uncertain_details:
            detail_parts.append(f"uncertain={';'.join(uncertain_details[:3])}")
        line = (
            f'- R{idx} | type={region.get("type", "") or "其它"} | '
            f'position={region.get("position", "") or "未标注"} | '
            f'spatial_anchor={region.get("spatial_anchor", "") or "未标注"} | '
            f'evidence={region.get("evidence_level", "") or "medium"} | '
            f'content={region.get("content", "") or "内容待确认"}'
        )
        if detail_parts:
            line += ' | ' + ' | '.join(detail_parts)
        lines.append(line)
    return '\n'.join(lines)


def _build_main_content_from_regions(layout_regions: List[Dict[str, Any]]) -> str:
    # from continuous_image_service.py L2543-2572
    if not layout_regions:
        return '当前页面的结构信息不足，暂无法生成稳定摘要。'
    snippets: List[str] = []
    for region in layout_regions[:6]:
        content = str(region.get('content', '') or '').strip()
        detail_parts: List[str] = []
        key_elements = region.get('key_elements', []) if isinstance(region.get('key_elements', []), list) else []
        visual_relations = region.get('visual_relations', []) if isinstance(region.get('visual_relations', []), list) else []
        if key_elements:
            detail_parts.append('关键词/符号：' + '、'.join(key_elements[:4]))
        if visual_relations:
            detail_parts.append('关系：' + '；'.join(visual_relations[:2]))
        if region.get('direction_notes'):
            detail_parts.append('方向：' + str(region.get('direction_notes')))
        if region.get('relative_layout'):
            detail_parts.append('相对位置：' + str(region.get('relative_layout')))
        if region.get('size_notes'):
            detail_parts.append('大小：' + str(region.get('size_notes')))
        if region.get('shape_notes'):
            detail_parts.append('形状：' + str(region.get('shape_notes')))
        snippet = content
        if detail_parts:
            snippet = f"{content}（{'；'.join(detail_parts)}）" if content else '；'.join(detail_parts)
        if snippet:
            snippets.append(snippet)
    if not snippets:
        return '当前页面存在多个区域，但内容细节不足，建议结合原图复核。'
    merged = '；'.join(snippets[:6])
    return f'页面主要包含以下结构与内容：{merged}。'


def _normalize_m_verification(raw_value: Any) -> Dict[str, Any]:
    # from continuous_image_service.py L2575-2636
    if not isinstance(raw_value, dict):
        return {
            'verified_regions': [],
            'uncertain_regions': [],
            'missing_regions': [],
            'summary_coverage': 'weak',
            'overall_verdict': 'weak',
        }

    verified_regions: List[str] = []
    for item in raw_value.get('verified_regions', []) if isinstance(raw_value.get('verified_regions', []), list) else []:
        region_id = str(item or '').strip()[:10]
        if region_id:
            verified_regions.append(region_id)

    uncertain_regions: List[Dict[str, str]] = []
    raw_uncertain = raw_value.get('uncertain_regions', [])
    if isinstance(raw_uncertain, list):
        for item in raw_uncertain:
            if not isinstance(item, dict):
                continue
            region_id = str(item.get('region_id', '') or '').strip()[:10]
            issue = str(item.get('issue', '') or '').strip()[:20]
            reason = str(item.get('reason', '') or '').strip()[:40]
            if region_id or issue or reason:
                uncertain_regions.append({
                    'region_id': region_id,
                    'issue': issue,
                    'reason': reason,
                })

    missing_regions: List[Dict[str, str]] = []
    raw_missing = raw_value.get('missing_regions', [])
    if isinstance(raw_missing, list):
        for item in raw_missing:
            if not isinstance(item, dict):
                continue
            region_type = str(item.get('type', '') or '').strip()[:20]
            position = str(item.get('position', '') or '').strip()[:20]
            reason = str(item.get('reason', '') or '').strip()[:40]
            if region_type or position or reason:
                missing_regions.append({
                    'type': region_type,
                    'position': position,
                    'reason': reason,
                })

    summary_coverage = str(raw_value.get('summary_coverage', '') or '').strip().lower()
    if summary_coverage not in {'full', 'partial', 'weak'}:
        summary_coverage = 'weak'
    overall_verdict = str(raw_value.get('overall_verdict', '') or '').strip().lower()
    if overall_verdict not in {'reliable', 'needs_patch', 'weak'}:
        overall_verdict = 'weak'

    return {
        'verified_regions': verified_regions,
        'uncertain_regions': uncertain_regions,
        'missing_regions': missing_regions,
        'summary_coverage': summary_coverage,
        'overall_verdict': overall_verdict,
    }


def _structure_candidate_instructions(candidate_mode: str) -> str:
    # from continuous_image_service.py L2639-2654
    mapping = {
        'coverage': (
            '本轮重点是版面区域完整性。优先确保不要漏掉主要区域；若同一区域内部细节看不清，允许保守，但不要因此漏掉整个区域。'
        ),
        'relations': (
            '本轮重点是图示关系细节。请优先补充圈画、箭头、连线、节点关系、from/to 和方向信息；若方向看不清，明确写方向待确认。'
        ),
        'geometry': (
            '本轮重点是几何布局。请优先补充相对位置、相对大小、几何形状、环绕/并列/上下左右分布等版面事实。'
        ),
        'characters': (
            '由于D层OCR已判定无意义，本轮重点是高价值文本锚点的视觉字符恢复。请优先对标题大字、列表关键词、圈内词、流程节点词、箭头旁短词、关键公式符号做逐字或逐符号保真抄录；看不清时明确写待确认，不要脑补整页全文。'
        ),
    }
    return mapping.get(candidate_mode, '')


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4.5a — M 层多模态内容构建（提前迁移，被 4.3/4.4/4.5 共享）
# from continuous_image_service.py L2412-2420
# ══════════════════════════════════════════════════════════════════════════════

def _build_m_multimodal_content(text: str, prev_asset_abs: str = '', current_asset_abs: str = '',
                                support_asset_abs: str = '') -> List[Any]:
    # from continuous_image_service.py L2412-2420
    user_content: List[Any] = [{'type': 'text', 'text': text}]
    for asset_abs in [prev_asset_abs, current_asset_abs, support_asset_abs]:
        if asset_abs:
            b64 = _image_path_to_base64_url(asset_abs)
            if b64:
                user_content.append({'type': 'image_url', 'image_url': {'url': b64}})
    return user_content


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4.3 — M 层多候选合并
# from continuous_image_service.py L2657-2912
# ══════════════════════════════════════════════════════════════════════════════

def _run_m_structure_candidate(structure_prompt: str, unit: Dict[str, Any], prev_asset_abs: str,
                               support_asset_abs: str, timeout: int, prefer_qwen35_plus: bool,
                               candidate_mode: str) -> Dict[str, Any]:
    # from continuous_image_service.py L2657-2677
    candidate_prompt = structure_prompt
    candidate_note = _structure_candidate_instructions(candidate_mode)
    if candidate_note:
        candidate_prompt += f'\n\n## 本轮并行观察重点\n{candidate_note}'
    raw = _call_m_layer_llm(
        CI_M_LAYER_STRUCTURE_SYSTEM_PROMPT,
        _build_m_multimodal_content(candidate_prompt, prev_asset_abs, unit['asset_abs_path'], support_asset_abs),
        timeout=timeout,
        prefer_qwen35_plus=prefer_qwen35_plus,
    )
    parsed = _parse_llm_json(raw, {}) if raw else {}
    layout_regions = _normalize_layout_regions(parsed.get('layout_regions', []))
    reading_order = str(parsed.get('reading_order', '') or '').strip()
    return {
        'mode': candidate_mode,
        'layout_regions': layout_regions,
        'reading_order': reading_order,
    }


def _region_text_tokens(region: Dict[str, Any]) -> List[str]:
    # from continuous_image_service.py L2680-2693
    tokens: List[str] = []
    content = str(region.get('content', '') or '').strip()
    if content and content not in _M_GENERIC_REGION_CONTENT:
        tokens.extend(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]{1,12}', content))
    for item in region.get('key_elements', []) if isinstance(region.get('key_elements', []), list) else []:
        text = str(item or '').strip()
        if text:
            tokens.append(text)
    unique_tokens: List[str] = []
    for token in tokens:
        if token and token not in unique_tokens:
            unique_tokens.append(token)
    return unique_tokens[:8]


def _regions_should_merge(region_a: Dict[str, Any], region_b: Dict[str, Any]) -> bool:
    # from continuous_image_service.py L2696-2713
    type_a = str(region_a.get('type', '') or '')
    type_b = str(region_b.get('type', '') or '')
    if type_a != type_b:
        return False
    anchor_a = str(region_a.get('spatial_anchor', '') or '')
    anchor_b = str(region_b.get('spatial_anchor', '') or '')
    position_a = str(region_a.get('position', '') or '')
    position_b = str(region_b.get('position', '') or '')
    same_anchor = anchor_a and anchor_b and anchor_a == anchor_b
    same_position = position_a and position_b and position_a == position_b
    if not same_anchor and not same_position:
        return False
    tokens_a = set(_region_text_tokens(region_a))
    tokens_b = set(_region_text_tokens(region_b))
    if tokens_a and tokens_b and tokens_a.isdisjoint(tokens_b) and len(tokens_a | tokens_b) >= 4:
        return False
    return True


def _region_detail_score(region: Dict[str, Any]) -> int:
    # from continuous_image_service.py L2716-2728
    score = 0
    if str(region.get('content', '') or '').strip() and str(region.get('content', '') or '').strip() not in _M_GENERIC_REGION_CONTENT:
        score += 2
    score += len(region.get('key_elements', []) if isinstance(region.get('key_elements', []), list) else []) * 2
    score += len(region.get('visual_relations', []) if isinstance(region.get('visual_relations', []), list) else []) * 2
    for field in ('direction_notes', 'relative_layout', 'size_notes', 'shape_notes'):
        if str(region.get(field, '') or '').strip():
            score += 2
    score += len(region.get('uncertain_details', []) if isinstance(region.get('uncertain_details', []), list) else [])
    evidence = str(region.get('evidence_level', '') or '').lower()
    score += {'low': 0, 'medium': 1, 'high': 2}.get(evidence, 0)
    return score


def _merge_string_field(primary: str, candidate: str) -> str:
    # from continuous_image_service.py L2731-2742
    primary = str(primary or '').strip()
    candidate = str(candidate or '').strip()
    if not primary:
        return candidate
    if not candidate:
        return primary
    if primary in _M_GENERIC_REGION_CONTENT and candidate not in _M_GENERIC_REGION_CONTENT:
        return candidate
    if len(candidate) > len(primary) and primary in candidate:
        return candidate
    return primary if len(primary) >= len(candidate) else candidate


def _merge_list_field(primary: Any, candidate: Any, limit: int) -> List[str]:
    # from continuous_image_service.py L2745-2753
    merged: List[str] = []
    for value in list(primary or []) + list(candidate or []):
        text = str(value or '').strip()
        if text and text not in merged:
            merged.append(text)
        if len(merged) >= limit:
            break
    return merged


def _merge_region_records(regions: List[Dict[str, Any]]) -> Dict[str, Any]:
    # from continuous_image_service.py L2756-2791
    merged = dict(regions[0])
    support_count = len(regions)
    for region in regions[1:]:
        merged['content'] = _merge_string_field(merged.get('content', ''), region.get('content', ''))
        merged['direction_notes'] = _merge_string_field(merged.get('direction_notes', ''), region.get('direction_notes', ''))
        merged['relative_layout'] = _merge_string_field(merged.get('relative_layout', ''), region.get('relative_layout', ''))
        merged['size_notes'] = _merge_string_field(merged.get('size_notes', ''), region.get('size_notes', ''))
        merged['shape_notes'] = _merge_string_field(merged.get('shape_notes', ''), region.get('shape_notes', ''))
        merged['key_elements'] = _merge_list_field(merged.get('key_elements', []), region.get('key_elements', []), 8)
        merged['visual_relations'] = _merge_list_field(merged.get('visual_relations', []), region.get('visual_relations', []), 6)
        merged['uncertain_details'] = _merge_list_field(merged.get('uncertain_details', []), region.get('uncertain_details', []), 6)
        if str(merged.get('position', '') or '').strip() == '' and str(region.get('position', '') or '').strip():
            merged['position'] = region.get('position', '')
        if str(merged.get('spatial_anchor', '') or '').strip() == '' and str(region.get('spatial_anchor', '') or '').strip():
            merged['spatial_anchor'] = region.get('spatial_anchor', '')
    content_values = [str(region.get('content', '') or '').strip() for region in regions if str(region.get('content', '') or '').strip()]
    unique_contents = []
    for value in content_values:
        if value not in unique_contents:
            unique_contents.append(value)
    if len(unique_contents) > 1:
        merged['uncertain_details'] = _merge_list_field(
            merged.get('uncertain_details', []),
            ['候选间文本细节存在冲突'],
            6,
        )
    evidence_levels = [str(region.get('evidence_level', '') or 'medium').lower() for region in regions]
    max_level = max(({'low': 1, 'medium': 2, 'high': 3}.get(level, 2) for level in evidence_levels), default=2)
    if support_count >= 3:
        merged['evidence_level'] = 'high' if max_level >= 2 else 'medium'
    elif support_count == 2:
        merged['evidence_level'] = 'high' if max_level >= 3 else 'medium'
    else:
        merged['evidence_level'] = 'medium' if max_level >= 2 else 'low'
    return merged


def _merge_m_structure_candidates(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    # from continuous_image_service.py L2794-2840
    valid_candidates = [item for item in candidates if item.get('layout_regions')]
    if not valid_candidates:
        return {'layout_regions': [], 'reading_order': '', 'candidate_count': 0, 'merged_region_count': 0}

    region_groups: List[List[Dict[str, Any]]] = []
    for candidate in valid_candidates:
        for region in candidate.get('layout_regions', []):
            if not isinstance(region, dict):
                continue
            matched_group: Optional[List[Dict[str, Any]]] = None
            for group in region_groups:
                if _regions_should_merge(group[0], region):
                    matched_group = group
                    break
            if matched_group is None:
                region_groups.append([region])
            else:
                matched_group.append(region)

    merged_regions = [_merge_region_records(group) for group in region_groups]
    anchor_order = {
        'upper_left': 0, 'upper_center': 1, 'upper_right': 2,
        'center_left': 3, 'center': 4, 'center_right': 5,
        'lower_left': 6, 'lower_center': 7, 'lower_right': 8,
        'margin': 9,
    }
    merged_regions.sort(
        key=lambda region: (
            anchor_order.get(str(region.get('spatial_anchor', '') or ''), 99),
            -_region_detail_score(region),
            str(region.get('type', '') or ''),
        )
    )

    reading_orders = [str(item.get('reading_order', '') or '').strip() for item in valid_candidates if str(item.get('reading_order', '') or '').strip()]
    reading_order = ''
    if reading_orders:
        counts = Counter(reading_orders)
        reading_order = max(reading_orders, key=lambda value: (counts[value], len(value)))

    return {
        'layout_regions': merged_regions,
        'reading_order': reading_order,
        'candidate_count': len(valid_candidates),
        'merged_region_count': len(merged_regions),
    }


def _format_structure_candidates_for_merge(candidates: List[Dict[str, Any]]) -> str:
    # from continuous_image_service.py L2843-2856
    if not candidates:
        return '（无候选）'
    parts: List[str] = []
    for idx, candidate in enumerate(candidates, start=1):
        mode = str(candidate.get('mode', '') or f'candidate_{idx}')
        regions = candidate.get('layout_regions', []) if isinstance(candidate.get('layout_regions', []), list) else []
        reading_order = str(candidate.get('reading_order', '') or '').strip() or '未标注'
        parts.append(
            f'### 候选{idx} | mode={mode}\n'
            f'{_format_layout_regions_for_prompt(regions)}\n'
            f'- reading_order={reading_order}'
        )
    return '\n\n'.join(parts)


def _call_structure_merge_with_fallback(system_prompt: str, user_content: list,
                                        timeout: int) -> Tuple[Optional[str], str]:
    # from continuous_image_service.py L2859-2886
    qwen35_plus_raw = _call_qwen35_plus_m_layer_llm(system_prompt, user_content, timeout, attempts=1)
    if qwen35_plus_raw:
        parsed = _parse_llm_json(qwen35_plus_raw, {})
        if isinstance(parsed, dict) and (parsed.get('layout_regions') or parsed.get('reading_order')):
            return qwen35_plus_raw, 'qwen35_plus'
        print('[ci_m_layer] qwen3.5-plus 结构合并返回不可用JSON，降级到 qwen3.5-flash')
    else:
        print('[ci_m_layer] qwen3.5-plus 结构合并无响应，降级到 qwen3.5-flash')

    qwen35_raw = _call_qwen35_m_layer_llm(system_prompt, user_content, timeout, attempts=1)
    if qwen35_raw:
        parsed = _parse_llm_json(qwen35_raw, {})
        if isinstance(parsed, dict) and (parsed.get('layout_regions') or parsed.get('reading_order')):
            return qwen35_raw, 'qwen35_flash'
        print('[ci_m_layer] qwen3.5-flash 结构合并返回不可用JSON，降级到 qwen3-vl-flash')
    else:
        print('[ci_m_layer] qwen3.5-flash 结构合并无响应，降级到 qwen3-vl-flash')

    qwen_vl_raw = _call_qwen_vl_flash_fast(system_prompt, user_content, timeout)
    if qwen_vl_raw:
        parsed = _parse_llm_json(qwen_vl_raw, {})
        if isinstance(parsed, dict) and (parsed.get('layout_regions') or parsed.get('reading_order')):
            return qwen_vl_raw, 'qwen3_vl_flash'
        print('[ci_m_layer] qwen3-vl-flash 结构合并返回不可用JSON')

    return None, ''


def _merge_m_structure_candidates_with_claude(current_filename: str, prev_filename: str,
                                              candidates: List[Dict[str, Any]], prev_asset_abs: str,
                                              current_asset_abs: str, support_asset_abs: str,
                                              timeout: int, meaningless_ocr: bool) -> Dict[str, Any]:
    # from continuous_image_service.py L2889-2911
    candidate_sections = _format_structure_candidates_for_merge(candidates)
    user_prompt = CI_M_LAYER_STRUCTURE_MERGE_USER_PROMPT_TEMPLATE.format(
        current_filename=current_filename,
        prev_filename=prev_filename or '（无，当前图为首图）',
        ocr_status='无意义，需重点关注高价值文本锚点' if meaningless_ocr else '可作为弱参考，不要求字符候选优先',
        candidate_sections=candidate_sections,
    )
    raw, merge_strategy = _call_structure_merge_with_fallback(
        CI_M_LAYER_STRUCTURE_MERGE_SYSTEM_PROMPT,
        _build_m_multimodal_content(user_prompt, prev_asset_abs, current_asset_abs, support_asset_abs),
        timeout,
    )
    parsed = _parse_llm_json(raw, {}) if raw else {}
    return {
        'layout_regions': _normalize_layout_regions(parsed.get('layout_regions', [])),
        'reading_order': str(parsed.get('reading_order', '') or '').strip(),
        'candidate_count': len(candidates),
        'merge_strategy': merge_strategy,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4.4 — M 层验证/补洞
# from continuous_image_service.py L2914-3134
# ══════════════════════════════════════════════════════════════════════════════

def _run_m_layer_verification(unit: Dict[str, Any], prev_section: Optional[Dict[str, Any]],
                              context_section: str, ocr_reference: str,
                              analyzed: Dict[str, Any], input_hint: str,
                              prefer_qwen35_plus: bool, timeout: int,
                              meaningless_ocr: bool = False,
                              support_asset_abs: str = '') -> Dict[str, Any]:
    # from continuous_image_service.py L2914-2948
    prev_filename = prev_section.get('source_file', '') if prev_section else ''
    prev_asset_abs = prev_section.get('_asset_abs_path', '') if prev_section else ''
    continuity = analyzed.get('continuity_with_prev', {}) if isinstance(analyzed.get('continuity_with_prev', {}), dict) else {}
    verify_prompt = CI_M_LAYER_VERIFY_USER_PROMPT_TEMPLATE.format(
        current_filename=unit['source_file'],
        prev_filename=prev_filename or '（无，当前图为首图）',
        structure_section=_format_layout_regions_for_prompt(analyzed.get('layout_regions', [])) + f'\n- reading_order={analyzed.get("reading_order", "") or "未标注"}',
        main_content=analyzed.get('main_content', '') or '（无）',
        handwriting_printing_relation=analyzed.get('handwriting_printing_relation', '') or '（无）',
        annotation_relation=analyzed.get('annotation_relation', '') or '（无）',
        continuity_type=continuity.get('type', '') or '（无）',
        continuity_reason=continuity.get('reason', '') or '（无）',
        continuity_bridge=continuity.get('key_bridge', '') or '（无）',
        ocr_reference=ocr_reference,
        context_section=context_section,
    )
    if input_hint:
        verify_prompt += f'\n\n## D层输入使用提示\n{input_hint}'
    if meaningless_ocr:
        verify_prompt += '\n\n## 额外复核要求\n由于D层OCR已判定无意义，请特别检查标题区、列表区、图示节点、流程节点等高价值文本锚点是否保留了可见字符级内容；若仍只有抽象概括，请标记为过于空泛或细节不足。'

    verify_raw = _call_m_layer_llm(
        CI_M_LAYER_VERIFY_SYSTEM_PROMPT,
        _build_m_multimodal_content(verify_prompt, prev_asset_abs, unit['asset_abs_path'], support_asset_abs),
        timeout=timeout,
        prefer_qwen35_plus=prefer_qwen35_plus,
    )
    verify_parsed = _parse_llm_json(verify_raw, {}) if verify_raw else {}
    return _normalize_m_verification(verify_parsed)


def _format_uncertain_regions_for_prompt(uncertain_regions: List[Dict[str, str]]) -> str:
    # from continuous_image_service.py L2951-2961
    if not uncertain_regions:
        return '- （无）'
    lines: List[str] = []
    for item in uncertain_regions:
        lines.append(
            f'- {item.get("region_id", "") or "未标注"} | '
            f'issue={item.get("issue", "") or "未标注"} | '
            f'reason={item.get("reason", "") or "未说明"}'
        )
    return '\n'.join(lines)


def _format_missing_regions_for_prompt(missing_regions: List[Dict[str, str]]) -> str:
    # from continuous_image_service.py L2964-2974
    if not missing_regions:
        return '- （无）'
    lines: List[str] = []
    for item in missing_regions:
        lines.append(
            f'- type={item.get("type", "") or "未标注"} | '
            f'position={item.get("position", "") or "未标注"} | '
            f'reason={item.get("reason", "") or "未说明"}'
        )
    return '\n'.join(lines)


def _run_m_layer_patch(unit: Dict[str, Any], prev_section: Optional[Dict[str, Any]], context_section: str,
                       ocr_reference: str, analyzed: Dict[str, Any], verification: Dict[str, Any],
                       input_hint: str, prefer_qwen35_plus: bool, timeout: int,
                       meaningless_ocr: bool = False,
                       support_asset_abs: str = '') -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # from continuous_image_service.py L2977-3051
    patch_meta: Dict[str, Any] = {
        'triggered': False,
        'applied': False,
        'reason': '',
    }
    overall_verdict = verification.get('overall_verdict', 'weak')
    uncertain_regions = verification.get('uncertain_regions', []) if isinstance(verification.get('uncertain_regions', []), list) else []
    missing_regions = verification.get('missing_regions', []) if isinstance(verification.get('missing_regions', []), list) else []
    if overall_verdict == 'reliable' and not uncertain_regions and not missing_regions:
        patch_meta['reason'] = 'verification_reliable'
        return analyzed, patch_meta

    patch_meta['triggered'] = True
    patch_meta['reason'] = overall_verdict or 'needs_patch'
    prev_filename = prev_section.get('source_file', '') if prev_section else ''
    prev_asset_abs = prev_section.get('_asset_abs_path', '') if prev_section else ''
    patch_prompt = CI_M_LAYER_PATCH_USER_PROMPT_TEMPLATE.format(
        current_filename=unit['source_file'],
        prev_filename=prev_filename or '（无，当前图为首图）',
        structure_section=_format_layout_regions_for_prompt(analyzed.get('layout_regions', [])) + f'\n- reading_order={analyzed.get("reading_order", "") or "未标注"}',
        main_content=analyzed.get('main_content', '') or '（无）',
        handwriting_printing_relation=analyzed.get('handwriting_printing_relation', '') or '（无）',
        annotation_relation=analyzed.get('annotation_relation', '') or '（无）',
        verified_regions=', '.join(verification.get('verified_regions', [])) or '（无）',
        uncertain_regions_section=_format_uncertain_regions_for_prompt(uncertain_regions),
        missing_regions_section=_format_missing_regions_for_prompt(missing_regions),
        summary_coverage=verification.get('summary_coverage', 'weak') or 'weak',
        overall_verdict=overall_verdict or 'weak',
        ocr_reference=ocr_reference,
        context_section=context_section,
    )
    if input_hint:
        patch_prompt += f'\n\n## D层输入使用提示\n{input_hint}'
    if meaningless_ocr:
        patch_prompt += '\n\n## 额外修补要求\n由于D层OCR已判定无意义，请优先补充标题区、列表区、圈内词、流程节点、箭头旁短词等高价值文本锚点的可见字符或符号，但看不清时必须保留待确认。'

    patch_raw = _call_m_layer_llm(
        CI_M_LAYER_PATCH_SYSTEM_PROMPT,
        _build_m_multimodal_content(patch_prompt, prev_asset_abs, unit['asset_abs_path'], support_asset_abs),
        timeout=timeout,
        prefer_qwen35_plus=prefer_qwen35_plus,
    )
    patch_parsed = _parse_llm_json(patch_raw, {}) if patch_raw else {}
    patched_layout_regions = _normalize_layout_regions(patch_parsed.get('layout_regions', []))
    patched_main_content = str(patch_parsed.get('main_content', '') or '').strip()
    patched_handwriting = str(patch_parsed.get('handwriting_printing_relation', '') or '').strip()
    patched_annotation = str(patch_parsed.get('annotation_relation', '') or '').strip()

    if patched_layout_regions:
        analyzed['layout_regions'] = patched_layout_regions
    if patched_main_content:
        analyzed['main_content'] = patched_main_content
    if patched_handwriting:
        analyzed['handwriting_printing_relation'] = patched_handwriting
    if patched_annotation:
        analyzed['annotation_relation'] = patched_annotation

    post_patch_structure_issues = _validate_m_structure(
        analyzed.get('layout_regions', []), analyzed.get('reading_order', ''), require_text_anchors=meaningless_ocr
    )
    post_patch_summary_issues = _validate_m_summary(
        analyzed.get('main_content', ''),
        analyzed.get('handwriting_printing_relation', ''),
        analyzed.get('annotation_relation', ''),
        analyzed.get('continuity_with_prev', {}),
    )
    patch_meta['applied'] = bool(patched_layout_regions or patched_main_content or patched_handwriting or patched_annotation)
    patch_meta['post_patch_structure_issues'] = post_patch_structure_issues
    patch_meta['post_patch_summary_issues'] = post_patch_summary_issues
    return analyzed, patch_meta


def _validate_m_structure(layout_regions: List[Dict[str, Any]], reading_order: str,
                          require_text_anchors: bool = False) -> List[str]:
    # from continuous_image_service.py L3054-3108
    issues: List[str] = []
    if not layout_regions:
        issues.append('未识别到有效版面区域')
    generic_regions = 0
    detail_thin_regions = 0
    text_anchor_thin_regions = 0
    for region in layout_regions:
        if not region.get('position'):
            issues.append('存在未标注位置的区域')
            break
    for region in layout_regions:
        content = region.get('content', '')
        if any(token in content for token in _M_GENERIC_REGION_CONTENT):
            generic_regions += 1
        region_type = str(region.get('type', '') or '')
        key_elements = region.get('key_elements', []) if isinstance(region.get('key_elements', []), list) else []
        visual_relations = region.get('visual_relations', []) if isinstance(region.get('visual_relations', []), list) else []
        direction_notes = str(region.get('direction_notes', '') or '').strip()
        relative_layout = str(region.get('relative_layout', '') or '').strip()
        size_notes = str(region.get('size_notes', '') or '').strip()
        shape_notes = str(region.get('shape_notes', '') or '').strip()
        if any(token in region_type for token in ('图示', '流程', '列表')):
            missing_detail_count = 0
            if not key_elements:
                missing_detail_count += 1
            if not visual_relations:
                missing_detail_count += 1
            if not relative_layout:
                missing_detail_count += 1
            if not size_notes:
                missing_detail_count += 1
            if not shape_notes:
                missing_detail_count += 1
            if any(token in region_type for token in ('图示', '流程')) and not direction_notes:
                missing_detail_count += 1
            if missing_detail_count >= 3:
                detail_thin_regions += 1
        if require_text_anchors and any(token in region_type for token in _M_TEXT_ANCHOR_REGION_TYPES):
            key_elements = region.get('key_elements', []) if isinstance(region.get('key_elements', []), list) else []
            content_text = str(region.get('content', '') or '').strip()
            if not key_elements and (not content_text or content_text in _M_GENERIC_REGION_CONTENT or len(content_text) < 4):
                text_anchor_thin_regions += 1
    if layout_regions and generic_regions == len(layout_regions):
        issues.append('版面区域描述过于空泛')
    if detail_thin_regions:
        issues.append('复杂区域细节不足，缺少关系/方向/布局/形状描述')
    if text_anchor_thin_regions:
        issues.append('高价值文本锚点缺少字符级内容')
    if len(layout_regions) == 1:
        issues.append('版面区域过少，可能遗漏重要区域')
    if len((reading_order or '').strip()) < 6:
        issues.append('阅读顺序描述过短')
    return list(dict.fromkeys(issues))


def _validate_m_summary(main_content: str, handwriting_printing_relation: str,
                        annotation_relation: str, continuity_with_prev: Dict[str, str]) -> List[str]:
    # from continuous_image_service.py L3111-3125
    issues: List[str] = []
    main_text = (main_content or '').strip()
    if len(main_text) < 20:
        issues.append('主体摘要过短')
    if any(token in main_text for token in _M_GENERIC_MAIN_CONTENT):
        issues.append('主体摘要过于空泛')
    if len((handwriting_printing_relation or '').strip()) < 6:
        issues.append('手写印刷关系描述不足')
    if not (annotation_relation or '').strip():
        issues.append('批注关系缺失')
    if continuity_with_prev.get('type') not in _M_CONTINUITY_TYPES:
        issues.append('连续性类型非法')
    return list(dict.fromkeys(issues))


def _build_retry_suffix(issues: List[str]) -> str:
    # from continuous_image_service.py L3128-3134
    if not issues:
        return ''
    lines = ['## 上一次输出存在的问题']
    lines.extend([f'- {issue}' for issue in issues])
    lines.append('请只修正上述问题，并继续严格输出合法JSON。')
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4.5 — M 层编排（第一步：双阶段主流程）
# from continuous_image_service.py L3137-3370
# ══════════════════════════════════════════════════════════════════════════════

def _run_m_layer_two_stage(username: str, unit: Dict[str, Any], prev_section: Optional[Dict[str, Any]],
                           context_section: str, ocr_text_for_prompt: str, input_hint: str,
                           prefer_qwen35_plus: bool, timeout: int,
                           total_units: int = 1, meaningless_ocr: bool = False,
                           support_asset_abs: str = '') -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # from continuous_image_service.py L3137-3370
    prev_filename = prev_section.get('source_file', '') if prev_section else ''
    prev_main_content = (prev_section.get('main_content') or '')[:300] if prev_section else ''
    prev_asset_abs = prev_section.get('_asset_abs_path', '') if prev_section else ''
    ocr_reference = ocr_text_for_prompt or '（本页OCR已被门控禁用或可信度不足，请忽略OCR，仅依据视觉分析）'

    quality: Dict[str, Any] = {
        'pipeline': 'three_stage',
        'ocr_mode': 'assist' if ocr_text_for_prompt else 'vision_only',
        'structure_parallel_used': False,
        'structure_parallel_candidate_count': 0,
        'structure_char_candidate_used': False,
        'structure_merge_strategy': 'single',
        'structure_retry_used': False,
        'summary_retry_used': False,
        'verification_used': True,
        'patch_used': False,
        'structure_issues': [],
        'summary_issues': [],
    }

    structure_prompt = CI_M_LAYER_STRUCTURE_USER_PROMPT_TEMPLATE.format(
        current_filename=unit['source_file'],
        prev_filename=prev_filename or '（无，当前图为首图）',
        ocr_reference=ocr_reference,
        context_section=context_section,
    )
    if input_hint:
        structure_prompt += f'\n\n## D层输入使用提示\n{input_hint}'

    use_parallel_structure = prev_section is None or total_units <= 1
    layout_regions: List[Dict[str, Any]] = []
    reading_order = ''
    structure_issues: List[str] = []
    if use_parallel_structure:
        candidate_modes = ['coverage', 'relations', 'geometry']
        if meaningless_ocr:
            candidate_modes.append('characters')
            quality['structure_char_candidate_used'] = True
        quality['structure_parallel_used'] = True
        quality['structure_parallel_candidate_count'] = len(candidate_modes)

        candidates: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(len(candidate_modes), 3)) as executor:
            future_map = {
                executor.submit(
                    _run_m_structure_candidate,
                    structure_prompt,
                    unit,
                    prev_asset_abs,
                    support_asset_abs,
                    timeout,
                    prefer_qwen35_plus,
                    mode,
                ): mode
                for mode in candidate_modes
            }
            for future in as_completed(future_map):
                try:
                    candidate = future.result()
                except Exception as exc:
                    print(f'[ci_m_layer] structure candidate {future_map[future]} failed: {exc}')
                    continue
                if candidate.get('layout_regions'):
                    candidates.append(candidate)

        merged_structure = _merge_m_structure_candidates_with_claude(
            current_filename=unit['source_file'],
            prev_filename=prev_filename,
            candidates=candidates,
            prev_asset_abs=prev_asset_abs,
            current_asset_abs=unit['asset_abs_path'],
            support_asset_abs=support_asset_abs,
            timeout=timeout,
            meaningless_ocr=meaningless_ocr,
        ) if candidates else {'layout_regions': [], 'reading_order': '', 'candidate_count': 0}
        if not merged_structure.get('layout_regions'):
            merged_structure = _merge_m_structure_candidates(candidates)
            quality['structure_merge_strategy'] = 'heuristic_fallback'
        else:
            quality['structure_merge_strategy'] = str(merged_structure.get('merge_strategy') or 'qwen35_plus')
        layout_regions = merged_structure.get('layout_regions', []) if isinstance(merged_structure.get('layout_regions', []), list) else []
        reading_order = str(merged_structure.get('reading_order', '') or '').strip()
        quality['structure_parallel_merged_region_count'] = int(merged_structure.get('merged_region_count', 0) or 0)
        structure_issues = _validate_m_structure(layout_regions, reading_order, require_text_anchors=meaningless_ocr)

    if not layout_regions:
        structure_raw = _call_m_layer_llm(
            CI_M_LAYER_STRUCTURE_SYSTEM_PROMPT,
            _build_m_multimodal_content(structure_prompt, prev_asset_abs, unit['asset_abs_path'], support_asset_abs),
            timeout=timeout,
            prefer_qwen35_plus=prefer_qwen35_plus,
        )
        structure_parsed = _parse_llm_json(structure_raw, {}) if structure_raw else {}
        layout_regions = _normalize_layout_regions(structure_parsed.get('layout_regions', []))
        reading_order = str(structure_parsed.get('reading_order', '') or '').strip()
        structure_issues = _validate_m_structure(layout_regions, reading_order, require_text_anchors=meaningless_ocr)

    if structure_issues:
        quality['structure_retry_used'] = True
        retry_prompt = structure_prompt + '\n\n' + _build_retry_suffix(structure_issues)
        retry_raw = _call_m_layer_llm(
            CI_M_LAYER_STRUCTURE_SYSTEM_PROMPT,
            _build_m_multimodal_content(retry_prompt, prev_asset_abs, unit['asset_abs_path'], support_asset_abs),
            timeout=timeout,
            prefer_qwen35_plus=prefer_qwen35_plus,
        )
        retry_parsed = _parse_llm_json(retry_raw, {}) if retry_raw else {}
        retry_layout_regions = _normalize_layout_regions(retry_parsed.get('layout_regions', []))
        retry_reading_order = str(retry_parsed.get('reading_order', '') or '').strip()
        retry_issues = _validate_m_structure(retry_layout_regions, retry_reading_order, require_text_anchors=meaningless_ocr)
        if retry_layout_regions and len(retry_issues) <= len(structure_issues):
            layout_regions = retry_layout_regions
            reading_order = retry_reading_order
            structure_issues = retry_issues

    quality['structure_issues'] = structure_issues
    quality['structure_parse_ok'] = bool(layout_regions)

    if not layout_regions:
        raise ValueError('m_structure_unavailable')

    summary_prompt = CI_M_LAYER_SUMMARY_USER_PROMPT_TEMPLATE.format(
        current_filename=unit['source_file'],
        prev_filename=prev_filename or '（无，当前图为首图）',
        prev_main_content=prev_main_content or '（无）',
        structure_section=_format_layout_regions_for_prompt(layout_regions) + f'\n- reading_order={reading_order or "未标注"}',
        ocr_reference=ocr_reference,
        context_section=context_section,
    )
    if input_hint:
        summary_prompt += f'\n\n## D层输入使用提示\n{input_hint}'

    summary_raw = _call_m_layer_llm(
        CI_M_LAYER_SUMMARY_SYSTEM_PROMPT,
        _build_m_multimodal_content(summary_prompt, prev_asset_abs, unit['asset_abs_path'], support_asset_abs),
        timeout=timeout,
        prefer_qwen35_plus=prefer_qwen35_plus,
    )
    summary_parsed = _parse_llm_json(summary_raw, {}) if summary_raw else {}
    continuity_with_prev = _normalize_continuity_with_prev(summary_parsed.get('continuity_with_prev', {}), not prev_section)
    main_content = str(summary_parsed.get('main_content', '') or '').strip()
    handwriting_printing_relation = str(summary_parsed.get('handwriting_printing_relation', '') or '').strip()
    annotation_relation = str(summary_parsed.get('annotation_relation', '') or '').strip()
    summary_issues = _validate_m_summary(main_content, handwriting_printing_relation, annotation_relation, continuity_with_prev)

    if summary_issues:
        quality['summary_retry_used'] = True
        retry_summary_prompt = summary_prompt + '\n\n' + _build_retry_suffix(summary_issues)
        retry_summary_raw = _call_m_layer_llm(
            CI_M_LAYER_SUMMARY_SYSTEM_PROMPT,
            _build_m_multimodal_content(retry_summary_prompt, prev_asset_abs, unit['asset_abs_path'], support_asset_abs),
            timeout=timeout,
            prefer_qwen35_plus=prefer_qwen35_plus,
        )
        retry_summary_parsed = _parse_llm_json(retry_summary_raw, {}) if retry_summary_raw else {}
        retry_continuity = _normalize_continuity_with_prev(retry_summary_parsed.get('continuity_with_prev', {}), not prev_section)
        retry_main_content = str(retry_summary_parsed.get('main_content', '') or '').strip()
        retry_handwriting = str(retry_summary_parsed.get('handwriting_printing_relation', '') or '').strip()
        retry_annotation = str(retry_summary_parsed.get('annotation_relation', '') or '').strip()
        retry_summary_issues = _validate_m_summary(
            retry_main_content, retry_handwriting, retry_annotation, retry_continuity
        )
        if retry_main_content and len(retry_summary_issues) <= len(summary_issues):
            main_content = retry_main_content
            handwriting_printing_relation = retry_handwriting
            annotation_relation = retry_annotation
            continuity_with_prev = retry_continuity
            summary_issues = retry_summary_issues

    if not main_content:
        main_content = _build_main_content_from_regions(layout_regions)
    if not handwriting_printing_relation:
        handwriting_printing_relation = '以版面结构为主，手写层与印刷层关系需结合原图复核。'
    if not annotation_relation:
        annotation_relation = '无批注' if '批注' not in ''.join(region.get('type', '') for region in layout_regions) else '批注关系待结合原图复核。'

    quality['summary_issues'] = summary_issues
    quality['summary_parse_ok'] = bool(main_content)

    analyzed = {
        'layout_regions': layout_regions,
        'reading_order': reading_order,
        'main_content': main_content,
        'handwriting_printing_relation': handwriting_printing_relation,
        'annotation_relation': annotation_relation,
        'continuity_with_prev': continuity_with_prev,
    }
    verification = _run_m_layer_verification(
        unit=unit,
        prev_section=prev_section,
        context_section=context_section,
        ocr_reference=ocr_reference,
        analyzed=analyzed,
        input_hint=input_hint,
        prefer_qwen35_plus=prefer_qwen35_plus,
        timeout=timeout,
        meaningless_ocr=meaningless_ocr,
        support_asset_abs=support_asset_abs,
    )
    quality['verified_region_count'] = len(verification.get('verified_regions', []))
    quality['uncertain_region_count'] = len(verification.get('uncertain_regions', []))
    quality['missing_region_count'] = len(verification.get('missing_regions', []))
    quality['summary_coverage'] = verification.get('summary_coverage', 'weak')
    quality['overall_verdict'] = verification.get('overall_verdict', 'weak')

    analyzed, patch_meta = _run_m_layer_patch(
        unit=unit,
        prev_section=prev_section,
        context_section=context_section,
        ocr_reference=ocr_reference,
        analyzed=analyzed,
        verification=verification,
        input_hint=input_hint,
        prefer_qwen35_plus=prefer_qwen35_plus,
        timeout=timeout,
        meaningless_ocr=meaningless_ocr,
        support_asset_abs=support_asset_abs,
    )
    quality['patch_used'] = bool(patch_meta.get('triggered'))
    quality['patch_applied'] = bool(patch_meta.get('applied'))
    quality['patch_reason'] = patch_meta.get('reason', '')
    if patch_meta.get('post_patch_structure_issues'):
        quality['structure_issues'] = patch_meta.get('post_patch_structure_issues', [])
    if patch_meta.get('post_patch_summary_issues'):
        quality['summary_issues'] = patch_meta.get('post_patch_summary_issues', [])

    analyzed['m_verification'] = verification
    analyzed['m_patch'] = patch_meta
    return analyzed, quality


# ══════════════════════════════════════════════════════════════════════════════
# Phase 4.6 — 版面可视化
# from continuous_image_service.py L2318-2400
# ══════════════════════════════════════════════════════════════════════════════

def _build_image_layout_visual(src_path: str, raw_txt_path: str, save_path: str) -> bool:
    # from continuous_image_service.py L2318-2370
    if not os.path.exists(src_path) or not os.path.exists(raw_txt_path):
        return False
    try:
        img = Image.open(src_path).convert('RGB')

        elements_by_page = extract_layout_elements_from_txt(raw_txt_path)
        page_elements: List[Dict[str, Any]] = []
        if elements_by_page:
            page_elements = elements_by_page.get(1, []) or next(iter(elements_by_page.values()), [])

        if not page_elements:
            try:
                with open(raw_txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                pattern = r'<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>'
                matches = re.findall(pattern, content, re.DOTALL)
                for match in matches:
                    label_type = match[0].strip()
                    coordinates_str = match[1].strip()
                    try:
                        cor_list = eval(coordinates_str)
                        for points in cor_list:
                            if len(points) >= 4:
                                x1, y1, x2, y2 = points[:4]
                                page_elements.append({
                                    'bbox': [x1, y1, x2, y2],
                                    'type': label_type,
                                    'normalized': True,
                                })
                    except Exception:
                        continue
            except Exception:
                pass

        if not page_elements:
            print(f'[ci] _build_image_layout_visual: 未从 raw.txt 提取到坐标，跳过: {raw_txt_path}')
            return False

        annotated = _draw_layout_on_image(img, page_elements)
        annotated.convert('RGB').save(save_path)
        return True
    except Exception as e:
        print(f'[ci] _build_image_layout_visual 失败 ({src_path}): {e}')
        return False


def _ensure_pdf_layout_visual(username: str, source_file: str, layout_visual_dir: str) -> Tuple[str, str, str]:
    # from continuous_image_service.py L2373-2400
    source_base = os.path.splitext(os.path.basename(source_file))[0]
    user_root = os.path.join('.', 'received_dir', 'user_raw_file', username)
    source_pdf = os.path.join(user_root, source_file)
    ocr_dir = os.path.join(user_root, f'{source_base}_ocr')
    source_layout_pdf = os.path.join(ocr_dir, f'{source_base}_layouts.pdf')

    target_name = f'{source_base}_layouts.pdf'
    target_abs = os.path.join(layout_visual_dir, target_name)
    target_rel = f'layout_visual/{target_name}'

    if os.path.exists(target_abs):
        return 'pdf', target_rel, 'ready'

    try:
        if os.path.exists(source_layout_pdf):
            shutil.copy2(source_layout_pdf, target_abs)
            return 'pdf', target_rel, 'ready'

        raw_txt = os.path.join(ocr_dir, f'{source_base}_raw.txt')
        if os.path.exists(source_pdf) and os.path.exists(raw_txt):
            success, generated_path = generate_layout_pdf(source_pdf, raw_txt, target_abs)
            if success and generated_path and os.path.exists(target_abs):
                return 'pdf', target_rel, 'ready'
    except Exception:
        pass

    return 'pdf', '', 'missing'


def build_m_layer(username: str, units: List[Dict[str, Any]], d_layer: Dict[str, Any], paths: Dict[str, str],
                  task_id: str) -> Dict[str, Any]:
    # from continuous_image_service.py L3373-3514
    d_map = {item['unit_id']: item for item in d_layer.get('items', [])}
    sections: List[Dict[str, Any]] = []

    _update_task(task_id, current_section='版面分析中', total_items=len(units), current_item=0)

    pdf_layout_cache: Dict[str, Tuple[str, str, str]] = {}

    for idx, unit in enumerate(units, start=1):
        _update_task(task_id, current_item=idx)

        d_item = d_map.get(unit['unit_id'], {})
        ocr_text = d_item.get('ocr_text', '')
        ocr_text_for_m = d_item.get('ocr_text_enhanced', '') or ocr_text
        d_text_gate = _should_skip_d_text_for_m(ocr_text_for_m, None)
        ocr_char_limit = max(int(d_text_gate.get('ocr_char_limit', 600) or 0), 0)
        ocr_text_for_prompt = (ocr_text_for_m or '')[:ocr_char_limit] if ocr_char_limit > 0 else ''
        input_hint = d_text_gate.get('input_hint', '') or ''

        if unit['source_type'] == 'pdf':
            if unit['source_file'] not in pdf_layout_cache:
                pdf_layout_cache[unit['source_file']] = _ensure_pdf_layout_visual(
                    username, unit['source_file'], paths['layout_visual']
                )
            layout_visual_type, layout_visual_path, layout_status = pdf_layout_cache[unit['source_file']]
            overlay_abs = ''
            ok = False
        else:
            unit_ocr_dir = os.path.join(paths['ocr_cache'], unit['unit_id'])
            raw_txt_path = ''
            if os.path.isdir(unit_ocr_dir):
                for fn in os.listdir(unit_ocr_dir):
                    if fn.endswith('_raw.txt'):
                        raw_txt_path = os.path.join(unit_ocr_dir, fn)
                        break
            overlay_name = f"{unit['unit_id']}_layout_visual.png"
            overlay_abs = os.path.join(paths['layout_visual'], overlay_name)
            ok = _build_image_layout_visual(unit['asset_abs_path'], raw_txt_path, overlay_abs)
            layout_visual_type = 'image_annotated'
            layout_visual_path = f'layout_visual/{overlay_name}' if ok else ''
            layout_status = 'ready' if ok else 'missing'

        prev_section = sections[-1] if sections else None
        print(f'[ci] build_m_layer unit={unit["unit_id"]} 调用 M 层双阶段分析...')
        try:
            analyzed, m_quality = _run_m_layer_two_stage(
                username=username,
                unit=unit,
                prev_section=prev_section,
                context_section='',
                ocr_text_for_prompt=ocr_text_for_prompt,
                input_hint=input_hint,
                prefer_qwen35_plus=bool(d_text_gate.get('prefer_qwen35_plus_for_m')),
                timeout=_M_LAYER_FLAGGED_TIMEOUT if d_text_gate.get('prefer_qwen35_plus_for_m') else 60,
                total_units=len(units),
                meaningless_ocr=bool(d_text_gate.get('meaningless_ocr')),
                support_asset_abs=overlay_abs if ok else '',
            )
            layout_regions = analyzed['layout_regions']
            reading_order = analyzed['reading_order']
            main_content = analyzed['main_content']
            handwriting_printing_relation = analyzed['handwriting_printing_relation']
            annotation_relation = analyzed['annotation_relation']
            continuity_with_prev = analyzed['continuity_with_prev']
            m_verification = analyzed.get('m_verification', _normalize_m_verification({}))
            m_patch = analyzed.get('m_patch', {'triggered': False, 'applied': False, 'reason': ''})
            print(f'[ci] build_m_layer unit={unit["unit_id"]} 双阶段分析成功: continuity={continuity_with_prev.get("type")}')
        except Exception as e:
            print(f'[ci] build_m_layer unit={unit["unit_id"]} 双阶段分析失败，使用 summarize_image 兜底: {e}')
            m_quality = {
                'pipeline': 'three_stage',
                'fallback': 'summarize_image',
                'error': str(e)[:160],
            }
            try:
                image_summary = util.summarize_image(unit['asset_abs_path'], user_name=username)
            except Exception as inner_e:
                image_summary = f'图片理解失败: {inner_e}'
            summary_lines = [line.strip() for line in str(image_summary).split('\n') if line.strip()]
            layout_regions = summary_lines[:4] if summary_lines else ([ocr_text[:180]] if ocr_text else [])
            reading_order = '默认按从上到下、从左到右阅读；结合标注与手写优先关注变化区域。'
            main_content = image_summary
            handwriting_printing_relation = '信息不足，无法区分印刷层与手写层。'
            annotation_relation = '已结合手写层/印刷层/标注层进行描述（若存在）。'
            continuity_with_prev = {'type': '首图' if not prev_section else '未知', 'reason': 'LLM调用失败', 'key_bridge': ''}
            m_verification = _normalize_m_verification({})
            m_patch = {'triggered': False, 'applied': False, 'reason': 'fallback'}

        title = f"{unit['source_file']} - 第{unit['page']}页" if unit['source_type'] == 'pdf' else unit['source_file']

        section: Dict[str, Any] = {
            'unit_id': unit['unit_id'],
            'seq': unit['seq'],
            'source_file': unit['source_file'],
            'page': unit['page'],
            'title': title,
            'layout_regions': layout_regions,
            'reading_order': reading_order,
            'main_content': main_content,
            'handwriting_printing_relation': handwriting_printing_relation,
            'annotation_relation': annotation_relation,
            'continuity_with_prev': continuity_with_prev,
            'context_used': {
                'context_mode': 'none',
                'context_doc_count': 0,
                'context_card_count': 0,
            },
            'ocr_input_policy': {
                'used_d_text_in_m': not d_text_gate['skip_d_text'],
                'meaningless_ocr': d_text_gate['meaningless_ocr'],
                'unrelated_to_context': d_text_gate['unrelated_to_context'],
                'reason': d_text_gate['reason'],
                'judge_model': d_text_gate['judge_model'],
                'prefer_qwen35_plus_for_m': d_text_gate.get('prefer_qwen35_plus_for_m', False),
                'ocr_char_limit': d_text_gate.get('ocr_char_limit', 600),
                'input_hint': input_hint,
            },
            'ocr_refs': [unit['unit_id']],
            'm_quality': m_quality,
            'm_verification': m_verification,
            'm_patch': m_patch,
            'layout_visual_type': layout_visual_type,
            'layout_visual_path': layout_visual_path,
            'layout_visual_status': layout_status,
            '_asset_abs_path': unit['asset_abs_path'],
        }
        sections.append(section)

    for sec in sections:
        sec.pop('_asset_abs_path', None)

    m_layer = {
        'layer': 'M',
        'total_sections': len(sections),
        'sections': sections,
    }
    _safe_json_dump(paths['m_layer'], m_layer)
    return m_layer


def build_m_layer_v2(username: str, units: List[Dict[str, Any]], d_layer: Dict[str, Any], paths: Dict[str, str],
                     task_id: str, m_layer_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    # from continuous_image_service.py L3517-3638
    d_map = {item['unit_id']: item for item in d_layer.get('items', [])}
    sections: List[Dict[str, Any]] = []
    _update_task(task_id, current_section='版面分析中', total_items=len(units), current_item=0)

    for idx, unit in enumerate(units, start=1):
        _update_task(task_id, current_item=idx)

        d_item = d_map.get(unit['unit_id'], {})
        ocr_text = d_item.get('ocr_text', '')
        ocr_text_for_m = d_item.get('ocr_text_enhanced', '') or ocr_text
        d_text_gate = _should_skip_d_text_for_m(ocr_text_for_m, m_layer_context)
        ocr_char_limit = max(int(d_text_gate.get('ocr_char_limit', 600) or 0), 0)
        ocr_text_for_prompt = (ocr_text_for_m or '')[:ocr_char_limit] if ocr_char_limit > 0 else ''
        input_hint = d_text_gate.get('input_hint', '') or ''

        layout_visual_abs = unit.get('_layout_visual_abs', '')
        if layout_visual_abs and os.path.exists(layout_visual_abs):
            overlay_name = f"{unit['unit_id']}_layout_visual.png"
            overlay_abs = os.path.join(paths['layout_visual'], overlay_name)
            if not os.path.exists(overlay_abs):
                shutil.copy2(layout_visual_abs, overlay_abs)
            layout_visual_type = 'image_annotated'
            layout_visual_path = f'layout_visual/{overlay_name}'
            layout_status = 'ready'
        elif unit['source_type'] == 'pdf':
            layout_visual_type, layout_visual_path, layout_status = _ensure_pdf_layout_visual(
                username, unit['source_file'], paths['layout_visual']
            )
            overlay_abs = ''
        else:
            layout_visual_type = 'image_annotated'
            layout_visual_path = ''
            layout_status = 'missing'
            overlay_abs = ''

        prev_section = sections[-1] if sections else None
        context_section = ''
        if m_layer_context:
            ctx_mode = 'full' if idx == 1 else 'brief'
            context_section = _format_m_layer_context(m_layer_context, mode=ctx_mode)

        print(f'[ci] build_m_layer_v2 unit={unit["unit_id"]} 调用 M 层双阶段分析...')
        try:
            analyzed, m_quality = _run_m_layer_two_stage(
                username=username,
                unit=unit,
                prev_section=prev_section,
                context_section=context_section,
                ocr_text_for_prompt=ocr_text_for_prompt,
                input_hint=input_hint,
                prefer_qwen35_plus=bool(d_text_gate.get('prefer_qwen35_plus_for_m')),
                timeout=_M_LAYER_FLAGGED_TIMEOUT if d_text_gate.get('prefer_qwen35_plus_for_m') else 60,
                total_units=len(units),
                meaningless_ocr=bool(d_text_gate.get('meaningless_ocr')),
                support_asset_abs=layout_visual_abs if layout_visual_abs and os.path.exists(layout_visual_abs) else '',
            )
            layout_regions = analyzed['layout_regions']
            reading_order = analyzed['reading_order']
            main_content = analyzed['main_content']
            handwriting_printing_relation = analyzed['handwriting_printing_relation']
            annotation_relation = analyzed['annotation_relation']
            continuity_with_prev = analyzed['continuity_with_prev']
            m_verification = analyzed.get('m_verification', _normalize_m_verification({}))
            m_patch = analyzed.get('m_patch', {'triggered': False, 'applied': False, 'reason': ''})
        except Exception as e:
            print(f'[ci] build_m_layer_v2 unit={unit["unit_id"]} 双阶段分析失败，使用兜底: {e}')
            m_quality = {
                'pipeline': 'three_stage',
                'fallback': 'summarize_image',
                'error': str(e)[:160],
            }
            try:
                image_summary = util.summarize_image(unit['asset_abs_path'], user_name=username)
            except Exception as inner_e:
                image_summary = f'图片理解失败: {inner_e}'
            summary_lines = [l.strip() for l in str(image_summary).split('\n') if l.strip()]
            layout_regions = summary_lines[:4] or ([ocr_text[:180]] if ocr_text else [])
            reading_order = '从上到下、从左到右阅读。'
            main_content = image_summary
            handwriting_printing_relation = '信息不足。'
            annotation_relation = '已综合描述。'
            continuity_with_prev = {'type': '首图' if not prev_section else '未知', 'reason': 'LLM调用失败', 'key_bridge': ''}
            m_verification = _normalize_m_verification({})
            m_patch = {'triggered': False, 'applied': False, 'reason': 'fallback'}

        title = f"{unit['source_file']} - 第{unit['page']}页" if unit['source_type'] == 'pdf' else unit['source_file']
        ctx_used = {'context_mode': 'none', 'context_doc_count': 0, 'context_card_count': 0}
        if m_layer_context and context_section:
            ctx_used = {
                'context_mode': 'full' if idx == 1 else 'brief',
                'context_doc_count': len(m_layer_context.get('doc_summaries', [])),
                'context_card_count': len(m_layer_context.get('card_summaries', [])),
            }
        section: Dict[str, Any] = {
            'unit_id': unit['unit_id'],
            'seq': unit['seq'],
            'source_file': unit['source_file'],
            'page': unit['page'],
            'title': title,
            'layout_regions': layout_regions,
            'reading_order': reading_order,
            'main_content': main_content,
            'handwriting_printing_relation': handwriting_printing_relation,
            'annotation_relation': annotation_relation,
            'continuity_with_prev': continuity_with_prev,
            'context_used': ctx_used,
            'ocr_input_policy': {
                'used_d_text_in_m': not d_text_gate['skip_d_text'],
                'meaningless_ocr': d_text_gate['meaningless_ocr'],
                'unrelated_to_context': d_text_gate['unrelated_to_context'],
                'reason': d_text_gate['reason'],
                'judge_model': d_text_gate['judge_model'],
                'prefer_qwen35_plus_for_m': d_text_gate.get('prefer_qwen35_plus_for_m', False),
                'ocr_char_limit': d_text_gate.get('ocr_char_limit', 600),
                'input_hint': input_hint,
            },
            'ocr_refs': [unit['unit_id']],
            'm_quality': m_quality,
            'm_verification': m_verification,
            'm_patch': m_patch,
            'layout_visual_type': layout_visual_type,
            'layout_visual_path': layout_visual_path,
            'layout_visual_status': layout_status,
            '_asset_abs_path': unit['asset_abs_path'],
        }
        sections.append(section)

    for sec in sections:
        sec.pop('_asset_abs_path', None)

    m_layer = {'layer': 'M', 'total_sections': len(sections), 'sections': sections}
    _safe_json_dump(paths['m_layer'], m_layer)
    return m_layer
