"""
ci/t_layer.py — T 层模块：本体理解与多图整体语义归纳。

Phase 5.3 迁移：
    - _build_t_layer_m_section_digest
    - build_t_layer
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app_chat.ci._context import _load_related_doc_summaries
from app_chat.ci._llm import (
    _call_t_layer_llm,
    _image_path_to_base64_url,
    _normalize_llm_response_text,
    _parse_llm_json,
    _repair_json_locally,
)
from app_chat.ci._utils import _safe_json_dump, _update_task
from app_chat.ci_prompts import (
    CI_T_LAYER_SYSTEM_PROMPT,
    CI_T_LAYER_USER_PROMPT_TEMPLATE,
)


SECTION_ONTOLOGY = '本体理解中'


def _build_t_layer_m_section_digest(sec: Dict[str, Any]) -> str:
    cont_prev = sec.get('continuity_with_prev', {})
    if isinstance(cont_prev, dict):
        cont_type = cont_prev.get('type', '未知')
        cont_reason = cont_prev.get('reason', '')
        cont_str = f'{cont_type}（{cont_reason}）' if cont_reason else cont_type
    else:
        cont_str = str(cont_prev)

    m_quality = sec.get('m_quality', {}) if isinstance(sec.get('m_quality', {}), dict) else {}
    m_verification = sec.get('m_verification', {}) if isinstance(sec.get('m_verification', {}), dict) else {}
    m_patch = sec.get('m_patch', {}) if isinstance(sec.get('m_patch', {}), dict) else {}
    layout_regions = sec.get('layout_regions', []) if isinstance(sec.get('layout_regions', []), list) else []

    overall_verdict = str(m_quality.get('overall_verdict', '') or m_verification.get('overall_verdict', '') or 'weak')
    summary_coverage = str(m_quality.get('summary_coverage', '') or m_verification.get('summary_coverage', '') or 'weak')
    patch_applied = bool(m_patch.get('applied'))

    verified_region_ids = m_verification.get('verified_regions', []) if isinstance(m_verification.get('verified_regions', []), list) else []
    verified_index_set = set()
    for item in verified_region_ids:
        match = re.match(r'R(\d+)$', str(item or '').strip(), re.IGNORECASE)
        if match:
            verified_index_set.add(int(match.group(1)) - 1)

    preferred_regions: List[Dict[str, Any]] = []
    if verified_index_set:
        preferred_regions = [region for idx, region in enumerate(layout_regions) if idx in verified_index_set]
    if not preferred_regions:
        preferred_regions = layout_regions[:4]

    region_lines: List[str] = []
    for idx, region in enumerate(preferred_regions[:4], start=1):
        if isinstance(region, dict):
            region_type = str(region.get('type', '') or '其它')
            position = str(region.get('position', '') or '未标注')
            anchor = str(region.get('spatial_anchor', '') or '未标注')
            content = str(region.get('content', '') or '内容待确认')
            evidence = str(region.get('evidence_level', '') or 'medium')
            detail_parts: List[str] = []
            key_elements = region.get('key_elements', []) if isinstance(region.get('key_elements', []), list) else []
            visual_relations = region.get('visual_relations', []) if isinstance(region.get('visual_relations', []), list) else []
            if key_elements:
                detail_parts.append('elements=' + '、'.join([str(x) for x in key_elements[:4]]))
            if visual_relations:
                detail_parts.append('relations=' + '；'.join([str(x) for x in visual_relations[:2]]))
            if region.get('direction_notes'):
                detail_parts.append(f"direction={region.get('direction_notes', '')}")
            if region.get('relative_layout'):
                detail_parts.append(f"layout={region.get('relative_layout', '')}")
            if region.get('size_notes'):
                detail_parts.append(f"size={region.get('size_notes', '')}")
            if region.get('shape_notes'):
                detail_parts.append(f"shape={region.get('shape_notes', '')}")
            line = f'R{idx}: {region_type} | {position} | {anchor} | {content} | evidence={evidence}'
            if detail_parts:
                line += ' | ' + ' | '.join(detail_parts)
            region_lines.append(line)
        elif isinstance(region, str):
            region_lines.append(f'R{idx}: 其它 | 未标注 | 未标注 | {region[:40]} | evidence=low')

    uncertain_regions = m_verification.get('uncertain_regions', []) if isinstance(m_verification.get('uncertain_regions', []), list) else []
    missing_regions = m_verification.get('missing_regions', []) if isinstance(m_verification.get('missing_regions', []), list) else []
    uncertain_text = '；'.join([
        f"{str(item.get('region_id', '') or '未标注')}:{str(item.get('issue', '') or '问题待定')}"
        for item in uncertain_regions[:3] if isinstance(item, dict)
    ]) or '无'
    missing_text = '；'.join([
        f"{str(item.get('type', '') or '区域')}@{str(item.get('position', '') or '未知位置')}"
        for item in missing_regions[:3] if isinstance(item, dict)
    ]) or '无'

    main_content = (sec.get('main_content') or '')[:220]
    handwriting_relation = (sec.get('handwriting_printing_relation') or '')[:140]

    return (
        f"[{sec.get('unit_id', '')}] {sec.get('title', '')}\n"
        f"质量：overall={overall_verdict} | coverage={summary_coverage} | patch_applied={'yes' if patch_applied else 'no'}\n"
        f'主要内容：{main_content}\n'
        f"结构锚点：{' / '.join(region_lines) if region_lines else '（无可靠结构锚点）'}\n"
        f"手写印刷关系：{handwriting_relation or '（无）'}\n"
        f'复核提示：uncertain={uncertain_text} | missing={missing_text}\n'
        f'与前图关系：{cont_str}\n'
    )


def build_t_layer(username: str, selected_file_names: List[str], related_docs: List[str], d_layer: Dict[str, Any],
                  m_layer: Dict[str, Any], paths: Dict[str, str], task_id: str,
                  notebook_ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    _update_task(task_id, current_section=SECTION_ONTOLOGY, total_items=1, current_item=1)

    if notebook_ctx:
        scene_name = notebook_ctx.get('scene_name', '')
        sub_scene_name = notebook_ctx.get('sub_scene_name', '')
        scene_summary = notebook_ctx.get('scene_summary', '')
        notebook_description = notebook_ctx.get('notebook_description', '')
    else:
        from app_chat.scene_context_helper import get_scene_info_from_username

        scene_name, sub_scene_name, scene_summary, notebook_description = get_scene_info_from_username(username)

    sections = m_layer.get('sections', [])
    d_items = d_layer.get('items', [])

    related_doc_summaries = _load_related_doc_summaries(username, selected_file_names)

    doc_parts = []
    seen_doc_names: set = set()

    if notebook_ctx:
        for doc in notebook_ctx.get('doc_summaries', []):
            fn = doc.get('file_name', '')
            summary = doc.get('summary', '')
            if fn and summary and fn not in seen_doc_names:
                doc_parts.append(f"### {fn}\n{summary[:4000]}")
                seen_doc_names.add(fn)

    for doc in related_doc_summaries:
        fn = doc.get('file_name', '')
        if fn in seen_doc_names:
            continue
        part = f"### {fn}\n"
        if doc.get('pre_summary'):
            part += f"**文档摘要**：\n{doc['pre_summary'][:4000]}\n"
        if doc.get('pre_image_summary'):
            part += f"**图片摘要**：\n{doc['pre_image_summary'][:2000]}\n"
        doc_parts.append(part)
        seen_doc_names.add(fn)

    doc_summaries_section = '\n'.join(doc_parts) if doc_parts else '（无关联文档摘要）'

    card_lines = []
    if notebook_ctx:
        for card in notebook_ctx.get('card_summaries', []):
            title = card.get('title', '')
            kw = card.get('keywords', '')
            preview = card.get('preview', '')
            parts = [title]
            if kw:
                parts.append(f'关键词:{kw}')
            if preview:
                parts.append(preview)
            card_lines.append(f"- {' | '.join(p for p in parts if p)}")
    card_summaries_section = '\n'.join(card_lines) if card_lines else '（无卡片知识）'

    m_summary_parts = []
    for i, sec in enumerate(sections, start=1):
        m_summary_parts.append(f'{i}. ' + _build_t_layer_m_section_digest(sec))
    m_layer_summary_section = '\n'.join(m_summary_parts) if m_summary_parts else '（无M层摘要）'

    unit_map = {item['unit_id']: item for item in d_items}
    all_asset_paths: List[Tuple[str, str]] = []

    for sec in sections:
        uid = sec.get('unit_id', '')
        page_assets_dir = paths['page_assets']
        found = ''
        if os.path.isdir(page_assets_dir):
            for fn in sorted(os.listdir(page_assets_dir)):
                if fn.startswith(uid[1:].lstrip('0') and uid) or fn.startswith(uid):
                    found = os.path.join(page_assets_dir, fn)
                    break
            if not found:
                seq_prefix = uid.replace('u', '').zfill(3) + '_'
                for fn in sorted(os.listdir(page_assets_dir)):
                    if fn.startswith(seq_prefix):
                        found = os.path.join(page_assets_dir, fn)
                        break
        if found and os.path.exists(found):
            all_asset_paths.append((uid, found))

    if len(all_asset_paths) > 8:
        step = len(all_asset_paths) / 8
        sampled = [all_asset_paths[int(i * step)] for i in range(8)]
    else:
        sampled = all_asset_paths

    image_filenames_section = '\n'.join(
        [f'{j + 1}. [{uid}] {os.path.basename(ap)}' for j, (uid, ap) in enumerate(sampled)]
    )

    user_text = CI_T_LAYER_USER_PROMPT_TEMPLATE.format(
        total_count=len(all_asset_paths),
        scene_name=scene_name or '未指定',
        sub_scene_name=sub_scene_name or '未指定',
        scene_summary=(scene_summary or '未提供')[:600],
        notebook_description=(notebook_description or '未提供')[:400],
        doc_summaries_section=doc_summaries_section,
        card_summaries_section=card_summaries_section,
        m_layer_summary_section=m_layer_summary_section,
        image_filenames_section=image_filenames_section,
    )
    user_content: List[Any] = [{'type': 'text', 'text': user_text}]
    for uid, ap in sampled:
        b64 = _image_path_to_base64_url(ap)
        if b64:
            user_content.append({'type': 'image_url', 'image_url': {'url': b64}})

    print(f'[ci] build_t_layer 调用 T 层 LLM（{len(sampled)}/{len(all_asset_paths)} 张图）...')
    raw_response = _call_t_layer_llm(CI_T_LAYER_SYSTEM_PROMPT, user_content, timeout=150)
    parsed = _parse_llm_json(raw_response, {}) if raw_response else {}
    repaired_raw_response = None

    if raw_response and not parsed:
        print('[ci] build_t_layer 原始响应解析失败，尝试执行 JSON 修复重试...')
        repaired_raw_response = _repair_json_locally(raw_response)
        parsed = _parse_llm_json(repaired_raw_response, {}) if repaired_raw_response else {}
        if parsed:
            print('[ci] build_t_layer JSON 修复重试成功')

    if parsed:
        core_theme = parsed.get('core_theme', '')
        overall_summary = parsed.get('overall_summary', '')
        group_relations = parsed.get('group_relations', [])
        doc_relations = parsed.get('doc_relations', [])
        scene_meaning = parsed.get('scene_meaning', {
            'scene_name': scene_name, 'sub_scene_name': sub_scene_name,
            'scene_summary_binding': '', 'meaning': '',
        })
        blind_spots = parsed.get('blind_spots', [])
        internal_friction = parsed.get('internal_friction', [])
        zpd_next_step = parsed.get('zpd_next_step', '')
        next_actions = parsed.get('next_actions', [])
        semantic_layer_candidate = parsed.get('semantic_layer_candidate', '')
        tribal_candidate = parsed.get('tribal_candidate', '')
        print(f'[ci] build_t_layer T 层 LLM 成功')
    else:
        raw_preview = _normalize_llm_response_text(raw_response).strip().replace('\n', ' ')
        if raw_preview:
            print(f'[ci] build_t_layer T 层返回存在，但 JSON 解析失败，响应片段: {raw_preview[:240]}')
        repaired_preview = _normalize_llm_response_text(repaired_raw_response).strip().replace('\n', ' ')
        if repaired_preview:
            print(f'[ci] build_t_layer JSON 修复重试后仍解析失败，修复响应片段: {repaired_preview[:240]}')
        print(f'[ci] build_t_layer T 层 LLM 失败，使用降级兜底')
        overall_summary_parts = []
        for sec in sections[:6]:
            content = (sec.get('main_content') or '').strip()
            if content:
                overall_summary_parts.append(content[:260])
        overall_summary = '\n'.join(overall_summary_parts) if overall_summary_parts else '已完成连续图片理解，但可用信息有限。'

        core_theme = '连续图片围绕同一学习/推导任务展开，包含识别层、结构层与语义层的递进信息。'
        if sections:
            first_title = sections[0].get('title', '')
            core_theme = f'以「{first_title}」为起点的连续认知材料，呈现逐页推进与补充。'

        group_relations = []
        for sec in sections:
            cont_prev = sec.get('continuity_with_prev', {})
            if isinstance(cont_prev, dict):
                relation_type = cont_prev.get('type', '未知')
                reason = cont_prev.get('reason', 'LLM降级')
            else:
                relation_type = str(cont_prev)
                reason = 'M层启发式'
            group_relations.append({
                'seq': sec.get('seq', 0),
                'unit_id': sec.get('unit_id', ''),
                'relation_type': relation_type,
                'reason': reason,
            })

        doc_relations = []
        for fn in seen_doc_names:
            doc_relations.append({
                'file_name': fn,
                'relation': '图文存在语义印证关系，可用于补充背景与术语定义。',
                'key_point': 'LLM降级，无法精确分析',
            })

        scene_meaning = {
            'scene_name': scene_name,
            'sub_scene_name': sub_scene_name,
            'scene_summary_binding': '已将连续图片理解绑定到当前场景语境。',
            'meaning': '连续图片承载了当前场景下的学习记录，可用于后续问答与知识萃取。',
        }

        low_conf_units = [item for item in d_items if item.get('low_confidence_hint')]
        blind_spots = []
        total_grey = sum(item.get('zone_summary', {}).get('grey', 0) for item in d_items)
        total_black = sum(item.get('zone_summary', {}).get('black', 0) for item in d_items)
        if total_black > 0:
            blind_spots.append(f'{total_black} 个区域OCR完全不可识别（黑区），已用视觉描述替代但可能丢失文字信息，建议回看原图。')
        if total_grey > 0:
            grey_repaired = sum(1 for item in d_items for r in item.get('regions', [])
                                if r.get('zone') == 'grey' and r.get('content_repaired'))
            if grey_repaired > 0:
                blind_spots.append(f'{total_grey} 个区域OCR部分不确定（灰区），其中 {grey_repaired} 个已通过语义修复，但修复准确性仍需验证。')
            else:
                blind_spots.append(f'{total_grey} 个区域OCR部分不确定（灰区），建议重点检查这些区域的识别准确性。')
        if low_conf_units and not total_grey and not total_black:
            blind_spots.append(f'{len(low_conf_units)} 个单元OCR置信不足，建议回看原图与布局态。')
        blind_spots = blind_spots or ['当前样本中未发现明显OCR盲区，可重点检查逻辑跳转处。']

        jump_count = sum(
            1 for s in sections
            if isinstance(s.get('continuity_with_prev'), dict)
            and s['continuity_with_prev'].get('type') in ('主题跳转', '中断')
            or isinstance(s.get('continuity_with_prev'), str)
            and '跳转' in s.get('continuity_with_prev', '')
        )
        internal_friction = [f'检测到 {jump_count} 处主题跳转，可能引发理解振荡。'] if jump_count else \
            ['整体连续性较好，内耗风险主要来自细节遗漏而非结构断裂。']

        zpd_next_step = '优先聚焦连续链路中的断点页，补充该页关键定义与推导依据。'
        next_actions = [
            '先按章节回看每页的版面结构与OCR明细，定位断点。',
            '对低置信页执行二次OCR或人工校对，减少误读。',
            '将连续组关键结论沉淀为可复用的知识条目。',
        ]
        semantic_layer_candidate = '当前信息不足以形成稳定语义层萃取（LLM降级模式）。'
        tribal_candidate = '暂无部落知识萃取内容（LLM降级模式）。'

    t_layer = {
        'layer': 'T',
        'overall_summary': overall_summary,
        'core_theme': core_theme,
        'group_relations': group_relations,
        'doc_relations': doc_relations,
        'scene_meaning': scene_meaning,
        'blind_spots': blind_spots,
        'internal_friction': internal_friction,
        'zpd_next_step': zpd_next_step,
        'next_actions': next_actions,
        'semantic_layer_candidate': semantic_layer_candidate,
        'tribal_candidate': tribal_candidate,
        'related_docs': related_docs,
    }

    _safe_json_dump(paths['t_layer'], t_layer)

    def _fmt_list(lst: Any) -> str:
        if isinstance(lst, list):
            return '\n'.join([f'- {x}' for x in lst]) if lst else '- （无）'
        return f'- {lst}' if lst else '- （无）'

    def _fmt_relations(lst: Any) -> str:
        if not isinstance(lst, list):
            return str(lst)
        lines = []
        for item in lst:
            if isinstance(item, dict):
                kv = ' | '.join(f'{k}: {v}' for k, v in item.items())
                lines.append(f'- {kv}')
            else:
                lines.append(f'- {item}')
        return '\n'.join(lines) if lines else '（无）'

    if isinstance(scene_meaning, dict):
        sm_text = (
            f"- 场景：{scene_meaning.get('scene_name', '')}\n"
            f"- 子场景：{scene_meaning.get('sub_scene_name', '')}\n"
            f"- 场景绑定：{scene_meaning.get('scene_summary_binding', '')}\n"
            f"- 认知贡献：{scene_meaning.get('meaning', '')}"
        )
    else:
        sm_text = str(scene_meaning)

    markdown_lines = [
        '# 整体纪要（T层）',
        '',
        f'## 核心主题\n{core_theme}',
        '',
        '## 总体理解',
        overall_summary,
        '',
        '## 多图连续关系',
        _fmt_relations(group_relations),
        '',
        '## 关联文档关系',
        _fmt_relations(doc_relations) if doc_relations else '（无关联文档）',
        '',
        '## 场景语义绑定',
        sm_text,
        '',
        '## 盲区',
        _fmt_list(blind_spots),
        '',
        '## 内耗区',
        _fmt_list(internal_friction),
        '',
        '## 最近发展区建议',
        zpd_next_step,
        '',
        '## 下一步动作',
        _fmt_list(next_actions),
        '',
        '## 语义层萃取',
        str(semantic_layer_candidate),
        '',
        '## 部落知识候选',
        str(tribal_candidate),
    ]
    with open(paths['t_layer_md'], 'w', encoding='utf-8') as f_md:
        f_md.write('\n'.join(markdown_lines))

    return t_layer