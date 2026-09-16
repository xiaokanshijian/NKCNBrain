"""
ci/d_layer.py — D 层模块：OCR 缓存管理 + 区域置信度分类 + 灰区/黑区修复 + D层编排

迁移来源：
  DCacheManager           — continuous_image_service.py L202-401 (Phase 3.1)
  RegionConfidenceClassifier + constants — continuous_image_service.py L2196-2368 (Phase 3.2)
  D 层函数群             — continuous_image_service.py (Phase 3.3)
"""

import base64
import io
import os
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

import fitz
from PIL import Image
from llm_langchain.pdf_ocr_utils import run_remote_ocr_asset

from app_chat.ci_prompts import (
    CI_D_GREY_REPAIR_SYSTEM_PROMPT,
    CI_D_GREY_REPAIR_USER_PROMPT_TEMPLATE,
    CI_D_BLACK_DESCRIBE_SYSTEM_PROMPT,
    CI_D_BLACK_DESCRIBE_USER_PROMPT_TEMPLATE,
)
from app_chat.ci._utils import (
    _safe_json_load, _safe_json_dump, _read_text_if_exists, _update_task,
    _resolve_user_file_path, _ci_dmt_root, _ci_d_cache_root,
)
from app_chat.ci._llm import _call_qwen_vl_flash_fast, _parse_llm_json

# 文件扩展名（本模块内独立定义，与 continuous_image_service.py 中保持一致）
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
PDF_EXTENSIONS = {'.pdf'}

# ── RegionConfidenceClassifier 所用常量 ──────────────────────────────────────
# from continuous_image_service.py L2196-2207
_ZONE_THRESHOLDS = {
    'white_mean_logprob': -0.3,
    'white_low_conf_ratio': 0.1,
    'grey_mean_logprob': -1.5,
    'grey_low_conf_ratio': 0.4,
    'token_low_threshold': -1.0,  # 单 token 视为"低置信"的阈值
}

# OCR 输出中用于定位区域的特殊标签 token，在计算置信度时排除
_TAG_PATTERNS = re.compile(
    r'<\|ref\|>|<\|/ref\|>|<\|det\|>|<\|/det\|>|<\|grounding\|>|<\|im_start\|>|<\|im_end\|>'
)


# ═══════════════════════════════════════════════════════════════
# Phase 3.1 — DCacheManager
# ═══════════════════════════════════════════════════════════════
# from continuous_image_service.py L202-401

class DCacheManager:
    """管理 continuous_image_dmt/d_cache/{filename}/ 共享 D 层 OCR 缓存。"""

    CACHE_VERSION = 2

    @staticmethod
    def _unit_dir(username: str, filename: str, page: Optional[int] = None) -> str:
        safe_name = os.path.basename(filename.replace('/', '_').replace('\\', '_'))
        safe = f'{safe_name}__p{page}' if page and page > 0 else safe_name
        return os.path.join(_ci_d_cache_root(username), safe)

    @staticmethod
    def _meta_path(unit_dir: str) -> str:
        return os.path.join(unit_dir, 'meta.json')

    @staticmethod
    def _is_valid(username: str, filename: str, page: Optional[int] = None) -> bool:
        unit_dir = DCacheManager._unit_dir(username, filename, page)
        meta_path = DCacheManager._meta_path(unit_dir)
        if not os.path.exists(meta_path):
            return False
        try:
            meta = _safe_json_load(meta_path)
        except Exception:
            return False
        if meta.get('cache_version', 1) < DCacheManager.CACHE_VERSION:
            return False
        # OCR 文本文件必须存在
        if not os.path.exists(os.path.join(unit_dir, 'ocr_raw.txt')):
            return False
        # 新结构必须包含区域分区结果
        if not os.path.exists(os.path.join(unit_dir, 'regions.json')):
            return False
        src = _resolve_user_file_path(username, filename)
        if not src or not os.path.exists(src):
            return True  # 源文件已不存在，缓存仍有效
        return (abs(meta.get('mtime', 0) - os.path.getmtime(src)) < 2.0
                and meta.get('size', -1) == os.path.getsize(src))

    @staticmethod
    def read_unit(username: str, filename: str, page: Optional[int] = None) -> Optional[Dict[str, Any]]:
        unit_dir = DCacheManager._unit_dir(username, filename, page)
        if not os.path.exists(DCacheManager._meta_path(unit_dir)):
            return None
        asset_path = os.path.join(unit_dir, 'asset.png')
        layout_path = os.path.join(unit_dir, 'layout_visual.png')
        meta = _safe_json_load(DCacheManager._meta_path(unit_dir))
        if meta.get('cache_version', 1) < DCacheManager.CACHE_VERSION:
            return None
        # 读取区域分区结果（新缓存格式）
        regions_path = os.path.join(unit_dir, 'regions.json')
        if not os.path.exists(regions_path):
            return None
        regions = []
        zone_summary = {'white': 0, 'grey': 0, 'black': 0}
        ocr_text_enhanced = ''
        if os.path.exists(regions_path):
            try:
                regions_data = _safe_json_load(regions_path)
                regions = regions_data.get('regions', [])
                zone_summary = regions_data.get('zone_summary', zone_summary)
                ocr_text_enhanced = regions_data.get('ocr_text_enhanced', '')
            except Exception:
                pass
        return {
            'ocr_text': _read_text_if_exists(os.path.join(unit_dir, 'ocr_raw.txt'), ''),
            'ocr_markdown': _read_text_if_exists(os.path.join(unit_dir, 'ocr_markdown.md'), ''),
            'asset_abs_path': asset_path if os.path.exists(asset_path) else '',
            'layout_visual_abs_path': layout_path if os.path.exists(layout_path) else '',
            'low_confidence_hint': meta.get('low_confidence_hint', False),
            'unit_dir': unit_dir,
            'regions': regions,
            'zone_summary': zone_summary,
            'ocr_text_enhanced': ocr_text_enhanced,
        }

    @staticmethod
    def get_or_build(username: str, filename: str, model_id: Optional[str] = None,
                     page: Optional[int] = None, asset_abs_path: str = '') -> Dict[str, Any]:
        """取有效缓存，或执行 OCR 后写入缓存，始终返回数据 dict。"""
        unit_dir = DCacheManager._unit_dir(username, filename, page)
        os.makedirs(unit_dir, exist_ok=True)

        if DCacheManager._is_valid(username, filename, page):
            result = DCacheManager.read_unit(username, filename, page)
            if result is not None:
                return result

        # ── 拷贝 asset ─────────────────────────────────────────
        src = _resolve_user_file_path(username, filename)
        asset_path = os.path.join(unit_dir, 'asset.png')
        ext = os.path.splitext(filename)[1].lower()
        if asset_abs_path and os.path.exists(asset_abs_path):
            shutil.copy2(asset_abs_path, asset_path)
        elif src and os.path.exists(src):
            if ext in IMAGE_EXTENSIONS:
                shutil.copy2(src, asset_path)
            elif ext in PDF_EXTENSIONS and (not page or page <= 1):
                try:
                    doc = fitz.open(src)
                    first_page = doc.load_page(0)
                    pix = first_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    pix.save(asset_path)
                    doc.close()
                except Exception as e:
                    print(f'[DCacheManager] PDF→PNG failed ({filename}): {e}')

        # ── OCR ────────────────────────────────────────────────
        ocr_text = ''
        ocr_markdown = ''
        ocr_res_token_logprobs = []
        if os.path.exists(asset_path):
            # 先查旧格式 ocr_cache（同名文件已存在旧分析目录中）
            old_cache_text, old_cache_md = ('', '')
            if not page or page == 1:
                old_cache_text, old_cache_md = _try_load_pdf_cached_segments_for_image(username, filename)
            if old_cache_text:
                ocr_text = old_cache_text
                ocr_markdown = old_cache_md or old_cache_text
            else:
                try:
                    res = run_remote_ocr_asset(
                        file_path=asset_path,
                        output_dir=unit_dir,
                        input_type='image',
                        model_id=model_id,
                    )
                    if res.get('success'):
                        ocr_text = res.get('raw_text', '')
                        ocr_markdown = res.get('markdown', {}).get('markdown_content', '') or ocr_text
                        ocr_res_token_logprobs = res.get('token_logprobs', [])
                except Exception as e:
                    print(f'[DCacheManager] OCR failed ({filename}): {e}')

        with open(os.path.join(unit_dir, 'ocr_raw.txt'), 'w', encoding='utf-8') as f:
            f.write(ocr_text)
        with open(os.path.join(unit_dir, 'ocr_markdown.md'), 'w', encoding='utf-8') as f:
            f.write(ocr_markdown)

        # ── 版面可视化 ──────────────────────────────────────────
        # 惰性导入：_build_image_layout_visual 在 Phase 4.6 将迁移至 m_layer.py
        from app_chat.continuous_image_service import _build_image_layout_visual  # noqa: PLC0415
        layout_visual_path = ''
        raw_txt_path = os.path.join(unit_dir, 'ocr_raw.txt')
        layout_out = os.path.join(unit_dir, 'layout_visual.png')
        if ocr_text and os.path.exists(asset_path):
            try:
                ok = _build_image_layout_visual(asset_path, raw_txt_path, layout_out)
                if ok:
                    layout_visual_path = layout_out
            except Exception:
                pass

        # ── 区域级置信度分区（白/灰/黑）──────────────────────────
        conf_result = compute_unit_confidence(ocr_text, ocr_res_token_logprobs)
        regions = conf_result['regions']
        zone_summary = conf_result['zone_summary']

        # ── 灰区修复 + 黑区描述 ──────────────────────────────────
        if zone_summary.get('grey', 0) > 0:
            _repair_grey_regions(regions, asset_path)
        if zone_summary.get('black', 0) > 0:
            _describe_black_regions(regions, asset_path)

        # ── 构建增强OCR文本 ─────────────────────────────────────
        ocr_text_enhanced = _build_enhanced_ocr_text(regions) if regions else ocr_text

        # ── 保存 regions.json ─────────────────────────────────
        regions_path = os.path.join(unit_dir, 'regions.json')
        _safe_json_dump(regions_path, {
            'regions': regions,
            'zone_summary': zone_summary,
            'ocr_text_enhanced': ocr_text_enhanced,
        })

        # ── 写 meta ────────────────────────────────────────────
        mtime = os.path.getmtime(src) if src and os.path.exists(src) else 0
        size = os.path.getsize(src) if src and os.path.exists(src) else 0
        low_confidence = conf_result['low_confidence_hint']
        _safe_json_dump(DCacheManager._meta_path(unit_dir), {
            'cache_version': DCacheManager.CACHE_VERSION,
            'filename': filename,
            'page': page or 1,
            'mtime': mtime,
            'size': size,
            'low_confidence_hint': low_confidence,
            'zone_summary': zone_summary,
            'grey_repaired': any(r.get('zone') == 'grey' and r.get('content_repaired') for r in regions),
            'black_described': any(r.get('zone') == 'black' and r.get('content_repaired') for r in regions),
        })

        return {
            'ocr_text': ocr_text,
            'ocr_markdown': ocr_markdown,
            'asset_abs_path': asset_path if os.path.exists(asset_path) else '',
            'layout_visual_abs_path': layout_visual_path,
            'low_confidence_hint': low_confidence,
            'unit_dir': unit_dir,
            'regions': regions,
            'zone_summary': zone_summary,
            'ocr_text_enhanced': ocr_text_enhanced,
        }


# ═══════════════════════════════════════════════════════════════
# Phase 3.2 — RegionConfidenceClassifier
# ═══════════════════════════════════════════════════════════════
# from continuous_image_service.py L2210-2368

class RegionConfidenceClassifier:
    """将 token 级 logprobs 映射到 OCR 检测区域，按区域计算置信度并分类白/灰/黑。"""

    @staticmethod
    def classify(raw_text: str, token_logprobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        主入口：解析 raw_text 中的区域标签，结合 token logprobs 给每个区域分类。

        返回区域列表，每项：
        {
            "region_id": str, "type": str, "bbox": list, "zone": "white"|"grey"|"black",
            "confidence_score": float, "content": str,
            "content_repaired": None, "repair_method": None,
            "metrics": {"mean_logprob": float, "min_logprob": float, "low_conf_ratio": float}
        }
        """
        regions = RegionConfidenceClassifier._parse_regions(raw_text)
        if not regions:
            return []
        if not token_logprobs:
            # 无 logprobs 时 fallback 到启发式
            return RegionConfidenceClassifier._fallback_heuristic(regions)

        for region in regions:
            start = region['_text_start']
            end = region['_text_end']
            # 收集覆盖该区域文本范围的所有 content token logprobs（排除标签 token）
            region_lps = []
            for lp_entry in token_logprobs:
                t_offset = lp_entry['offset']
                t_end = t_offset + len(lp_entry.get('token', ''))
                # token 与区域内容范围有交集
                if t_end > start and t_offset < end:
                    # 排除标签类 token
                    if not _TAG_PATTERNS.search(lp_entry.get('token', '')):
                        region_lps.append(lp_entry['logprob'])

            if region_lps:
                mean_lp = sum(region_lps) / len(region_lps)
                min_lp = min(region_lps)
                low_count = sum(1 for lp in region_lps if lp < _ZONE_THRESHOLDS['token_low_threshold'])
                low_ratio = low_count / len(region_lps)
            else:
                mean_lp = -999.0
                min_lp = -999.0
                low_ratio = 1.0

            zone = RegionConfidenceClassifier._classify_zone(mean_lp, low_ratio)
            # confidence_score: 将 mean_logprob 映射到 [0, 1]
            conf_score = max(0.0, min(1.0, 1.0 + mean_lp)) if mean_lp > -1.0 else max(0.0, 0.5 * (1.0 + mean_lp / 3.0))

            region['zone'] = zone
            region['confidence_score'] = round(conf_score, 3)
            region['metrics'] = {
                'mean_logprob': round(mean_lp, 4),
                'min_logprob': round(min_lp, 4),
                'low_conf_ratio': round(low_ratio, 4),
            }

        # 清理内部字段
        for r in regions:
            r.pop('_text_start', None)
            r.pop('_text_end', None)
        return regions

    @staticmethod
    def _parse_regions(raw_text: str) -> List[Dict[str, Any]]:
        """从 raw_text 解析 <|ref|>type<|/ref|><|det|>coords<|/det|> 标记的区域。"""
        pattern = r'<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>'
        regions = []
        region_idx = 0

        for m in re.finditer(pattern, raw_text, re.DOTALL):
            region_type = m.group(1).strip()
            coords_str = m.group(2).strip()

            bboxes = []
            try:
                cor_list = eval(coords_str)
                for points in cor_list:
                    if len(points) >= 4:
                        bboxes.append(list(points[:4]))
            except Exception:
                continue

            # 确定该区域内容的文本范围（标签之后到下一个标签之前）
            tag_end = m.end()
            next_tag = re.search(r'<\|ref\|>', raw_text[tag_end:])
            content_end = tag_end + next_tag.start() if next_tag else len(raw_text)
            content_text = raw_text[tag_end:content_end].strip()

            if not bboxes:
                continue

            region_idx += 1
            regions.append({
                'region_id': f'r{region_idx:03d}',
                'type': region_type,
                'bbox': bboxes[0],
                'bboxes': bboxes,
                'zone': 'white',
                'confidence_score': 1.0,
                'content': content_text,
                'content_repaired': None,
                'repair_method': None,
                'metrics': {'mean_logprob': 0.0, 'min_logprob': 0.0, 'low_conf_ratio': 0.0},
                '_text_start': tag_end,
                '_text_end': content_end,
            })

        return regions

    @staticmethod
    def _build_logprob_map(token_logprobs: List[Dict[str, Any]]) -> Dict[int, float]:
        return {lp['offset']: lp['logprob'] for lp in token_logprobs}

    @staticmethod
    def _classify_zone(mean_logprob: float, low_conf_ratio: float) -> str:
        th = _ZONE_THRESHOLDS
        if mean_logprob >= th['white_mean_logprob'] and low_conf_ratio < th['white_low_conf_ratio']:
            return 'white'
        if mean_logprob >= th['grey_mean_logprob'] and low_conf_ratio < th['grey_low_conf_ratio']:
            return 'grey'
        return 'black'

    @staticmethod
    def _fallback_heuristic(regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """无 logprobs 时的启发式 fallback。"""
        for region in regions:
            text = region.get('content', '')
            region.pop('_text_start', None)
            region.pop('_text_end', None)

            if not text or len(text.strip()) < 3:
                region['zone'] = 'black'
                region['confidence_score'] = 0.0
                region['metrics'] = {'mean_logprob': -999.0, 'min_logprob': -999.0, 'low_conf_ratio': 1.0}
                continue

            garbled = len(re.findall(r'[□◆◇■△▽○●]', text))
            total = max(len(text), 1)
            garble_ratio = garbled / total

            if garble_ratio > 0.3:
                region['zone'] = 'black'
                region['confidence_score'] = 0.1
            elif garble_ratio > 0.05 or len(text.strip()) < 10:
                region['zone'] = 'grey'
                region['confidence_score'] = 0.5
            else:
                region['zone'] = 'white'
                region['confidence_score'] = 0.9

            region['metrics'] = {
                'mean_logprob': 0.0, 'min_logprob': 0.0,
                'low_conf_ratio': garble_ratio,
            }
        return regions


# ═══════════════════════════════════════════════════════════════
# Phase 3.3 — D 层函数群
# ═══════════════════════════════════════════════════════════════

# ── D 层 OCR 阶段常量 ────────────────────────────────────────────────────────
# from continuous_image_service.py L92-93, L2031, L2144
_GREY_REPAIR_TIMEOUT = 8
_BLACK_DESCRIBE_TIMEOUT = 8
_MAX_GREY_REPAIRS_PER_UNIT = 5   # 单图最多修复的灰区数量
_MAX_BLACK_DESCRIBES_PER_UNIT = 5  # 单图最多描述的黑区数量

# D 层任务阶段标签（与 continuous_image_service.py 中值保持一致）
SECTION_OCR = 'OCR处理中'


# from continuous_image_service.py L207-225
def _try_load_pdf_cached_segments_for_image(username: str, filename: str) -> Tuple[str, str]:
    """查找旧分析目录中该文件对应的 OCR 缓存（兼容旧格式）。"""
    base = os.path.splitext(os.path.basename(filename))[0]
    dmt_root = _ci_dmt_root(username)
    if not os.path.isdir(dmt_root):
        return '', ''
    for analysis_dir in os.listdir(dmt_root):
        if analysis_dir in ('d_cache', 'index.json'):
            continue
        ocr_cache = os.path.join(dmt_root, analysis_dir, 'ocr_cache')
        for unit_dir in (os.listdir(ocr_cache) if os.path.isdir(ocr_cache) else []):
            unit_path = os.path.join(ocr_cache, unit_dir)
            raw_path = ''
            md_path = ''
            for fn in (os.listdir(unit_path) if os.path.isdir(unit_path) else []):
                if fn.lower().endswith('_raw.txt') and base.lower() in fn.lower():
                    raw_path = os.path.join(unit_path, fn)
                elif fn.lower().endswith('.md') and base.lower() in fn.lower():
                    md_path = os.path.join(unit_path, fn)
            if raw_path:
                return _read_text_if_exists(raw_path, ''), _read_text_if_exists(md_path, '')
    return '', ''


# from continuous_image_service.py L1983-1991
def _heuristic_low_confidence(text: str) -> bool:
    if not text or len(text.strip()) < 20:
        return True
    garbled_chars = re.findall(r'[□◆◇■△▽○●]+', text)
    if len(garbled_chars) > 3:
        return True
    if re.search(r'(无法识别|未识别|空结果|no\s*text|empty)', text, re.IGNORECASE):
        return True
    return False


# from continuous_image_service.py L2002-2024
def compute_unit_confidence(ocr_text: str, token_logprobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """结构化置信度评估：返回区域分类结果和汇总信息。兼容旧 low_confidence_hint 接口。"""
    regions = RegionConfidenceClassifier.classify(ocr_text, token_logprobs)

    white_count = sum(1 for r in regions if r['zone'] == 'white')
    grey_count = sum(1 for r in regions if r['zone'] == 'grey')
    black_count = sum(1 for r in regions if r['zone'] == 'black')

    zone_summary = {'white': white_count, 'grey': grey_count, 'black': black_count}

    if black_count > 0 and black_count >= len(regions) * 0.3:
        overall_zone = 'black'
    elif grey_count + black_count > len(regions) * 0.3:
        overall_zone = 'grey'
    else:
        overall_zone = 'white'

    return {
        'regions': regions,
        'zone_summary': zone_summary,
        'overall_zone': overall_zone,
        'low_confidence_hint': overall_zone != 'white',
    }


# from continuous_image_service.py L2034-2077
def _crop_region_image(asset_path: str, bbox: list, image_width: int = 0, image_height: int = 0,
                       bboxes: Optional[List[list]] = None) -> Optional[str]:
    """根据 bbox（归一化 0-999）从 asset 图片裁剪区域，返回 base64 字符串。"""
    if not asset_path or not os.path.exists(asset_path):
        return None
    try:
        img = Image.open(asset_path).convert('RGB')
        w, h = img.size
        boxes = bboxes or [bbox]
        xs1, ys1, xs2, ys2 = [], [], [], []
        for bx in boxes:
            if len(bx) < 4:
                continue
            xs1.append(int(bx[0] / 999 * w))
            ys1.append(int(bx[1] / 999 * h))
            xs2.append(int(bx[2] / 999 * w))
            ys2.append(int(bx[3] / 999 * h))
        if not xs1:
            return None

        # 多 bbox 合并为外接矩形
        x1 = min(xs1)
        y1 = min(ys1)
        x2 = max(xs2)
        y2 = max(ys2)
        # 校正
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        # 添加少量 padding
        pad = 10
        x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
        x2, y2 = min(w, x2 + pad), min(h, y2 + pad)
        cropped = img.crop((x1, y1, x2, y2))
        buf = io.BytesIO()
        cropped.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        print(f'[ci_d_repair] 裁剪区域失败: {e}')
        return None


# from continuous_image_service.py L2080-2137
def _repair_grey_regions(regions: List[Dict[str, Any]], asset_path: str) -> List[Dict[str, Any]]:
    """对灰区调用视觉 LLM 进行语义修复。就地修改 regions 列表。"""
    grey_regions = [(i, r) for i, r in enumerate(regions) if r['zone'] == 'grey']
    if not grey_regions:
        return regions

    # 收集白区文本作为上下文
    white_texts = [r['content'] for r in regions if r['zone'] == 'white' and r['content']]

    repaired_count = 0
    for idx, region in grey_regions:
        if repaired_count >= _MAX_GREY_REPAIRS_PER_UNIT:
            break

        crop_b64 = _crop_region_image(asset_path, region['bbox'], bboxes=region.get('bboxes'))
        if not crop_b64:
            continue

        # 组装上下文：前后相邻白区
        context_before = ''
        context_after = ''
        for j in range(idx - 1, -1, -1):
            if regions[j]['zone'] == 'white' and regions[j]['content']:
                context_before = regions[j]['content'][:200]
                break
        for j in range(idx + 1, len(regions)):
            if regions[j]['zone'] == 'white' and regions[j]['content']:
                context_after = regions[j]['content'][:200]
                break

        user_text = CI_D_GREY_REPAIR_USER_PROMPT_TEMPLATE.format(
            region_type=region['type'],
            ocr_text=region['content'][:500],
            context_before=context_before or '（无前文上下文）',
            context_after=context_after or '（无后文上下文）',
        )

        user_content = [
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{crop_b64}'}},
            {'type': 'text', 'text': user_text},
        ]

        try:
            raw_resp = _call_qwen_vl_flash_fast(
                CI_D_GREY_REPAIR_SYSTEM_PROMPT,
                user_content,
                timeout=_GREY_REPAIR_TIMEOUT,
            )
            if raw_resp:
                repair_data = _parse_llm_json(raw_resp, {})
                if repair_data.get('repaired_text'):
                    region['content_repaired'] = repair_data['repaired_text']
                    region['repair_method'] = 'llm_semantic'
                    repaired_count += 1
        except Exception as e:
            print(f'[ci_d_repair] 灰区修复失败 ({region["region_id"]}): {e}')

    return regions


# from continuous_image_service.py L2147-2188
def _describe_black_regions(regions: List[Dict[str, Any]], asset_path: str) -> List[Dict[str, Any]]:
    """对黑区调用视觉 LLM 生成视觉描述替代。就地修改 regions 列表。"""
    black_regions = [(i, r) for i, r in enumerate(regions) if r['zone'] == 'black']
    if not black_regions:
        return regions

    described_count = 0
    for idx, region in black_regions:
        if described_count >= _MAX_BLACK_DESCRIBES_PER_UNIT:
            break

        crop_b64 = _crop_region_image(asset_path, region['bbox'], bboxes=region.get('bboxes'))
        if not crop_b64:
            continue

        user_text = CI_D_BLACK_DESCRIBE_USER_PROMPT_TEMPLATE.format(
            region_type=region['type'],
        )

        user_content = [
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{crop_b64}'}},
            {'type': 'text', 'text': user_text},
        ]

        try:
            raw_resp = _call_qwen_vl_flash_fast(
                CI_D_BLACK_DESCRIBE_SYSTEM_PROMPT,
                user_content,
                timeout=_BLACK_DESCRIBE_TIMEOUT,
            )
            if raw_resp:
                desc_data = _parse_llm_json(raw_resp, {})
                description = desc_data.get('description', '')
                visual_type = desc_data.get('visual_type', 'unknown')
                if description:
                    region['content_repaired'] = f'[视觉描述|{visual_type}] {description}'
                    region['repair_method'] = 'visual_description'
                    described_count += 1
        except Exception as e:
            print(f'[ci_d_describe] 黑区描述失败 ({region["region_id"]}): {e}')

    return regions


# from continuous_image_service.py L2191-2211
def _build_enhanced_ocr_text(regions: List[Dict[str, Any]]) -> str:
    """将白区原文 + 灰区修复文 + 黑区视觉描述合并为增强 OCR 文本。"""
    parts = []
    for r in regions:
        if r['zone'] == 'white':
            if r['content']:
                parts.append(r['content'])
        elif r['zone'] == 'grey':
            text = r.get('content_repaired') or r['content']
            if r.get('content_repaired') and r['content_repaired'] != r['content']:
                parts.append(text)  # 灰区修复后直接使用修复文本
            else:
                if text:
                    parts.append(text)
        elif r['zone'] == 'black':
            desc = r.get('content_repaired', '')
            if desc:
                parts.append(f'【黑区视觉描述】{desc}')
            # 黑区无描述则跳过

    return '\n'.join(parts)


# from continuous_image_service.py L2214-2229
def _split_pdf_raw_by_pages(raw_text: str) -> List[str]:
    if not raw_text:
        return []
    separators = [
        r'\n\s*\[\s*page\s*\d+\s*\]\s*\n',
        r'\n\s*第\s*\d+\s*页\s*\n',
        r'\f',
        r'\n\s*-{3,}\s*\n',
    ]
    chunks = [raw_text]
    for pattern in separators:
        if len(chunks) == 1:
            parts = re.split(pattern, raw_text, flags=re.IGNORECASE)
            if len(parts) > 1:
                chunks = [p.strip() for p in parts if p.strip()]
    return chunks


# from continuous_image_service.py L2232-2239
def _try_load_pdf_cached_segments(username: str, source_file: str) -> List[str]:
    base = os.path.splitext(os.path.basename(source_file))[0]
    ocr_dir = os.path.join('.', 'received_dir', 'user_raw_file', username, f'{base}_ocr')
    raw_path = os.path.join(ocr_dir, f'{base}_raw.txt')
    if not os.path.exists(raw_path):
        return []
    raw_text = _read_text_if_exists(raw_path, '')
    return _split_pdf_raw_by_pages(raw_text)


# from continuous_image_service.py L2242-2261
def _try_load_unit_cached_ocr(unit_ocr_dir: str) -> Tuple[str, str]:
    """复用单元级 OCR 缓存（raw.txt + markdown），用于 D 层增量恢复。"""
    if not os.path.isdir(unit_ocr_dir):
        return '', ''

    raw_path = ''
    md_path = ''
    for fn in os.listdir(unit_ocr_dir):
        lower = fn.lower()
        abs_path = os.path.join(unit_ocr_dir, fn)
        if not os.path.isfile(abs_path):
            continue
        if lower.endswith('_raw.txt') and not raw_path:
            raw_path = abs_path
        elif lower.endswith('.md') and not md_path:
            md_path = abs_path

    ocr_text = _read_text_if_exists(raw_path, '') if raw_path else ''
    ocr_markdown = _read_text_if_exists(md_path, '') if md_path else ''
    return ocr_text, ocr_markdown


# from continuous_image_service.py L2264-2344
def build_d_layer(username: str, units: List[Dict[str, Any]], paths: Dict[str, str], task_id: str,
                  model_id: Optional[str] = None) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    total = len(units)
    _update_task(task_id, current_section=SECTION_OCR, total_items=total)

    pdf_segment_cache: Dict[str, List[str]] = {}

    for idx, unit in enumerate(units, start=1):
        _update_task(task_id, current_item=idx)
        source_file = unit['source_file']

        if unit['source_type'] == 'pdf' and source_file not in pdf_segment_cache:
            pdf_segment_cache[source_file] = _try_load_pdf_cached_segments(username, source_file)

        page_segments = pdf_segment_cache.get(source_file, []) if unit['source_type'] == 'pdf' else []
        ocr_text = ''
        ocr_markdown = ''
        reused = False
        ocr_result = None

        if page_segments and unit['page'] - 1 < len(page_segments):
            ocr_text = page_segments[unit['page'] - 1]
            ocr_markdown = ocr_text
            reused = True

        if not ocr_text.strip():
            unit_ocr_dir = os.path.join(paths['ocr_cache'], unit['unit_id'])
            os.makedirs(unit_ocr_dir, exist_ok=True)

            # 优先复用已存在的单元 OCR 缓存，避免重复调用远程 OCR
            cached_text, cached_md = _try_load_unit_cached_ocr(unit_ocr_dir)
            if cached_text.strip():
                ocr_text = cached_text
                ocr_markdown = cached_md or cached_text
                reused = True

        if not ocr_text.strip():
            unit_ocr_dir = os.path.join(paths['ocr_cache'], unit['unit_id'])
            os.makedirs(unit_ocr_dir, exist_ok=True)
            try:
                ocr_result = run_remote_ocr_asset(
                    file_path=unit['asset_abs_path'],
                    output_dir=unit_ocr_dir,
                    input_type='image',
                    model_id=model_id,
                )
            except Exception as ocr_exc:
                print(f'[ci] build_d_layer OCR异常 unit={unit["unit_id"]}: {ocr_exc}')
                ocr_result = {'success': False, 'error': str(ocr_exc)}
            if ocr_result.get('success'):
                ocr_text = ocr_result.get('raw_text', '')
                ocr_markdown = ocr_result.get('markdown', {}).get('markdown_content', '')

        low_confidence = _heuristic_low_confidence(ocr_text)

        items.append({
            'unit_id': unit['unit_id'],
            'seq': unit['seq'],
            'source_file': source_file,
            'page': unit['page'],
            'ocr_text': ocr_text,
            'ocr_markdown': ocr_markdown,
            'low_confidence_hint': low_confidence,
            'source_locator': {
                'source_file': source_file,
                'page': unit['page'],
                'seq': unit['seq'],
                'unit_id': unit['unit_id'],
            },
            'reused_cached_ocr': reused,
            'ocr_error': '' if (ocr_text.strip() or reused or (ocr_result and ocr_result.get('success'))) else (ocr_result or {}).get('error', ''),
        })

    d_layer = {
        'layer': 'D',
        'total_units': len(items),
        'items': items,
    }
    _safe_json_dump(paths['d_layer'], d_layer)
    return d_layer
