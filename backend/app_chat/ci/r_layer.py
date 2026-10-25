"""
ci/r_layer.py — R 层模块：复现图辅助函数与迭代上下文构建。

Phase 6.1 迁移：
    - R 层辅助函数与 Gemini 原生调用
    - 复现图上下文、快照、归一化与单页生成辅助

注意：
    - Phase 6.1 仅迁移辅助函数，不替换 continuous_image_service.py 中现有调用。
    - 后续阶段已将对旧服务文件的惰性依赖逐步切回新模块，避免 Phase 7.3 薄转发层形成循环导入。
"""
import nkcn_public_config as _public_config

import base64
import copy
import datetime
import io
import json
import os
import re
import shutil
import threading as _threading_ci
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from openai import OpenAI
from PIL import Image

from app_chat.ci.d_layer import DCacheManager
from app_chat.ci._utils import (
    _ci_dmt_root,
    _normalize_rel,
    _now_iso,
    _safe_bool,
    _safe_json_dump,
    _update_task,
    _truncate_text,
)
from app_chat.ci_prompts import (
    CI_R_REPRODUCTION_WITH_SKETCH_SYSTEM_PROMPT,
    CI_R_REPRODUCTION_WITH_SKETCH_USER_PROMPT_TEMPLATE,
    CI_R_REPRODUCTION_WITHOUT_SKETCH_SYSTEM_PROMPT,
    CI_R_REPRODUCTION_WITHOUT_SKETCH_USER_PROMPT_TEMPLATE,
    CI_R_SINGLE_STEPWISE_INITIAL_SYSTEM_APPENDIX,   
    CI_R_SINGLE_STEPWISE_INITIAL_USER_APPENDIX,
)
from llm_langchain import global_var


_GEMINI_REPRO_API_KEY = _public_config.secret('NKCN_R_LAYER_GEMINI_REPRO_API_KEY')
_GEMINI_REPRO_BASE_URL = _public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/')
_GEMINI_REPRO_MODEL_DEFAULT = 'gemini-3.1-flash-image-preview-X'


def _r_layer_gemini_model() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('ci_r_layer_gemini', _GEMINI_REPRO_MODEL_DEFAULT)

_GEMINI_REPRO_TIMEOUT = 8 * 60
_GEMINI_REPRO_NATIVE_BASE_URL = _public_config.endpoint('NKCN_MODEL_GATEWAY_URL', 'http://localhost:9999')

_R_LAYER_ITER_CONTEXT_VERSION = 1
_R_LAYER_ROLLBACK_HISTORY_LIMIT = 10
_R_LAYER_ITER_EDITABLE_TEXT_LIMITS = {
    't_focus_text': 3000,
    'main_content': 4000,
    'layout_regions_text': 12000,
    'reading_order': 2000,
    'handwriting_printing_relation': 2000,
    'annotation_section': 2000,
    'continuity_text': 2000,
    'm_verification_text': 3000,
    'color_instruction': 500,
    'ratio_instruction': 500,
}

SECTION_PREPARING = '准备中'
SECTION_REPRODUCTION = '升维复现中'
SECTION_FINALIZING = '结果整理中'
SECTION_COMPLETED = '完成'
SECTION_FAILED = '失败'

_ci_reproduction_iter_lock = _threading_ci.Lock()
_ci_reproduction_iterating: Dict[str, set] = {}

_CROP_CONTEXT_PAD_RATIO = 0.18
_CROP_CONTEXT_MIN_PAD = 0.012
_CROP_CONTEXT_MAX_PAD = 0.06


def _reproduction_iter_key(username: str, analysis_id: str, unit_id: str) -> str:
    return f'{username}::{analysis_id}::{unit_id}'


def _set_reproduction_iterating(username: str, analysis_id: str, unit_id: str, running: bool) -> None:
    key = _reproduction_iter_key(username, analysis_id, unit_id)
    with _ci_reproduction_iter_lock:
        if running:
            bucket = _ci_reproduction_iterating.setdefault(username, set())
            bucket.add(key)
        else:
            bucket = _ci_reproduction_iterating.get(username)
            if bucket is not None:
                bucket.discard(key)
                if not bucket:
                    _ci_reproduction_iterating.pop(username, None)


def _is_reproduction_iterating(username: str, analysis_id: str, unit_id: str) -> bool:
    key = _reproduction_iter_key(username, analysis_id, unit_id)
    with _ci_reproduction_iter_lock:
        return key in _ci_reproduction_iterating.get(username, set())


def _extract_repro_base64(response_text: str) -> Optional[str]:
    """从 Gemini 模型响应中提取 base64 图片数据。"""
    if not response_text:
        return None
    pattern1 = r'data:image/[^;]+;base64,([A-Za-z0-9+/=\n]+)'
    match = re.search(pattern1, response_text, re.DOTALL)
    if match:
        return match.group(0).replace('\n', '').strip()
    cleaned = response_text.strip().replace('\n', '').replace(' ', '')
    if len(cleaned) > 1000 and re.match(r'^[A-Za-z0-9+/=]+$', cleaned):
        return cleaned
    # 兼容 markdown 链接返回：![...](https://xxx.png) / [下载](https://xxx)
    md_urls = re.findall(r'\((https?://[^)\s]+)\)', str(response_text), flags=re.IGNORECASE)
    for url in md_urls:
        fetched = _fetch_image_as_data_url(url)
        if fetched:
            return fetched
    # 兼容裸 URL 返回
    raw_urls = re.findall(r'https?://[^\s<>"\')]+', str(response_text), flags=re.IGNORECASE)
    for url in raw_urls:
        fetched = _fetch_image_as_data_url(url)
        if fetched:
            return fetched
    return None


def _fetch_image_as_data_url(url: str) -> Optional[str]:
    try:
        resp = requests.get(str(url or '').strip(), timeout=min(_GEMINI_REPRO_TIMEOUT, 60))
        if resp.status_code != 200:
            return None
        content_type = str(resp.headers.get('Content-Type') or 'image/png').strip() or 'image/png'
        b64 = base64.b64encode(resp.content).decode('utf-8')
        return f'data:{content_type};base64,{b64}'
    except Exception:
        return None


def _extract_repro_base64_from_completion(response: Any) -> Optional[str]:
    """兼容 chat.completions / images 风格返回：content 文本、结构化 content、data[0].b64_json/url。"""
    if response is None:
        return None

    # 1) 常规 chat.completions -> choices[0].message.content
    try:
        choices = getattr(response, 'choices', None) or []
        if choices:
            msg = getattr(choices[0], 'message', None)
            content = getattr(msg, 'content', None)
            if isinstance(content, str):
                parsed = _extract_repro_base64(content)
                if parsed:
                    return parsed
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, str):
                        parsed = _extract_repro_base64(part)
                        if parsed:
                            return parsed
                        continue
                    if not isinstance(part, dict):
                        continue
                    # 常见结构化字段
                    txt = str(part.get('text') or '')
                    if txt:
                        parsed = _extract_repro_base64(txt)
                        if parsed:
                            return parsed
                    b64 = str(part.get('b64_json') or part.get('image_base64') or part.get('data') or '').strip()
                    if b64 and re.match(r'^[A-Za-z0-9+/=\n]+$', b64):
                        return b64.replace('\n', '').strip()
                    image_url = part.get('image_url')
                    if isinstance(image_url, dict):
                        url = str(image_url.get('url') or '').strip()
                        if url.startswith('data:image/'):
                            return url
                        if url.startswith('http://') or url.startswith('https://'):
                            fetched = _fetch_image_as_data_url(url)
                            if fetched:
                                return fetched
                    url = str(part.get('url') or '').strip()
                    if url.startswith('data:image/'):
                        return url
                    if url.startswith('http://') or url.startswith('https://'):
                        fetched = _fetch_image_as_data_url(url)
                        if fetched:
                            return fetched
    except Exception:
        pass

    # 2) images 风格 -> data[0].b64_json / data[0].url
    try:
        data = getattr(response, 'data', None) or []
        if data:
            item = data[0]
            b64 = str(getattr(item, 'b64_json', None) or '').strip()
            if b64 and re.match(r'^[A-Za-z0-9+/=\n]+$', b64):
                return b64.replace('\n', '').strip()
            url = str(getattr(item, 'url', None) or '').strip()
            if url.startswith('data:image/'):
                return url
            if url.startswith('http://') or url.startswith('https://'):
                fetched = _fetch_image_as_data_url(url)
                if fetched:
                    return fetched
    except Exception:
        pass

    return None


def _brief_completion_debug(response: Any) -> str:
    """提炼响应摘要，便于排查“模型已成功但未提取到图片”场景。"""
    try:
        model = str(getattr(response, 'model', '') or '')
        choices = getattr(response, 'choices', None) or []
        if choices:
            msg = getattr(choices[0], 'message', None)
            content = getattr(msg, 'content', None)
            if isinstance(content, str):
                snippet = _truncate_text(content.replace('\n', ' '), 220)
                return f'model={model}; content_type=str; content={snippet}'
            if isinstance(content, list):
                types = []
                for part in content[:8]:
                    if isinstance(part, dict):
                        types.append(str(part.get('type') or 'dict'))
                    else:
                        types.append(type(part).__name__)
                return f'model={model}; content_type=list; part_types={types}'
            return f'model={model}; content_type={type(content).__name__}'
        data = getattr(response, 'data', None) or []
        if data:
            item = data[0]
            has_b64 = bool(getattr(item, 'b64_json', None))
            has_url = bool(getattr(item, 'url', None))
            return f'model={model}; data_len={len(data)}; has_b64={has_b64}; has_url={has_url}'
        return f'model={model}; empty_choices_and_data'
    except Exception as e:
        return f'debug_summary_error={type(e).__name__}:{e}'


def _extract_image_data_url_from_images_response(resp: Any) -> Optional[str]:
    """兼容 images.edit 返回：data[0].b64_json / data[0].url。"""
    try:
        data = getattr(resp, 'data', None) or []
        if not data:
            return None
        item = data[0]
        b64 = str(getattr(item, 'b64_json', None) or '').strip()
        if b64 and re.match(r'^[A-Za-z0-9+/=\n]+$', b64):
            return f'data:image/png;base64,{b64.replace(chr(10), "").strip()}'
        url = str(getattr(item, 'url', None) or '').strip()
        if url.startswith('data:image/'):
            return url
        if url.startswith('http://') or url.startswith('https://'):
            return _fetch_image_as_data_url(url)
    except Exception:
        return None
    return None


def _generate_image_via_images_edit(
    model_name: str,
    prompt_text: str,
    input_image_b64: str,
    input_mime: str = 'image/png',
) -> Optional[str]:
    """使用 images.edit 直连生图（对 gpt-image 系列更稳）。"""
    img_bytes = _decode_inline_image_bytes(input_image_b64)
    ext = 'jpg' if 'jpeg' in str(input_mime or '').lower() else 'png'
    file_obj = io.BytesIO(img_bytes)
    file_obj.name = f'input.{ext}'
    client = OpenAI(
        api_key=_GEMINI_REPRO_API_KEY,
        base_url=_GEMINI_REPRO_BASE_URL,
        timeout=_GEMINI_REPRO_TIMEOUT,
    )
    resp = client.images.edit(
        model=str(model_name or '').strip(),
        image=file_obj,
        prompt=str(prompt_text or '').strip(),
        size='auto',
    )
    return _extract_image_data_url_from_images_response(resp)


def _save_repro_image(base64_string: str, output_path: str) -> bool:
    """将 base64 图片数据解码并保存为文件，返回是否成功。"""
    try:
        img_bytes = _decode_inline_image_bytes(base64_string)
        with open(output_path, 'wb') as f:
            f.write(img_bytes)
        return True
    except Exception as e:
        print(f'[ci_repro] 保存图片失败: {e}')
        return False


def _decode_inline_image_bytes(image_payload: Any) -> bytes:
    if not isinstance(image_payload, str) or not image_payload.strip():
        raise ValueError('缺少底图数据')
    payload = image_payload.strip()
    if payload.startswith('data:'):
        parts = payload.split(',', 1)
        payload = parts[1] if len(parts) > 1 else ''
    payload = re.sub(r'[^A-Za-z0-9+/=]', '', payload)
    if not payload:
        raise ValueError('底图数据为空')
    pad = len(payload) % 4
    if pad:
        payload += '=' * (4 - pad)
    try:
        return base64.b64decode(payload)
    except Exception as exc:
        raise ValueError('底图数据解码失败') from exc


def _pil_from_response_base64(base64_string: str) -> Optional[Image.Image]:
    try:
        raw = _decode_inline_image_bytes(base64_string)
        return Image.open(io.BytesIO(raw))
    except Exception:
        return None


def _resample_lanczos():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def _normalize_edit_region(edit_region: Any) -> Optional[Dict[str, float]]:
    if not edit_region or not isinstance(edit_region, dict):
        return None
    try:
        x = float(edit_region.get('x', 0.0))
        y = float(edit_region.get('y', 0.0))
        w = float(edit_region.get('w', 0.0))
        h = float(edit_region.get('h', 0.0))
    except (TypeError, ValueError):
        return None

    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    w = max(0.0, min(1.0, w))
    h = max(0.0, min(1.0, h))
    if x + w > 1.0:
        w = max(0.0, 1.0 - x)
    if y + h > 1.0:
        h = max(0.0, 1.0 - y)
    if w < 0.01 or h < 0.01:
        return None
    return {'x': x, 'y': y, 'w': w, 'h': h}


def _region_to_pixel_box(img_w: int, img_h: int, region: Dict[str, float]) -> Tuple[int, int, int, int, int, int]:
    x, y, w, h = region['x'], region['y'], region['w'], region['h']
    left = int(round(x * img_w))
    top = int(round(y * img_h))
    crop_w = int(round(w * img_w))
    crop_h = int(round(h * img_h))
    left = max(0, min(left, max(0, img_w - 1)))
    top = max(0, min(top, max(0, img_h - 1)))
    crop_w = max(1, min(crop_w, img_w - left))
    crop_h = max(1, min(crop_h, img_h - top))
    right = left + crop_w
    bottom = top + crop_h
    return left, top, right, bottom, crop_w, crop_h


def _expand_edit_region_for_context(region: Dict[str, float]) -> Dict[str, float]:
    pad_x = min(_CROP_CONTEXT_MAX_PAD, max(_CROP_CONTEXT_MIN_PAD, region['w'] * _CROP_CONTEXT_PAD_RATIO))
    pad_y = min(_CROP_CONTEXT_MAX_PAD, max(_CROP_CONTEXT_MIN_PAD, region['h'] * _CROP_CONTEXT_PAD_RATIO))
    crop_x = max(0.0, region['x'] - pad_x)
    crop_y = max(0.0, region['y'] - pad_y)
    crop_right = min(1.0, region['x'] + region['w'] + pad_x)
    crop_bottom = min(1.0, region['y'] + region['h'] + pad_y)
    crop_w = max(region['w'], crop_right - crop_x)
    crop_h = max(region['h'], crop_bottom - crop_y)
    return {
        'x': crop_x,
        'y': crop_y,
        'w': crop_w,
        'h': crop_h,
    }


def _format_crop_iterate_region_block(
    region: Dict[str, float],
    crop_region: Dict[str, float],
    img_w: int,
    img_h: int,
    crop_left: int,
    crop_top: int,
    crop_w: int,
    crop_h: int,
    target_left_in_crop: int,
    target_top_in_crop: int,
    target_w_in_crop: int,
    target_h_in_crop: int,
) -> str:
    return (
        '\n\n【本次输入的局部上下文裁切图在当前复现图中的位置】\n'
        f'- 局部上下文图归一化矩形：左上 ({crop_region["x"]:.4f}, {crop_region["y"]:.4f})，宽 × 高 = {crop_region["w"]:.4f} × {crop_region["h"]:.4f}。\n'
        f'- 对应像素（整图尺寸 {img_w}×{img_h}）：left={crop_left}, top={crop_top}，裁切宽={crop_w}、高={crop_h}。\n\n'
        '【其中真正允许修改的目标框】\n'
        f'- 归一化矩形：左上 ({region["x"]:.4f}, {region["y"]:.4f})，宽 × 高 = {region["w"]:.4f} × {region["h"]:.4f}。\n'
        f'- 在第一张局部上下文图内，对应像素：left={target_left_in_crop}, top={target_top_in_crop}，宽={target_w_in_crop}、高={target_h_in_crop}。\n\n'
        '【输出硬约束】\n'
        f'- 你必须输出与第一张「局部上下文裁切图」完全相同像素尺寸的单张图片，即 {crop_w}×{crop_h} 像素。\n'
        '- 禁止输出完整整图；禁止改变画布宽高或宽高比。\n'
        '- 只有上面标出的「目标框」允许重绘；目标框外的上下文带必须与第一张局部上下文图保持一致，不要挪动、缩放、删改或重排。\n'
        '- 若目标框内原本已有文字、符号、线条、表格或公式，默认保持与输入局部图相同的字高、字号感受、行距、粗细、列宽、块宽占比、距边留白和锚点位置。除非用户明确要求缩放，否则禁止把文字整体做得比原来更小。\n'
        '- 修改后的文字或图形应尽量占据与原目标框内旧内容相近的视觉面积；若内容需要换行，优先通过重排、局部压缩空白或微调间距解决，不要把整块内容缩成更小一团。\n'
        '- 修改时必须参考第二张完整复现图中该区域周边的线条、颜色、字体与布局，使拼回后边界自然衔接。'
    )


def _composite_edited_crop_onto_original(original_path: str, left: int, top: int, crop_w: int, crop_h: int, edited_pil: Image.Image) -> Image.Image:
    base = Image.open(original_path).convert('RGBA')
    edited = edited_pil.convert('RGBA')
    if edited.size != (crop_w, crop_h):
        edited = edited.resize((crop_w, crop_h), _resample_lanczos())
    out = base.copy()
    out.paste(edited, (left, top))
    return out.convert('RGB')


def _extract_inline_b64_from_gemini_native_json(resp_json: Dict[str, Any]) -> str:
    candidates = (resp_json or {}).get('candidates') or []
    if not candidates:
        return ''
    parts = ((candidates[0] or {}).get('content') or {}).get('parts') or []
    for part in parts:
        if isinstance(part, dict) and 'inlineData' in part:
            inline = part.get('inlineData') or {}
            data_b64 = inline.get('data') or ''
            if data_b64:
                return data_b64
    return ''


def _gemini_repro_native_generate_image_from_parts(parts: List[Dict[str, Any]], image_size: str = '4K', model_name: str = '') -> str:
    active_model = str(model_name or _r_layer_gemini_model()).strip() or _r_layer_gemini_model()
    endpoint = f'/v1beta/models/{active_model}:generateContent/'
    url = _GEMINI_REPRO_NATIVE_BASE_URL.rstrip('/') + endpoint
    payload = {
        'contents': [
            {'role': 'user', 'parts': parts},
        ],
        'generationConfig': {
            'responseModalities': ['IMAGE'],
            'imageConfig': {'imageSize': image_size},
        },
    }
    headers = {
        'Authorization': f'Bearer {_GEMINI_REPRO_API_KEY}',
        'Content-Type': 'application/json',
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=_GEMINI_REPRO_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f'Gemini native HTTP {resp.status_code}: {resp.text[:500]}')
    data = resp.json()
    return _extract_inline_b64_from_gemini_native_json(data)


def _format_reproduction_layout_regions_text(regions: Any) -> str:
    if not isinstance(regions, list) or not regions:
        return '  （未识别版面区域）'
    region_lines: List[str] = []
    for r in regions:
        if not isinstance(r, dict):
            region_lines.append(f'  - {str(r)}')
            continue
        detail_parts: List[str] = []
        key_elements = r.get('key_elements', []) if isinstance(r.get('key_elements', []), list) else []
        visual_relations = r.get('visual_relations', []) if isinstance(r.get('visual_relations', []), list) else []
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
        line = f"  - [{r.get('type', '区域')}] {r.get('position', '')}/{r.get('spatial_anchor', '')}：{r.get('content', '')} [evidence={r.get('evidence_level', '')}]"
        if detail_parts:
            line += ' | ' + ' | '.join(detail_parts)
        region_lines.append(line)
    return '\n'.join(region_lines)


def _format_reproduction_verification_text(m_verification: Any) -> str:
    if not isinstance(m_verification, dict):
        return 'verified=无 | uncertain=无 | missing=无'
    verified_regions = m_verification.get('verified_regions', []) if isinstance(m_verification.get('verified_regions', []), list) else []
    uncertain_regions = m_verification.get('uncertain_regions', []) if isinstance(m_verification.get('uncertain_regions', []), list) else []
    missing_regions = m_verification.get('missing_regions', []) if isinstance(m_verification.get('missing_regions', []), list) else []
    uncertain_text = '；'.join([
        f"{str(item.get('region_id', '') or '未标注')}:{str(item.get('issue', '') or '待确认')}"
        for item in uncertain_regions[:3] if isinstance(item, dict)
    ]) or '无'
    missing_text = '；'.join([
        f"{str(item.get('type', '') or '区域')}@{str(item.get('position', '') or '未知位置')}"
        for item in missing_regions[:3] if isinstance(item, dict)
    ]) or '无'
    verified_text = ', '.join([str(item) for item in verified_regions[:4]]) or '无'
    return f'verified={verified_text} | uncertain={uncertain_text} | missing={missing_text}'


def _resolve_asset_path(username: str, analysis_id: str, section: Dict[str, Any], manifest: Dict[str, Any]) -> str:
    unit_id = str((section or {}).get('unit_id', '') or '').strip()
    source_file = str((section or {}).get('source_file', '') or '').strip()
    page = (section or {}).get('page', 1)
    root = os.path.join(_ci_dmt_root(username), analysis_id)

    for unit in (manifest.get('input_units') or []):
        if not isinstance(unit, dict):
            continue
        if unit_id and unit.get('unit_id') != unit_id:
            continue
        asset_rel = str(unit.get('asset_path', '') or '').strip()
        if asset_rel:
            asset_abs = os.path.normpath(os.path.join(root, asset_rel))
            if os.path.isfile(asset_abs):
                return asset_abs
        break

    try:
        cache = DCacheManager.read_unit(username, source_file, page)
        if cache and cache.get('asset_abs_path') and os.path.isfile(cache['asset_abs_path']):
            return cache['asset_abs_path']
    except Exception:
        pass

    page_assets_dir = os.path.join(root, 'page_assets')
    if os.path.isdir(page_assets_dir):
        for name in os.listdir(page_assets_dir):
            candidate = os.path.join(page_assets_dir, name)
            if not os.path.isfile(candidate):
                continue
            if source_file and source_file in name:
                return candidate

    return ''


def _build_digest_unit_from_layers(
    username: str,
    analysis_id: str,
    unit_id: str,
    manifest: Dict[str, Any],
    d_layer: Dict[str, Any],
    m_layer: Dict[str, Any],
    t_layer: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    d_map = {it.get('unit_id', ''): it for it in (d_layer.get('items', []) or []) if isinstance(it, dict)}
    sections = [sec for sec in (m_layer.get('sections', []) or []) if isinstance(sec, dict)]
    section = next((sec for sec in sections if sec.get('unit_id') == unit_id), None)
    if not section:
        return None
    d_item = d_map.get(unit_id, {})
    return {
        'unit_id': unit_id,
        'seq': section.get('seq', 0),
        'source_file': section.get('source_file', ''),
        'page': section.get('page', 1),
        'title': section.get('title', ''),
        'main_content': section.get('main_content', ''),
        'ocr_text': d_item.get('ocr_text_enhanced', '') or d_item.get('ocr_text', ''),
        'ocr_text_raw': d_item.get('ocr_text', ''),
        'layout_regions': section.get('layout_regions', []),
        'reading_order': section.get('reading_order', ''),
        'continuity_with_prev': section.get('continuity_with_prev', {}),
        'handwriting_printing_relation': section.get('handwriting_printing_relation', ''),
        'annotation_relation': section.get('annotation_relation', ''),
        'm_verification': section.get('m_verification', {}),
        'core_theme': t_layer.get('core_theme', ''),
        'overall_summary': t_layer.get('overall_summary', ''),
        'asset_abs_path': _resolve_asset_path(username, analysis_id, section, manifest),
    }


def _build_reproduction_iter_context(
    username: str,
    unit: Dict[str, Any],
    digest_unit: Optional[Dict[str, Any]],
    total_units: int,
    use_sketch_input: bool = True,
) -> Dict[str, Any]:
    source_file = unit.get('source_file', '')
    page = unit.get('page', 1)
    seq = unit.get('seq', 1)

    t_focus_text = '（暂无可用的高层理解补充）'
    main_content = ''
    layout_regions_text = '  （未识别版面区域）'
    reading_order = ''
    handwriting_printing_relation = ''
    annotation_section = ''
    continuity_text = '首图或无明显连续关系'
    m_verification_text = 'verified=无 | uncertain=无 | missing=无'

    if digest_unit:
        main_content = _truncate_text(digest_unit.get('main_content', ''), _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['main_content'])
        t_focus_parts: List[str] = []
        core_theme = _truncate_text(digest_unit.get('core_theme', ''), 120)
        overall_summary = _truncate_text(digest_unit.get('overall_summary', ''), 260)
        if core_theme:
            t_focus_parts.append(f'核心主题：{core_theme}')
        if overall_summary:
            t_focus_parts.append(f'整体理解：{overall_summary}')
        if t_focus_parts:
            t_focus_text = '\n'.join([f'- {item}' for item in t_focus_parts])
        layout_regions_text = _format_reproduction_layout_regions_text(digest_unit.get('layout_regions', []))
        reading_order = _truncate_text(digest_unit.get('reading_order', ''), _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['reading_order'])
        handwriting_printing_relation = _truncate_text(
            digest_unit.get('handwriting_printing_relation', '') or '以草图中的手写层、印刷层和标注层相互关系为准',
            _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['handwriting_printing_relation'],
        )
        annotation_rel = _truncate_text(digest_unit.get('annotation_relation', ''), 1000)
        if annotation_rel and annotation_rel != '无批注':
            annotation_section = f'\n- 批注关系：{annotation_rel}'
        cont = digest_unit.get('continuity_with_prev') or {}
        if isinstance(cont, dict) and (cont.get('type') or cont.get('reason')):
            continuity_text = _truncate_text(cont.get('type', ''), 120) or continuity_text
            if cont.get('reason'):
                continuity_text = _truncate_text(f"{continuity_text}：{cont.get('reason', '')}", _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['continuity_text'])
        m_verification_text = _format_reproduction_verification_text(digest_unit.get('m_verification', {}))

    color_info = _get_document_four_color_info(username, source_file)
    color_instruction = _truncate_text(_build_repro_color_instruction(color_info), _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['color_instruction'])
    ratio_instruction = _truncate_text(
        '原草图显性内容与布局 : T+M 层结构理解强化 : 纯视觉装饰 = 7 : 2 : 1。即以草图保真为主，理解强化为辅，装饰只作轻量点缀',
        _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['ratio_instruction'],
    )

    return {
        'context_version': _R_LAYER_ITER_CONTEXT_VERSION,
        'context_source': 'auto',
        'updated_at': _now_iso(),
        'unit_id': unit.get('unit_id', ''),
        'source_file': source_file,
        'page': page,
        'seq': seq,
        'total': total_units,
        'use_sketch_input': bool(use_sketch_input),
        'use_original_sketch_as_r': False,
        't_focus_text': _truncate_text(t_focus_text, _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['t_focus_text']),
        'main_content': main_content,
        'layout_regions_text': _truncate_text(layout_regions_text, _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['layout_regions_text']),
        'reading_order': reading_order,
        'handwriting_printing_relation': handwriting_printing_relation,
        'annotation_section': _truncate_text(annotation_section, _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['annotation_section']),
        'continuity_text': _truncate_text(continuity_text, _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['continuity_text']),
        'm_verification_text': _truncate_text(m_verification_text, _R_LAYER_ITER_EDITABLE_TEXT_LIMITS['m_verification_text']),
        'color_instruction': color_instruction,
        'ratio_instruction': ratio_instruction,
    }


def _normalize_reproduction_iter_context(base_context: Optional[Dict[str, Any]], updates: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = copy.deepcopy(base_context) if isinstance(base_context, dict) else {}
    ctx.setdefault('context_version', _R_LAYER_ITER_CONTEXT_VERSION)
    ctx.setdefault('context_source', 'auto')
    for key, max_len in _R_LAYER_ITER_EDITABLE_TEXT_LIMITS.items():
        ctx[key] = _truncate_text(ctx.get(key, ''), max_len)
    ctx['use_sketch_input'] = _safe_bool(ctx.get('use_sketch_input', True), True)
    ctx['use_original_sketch_as_r'] = _safe_bool(ctx.get('use_original_sketch_as_r', False), False)
    if ctx.get('use_sketch_input') is False:
        ctx['use_original_sketch_as_r'] = False

    if isinstance(updates, dict):
        for key, max_len in _R_LAYER_ITER_EDITABLE_TEXT_LIMITS.items():
            if key in updates:
                ctx[key] = _truncate_text(updates.get(key, ''), max_len)
        if 'use_sketch_input' in updates:
            ctx['use_sketch_input'] = _safe_bool(updates.get('use_sketch_input'), ctx.get('use_sketch_input', True))
        if 'use_original_sketch_as_r' in updates:
            ctx['use_original_sketch_as_r'] = _safe_bool(updates.get('use_original_sketch_as_r'), False)
        if ctx.get('use_sketch_input') is False:
            ctx['use_original_sketch_as_r'] = False
        ctx['context_source'] = 'user'

    ctx['updated_at'] = _now_iso()
    return ctx


def _normalize_reproduction_rollback_stack(stack: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(stack, list):
        return normalized
    for raw in stack:
        if not isinstance(raw, dict):
            continue
        snapshot_path = _normalize_rel(str(raw.get('snapshot_path') or '').strip())
        reproduction_path = _normalize_rel(str(raw.get('reproduction_path') or '').strip())
        if not snapshot_path or not reproduction_path:
            continue
        normalized.append({
            'snapshot_path': snapshot_path,
            'reproduction_path': reproduction_path,
            'created_at': str(raw.get('created_at') or ''),
            'reason': str(raw.get('reason') or ''),
            'iter_context': _normalize_reproduction_iter_context(raw.get('iter_context')),
            'last_generated_context': _normalize_reproduction_iter_context(raw.get('last_generated_context') or raw.get('iter_context')),
        })
    return normalized[-_R_LAYER_ROLLBACK_HISTORY_LIMIT:]


def _cleanup_reproduction_snapshot_file(paths: Dict[str, str], snapshot_rel: str) -> None:
    rel = _normalize_rel(snapshot_rel)
    if not rel:
        return
    abs_path = os.path.normpath(os.path.join(paths['root'], rel))
    if os.path.isfile(abs_path):
        try:
            os.remove(abs_path)
        except Exception:
            pass


def _append_reproduction_rollback_snapshot(
    paths: Dict[str, str],
    item: Dict[str, Any],
    *,
    reason: str,
) -> List[Dict[str, Any]]:
    if not isinstance(item, dict):
        return _normalize_reproduction_rollback_stack([])
    reproduction_rel = _normalize_rel(str(item.get('reproduction_path') or '').strip())
    if not reproduction_rel:
        return _normalize_reproduction_rollback_stack(item.get('rollback_stack'))

    reproduction_abs = os.path.normpath(os.path.join(paths['root'], reproduction_rel))
    if not os.path.isfile(reproduction_abs):
        return _normalize_reproduction_rollback_stack(item.get('rollback_stack'))

    unit_id = str(item.get('unit_id') or 'unit').strip() or 'unit'
    history_dir = os.path.join(paths['reproduction_dir'], 'history')
    os.makedirs(history_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    safe_unit_id = re.sub(r'[^\w\-]', '_', unit_id)
    snapshot_name = f'{safe_unit_id}_{timestamp}.png'
    snapshot_abs = os.path.join(history_dir, snapshot_name)
    shutil.copy2(reproduction_abs, snapshot_abs)

    stack = _normalize_reproduction_rollback_stack(item.get('rollback_stack'))
    stack.append({
        'snapshot_path': f'reproduction/history/{snapshot_name}',
        'reproduction_path': reproduction_rel,
        'created_at': _now_iso(),
        'reason': reason,
        'iter_context': _normalize_reproduction_iter_context(item.get('iter_context')),
        'last_generated_context': _normalize_reproduction_iter_context(item.get('last_generated_context') or item.get('iter_context')),
    })

    while len(stack) > _R_LAYER_ROLLBACK_HISTORY_LIMIT:
        removed = stack.pop(0)
        _cleanup_reproduction_snapshot_file(paths, removed.get('snapshot_path', ''))
    return stack


def _copy_asset_to_reproduction_png(asset_path: str, out_abs: str) -> bool:
    """将原草图（任意常见位图格式）转为 PNG 写入复现图路径。"""
    try:
        if not asset_path or not os.path.isfile(asset_path):
            return False
        out_dir = os.path.dirname(out_abs)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with Image.open(asset_path) as im:
            if im.mode in ('RGBA', 'LA', 'P'):
                im = im.convert('RGBA')
            else:
                im = im.convert('RGB')
            im.save(out_abs, format='PNG')
        return os.path.isfile(out_abs)
    except Exception:
        traceback.print_exc()
        return False


def _sanitize_reproduction_item_for_response(item: Dict[str, Any]) -> Dict[str, Any]:
    safe_item = copy.deepcopy(item) if isinstance(item, dict) else {}
    for key in ('_asset_abs_path', '_reproduction_abs_path'):
        safe_item.pop(key, None)
    rollback_stack = _normalize_reproduction_rollback_stack(safe_item.pop('rollback_stack', []))
    safe_item['rollback_count'] = len(rollback_stack)
    safe_item['rollback_available'] = len(rollback_stack) > 0
    safe_item['latest_rollback_at'] = rollback_stack[-1].get('created_at', '') if rollback_stack else ''
    return safe_item


def _analysis_units_from_manifest(username: str, analysis_id: str, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    raw_units = manifest.get('input_units') or []
    root = _ci_dmt_root(username)
    for idx, raw in enumerate(raw_units):
        if not isinstance(raw, dict) or not raw.get('unit_id'):
            continue
        unit = copy.deepcopy(raw)
        asset_rel = unit.get('asset_path', '') or ''
        asset_abs = ''
        if asset_rel:
            candidate = os.path.normpath(os.path.join(root, analysis_id, asset_rel))
            if os.path.isfile(candidate):
                asset_abs = candidate
        unit['asset_abs_path'] = asset_abs or unit.get('asset_abs_path', '')
        unit.setdefault('seq', idx + 1)
        unit.setdefault('page', 1)
        units.append(unit)
    return units


def _ensure_r_layer_items(
    username: str,
    analysis_id: str,
    manifest: Dict[str, Any],
    d_layer: Dict[str, Any],
    m_layer: Dict[str, Any],
    t_layer: Dict[str, Any],
    r_layer: Optional[Dict[str, Any]],
    paths: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    units = _analysis_units_from_manifest(username, analysis_id, manifest)
    if not units and manifest.get('selected_files'):
        from app_chat.ci.legacy import build_image_units

        page_assets_dir = os.path.join(_ci_dmt_root(username), analysis_id, 'page_assets')
        units, _related_docs, _selected = build_image_units(username, manifest.get('selected_files', []), page_assets_dir)

    existing_items = (r_layer or {}).get('items', []) if isinstance(r_layer, dict) else []
    existing_map = {
        item.get('unit_id', ''): copy.deepcopy(item)
        for item in existing_items
        if isinstance(item, dict) and item.get('unit_id')
    }
    changed = False
    default_use_sketch_input = _safe_bool(manifest.get('reproduction_last_use_sketch_input', True), True)

    merged_items: List[Dict[str, Any]] = []
    total_units = len(units)
    for unit in units:
        unit_id = unit.get('unit_id', '')
        item = existing_map.get(unit_id, {
            'unit_id': unit_id,
            'source_file': unit.get('source_file', ''),
            'page': unit.get('page', 1),
            'reproduction_path': '',
            'status': 'not_started',
            'error': '',
        })
        item['source_file'] = unit.get('source_file', '')
        item['page'] = unit.get('page', 1)

        digest_unit = _build_digest_unit_from_layers(username, analysis_id, unit_id, manifest, d_layer, m_layer, t_layer)
        if not isinstance(item.get('iter_context'), dict):
            item['iter_context'] = _build_reproduction_iter_context(
                username,
                unit,
                digest_unit,
                total_units,
                use_sketch_input=_safe_bool(item.get('use_sketch_input', default_use_sketch_input), default_use_sketch_input),
            )
            changed = True
        else:
            item['iter_context'] = _normalize_reproduction_iter_context(item.get('iter_context'))

        if not isinstance(item.get('last_generated_context'), dict):
            if item.get('status') == 'ready':
                item['last_generated_context'] = copy.deepcopy(item['iter_context'])
            else:
                item['last_generated_context'] = copy.deepcopy(item['iter_context'])
            changed = True
        else:
            item['last_generated_context'] = _normalize_reproduction_iter_context(item.get('last_generated_context'))

        item['rollback_stack'] = _normalize_reproduction_rollback_stack(item.get('rollback_stack'))

        merged_items.append(item)

    result = {'layer': 'R', 'total_units': len(merged_items), 'items': merged_items}
    if paths and (changed or not os.path.exists(paths['r_layer'])):
        _safe_json_dump(paths['r_layer'], result)
    return result


def _update_single_r_layer_item(paths: Dict[str, str], unit_id: str, updater: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    from app_chat.ci.orchestrator import _load_existing_layer

    r_layer = _load_existing_layer(paths['r_layer']) or {'layer': 'R', 'total_units': 0, 'items': []}
    items = r_layer.get('items', []) if isinstance(r_layer, dict) else []
    updated = None
    new_items: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and item.get('unit_id') == unit_id:
            updated = updater(copy.deepcopy(item))
            new_items.append(updated)
        else:
            new_items.append(item)
    if updated is None:
        raise ValueError(f'未找到 unit_id={unit_id} 对应的R层页项')
    r_layer['items'] = new_items
    r_layer['total_units'] = len(new_items)
    _safe_json_dump(paths['r_layer'], r_layer)
    return updated


def _parse_reference_image_payload(reference_image: Any) -> Tuple[Optional[str], str]:
    reference_image_mime = 'image/png'
    if reference_image and isinstance(reference_image, str) and reference_image.strip():
        ref = reference_image.strip()
        if ref.startswith('data:') and 'base64,' in ref:
            reference_image_b64 = ref.split('base64,', 1)[-1]
            try:
                prefix = ref.split('base64,', 1)[0]
                mime_part = prefix.split(':', 1)[1]
                reference_image_mime = mime_part.split(';')[0] or reference_image_mime
            except Exception:
                pass
        else:
            reference_image_b64 = ref
        return reference_image_b64, reference_image_mime
    return None, reference_image_mime


def _format_iter_context_for_prompt(ctx: Dict[str, Any]) -> str:
    return '\n'.join([
        f"- T层高价值理解补充：\n{ctx.get('t_focus_text', '') or '（空）'}",
        f"- 主要内容摘要：{ctx.get('main_content', '') or '（空）'}",
        f"- 版面区域划分：\n{ctx.get('layout_regions_text', '') or '（空）'}",
        f"- 阅读顺序：{ctx.get('reading_order', '') or '（空）'}",
        f"- 手写/印刷层说明：{ctx.get('handwriting_printing_relation', '') or '（空）'}",
        f"- 批注关系：{ctx.get('annotation_section', '') or '（空）'}",
        f"- 与前图关系：{ctx.get('continuity_text', '') or '（空）'}",
        f"- M层复核结果：{ctx.get('m_verification_text', '') or '（空）'}",
        f"- 底色指示：{ctx.get('color_instruction', '') or '（空）'}",
        f"- 信息比例：{ctx.get('ratio_instruction', '') or '（空）'}",
    ])


def _get_document_four_color_info(username: str, filename: str) -> Dict[str, str]:
    """只读获取文档的主辅四色属性，优先数据库，再降级到 segments metadata。"""
    main_four_color = ''
    secondary_four_color = ''
    dmt_level = ''

    try:
        from app_chat.scene_context_helper import get_scene_info_from_username
        from zym.models import UserNotebook, scene

        real_name = username.split('_')[0] if '_' in username else username
        book_name = username[len(real_name) + 1:] if '_' in username and len(username) > len(real_name) + 1 else None
        notebook = None

        if book_name:
            notebook = UserNotebook.objects.filter(username=real_name, bookName=book_name).first()

        if notebook is None:
            scene_name, _, _, _ = get_scene_info_from_username(username, filename)
            if scene_name:
                scene_obj = scene.objects.filter(sceneDescription=scene_name).first()
                if scene_obj:
                    notebook = UserNotebook.objects.filter(username=real_name, sid=scene_obj.sid).first()

        if notebook and notebook.documentFourColorDMT:
            doc_attrs = json.loads(notebook.documentFourColorDMT)
            attrs = doc_attrs.get(filename, {}) if isinstance(doc_attrs, dict) else {}
            main_four_color = attrs.get('main_four_color', '') or ''
            secondary_four_color = attrs.get('secondary_four_color', '') or ''
            dmt_level = attrs.get('dmt_level', '') or ''
    except Exception as e:
        print(f'[ci_repro] 读取文档四色属性失败 {filename}: {e}')

    if not main_four_color and not dmt_level:
        try:
            segments = global_var.get_user_split(username, filename)
            if segments:
                first_segment = segments[0]
                metadata = getattr(first_segment, 'metadata', {}) or {}
                main_four_color = metadata.get('main_four_color', '') or ''
                secondary_four_color = metadata.get('secondary_four_color', '') or ''
                dmt_level = metadata.get('dmt_level', '') or ''
        except Exception as e:
            print(f'[ci_repro] 读取 segments 四色属性失败 {filename}: {e}')

    return {
        'main_four_color': main_four_color,
        'secondary_four_color': secondary_four_color,
        'dmt_level': dmt_level,
    }


def _build_repro_color_instruction(color_info: Dict[str, str]) -> str:
    color_map = {
        'R': '整体以较浅的红色为主，传达专业、重点、判断感',
        'B': '整体以较浅的蓝色为主，传达工具、步骤、方法感',
        'P': '整体以较浅的紫色为主，传达框架、结构、抽象感',
        'G': '整体以较浅的绿色为主，传达自然、洞察、轻盈感',
    }
    main_color = (color_info.get('main_four_color') or '').strip().upper()
    secondary_color = (color_info.get('secondary_four_color') or '').strip().upper()

    if not main_color:
        return '整体保持中浅色调，以白底、浅灰或浅米色为主，避免大面积高饱和颜色'

    note = color_map.get(main_color, '整体保持中浅色调')
    if secondary_color and secondary_color in color_map and secondary_color != main_color:
        note += f'；可用少量{secondary_color}色系作为辅助强调，但不可压过主色'
    return note


def _generate_reproduction_image(
    username: str,
    unit: Dict[str, Any],
    d_item: Dict[str, Any],
    digest_unit: Optional[Dict[str, Any]],
    output_dir: str,
    total_units: int,
    use_sketch_input: bool = True,
    iter_context: Optional[Dict[str, Any]] = None,
    use_original_sketch_as_r: bool = False,
) -> Dict[str, Any]:
    """为单个 ImageUnit 生成升维复现图。返回 {unit_id, source_file, page, reproduction_path, status, error}。"""
    unit_id = unit['unit_id']
    source_file = unit.get('source_file', '')
    page = unit.get('page', 1)
    seq = unit.get('seq', 1)

    try:
        asset_path = ''
        if digest_unit:
            asset_path = digest_unit.get('asset_abs_path', '') or ''
        if not asset_path:
            asset_path = d_item.get('_asset_abs_path', '') or unit.get('asset_abs_path', '')
        use_orig_r = bool(use_original_sketch_as_r and use_sketch_input)

        if use_orig_r:
            if not asset_path or not os.path.exists(asset_path):
                return {
                    'unit_id': unit_id,
                    'source_file': source_file,
                    'page': page,
                    'reproduction_path': '',
                    'status': 'skipped',
                    'error': '草图文件不存在，无法直接使用原草图作为复现图',
                }
            base_ctx = iter_context or _build_reproduction_iter_context(
                username, unit, digest_unit, total_units, use_sketch_input=True
            )
            current_context = _normalize_reproduction_iter_context(
                base_ctx,
                {'use_sketch_input': True, 'use_original_sketch_as_r': True},
            )
            uid_safe = re.sub(r'[^\w\-]', '_', unit_id)
            out_filename = f'{uid_safe}_reproduction.png'
            out_abs = os.path.join(output_dir, out_filename)
            if not _copy_asset_to_reproduction_png(asset_path, out_abs):
                return {
                    'unit_id': unit_id,
                    'source_file': source_file,
                    'page': page,
                    'reproduction_path': '',
                    'status': 'failed',
                    'error': '原草图写入复现图失败',
                }
            return {
                'unit_id': unit_id,
                'source_file': source_file,
                'page': page,
                'reproduction_path': f'reproduction/{out_filename}',
                'status': 'ready',
                'error': '',
                'iter_context': copy.deepcopy(current_context),
                'last_generated_context': copy.deepcopy(current_context),
                'updated_at': _now_iso(),
            }

        if use_sketch_input and (not asset_path or not os.path.exists(asset_path)):
            return {
                'unit_id': unit_id,
                'source_file': source_file,
                'page': page,
                'reproduction_path': '',
                'status': 'skipped',
                'error': '草图文件不存在，无法按草图模式生成',
            }

        img_b64 = ''
        mime = 'image/png'
        if use_sketch_input:
            with open(asset_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')
            ext = os.path.splitext(asset_path)[1].lower()
            mime = 'image/jpeg' if ext in ('.jpg', '.jpeg') else 'image/png'

        current_context = _normalize_reproduction_iter_context(
            iter_context or _build_reproduction_iter_context(username, unit, digest_unit, total_units, use_sketch_input=use_sketch_input)
        )

        user_prompt_template = CI_R_REPRODUCTION_WITH_SKETCH_USER_PROMPT_TEMPLATE if use_sketch_input else CI_R_REPRODUCTION_WITHOUT_SKETCH_USER_PROMPT_TEMPLATE
        system_prompt = CI_R_REPRODUCTION_WITH_SKETCH_SYSTEM_PROMPT if use_sketch_input else CI_R_REPRODUCTION_WITHOUT_SKETCH_SYSTEM_PROMPT

        user_prompt = user_prompt_template.format(
            filename=source_file,
            seq=seq,
            total=total_units,
            t_focus_text=current_context.get('t_focus_text', ''),
            main_content=current_context.get('main_content', ''),
            layout_regions=current_context.get('layout_regions_text', ''),
            reading_order=current_context.get('reading_order', ''),
            handwriting_printing_relation=current_context.get('handwriting_printing_relation', ''),
            annotation_section=current_context.get('annotation_section', ''),
            continuity_text=current_context.get('continuity_text', ''),
            m_verification_text=current_context.get('m_verification_text', ''),
            color_instruction=current_context.get('color_instruction', ''),
            ratio_instruction=current_context.get('ratio_instruction', ''),
        )

        system_prompt = system_prompt + '\n\n' + CI_R_SINGLE_STEPWISE_INITIAL_SYSTEM_APPENDIX
        user_prompt = user_prompt + '\n\n' + CI_R_SINGLE_STEPWISE_INITIAL_USER_APPENDIX

        client = OpenAI(
            api_key=_GEMINI_REPRO_API_KEY,
            base_url=_GEMINI_REPRO_BASE_URL,
            timeout=_GEMINI_REPRO_TIMEOUT,
        )
        content_parts = [
            {'type': 'text', 'text': system_prompt},
        ]
        if use_sketch_input:
            content_parts.append({'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{img_b64}'}})
        content_parts.append({'type': 'text', 'text': user_prompt})
        response = client.chat.completions.create(
            model=_r_layer_gemini_model(),
            messages=[{
                'role': 'user',
                'content': content_parts,
            }],
            temperature=0.2,
            max_tokens=8192,
        )
        res = response.choices[0].message.content
        if not res:
            return {
                'unit_id': unit_id,
                'source_file': source_file,
                'page': page,
                'reproduction_path': '',
                'status': 'failed',
                'error': '模型未返回内容',
            }

        b64_img = _extract_repro_base64(res)
        if not b64_img:
            return {
                'unit_id': unit_id,
                'source_file': source_file,
                'page': page,
                'reproduction_path': '',
                'status': 'failed',
                'error': '无法从响应提取图片',
            }

        uid_safe = re.sub(r'[^\w\-]', '_', unit_id)
        out_filename = f'{uid_safe}_reproduction.png'
        out_abs = os.path.join(output_dir, out_filename)
        if not _save_repro_image(b64_img, out_abs):
            return {
                'unit_id': unit_id,
                'source_file': source_file,
                'page': page,
                'reproduction_path': '',
                'status': 'failed',
                'error': '图片文件保存失败',
            }

        return {
            'unit_id': unit_id,
            'source_file': source_file,
            'page': page,
            'reproduction_path': f'reproduction/{out_filename}',
            'status': 'ready',
            'error': '',
            'iter_context': copy.deepcopy(current_context),
            'last_generated_context': copy.deepcopy(current_context),
            'updated_at': _now_iso(),
        }
    except Exception as e:
        traceback.print_exc()
        return {
            'unit_id': unit_id,
            'source_file': source_file,
            'page': page,
            'reproduction_path': '',
            'status': 'failed',
            'error': str(e)[:200],
            'iter_context': copy.deepcopy(iter_context) if isinstance(iter_context, dict) else None,
        }


# Phase 6.3a: migrated from continuous_image_service.py R-layer orchestration core.
def build_r_layer(
    username: str,
    analysis_id: str,
    units: List[Dict[str, Any]],
    d_layer: Dict[str, Any],
    m_layer: Dict[str, Any],
    t_layer: Dict[str, Any],
    paths: Dict[str, str],
    task_id: str,
    use_sketch_input: bool = True,
    use_original_sketch_as_r: bool = False,
) -> Dict[str, Any]:
    """R 层：并发为每个 ImageUnit 生成升维复现图，保存为 r_layer.json。"""
    if not units:
        r_layer = {'layer': 'R', 'total_units': 0, 'items': []}
        _safe_json_dump(paths['r_layer'], r_layer)
        return r_layer

    from app_chat.ci.orchestrator import _load_existing_layer

    _update_task(task_id, current_section=SECTION_REPRODUCTION, current_item=0, total_items=len(units))

    d_map = {it['unit_id']: it for it in d_layer.get('items', [])}
    output_dir = paths['reproduction_dir']
    total = len(units)
    results: List[Optional[Dict[str, Any]]] = [None] * total

    manifest = _load_existing_layer(paths['manifest']) or {}
    manifest['reproduction_last_use_sketch_input'] = bool(use_sketch_input)
    manifest['reproduction_last_use_original_sketch_as_r'] = bool(use_original_sketch_as_r and use_sketch_input)
    _safe_json_dump(paths['manifest'], manifest)

    existing_r_layer = _ensure_r_layer_items(
        username,
        analysis_id,
        manifest,
        d_layer,
        m_layer,
        t_layer,
        _load_existing_layer(paths['r_layer']) or {},
        paths=paths,
    )
    existing_map = {
        item.get('unit_id', ''): item
        for item in (existing_r_layer.get('items') or [])
        if isinstance(item, dict) and item.get('unit_id')
    }

    digest_units: Dict[str, Dict[str, Any]] = {}
    try:
        from app_chat.ci_result_adapter import fetch_ci_digest_with_layers, extract_unit_digest

        digest = fetch_ci_digest_with_layers(username, analysis_id, result_layers='tm')
        if digest.get('ok'):
            for unit in units:
                unit_digest = extract_unit_digest(digest, unit['unit_id'])
                if unit_digest:
                    digest_units[unit['unit_id']] = unit_digest
        else:
            print(f"[ci_repro] 读取封装层摘要失败: {digest.get('error', '')}")
    except Exception as e:
        print(f'[ci_repro] 调用封装层失败: {e}')

    count_lock = _threading_ci.Lock()
    completed_n = [0]

    def _do_unit(idx: int, unit: Dict[str, Any]) -> None:
        d_item = d_map.get(unit['unit_id'], {})
        digest_unit = digest_units.get(unit['unit_id'])
        existing_item = copy.deepcopy(existing_map.get(unit['unit_id'], {}))
        current_context = existing_item.get('iter_context') if isinstance(existing_item.get('iter_context'), dict) else None
        unit_use_sketch_input = _safe_bool(
            (current_context or {}).get('use_sketch_input', use_sketch_input),
            bool(use_sketch_input),
        )
        batch_use_original = bool(use_original_sketch_as_r and use_sketch_input)
        unit_use_original_sketch_as_r = unit_use_sketch_input and (
            batch_use_original
            or _safe_bool((current_context or {}).get('use_original_sketch_as_r'), False)
        )
        result = _generate_reproduction_image(
            username,
            unit,
            d_item,
            digest_unit,
            output_dir,
            total,
            unit_use_sketch_input,
            iter_context=current_context,
            use_original_sketch_as_r=unit_use_original_sketch_as_r,
        )
        if result.get('status') == 'failed':
            result = _generate_reproduction_image(
                username,
                unit,
                d_item,
                digest_unit,
                output_dir,
                total,
                unit_use_sketch_input,
                iter_context=current_context,
                use_original_sketch_as_r=unit_use_original_sketch_as_r,
            )
        merged = existing_item or {
            'unit_id': unit.get('unit_id', ''),
            'source_file': unit.get('source_file', ''),
            'page': unit.get('page', 1),
            'reproduction_path': '',
            'status': 'not_started',
            'error': '',
        }
        merged.update({
            'unit_id': unit.get('unit_id', ''),
            'source_file': unit.get('source_file', ''),
            'page': unit.get('page', 1),
        })
        merged['rollback_stack'] = _normalize_reproduction_rollback_stack(existing_item.get('rollback_stack'))
        try:
            if existing_item.get('status') == 'ready':
                merged['rollback_stack'] = _append_reproduction_rollback_snapshot(paths, existing_item, reason='regenerate')
        except Exception as snapshot_error:
            print(f'[ci_repro] 记录回滚快照失败({unit.get("unit_id", "")}): {snapshot_error}')
        if result.get('status') == 'ready':
            merged.update(result)
        else:
            merged['status'] = result.get('status', 'failed')
            merged['error'] = result.get('error', '')
            merged['reproduction_path'] = result.get('reproduction_path', '') or ''
            if isinstance(result.get('iter_context'), dict):
                merged['iter_context'] = copy.deepcopy(result.get('iter_context'))
            merged['updated_at'] = _now_iso()
        results[idx] = merged
        with count_lock:
            completed_n[0] += 1
            _update_task(task_id, current_item=completed_n[0])

    max_workers = min(3, total)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = [executor.submit(_do_unit, i, u) for i, u in enumerate(units)]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                print(f'[ci_repro] build_r_layer future error: {e}')

    r_items = [r for r in results if r is not None]
    ready = sum(1 for r in r_items if r.get('status') == 'ready')
    print(f'[ci_repro] R层完成：{ready}/{total} 成功')
    r_layer = {'layer': 'R', 'total_units': len(r_items), 'items': r_items}
    _safe_json_dump(paths['r_layer'], r_layer)
    return r_layer


def _iterate_reproduction_image(
    username: str,
    unit: Dict[str, Any],
    r_item: Dict[str, Any],
    revision_instruction: Optional[str] = None,
    edit_region: Optional[Dict[str, Any]] = None,
    reference_image_b64: Optional[str] = None,
    reference_image_mime: str = 'image/png',
    reference_image_role: str = 'reference',
    image_quality: str = 'normal',
    include_full_image_context: bool = True,
    model_name: str = '',
) -> Dict[str, Any]:
    unit_id = unit.get('unit_id', '')
    source_file = unit.get('source_file', '')
    page = unit.get('page', 1)

    repro_rel = (r_item.get('reproduction_path') or '').strip()
    if not repro_rel:
        raise ValueError('当前页尚无复现图，请先生成复现图')
    repro_abs = os.path.normpath(os.path.join(_ci_dmt_root(username), unit.get('analysis_id', ''), repro_rel))
    if not os.path.isfile(repro_abs):
        raise ValueError('当前页复现图文件不存在，请先重新生成复现图')

    with open(repro_abs, 'rb') as f:
        repro_raw = f.read()
    repro_b64 = base64.b64encode(repro_raw).decode('utf-8')
    active_model = str(model_name or _r_layer_gemini_model()).strip() or _r_layer_gemini_model()

    normalized_edit_region = _normalize_edit_region(edit_region)
    use_crop_iterate = bool(normalized_edit_region)

    crop_b64 = None
    crop_region_block = ''
    crop_left = crop_top = crop_w = crop_h = 0
    target_left = target_top = target_w = target_h = 0
    target_left_in_crop = target_top_in_crop = 0
    target_right_in_crop = target_bottom_in_crop = 0
    if use_crop_iterate:
        repro_im = Image.open(io.BytesIO(repro_raw)).convert('RGBA')
        img_w, img_h = repro_im.size
        target_left, target_top, target_right, target_bottom, target_w, target_h = _region_to_pixel_box(img_w, img_h, normalized_edit_region)
        crop_region = _expand_edit_region_for_context(normalized_edit_region)
        crop_left, crop_top, crop_right, crop_bottom, crop_w, crop_h = _region_to_pixel_box(img_w, img_h, crop_region)
        target_left_in_crop = max(0, min(crop_w - 1, target_left - crop_left))
        target_top_in_crop = max(0, min(crop_h - 1, target_top - crop_top))
        target_right_in_crop = max(target_left_in_crop + 1, min(crop_w, target_right - crop_left))
        target_bottom_in_crop = max(target_top_in_crop + 1, min(crop_h, target_bottom - crop_top))
        cropped = repro_im.crop((crop_left, crop_top, crop_right, crop_bottom))
        crop_buf = io.BytesIO()
        cropped.save(crop_buf, format='PNG')
        crop_b64 = base64.b64encode(crop_buf.getvalue()).decode('utf-8')
        crop_region_block = _format_crop_iterate_region_block(
            normalized_edit_region,
            crop_region,
            img_w,
            img_h,
            crop_left,
            crop_top,
            crop_w,
            crop_h,
            target_left_in_crop,
            target_top_in_crop,
            target_right_in_crop - target_left_in_crop,
            target_bottom_in_crop - target_top_in_crop,
        )

    current_context = _normalize_reproduction_iter_context(r_item.get('iter_context'))
    old_context = _normalize_reproduction_iter_context(r_item.get('last_generated_context') or current_context)

    use_sketch_input = _safe_bool(current_context.get('use_sketch_input', True), True)
    sketch_b64 = ''
    sketch_mime = 'image/png'
    asset_path = unit.get('asset_abs_path', '') or ''
    if use_sketch_input and asset_path and os.path.isfile(asset_path):
        with open(asset_path, 'rb') as f:
            sketch_b64 = base64.b64encode(f.read()).decode('utf-8')
        ext = os.path.splitext(asset_path)[1].lower()
        sketch_mime = 'image/jpeg' if ext in ('.jpg', '.jpeg') else 'image/png'

    base_system_prompt = CI_R_REPRODUCTION_WITH_SKETCH_SYSTEM_PROMPT if use_sketch_input else CI_R_REPRODUCTION_WITHOUT_SKETCH_SYSTEM_PROMPT
    user_revision_block = ''
    if revision_instruction and revision_instruction.strip():
        user_revision_block = f"\n\n【用户对本次迭代的具体修改要求】\n{revision_instruction.strip()[:2000]}\n"
    reference_image_block = ''
    reference_image_role = str(reference_image_role or 'reference').strip().lower()
    reference_image_label = '【用户提供的参考图】'
    if reference_image_b64 and reference_image_b64.strip():
        if reference_image_role == 'original_sketch_crop':
            reference_image_label = '【原始草图局部】'
            reference_image_block = (
                "\n\n【原始草图局部】\n"
                '这不是普通参考图，而是本次目标框内手写笔迹、线条、符号、轮廓的唯一来源。'
                '你必须尽量原样保留其中可见的手写痕迹；除这些痕迹外，其余背景、底纹、留白、'
                '颜色和边缘衔接都应与当前复现图局部保持一致。\n'
            )
        else:
            reference_image_block = "\n\n【用户提供的参考图】\n若用户希望某一块区域改成类似参考图的结构或感觉，请结合下方当前/历史生成依据一起落实；严禁直接照抄参考图内容。\n"

    if use_crop_iterate:
        full_ref_line = (
            "- 第二张图为完整当前复现图，仅用于理解该局部在整页中的位置、邻接关系和边缘衔接；禁止输出整页。\n"
            if include_full_image_context
            else "- 本次不再提供完整整图参考；仅根据第一张局部上下文裁切图完成修改。\n"
        )
        instruction = f"""你现在要对一张已经生成好的「R层升维复现图」做局部裁切迭代更新。

【必须继续遵守的基础复现规范】
{base_system_prompt}

【输入说明（局部裁切模式）】
- 第一张图为当前复现图的局部上下文裁切图，其中已经标明了真正允许修改的目标框；你最终仍需输出与第一张图同尺寸的局部图。
{full_ref_line.rstrip()}
- 若提供原始草图，它只是帮助你校正该局部与原图结构的一致性；若提供参考图，它只用于目标局部的效果参考。
{crop_region_block}

【本次迭代总原则】
1. 只修改上述锁定局部，其余区域保持不变；尤其不要把原本占满目标框的内容整体缩小后摆在中间。
2. 若“当前生成依据”相较“上次生成依据”只有少量变化，则只做小范围更新，不要推翻重画。
3. 任何修改都必须继续服从 R 层的布局保真、辨识度分层和“不新增知识”规则。
4. 输出必须是一张局部图，尺寸与第一张局部上下文裁切图完全一致，供后端从中裁出目标框后拼回完整复现图。
5. 若目标框内存在标题、正文、批注、表格、公式或标签，默认沿用输入图中的字级、字高、块宽占比和对齐关系；除非用户明确要求缩小或放大，否则不得整体改变这些比例。
{user_revision_block}{reference_image_block}

【上次生成该页复现图时使用的生成依据】
{_format_iter_context_for_prompt(old_context)}

【当前希望用于迭代该页复现图的生成依据】
{_format_iter_context_for_prompt(current_context)}

请仅输出修改后的局部图片。"""
    else:
        instruction = f"""你现在要对一张已经生成好的「R层升维复现图」做局部迭代更新。

【必须继续遵守的基础复现规范】
{base_system_prompt}

【本次迭代总原则】
1. 保持当前复现图的整体风格、配色、布局骨架和视觉语言稳定，只更新真正需要变化的局部。
2. 若“当前生成依据”相较“上次生成依据”只有少量变化，则只做小范围更新，不要推翻重画。
3. 任何修改都必须继续服从 R 层的布局保真、辨识度分层和“不新增知识”规则。
4. 当前复现图是主要保留对象；若提供了原草图，则原草图用于校正结构保真；若提供了参考图，则参考图只用于目标区域的效果参考。
{user_revision_block}{reference_image_block}

【上次生成该页复现图时使用的生成依据】
{_format_iter_context_for_prompt(old_context)}

【当前希望用于迭代该页复现图的生成依据】
{_format_iter_context_for_prompt(current_context)}

请基于当前复现图做一次完整的图片迭代，直接输出修改后的完整图片。"""

    if active_model.lower().startswith('gpt-image'):
        # gpt-image 系列在 chat.completions 下常返回中间态文本，局部候选改走 images.edit 提升稳定性。
        primary_b64 = crop_b64 if use_crop_iterate else repro_b64
        b64_img = _generate_image_via_images_edit(
            model_name=active_model,
            prompt_text=instruction,
            input_image_b64=primary_b64 or '',
            input_mime='image/png',
        )
        if not b64_img:
            raise ValueError('gpt-image images.edit 未返回可用图像（data[0].b64_json/url 为空）')
    elif str(image_quality).strip().lower() == 'high':
        if use_crop_iterate:
            native_parts = [
                {'text': '【当前R层复现图的局部上下文裁切图】（主输入；只输出与此图同尺寸的修改后局部图，且只改其中锁定目标框）：'},
                {'inlineData': {'mimeType': 'image/png', 'data': crop_b64}},
            ]
            if include_full_image_context:
                native_parts.extend([
                    {'text': '【完整当前R层复现图】（上下文参考；仅用于理解边缘衔接，禁止输出整图）：'},
                    {'inlineData': {'mimeType': 'image/png', 'data': repro_b64}},
                ])
        else:
            native_parts = [
                {'text': '【当前R层复现图】（请基于此图做局部迭代，尽量保持其风格与布局稳定）：'},
                {'inlineData': {'mimeType': 'image/png', 'data': repro_b64}},
            ]
        if sketch_b64:
            native_parts.extend([
                {'text': '【原始草图】（用于保证迭代后仍贴合原图结构）：'},
                {'inlineData': {'mimeType': sketch_mime, 'data': sketch_b64}},
            ])
        native_parts.append({'text': instruction})
        if reference_image_b64 and reference_image_b64.strip():
            native_parts.extend([
                {'text': reference_image_label},
                {'inlineData': {'mimeType': reference_image_mime or 'image/png', 'data': reference_image_b64.strip()}},
            ])
        b64_img = _gemini_repro_native_generate_image_from_parts(native_parts, image_size='4K', model_name=active_model)
    else:
        client = OpenAI(
            api_key=_GEMINI_REPRO_API_KEY,
            base_url=_GEMINI_REPRO_BASE_URL,
            timeout=_GEMINI_REPRO_TIMEOUT,
        )
        if use_crop_iterate:
            content_parts = [
                {'type': 'text', 'text': '【当前R层复现图的局部上下文裁切图】（主输入；只输出与此图同尺寸的修改后局部图，且只改其中锁定目标框）：'},
                {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{crop_b64}'}},
            ]
            if include_full_image_context:
                content_parts.extend([
                    {'type': 'text', 'text': '【完整当前R层复现图】（上下文参考；仅用于理解边缘衔接，禁止输出整图）：'},
                    {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{repro_b64}'}},
                ])
        else:
            content_parts = [
                {'type': 'text', 'text': '【当前R层复现图】（请基于此图做局部迭代，尽量保持其风格与布局稳定）：'},
                {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{repro_b64}'}},
            ]
        if sketch_b64:
            content_parts.extend([
                {'type': 'text', 'text': '【原始草图】（用于保证迭代后仍贴合原图结构）：'},
                {'type': 'image_url', 'image_url': {'url': f'data:{sketch_mime};base64,{sketch_b64}'}},
            ])
        content_parts.append({'type': 'text', 'text': instruction})
        if reference_image_b64 and reference_image_b64.strip():
            content_parts.extend([
                {'type': 'text', 'text': reference_image_label},
                {'type': 'image_url', 'image_url': {'url': f'data:{reference_image_mime or "image/png"};base64,{reference_image_b64.strip()}'}},
            ])
        response = client.chat.completions.create(
            model=active_model,
            messages=[{'role': 'user', 'content': content_parts}],
            temperature=0.2,
            max_tokens=8192,
        )
        b64_img = _extract_repro_base64_from_completion(response)
        if not b64_img:
            # 向后兼容：若 content 为纯字符串，再走旧解析一次
            res = response.choices[0].message.content
            if isinstance(res, str):
                b64_img = _extract_repro_base64(res)
        if not b64_img:
            debug_summary = _brief_completion_debug(response)
            raise ValueError(f'无法从响应提取图片；响应摘要: {debug_summary}')

    if not b64_img:
        raise ValueError('无法从响应提取图片')
    if use_crop_iterate:
        edited_pil = _pil_from_response_base64(b64_img)
        if edited_pil is None:
            raise ValueError('局部裁切模式无法解码模型返回图片')
        try:
            edited_crop = edited_pil.convert('RGBA')
            if edited_crop.size != (crop_w, crop_h):
                edited_crop = edited_crop.resize((crop_w, crop_h), _resample_lanczos())
            edited_target = edited_crop.crop((
                target_left_in_crop,
                target_top_in_crop,
                target_right_in_crop,
                target_bottom_in_crop,
            ))
            final_im = _composite_edited_crop_onto_original(repro_abs, target_left, target_top, target_w, target_h, edited_target)
            final_im.save(repro_abs, 'PNG')
        except Exception as exc:
            raise ValueError(f'局部裁切模式拼回原图失败: {exc}') from exc
    elif not _save_repro_image(b64_img, repro_abs):
        raise ValueError('迭代后的图片保存失败')

    return {
        'unit_id': unit_id,
        'source_file': source_file,
        'page': page,
        'reproduction_path': repro_rel.replace('\\', '/'),
        'status': 'ready',
        'error': '',
        'iter_context': copy.deepcopy(current_context),
        'last_generated_context': copy.deepcopy(current_context),
        'updated_at': _now_iso(),
    }


def iterate_ci_reproduction_unit(
    task_id: str,
    username: str,
    analysis_id: str,
    unit_id: str,
    revision_instruction: Optional[str] = None,
    edit_region: Optional[Dict[str, Any]] = None,
    reference_image_b64: Optional[str] = None,
    reference_image_mime: str = 'image/png',
    image_quality: str = 'normal',
    iter_context_updates: Optional[Dict[str, Any]] = None,
) -> None:
    from app_chat.ci.orchestrator import prepare_analysis_workspace, _load_existing_layer

    try:
        _update_task(task_id, current_item=0, total_items=1, current_section=SECTION_PREPARING, completed=False, error='')
        paths = prepare_analysis_workspace(username, analysis_id)
        manifest = _load_existing_layer(paths['manifest']) or {}
        d_layer = _load_existing_layer(paths['d_layer']) or {}
        m_layer = _load_existing_layer(paths['m_layer']) or {}
        t_layer = _load_existing_layer(paths['t_layer']) or {}
        r_layer = _ensure_r_layer_items(
            username,
            analysis_id,
            manifest,
            d_layer,
            m_layer,
            t_layer,
            _load_existing_layer(paths['r_layer']) or {},
            paths=paths,
        )
        unit_list = _analysis_units_from_manifest(username, analysis_id, manifest)
        unit_map = {unit.get('unit_id', ''): unit for unit in unit_list if unit.get('unit_id')}
        unit = unit_map.get(unit_id)
        if not unit:
            raise ValueError(f'未找到 unit_id={unit_id} 对应的分析页')
        unit['analysis_id'] = analysis_id

        current_item = next((item for item in (r_layer.get('items') or []) if item.get('unit_id') == unit_id), None)
        if not current_item:
            raise ValueError(f'未找到 unit_id={unit_id} 对应的R层页项')

        rollback_stack = _normalize_reproduction_rollback_stack(current_item.get('rollback_stack'))
        try:
            if current_item.get('status') == 'ready':
                rollback_stack = _append_reproduction_rollback_snapshot(paths, current_item, reason='iterate')
        except Exception as snapshot_error:
            print(f'[ci_repro] 单页迭代记录回滚快照失败({unit_id}): {snapshot_error}')

        if isinstance(iter_context_updates, dict) and iter_context_updates:
            current_item = _update_single_r_layer_item(
                paths,
                unit_id,
                lambda item: {
                    **item,
                    'rollback_stack': rollback_stack,
                    'iter_context': _normalize_reproduction_iter_context(item.get('iter_context'), iter_context_updates),
                    'updated_at': _now_iso(),
                },
            )

        _update_task(task_id, current_section=SECTION_REPRODUCTION, current_item=0, total_items=1)
        result = _iterate_reproduction_image(
            username,
            unit,
            current_item,
            revision_instruction=revision_instruction,
            edit_region=edit_region,
            reference_image_b64=reference_image_b64,
            reference_image_mime=reference_image_mime,
            image_quality=image_quality,
        )

        _update_single_r_layer_item(
            paths,
            unit_id,
            lambda item: {
                **item,
                'rollback_stack': rollback_stack,
                **result,
            },
        )
        _update_task(task_id, current_section=SECTION_FINALIZING, current_item=1, total_items=1)
        _update_task(task_id, current_section=SECTION_COMPLETED, current_item=1, total_items=1, completed=True, error='')
    except Exception as e:
        traceback.print_exc()
        try:
            paths = prepare_analysis_workspace(username, analysis_id)
            _update_single_r_layer_item(
                paths,
                unit_id,
                lambda item: {
                    **item,
                    'rollback_stack': rollback_stack if 'rollback_stack' in locals() else _normalize_reproduction_rollback_stack(item.get('rollback_stack')),
                    'status': 'failed',
                    'error': str(e)[:200],
                    'updated_at': _now_iso(),
                },
            )
        except Exception:
            pass
        _update_task(task_id, current_section=SECTION_FAILED, current_item=1, total_items=1, completed=True, error=str(e))
    finally:
        _set_reproduction_iterating(username, analysis_id, unit_id, False)


def save_ci_reproduction_iter_context(
    username: str,
    analysis_id: str,
    unit_id: str,
    iter_context_updates: Dict[str, Any],
) -> Dict[str, Any]:
    from app_chat.ci.orchestrator import prepare_analysis_workspace, _load_existing_layer

    paths = prepare_analysis_workspace(username, analysis_id)
    manifest = _load_existing_layer(paths['manifest']) or {}
    d_layer = _load_existing_layer(paths['d_layer']) or {}
    m_layer = _load_existing_layer(paths['m_layer']) or {}
    t_layer = _load_existing_layer(paths['t_layer']) or {}
    _ensure_r_layer_items(
        username,
        analysis_id,
        manifest,
        d_layer,
        m_layer,
        t_layer,
        _load_existing_layer(paths['r_layer']) or {},
        paths=paths,
    )
    item = _update_single_r_layer_item(
        paths,
        unit_id,
        lambda current: {
            **current,
            'iter_context': _normalize_reproduction_iter_context(current.get('iter_context'), iter_context_updates),
            'updated_at': _now_iso(),
        },
    )
    return _sanitize_reproduction_item_for_response(item)


def save_ci_reproduction_file(
    username: str,
    analysis_id: str,
    unit_id: str,
    reproduction_image: Any,
) -> Dict[str, Any]:
    from app_chat.ci.orchestrator import prepare_analysis_workspace, _load_existing_layer
    from app_chat.ci.legacy import _set_manifest_reproduction_status

    paths = prepare_analysis_workspace(username, analysis_id)
    manifest = _load_existing_layer(paths['manifest']) or {}
    d_layer = _load_existing_layer(paths['d_layer']) or {}
    m_layer = _load_existing_layer(paths['m_layer']) or {}
    t_layer = _load_existing_layer(paths['t_layer']) or {}
    r_layer = _ensure_r_layer_items(
        username,
        analysis_id,
        manifest,
        d_layer,
        m_layer,
        t_layer,
        _load_existing_layer(paths['r_layer']) or {},
        paths=paths,
    )

    item = next((entry for entry in (r_layer.get('items') or []) if isinstance(entry, dict) and entry.get('unit_id') == unit_id), None)
    if not item:
        raise ValueError(f'未找到 unit_id={unit_id} 对应的R层页项')
    if _is_reproduction_iterating(username, analysis_id, unit_id):
        raise ValueError('该页复现图正在迭代中，请稍后再试')

    reproduction_rel = _normalize_rel(str(item.get('reproduction_path') or '').strip())
    if not reproduction_rel:
        raise ValueError('当前页暂无可编辑的复现图')

    reproduction_abs = os.path.normpath(os.path.join(paths['root'], reproduction_rel))
    if not os.path.isfile(reproduction_abs):
        raise ValueError('当前复现图文件不存在，无法保存编辑结果')

    rollback_stack = _normalize_reproduction_rollback_stack(item.get('rollback_stack'))
    try:
        rollback_stack = _append_reproduction_rollback_snapshot(paths, item, reason='manual_edit')
    except Exception as snapshot_error:
        print(f'[ci_repro] 手工编辑记录回滚快照失败({unit_id}): {snapshot_error}')

    image_bytes = _decode_inline_image_bytes(reproduction_image)
    os.makedirs(os.path.dirname(reproduction_abs), exist_ok=True)
    with open(reproduction_abs, 'wb') as f:
        f.write(image_bytes)

    updated_item = _update_single_r_layer_item(
        paths,
        unit_id,
        lambda current: {
            **current,
            'reproduction_path': reproduction_rel,
            'status': 'ready',
            'error': '',
            'rollback_stack': rollback_stack,
            'updated_at': _now_iso(),
        },
    )
    _set_manifest_reproduction_status(paths, manifest, 'completed')
    return _sanitize_reproduction_item_for_response(updated_item)


def rollback_ci_reproduction_unit(
    username: str,
    analysis_id: str,
    unit_id: str,
) -> Dict[str, Any]:
    from app_chat.ci.orchestrator import prepare_analysis_workspace, _load_existing_layer
    from app_chat.ci.legacy import _set_manifest_reproduction_status

    paths = prepare_analysis_workspace(username, analysis_id)
    manifest = _load_existing_layer(paths['manifest']) or {}
    d_layer = _load_existing_layer(paths['d_layer']) or {}
    m_layer = _load_existing_layer(paths['m_layer']) or {}
    t_layer = _load_existing_layer(paths['t_layer']) or {}
    r_layer = _ensure_r_layer_items(
        username,
        analysis_id,
        manifest,
        d_layer,
        m_layer,
        t_layer,
        _load_existing_layer(paths['r_layer']) or {},
        paths=paths,
    )

    item = next((entry for entry in (r_layer.get('items') or []) if isinstance(entry, dict) and entry.get('unit_id') == unit_id), None)
    if not item:
        raise ValueError(f'未找到 unit_id={unit_id} 对应的R层页项')
    if _is_reproduction_iterating(username, analysis_id, unit_id):
        raise ValueError('该页复现图正在迭代中，请稍后再试')

    rollback_stack = _normalize_reproduction_rollback_stack(item.get('rollback_stack'))
    if not rollback_stack:
        raise ValueError('当前页暂无可回滚版本')

    snapshot = rollback_stack.pop()
    snapshot_rel = _normalize_rel(snapshot.get('snapshot_path', ''))
    reproduction_rel = _normalize_rel(snapshot.get('reproduction_path') or item.get('reproduction_path') or '')
    if not snapshot_rel or not reproduction_rel:
        raise ValueError('回滚版本信息不完整')

    snapshot_abs = os.path.normpath(os.path.join(paths['root'], snapshot_rel))
    target_abs = os.path.normpath(os.path.join(paths['root'], reproduction_rel))
    if not os.path.isfile(snapshot_abs):
        raise ValueError('回滚快照文件不存在，无法执行回滚')

    os.makedirs(os.path.dirname(target_abs), exist_ok=True)
    shutil.copy2(snapshot_abs, target_abs)
    _cleanup_reproduction_snapshot_file(paths, snapshot_rel)

    updated_item = _update_single_r_layer_item(
        paths,
        unit_id,
        lambda current: {
            **current,
            'reproduction_path': reproduction_rel,
            'status': 'ready',
            'error': '',
            'iter_context': copy.deepcopy(snapshot.get('iter_context') or current.get('iter_context')),
            'last_generated_context': copy.deepcopy(snapshot.get('last_generated_context') or snapshot.get('iter_context') or current.get('last_generated_context') or current.get('iter_context')),
            'rollback_stack': rollback_stack,
            'updated_at': _now_iso(),
        },
    )

    _set_manifest_reproduction_status(paths, manifest, 'completed')
    return _sanitize_reproduction_item_for_response(updated_item)