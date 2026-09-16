# -*- coding: utf-8 -*-
"""
CI 理解结果适配器（只读封装层）

将「连续图片认知理解」(CI) 的 D-M-T 三层分析结果，以及图片上传时
由 ``summarize_image()`` 生成的理解结果，统一封装为标准化的
「理解摘要」(CIDigest)，供文生图等下游模块消费。

数据源优先级：
  1. CI 系统的 D-M-T 三层分析结果（精确匹配 → 超集匹配）
  2. 上传时写入 global_var / Chroma 的 ``summarize_image()`` 结果
  3. 上传时写入磁盘的 PreImageOrigin / PreImageSummary 文件

设计原则：
  1. 只读 —— 仅读取已有结果，不修改 CI 系统或上传流程的任何数据。
  2. 解耦 —— 上游结构变化时只需调整本文件的字段映射，下游接口不变。
  3. 稳定输出 —— CIDigest 字典结构字段只增不删、语义不变。
"""

from __future__ import annotations

import os
import importlib
from typing import Optional, List, Dict, Any

from app_chat.continuous_image_service import (
    get_ci_result,
    query_ci_analyses,
    build_analysis_id,
    CIIndexManager,
    _ci_dmt_root,
    _ci_d_cache_root,
)
from llm_langchain import global_var
from llm_langchain import util
from llm_langchain.parse_input import get_user_db_path, embeddings

# ════════════════════════════════════════════════════════════════
# 公开接口
# ════════════════════════════════════════════════════════════════


def fetch_ci_digest(username: str, analysis_id: str) -> Dict[str, Any]:
    """按 analysis_id 获取理解摘要。

    Args:
        username:     用户名
        analysis_id:  CI 分析 ID（如 ``single_abc123`` / ``multi_def456``）

    Returns:
        CIDigest 字典（见下方 ``_build_digest``），若分析不存在或未完成
        则返回 ``{'ok': False, 'error': '...'}``。
    """
    raw = get_ci_result(username, analysis_id)
    if raw.get('error_num', 1) != 0:
        return {'ok': False, 'error': raw.get('msg', '分析结果不存在或读取失败')}
    return _build_digest(username, analysis_id, raw, result_layers='t')


def fetch_ci_digest_by_files(
    username: str,
    files: List[str],
    mode: Optional[str] = None,
    result_layers: str = 't',
) -> Dict[str, Any]:
    """按文件列表查找最佳匹配的已完成分析，返回理解摘要。

    查找优先级:
      1. 精确匹配（文件集合完全一致）
      2. 超集匹配（已有分析的文件集包含当前文件集）

    Args:
        username: 用户名
        files:    文件名列表（与上传时一致）
        mode:     ``'single'`` / ``'group'`` / ``None``（自动推断）
        result_layers: ``'t'`` / ``'tm'`` / ``'dmt'``，默认 ``'t'``

    Returns:
        CIDigest 字典，若未找到已完成的分析则
        返回 ``{'ok': False, 'error': '...'}``。
    """
    if not files:
        return {'ok': False, 'error': 'files 不能为空'}

    if mode is None:
        mode = 'single' if len(files) == 1 else 'group'

    # 1) 精确匹配
    analysis_id = build_analysis_id(mode, files)
    rec = CIIndexManager.find_by_id(username, analysis_id)
    if rec and rec.get('status') == 'completed':
        return fetch_ci_digest_with_layers(username, analysis_id, result_layers=result_layers)

    # 2) 超集匹配（仅 group 模式有意义）
    if len(files) > 1:
        sup = CIIndexManager.find_superset_group(username, files)
        if sup:
            return fetch_ci_digest_with_layers(username, sup['analysis_id'], result_layers=result_layers)

    # 3) 单图模式下尝试反向查询
    if mode == 'single' and len(files) == 1:
        q = query_ci_analyses(username, files)
        singles = [s for s in q.get('singles', []) if s.get('status') == 'completed']
        if singles:
            return fetch_ci_digest_with_layers(username, singles[0]['analysis_id'], result_layers=result_layers)

    # 4) 降级：使用图片上传时的理解结果（global_var / PreImageOrigin 文件）
    upload_digest = _try_upload_time_digest(username, files, result_layers=result_layers)
    if upload_digest:
        return upload_digest

    return {'ok': False, 'error': '未找到已完成的分析结果，请先执行图片理解'}


def list_completed_digests(username: str, files: List[str]) -> List[Dict[str, Any]]:
    """列出指定文件关联的所有已完成分析的摘要信息（仅元数据，不含完整内容）。

    用于让调用方了解可选用哪些 analysis_id，再按需调用 ``fetch_ci_digest``。

    Returns:
        元素格式::

            {
                'analysis_id': str,
                'mode': 'single' | 'group',
                'files': [str, ...],
                'created_at': str,
            }
    """
    q = query_ci_analyses(username, files)
    out = []
    for rec in q.get('singles', []) + q.get('groups', []):
        if rec.get('status') == 'completed':
            out.append({
                'analysis_id': rec['analysis_id'],
                'mode': rec.get('mode', ''),
                'files': rec.get('files', []),
                'created_at': rec.get('created_at', ''),
            })
    return out


def fetch_upload_digest(
    username: str,
    files: List[str],
    result_layers: str = 't',
) -> Dict[str, Any]:
    """仅从上传时的理解结果构建摘要（不查 CI 分析）。

    当调用方明确知道图片尚未经过 CI 分析、只想使用上传时
    ``summarize_image()`` 的结果时，可直接调用本函数。

    数据源优先级：
            1. ``global_var`` 内存态 split_docs（上传后未重启时可用）
            2. Chroma 持久化向量库中的图片理解文档
            3. ``pre_image_summary/`` 目录下的 PreImageOrigin / PreImageSummary 文件

    Args:
        username: 用户名（格式：``用户名_本子名``）
        files:    文件名列表
        result_layers: ``'t'`` / ``'tm'`` / ``'dmt'``，上传时来源会尽量兼容

    Returns:
        CIDigest 字典（``source='upload'``），或 ``{'ok': False, ...}``。
    """
    result = _try_upload_time_digest(username, files, result_layers=result_layers)
    if result:
        return result
    return {'ok': False, 'error': '未找到上传时的图片理解结果'}


def fetch_ci_digest_with_layers(
    username: str,
    analysis_id: str,
    result_layers: str = 't',
) -> Dict[str, Any]:
    """按 analysis_id 获取理解摘要，并指定用于生图的层级组合。"""
    raw = get_ci_result(username, analysis_id)
    if raw.get('error_num', 1) != 0:
        return {'ok': False, 'error': raw.get('msg', '分析结果不存在或读取失败')}
    return _build_digest(username, analysis_id, raw, result_layers=result_layers)


# ════════════════════════════════════════════════════════════════
# 内部实现
# ════════════════════════════════════════════════════════════════


def _try_upload_time_digest(
    username: str,
    files: List[str],
    result_layers: str = 't',
) -> Optional[Dict[str, Any]]:
    """尝试从上传时的理解结果构建 CIDigest。

    数据源优先级：
            1. global_var 内存态中 type='image' 的 Document（服务未重启时可用）
            2. Chroma 持久化向量库中的图片理解文档
            3. pre_image_summary 目录下 PreImageOrigin / PreImageSummary 文件（持久化）
    """
    if not files:
        return None

    units: List[Dict[str, Any]] = []
    user_dir = os.path.normpath(os.path.join('.', 'received_dir', 'user_raw_file', username))

    for filename in files:
        content_text = _get_upload_image_content(username, filename)
        if not content_text:
            continue

        asset_path = _resolve_upload_asset_path(user_dir, filename)
        units.append({
            'unit_id': f'upload_{filename}',
            'seq': len(units) + 1,
            'source_file': filename,
            'page': 1,
            'title': filename,
            'main_content': content_text,
            'ocr_text': '',
            'layout_regions': [],
            'reading_order': '',
            'continuity_with_prev': {},
            'asset_abs_path': asset_path,
        })

    if not units:
        return None

    mode = 'single' if len(units) == 1 else 'group'

    # 合成文本（复用现有逻辑，T 层为空）
    t_stub: Dict[str, Any] = {}
    composite = _build_composite_text(mode, files, t_stub, units, result_layers=result_layers, source='upload')

    return {
        'ok': True,
        'analysis_id': '',
        'mode': mode,
        'source': 'upload',
        'result_layers': _normalize_result_layers(result_layers),
        'source_files': files,
        # T 层（上传时无 T 层，留空）
        'core_theme': '',
        'overall_summary': '',
        'blind_spots': [],
        'internal_friction': [],
        'zpd_next_step': '',
        'next_actions': [],
        'scene_meaning': {},
        'group_relations': [],
        # 逐图
        'units': units,
        # 文生图合成
        'composite_text': composite,
    }


def _get_upload_image_content(username: str, filename: str) -> Optional[str]:
    """从 global_var / Chroma / PreImage 文件中获取单个文件的上传时理解文本。"""
    # 1) global_var 内存态
    docs = global_var.get_user_split(username, filename)
    if docs:
        image_texts = []
        for doc in docs:
            meta = getattr(doc, 'metadata', {}) or {}
            if meta.get('type') == 'image':
                pc = getattr(doc, 'page_content', '') or ''
                if pc.strip():
                    image_texts.append(pc.strip())
        if image_texts:
            return "\n\n".join(image_texts)

    # 2) Chroma 持久化向量库
    chroma_text = _get_upload_image_content_from_chroma(username, filename)
    if chroma_text:
        return chroma_text

    # 3) PreImageOrigin / PreImageSummary 文件（持久化）
    file_base = os.path.splitext(filename)[0]
    pre_dir = os.path.join('.', 'received_dir', 'user_raw_file', username, 'pre_image_summary')

    for suffix in (
        f'{file_base}_PreImageOrigin_pdf.md',
        f'{file_base}_PreImageSummary_pdf.md',
    ):
        path = os.path.join(pre_dir, suffix)
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read().strip()
                if text:
                    return text
            except Exception:
                pass

    return None


def _get_upload_image_content_from_chroma(username: str, filename: str) -> Optional[str]:
    """从 Chroma 持久化向量库读取上传阶段写入的图片理解文本。"""
    try:
        chroma_module = importlib.import_module('langchain_chroma.vectorstores')
        Chroma = getattr(chroma_module, 'Chroma')

        actual_db_path, _, _ = get_user_db_path(username)
        collection_name = util.construct_collection(username)
        vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=actual_db_path,
        )

        file_path = util.construct_file_path(username, filename)
        rows = vector_store.get(where={'source': file_path})
        ids = rows.get('ids', []) or []
        documents = rows.get('documents', []) or []
        metadatas = rows.get('metadatas', []) or []
        if not ids or not documents:
            return None

        ordered = []
        for idx, doc_id in enumerate(ids):
            meta = metadatas[idx] if idx < len(metadatas) else {}
            if (meta or {}).get('type') != 'image':
                continue
            content = documents[idx] if idx < len(documents) else ''
            if not str(content).strip():
                continue
            ordered.append((_extract_seq_from_doc_id(doc_id, idx), str(content).strip()))

        if not ordered:
            return None

        ordered.sort(key=lambda x: x[0])
        return "\n\n".join(text for _, text in ordered)
    except Exception:
        return None


def _extract_seq_from_doc_id(doc_id: str, default: int = 0) -> int:
    """从向量库文档 ID 尾部提取顺序号。"""
    try:
        return int(str(doc_id).rsplit('_', 1)[-1])
    except Exception:
        return default


def _resolve_upload_asset_path(user_dir: str, filename: str) -> Optional[str]:
    """在用户文件目录下查找原始图片文件。"""
    path = os.path.normpath(os.path.join(user_dir, filename))
    if os.path.isfile(path):
        return path.replace('\\', '/')
    return None


def _build_digest(username: str, analysis_id: str, raw: dict, result_layers: str = 't') -> Dict[str, Any]:
    """将 CI 原始结果转换为标准化 CIDigest。

    CIDigest 顶层结构::

        {
            'ok': True,
            'analysis_id': str,
            'mode': 'single' | 'group',
            'source_files': [str, ...],

            # ── T 层摘要 ──
            'core_theme': str,
            'overall_summary': str,
            'blind_spots': [str, ...],
            'internal_friction': [str, ...],
            'zpd_next_step': str,
            'next_actions': [str, ...],
            'scene_meaning': { ... },
            'group_relations': [ ... ],

            # ── 逐图单元 ──
            'units': [
                {
                    'unit_id': str,
                    'seq': int,
                    'source_file': str,
                    'page': int,
                    'title': str,
                    'main_content': str,          # M 层摘要
                    'ocr_text': str,              # D 层原文
                    'layout_regions': [...],
                    'reading_order': str,
                    'continuity_with_prev': {...},
                    'asset_abs_path': str | None,  # 原图绝对路径
                },
                ...
            ],

            # ── 用于文生图的合成文本 ──
            'composite_text': str,
        }
    """
    manifest = raw.get('manifest') or {}
    d_layer = raw.get('d_layer') or {}
    m_layer = raw.get('m_layer') or {}
    t_layer = raw.get('t_layer') or {}

    mode = manifest.get('mode', 'single')
    source_files = manifest.get('selected_files') or manifest.get('files') or []

    # 按 unit_id 索引 D 层
    d_map: Dict[str, dict] = {}
    for item in d_layer.get('items', []):
        d_map[item.get('unit_id', '')] = item

    # 构建 units
    units: List[Dict[str, Any]] = []
    for sec in m_layer.get('sections', []):
        uid = sec.get('unit_id', '')
        d_item = d_map.get(uid, {})
        asset_path = _resolve_asset_path(username, analysis_id, sec, manifest)
        ocr_text_raw = d_item.get('ocr_text', '')
        ocr_text = d_item.get('ocr_text_enhanced', '') or ocr_text_raw
        units.append({
            'unit_id': uid,
            'seq': sec.get('seq', 0),
            'source_file': sec.get('source_file', ''),
            'page': sec.get('page', 1),
            'title': sec.get('title', ''),
            'main_content': sec.get('main_content', ''),
            'ocr_text': ocr_text,
            'ocr_text_raw': ocr_text_raw,
            'layout_regions': sec.get('layout_regions', []),
            'reading_order': sec.get('reading_order', ''),
            'continuity_with_prev': sec.get('continuity_with_prev', {}),
            'handwriting_printing_relation': sec.get('handwriting_printing_relation', ''),
            'annotation_relation': sec.get('annotation_relation', ''),
            'm_quality': sec.get('m_quality', {}),
            'm_verification': sec.get('m_verification', {}),
            'm_patch': sec.get('m_patch', {}),
            'asset_abs_path': asset_path,
        })

    # 合成文本
    result_layers = _normalize_result_layers(result_layers)
    composite = _build_composite_text(mode, source_files, t_layer, units, result_layers=result_layers, source='ci')

    return {
        'ok': True,
        'analysis_id': analysis_id,
        'mode': mode,
        'source': 'ci',
        'result_layers': result_layers,
        'source_files': source_files,
        # T 层
        'core_theme': t_layer.get('core_theme', ''),
        'overall_summary': t_layer.get('overall_summary', ''),
        'blind_spots': t_layer.get('blind_spots', []),
        'internal_friction': t_layer.get('internal_friction', []),
        'zpd_next_step': t_layer.get('zpd_next_step', ''),
        'next_actions': t_layer.get('next_actions', []),
        'scene_meaning': t_layer.get('scene_meaning', {}),
        'group_relations': t_layer.get('group_relations', []),
        # 逐图
        'units': units,
        # 文生图合成
        'composite_text': composite,
    }


def _resolve_asset_path(
    username: str, analysis_id: str, section: dict, manifest: dict,
) -> Optional[str]:
    """尝试定位原图的绝对路径（在 page_assets / d_cache / 用户文件目录中查找）。"""
    source_file = section.get('source_file', '')
    # 1) analysis 目录下的 page_assets
    dmt_root = _ci_dmt_root(username)
    candidates = []
    asset_rel = ''
    for unit_info in manifest.get('input_units', []):
        if unit_info.get('unit_id') == section.get('unit_id'):
            asset_rel = unit_info.get('asset_path', '')
            break
    if asset_rel:
        candidates.append(os.path.normpath(os.path.join(dmt_root, analysis_id, asset_rel)))

    # 2) d_cache 中的 asset
    d_cache = _ci_d_cache_root(username)
    if source_file:
        candidates.append(os.path.normpath(os.path.join(d_cache, source_file, 'asset.png')))

    # 3) 用户原始文件目录
    user_dir = os.path.normpath(os.path.join('.', 'received_dir', 'user_raw_file', username))
    if source_file:
        candidates.append(os.path.normpath(os.path.join(user_dir, source_file)))

    for c in candidates:
        if os.path.isfile(c):
            return c.replace('\\', '/')
    return None


def _build_composite_text(
    mode: str,
    source_files: list,
    t_layer: dict,
    units: List[Dict[str, Any]],
    result_layers: str = 't',
    source: str = 'ci',
) -> str:
    """将 D-M-T 三层理解结果合成为一段结构化的文本，供文生图 Prompt 直接使用。

    合成策略：
    - ``t``: 仅使用 T 层
    - ``tm``: 使用 T + M 层
    - ``dmt``: 使用 D + M + T 三层
    - 对上传时来源（source=upload），由于缺少 D/T 分层，统一退化为上传时理解文本
    """
    parts: List[str] = []
    result_layers = _normalize_result_layers(result_layers)

    if source == 'upload':
        for u in units:
            title = u.get('title') or u.get('source_file') or ''
            main = (u.get('main_content') or '').strip()
            if main:
                parts.append(f"【{title}】\n{main}")
        return "\n\n".join(parts)

    def _format_m_quality_text(unit: dict) -> str:
        quality = unit.get('m_quality', {}) if isinstance(unit.get('m_quality', {}), dict) else {}
        overall = quality.get('overall_verdict', 'weak') or 'weak'
        coverage = quality.get('summary_coverage', 'weak') or 'weak'
        patch_applied = 'yes' if quality.get('patch_applied') else 'no'
        verified = quality.get('verified_region_count', 0)
        uncertain = quality.get('uncertain_region_count', 0)
        missing = quality.get('missing_region_count', 0)
        return f'overall={overall} | coverage={coverage} | patch_applied={patch_applied} | verified={verified} | uncertain={uncertain} | missing={missing}'

    def _format_m_verification_text(unit: dict) -> str:
        verification = unit.get('m_verification', {}) if isinstance(unit.get('m_verification', {}), dict) else {}
        verified_regions = verification.get('verified_regions', []) if isinstance(verification.get('verified_regions', []), list) else []
        uncertain_regions = verification.get('uncertain_regions', []) if isinstance(verification.get('uncertain_regions', []), list) else []
        missing_regions = verification.get('missing_regions', []) if isinstance(verification.get('missing_regions', []), list) else []
        verified_text = ', '.join([str(item) for item in verified_regions[:4]]) or '无'
        uncertain_text = '；'.join([
            f"{str(item.get('region_id', '') or '未标注')}:{str(item.get('issue', '') or '待确认')}"
            for item in uncertain_regions[:3] if isinstance(item, dict)
        ]) or '无'
        missing_text = '；'.join([
            f"{str(item.get('type', '') or '区域')}@{str(item.get('position', '') or '未知位置')}"
            for item in missing_regions[:3] if isinstance(item, dict)
        ]) or '无'
        return f'verified={verified_text} | uncertain={uncertain_text} | missing={missing_text}'

    def _format_m_patch_text(unit: dict) -> str:
        patch = unit.get('m_patch', {}) if isinstance(unit.get('m_patch', {}), dict) else {}
        return f"triggered={'yes' if patch.get('triggered') else 'no'} | applied={'yes' if patch.get('applied') else 'no'} | reason={str(patch.get('reason', '') or 'none')}"

    # ── T 层概览 ──
    core_theme = (t_layer.get('core_theme') or '').strip()
    overall = (t_layer.get('overall_summary') or '').strip()

    if result_layers in ('t', 'tm', 'dmt'):
        if core_theme:
            parts.append(f"【核心主题】{core_theme}")
        if overall:
            parts.append(f"【整体摘要】\n{overall}")

        relations = t_layer.get('group_relations', [])
        if relations:
            rel_lines = []
            for r in relations:
                rel_lines.append(
                    f"  第{r.get('seq', '?')}图（{r.get('unit_id', '')}）"
                    f"—— {r.get('relation_type', '')}：{r.get('reason', '')}"
                )
            parts.append("【多图连续关系】\n" + "\n".join(rel_lines))

        zpd = (t_layer.get('zpd_next_step') or '').strip()
        if zpd:
            parts.append(f"【认知建议】{zpd}")

        blind = t_layer.get('blind_spots', [])
        if blind and not (len(blind) == 1 and '不足' in blind[0]):
            parts.append("【认知盲区】" + "；".join(blind))

    if result_layers in ('tm', 'dmt'):
        for u in units:
            title = u.get('title') or u.get('source_file') or ''
            main = (u.get('main_content') or '').strip()
            if main:
                parts.append(f"【{title}】\n{main}")

            quality_text = _format_m_quality_text(u)
            verification_text = _format_m_verification_text(u)
            patch_text = _format_m_patch_text(u)
            parts.append(f"【M层质量】{quality_text}")
            parts.append(f"【M层复核】{verification_text}")
            parts.append(f"【M层补洞】{patch_text}")

            regions = u.get('layout_regions', [])
            if regions:
                region_lines = []
                for r in regions[:8]:
                    if isinstance(r, dict):
                        detail_parts = []
                        key_elements = r.get('key_elements', []) if isinstance(r.get('key_elements', []), list) else []
                        visual_relations = r.get('visual_relations', []) if isinstance(r.get('visual_relations', []), list) else []
                        uncertain_details = r.get('uncertain_details', []) if isinstance(r.get('uncertain_details', []), list) else []
                        if key_elements:
                            detail_parts.append('elements=' + '、'.join([str(x) for x in key_elements[:5]]))
                        if visual_relations:
                            detail_parts.append('relations=' + '；'.join([str(x) for x in visual_relations[:3]]))
                        if r.get('direction_notes'):
                            detail_parts.append(f"direction={r.get('direction_notes', '')}")
                        if r.get('relative_layout'):
                            detail_parts.append(f"layout={r.get('relative_layout', '')}")
                        if r.get('size_notes'):
                            detail_parts.append(f"size={r.get('size_notes', '')}")
                        if r.get('shape_notes'):
                            detail_parts.append(f"shape={r.get('shape_notes', '')}")
                        if uncertain_details:
                            detail_parts.append('uncertain=' + '；'.join([str(x) for x in uncertain_details[:2]]))
                        line = f"  - {r.get('type', '')}（{r.get('position', '')}/{r.get('spatial_anchor', '')}）：{r.get('content', '')} [evidence={r.get('evidence_level', '')}]"
                        if detail_parts:
                            line += ' | ' + ' | '.join(detail_parts)
                        region_lines.append(line)
                    elif isinstance(r, str):
                        region_lines.append(f"  - {r}")
                if region_lines:
                    parts.append("【版面区域】\n" + "\n".join(region_lines))

            reading_order = (u.get('reading_order') or '').strip()
            if reading_order:
                parts.append(f"【阅读顺序】{reading_order}")

            handwriting = (u.get('handwriting_printing_relation') or '').strip()
            if handwriting:
                parts.append(f"【手写/印刷关系】{handwriting}")

            annotation = (u.get('annotation_relation') or '').strip()
            if annotation:
                parts.append(f"【批注关系】{annotation}")

            cont = u.get('continuity_with_prev') or {}
            if isinstance(cont, dict) and (cont.get('type') or cont.get('reason')):
                cont_text = cont.get('type', '')
                if cont.get('reason'):
                    cont_text += f"：{cont.get('reason')}"
                parts.append(f"【与前图关系】{cont_text}")

    if result_layers == 'dmt':
        for u in units:
            ocr = (u.get('ocr_text') or '').strip()
            if ocr:
                parts.append(f"【原始文字（节选）】\n{ocr[:2000]}")

    return "\n\n".join(parts)


def _normalize_result_layers(result_layers: str) -> str:
    value = (result_layers or 't').strip().lower()
    mapping = {
        't': 't',
        'only_t': 't',
        'tm': 'tm',
        't+m': 'tm',
        'only_tm': 'tm',
        'dmt': 'dmt',
        'd+m+t': 'dmt',
        'all': 'dmt',
    }
    return mapping.get(value, 't')


# ════════════════════════════════════════════════════════════════
# 便捷：直接提取单个 unit 的理解摘要
# ════════════════════════════════════════════════════════════════


def extract_unit_digest(digest: Dict[str, Any], unit_id: str) -> Optional[Dict[str, Any]]:
    """从完整 CIDigest 中提取单个 unit 的信息与对应 T 层上下文。

    适用于多图理解结果中只需对其中一张图进行升维复现的场景。

    Returns:
        单元摘要字典，格式::

            {
                'unit_id': str,
                'source_file': str,
                'page': int,
                'title': str,
                'main_content': str,
                'ocr_text': str,
                'layout_regions': [...],
                'reading_order': str,
                'continuity_with_prev': {...},
                'asset_abs_path': str | None,
                'core_theme': str,
                'overall_summary': str,
                'composite_text': str,  # 仅含该 unit 的合成文本
            }

        未找到 unit_id 时返回 ``None``。
    """
    if not digest or not digest.get('ok'):
        return None
    for u in digest.get('units', []):
        if u.get('unit_id') == unit_id:
            # 为该单元单独合成文本
            t_layer_subset = {
                'core_theme': digest.get('core_theme', ''),
                'overall_summary': digest.get('overall_summary', ''),
                'group_relations': digest.get('group_relations', []),
                'zpd_next_step': digest.get('zpd_next_step', ''),
                'blind_spots': digest.get('blind_spots', []),
            }
            single_composite = _build_composite_text(
                'single',
                [u.get('source_file', '')],
                t_layer_subset,
                [u],
                result_layers=digest.get('result_layers', 't'),
                source=digest.get('source', 'ci'),
            )
            result = dict(u)
            result['core_theme'] = digest.get('core_theme', '')
            result['overall_summary'] = digest.get('overall_summary', '')
            result['result_layers'] = digest.get('result_layers', 't')
            result['composite_text'] = single_composite
            return result
    return None
