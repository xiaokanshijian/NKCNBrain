import copy
import json
import os
import re
from typing import Any, Dict, List, Optional

from app_chat.ci._llm import (
    _call_claude4_sonnet_text_llm,
    _call_qwen35_m_layer_llm,
    _call_qwen35_plus_m_layer_llm,
    _normalize_llm_response_text,
    _parse_llm_json,
    _repair_json_locally,
)
from app_chat.ci._utils import _truncate_text, _update_task
from app_chat.ci.overlay_layer import _load_ci_context
from app_chat.ci.r_layer import iterate_ci_reproduction_unit, _normalize_reproduction_iter_context
from app_chat.ci_prompts import (
    CI_R_SINGLE_REGION_PLANNER_SYSTEM_PROMPT,
    CI_R_SINGLE_REGION_PLANNER_USER_PROMPT_TEMPLATE,
    CI_R_SINGLE_REGION_USER_ONLY_REWRITE_SYSTEM_PROMPT,
    CI_R_SINGLE_REGION_USER_ONLY_REWRITE_USER_PROMPT_TEMPLATE,
)


_LAYOUT_REGION_LIMITS = {'d': 3, 'm': 2, 't': 1}
_LAYOUT_REGION_ORDER = {'t': 0, 'm': 1, 'd': 2}
_LAYOUT_RECOGNITION_TEXT = {
    'white': '以标准印刷体效果呈现，清晰规整、辨识度较高',
    'gray': '以自然手写体效果呈现，保留自然波动、辨识度一般',
    'black': '尽量保留原貌，只做必要最小改动，维持较低辨识度',
}
_LAYOUT_ITERATION_MODE_REWRITE = 'rewrite'
_LAYOUT_ITERATION_MODE_CROP = 'crop'
_LAYOUT_ITERATION_SECTION_REWRITE = '重写版面级指令'


def _normalize_selected_layout_regions(selected_regions: Any) -> List[Dict[str, Any]]:
    if not isinstance(selected_regions, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in selected_regions:
        if not isinstance(item, dict):
            continue
        region_id = str(item.get('region_id') or '').strip()
        if not region_id:
            continue
        recognition = str(item.get('recognition') or item.get('recognition_mode') or 'gray').strip().lower()
        if recognition not in _LAYOUT_RECOGNITION_TEXT:
            recognition = 'gray'
        user_instruction = _truncate_text(item.get('user_instruction') or item.get('instruction') or '', 500)
        normalized.append({
            'region_id': region_id,
            'recognition': recognition,
            'user_instruction': user_instruction,
        })
    return normalized


def _normalize_layout_iteration_mode(iteration_mode: Any) -> str:
    mode = str(iteration_mode or _LAYOUT_ITERATION_MODE_REWRITE).strip().lower()
    if mode not in (_LAYOUT_ITERATION_MODE_REWRITE, _LAYOUT_ITERATION_MODE_CROP):
        return _LAYOUT_ITERATION_MODE_REWRITE
    return mode


def _describe_layout_bbox(bbox: Dict[str, Any]) -> str:
    x = float(bbox.get('x') or 0.0)
    y = float(bbox.get('y') or 0.0)
    w = float(bbox.get('w') or 0.0)
    h = float(bbox.get('h') or 0.0)
    cx = x + w / 2.0
    cy = y + h / 2.0
    horizontal = '左侧' if cx < 0.34 else ('右侧' if cx > 0.66 else '中部')
    vertical = '上部' if cy < 0.34 else ('下部' if cy > 0.66 else '中部')
    if horizontal == '中部' and vertical == '中部':
        anchor = '画面中部'
    elif horizontal == '中部':
        anchor = f'画面{vertical}'
    elif vertical == '中部':
        anchor = f'画面{horizontal}'
    else:
        anchor = f'画面{vertical}{horizontal}'
    return f'{anchor}附近'


def _validate_and_resolve_layout_regions(
    overlay_item: Dict[str, Any],
    selected_regions: Any,
    iteration_mode: str = _LAYOUT_ITERATION_MODE_REWRITE,
) -> List[Dict[str, Any]]:
    normalized = _normalize_selected_layout_regions(selected_regions)
    if not normalized:
        raise ValueError('至少需要选择一个版面')

    mode = _normalize_layout_iteration_mode(iteration_mode)

    available = {
        str(region.get('region_id') or '').strip(): region
        for region in (overlay_item.get('regions') or [])
        if isinstance(region, dict) and str(region.get('region_id') or '').strip()
    }
    if not available:
        raise ValueError('当前覆盖层未解析到可迭代版面，请先重新生成或手工修正覆盖层')

    resolved: List[Dict[str, Any]] = []
    counts = {'d': 0, 'm': 0, 't': 0}
    seen = set()
    for item in normalized:
        region_id = item['region_id']
        if region_id in seen:
            continue
        seen.add(region_id)
        base_region = available.get(region_id)
        if not base_region:
            raise ValueError(f'版面 {region_id} 已失效，请重新选择')
        level = str(base_region.get('level') or '').strip().lower()
        if level not in _LAYOUT_REGION_LIMITS:
            raise ValueError(f'版面 {region_id} 缺少有效层级')
        counts[level] += 1
        if counts[level] > _LAYOUT_REGION_LIMITS[level]:
            raise ValueError(f'{level.upper()}级版面最多选择 {_LAYOUT_REGION_LIMITS[level]} 个')
        user_instruction = item['user_instruction']
        resolved.append({
            **copy.deepcopy(base_region),
            'recognition': item['recognition'],
            'user_instruction': user_instruction,
            'has_user_instruction': bool(user_instruction.strip()),
            'position_text': _describe_layout_bbox(base_region.get('bbox') or {}),
        })

    resolved.sort(
        key=lambda item: (
            _LAYOUT_REGION_ORDER.get(item.get('level'), 99),
            item.get('rank') or 999,
            item.get('region_id') or '',
        )
    )
    if mode == _LAYOUT_ITERATION_MODE_CROP and len(resolved) != 1:
        raise ValueError('局部裁切迭代每次只能选择一个版面')
    return resolved


def _resolve_layout_iteration_edit_region(regions: List[Dict[str, Any]], iteration_mode: str) -> Optional[Dict[str, float]]:
    mode = _normalize_layout_iteration_mode(iteration_mode)
    if mode != _LAYOUT_ITERATION_MODE_CROP:
        return None
    if len(regions) != 1:
        raise ValueError('局部裁切迭代每次只能选择一个版面')
    bbox = regions[0].get('bbox') or {}
    try:
        x = float(bbox.get('x') or 0.0)
        y = float(bbox.get('y') or 0.0)
        w = float(bbox.get('w') or 0.0)
        h = float(bbox.get('h') or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError('所选版面缺少有效 bbox，无法执行局部裁切迭代') from exc

    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    w = max(0.0, min(1.0, w))
    h = max(0.0, min(1.0, h))
    if x + w > 1.0:
        w = max(0.0, 1.0 - x)
    if y + h > 1.0:
        h = max(0.0, 1.0 - y)
    if w < 0.01 or h < 0.01:
        raise ValueError('所选版面过小，无法执行局部裁切迭代')
    return {'x': x, 'y': y, 'w': w, 'h': h}


def _format_selected_regions_text(regions: List[Dict[str, Any]]) -> str:
    lines = []
    for index, region in enumerate(regions, start=1):
        bbox = region.get('bbox') or {}
        lines.append(
            f"{index}. {region.get('title') or region.get('region_id')} "
            f"({str(region.get('level') or '').upper()}级, {region.get('position_text')})；"
            f"bbox=({bbox.get('x', 0):.4f}, {bbox.get('y', 0):.4f}, {bbox.get('w', 0):.4f}, {bbox.get('h', 0):.4f})；"
            f"用户要求：{region.get('user_instruction', '') or '（未填写，需结合当前页理解自动补全）'}；"
            f"辨识度要求：{_LAYOUT_RECOGNITION_TEXT.get(region.get('recognition'), _LAYOUT_RECOGNITION_TEXT['gray'])}"
        )
    return '\n'.join(lines)


def _format_explicit_user_feedback(regions: List[Dict[str, Any]]) -> str:
    lines = []
    for region in regions:
        user_instruction = str(region.get('user_instruction') or '').strip()
        if not user_instruction:
            continue
        lines.append(f"- {region.get('title') or region.get('region_id')}：{user_instruction}")
    if lines:
        return '\n'.join(lines)
    return '（当前所选版面均未填写用户指令，将结合当前页理解与本子内上下文自动补全）'


def _format_layout_iteration_page_context(current_context: Dict[str, Any]) -> str:
    lines = [
        f"- T层补充：{current_context.get('t_focus_text', '') or '（空）'}",
        f"- 主要内容：{current_context.get('main_content', '') or '（空）'}",
        f"- 版面区域：{current_context.get('layout_regions_text', '') or '（空）'}",
        f"- 阅读顺序：{current_context.get('reading_order', '') or '（空）'}",
        f"- 手写/印刷关系：{current_context.get('handwriting_printing_relation', '') or '（空）'}",
        f"- 批注关系：{current_context.get('annotation_section', '') or '（空）'}",
        f"- 与前图关系：{current_context.get('continuity_text', '') or '（空）'}",
        f"- M层复核：{current_context.get('m_verification_text', '') or '（空）'}",
    ]
    return '\n'.join(lines)


def _load_layout_iteration_notebook_context(username: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from app_chat.ci._context import _filter_user_selected_context, _gather_notebook_context

        selected_files = manifest.get('selected_files') or []
        context_config = manifest.get('context_config') or {}
        notebook_ctx = _gather_notebook_context(username)
        return _filter_user_selected_context(
            notebook_ctx,
            username=username,
            selected_files=selected_files,
            context_docs=context_config.get('user_selected_docs'),
            context_card_ids=context_config.get('user_selected_card_ids'),
        )
    except Exception as error:
        print(f'[ci_layout_iter] 加载本子上下文失败: {error}')
        return {}


def _format_layout_iteration_notebook_context(notebook_ctx: Dict[str, Any]) -> str:
    if not isinstance(notebook_ctx, dict) or not notebook_ctx:
        return '（无可用本子上下文）'

    lines = [
        f"- 场景：{notebook_ctx.get('scene_name', '') or '未提供'} / {notebook_ctx.get('sub_scene_name', '') or '未提供'}",
        f"- 本子说明：{notebook_ctx.get('notebook_description', '') or '未提供'}",
        f"- 场景摘要：{notebook_ctx.get('scene_summary', '') or '未提供'}",
    ]

    doc_lines = []
    for doc in (notebook_ctx.get('doc_summaries') or [])[:3]:
        file_name = str(doc.get('file_name') or '未命名文档')
        summary = _truncate_text(doc.get('summary') or doc.get('pre_summary') or '', 240)
        if summary:
            doc_lines.append(f'- {file_name}：{summary}')
    if doc_lines:
        lines.append('### 关联文档摘要')
        lines.extend(doc_lines)

    card_lines = []
    for card in (notebook_ctx.get('card_summaries') or [])[:5]:
        title = _truncate_text(card.get('title') or '未命名卡片', 80)
        keywords = _truncate_text(card.get('keywords') or '', 120)
        preview = _truncate_text(card.get('preview') or '', 120)
        card_parts = [title]
        if keywords:
            card_parts.append(f'关键词:{keywords}')
        if preview:
            card_parts.append(preview)
        card_lines.append(f"- {' | '.join(card_parts)}")
    if card_lines:
        lines.append('### 本子卡片知识')
        lines.extend(card_lines)

    return '\n'.join(lines)


def _resolve_layout_iteration_filename(manifest: Dict[str, Any], unit_id: str) -> str:
    for unit in (manifest.get('input_units') or []):
        if not isinstance(unit, dict) or str(unit.get('unit_id') or '').strip() != unit_id:
            continue
        for key in ('display_name', 'source_file', 'file_name', 'filename'):
            value = str(unit.get(key) or '').strip()
            if value:
                return os.path.basename(value)
    return unit_id


def _build_layout_region_prompt(
    filename: str,
    regions: List[Dict[str, Any]],
    current_context: Dict[str, Any],
    overlay_item: Dict[str, Any],
    notebook_ctx: Dict[str, Any],
) -> Dict[str, Any]:
    region_batch_text = _format_selected_regions_text(regions)
    explicit_user_feedback = _format_explicit_user_feedback(regions)
    needs_context = any(not region.get('has_user_instruction') for region in regions)

    if not needs_context:
        user_text = CI_R_SINGLE_REGION_USER_ONLY_REWRITE_USER_PROMPT_TEMPLATE.format(
            filename=filename,
            region_batch_text=region_batch_text,
            explicit_user_feedback=explicit_user_feedback,
        )
        return {
            'system_prompt': CI_R_SINGLE_REGION_USER_ONLY_REWRITE_SYSTEM_PROMPT,
            'user_content': [{'type': 'text', 'text': user_text}],
            'used_context': False,
        }

    user_text = CI_R_SINGLE_REGION_PLANNER_USER_PROMPT_TEMPLATE.format(
        filename=filename,
        region_batch_text=region_batch_text,
        explicit_user_feedback=explicit_user_feedback,
        image_understanding_context=_format_layout_iteration_page_context(current_context),
        overlay_instruction_text=_truncate_text(overlay_item.get('instruction_text') or '（空）', 3000),
        notebook_context=_format_layout_iteration_notebook_context(notebook_ctx),
    )
    return {
        'system_prompt': CI_R_SINGLE_REGION_PLANNER_SYSTEM_PROMPT,
        'user_content': [{'type': 'text', 'text': user_text}],
        'used_context': True,
    }


def _normalize_revision_instruction_text(raw_text: Any) -> str:
    text = _normalize_llm_response_text(raw_text).strip()
    if text.startswith('```json'):
        text = text[7:].strip()
    elif text.startswith('```'):
        text = text[3:].strip()
    if text.endswith('```'):
        text = text[:-3].strip()
    return text.strip()


def _normalize_layout_region_identity_key(value: Any) -> str:
    text = str(value or '').strip().lower()
    if not text:
        return ''
    text = text.replace('—', '-').replace('－', '-')
    text = re.sub(r'[\s\-]+', '_', text)
    text = re.sub(r'[^a-z0-9_]', '', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text


def _extract_layout_region_planner_result(raw: Any, expected_region_ids: List[str]) -> Optional[Dict[str, Any]]:
    parsed = _parse_llm_json(raw, {})
    if not parsed:
        repaired = _repair_json_locally(_normalize_llm_response_text(raw))
        if repaired:
            try:
                parsed = json.loads(repaired)
            except Exception:
                parsed = {}
    if not isinstance(parsed, dict) or not parsed:
        return None

    instruction_text = _normalize_revision_instruction_text(parsed.get('instruction_text') or '')
    if not instruction_text:
        return None

    expected_region_set = set(expected_region_ids)
    expected_region_lookup: Dict[str, str] = {}
    for expected_region_id in expected_region_ids:
        normalized_key = _normalize_layout_region_identity_key(expected_region_id)
        if normalized_key and normalized_key not in expected_region_lookup:
            expected_region_lookup[normalized_key] = expected_region_id

    raw_target_ids = parsed.get('target_region_ids') or []
    target_region_ids = [str(region_id).strip() for region_id in raw_target_ids if str(region_id).strip()]
    if target_region_ids:
        filtered_ids: List[str] = []
        for region_id in target_region_ids:
            canonical_region_id = expected_region_lookup.get(_normalize_layout_region_identity_key(region_id), '')
            if canonical_region_id and canonical_region_id not in filtered_ids:
                filtered_ids.append(canonical_region_id)
        if set(filtered_ids) != expected_region_set:
            return None
        target_region_ids = filtered_ids
    else:
        target_region_ids = list(expected_region_ids)

    edit_goals = []
    for goal in (parsed.get('edit_goals') or [])[:6]:
        goal_text = _truncate_text(goal, 160)
        if goal_text:
            edit_goals.append(goal_text)

    return {
        'instruction_text': instruction_text,
        'target_region_ids': target_region_ids,
        'edit_goals': edit_goals,
        'preserve_rest': True,
        'used_context': bool(parsed.get('used_context', False)),
        'user_feedback_applied': bool(parsed.get('user_feedback_applied', False)),
        'summary': _truncate_text(parsed.get('summary') or '', 300),
    }


def _plan_layout_region_instruction_with_llm(
    system_prompt: str,
    user_content: List[Dict[str, Any]],
    expected_region_ids: List[str],
) -> Optional[Dict[str, Any]]:
    candidates = [
        ('claude-4-sonnet', _call_claude4_sonnet_text_llm, 2),
        ('qwen3.5-plus', _call_qwen35_plus_m_layer_llm, 1),
        ('qwen3.5-flash', _call_qwen35_m_layer_llm, 1),
    ]
    for model_name, caller, attempts in candidates:
        raw = caller(system_prompt, user_content, timeout=45, attempts=attempts)
        if not raw:
            continue
        parsed = _extract_layout_region_planner_result(raw, expected_region_ids)
        if parsed:
            parsed['model_name'] = model_name
            return parsed
        print(f'[ci_layout_iter] {model_name} 输出不可用，继续降级')
    return None


def _build_layout_region_fallback_instruction(regions: List[Dict[str, Any]]) -> str:
    parts: List[str] = ['请仅修改以下指定版面：']
    for region in regions:
        user_instruction = str(region.get('user_instruction') or '').strip()
        if user_instruction:
            action_text = f'按“{user_instruction}”执行修改'
        else:
            action_text = '结合当前页已有内容做最小必要整理，不新增未确认内容'
        parts.append(
            f"{region.get('position_text')}的{region.get('title') or region.get('region_id')}版面，"
            f"{action_text}，并{_LAYOUT_RECOGNITION_TEXT.get(region.get('recognition'), _LAYOUT_RECOGNITION_TEXT['gray'])}。"
        )
    parts.append('就改这些地方，其他不要变。')
    return ''.join(parts)


def build_layout_region_revision_instruction(
    username: str,
    analysis_id: str,
    unit_id: str,
    selected_regions: Any,
    iteration_mode: str = _LAYOUT_ITERATION_MODE_REWRITE,
    iter_context_updates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _paths, manifest, _r_layer, r_item, overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
    mode = _normalize_layout_iteration_mode(iteration_mode)
    resolved_regions = _validate_and_resolve_layout_regions(overlay_item, selected_regions, mode)
    current_context = _normalize_reproduction_iter_context(r_item.get('iter_context'), iter_context_updates)
    notebook_ctx = _load_layout_iteration_notebook_context(username, manifest)
    filename = _resolve_layout_iteration_filename(manifest, unit_id)
    prompt_payload = _build_layout_region_prompt(filename, resolved_regions, current_context, overlay_item, notebook_ctx)
    expected_region_ids = [str(region.get('region_id') or '').strip() for region in resolved_regions if str(region.get('region_id') or '').strip()]
    planner_result = _plan_layout_region_instruction_with_llm(
        prompt_payload['system_prompt'],
        prompt_payload['user_content'],
        expected_region_ids,
    )

    revision_instruction = _normalize_revision_instruction_text(
        (planner_result or {}).get('instruction_text') or ''
    )
    if not revision_instruction:
        revision_instruction = _build_layout_region_fallback_instruction(resolved_regions)
    if '其他不要变' not in revision_instruction and '其他地方不要变' not in revision_instruction:
        revision_instruction = revision_instruction.rstrip('。；; ') + '，就改这些地方，其他不要变。'

    return {
        'revision_instruction': _truncate_text(revision_instruction, 4000),
        'selected_regions': resolved_regions,
        'edit_region': _resolve_layout_iteration_edit_region(resolved_regions, mode),
        'overlay_item': overlay_item,
        'iteration_mode': mode,
        'planner_model': (planner_result or {}).get('model_name') or 'local_fallback',
        'planner_used_context': bool(prompt_payload.get('used_context')),
    }


def iterate_ci_layout_regions(
    task_id: str,
    username: str,
    analysis_id: str,
    unit_id: str,
    selected_regions: Any,
    iteration_mode: str = _LAYOUT_ITERATION_MODE_REWRITE,
    reference_image_b64: Optional[str] = None,
    reference_image_mime: str = 'image/png',
    image_quality: str = 'normal',
    iter_context_updates: Optional[Dict[str, Any]] = None,
) -> None:
    delegated = False
    try:
        _update_task(task_id, current_item=0, total_items=1, current_section=_LAYOUT_ITERATION_SECTION_REWRITE, completed=False, error='')
        rewritten = build_layout_region_revision_instruction(
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
            selected_regions=selected_regions,
            iteration_mode=iteration_mode,
            iter_context_updates=iter_context_updates,
        )
        delegated = True
        iterate_ci_reproduction_unit(
            task_id=task_id,
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
            revision_instruction=rewritten['revision_instruction'],
            edit_region=rewritten.get('edit_region'),
            reference_image_b64=reference_image_b64,
            reference_image_mime=reference_image_mime,
            image_quality=image_quality,
            iter_context_updates=iter_context_updates,
        )
    except Exception as exc:
        _update_task(task_id, current_section='失败', current_item=1, total_items=1, completed=True, error=str(exc))
        if not delegated:
            from app_chat.continuous_image_service import _set_reproduction_iterating

            _set_reproduction_iterating(username, analysis_id, unit_id, False)
        raise