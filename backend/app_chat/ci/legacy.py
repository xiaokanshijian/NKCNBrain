"""
ci/legacy.py — 旧架构兼容层。

Phase 7.2a 迁移：
    - build_group_id
    - prepare_group_workspace
    - render_pdf_pages_to_assets
    - build_image_units
    - R 层 manifest 状态助手

注意：
    - Phase 7.2a 仅迁移旧架构基础函数，不替换旧服务文件中的现有导出。
    - 旧服务层仍保留原定义，待 Phase 7.3 薄转发层统一收口。
"""

import hashlib
import os
import shutil
import traceback
from typing import Any, Dict, List, Optional, Tuple

import fitz

from app_chat.ci._utils import _extract_filename, _resolve_user_file_path, _safe_json_dump, _update_task
from app_chat.ci.d_layer import build_d_layer
from app_chat.ci.m_layer import build_m_layer
from app_chat.ci.orchestrator import _build_manifest, _load_existing_layer
from app_chat.ci.t_layer import build_t_layer


IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
PDF_EXTENSIONS = {'.pdf'}

SECTION_PREPARING = '准备中'
SECTION_FINALIZING = '结果整理中'
SECTION_COMPLETED = '完成'
SECTION_FAILED = '失败'


def _set_manifest_reproduction_status(paths: Dict[str, str], manifest: Dict[str, Any], status: str) -> None:
    if not isinstance(manifest, dict):
        manifest = {}
    manifest['reproduction_status'] = status
    _safe_json_dump(paths['manifest'], manifest)


def build_group_id(username: str, mode: str, selected_files: List[Any]) -> str:
    digest_parts: List[str] = [username, mode]
    for item in selected_files:
        file_name = _extract_filename(item)
        if not file_name:
            continue
        path = _resolve_user_file_path(username, file_name)
        if path and os.path.exists(path):
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
            digest_parts.append(f'{file_name}|{mtime}|{size}')
        else:
            digest_parts.append(f'{file_name}|missing')

    digest_raw = '||'.join(digest_parts)
    digest = hashlib.sha1(digest_raw.encode('utf-8')).hexdigest()[:16]
    return f'ci_{digest}'


def prepare_group_workspace(username: str, group_id: str) -> Dict[str, str]:
    root = os.path.join('.', 'received_dir', 'user_raw_file', username, 'continuous_image_dmt', group_id)
    page_assets = os.path.join(root, 'page_assets')
    layout_visual = os.path.join(root, 'layout_visual')
    ocr_cache = os.path.join(root, 'ocr_cache')

    os.makedirs(root, exist_ok=True)
    os.makedirs(page_assets, exist_ok=True)
    os.makedirs(layout_visual, exist_ok=True)
    os.makedirs(ocr_cache, exist_ok=True)

    return {
        'root': root,
        'page_assets': page_assets,
        'layout_visual': layout_visual,
        'ocr_cache': ocr_cache,
        'manifest': os.path.join(root, 'manifest.json'),
        'd_layer': os.path.join(root, 'd_layer.json'),
        'm_layer': os.path.join(root, 'm_layer.json'),
        't_layer': os.path.join(root, 't_layer.json'),
        't_layer_md': os.path.join(root, 't_layer.md'),
    }


def render_pdf_pages_to_assets(pdf_path: str, page_assets_dir: str, source_file: str, seq_start: int) -> Tuple[List[Dict[str, Any]], int]:
    units: List[Dict[str, Any]] = []
    seq = seq_start
    document = fitz.open(pdf_path)
    try:
        for page_index in range(len(document)):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            asset_name = f'{seq:03d}_{os.path.splitext(os.path.basename(source_file))[0]}_p{page_index + 1}.png'
            asset_abs_path = os.path.join(page_assets_dir, asset_name)
            pixmap.save(asset_abs_path)
            unit_id = f'u{seq:03d}'
            units.append({
                'unit_id': unit_id,
                'source_type': 'pdf',
                'source_file': source_file,
                'source_abs_path': pdf_path,
                'page': page_index + 1,
                'seq': seq,
                'asset_path': f'page_assets/{asset_name}',
                'asset_abs_path': asset_abs_path,
            })
            seq += 1
    finally:
        document.close()

    return units, seq


def build_image_units(username: str, selected_files: List[Any], page_assets_dir: str) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    units: List[Dict[str, Any]] = []
    related_docs: List[str] = []
    selected_file_names: List[str] = []
    seq = 1

    for item in selected_files:
        file_name = _extract_filename(item)
        if not file_name:
            continue
        selected_file_names.append(file_name)
        abs_path = _resolve_user_file_path(username, file_name)
        if not abs_path or not os.path.exists(abs_path):
            continue

        ext = os.path.splitext(abs_path)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            src_base = os.path.splitext(os.path.basename(file_name))[0]
            asset_name = f'{seq:03d}_{src_base}{ext}'
            asset_abs_path = os.path.join(page_assets_dir, asset_name)
            shutil.copy2(abs_path, asset_abs_path)
            unit_id = f'u{seq:03d}'
            units.append({
                'unit_id': unit_id,
                'source_type': 'image',
                'source_file': file_name,
                'source_abs_path': abs_path,
                'page': 1,
                'seq': seq,
                'asset_path': f'page_assets/{asset_name}',
                'asset_abs_path': asset_abs_path,
            })
            seq += 1
        elif ext in PDF_EXTENSIONS:
            pdf_units, seq = render_pdf_pages_to_assets(abs_path, page_assets_dir, file_name, seq)
            units.extend(pdf_units)
            related_docs.append(file_name)
        else:
            related_docs.append(file_name)

    units.sort(key=lambda item: item['seq'])
    for index, unit in enumerate(units):
        unit['prev_unit_id'] = units[index - 1]['unit_id'] if index > 0 else ''
        unit['next_unit_id'] = units[index + 1]['unit_id'] if index < len(units) - 1 else ''

    return units, related_docs, selected_file_names


def run_continuous_image_analysis(task_id: str, username: str, mode: str, selected_files: List[Any],
                                  group_id: str, force_rebuild: bool = False,
                                  model_id: Optional[str] = None) -> None:
    try:
        _update_task(
            task_id,
            current_item=0,
            total_items=0,
            current_section=SECTION_PREPARING,
            completed=False,
            error='',
        )

        paths = prepare_group_workspace(username, group_id)
        units, related_docs, selected_file_names = build_image_units(username, selected_files, paths['page_assets'])
        manifest = _build_manifest(username, group_id, mode, selected_file_names, units, related_docs, status='running')
        _safe_json_dump(paths['manifest'], manifest)

        if not units:
            raise ValueError('未找到可分析的图片或PDF页，请检查勾选文件是否存在。')

        d_layer = None if force_rebuild else _load_existing_layer(paths['d_layer'])
        m_layer = None if force_rebuild else _load_existing_layer(paths['m_layer'])
        t_layer = None if force_rebuild else _load_existing_layer(paths['t_layer'])

        if d_layer is None:
            d_layer = build_d_layer(username, units, paths, task_id, model_id=model_id)
        if m_layer is None:
            m_layer = build_m_layer(username, units, d_layer, paths, task_id)
        if t_layer is None:
            t_layer = build_t_layer(username, selected_file_names, related_docs, d_layer, m_layer, paths, task_id)

        _update_task(task_id, current_section=SECTION_FINALIZING, current_item=1, total_items=1)
        manifest['status'] = 'completed'
        _safe_json_dump(paths['manifest'], manifest)
        _update_task(
            task_id,
            current_section=SECTION_COMPLETED,
            current_item=1,
            total_items=1,
            completed=True,
            error='',
        )
    except Exception as exc:
        traceback.print_exc()
        _update_task(task_id, current_section=SECTION_FAILED, completed=True, error=str(exc))


def _find_group_root_by_group_id(group_id: str, username: Optional[str] = None) -> str:
    if username:
        candidate = os.path.join('.', 'received_dir', 'user_raw_file', username, 'continuous_image_dmt', group_id)
        if os.path.exists(candidate):
            return candidate

    root = os.path.join('.', 'received_dir', 'user_raw_file')
    if not os.path.exists(root):
        return ''

    for user in os.listdir(root):
        candidate = os.path.join(root, user, 'continuous_image_dmt', group_id)
        if os.path.exists(candidate):
            return candidate
    return ''


def get_continuous_image_result(group_id: str, username: Optional[str] = None) -> Dict[str, Any]:
    group_root = _find_group_root_by_group_id(group_id, username=username)
    if not group_root:
        return {'error_num': 1, 'msg': '结果不存在'}

    manifest = _load_existing_layer(os.path.join(group_root, 'manifest.json')) or {}
    d_layer = _load_existing_layer(os.path.join(group_root, 'd_layer.json')) or {}
    m_layer = _load_existing_layer(os.path.join(group_root, 'm_layer.json')) or {}
    t_layer = _load_existing_layer(os.path.join(group_root, 't_layer.json')) or {}

    has_layout_visual = False
    layout_visual_type = 'none'
    layout_visual_path = ''
    sections = m_layer.get('sections', []) if isinstance(m_layer, dict) else []
    for section in sections:
        if section.get('layout_visual_status') == 'ready' and section.get('layout_visual_path'):
            has_layout_visual = True
            layout_visual_type = section.get('layout_visual_type', 'none')
            layout_visual_path = section.get('layout_visual_path', '')
            break

    return {
        'error_num': 0,
        'group_id': group_id,
        'manifest': manifest,
        'd_layer': d_layer,
        'm_layer': m_layer,
        't_layer': t_layer,
        'has_layout_visual': has_layout_visual,
        'layout_visual_type': layout_visual_type,
        'layout_visual_path': layout_visual_path,
        'is_layout_view_default': False,
    }