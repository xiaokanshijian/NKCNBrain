"""
ci/orchestrator.py — 新架构主编排层。

Phase 7.1a 迁移：
    - build_analysis_id
    - query_ci_analyses
    - prepare_analysis_workspace
    - _build_manifest
    - _load_existing_layer
    - 主编排共享私有助手

注意：
    - Phase 7.1a 仅迁移主编排公共助手，不替换旧服务文件中的现有调用。
    - 旧服务层仍保留原定义，待 Phase 7.3 薄转发层统一收口。
"""

import datetime as _datetime_ci
import hashlib
import os
import shutil
import traceback
from typing import Any, Dict, List, Optional, Tuple

from app_chat.ci._context import _filter_user_selected_context, _gather_notebook_context
from app_chat.ci._utils import _ci_d_cache_root, _ci_dmt_root, _safe_json_dump, _safe_json_load, _update_task
from app_chat.ci.d_layer import DCacheManager
from app_chat.ci.index_manager import CIIndexManager
from app_chat.ci.m_layer import build_m_layer_v2
from app_chat.ci.r_layer import build_r_layer, _ensure_r_layer_items, _sanitize_reproduction_item_for_response
from app_chat.ci.t_layer import build_t_layer


SECTION_PREPARING = '准备中'
SECTION_OCR = 'OCR处理中'
SECTION_CONFIDENCE = '置信度分析中'
SECTION_GREY_REPAIR = '灰区修复中'
SECTION_FINALIZING = '结果整理中'
SECTION_COMPLETED = '完成'
SECTION_FAILED = '失败'


def _build_failed_r_layer(units: List[Dict[str, Any]], error_text: str) -> Dict[str, Any]:
    return {
        'layer': 'R',
        'total_units': len(units),
        'items': [
            {
                'unit_id': unit['unit_id'],
                'source_file': unit.get('source_file', ''),
                'page': unit.get('page', 1),
                'reproduction_path': '',
                'status': 'failed',
                'error': error_text[:100],
            }
            for unit in units
        ],
    }


def _r_layer_has_ready_item(r_layer: Dict[str, Any]) -> bool:
    if not isinstance(r_layer, dict):
        return False
    return any(item.get('status') == 'ready' for item in (r_layer.get('items') or []))


def _r_layer_has_attempt(r_layer: Dict[str, Any]) -> bool:
    if not isinstance(r_layer, dict):
        return False
    return any(
        (item or {}).get('status') in ('ready', 'failed', 'skipped')
        for item in (r_layer.get('items') or [])
        if isinstance(item, dict)
    )


def build_analysis_id(mode: str, files: List[str]) -> str:
    """按 mode + 文件集合（排序后）生成稳定的 analysis_id（单图/多图各异）。"""
    sorted_files = sorted(file_name.strip() for file_name in files if file_name and file_name.strip())
    raw = mode + '|' + '||'.join(sorted_files)
    digest = hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]
    prefix = 'single' if mode == 'single' else 'multi'
    return f'{prefix}_{digest}'


def query_ci_analyses(username: str, files: List[str]) -> Dict[str, Any]:
    """查询与指定文件集合有关联的所有已有分析记录。"""
    if not files:
        return {'singles': [], 'groups': [], 'superset_match': None}

    file_set = set(files)
    all_analyses = CIIndexManager.load(username)

    singles = []
    groups = []
    for record in all_analyses:
        record_files = set(record.get('files', []))
        if record.get('mode') == 'single':
            if record_files & file_set:
                singles.append(record)
        elif record.get('mode') == 'group':
            if record_files & file_set:
                groups.append(record)

    superset_match = None
    if len(files) > 1:
        candidates = [
            record for record in groups
            if record.get('status') == 'completed' and file_set.issubset(set(record.get('files', [])))
        ]
        if candidates:
            superset_match = min(candidates, key=lambda record: len(record.get('files', [])))

    return {
        'singles': sorted(singles, key=lambda record: record.get('created_at', ''), reverse=True),
        'groups': sorted(groups, key=lambda record: record.get('created_at', ''), reverse=True),
        'superset_match': superset_match,
    }


def prepare_analysis_workspace(username: str, analysis_id: str) -> Dict[str, str]:
    """新架构：分析目录使用 analysis_id 命名，D层从 d_cache 读取。"""
    root = os.path.join(_ci_dmt_root(username), analysis_id)
    page_assets = os.path.join(root, 'page_assets')
    layout_visual = os.path.join(root, 'layout_visual')
    reproduction_dir = os.path.join(root, 'reproduction')

    os.makedirs(root, exist_ok=True)
    os.makedirs(page_assets, exist_ok=True)
    os.makedirs(layout_visual, exist_ok=True)
    os.makedirs(reproduction_dir, exist_ok=True)

    return {
        'root': root,
        'page_assets': page_assets,
        'layout_visual': layout_visual,
        'reproduction_dir': reproduction_dir,
        'ocr_cache': _ci_d_cache_root(username),
        'manifest': os.path.join(root, 'manifest.json'),
        'd_layer': os.path.join(root, 'd_layer.json'),
        'm_layer': os.path.join(root, 'm_layer.json'),
        't_layer': os.path.join(root, 't_layer.json'),
        't_layer_md': os.path.join(root, 't_layer.md'),
        'r_layer': os.path.join(root, 'r_layer.json'),
    }


def _build_manifest(username: str, group_id: str, mode: str, selected_file_names: List[str], units: List[Dict[str, Any]],
                    related_docs: List[str], status: str) -> Dict[str, Any]:
    from app_chat.scene_context_helper import get_scene_info_from_username  # noqa: PLC0415

    scene_name, sub_scene_name, _, _ = get_scene_info_from_username(username)
    manifest_units = []
    for unit in units:
        manifest_units.append({
            'unit_id': unit['unit_id'],
            'source_file': unit['source_file'],
            'page': unit['page'],
            'seq': unit['seq'],
            'asset_path': unit['asset_path'],
            'prev_unit_id': unit.get('prev_unit_id', ''),
            'next_unit_id': unit.get('next_unit_id', ''),
        })

    return {
        'group_id': group_id,
        'username': username,
        'scene_name': scene_name,
        'sub_scene_name': sub_scene_name,
        'mode': mode,
        'selected_files': selected_file_names,
        'input_units': manifest_units,
        'related_docs': related_docs,
        'status': status,
    }


def _load_existing_layer(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        return _safe_json_load(path)
    except Exception:
        return None


def run_ci_analysis(task_id: str, username: str, mode: str, selected_files: List[str],
                    analysis_id: str, force_rebuild_mt: bool = False,
                    model_id: Optional[str] = None,
                    context_docs: Optional[List[str]] = None,
                    context_card_ids: Optional[List[int]] = None) -> None:
    """新架构主流程：使用共享 d_cache + analysis_id 目录。"""
    from app_chat.ci.legacy import build_image_units  # noqa: PLC0415

    try:
        _update_task(task_id, current_item=0, total_items=0,
                     current_section=SECTION_PREPARING, completed=False, error='')

        paths = prepare_analysis_workspace(username, analysis_id)
        notebook_ctx = _gather_notebook_context(username)
        notebook_ctx = _filter_user_selected_context(
            notebook_ctx,
            username=username,
            selected_files=selected_files,
            context_docs=context_docs,
            context_card_ids=context_card_ids,
        )

        units, related_docs, file_names = build_image_units(username, selected_files, paths['page_assets'])
        if not units:
            raise ValueError('未找到可分析的图片或 PDF 页，请检查文件是否存在。')

        manifest = _build_manifest(username, analysis_id, mode, file_names, units, related_docs, status='running')
        manifest['reproduction_status'] = 'waiting_t_layer'
        manifest['context_config'] = {
            'user_selected_docs': context_docs or [],
            'user_selected_card_ids': context_card_ids or [],
            'auto_mode': not context_docs and not context_card_ids,
            'doc_count': len(notebook_ctx.get('doc_summaries', [])),
            'card_count': len(notebook_ctx.get('card_summaries', [])),
        }
        _safe_json_dump(paths['manifest'], manifest)

        d_layer = None if force_rebuild_mt else _load_existing_layer(paths['d_layer'])
        if d_layer is None:
            _update_task(task_id, current_section=SECTION_OCR, total_items=len(units))
            d_items = []
            for index, unit in enumerate(units, start=1):
                _update_task(task_id, current_item=index)
                _update_task(task_id, current_section=SECTION_OCR)
                cache = DCacheManager.get_or_build(
                    username,
                    unit['source_file'],
                    model_id=model_id,
                    page=unit.get('page', 1),
                    asset_abs_path=unit.get('asset_abs_path', ''),
                )
                _update_task(task_id, current_section=SECTION_CONFIDENCE)
                if cache.get('zone_summary', {}).get('grey', 0) > 0:
                    _update_task(task_id, current_section=SECTION_GREY_REPAIR)
                d_items.append({
                    'unit_id': unit['unit_id'],
                    'seq': unit['seq'],
                    'source_file': unit['source_file'],
                    'page': unit['page'],
                    'ocr_text': cache['ocr_text'],
                    'ocr_markdown': cache['ocr_markdown'],
                    'low_confidence_hint': cache['low_confidence_hint'],
                    'regions': cache.get('regions', []),
                    'zone_summary': cache.get('zone_summary', {'white': 0, 'grey': 0, 'black': 0}),
                    'ocr_text_enhanced': cache.get('ocr_text_enhanced', cache['ocr_text']),
                    'source_locator': {
                        'source_file': unit['source_file'],
                        'page': unit['page'],
                        'seq': unit['seq'],
                        'unit_id': unit['unit_id'],
                    },
                    'reused_cached_ocr': True,
                    'ocr_error': '',
                    '_asset_abs_path': cache['asset_abs_path'] or unit.get('asset_abs_path', ''),
                    '_layout_visual_abs': cache['layout_visual_abs_path'],
                    '_unit_dir': cache['unit_dir'],
                })
            d_layer = {'layer': 'D', 'total_units': len(d_items), 'items': d_items}
            clean_items = [{key: value for key, value in item.items() if not key.startswith('_')} for item in d_items]
            _safe_json_dump(paths['d_layer'], {'layer': 'D', 'total_units': len(clean_items), 'items': clean_items})
        else:
            d_items = d_layer.get('items', [])

        m_layer = None if force_rebuild_mt else _load_existing_layer(paths['m_layer'])
        if m_layer is None:
            d_map_ext = {item['unit_id']: item for item in d_items}
            for unit in units:
                ext_info = d_map_ext.get(unit['unit_id'], {})
                if ext_info.get('_asset_abs_path'):
                    unit['asset_abs_path'] = ext_info['_asset_abs_path']
                unit['_layout_visual_abs'] = ext_info.get('_layout_visual_abs', '')
                unit['_unit_dir'] = ext_info.get('_unit_dir', '')
            m_layer = build_m_layer_v2(username, units, d_layer, paths, task_id, m_layer_context=notebook_ctx)

        t_layer = None if force_rebuild_mt else _load_existing_layer(paths['t_layer'])
        if t_layer is None:
            t_layer = build_t_layer(username, file_names, related_docs, d_layer, m_layer, paths, task_id,
                                    notebook_ctx=notebook_ctx)

        _update_task(task_id, current_section=SECTION_FINALIZING, current_item=1, total_items=1)
        manifest['status'] = 'completed'
        manifest['reproduction_status'] = 'pending_confirm'
        _safe_json_dump(paths['manifest'], manifest)
        CIIndexManager.update_status(username, analysis_id, 'completed')
        if mode == 'group':
            CIIndexManager.remove_subset_groups(username, file_names)
        _update_task(task_id, current_section=SECTION_COMPLETED,
                     current_item=1, total_items=1, completed=True, error='')
    except Exception as exc:
        traceback.print_exc()
        _update_task(task_id, current_section=SECTION_FAILED, completed=True, error=str(exc))
        CIIndexManager.update_status(username, analysis_id, 'failed')


def redo_ci_analysis(task_id: str, username: str, analysis_id: str, redo_scope: str = 'mt') -> None:
    """重做分析层。

    redo_scope:
      - 'mt': 重做 M/T 层（复用 D 层缓存）
      - 't': 仅重做 T 层（复用现有 D/M 层）
    """
    from app_chat.ci.legacy import build_image_units  # noqa: PLC0415

    try:
        scope = str(redo_scope or 'mt').strip().lower()
        if scope not in ('mt', 't'):
            scope = 'mt'

        _update_task(task_id, current_item=0, total_items=0,
                     current_section=SECTION_PREPARING, completed=False, error='')

        paths = prepare_analysis_workspace(username, analysis_id)
        manifest = _load_existing_layer(paths['manifest']) or {}
        manifest['reproduction_status'] = 'waiting_t_layer'
        _safe_json_dump(paths['manifest'], manifest)
        file_names = manifest.get('selected_files', [])

        if not file_names:
            raise ValueError(f'找不到分析 {analysis_id} 的原始文件记录')

        units, related_docs, _ = build_image_units(username, file_names, paths['page_assets'])
        if not units:
            raise ValueError('原始文件已不存在，无法迭代')

        ctx_cfg = manifest.get('context_config', {})
        notebook_ctx = _gather_notebook_context(username)
        notebook_ctx = _filter_user_selected_context(
            notebook_ctx,
            username=username,
            selected_files=file_names,
            context_docs=ctx_cfg.get('user_selected_docs'),
            context_card_ids=ctx_cfg.get('user_selected_card_ids'),
        )

        d_items = []
        for unit in units:
            cache = DCacheManager.read_unit(username, unit['source_file'], page=unit.get('page', 1))
            if cache is None:
                old_d = _load_existing_layer(paths['d_layer']) or {}
                cache_hit = next((item for item in old_d.get('items', []) if item['unit_id'] == unit['unit_id']), {})
                cache = {
                    'ocr_text': cache_hit.get('ocr_text', ''),
                    'ocr_markdown': cache_hit.get('ocr_markdown', ''),
                    'asset_abs_path': unit.get('asset_abs_path', ''),
                    'layout_visual_abs_path': '',
                    'low_confidence_hint': cache_hit.get('low_confidence_hint', False),
                    'unit_dir': DCacheManager._unit_dir(username, unit['source_file'], unit.get('page', 1)),
                    'regions': cache_hit.get('regions', []),
                    'zone_summary': cache_hit.get('zone_summary', {'white': 0, 'grey': 0, 'black': 0}),
                    'ocr_text_enhanced': cache_hit.get('ocr_text_enhanced', cache_hit.get('ocr_text', '')),
                }
            d_items.append({
                'unit_id': unit['unit_id'],
                'seq': unit['seq'],
                'source_file': unit['source_file'],
                'page': unit['page'],
                'ocr_text': cache['ocr_text'],
                'ocr_markdown': cache['ocr_markdown'],
                'low_confidence_hint': cache['low_confidence_hint'],
                'regions': cache.get('regions', []),
                'zone_summary': cache.get('zone_summary', {'white': 0, 'grey': 0, 'black': 0}),
                'ocr_text_enhanced': cache.get('ocr_text_enhanced', cache['ocr_text']),
                'source_locator': {'source_file': unit['source_file'], 'page': unit['page'],
                                   'seq': unit['seq'], 'unit_id': unit['unit_id']},
                'reused_cached_ocr': True,
                'ocr_error': '',
                '_asset_abs_path': cache['asset_abs_path'],
                '_layout_visual_abs': cache['layout_visual_abs_path'],
                '_unit_dir': cache['unit_dir'],
            })
        d_layer = {'layer': 'D', 'total_units': len(d_items), 'items': d_items}

        d_map_ext = {item['unit_id']: item for item in d_items}
        for unit in units:
            ext_info = d_map_ext.get(unit['unit_id'], {})
            if ext_info.get('_asset_abs_path'):
                unit['asset_abs_path'] = ext_info['_asset_abs_path']
            unit['_layout_visual_abs'] = ext_info.get('_layout_visual_abs', '')
            unit['_unit_dir'] = ext_info.get('_unit_dir', '')

        if scope == 't':
            m_layer = _load_existing_layer(paths['m_layer']) or {}
            if not m_layer:
                raise ValueError('当前分析缺少M层结果，无法仅迭代T层，请先执行M/T迭代')
            for path in (paths['t_layer'], paths['t_layer_md']):
                if os.path.exists(path):
                    os.remove(path)
            build_t_layer(username, file_names, related_docs, d_layer, m_layer, paths, task_id,
                          notebook_ctx=notebook_ctx)
            _update_task(task_id, current_section=SECTION_FINALIZING, current_item=1, total_items=1)
            manifest['status'] = 'completed'
            manifest['reproduction_status'] = 'waiting_t_layer'
            _safe_json_dump(paths['manifest'], manifest)
            CIIndexManager.update_status(username, analysis_id, 'completed')
            _update_task(task_id, current_section=SECTION_COMPLETED,
                         current_item=1, total_items=1, completed=True, error='')
            return

        for path in (paths['m_layer'], paths['t_layer'], paths['t_layer_md'], paths['r_layer']):
            if os.path.exists(path):
                os.remove(path)
        repro_dir = paths.get('reproduction_dir', '')
        if repro_dir and os.path.isdir(repro_dir):
            shutil.rmtree(repro_dir, ignore_errors=True)
            os.makedirs(repro_dir, exist_ok=True)

        m_layer = build_m_layer_v2(username, units, d_layer, paths, task_id, m_layer_context=notebook_ctx)
        build_t_layer(username, file_names, related_docs, d_layer, m_layer, paths, task_id,
                      notebook_ctx=notebook_ctx)
        _update_task(task_id, current_section=SECTION_FINALIZING, current_item=1, total_items=1)
        manifest['status'] = 'completed'
        manifest['reproduction_status'] = 'pending_confirm'
        _safe_json_dump(paths['manifest'], manifest)
        CIIndexManager.update_status(username, analysis_id, 'completed')
        _update_task(task_id, current_section=SECTION_COMPLETED,
                     current_item=1, total_items=1, completed=True, error='')
    except Exception as exc:
        traceback.print_exc()
        _update_task(task_id, current_section=SECTION_FAILED, completed=True, error=str(exc))
        CIIndexManager.update_status(username, analysis_id, 'failed')


def get_ci_result(username: str, analysis_id: str) -> Dict[str, Any]:
    """按 analysis_id 读取分析结果。"""
    root = os.path.join(_ci_dmt_root(username), analysis_id)
    if not os.path.isdir(root):
        return {'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'}

    manifest = _load_existing_layer(os.path.join(root, 'manifest.json')) or {}
    d_layer = _load_existing_layer(os.path.join(root, 'd_layer.json')) or {}
    m_layer = _load_existing_layer(os.path.join(root, 'm_layer.json')) or {}
    t_layer = _load_existing_layer(os.path.join(root, 't_layer.json')) or {}
    r_layer_path = os.path.join(root, 'r_layer.json')
    paths = prepare_analysis_workspace(username, analysis_id)
    r_layer = _ensure_r_layer_items(
        username,
        analysis_id,
        manifest,
        d_layer,
        m_layer,
        t_layer,
        _load_existing_layer(r_layer_path) or {},
        paths=paths,
    )

    from app_chat.ci.overlay_layer import build_ci_overlay_result  # noqa: PLC0415

    overlay_layer, overlay_layer_version = build_ci_overlay_result(username, analysis_id, manifest, r_layer, paths)

    r_layer_version = ''
    if os.path.exists(r_layer_path):
        try:
            r_layer_version = str(int(os.path.getmtime(r_layer_path) * 1000))
        except Exception:
            r_layer_version = ''

    reproduction_status = (manifest.get('reproduction_status') or '').strip()
    if not reproduction_status:
        if _r_layer_has_ready_item(r_layer):
            reproduction_status = 'completed'
        elif _r_layer_has_attempt(r_layer):
            reproduction_status = 'failed'
        else:
            reproduction_status = 'pending_confirm'

    has_layout_visual = False
    layout_visual_type = 'none'
    layout_visual_path = ''
    for section in (m_layer.get('sections', []) if isinstance(m_layer, dict) else []):
        if section.get('layout_visual_status') == 'ready' and section.get('layout_visual_path'):
            has_layout_visual = True
            layout_visual_type = section.get('layout_visual_type', 'none')
            layout_visual_path = section.get('layout_visual_path', '')
            break

    return {
        'error_num': 0,
        'analysis_id': analysis_id,
        'manifest': manifest,
        'd_layer': d_layer,
        'm_layer': m_layer,
        't_layer': t_layer,
        'r_layer': {
            'layer': r_layer.get('layer', 'R'),
            'total_units': r_layer.get('total_units', 0),
            'items': [_sanitize_reproduction_item_for_response(item) for item in (r_layer.get('items') or [])],
        },
        'r_layer_version': r_layer_version,
        'overlay_layer': overlay_layer,
        'overlay_layer_version': overlay_layer_version,
        'reproduction_status': reproduction_status,
        'reproduction_confirmation_required': reproduction_status == 'pending_confirm',
        'has_layout_visual': has_layout_visual,
        'layout_visual_type': layout_visual_type,
        'layout_visual_path': layout_visual_path,
        'is_layout_view_default': False,
    }


def _build_d_layer_from_cache(username: str, units: List[Dict[str, Any]], paths: Dict[str, str]) -> Dict[str, Any]:
    """仅拉取/构建 D 层 OCR 缓存，不调用 M/T 理解模型（供原草图直出 R 使用）。"""
    d_items: List[Dict[str, Any]] = []
    for unit in units:
        cache = DCacheManager.get_or_build(
            username,
            unit['source_file'],
            page=unit.get('page', 1),
            asset_abs_path=unit.get('asset_abs_path', ''),
        )
        d_items.append({
            'unit_id': unit['unit_id'],
            'seq': unit['seq'],
            'source_file': unit['source_file'],
            'page': unit['page'],
            'ocr_text': cache.get('ocr_text', ''),
            'ocr_markdown': cache.get('ocr_markdown', ''),
            'low_confidence_hint': cache.get('low_confidence_hint', ''),
            'regions': cache.get('regions', []),
            'zone_summary': cache.get('zone_summary', {'white': 0, 'grey': 0, 'black': 0}),
            'ocr_text_enhanced': cache.get('ocr_text_enhanced', cache.get('ocr_text', '')),
            'source_locator': {
                'source_file': unit['source_file'],
                'page': unit['page'],
                'seq': unit['seq'],
                'unit_id': unit['unit_id'],
            },
            'reused_cached_ocr': True,
            'ocr_error': '',
            '_asset_abs_path': cache.get('asset_abs_path') or unit.get('asset_abs_path', ''),
        })
    d_layer = {'layer': 'D', 'total_units': len(d_items), 'items': d_items}
    clean_items = [{key: value for key, value in item.items() if not key.startswith('_')} for item in d_items]
    _safe_json_dump(paths['d_layer'], {'layer': 'D', 'total_units': len(clean_items), 'items': clean_items})
    return d_layer


def _build_stub_m_layer_for_sketch_r(units: List[Dict[str, Any]], paths: Dict[str, str]) -> Dict[str, Any]:
    sections: List[Dict[str, Any]] = []
    for unit in units:
        title = (
            f"{unit['source_file']} - 第{unit['page']}页"
            if unit.get('source_type') == 'pdf'
            else unit.get('source_file', '')
        )
        sections.append({
            'unit_id': unit['unit_id'],
            'seq': unit['seq'],
            'source_file': unit['source_file'],
            'page': unit['page'],
            'title': title,
            'layout_regions': ['（原草图直出 R：未执行 M 层版面理解）'],
            'reading_order': '按原图阅读。',
            'main_content': '本分析跳过 M 层模型理解，仅将原草图复制为 R 层复现图。',
            'handwriting_printing_relation': '未区分',
            'annotation_relation': '未区分',
            'continuity_with_prev': {'type': '首图' if unit.get('seq', 1) == 1 else '承接', 'reason': '原草图直出 R', 'key_bridge': ''},
            'context_used': {'context_mode': 'sketch_r_only', 'context_doc_count': 0, 'context_card_count': 0},
            'ocr_refs': [unit['unit_id']],
            'layout_visual_type': 'none',
            'layout_visual_path': '',
            'layout_visual_status': 'skipped',
        })
    m_layer = {'layer': 'M', 'total_sections': len(sections), 'sections': sections}
    _safe_json_dump(paths['m_layer'], m_layer)
    return m_layer


def _build_stub_t_layer_for_sketch_r(
    units: List[Dict[str, Any]],
    m_layer: Dict[str, Any],
    file_names: List[str],
    paths: Dict[str, str],
    username: str,
) -> Dict[str, Any]:
    from app_chat.scene_context_helper import get_scene_info_from_username  # noqa: PLC0415

    scene_name, sub_scene_name, _, _ = get_scene_info_from_username(username)
    sections = m_layer.get('sections', []) if isinstance(m_layer, dict) else []
    group_relations = [
        {
            'seq': sec.get('seq', 0),
            'unit_id': sec.get('unit_id', ''),
            'relation_type': '原草图直出 R',
            'reason': '跳过 T 层模型理解',
        }
        for sec in sections
    ]
    t_layer = {
        'layer': 'T',
        'overall_summary': '已跳过完整图片理解，直接将原草图作为 R 层复现图，可在单图迭代工作区继续编辑。',
        'core_theme': '原草图直出 R 层复现',
        'group_relations': group_relations,
        'doc_relations': [],
        'scene_meaning': {
            'scene_name': scene_name,
            'sub_scene_name': sub_scene_name,
            'scene_summary_binding': '原草图直出 R（无 T 层模型）',
            'meaning': '用于快速进入 R 层单图迭代，不依赖先完成双击图片理解。',
        },
        'blind_spots': ['未执行 T 层综合理解，语义与盲区分析为占位内容。'],
        'internal_friction': [],
        'zpd_next_step': '在单图迭代工作区检查复现图并继续 DMT/覆盖层编辑。',
        'next_actions': ['打开单图迭代工作区核对原草图复现效果。'],
        'semantic_layer_candidate': '',
        'tribal_candidate': '',
        'related_docs': [],
        'bootstrap_mode': 'sketch_r_only',
        'selected_files': file_names,
    }
    _safe_json_dump(paths['t_layer'], t_layer)
    t_md = (
        '# T 层（原草图直出 R 占位）\n\n'
        '本记录由「右键查看图片 → 原草图作 R 层」生成，未调用 T 层理解模型。\n'
    )
    _safe_json_dump(paths['t_layer_md'], t_md)
    return t_layer


def _bootstrap_dmt_layers_for_sketch_r(
    username: str,
    paths: Dict[str, str],
    units: List[Dict[str, Any]],
    file_names: List[str],
    related_docs: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """补齐最小 D/M/T 层，使原草图直出 R 不必先完成双击图片理解。"""
    d_layer = _build_d_layer_from_cache(username, units, paths)
    m_layer = _build_stub_m_layer_for_sketch_r(units, paths)
    t_layer = _build_stub_t_layer_for_sketch_r(units, m_layer, file_names, paths, username)
    return d_layer, m_layer, t_layer


def run_ci_sketch_r_quickstart(task_id: str, username: str, files: List[str]) -> str:
    """无完整 M/T 理解时：建工作区 → 占位 D/M/T → 原草图直出 R。返回 analysis_id。"""
    from app_chat.ci.legacy import _set_manifest_reproduction_status, build_image_units  # noqa: PLC0415

    selected = [f.strip() for f in (files or []) if f and str(f).strip()]
    if not selected:
        raise ValueError('files 不能为空')
    mode = 'single' if len(selected) == 1 else 'group'
    analysis_id = build_analysis_id(mode, selected)

    try:
        _update_task(task_id, current_item=0, total_items=0,
                     current_section=SECTION_PREPARING, completed=False, error='')

        paths = prepare_analysis_workspace(username, analysis_id)
        units, related_docs, file_names = build_image_units(username, selected, paths['page_assets'])
        if not units:
            raise ValueError('未找到可分析的图片或 PDF 页，请检查文件是否存在。')

        manifest = _load_existing_layer(paths['manifest']) or _build_manifest(
            username, analysis_id, mode, file_names, units, related_docs, status='running',
        )
        manifest['bootstrap_mode'] = 'sketch_r_only'
        manifest['reproduction_status'] = 'running'
        _safe_json_dump(paths['manifest'], manifest)

        now = _datetime_ci.datetime.now().isoformat()
        CIIndexManager.add_or_update(username, {
            'analysis_id': analysis_id,
            'mode': mode,
            'files': file_names,
            'status': 'running',
            'created_at': now,
            'updated_at': now,
        })

        d_layer, m_layer, t_layer = _bootstrap_dmt_layers_for_sketch_r(
            username, paths, units, file_names, related_docs,
        )

        manifest['reproduction_last_use_sketch_input'] = True
        manifest['reproduction_last_use_original_sketch_as_r'] = True
        _safe_json_dump(paths['manifest'], manifest)
        _set_manifest_reproduction_status(paths, manifest, 'running')

        d_items = d_layer.get('items', []) if isinstance(d_layer, dict) else []
        d_map_ext = {item['unit_id']: item for item in d_items}
        for unit in units:
            ext_info = d_map_ext.get(unit['unit_id'], {})
            if ext_info.get('_asset_abs_path'):
                unit['asset_abs_path'] = ext_info['_asset_abs_path']
            elif not unit.get('asset_abs_path'):
                cache = DCacheManager.read_unit(username, unit['source_file'], page=unit.get('page', 1))
                if cache and cache.get('asset_abs_path'):
                    unit['asset_abs_path'] = cache['asset_abs_path']

        build_r_layer(
            username, analysis_id, units, d_layer, m_layer, t_layer, paths, task_id,
            use_sketch_input=True,
            use_original_sketch_as_r=True,
        )
        manifest = _load_existing_layer(paths['manifest']) or manifest
        manifest['status'] = 'completed'
        manifest['bootstrap_mode'] = 'sketch_r_only'
        _safe_json_dump(paths['manifest'], manifest)
        _set_manifest_reproduction_status(paths, manifest, 'completed')
        CIIndexManager.update_status(username, analysis_id, 'completed')

        _update_task(task_id, current_section=SECTION_FINALIZING, current_item=1, total_items=1)
        _update_task(task_id, current_section=SECTION_COMPLETED,
                     current_item=1, total_items=1, completed=True, error='')
        return analysis_id
    except Exception as exc:
        traceback.print_exc()
        try:
            paths = prepare_analysis_workspace(username, analysis_id)
            manifest = _load_existing_layer(paths['manifest']) or {}
            units_fail = list(manifest.get('input_units') or [])
            if units_fail:
                _safe_json_dump(paths['r_layer'], _build_failed_r_layer(units_fail, str(exc)))
            _set_manifest_reproduction_status(paths, manifest, 'failed')
        except Exception:
            pass
        CIIndexManager.update_status(username, analysis_id, 'failed')
        _update_task(task_id, current_section=SECTION_FAILED, completed=True, error=str(exc))
        raise


def start_ci_reproduction(task_id: str, username: str, analysis_id: str, force_rebuild: bool = False,
                          use_sketch_input: bool = True, use_original_sketch_as_r: bool = False) -> None:
    from app_chat.ci.legacy import _set_manifest_reproduction_status, build_image_units  # noqa: PLC0415

    try:
        _update_task(task_id, current_item=0, total_items=0,
                     current_section=SECTION_PREPARING, completed=False, error='')

        paths = prepare_analysis_workspace(username, analysis_id)
        manifest = _load_existing_layer(paths['manifest']) or {}
        file_names = manifest.get('selected_files', [])
        if not file_names:
            raise ValueError(f'找不到分析 {analysis_id} 的原始文件记录')

        units, related_docs, _selected = build_image_units(username, file_names, paths['page_assets'])
        if not units:
            raise ValueError('原始图片或 PDF 页不存在，无法生成复现图')

        d_layer = _load_existing_layer(paths['d_layer']) or {}
        m_layer = _load_existing_layer(paths['m_layer']) or {}
        t_layer = _load_existing_layer(paths['t_layer']) or {}
        if not d_layer or not m_layer or not t_layer:
            if use_original_sketch_as_r and use_sketch_input:
                d_layer, m_layer, t_layer = _bootstrap_dmt_layers_for_sketch_r(
                    username, paths, units, file_names, related_docs,
                )
                manifest['bootstrap_mode'] = 'sketch_r_only'
                manifest['status'] = manifest.get('status') or 'completed'
                _safe_json_dump(paths['manifest'], manifest)
            else:
                raise ValueError('D/M/T 层结果不完整，暂无法生成复现图')

        if force_rebuild:
            repro_dir = paths.get('reproduction_dir', '')
            if repro_dir and os.path.isdir(repro_dir):
                shutil.rmtree(repro_dir, ignore_errors=True)
                os.makedirs(repro_dir, exist_ok=True)

        manifest['reproduction_last_use_sketch_input'] = bool(use_sketch_input)
        manifest['reproduction_last_use_original_sketch_as_r'] = bool(use_original_sketch_as_r and use_sketch_input)
        _safe_json_dump(paths['manifest'], manifest)
        _set_manifest_reproduction_status(paths, manifest, 'running')

        d_items = d_layer.get('items', []) if isinstance(d_layer, dict) else []
        d_map_ext = {item['unit_id']: item for item in d_items}
        for unit in units:
            ext_info = d_map_ext.get(unit['unit_id'], {})
            cache = DCacheManager.read_unit(username, unit['source_file'], page=unit.get('page', 1))
            if cache and cache.get('asset_abs_path'):
                unit['asset_abs_path'] = cache['asset_abs_path']
            elif ext_info.get('_asset_abs_path'):
                unit['asset_abs_path'] = ext_info['_asset_abs_path']

        build_r_layer(username, analysis_id, units, d_layer, m_layer, t_layer, paths, task_id,
                      use_sketch_input=use_sketch_input,
                      use_original_sketch_as_r=use_original_sketch_as_r)
        _set_manifest_reproduction_status(paths, manifest, 'completed')
        _update_task(task_id, current_section=SECTION_FINALIZING, current_item=1, total_items=1)
        _update_task(task_id, current_section=SECTION_COMPLETED,
                     current_item=1, total_items=1, completed=True, error='')
    except Exception as exc:
        traceback.print_exc()
        try:
            paths = prepare_analysis_workspace(username, analysis_id)
            manifest = _load_existing_layer(paths['manifest']) or {}
            units = []
            for unit in manifest.get('input_units') or []:
                if isinstance(unit, dict) and unit.get('unit_id'):
                    units.append(unit)
            if units:
                _safe_json_dump(paths['r_layer'], _build_failed_r_layer(units, str(exc)))
            _set_manifest_reproduction_status(paths, manifest, 'failed')
        except Exception:
            pass
        _update_task(task_id, current_section=SECTION_FAILED, completed=True, error=str(exc))
