import base64
import copy
import io
import json
import os
import re
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from app_chat.ci._utils import _normalize_rel, _now_iso, _safe_bool, _safe_json_dump, _safe_json_load, _truncate_text
from app_chat.ci.r_layer import _ensure_r_layer_items, _is_reproduction_iterating, _normalize_reproduction_iter_context
from app_chat.views_card_image import (
    GEMINI_IMAGE_API_KEY_HIGH,
    GEMINI_IMAGE_API_KEY_SINGLE,
    GEMINI_IMAGE_BASE_URL,
    GEMINI_IMAGE_TIMEOUT,
    _encode_overlay_png_capped_bytes,
    _extract_base64_from_response,
    _extract_nonwhite_bbox_norm,
    _gemini_native_generate_image_from_parts,
    _load_overlay_style_reference_base64,
    _detect_overlay_red_boxes_for_pil,
    _overlay_dark_neutral_pixel_ratio_rgba,
    _bleach_dark_neutral_pixels_on_overlay,
    _bleach_overlay_ink_residual_pipeline,
    _iterate_overlay_test_layer_image,
    _card_image_dir,
    _pil_from_response_base64,
    _resample_lanczos,
)


CI_DMT_GEMINI_BASE_URL = os.environ.get('NKCN_DMT_GEMINI_BASE_URL', 'https://www.dmxapi.cn/v1')
CI_DMT_GEMINI_API_KEY = os.environ.get(
    'NKCN_DMT_GEMINI_API_KEY',
    os.environ.get("DMX_API_KEY", ""),
)
CI_DMT_GEMINI_MODEL_DEFAULT = 'gemini-3.1-pro-preview'
CI_DMT_GEMINI_TIMEOUT = 300
CI_DMT_GEMINI_MAX_RETRIES = 3
# D 清单一长就容易占满默认 8k，导致截断在「【M级·蓝框】」之前；可用环境变量调高
CI_DMT_MAX_OUTPUT_TOKENS = int(os.environ.get('NKCN_CI_DMT_MAX_OUTPUT_TOKENS', '16384'))

# _ensure_overlay_layer 会按 manifest 重建 items；以下字段必须由旧条目合并保留，否则 DMT 写入的占比/粗粒度或轻量识字摘要会被下次对齐覆盖。
_OVERLAY_ITEM_MERGED_STATE_KEYS = (
    'ci_sketch_handwriting_area_ratio',
    'ci_dmt_coarse_layout',
    'ci_sketch_handwriting_estimate_note',
    'lite_auto_iteration_last',
)


def _ci_overlay_timing_log(step: str, started_at: float, extra: str = '') -> float:
    elapsed = time.perf_counter() - started_at
    suffix = f' | {extra}' if extra else ''
    print(f'[CI overlay save] {step}: {elapsed:.3f}s{suffix}', flush=True)
    return time.perf_counter()


def _merge_overlay_item_preserved_state(current: Dict[str, Any], target: Dict[str, Any]) -> None:
    """把不参与几何重建、但需要持久化的扩展状态写回 target。"""
    for key in _OVERLAY_ITEM_MERGED_STATE_KEYS:
        if key in current:
            target[key] = copy.deepcopy(current[key])


# 与原草图手写占比检测（Qwen3.6-plus，整图一张）
_CI_SKETCH_QWEN_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
_CI_SKETCH_QWEN_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
_CI_SKETCH_QWEN_MODEL_DEFAULT = 'qwen3.6-plus'


def _overlay_dmt_gemini_model() -> str:
    env = os.environ.get('NKCN_DMT_GEMINI_MODEL', '').strip()
    if env:
        return env
    from app_chat.scene_models import get_scene_value
    return get_scene_value('ci_overlay_dmt_gemini', CI_DMT_GEMINI_MODEL_DEFAULT)


def _overlay_sketch_qwen_model() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('ci_overlay_sketch_qwen', _CI_SKETCH_QWEN_MODEL_DEFAULT)


def _overlay_gemini_image_model() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('card_image_gemini', 'gemini-3.1-flash-image-preview-X')

CI_DMT_OVERLAY_SYSTEM = (
    '你是专业手稿/示意图版面分析助手。用户会给你一张图（当前单图复现图）和当前单图理解补充文本（文本可能有误，以图像为准）。'
    '你必须只输出一段可直接复制给「文生图/生图AI」的完整中文指令正文，不要 Markdown 代码块、不要前言后语、不要解释。'
    '输出从「原图是一张手稿图」或「原图是一张手稿/示意图」起笔，直至用户要求的结尾句为止，结构完整。'
    '对【M级·蓝框】和【T级·紫框】的每一条：除包含哪些图中元素外，必须写清版面相对位置；若相对位置实在不好描述，则写准绝对坐标范围。'
    '所有 D/M/T 都只描述闭合框线本身，不生成任何标签、序号、角标或定位色块；M/T 框应优先描述为闭合、连续、清晰可辨的完整包裹框。'
)

CI_DMT_OVERLAY_USER_PREFIX = """原图是一张手稿图，图中应该标注多个红、蓝、紫色框，具体如下：

【颜色规则】D=红框(#E53935,1.5px) M=蓝框(#1E88E5,1.5px) T=紫框(#8E24AA,1.5px)；整张图只保留红框/蓝框/紫框三类闭合框线，不生成任何 D/M/T 标签、序号、角标、字母块或纯色定位块。嵌套关系：T⊃M⊃D。

【D级·红框】最小颗粒，每个独立格子各一框，每个词/短语/对象作为一个D框（宁可偏细勿粗）：
- D1：......
- D2：......
......

【M级·蓝框】中等颗粒，按版本/功能区块合并：
- M1：......
- M2：......
......

【T级·紫框】最大颗粒，全局架构：
- T0：全图整体
- T1：......
......

我需要将上述所有的红蓝紫色框生成出来，底图内容（所有文字、线条、颜色等）全部清除不要；你生成出的图里应该只有红蓝紫三类闭合框线，不要保留原图黑字正文、底色，也不要额外生成任何标签、序号、字母、角标或色块。

风格严格按照参考图，仅参考红框/蓝框/紫框的线条样式与层级组织方式，不参考任何标签样式。

---

你最终输出必须严格采用上面的整体结构与措辞（对于【D级·红框】、【M级·蓝框】和【T级·紫框】中的「......」，请你主要根据原图（补充文本很可能有不少错误，不要太相信文本，以原图为准）理解并填写完善，可调整条目数量，但层级与颜色规则说明保持一致），输出可直接粘贴给其他生图AI的最终版本。务必注意：
1) 开头、【颜色规则】与结尾两段保持和上述格式、内容完全一致；
2) 【D级·红框】展开为具体 D 清单时，逐条列出全部的 D1、D2、D3...，不可省略任何一处，每条写明位置特征，禁止尝试描述手写文字具体是什么，只可描述相对或绝对位置；一般一处连续字迹作为一个D，若数量过多可适度合并同类项，但仍需给出可执行的最小颗粒框分配方案。
3) 【M级·蓝框】和【T级·紫框】每一条「......」展开时必须同时满足（表述须简洁、精炼、准确，切忌冗长）：(a)该层级框所覆盖的内容/元素要点；(b)该框在图中的相对位置或显著特征（如左上/右下/跨中部/被竖向长条手绘圈包住/左侧边缘是一条手绘曲线...等），若实在难以描述则给出准确的归一化坐标范围（以整图宽 W、高 H 为参照，例如「约 x/W∈[0.05,0.40]，y/H∈[0.10,0.38]」或等价描述），便于生图模型定位；(c)该框需要保持闭合、连续、清晰可辨，优先使用规整直线边界完成完整包裹；(d)不要写“包含Dxx-Dxx”。
4) M 版面的划分粒度应该是中等（Middle），既不宜过大也不宜过小；像人一样读图：优先关注图中的圈画、箭头等标注。原图中的手绘长横线、长竖线、长斜线或曲线只可作为分区参考，不要直接把断裂手绘线当作蓝框或紫框边界；相应 M/T 框仍应是闭合、连续的完整框线。关系密切且未被明确分区隔开的元素/文字应在同一 M 内。
5) M 与 T 的条目数量需保持“适中且稳定”：避免明显过多碎裂或过少粗并；在保证覆盖完整前提下，优先让同层条目数落在可读的中等范围，并与图中结构复杂度匹配。

下面第一张图即待分析的原图。随后会给你与此图相关的标题与补充文本（置信度不高，仅供参考，必须以原图为准），请综合理解，完成上述输出。
"""

# 手写占比低于 60% 时使用：D/M/T 结构与原版一致，但 D 红框刻意偏粗；仍需全覆盖、无遗漏。
CI_DMT_OVERLAY_USER_PREFIX_COARSE = """原图是一张手稿图，图中应该标注多个红、蓝、紫色框，具体如下：

【颜色规则】D=红框(#E53935,1.5px) M=蓝框(#1E88E5,1.5px) T=紫框(#8E24AA,1.5px)；整张图只保留红框/蓝框/紫框三类闭合框线，不生成任何 D/M/T 标签、序号、角标、字母块或纯色定位块。嵌套关系：T⊃M⊃D。

【D级·红框】粗粒度优先（本页印刷体或留白较多，手写占比偏低）：每个相对独立的手写簇或印刷内容块，尽量用 1～2 个红框覆盖即可；同一行/同一段连续手写若关系密切，可合并为单个 D 框；印刷体标题、正文区也可合并成较少的大块红框，但必须保证整张图所有可见正文与手写区域都被红框覆盖到，禁止遗漏。
- D1：......
- D2：......
......

【M级·蓝框】中等颗粒，按版本/功能区块合并：
- M1：......
- M2：......
......

【T级·紫框】最大颗粒，全局架构：
- T0：全图整体
- T1：......
......

我需要将上述所有的红蓝紫色框生成出来，底图内容（所有文字、线条、颜色等）全部清除不要；你生成出的图里应该只有红蓝紫三类闭合框线，不要保留原图黑字正文、底色，也不要额外生成任何标签、序号、字母、角标或色块。

风格严格按照参考图，仅参考红框/蓝框/紫框的线条样式与层级组织方式，不参考任何标签样式。

---

你最终输出必须严格采用上面的整体结构与措辞（对于【D级·红框】、【M级·蓝框】和【T级·紫框】中的「......」，请你主要根据原图（补充文本很可能有不少错误，不要太相信文本，以原图为准）理解并填写完善，可调整条目数量，但层级与颜色规则说明保持一致），输出可直接粘贴给其他生图AI的最终版本。务必注意：
1) 开头、【颜色规则】与结尾两段保持和上述格式、内容完全一致；
2) 【D级·红框】展开为具体 D 清单时，逐条列出全部的 D1、D2、D3...，不可省略任何一处，每条写明位置特征，禁止尝试描述手写文字具体是什么，只可描述相对或绝对位置；粗粒度下条目数应明显少于“最小颗粒”方案，但仍须覆盖全图。
3) 【M级·蓝框】和【T级·紫框】每一条「......」展开时必须同时满足（表述须简洁、精炼、准确，切忌冗长）：(a)该层级框所覆盖的内容/元素要点；(b)该框在图中的相对位置或显著特征；(c)该框需要保持闭合、连续、清晰可辨；(d)不要写“包含Dxx-Dxx”。
4) M 版面的划分粒度应该是中等（Middle）；原图中的手绘长横线、长竖线、长斜线或曲线只可作为分区参考，不要直接把断裂手绘线当作蓝框或紫框边界。
5) M 与 T 的条目数量需保持适中：避免过多碎裂或过少粗并；在保证覆盖完整前提下优先可读。

下面第一张图即待分析的原图。随后会给你与此图相关的标题与补充文本（置信度不高，仅供参考，必须以原图为准），请综合理解，完成上述输出。
"""

_DMT_REQUIRED_PREFIX = (
    "原图是一张手稿图，图中应该标注多个红、蓝、紫色框，具体如下：\n\n"
    "【颜色规则】D=红框(#E53935,1.5px) M=蓝框(#1E88E5,1.5px) T=紫框(#8E24AA,1.5px)；整张图只保留红框/蓝框/紫框三类闭合框线，不生成任何 D/M/T 标签、序号、角标、字母块或纯色定位块。嵌套关系：T⊃M⊃D。"
)
_DMT_REQUIRED_SUFFIX = (
    "我需要将上述所有的红蓝紫色框生成出来，底图内容（所有文字、线条、颜色等）全部清除不要；你生成出的图里应该只有红蓝紫三类闭合框线，不要保留原图黑字正文、底色，也不要额外生成任何标签、序号、字母、角标或色块。\n\n"
    "风格严格按照参考图，仅参考红框/蓝框/紫框的线条样式与层级组织方式，不参考任何标签样式。"
)

# DMT 初稿（第一遍流式）最多尝试次数：首Call + 3 次重试（模型偶发在中途截断，缺 M/T 段时第二遍无法补全）
_DMT_FIRST_PASS_MAX_ATTEMPTS = int(os.environ.get('NKCN_CI_DMT_FIRST_PASS_MAX_ATTEMPTS', '4'))


def _ensure_dmt_fixed_suffix(text: str) -> str:
    """若已有完整 D/M/T 结构但缺少末尾两段固定话术，用代码补上（与 refine 内逻辑一致）。"""
    s = str(text or '').rstrip()
    if not s:
        return s
    if _DMT_REQUIRED_SUFFIX in s:
        return s
    if '【M级·蓝框】' not in s or '【T级·紫框】' not in s:
        return s
    return f'{s}\n\n{_DMT_REQUIRED_SUFFIX}'


def _dmt_instruction_structure_complete(text: str) -> bool:
    """
    判断第一遍 Gemini 输出是否具备完整 DMT 骨架（供第二遍仅 D 段复核使用）。
    要求：按顺序出现 D/M/T 三段标题，且各段至少有一条「- Dx： / - Mx： / - Tx：」条目。
    """
    s = str(text or '').strip()
    if len(s) < 200:
        return False
    h_d, h_m, h_t = '【D级·红框】', '【M级·蓝框】', '【T级·紫框】'
    if h_d not in s or h_m not in s or h_t not in s:
        return False
    i_d, i_m, i_t = s.find(h_d), s.find(h_m), s.find(h_t)
    if not (0 <= i_d < i_m < i_t):
        return False
    d_seg = s[i_d + len(h_d):i_m]
    m_seg = s[i_m + len(h_m):i_t]
    t_seg = s[i_t + len(h_t):]
    if not re.search(r'(?mi)^\s*-\s*D\d+\s*[：:]', d_seg):
        return False
    if not re.search(r'(?mi)^\s*-\s*M\d+\s*[：:]', m_seg):
        return False
    if not re.search(r'(?mi)^\s*-\s*T\d+\s*[：:]', t_seg):
        return False
    return True


def _collect_ci_dmt_overlay_first_pass(
    image_data_url: str,
    card_title: str,
    card_content: str,
    user_prefix: Optional[str],
) -> str:
    chunks: List[str] = []
    for chunk in _ci_dmt_overlay_stream_generator(image_data_url, card_title, card_content, user_prefix=user_prefix):
        try:
            text = chunk.decode('utf-8', errors='ignore')
        except Exception:
            text = ''
        if text:
            chunks.append(text)
    return ''.join(chunks).strip()


_ci_overlay_jobs_lock = threading.Lock()
_ci_overlay_jobs: Dict[str, Dict[str, Any]] = {}
_ci_overlay_busy: Dict[str, set] = {}


def _ci_dmt_overlay_parse_image_data_url(image_data_url: str):
    url = str(image_data_url or '').strip()
    if not url:
        return None, None
    b64 = url
    mime = 'image/png'
    if url.startswith('data:') and 'base64,' in url:
        head, b64 = url.split('base64,', 1)
        try:
            mime = head.split(':', 1)[1].split(';')[0].strip() or mime
        except Exception:
            pass
    b64 = ''.join(c for c in b64 if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
    if not b64:
        return None, None
    return mime, b64


def _ci_dmt_gemini_client():
    return OpenAI(
        api_key=CI_DMT_GEMINI_API_KEY,
        base_url=CI_DMT_GEMINI_BASE_URL.rstrip('/') + '/',
        default_headers={'x-foo': 'true'},
        timeout=CI_DMT_GEMINI_TIMEOUT,
    )


def _ci_sketch_qwen_client():
    return OpenAI(
        api_key=_CI_SKETCH_QWEN_KEY,
        base_url=_CI_SKETCH_QWEN_BASE.rstrip('/') + '/',
        timeout=120,
    )


def _estimate_sketch_handwriting_area_ratio_qwen(sketch_abs: str) -> Tuple[float, str]:
    """返回手写区域占整图面积的估计比例 0~1，以及模型原始说明片段。"""
    try:
        with open(sketch_abs, 'rb') as handle:
            b64 = base64.b64encode(handle.read()).decode('utf-8')
    except Exception as exc:
        return 0.65, f'read_sketch_failed:{exc}'
    prompt = (
        '你是手稿图像版面分析助手。输入是一张完整页面图像。\n'
        '请估计图中「手写笔迹（含手写汉字、字母数字、手绘符号笔迹）」所占整张图面积的大致百分比。\n'
        '印刷体正文、表格印刷字、纯留白、几何图形轮廓（非手写笔迹）不计入手写区域。\n'
        '若手写与印刷重叠，按手写笔画可视覆盖估算。\n'
        '只输出一行合法 JSON，不要其它文字：'
        '{"handwriting_area_percent":<0到100的整数>,"note":"<一句中文说明>"}\n'
    )
    content = [
        {'type': 'text', 'text': prompt},
        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
    ]
    raw_note = ''
    for attempt in range(1, 4):
        try:
            client = _ci_sketch_qwen_client()
            rsp = client.chat.completions.create(
                model=_overlay_sketch_qwen_model(),
                messages=[{'role': 'user', 'content': content}],
                temperature=0,
                max_tokens=256,
                extra_body={'enable_thinking': False},
            )
            text = str(rsp.choices[0].message.content or '').strip()
            raw_note = text[:800]
            obj = None
            try:
                obj = json.loads(text)
            except Exception:
                m = re.search(r'\{[^{}]*\}', text)
                if m:
                    obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                pct = obj.get('handwriting_area_percent')
                try:
                    v = float(pct)
                except Exception:
                    v = -1.0
                if 0 <= v <= 1:
                    return float(v), raw_note
                if 1 < v <= 100:
                    return v / 100.0, raw_note
            break
        except Exception as exc:
            raw_note = str(exc)
            time.sleep(0.6 * attempt)
    return 0.65, raw_note or 'estimate_failed_default_fine'


def _ci_dmt_overlay_stream_generator(
    image_data_url: str,
    card_title: str,
    card_content: str,
    user_prefix: Optional[str] = None,
):
    parsed = _ci_dmt_overlay_parse_image_data_url(image_data_url)
    if not parsed or not parsed[1]:
        return
    mime, b64 = parsed

    tail_text = (
        '【标题】\n'
        + (card_title or '').strip()
        + '\n\n【补充文本】\n'
        + (card_content or '').strip()
    )

    prefix_text = (user_prefix or CI_DMT_OVERLAY_USER_PREFIX).strip()
    content_parts = [
        {'type': 'text', 'text': prefix_text},
        {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}},
        {'type': 'text', 'text': tail_text},
    ]

    max_attempts = 1 + int(max(0, CI_DMT_GEMINI_MAX_RETRIES))
    for attempt in range(1, max_attempts + 1):
        try:
            client = _ci_dmt_gemini_client()
            stream = client.chat.completions.create(
                model=_overlay_dmt_gemini_model(),
                messages=[
                    {'role': 'system', 'content': CI_DMT_OVERLAY_SYSTEM},
                    {'role': 'user', 'content': content_parts},
                ],
                stream=True,
                max_tokens=CI_DMT_MAX_OUTPUT_TOKENS,
                temperature=0.3,
            )
            for chunk in stream:
                try:
                    choice = chunk.choices[0]
                    delta = getattr(choice, 'delta', None)
                    if delta is None:
                        continue
                    piece = getattr(delta, 'content', None) or ''
                    if piece:
                        yield piece.encode('utf-8')
                except (IndexError, AttributeError, TypeError):
                    continue
            return
        except Exception as ex:
            print(f'[ci_overlay] DMT 覆盖层说明流式失败 try={attempt}/{max_attempts}: {ex}')
            if attempt >= max_attempts:
                return
            time.sleep(1.2 * attempt)


def _ci_dmt_refine_d_coverage(
    image_data_url: str,
    draft_instruction: str,
    card_title: str,
    card_content: str,
    coarse_layout: bool = False,
) -> str:
    """
    二次校验 D 清单是否遗漏手写字迹位置（仅复核 D 段）：
    - 若缺失固定前缀/尾部段，先补齐
    - 仅把【D级·红框】段发给模型复核，输出也只接收 D 段
    - 若复核后 D 条目数减少：重试一次；若仍减少，回退到复核前
    - 仅当 D 条目数增加时，替换回完整正文；否则保留原文
    """
    parsed = _ci_dmt_overlay_parse_image_data_url(image_data_url)
    if not parsed or not parsed[1]:
        return str(draft_instruction or '').strip()
    mime, b64 = parsed
    draft = str(draft_instruction or '').strip()
    if not draft:
        return draft
    if _DMT_REQUIRED_PREFIX not in draft:
        if '【D级·红框】' in draft:
            draft = draft.replace('【D级·红框】', f'{_DMT_REQUIRED_PREFIX}\n\n【D级·红框】', 1)
        else:
            draft = f'{_DMT_REQUIRED_PREFIX}\n\n{draft}'
    # 结尾「我需要将上述…」「风格严格按照参考图…」必须落在 M/T 段之后；若在尚无蓝框/紫框段落时插入，
    # 会插在 D 清单末尾，挤占模型后续输出位置，表现为正文只剩 D 段+结尾，不见【M级】【T级】。
    if _DMT_REQUIRED_SUFFIX not in draft and '【M级·蓝框】' in draft and '【T级·紫框】' in draft:
        draft = f'{draft.rstrip()}\n\n{_DMT_REQUIRED_SUFFIX}'

    def _count_d_items(text: str) -> int:
        return len(re.findall(r'(?mi)^\s*-\s*D\d+\s*[：:]', str(text or '')))

    def _extract_section(source: str, header: str, next_headers: List[str]) -> str:
        s = str(source or '')
        start = s.find(header)
        if start < 0:
            return ''
        end = len(s)
        for h in next_headers:
            p = s.find(h, start + len(header))
            if p >= 0:
                end = min(end, p)
        return s[start:end].strip()

    def _replace_section(source: str, header: str, next_headers: List[str], new_section: str) -> str:
        s = str(source or '')
        start = s.find(header)
        if start < 0:
            return s
        end = len(s)
        for h in next_headers:
            p = s.find(h, start + len(header))
            if p >= 0:
                end = min(end, p)
        return (s[:start].rstrip() + '\n\n' + str(new_section or '').strip() + '\n\n' + s[end:].lstrip()).strip()

    d_before = _extract_section(draft, '【D级·红框】', ['【M级·蓝框】', '【T级·紫框】'])
    if not d_before:
        return draft
    before_count = _count_d_items(d_before)

    tail_text = "【标题】\n" + (card_title or '').strip() + "\n\n【补充文本】\n" + (card_content or '').strip()
    coarse_hint = ''
    if coarse_layout:
        coarse_hint = (
            "【粗粒度模式】本页估计手写占比较低：优先用较少 D 红框覆盖同一手写簇/印刷块（每簇 1～2 框）；"
            "仅在仍有明显遗漏时增补条目；禁止为了“细碎”而过度拆分。\n"
        )
    prompt = (
        "你只做 D 清单补漏复核。必须以图像手写字迹位置为准。\n"
        f"{coarse_hint}"
        "要求：\n"
        "1) 只输出【D级·红框】这一段，不要输出 M/T，也不要输出前后其它段落；\n"
        "2) 只要存在手写字迹位置，就应有对应 D 项；\n"
        "3) 可补充/拆分 D 项，但不要减少已合理覆盖的 D 项；\n"
        "4) 每条保持“- Dxx：...”格式，可直接替换原 D 段。\n\n"
        "【当前D段草案】\n"
        f"{d_before[:12000]}"
    )
    content = [{'type': 'text', 'text': prompt}, {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}}, {'type': 'text', 'text': tail_text}]

    def _run_once() -> str:
        client = _ci_dmt_gemini_client()
        rsp = client.chat.completions.create(
            model=_overlay_dmt_gemini_model(),
            messages=[
                {'role': 'system', 'content': '你是 D 清单补漏审校助手，只输出【D级·红框】段。'},
                {'role': 'user', 'content': content},
            ],
            temperature=0.2,
            max_tokens=8192,
        )
        text = str(rsp.choices[0].message.content or '').strip()
        sec = _extract_section(text, '【D级·红框】', ['【M级·蓝框】', '【T级·紫框】'])
        return (sec or text).strip()

    max_attempts = 1 + int(max(0, CI_DMT_GEMINI_MAX_RETRIES))
    last = d_before
    candidate = ''
    for attempt in range(1, max_attempts + 1):
        try:
            candidate = _run_once()
            if candidate:
                last = candidate
                # 少于复核前数量：允许再重试一次；连续仍少则回退
                if _count_d_items(candidate) < before_count:
                    if attempt < 2 and attempt < max_attempts:
                        time.sleep(0.8 * attempt)
                        continue
                    return draft
                break
        except Exception:
            pass
        if attempt < max_attempts:
            time.sleep(1.0 * attempt)

    if not candidate:
        return draft
    after_count = _count_d_items(candidate)
    if after_count > before_count:
        return _replace_section(draft, '【D级·红框】', ['【M级·蓝框】', '【T级·紫框】'], candidate)
    return draft


def _safe_overlay_debug_segment(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return 'item'
    cleaned = ''.join(ch if (ch.isalnum() or ch in ('-', '_')) else '_' for ch in text)
    cleaned = cleaned.strip('._')
    return (cleaned or 'item')[:120]


def _overlay_debug_stamp() -> str:
    return (_now_iso() or '').replace('-', '').replace(':', '').replace('.', '_')


def _overlay_debug_root(paths: Dict[str, str], create: bool = False) -> str:
    path = os.path.join(paths['root'], 'overlay_debug')
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _overlay_debug_dir(paths: Dict[str, str], unit_id: str, create: bool = False) -> str:
    path = os.path.join(_overlay_debug_root(paths, create=create), _safe_overlay_debug_segment(unit_id))
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def _clear_overlay_debug_dir(paths: Dict[str, str], unit_id: str) -> None:
    try:
        path = _overlay_debug_dir(paths, unit_id, create=False)
        if os.path.isdir(path):
            import shutil

            shutil.rmtree(path, ignore_errors=True)
        root = _overlay_debug_root(paths, create=False)
        if os.path.isdir(root) and not os.listdir(root):
            os.rmdir(root)
    except Exception:
        pass


def _write_overlay_debug_text(paths: Dict[str, str], unit_id: str, stem: str, text: str) -> Dict[str, str]:
    return {}


def _write_overlay_debug_image(paths: Dict[str, str], unit_id: str, stem: str, image) -> Dict[str, str]:
    return {}


def _copy_overlay_debug_file(paths: Dict[str, str], unit_id: str, stem: str, src_path: str) -> Dict[str, str]:
    return {}


def _overlay_pil_to_base64_png(image) -> str:
    buf = io.BytesIO()
    image.convert('RGBA').save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')


def _ci_overlay_helper_cid(analysis_id: str, unit_id: str) -> str:
    return f"ci_{_safe_overlay_debug_segment(analysis_id)}_{_safe_overlay_debug_segment(unit_id)}"


def _set_ci_overlay_progress(username: str, analysis_id: str, unit_id: str, step: int, total: int, message: str) -> None:
    payload = get_ci_overlay_job(username, analysis_id, unit_id) or {}
    payload.update({
        'status': 'running',
        'msg': 'running',
        'progress_step': int(step),
        'progress_total': int(total),
        'progress_msg': str(message or ''),
    })
    _set_ci_overlay_job(username, analysis_id, unit_id, payload)


_OVERLAY_REGION_LEVEL_SPECS = {
    'd': {'label': 'D', 'color': (229, 57, 53), 'tolerance': 230, 'min_width': 18, 'min_height': 18, 'min_pixels': 28},
    'm': {'label': 'M', 'color': (30, 136, 229), 'tolerance': 230, 'min_width': 20, 'min_height': 20, 'min_pixels': 32},
    't': {'label': 'T', 'color': (142, 36, 170), 'tolerance': 240, 'min_width': 24, 'min_height': 24, 'min_pixels': 36},
}
_OVERLAY_REGION_PARSE_MAX_DIM = 1440
_OVERLAY_REGION_DRAW_ORDER = {'t': 0, 'm': 1, 'd': 2}
_OVERLAY_LEVELS = ('d', 'm', 't')
_OVERLAY_LAYER_COMPOSITE_ORDER = ('t', 'm', 'd')
_OVERLAY_LABEL_FONT_CANDIDATES = [
    os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'arialbd.ttf'),
    os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'arial.ttf'),
    'arialbd.ttf',
    'arial.ttf',
    'DejaVuSans-Bold.ttf',
    'DejaVuSans.ttf',
]


def _overlay_file_version(path: str) -> str:
    if not path or not os.path.exists(path):
        return ''
    try:
        return str(int(os.path.getmtime(path) * 1000))
    except Exception:
        return ''


def _clip_region_ratio(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _build_region_bbox_norm(x: int, y: int, w: int, h: int, width: int, height: int) -> Dict[str, float]:
    if width <= 0 or height <= 0:
        return {'x': 0.0, 'y': 0.0, 'w': 0.0, 'h': 0.0}
    left = _clip_region_ratio(x / width)
    top = _clip_region_ratio(y / height)
    right = _clip_region_ratio((x + w) / width)
    bottom = _clip_region_ratio((y + h) / height)
    return {
        'x': round(left, 6),
        'y': round(top, 6),
        'w': round(max(0.0, right - left), 6),
        'h': round(max(0.0, bottom - top), 6),
    }


def _normalize_manual_regions_payload(raw_regions: Any, image_width: int, image_height: int) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(raw_regions, list) or image_width <= 0 or image_height <= 0:
        return None
    normalized: List[Dict[str, Any]] = []
    for item in raw_regions:
        if not isinstance(item, dict):
            continue
        level = _normalize_overlay_level(item.get('level'))
        if not level:
            continue
        bbox = item.get('bbox')
        if isinstance(bbox, dict):
            parsed_bbox = {
                'x': round(_clip_region_ratio(bbox.get('x', 0)), 6),
                'y': round(_clip_region_ratio(bbox.get('y', 0)), 6),
                'w': round(_clip_region_ratio(bbox.get('w', 0)), 6),
                'h': round(_clip_region_ratio(bbox.get('h', 0)), 6),
            }
        else:
            try:
                parsed_bbox = _build_region_bbox_norm(
                    int(item.get('x', 0)),
                    int(item.get('y', 0)),
                    int(item.get('w', 0)),
                    int(item.get('h', 0)),
                    image_width,
                    image_height,
                )
            except (TypeError, ValueError):
                continue
        if parsed_bbox['w'] <= 0 or parsed_bbox['h'] <= 0:
            continue
        region_id = str(item.get('region_id') or '').strip()
        if not region_id:
            region_id = f'manual_{level}_{len(normalized) + 1}'
        normalized.append({
            'region_id': region_id,
            'level': level,
            'title': str(item.get('title') or region_id),
            'bbox': parsed_bbox,
            'rank': int(item.get('rank') or (len(normalized) + 1)),
            'source': str(item.get('source') or 'manual_edit'),
        })
    return _sort_overlay_regions(normalized) if normalized else None


def _bbox_from_overlay_regions(regions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    valid = [
        region for region in (regions or [])
        if isinstance(region, dict) and isinstance(region.get('bbox'), dict)
    ]
    if not valid:
        return None
    left = min(_clip_region_ratio(region['bbox'].get('x', 0)) for region in valid)
    top = min(_clip_region_ratio(region['bbox'].get('y', 0)) for region in valid)
    right = max(
        _clip_region_ratio(region['bbox'].get('x', 0)) + _clip_region_ratio(region['bbox'].get('w', 0))
        for region in valid
    )
    bottom = max(
        _clip_region_ratio(region['bbox'].get('y', 0)) + _clip_region_ratio(region['bbox'].get('h', 0))
        for region in valid
    )
    return {
        'x': round(left, 6),
        'y': round(top, 6),
        'w': round(max(0.0, right - left), 6),
        'h': round(max(0.0, bottom - top), 6),
    }


def _build_manual_save_layer_images(image_size: Tuple[int, int], regions: List[Dict[str, Any]]) -> Dict[str, Any]:
    layer_images: Dict[str, Any] = {}
    for level in _OVERLAY_LEVELS:
        level_regions = [
            region for region in regions
            if _normalize_overlay_level(region.get('level')) == level
        ]
        if level_regions:
            layer_images[level] = _render_overlay_from_regions(image_size, level_regions)
        else:
            layer_images[level] = _create_blank_overlay_image(image_size)
    return layer_images


def _normalize_overlay_level(level: Any) -> str:
    normalized = str(level or '').strip().lower()
    return normalized if normalized in _OVERLAY_LEVELS else ''


def _overlay_default_bbox() -> Dict[str, float]:
    return {'x': 0.2, 'y': 0.2, 'w': 0.6, 'h': 0.6}


def _sort_overlay_regions(regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        list(regions or []),
        key=lambda item: (
            _OVERLAY_REGION_DRAW_ORDER.get(_normalize_overlay_level(item.get('level')), 99),
            int(item.get('rank') or 0),
            str(item.get('region_id') or ''),
        ),
    )


def _create_blank_overlay_image(size: Tuple[int, int]):
    from PIL import Image

    width = max(1, int((size or (1, 1))[0] or 1))
    height = max(1, int((size or (1, 1))[1] or 1))
    return Image.new('RGBA', (width, height), (255, 255, 255, 255))


def _should_match_overlay_level(level: str, r: int, g: int, b: int, a: int) -> bool:
    if a < 24:
        return False
    if r >= 245 and g >= 245 and b >= 245:
        return False
    target = _OVERLAY_REGION_LEVEL_SPECS[level]['color']
    distance = abs(r - target[0]) + abs(g - target[1]) + abs(b - target[2])
    if distance > _OVERLAY_REGION_LEVEL_SPECS[level]['tolerance']:
        return False
    if level == 'd':
        return r >= g + 28 and r >= b + 24
    if level == 'm':
        return b >= r + 32 and b >= g + 18
    return r >= g + 12 and b >= g + 12


def _detect_overlay_cleanup_level(r: int, g: int, b: int, a: int) -> str:
    if a < 16:
        return ''
    if r >= 242 and g >= 242 and b >= 242:
        return ''

    best_level = ''
    best_distance = None
    for level in ('d', 'm', 't'):
        target = _OVERLAY_REGION_LEVEL_SPECS[level]['color']
        distance = abs(r - target[0]) + abs(g - target[1]) + abs(b - target[2])
        if level == 'd':
            if r < 116 or r < g + 14 or r < b + 12 or distance > 300:
                continue
        elif level == 'm':
            if b < 116 or b < r + 14 or b < g + 8 or distance > 300:
                continue
        else:
            if max(r, b) < 108 or r < g + 6 or b < g + 6 or distance > 320:
                continue
        if best_distance is None or distance < best_distance:
            best_level = level
            best_distance = distance
    return best_level


def _normalize_overlay_palette(image):
    work = image.convert('RGBA')
    normalized = work.copy()
    pixels = []
    for r, g, b, a in work.getdata():
        level = _detect_overlay_cleanup_level(r, g, b, a)
        if not level:
            pixels.append((255, 255, 255, 255))
            continue
        color = _OVERLAY_REGION_LEVEL_SPECS[level]['color']
        pixels.append((color[0], color[1], color[2], 255))
    normalized.putdata(pixels)
    return normalized


def _load_overlay_label_font(size: int):
    from PIL import ImageFont

    font_size = max(12, min(36, int(size or 12)))
    for candidate in _OVERLAY_LABEL_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, font_size)
        except Exception:
            continue
    return ImageFont.load_default()


def _overlay_region_bbox_to_pixels(region: Dict[str, Any], width: int, height: int) -> Optional[Tuple[int, int, int, int]]:
    if width <= 0 or height <= 0:
        return None
    bbox = region.get('bbox') or {}
    left_ratio = _clip_region_ratio(bbox.get('x'))
    top_ratio = _clip_region_ratio(bbox.get('y'))
    right_ratio = _clip_region_ratio(left_ratio + _clip_region_ratio(bbox.get('w')))
    bottom_ratio = _clip_region_ratio(top_ratio + _clip_region_ratio(bbox.get('h')))
    left = int(round(left_ratio * width))
    top = int(round(top_ratio * height))
    right = int(round(right_ratio * width))
    bottom = int(round(bottom_ratio * height))
    left = max(0, min(width - 1, left))
    top = max(0, min(height - 1, top))
    right = max(left + 1, min(width, right)) - 1
    bottom = max(top + 1, min(height, bottom)) - 1
    return left, top, right, bottom


def _render_overlay_from_regions(image_size: Tuple[int, int], regions: List[Dict[str, Any]]):
    from PIL import Image, ImageDraw

    width, height = image_size
    overlay = Image.new('RGBA', (max(1, width), max(1, height)), (255, 255, 255, 255))
    if width <= 0 or height <= 0:
        return overlay

    draw = ImageDraw.Draw(overlay)
    font_cache: Dict[int, Any] = {}

    def _font_for(size: int):
        key = max(12, min(36, int(size or 12)))
        if key not in font_cache:
            font_cache[key] = _load_overlay_label_font(key)
        return font_cache[key]

    ordered_regions = sorted(
        [region for region in (regions or []) if isinstance(region, dict) and region.get('bbox')],
        key=lambda item: (
            _OVERLAY_REGION_DRAW_ORDER.get(str(item.get('level') or '').lower(), 99),
            int(item.get('rank') or 0),
            str(item.get('region_id') or ''),
        ),
    )
    for region in ordered_regions:
        level = str(region.get('level') or '').lower()
        spec = _OVERLAY_REGION_LEVEL_SPECS.get(level)
        rect = _overlay_region_bbox_to_pixels(region, width, height)
        if not spec or not rect:
            continue
        left, top, right, bottom = rect
        box_w = max(1, right - left + 1)
        box_h = max(1, bottom - top + 1)
        label_text = str(region.get('title') or f"{spec['label']}-{int(region.get('rank') or 0) or 1}")
        label_font = _font_for(min(max(int(round(min(box_w, box_h) * 0.18)), 12), 28))
        stroke_width = 2 if level in ('d', 'm') else 3
        draw.rectangle([left, top, right, bottom], outline=spec['color'], width=stroke_width)
        draw.text((left + 6, top + 4), label_text, fill=spec['color'], font=label_font)
    return overlay


def _sanitize_overlay_image(image):
    normalized = _normalize_overlay_palette(image)
    regions = _extract_overlay_regions(normalized)
    if not regions:
        return normalized
    rendered = _render_overlay_from_regions(normalized.size, regions)
    return _normalize_overlay_palette(rendered)


def _resize_overlay_for_region_parse(image):
    width, height = image.size
    if width <= 0 or height <= 0:
        return image
    max_dim = max(width, height)
    if max_dim <= _OVERLAY_REGION_PARSE_MAX_DIM:
        return image
    ratio = _OVERLAY_REGION_PARSE_MAX_DIM / float(max_dim)
    next_width = max(1, int(round(width * ratio)))
    next_height = max(1, int(round(height * ratio)))
    return image.resize((next_width, next_height), _resample_lanczos())


_OVERLAY_REGION_CONTOUR_PAD = {'d': 5, 'm': 6, 't': 7}
_OVERLAY_REGION_HOLE_MIN_AREA = {'d': 160.0, 'm': 220.0, 't': 320.0}
_OVERLAY_REGION_OUTER_MAX_FILL = {'m': 0.16, 't': 0.18}
_OVERLAY_REGION_D_OUTER_MIN_AREA = 8000.0
_OVERLAY_REGION_D_OUTER_MAX_FILL = 0.58
_OVERLAY_REGION_D_INNER_MIN_AREA = 350


def _overlay_region_box_contains(outer: Tuple[int, int, int, int], inner: Tuple[int, int, int, int],
                                 tolerance: int = 3) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (
        ix >= ox - tolerance
        and iy >= oy - tolerance
        and (ix + iw) <= (ox + ow + tolerance)
        and (iy + ih) <= (oy + oh + tolerance)
    )


def _group_overlay_projection_indices(values, threshold: int) -> List[Tuple[int, int]]:
    try:
        import numpy as np  # noqa: PLC0415
    except Exception:
        return []

    idxs = np.where(values >= max(1, int(threshold)))[0]
    if idxs.size <= 0:
        return []
    groups: List[Tuple[int, int]] = []
    start = int(idxs[0])
    prev = int(idxs[0])
    for raw_value in idxs[1:]:
        value = int(raw_value)
        if value <= prev + 1:
            prev = value
            continue
        groups.append((start, prev))
        start = value
        prev = value
    groups.append((start, prev))
    return groups


def _split_overlay_m_outer_candidate(mask, outer: Dict[str, Any], holes: List[Dict[str, Any]],
                                     width: int, height: int) -> List[Dict[str, Any]]:
    try:
        import cv2  # noqa: PLC0415
    except Exception:
        return []

    x = int(outer['x'])
    y = int(outer['y'])
    w = int(outer['w'])
    h = int(outer['h'])
    if w < 180 or h < 180:
        return []

    sub = mask[y:y + h, x:x + w]
    if sub.size <= 0:
        return []
    closed = cv2.morphologyEx(sub, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))

    binary_closed = (closed > 0).astype('uint8')
    col_groups = _group_overlay_projection_indices(binary_closed.sum(axis=0), max(20, int(h * 0.22)))
    if len(col_groups) < 3:
        return []
    left_col = (col_groups[0][0] + col_groups[0][1]) // 2
    right_col = (col_groups[-1][0] + col_groups[-1][1]) // 2
    full_span_width = right_col - left_col + 1
    if full_span_width < max(120, int(w * 0.55)):
        return []

    row_groups = _group_overlay_projection_indices(
        binary_closed[:, left_col:right_col + 1].sum(axis=1),
        max(20, int(full_span_width * 0.22)),
    )
    if len(row_groups) < 2:
        return []

    top_row = (row_groups[0][0] + row_groups[0][1]) // 2
    divider_row = (row_groups[1][0] + row_groups[1][1]) // 2
    if divider_row - top_row < 40:
        return []

    top_box = {
        'x': x + left_col,
        'y': y + top_row,
        'w': full_span_width,
        'h': divider_row - top_row + 1,
        'pixel_count': int(outer.get('pixel_count') or 0),
        'kind': 'split_top',
    }

    outer_box = (x, y, w, h)
    contained_left_holes = [
        hole for hole in holes
        if _overlay_region_box_contains(outer_box, (hole['x'], hole['y'], hole['w'], hole['h']))
        and hole['x'] <= x + int(w * 0.55)
        and (hole['y'] + hole['h']) >= (top_box['y'] + top_box['h'])
    ]
    if not contained_left_holes:
        return [top_box]

    left_hole = min(contained_left_holes, key=lambda item: (item['x'], -item['h'], -item['w']))
    residual_left = max(left_hole['x'] + left_hole['w'], x + int(w * 0.22))
    residual_top = max(top_box['y'] + top_box['h'] - 1, left_hole['y'])
    residual_w = (x + w) - residual_left
    residual_h = (y + h) - residual_top
    if residual_w < 120 or residual_h < 120:
        return [top_box]

    residual_box = {
        'x': residual_left,
        'y': residual_top,
        'w': residual_w,
        'h': residual_h,
        'pixel_count': int(outer.get('pixel_count') or 0),
        'kind': 'split_residual',
    }
    return [top_box, residual_box]


def _extract_overlay_t_regions_from_mask(mask, width: int, height: int) -> List[Dict[str, Any]]:
    try:
        import cv2  # noqa: PLC0415
    except Exception:
        return []

    if width <= 0 or height <= 0:
        return []

    image_area = float(width * height)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    contours, hierarchy = cv2.findContours(closed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []

    outer_candidates: List[Dict[str, Any]] = []
    hole_candidates: List[Dict[str, Any]] = []
    for index, contour in enumerate(contours):
        x, y, w, h = cv2.boundingRect(contour)
        box_area = float(w * h)
        if box_area < max(4000.0, image_area * 0.08):
            continue
        contour_area = float(cv2.contourArea(contour))
        fill_ratio = contour_area / box_area if box_area > 0 else 0.0
        parent = int(hierarchy[0][index][3])
        child = int(hierarchy[0][index][2])
        if parent == -1:
            touches_edge = x <= 4 or y <= 4 or (x + w) >= width - 4 or (y + h) >= height - 4
            if not touches_edge or child == -1 or box_area < image_area * 0.22:
                continue
            outer_candidates.append({
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'pixel_count': int(round(contour_area)),
            })
            continue
        if box_area < image_area * 0.12 or fill_ratio < 0.55:
            continue
        hole_candidates.append({
            'x': x,
            'y': y,
            'w': w,
            'h': h,
            'pixel_count': int(round(contour_area)),
        })

    if not outer_candidates:
        return []

    spec = _OVERLAY_REGION_LEVEL_SPECS['t']
    primary_outer = max(outer_candidates, key=lambda item: item['w'] * item['h'])
    outer_box = (primary_outer['x'], primary_outer['y'], primary_outer['w'], primary_outer['h'])

    kept: List[Dict[str, Any]] = [
        {
            'x': primary_outer['x'],
            'y': primary_outer['y'],
            'w': primary_outer['w'],
            'h': primary_outer['h'],
            'pixel_count': primary_outer['pixel_count'],
            'kind': 'outer',
        }
    ]
    nested_holes = [
        hole for hole in hole_candidates
        if _overlay_region_box_contains(outer_box, (hole['x'], hole['y'], hole['w'], hole['h']))
    ]
    nested_holes.sort(key=lambda item: (-(item['w'] * item['h']), item['y'], item['x']))
    for hole in nested_holes[:3]:
        kept.append({
            'x': hole['x'],
            'y': hole['y'],
            'w': hole['w'],
            'h': hole['h'],
            'pixel_count': hole['pixel_count'],
            'kind': 'hole',
        })

    kept.sort(key=lambda item: (item['y'], item['x'], -(item['w'] * item['h'])))
    regions: List[Dict[str, Any]] = []
    for index, component in enumerate(kept, start=1):
        regions.append({
            'region_id': f't_{index}',
            'level': 't',
            'title': f"{spec['label']}-{index}",
            'bbox': _build_region_bbox_norm(component['x'], component['y'], component['w'], component['h'], width, height),
            'rank': index,
            'source': f"auto_{component['kind']}",
            'pixel_count': component['pixel_count'],
        })
    return regions


def _extract_overlay_d_regions_from_mask(mask, width: int, height: int) -> List[Dict[str, Any]]:
    try:
        import cv2  # noqa: PLC0415
    except Exception:
        return []

    if width <= 0 or height <= 0:
        return []

    image_area = float(width * height)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []

    spec = _OVERLAY_REGION_LEVEL_SPECS['d']
    hole_candidates: List[Dict[str, Any]] = []
    outer_candidates: List[Dict[str, Any]] = []
    supplemental_candidates: List[Dict[str, Any]] = []

    for index, contour in enumerate(contours):
        x, y, w, h = cv2.boundingRect(contour)
        if w < spec['min_width'] or h < spec['min_height']:
            continue
        contour_area = float(cv2.contourArea(contour))
        box_area = float(w * h)
        child = int(hierarchy[0][index][2])
        parent = int(hierarchy[0][index][3])

        if parent != -1:
            if contour_area < _OVERLAY_REGION_HOLE_MIN_AREA['d']:
                continue
            bx, by, bw, bh = _expand_overlay_region_box(x, y, w, h, width, height, _OVERLAY_REGION_CONTOUR_PAD['d'])
            hole_candidates.append({
                'x': bx,
                'y': by,
                'w': bw,
                'h': bh,
                'pixel_count': int(round(contour_area)),
                'kind': 'hole',
            })
            continue

        if child == -1 or box_area < max(_OVERLAY_REGION_D_OUTER_MIN_AREA, image_area * 0.006):
            continue
        fill_ratio = contour_area / box_area if box_area > 0 else 0.0
        if fill_ratio > _OVERLAY_REGION_D_OUTER_MAX_FILL:
            continue

        outer_candidates.append({
            'x': int(x),
            'y': int(y),
            'w': int(w),
            'h': int(h),
            'box_area': box_area,
        })

    for outer in outer_candidates:
        x = int(outer['x'])
        y = int(outer['y'])
        w = int(outer['w'])
        h = int(outer['h'])

        sub = mask[y:y + h, x:x + w]
        if sub.size <= 0:
            continue
        closed = cv2.morphologyEx(sub, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        binary_closed = (closed > 0).astype('uint8')
        binary_closed[0, :] = 1
        binary_closed[-1, :] = 1
        binary_closed[:, 0] = 1
        binary_closed[:, -1] = 1

        free = (1 - binary_closed).astype('uint8')
        num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(free, 8)
        local_candidates: List[Dict[str, Any]] = []
        min_inner_area = max(_OVERLAY_REGION_D_INNER_MIN_AREA, int(outer['box_area'] * 0.045), 1200)
        for label in range(1, int(num_labels)):
            inner_x, inner_y, inner_w, inner_h, inner_area = stats[label]
            if inner_area < min_inner_area:
                continue
            if inner_w < spec['min_width'] or inner_h < spec['min_height']:
                continue
            if min(int(inner_w), int(inner_h)) < 36:
                continue
            local_candidates.append({
                'x': int(inner_x + x),
                'y': int(inner_y + y),
                'w': int(inner_w),
                'h': int(inner_h),
                'pixel_count': int(inner_area),
                'kind': 'inner',
                'outer_w': int(w),
                'outer_h': int(h),
            })

        strong_count = len(local_candidates)
        accepted_local_candidates: List[Dict[str, Any]] = []
        for candidate in sorted(local_candidates, key=lambda item: (-(item['w'] * item['h']), item['y'], item['x'])):
            if strong_count > 1 and candidate['w'] >= candidate['outer_w'] * 0.85 and candidate['h'] >= candidate['outer_h'] * 0.55:
                continue

            contains_other = False
            candidate_area = candidate['w'] * candidate['h']
            candidate_box = (candidate['x'], candidate['y'], candidate['w'], candidate['h'])
            for other in local_candidates:
                if other is candidate:
                    continue
                other_area = other['w'] * other['h']
                if other_area >= max(_OVERLAY_REGION_D_INNER_MIN_AREA, int(candidate_area * 0.12)) and other_area < candidate_area:
                    other_box = (other['x'], other['y'], other['w'], other['h'])
                    if _overlay_region_box_contains(candidate_box, other_box, tolerance=0):
                        contains_other = True
                        break
            if contains_other:
                continue

            center_x = candidate['x'] + candidate['w'] / 2.0
            center_y = candidate['y'] + candidate['h'] / 2.0
            duplicate_with_hole = False
            for hole in hole_candidates:
                if (
                    hole['x'] <= center_x <= (hole['x'] + hole['w'])
                    and hole['y'] <= center_y <= (hole['y'] + hole['h'])
                ):
                    duplicate_with_hole = True
                    break
                if _overlay_region_box_iou(candidate_box, (hole['x'], hole['y'], hole['w'], hole['h'])) > 0.25:
                    duplicate_with_hole = True
                    break
            if duplicate_with_hole:
                continue

            accepted_local_candidates.append({
                'x': candidate['x'],
                'y': candidate['y'],
                'w': candidate['w'],
                'h': candidate['h'],
                'pixel_count': candidate['pixel_count'],
                'kind': 'inner',
            })

        supplemental_candidates.extend(accepted_local_candidates[:2])

    candidates: List[Dict[str, Any]] = []
    candidates.extend(hole_candidates)
    candidates.extend(supplemental_candidates)
    candidates.sort(key=lambda item: (0 if item['kind'] == 'hole' else 1, item['y'], item['x'], -(item['w'] * item['h'])))

    kept: List[Dict[str, Any]] = []
    for candidate in candidates:
        box = (candidate['x'], candidate['y'], candidate['w'], candidate['h'])
        if any(_overlay_region_box_iou(box, (item['x'], item['y'], item['w'], item['h'])) > 0.78 for item in kept):
            continue
        kept.append(candidate)

    kept.sort(key=lambda item: (item['y'], item['x'], -(item['w'] * item['h'])))
    regions: List[Dict[str, Any]] = []
    for index, component in enumerate(kept, start=1):
        regions.append({
            'region_id': f'd_{index}',
            'level': 'd',
            'title': f"{spec['label']}-{index}",
            'bbox': _build_region_bbox_norm(component['x'], component['y'], component['w'], component['h'], width, height),
            'rank': index,
            'source': f"auto_{component['kind']}",
            'pixel_count': component['pixel_count'],
        })
    return regions


def _expand_overlay_region_box(x: int, y: int, w: int, h: int, width: int, height: int,
                               pad: int) -> Tuple[int, int, int, int]:
    next_x = max(0, int(x) - int(pad))
    next_y = max(0, int(y) - int(pad))
    next_w = min(width - next_x, int(w) + int(pad) * 2)
    next_h = min(height - next_y, int(h) + int(pad) * 2)
    return next_x, next_y, max(1, next_w), max(1, next_h)


def _overlay_region_box_iou(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh
    inter_w = max(0, min(ax2, bx2) - max(ax, bx))
    inter_h = max(0, min(ay2, by2) - max(ay, by))
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    if union <= 0:
        return 0.0
    return inter / float(union)


def _extract_overlay_regions_by_connected_components(image) -> List[Dict[str, Any]]:
    work = _resize_overlay_for_region_parse(image.convert('RGBA'))
    width, height = work.size
    if width <= 0 or height <= 0:
        return []

    points_by_level = {'d': set(), 'm': set(), 't': set()}
    for idx, (r, g, b, a) in enumerate(work.getdata()):
        matched_level = ''
        for level in ('d', 'm', 't'):
            if _should_match_overlay_level(level, r, g, b, a):
                matched_level = level
                break
        if not matched_level:
            continue
        x = idx % width
        y = idx // width
        points_by_level[matched_level].add((x, y))

    regions: List[Dict[str, Any]] = []
    for level in ('d', 'm', 't'):
        spec = _OVERLAY_REGION_LEVEL_SPECS[level]
        remaining = points_by_level[level]
        components: List[Dict[str, int]] = []
        while remaining:
            start_x, start_y = remaining.pop()
            stack = [(start_x, start_y)]
            min_x = max_x = start_x
            min_y = max_y = start_y
            pixel_count = 1
            while stack:
                current_x, current_y = stack.pop()
                for next_x in range(current_x - 1, current_x + 2):
                    for next_y in range(current_y - 1, current_y + 2):
                        if (next_x, next_y) not in remaining:
                            continue
                        remaining.remove((next_x, next_y))
                        stack.append((next_x, next_y))
                        pixel_count += 1
                        if next_x < min_x:
                            min_x = next_x
                        if next_x > max_x:
                            max_x = next_x
                        if next_y < min_y:
                            min_y = next_y
                        if next_y > max_y:
                            max_y = next_y
            box_width = max_x - min_x + 1
            box_height = max_y - min_y + 1
            if pixel_count < spec['min_pixels']:
                continue
            if box_width < spec['min_width'] or box_height < spec['min_height']:
                continue
            components.append({
                'x': min_x,
                'y': min_y,
                'w': box_width,
                'h': box_height,
                'pixel_count': pixel_count,
            })

        components.sort(key=lambda item: (item['y'], item['x'], -(item['w'] * item['h'])))
        for index, component in enumerate(components, start=1):
            regions.append({
                'region_id': f'{level}_{index}',
                'level': level,
                'title': f"{spec['label']}-{index}",
                'bbox': _build_region_bbox_norm(component['x'], component['y'], component['w'], component['h'], width, height),
                'rank': index,
                'source': 'auto_fallback',
                'pixel_count': component['pixel_count'],
            })
    return regions


def _extract_overlay_regions_by_contours(image) -> List[Dict[str, Any]]:
    try:
        import cv2  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
    except Exception:
        return []

    work = _normalize_overlay_palette(_resize_overlay_for_region_parse(image.convert('RGBA')))
    width, height = work.size
    if width <= 0 or height <= 0:
        return []

    image_area = float(width * height)
    rgba = np.asarray(work)
    regions: List[Dict[str, Any]] = []

    for level in ('d', 'm', 't'):
        spec = _OVERLAY_REGION_LEVEL_SPECS[level]
        target = spec['color']
        pad = _OVERLAY_REGION_CONTOUR_PAD[level]
        mask = (
            (rgba[:, :, 0] == target[0])
            & (rgba[:, :, 1] == target[1])
            & (rgba[:, :, 2] == target[2])
            & (rgba[:, :, 3] >= 200)
        ).astype(np.uint8) * 255
        if not np.any(mask):
            continue

        if level == 'd':
            d_regions = _extract_overlay_d_regions_from_mask(mask, width, height)
            if d_regions:
                regions.extend(d_regions)
                continue

        if level == 't':
            t_regions = _extract_overlay_t_regions_from_mask(mask, width, height)
            if t_regions:
                regions.extend(t_regions)
                continue

        contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is None:
            continue

        candidates: List[Dict[str, Any]] = []
        hole_candidates: List[Dict[str, Any]] = []
        outer_candidates: List[Dict[str, Any]] = []
        largest_t_outer = None
        largest_t_outer_score = -1.0

        for index, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            if w < spec['min_width'] or h < spec['min_height']:
                continue
            contour_area = float(cv2.contourArea(contour))
            box_area = float(w * h)
            child = int(hierarchy[0][index][2])
            parent = int(hierarchy[0][index][3])

            if parent != -1:
                if contour_area < _OVERLAY_REGION_HOLE_MIN_AREA[level]:
                    continue
                bx, by, bw, bh = _expand_overlay_region_box(x, y, w, h, width, height, pad)
                hole_candidate = {
                    'x': bx,
                    'y': by,
                    'w': bw,
                    'h': bh,
                    'pixel_count': int(round(contour_area)),
                    'kind': 'hole',
                }
                hole_candidates.append(hole_candidate)
                continue

            if level == 'd':
                continue

            fill_ratio = contour_area / box_area if box_area > 0 else 0.0
            if level == 'm':
                if child == -1:
                    continue
                if fill_ratio <= _OVERLAY_REGION_OUTER_MAX_FILL['m'] and box_area >= max(2800.0, image_area * 0.012):
                    bx, by, bw, bh = _expand_overlay_region_box(x, y, w, h, width, height, 1)
                    outer_candidates.append({
                        'x': bx,
                        'y': by,
                        'w': bw,
                        'h': bh,
                        'pixel_count': int(round(contour_area)),
                        'kind': 'outer',
                    })
                continue

            touches_edge = x <= 4 or y <= 4 or (x + w) >= width - 4 or (y + h) >= height - 4
            if not touches_edge or fill_ratio > _OVERLAY_REGION_OUTER_MAX_FILL['t']:
                continue
            if box_area > largest_t_outer_score:
                bx, by, bw, bh = _expand_overlay_region_box(x, y, w, h, width, height, 1)
                largest_t_outer = {
                    'x': bx,
                    'y': by,
                    'w': bw,
                    'h': bh,
                    'pixel_count': int(round(contour_area)),
                    'kind': 'outer',
                }
                largest_t_outer_score = box_area

        if level == 't' and largest_t_outer is not None:
            candidates.append(largest_t_outer)

        if level == 'm':
            candidates.extend(hole_candidates)
            for outer_candidate in outer_candidates:
                split_candidates = _split_overlay_m_outer_candidate(mask, outer_candidate, hole_candidates, width, height)
                if split_candidates:
                    candidates.extend(split_candidates)
                else:
                    candidates.append(outer_candidate)
        else:
            candidates.extend(hole_candidates)

        candidates.sort(key=lambda item: (0 if item['kind'] == 'hole' else 1, item['y'], item['x'], -(item['w'] * item['h'])))
        kept: List[Dict[str, Any]] = []
        for candidate in candidates:
            box = (candidate['x'], candidate['y'], candidate['w'], candidate['h'])
            if any(_overlay_region_box_iou(box, (item['x'], item['y'], item['w'], item['h'])) > 0.78 for item in kept):
                continue
            kept.append(candidate)

        kept.sort(key=lambda item: (item['y'], item['x'], -(item['w'] * item['h'])))
        for index, component in enumerate(kept, start=1):
            regions.append({
                'region_id': f'{level}_{index}',
                'level': level,
                'title': f"{spec['label']}-{index}",
                'bbox': _build_region_bbox_norm(component['x'], component['y'], component['w'], component['h'], width, height),
                'rank': index,
                'source': f"auto_{component['kind']}",
                'pixel_count': component['pixel_count'],
            })
    return regions


def _extract_overlay_regions(image) -> List[Dict[str, Any]]:
    regions = _extract_overlay_regions_by_contours(image)
    if regions:
        return regions
    return _extract_overlay_regions_by_connected_components(image)


def _overlay_job_key(username: str, analysis_id: str, unit_id: str) -> str:
    return f'{username}::{analysis_id}::{unit_id}'


def _set_ci_overlay_busy(username: str, analysis_id: str, unit_id: str, running: bool) -> None:
    key = _overlay_job_key(username, analysis_id, unit_id)
    with _ci_overlay_jobs_lock:
        if running:
            bucket = _ci_overlay_busy.setdefault(username, set())
            bucket.add(key)
        else:
            bucket = _ci_overlay_busy.get(username)
            if bucket is not None:
                bucket.discard(key)
                if not bucket:
                    _ci_overlay_busy.pop(username, None)


def _is_ci_overlay_busy(username: str, analysis_id: str, unit_id: str) -> bool:
    key = _overlay_job_key(username, analysis_id, unit_id)
    with _ci_overlay_jobs_lock:
        return key in _ci_overlay_busy.get(username, set())


def _set_ci_overlay_job(username: str, analysis_id: str, unit_id: str, payload: Dict[str, Any]) -> None:
    key = _overlay_job_key(username, analysis_id, unit_id)
    with _ci_overlay_jobs_lock:
        _ci_overlay_jobs[key] = payload


def get_ci_overlay_job(username: str, analysis_id: str, unit_id: str) -> Optional[Dict[str, Any]]:
    key = _overlay_job_key(username, analysis_id, unit_id)
    with _ci_overlay_jobs_lock:
        job = _ci_overlay_jobs.get(key)
    if not isinstance(job, dict):
        return None
    return dict(job)


def _overlay_layer_path(paths: Dict[str, str]) -> str:
    return os.path.join(paths['root'], 'overlay_layer.json')


def _overlay_dir(paths: Dict[str, str]) -> str:
    path = os.path.join(paths['root'], 'overlay')
    os.makedirs(path, exist_ok=True)
    return path


def _overlay_item_paths(paths: Dict[str, str], unit_id: str) -> Tuple[str, str]:
    base = os.path.join(_overlay_dir(paths), unit_id)
    return f'{base}.overlay_current.png', f'{base}.overlay_prev.png'


def _overlay_layer_item_paths(paths: Dict[str, str], unit_id: str, level: str) -> Tuple[str, str]:
    normalized_level = _normalize_overlay_level(level)
    if not normalized_level:
        raise ValueError(f'未知覆盖层级: {level}')
    base = os.path.join(_overlay_dir(paths), f'{unit_id}.{normalized_level}')
    return f'{base}.overlay_current.png', f'{base}.overlay_prev.png'


def _overlay_rel_path(paths: Dict[str, str], abs_path: str) -> str:
    rel = os.path.relpath(abs_path, paths['root'])
    return _normalize_rel(rel).replace('\\', '/')


def _filter_overlay_image_to_level(image, level: str, white_alpha: int = 255):
    normalized_level = _normalize_overlay_level(level)
    source = _normalize_overlay_palette(image.convert('RGBA'))
    if not normalized_level:
        return source

    target = _OVERLAY_REGION_LEVEL_SPECS[normalized_level]['color']
    next_pixels = []
    bg_alpha = max(0, min(255, int(white_alpha)))
    for r, g, b, a in source.getdata():
        if _should_match_overlay_level(normalized_level, r, g, b, a):
            next_pixels.append((target[0], target[1], target[2], 255))
        else:
            next_pixels.append((255, 255, 255, bg_alpha))
    out = source.copy()
    out.putdata(next_pixels)
    return out


def _split_overlay_image_by_levels(image) -> Dict[str, Any]:
    source = image.convert('RGBA')
    return {level: _filter_overlay_image_to_level(source, level) for level in _OVERLAY_LEVELS}


def _coerce_overlay_layer_images(layer_images: Optional[Dict[str, Any]], base_size: Tuple[int, int]) -> Dict[str, Any]:
    width = max(1, int((base_size or (1, 1))[0] or 1))
    height = max(1, int((base_size or (1, 1))[1] or 1))
    next_images: Dict[str, Any] = {}
    for level in _OVERLAY_LEVELS:
        image = layer_images.get(level) if isinstance(layer_images, dict) else None
        if image is None:
            next_images[level] = _create_blank_overlay_image((width, height))
            continue
        coerced = image.convert('RGBA')
        if coerced.size != (width, height):
            coerced = coerced.resize((width, height), _resample_lanczos())
        next_images[level] = coerced
    return next_images


def _compose_overlay_level_images(layer_images: Dict[str, Any], size: Optional[Tuple[int, int]] = None):
    from PIL import Image

    base_size = None
    if size and len(size) == 2:
        base_size = (max(1, int(size[0])), max(1, int(size[1])))
    if not base_size:
        for level in _OVERLAY_LAYER_COMPOSITE_ORDER:
            image = layer_images.get(level)
            if image is not None and getattr(image, 'size', None):
                base_size = image.size
                break
    if not base_size:
        raise ValueError('缺少可合成的 D/M/T 覆盖层图片')

    composite = Image.new('RGBA', base_size, (255, 255, 255, 0))
    for level in _OVERLAY_LAYER_COMPOSITE_ORDER:
        image = layer_images.get(level)
        if image is None:
            continue
        layer = _filter_overlay_image_to_level(image, level, white_alpha=0).convert('RGBA')
        if layer.size != base_size:
            layer = layer.resize(base_size, _resample_lanczos())
        composite.alpha_composite(layer)

    out = Image.new('RGBA', base_size, (255, 255, 255, 255))
    out.alpha_composite(composite)
    return out


def _load_overlay_level_images(paths: Dict[str, str], unit_id: str, target: str = 'current', base_image=None) -> Dict[str, Any]:
    from PIL import Image

    normalized_target = 'prev' if str(target).strip().lower() == 'prev' else 'current'
    cur_path, prev_path = _overlay_item_paths(paths, unit_id)
    aggregate_path = prev_path if normalized_target == 'prev' else cur_path
    aggregate_image = base_image.convert('RGBA') if base_image is not None else None
    if aggregate_image is None and os.path.isfile(aggregate_path):
        aggregate_image = Image.open(aggregate_path).convert('RGBA')

    images: Dict[str, Any] = {}
    for level in _OVERLAY_LEVELS:
        level_cur_path, level_prev_path = _overlay_layer_item_paths(paths, unit_id, level)
        level_path = level_prev_path if normalized_target == 'prev' else level_cur_path
        if os.path.isfile(level_path):
            images[level] = Image.open(level_path).convert('RGBA')
        elif aggregate_image is not None:
            images[level] = _filter_overlay_image_to_level(aggregate_image, level)
        else:
            images[level] = None
    return images


def _build_overlay_layer_state(level: str, bbox: Optional[Dict[str, Any]], regions: List[Dict[str, Any]],
                               version: str, updated_at: str) -> Dict[str, Any]:
    return {
        'level': _normalize_overlay_level(level),
        'overlay_bbox': copy.deepcopy(bbox) if isinstance(bbox, dict) else None,
        'regions': _sort_overlay_regions(copy.deepcopy(regions) or []),
        'regions_version': version or '',
        'updated_at': updated_at or '',
    }


def _merge_overlay_regions_from_layers(layer_states: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for level in _OVERLAY_LEVELS:
        merged.extend(copy.deepcopy((layer_states.get(level) or {}).get('regions') or []))
    return _sort_overlay_regions(merged)


def _save_overlay_image_file(path: str, overlay_img, preserve_exact: bool = False, overlay_level: str = '',
                             fallback_bbox: Optional[Dict[str, Any]] = None,
                             regions_override: Optional[List[Dict[str, Any]]] = None,
                             timing_label: str = '',
                             fast_manual: bool = False,
                             skip_write: bool = False) -> Tuple[str, Optional[Dict[str, Any]], List[Dict[str, Any]], str]:
    t0 = time.perf_counter()
    normalized_level = _normalize_overlay_level(overlay_level)
    level_regions_override = None
    if regions_override is not None:
        level_regions_override = copy.deepcopy(regions_override)
        if normalized_level:
            level_regions_override = [
                region for region in level_regions_override
                if _normalize_overlay_level(region.get('level')) == normalized_level
            ]

    if skip_write and os.path.isfile(path):
        bbox = _bbox_from_overlay_regions(level_regions_override or []) if level_regions_override is not None else None
        if bbox is None and fallback_bbox is not None:
            bbox = copy.deepcopy(fallback_bbox)
        regions = _sort_overlay_regions(level_regions_override or [])
        _ci_overlay_timing_log(
            f'skip_write{(" " + timing_label) if timing_label else ""}',
            t0,
            f'count={len(regions)} level={normalized_level or "all"}',
        )
        return path, bbox, regions, _overlay_file_version(path)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    use_fast_manual = bool(fast_manual and regions_override is not None)
    data, overlay_comp = _prepare_overlay_write_payload(
        overlay_img,
        preserve_exact=bool(preserve_exact),
        skip_palette_normalize=use_fast_manual,
        fast_encode=use_fast_manual,
    )
    t1 = _ci_overlay_timing_log(
        f'encode_png{(" " + timing_label) if timing_label else ""}',
        t0,
        f'{overlay_img.size[0]}x{overlay_img.size[1]} bytes={len(data)} preserve_exact={preserve_exact} fast={use_fast_manual}',
    )
    with open(path, 'wb') as f:
        f.write(data)
    t2 = _ci_overlay_timing_log(f'write_file{(" " + timing_label) if timing_label else ""}', t1, os.path.basename(path))

    if use_fast_manual:
        regions = _sort_overlay_regions(level_regions_override or [])
        bbox = _bbox_from_overlay_regions(regions if not normalized_level else level_regions_override or [])
        if bbox is None and fallback_bbox is not None:
            bbox = copy.deepcopy(fallback_bbox)
        _ci_overlay_timing_log(
            f'bbox_from_regions{(" " + timing_label) if timing_label else ""}',
            t2,
            f'count={len(regions)} level={normalized_level or "all"}',
        )
        return path, bbox, regions, _overlay_file_version(path)

    analysis_image = _filter_overlay_image_to_level(overlay_comp, normalized_level) if normalized_level else overlay_comp
    bbox = _extract_nonwhite_bbox_norm(analysis_image, threshold=240)
    if bbox is None and fallback_bbox is not None:
        bbox = copy.deepcopy(fallback_bbox)
    t3 = _ci_overlay_timing_log(f'bbox{(" " + timing_label) if timing_label else ""}', t2)
    if regions_override is not None:
        regions = copy.deepcopy(regions_override)
        if normalized_level:
            regions = [region for region in regions if _normalize_overlay_level(region.get('level')) == normalized_level]
        _ci_overlay_timing_log(
            f'regions_override{(" " + timing_label) if timing_label else ""}',
            t3,
            f'count={len(regions)} level={normalized_level or "all"}',
        )
    else:
        regions = _extract_overlay_regions(analysis_image)
        if normalized_level:
            regions = [region for region in regions if _normalize_overlay_level(region.get('level')) == normalized_level]
        _ci_overlay_timing_log(
            f'regions_extract{(" " + timing_label) if timing_label else ""}',
            t3,
            f'count={len(regions)} level={normalized_level or "all"}',
        )
    return path, bbox, _sort_overlay_regions(regions), _overlay_file_version(path)


def _overlay_layer_to_response(paths: Dict[str, str], unit_id: str, level: str, item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    level_item = item if isinstance(item, dict) else {}
    cur_path, prev_path = _overlay_layer_item_paths(paths, unit_id, level)
    current_exists = os.path.isfile(cur_path)
    prev_exists = os.path.isfile(prev_path)
    return {
        'level': level,
        'label': _OVERLAY_REGION_LEVEL_SPECS[level]['label'],
        'overlay_path': _overlay_rel_path(paths, cur_path) if current_exists else '',
        'overlay_bbox': copy.deepcopy(level_item.get('overlay_bbox')) if isinstance(level_item.get('overlay_bbox'), dict) else None,
        'regions': copy.deepcopy(level_item.get('regions') or []),
        'regions_version': level_item.get('regions_version', ''),
        'updated_at': level_item.get('updated_at', ''),
        'current_available': current_exists,
        'prev_available': prev_exists,
    }


def _overlay_item_to_response(paths: Dict[str, str], item: Dict[str, Any]) -> Dict[str, Any]:
    unit_id = item.get('unit_id', '')
    cur_path, prev_path = _overlay_item_paths(paths, unit_id)
    layer_items = item.get('layers') if isinstance(item.get('layers'), dict) else {}
    auto_iteration = copy.deepcopy(item.get('auto_iteration')) if isinstance(item.get('auto_iteration'), dict) else None
    layer_current_exists = any(os.path.isfile(_overlay_layer_item_paths(paths, unit_id, level)[0]) for level in _OVERLAY_LEVELS)
    layer_prev_exists = any(os.path.isfile(_overlay_layer_item_paths(paths, unit_id, level)[1]) for level in _OVERLAY_LEVELS)
    current_exists = os.path.isfile(cur_path) or layer_current_exists
    prev_exists = os.path.isfile(prev_path) or layer_prev_exists
    status = item.get('status', 'not_started')
    if current_exists:
        status = 'ready'
    elif status not in ('failed', 'running'):
        status = 'not_started'
    return {
        'unit_id': unit_id,
        'status': status,
        'instruction_text': item.get('instruction_text', ''),
        'overlay_path': _overlay_rel_path(paths, cur_path) if current_exists else '',
        'overlay_bbox': item.get('overlay_bbox') or None,
        'regions': copy.deepcopy(item.get('regions') or []),
        'regions_version': item.get('regions_version', ''),
        'updated_at': item.get('updated_at', ''),
        'error': item.get('error', ''),
        'current_available': current_exists,
        'prev_available': prev_exists,
        'layers': {level: _overlay_layer_to_response(paths, unit_id, level, layer_items.get(level)) for level in _OVERLAY_LEVELS},
        'auto_iteration': auto_iteration,
        'ci_sketch_handwriting_area_ratio': item.get('ci_sketch_handwriting_area_ratio'),
        'ci_dmt_coarse_layout': bool(item.get('ci_dmt_coarse_layout')),
        'ci_sketch_handwriting_estimate_note': item.get('ci_sketch_handwriting_estimate_note') or '',
        'lite_auto_iteration_last': copy.deepcopy(item.get('lite_auto_iteration_last')) if isinstance(item.get('lite_auto_iteration_last'), dict) else None,
        'debug_dir': '',
    }


def _ensure_overlay_layer(paths: Dict[str, str], manifest: Dict[str, Any], r_layer: Dict[str, Any]) -> Dict[str, Any]:
    ensure_t0 = time.perf_counter()
    layer_path = _overlay_layer_path(paths)
    raw = _safe_json_load(layer_path) if os.path.exists(layer_path) else None
    existing_items = {}
    if isinstance(raw, dict):
        for item in (raw.get('items') or []):
            if isinstance(item, dict) and item.get('unit_id'):
                existing_items[item['unit_id']] = dict(item)

    r_items = {
        item.get('unit_id', ''): item
        for item in (r_layer.get('items') or [])
        if isinstance(item, dict) and item.get('unit_id')
    }
    items = []
    input_units = [unit for unit in (manifest.get('input_units') or []) if isinstance(unit, dict) and unit.get('unit_id')]
    print(f'[CI overlay save] _ensure_overlay_layer start units={len(input_units)}', flush=True)
    for unit in input_units:
        unit_id = unit.get('unit_id', '')
        unit_t0 = time.perf_counter()
        current = existing_items.get(unit_id, {})
        r_item = r_items.get(unit_id, {})
        cur_path, _prev_path = _overlay_item_paths(paths, unit_id)
        overlay_bbox = current.get('overlay_bbox')
        regions: List[Dict[str, Any]] = copy.deepcopy(current.get('regions') or [])
        regions_version = current.get('regions_version', '')
        auto_iteration = copy.deepcopy(current.get('auto_iteration')) if isinstance(current.get('auto_iteration'), dict) else None
        current_layers = current.get('layers') if isinstance(current.get('layers'), dict) else {}
        layer_states = {
            level: _build_overlay_layer_state(
                level,
                (current_layers.get(level) or {}).get('overlay_bbox'),
                (current_layers.get(level) or {}).get('regions') or [],
                (current_layers.get(level) or {}).get('regions_version', ''),
                (current_layers.get(level) or {}).get('updated_at', current.get('updated_at', '')),
            )
            for level in _OVERLAY_LEVELS
        }

        aggregate_image = None
        current_level_images = _load_overlay_level_images(paths, unit_id, 'current')
        try:
            if os.path.isfile(cur_path):
                from PIL import Image

                aggregate_image = Image.open(cur_path).convert('RGBA')
            elif any(image is not None for image in current_level_images.values()):
                aggregate_image = _compose_overlay_level_images(current_level_images)
        except Exception:
            aggregate_image = None

        if aggregate_image is not None:
            overlay_bbox = _extract_nonwhite_bbox_norm(aggregate_image, threshold=240) or overlay_bbox
            regions_version = _overlay_file_version(cur_path) or regions_version

        for level in _OVERLAY_LEVELS:
            base_entry = current_layers.get(level) if isinstance(current_layers.get(level), dict) else {}
            level_cur_path, _level_prev_path = _overlay_layer_item_paths(paths, unit_id, level)
            level_image = current_level_images.get(level)
            level_bbox = base_entry.get('overlay_bbox')
            level_regions = copy.deepcopy(base_entry.get('regions') or [])
            level_version = base_entry.get('regions_version', '')
            level_updated_at = base_entry.get('updated_at', current.get('updated_at', ''))
            if level_image is not None:
                try:
                    level_bbox = _extract_nonwhite_bbox_norm(level_image, threshold=240)
                    extract_t0 = time.perf_counter()
                    level_regions = [
                        region for region in _extract_overlay_regions(level_image)
                        if _normalize_overlay_level(region.get('level')) == level
                    ]
                    _ci_overlay_timing_log(
                        f'_ensure_overlay_layer unit={unit_id} level={level} regions_extract',
                        extract_t0,
                        f'count={len(level_regions)} size={level_image.size[0]}x{level_image.size[1]}',
                    )
                    level_regions = _sort_overlay_regions(level_regions)
                    level_version = _overlay_file_version(level_cur_path) or level_version or regions_version
                except Exception:
                    pass
            layer_states[level] = _build_overlay_layer_state(level, level_bbox, level_regions, level_version, level_updated_at)

        merged_regions = _merge_overlay_regions_from_layers(layer_states)
        if merged_regions:
            regions = merged_regions
        elif aggregate_image is not None:
            try:
                extract_t0 = time.perf_counter()
                regions = _sort_overlay_regions(_extract_overlay_regions(aggregate_image))
                _ci_overlay_timing_log(
                    f'_ensure_overlay_layer unit={unit_id} aggregate regions_extract',
                    extract_t0,
                    f'count={len(regions)} size={aggregate_image.size[0]}x{aggregate_image.size[1]}',
                )
            except Exception:
                pass
        row = {
            'unit_id': unit_id,
            'status': current.get('status') or ('ready' if os.path.isfile(cur_path) else 'not_started'),
            'instruction_text': current.get('instruction_text', ''),
            'overlay_bbox': overlay_bbox,
            'regions': regions,
            'regions_version': regions_version,
            'layers': layer_states,
            'auto_iteration': auto_iteration,
            'updated_at': current.get('updated_at', ''),
            'error': current.get('error', ''),
            'reproduction_ready': r_item.get('status') == 'ready',
        }
        _merge_overlay_item_preserved_state(current, row)
        items.append(row)
        _ci_overlay_timing_log(f'_ensure_overlay_layer unit={unit_id} total', unit_t0)

    layer = {'layer': 'OVERLAY', 'items': items}
    dump_t0 = time.perf_counter()
    _safe_json_dump(layer_path, layer)
    _ci_overlay_timing_log('_ensure_overlay_layer json_dump', dump_t0)
    _ci_overlay_timing_log('_ensure_overlay_layer total', ensure_t0, f'units={len(items)}')
    return layer


def _load_overlay_layer_raw(paths: Dict[str, str]) -> Dict[str, Any]:
    layer_path = _overlay_layer_path(paths)
    raw = _safe_json_load(layer_path) if os.path.exists(layer_path) else None
    if isinstance(raw, dict):
        return raw
    return {'layer': 'OVERLAY', 'items': []}


def _update_overlay_item(paths: Dict[str, str], manifest: Dict[str, Any], r_layer: Dict[str, Any], unit_id: str,
                         updater, skip_ensure: bool = False) -> Dict[str, Any]:
    update_t0 = time.perf_counter()
    ensure_t0 = time.perf_counter()
    if skip_ensure:
        layer = _load_overlay_layer_raw(paths)
        if not isinstance(layer.get('items'), list):
            layer['items'] = []
        _ci_overlay_timing_log('_update_overlay_item load_overlay_layer_raw', ensure_t0, f'unit={unit_id}')
    else:
        layer = _ensure_overlay_layer(paths, manifest, r_layer)
        _ci_overlay_timing_log('_update_overlay_item ensure_overlay_layer', ensure_t0, f'unit={unit_id}')
    items = []
    updated = None
    for item in (layer.get('items') or []):
        if isinstance(item, dict) and item.get('unit_id') == unit_id:
            updated = updater(dict(item))
            items.append(updated)
        else:
            items.append(item)
    if updated is None:
        raise ValueError(f'未找到 unit_id={unit_id} 对应的覆盖层页项')
    layer['items'] = items
    dump_t0 = time.perf_counter()
    _safe_json_dump(_overlay_layer_path(paths), layer)
    _ci_overlay_timing_log('_update_overlay_item json_dump', dump_t0)
    _ci_overlay_timing_log('_update_overlay_item total', update_t0, f'unit={unit_id}')
    return updated


def _overlay_file_to_payload(path: str) -> Optional[Dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return None
    from PIL import Image

    image = Image.open(path).convert('RGBA')
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    bbox = _extract_nonwhite_bbox_norm(image, threshold=240) or {'x': 0.2, 'y': 0.2, 'w': 0.6, 'h': 0.6}
    return {
        'image': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('utf-8'),
        'bbox': bbox,
    }


def load_ci_overlay_history(username: str, analysis_id: str, unit_id: str) -> List[Dict[str, Any]]:
    from app_chat.ci.orchestrator import prepare_analysis_workspace

    paths = prepare_analysis_workspace(username, analysis_id)
    _clear_overlay_debug_dir(paths, unit_id)
    cur_path, prev_path = _overlay_item_paths(paths, unit_id)
    items = []
    prev_item = _overlay_file_to_payload(prev_path)
    cur_item = _overlay_file_to_payload(cur_path)
    if prev_item:
        items.append(prev_item)
    if cur_item:
        items.append(cur_item)
    return items


def get_ci_overlay_item(username: str, analysis_id: str, unit_id: str) -> Optional[Dict[str, Any]]:
    from app_chat.ci.orchestrator import _load_existing_layer, prepare_analysis_workspace

    paths = prepare_analysis_workspace(username, analysis_id)
    _clear_overlay_debug_dir(paths, unit_id)
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
    layer = _ensure_overlay_layer(paths, manifest, r_layer)
    current = next((item for item in (layer.get('items') or []) if isinstance(item, dict) and item.get('unit_id') == unit_id), None)
    if not current:
        return None
    return _overlay_item_to_response(paths, current)


def _save_overlay_snapshot(paths: Dict[str, str], unit_id: str, overlay_img,
                          layer_images: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]], str, Dict[str, Any]]:
    cur_path, prev_path = _overlay_item_paths(paths, unit_id)
    os.makedirs(os.path.dirname(cur_path), exist_ok=True)
    try:
        if os.path.isfile(cur_path):
            shutil.copy2(cur_path, prev_path)
    except Exception:
        pass
    for level in _OVERLAY_LEVELS:
        level_cur_path, level_prev_path = _overlay_layer_item_paths(paths, unit_id, level)
        try:
            if os.path.isfile(level_cur_path):
                shutil.copy2(level_cur_path, level_prev_path)
        except Exception:
            pass

    aggregate_source = overlay_img.convert('RGBA')
    if layer_images is None:
        next_layer_images = _split_overlay_image_by_levels(aggregate_source)
    else:
        next_layer_images = _coerce_overlay_layer_images(layer_images, aggregate_source.size)

    _saved_path, bbox, aggregate_regions, regions_version = _save_overlay_image_file(
        cur_path,
        aggregate_source,
        preserve_exact=True,
        fallback_bbox=_overlay_default_bbox(),
    )
    updated_at = _now_iso()
    layers_state: Dict[str, Dict[str, Any]] = {}
    for level in _OVERLAY_LEVELS:
        level_cur_path, _level_prev_path = _overlay_layer_item_paths(paths, unit_id, level)
        _saved_level_path, level_bbox, level_regions, level_version = _save_overlay_image_file(
            level_cur_path,
            next_layer_images[level],
            preserve_exact=True,
            overlay_level=level,
        )
        layers_state[level] = _build_overlay_layer_state(level, level_bbox, level_regions, level_version, updated_at)

    regions = _merge_overlay_regions_from_layers(layers_state) or aggregate_regions
    return cur_path, bbox, regions, regions_version, layers_state


def _encode_overlay_png_exact_bytes(overlay_img, fast: bool = False):
    from PIL import Image

    src = overlay_img.convert('RGBA')
    buf = io.BytesIO()
    if fast:
        src.save(buf, format='PNG', optimize=False, compress_level=3)
        return buf.getvalue(), src
    src.save(buf, format='PNG', optimize=True)
    data = buf.getvalue()
    exact = Image.open(io.BytesIO(data)).convert('RGBA')
    return data, exact


def _prepare_overlay_write_payload(overlay_img, preserve_exact: bool = False,
                                   skip_palette_normalize: bool = False,
                                   fast_encode: bool = False) -> Tuple[bytes, Any]:
    source = overlay_img.convert('RGBA')
    analysis_overlay = source if skip_palette_normalize else _normalize_overlay_palette(source)
    if preserve_exact:
        if fast_encode:
            buf = io.BytesIO()
            source.save(buf, format='PNG', optimize=False, compress_level=3)
            data = buf.getvalue()
        else:
            data, _written_overlay = _encode_overlay_png_exact_bytes(source)
        if len(data) > 2200000:
            data, _written_overlay = _encode_overlay_png_capped_bytes(source, max_bytes=2200000)
        return data, analysis_overlay

    data, _written_overlay = _encode_overlay_png_capped_bytes(source, max_bytes=2200000)
    return data, analysis_overlay


def _save_overlay_to_target(paths: Dict[str, str], unit_id: str, overlay_img, target: str,
                            preserve_exact: bool = False, overlay_level: str = '',
                            regions_override: Optional[List[Dict[str, Any]]] = None) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]], str, Dict[str, Any]]:
    save_t0 = time.perf_counter()
    cur_path, prev_path = _overlay_item_paths(paths, unit_id)
    normalized_target = 'prev' if str(target).strip().lower() == 'prev' else 'current'
    normalized_level = _normalize_overlay_level(overlay_level)
    source_image = overlay_img.convert('RGBA')
    manual_fast = regions_override is not None and not normalized_level

    if normalized_level:
        layer_images = _load_overlay_level_images(paths, unit_id, normalized_target)
        layer_images[normalized_level] = source_image
        base_size = source_image.size
    elif manual_fast:
        build_t0 = time.perf_counter()
        base_size = source_image.size
        aggregate_image = source_image
        layer_images = _build_manual_save_layer_images(base_size, regions_override)
        _ci_overlay_timing_log(
            '_save_overlay_to_target manual_fast_path',
            build_t0,
            f'size={base_size[0]}x{base_size[1]} regions={len(regions_override)}',
        )
    else:
        split_t0 = time.perf_counter()
        layer_images = _split_overlay_image_by_levels(source_image)
        base_size = source_image.size
        _ci_overlay_timing_log('_save_overlay_to_target split_by_levels', split_t0, f'size={base_size[0]}x{base_size[1]}')

    layer_images = _coerce_overlay_layer_images(layer_images, base_size)

    if manual_fast:
        pass
    else:
        compose_t0 = time.perf_counter()
        aggregate_image = _compose_overlay_level_images(layer_images, size=base_size)
        _ci_overlay_timing_log('_save_overlay_to_target compose_aggregate', compose_t0)
    out_path = prev_path if normalized_target == 'prev' else cur_path
    _saved_path, bbox, aggregate_regions, regions_version = _save_overlay_image_file(
        out_path,
        aggregate_image,
        preserve_exact=bool(preserve_exact or normalized_level),
        fallback_bbox=_overlay_default_bbox(),
        regions_override=regions_override,
        timing_label='aggregate',
        fast_manual=manual_fast,
    )

    updated_at = _now_iso()
    layers_state: Dict[str, Dict[str, Any]] = {}
    for level in _OVERLAY_LEVELS:
        level_cur_path, level_prev_path = _overlay_layer_item_paths(paths, unit_id, level)
        level_path = level_prev_path if normalized_target == 'prev' else level_cur_path
        level_regions = [
            region for region in (regions_override or [])
            if _normalize_overlay_level(region.get('level')) == level
        ] if manual_fast else None
        skip_level_write = bool(
            manual_fast
            and not level_regions
            and os.path.isfile(level_path)
        )
        _saved_level_path, level_bbox, level_regions, level_version = _save_overlay_image_file(
            level_path,
            layer_images[level],
            preserve_exact=True,
            overlay_level=level,
            regions_override=regions_override,
            timing_label=f'layer_{level}',
            fast_manual=manual_fast,
            skip_write=skip_level_write,
        )
        layers_state[level] = _build_overlay_layer_state(level, level_bbox, level_regions, level_version, updated_at)

    regions = _merge_overlay_regions_from_layers(layers_state) or aggregate_regions
    _ci_overlay_timing_log(
        '_save_overlay_to_target total',
        save_t0,
        f'unit={unit_id} regions={len(regions)} override={"yes" if regions_override is not None else "no"} manual_fast={manual_fast}',
    )
    return out_path, bbox, regions, regions_version, layers_state


def _load_ci_context(username: str, analysis_id: str, unit_id: str, skip_overlay_ensure: bool = False):
    from app_chat.ci.orchestrator import _load_existing_layer, prepare_analysis_workspace

    ctx_t0 = time.perf_counter()
    paths = prepare_analysis_workspace(username, analysis_id)
    _ci_overlay_timing_log('_load_ci_context prepare_workspace', ctx_t0)
    load_t0 = time.perf_counter()
    manifest = _load_existing_layer(paths['manifest']) or {}
    d_layer = _load_existing_layer(paths['d_layer']) or {}
    m_layer = _load_existing_layer(paths['m_layer']) or {}
    t_layer = _load_existing_layer(paths['t_layer']) or {}
    _ci_overlay_timing_log('_load_ci_context load_layers', load_t0)
    r_t0 = time.perf_counter()
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
    _ci_overlay_timing_log('_load_ci_context ensure_r_layer_items', r_t0)
    overlay_t0 = time.perf_counter()
    if skip_overlay_ensure:
        overlay_layer = _load_overlay_layer_raw(paths)
        _ci_overlay_timing_log('_load_ci_context load_overlay_layer_raw', overlay_t0)
    else:
        overlay_layer = _ensure_overlay_layer(paths, manifest, r_layer)
        _ci_overlay_timing_log('_load_ci_context ensure_overlay_layer', overlay_t0)

    r_item = next((item for item in (r_layer.get('items') or []) if isinstance(item, dict) and item.get('unit_id') == unit_id), None)
    if not r_item:
        raise ValueError(f'未找到 unit_id={unit_id} 对应的复现图页项')

    overlay_item = next((item for item in (overlay_layer.get('items') or []) if isinstance(item, dict) and item.get('unit_id') == unit_id), None)
    if not overlay_item:
        raise ValueError(f'未找到 unit_id={unit_id} 对应的覆盖层页项')

    reproduction_path = (r_item.get('reproduction_path') or '').strip()
    if not reproduction_path:
        raise ValueError('当前页尚无复现图，请先生成复现图')
    repro_abs = os.path.normpath(os.path.join(paths['root'], reproduction_path))
    if not os.path.isfile(repro_abs):
        raise ValueError('当前页复现图文件不存在，请先重新生成复现图')
    _ci_overlay_timing_log('_load_ci_context total', ctx_t0, f'unit={unit_id}')
    return paths, manifest, r_layer, r_item, overlay_item, repro_abs


def _resolve_unit_sketch_abs_path(paths: Dict[str, str], manifest: Dict[str, Any], unit_id: str, r_item: Dict[str, Any], repro_abs: str) -> str:
    # 优先用 r_item 里的 asset_abs_path（若存在且可读）
    candidate = str((r_item or {}).get('asset_abs_path') or '').strip()
    if candidate and os.path.isfile(candidate):
        return os.path.normpath(candidate)
    # 再回落到 manifest input_units 的 asset_path
    for unit in (manifest.get('input_units') or []):
        if not isinstance(unit, dict):
            continue
        if str(unit.get('unit_id') or '').strip() != str(unit_id or '').strip():
            continue
        asset_rel = str(unit.get('asset_path') or '').strip()
        if not asset_rel:
            break
        abs_path = os.path.normpath(os.path.join(paths['root'], asset_rel))
        if os.path.isfile(abs_path):
            return abs_path
        break
    # 最后兜底，保持现状可用
    return repro_abs


def _build_tm_context_text(iter_context: Dict[str, Any]) -> str:
    lines = [
        '【T层高价值理解补充】',
        iter_context.get('t_focus_text', '') or '（空）',
        '',
        '【M层主要内容摘要】',
        iter_context.get('main_content', '') or '（空）',
        '',
        '【M层版面区域】',
        iter_context.get('layout_regions_text', '') or '（空）',
        '',
        '【阅读顺序】',
        iter_context.get('reading_order', '') or '（空）',
        '',
        '【手写/印刷层关系】',
        iter_context.get('handwriting_printing_relation', '') or '（空）',
        '',
        '【批注关系】',
        iter_context.get('annotation_section', '') or '（空）',
        '',
        '【与前图连续关系】',
        iter_context.get('continuity_text', '') or '（空）',
        '',
        '【M层复核】',
        iter_context.get('m_verification_text', '') or '（空）',
    ]
    return '\n'.join(lines)


def _build_ci_overlay_prompt_body(iter_context: Dict[str, Any], include_tm_context: bool) -> str:
    if include_tm_context:
        return _build_tm_context_text(iter_context)
    return '（本次不附带 T/M 理解文本，请仅根据图像内容完成 DMT 微版面化输出。）'


def _build_overlay_generation_level_hint(overlay_level: str) -> str:
    normalized_level = _normalize_overlay_level(overlay_level)
    if not normalized_level:
        return ''
    if normalized_level == 'd':
        return (
            '【本次层级限定】\n'
            '只生成 D 层红色闭合框线，不输出任何 M 层蓝框线、T 层紫框线，也不要输出任何标签、序号、角标或色块。\n'
            '【线条质量（红框）】每条红框必须轮廓清晰、一笔连贯、首尾闭合，禁止中途断裂、淡化消失、虚边或与白底对比度过低；'
            '线宽约 1.5px 且尽量均匀；拐角转折清晰可辨，相邻框线勿糊成一团。\n'
        )
    if normalized_level == 'm':
        return '【本次层级限定】\n只生成 M 层蓝色闭合框线，不输出任何 D 层红框线、T 层紫框线，也不要输出任何标签、序号、角标或色块。\n'
    return '【本次层级限定】\n只生成 T 层紫色闭合框线，不输出任何 D 层红框线、M 层蓝框线，也不要输出任何标签、序号、角标或色块。\n'


def _build_overlay_generation_label_rule(overlay_level: str) -> str:
    return '不要生成任何 D/M/T 标签、序号、角标、字母块或纯色定位块；整张图中只保留红/蓝/紫三类闭合框线。'


def _extract_overlay_section(text: str, header: str, next_headers: List[str]) -> str:
    source = str(text or '')
    start = source.find(header)
    if start < 0:
        return ''
    end = len(source)
    for marker in next_headers:
        pos = source.find(marker, start + len(header))
        if pos >= 0:
            end = min(end, pos)
    return source[start:end].strip()


def _build_single_level_overlay_requirement(instruction_text: str, overlay_level: str,
                                            coarse_layout: bool = False) -> str:
    """把 DMT 合并说明剥离为单层说明，避免并行分层生图时跨层噪声干扰。"""
    normalized_level = _normalize_overlay_level(overlay_level)
    raw = str(instruction_text or '').strip()
    if not raw or not normalized_level:
        return raw

    d_block = _extract_overlay_section(raw, '【D级·红框】', ['【M级·蓝框】', '【T级·紫框】'])
    m_block = _extract_overlay_section(raw, '【M级·蓝框】', ['【T级·紫框】'])
    t_block = _extract_overlay_section(raw, '【T级·紫框】', [])

    if normalized_level == 'd':
        if coarse_layout:
            level_header = (
                '【D级·红框】粗粒度优先（本页印刷体或留白较多，手写占比偏低）：每个相对独立的手写簇或印刷内容块，'
                '尽量用 1～2 个红框覆盖即可；同一行/同一段连续手写若关系密切，可合并为单个 D 框；印刷体标题、正文区也可合并成较少的大块红框，'
                '但必须保证整张图所有可见正文与手写区域都被红框覆盖到，禁止遗漏。'
            )
            level_block = d_block or (
                '【D级·红框】\n- D1：请根据图像补全粗粒度 D 清单（每簇 1～2 框），保证全图覆盖、无遗漏，框线闭合完整。'
            )
        else:
            level_header = '【D级·红框】最小颗粒，每个独立格子各一框，每个词/短语/对象作为一个D框（宁可偏细勿粗）：'
            level_block = d_block or '【D级·红框】\n- D1：请根据图像补全具体 D 清单，并保证最小颗粒闭合包裹。'
        color_rule = '【颜色规则】仅保留 D=红框(#E53935,1.5px)；整张图只输出红色闭合框线，不生成任何标签、序号、角标、字母块或纯色定位块。'
        tail_rule = '我只需要将上述红色框线生成出来，底图内容（所有文字、线条、颜色等）全部清除不要；你生成出的图里应该只有红色闭合框线，不要保留原图黑字正文、底色，也不要额外生成任何标签、序号、字母、角标或色块。'
    elif normalized_level == 'm':
        level_header = '【M级·蓝框】中等颗粒，按版本/功能区块合并：'
        level_block = m_block or '【M级·蓝框】\n- M1：请根据图像补全中等粒度 M 清单，并给出位置或坐标范围。'
        color_rule = '【颜色规则】仅保留 M=蓝框(#1E88E5,1.5px)；整张图只输出蓝色闭合框线，不生成任何标签、序号、角标、字母块或纯色定位块。'
        tail_rule = '我只需要将上述蓝色框线生成出来，底图内容（所有文字、线条、颜色等）全部清除不要；你生成出的图里应该只有蓝色闭合框线，不要保留原图黑字正文、底色，也不要额外生成任何标签、序号、字母、角标或色块。'
    else:
        level_header = '【T级·紫框】最大颗粒，全局架构：'
        level_block = t_block or '【T级·紫框】\n- T0：请根据图像补全全局结构层清单，并给出位置或坐标范围。'
        color_rule = '【颜色规则】仅保留 T=紫框(#8E24AA,1.5px)；整张图只输出紫色闭合框线，不生成任何标签、序号、角标、字母块或纯色定位块。'
        tail_rule = '我只需要将上述紫色框线生成出来，底图内容（所有文字、线条、颜色等）全部清除不要；你生成出的图里应该只有紫色闭合框线，不要保留原图黑字正文、底色，也不要额外生成任何标签、序号、字母、角标或色块。'

    style_rule = '风格严格按照参考图，仅参考对应颜色框线的样式与层级组织方式，不参考任何标签样式。'
    return '\n'.join([
        '原图是一张手稿图，图中应该标注对应层级的闭合框线，具体如下：',
        '',
        color_rule,
        '',
        level_header,
        level_block,
        '',
        tail_rule,
        '',
        style_rule,
    ]).strip()


def _build_overlay_generation_structure_rules(overlay_level: str, coarse_layout: bool = False) -> List[str]:
    normalized_level = _normalize_overlay_level(overlay_level)
    rules: List[str] = []
    if normalized_level in ('', 'd'):
        if coarse_layout:
            rules.append(
                'D 级红框采用偏粗粒度：同一手写簇或印刷内容块优先用 1～2 个红框覆盖；禁止遗漏版面内容，避免无必要细碎拆分；框线闭合并完整包住目标。'
            )
        else:
            rules.append(
                'D 级红框保持最小颗粒：每个独立格子、词/短语、圈注对象或独立笔画簇应尽量单独成框，框线必须闭合并完整包住目标，勿画无内容空红框。'
            )
        rules.append(
            'D 层输出优先保证线条可读性：红框边线须连续、闭合、边界清晰，避免出现肉眼难以辨认的断裂线、断续虚线或与底色融为一体的浅线。'
        )
    if normalized_level in ('', 'm'):
        rules.append(
            'M 级蓝框粒度保持中等（Middle）；每个 M 必须是闭合、连续、清晰可辨的完整蓝框，优先使用规整直线边界包住对应内容区。原图中的手绘长横/长竖/长斜/曲线分隔只能作为分区参考，不能直接拿来当蓝框边界，更不能沿断裂手绘线或开放曲线走形。'
        )
    if normalized_level in ('', 't'):
        rules.append('T 级紫框表示较大结构层；每个 T 必须是闭合、连续的完整包裹框，保持 T⊃M⊃D 的层级包裹关系。')
    return rules


def run_ci_sketch_handwriting_estimate_and_persist(username: str, analysis_id: str, unit_id: str) -> Dict[str, Any]:
    """仅估算原草图手写区域占比并写入 overlay_layer（供单独按钮调用；DMT 流式不再内置此步）。"""
    paths, manifest, r_layer, r_item, _overlay, repro_abs = _load_ci_context(username, analysis_id, unit_id)
    sketch_abs = _resolve_unit_sketch_abs_path(paths, manifest, unit_id, r_item, repro_abs)
    hw_ratio, hw_note = _estimate_sketch_handwriting_area_ratio_qwen(sketch_abs)
    coarse_layout = bool(hw_ratio < 0.6)
    _update_overlay_item(
        paths,
        manifest,
        r_layer,
        unit_id,
        lambda cur: {
            **cur,
            'ci_sketch_handwriting_area_ratio': round(float(hw_ratio), 4),
            'ci_dmt_coarse_layout': coarse_layout,
            'ci_sketch_handwriting_estimate_note': _truncate_text(hw_note, 1200),
            'updated_at': _now_iso(),
        },
    )
    _write_overlay_debug_text(
        paths,
        unit_id,
        'dmt_handwriting_metrics',
        f'handwriting_area_ratio={hw_ratio}\ncoarse_layout={1 if coarse_layout else 0}\nnote={hw_note}',
    )
    return {
        'handwriting_area_ratio': round(float(hw_ratio), 4),
        'coarse_layout': coarse_layout,
        'estimate_note': _truncate_text(hw_note, 1200),
    }


def stream_ci_dmt_overlay_prompt(username: str, analysis_id: str, unit_id: str, include_tm_context: bool = True):
    paths, manifest, r_layer, r_item, overlay_item, repro_abs = _load_ci_context(username, analysis_id, unit_id)
    _clear_overlay_debug_dir(paths, unit_id)
    sketch_abs = _resolve_unit_sketch_abs_path(paths, manifest, unit_id, r_item, repro_abs)
    with open(sketch_abs, 'rb') as f:
        sketch_b64 = base64.b64encode(f.read()).decode('utf-8')

    iter_context = _normalize_reproduction_iter_context(r_item.get('iter_context'))
    prompt_title = '当前单图理解补充'
    prompt_body = _build_ci_overlay_prompt_body(iter_context, bool(include_tm_context))
    _write_overlay_debug_text(
        paths,
        unit_id,
        'dmt_prompt_request',
        f'include_tm_context={1 if include_tm_context else 0}\n\n【标题】\n{prompt_title}\n\n【正文】\n{prompt_body}',
    )

    def _stream():
        image_data_url = f'data:image/png;base64,{sketch_b64}'
        # 粗/细粒度完全由 overlay 已保存的 ci_dmt_coarse_layout 决定（先点「手写占比估算」写入；未估算则视为细粒度，与手写≥60%一致）
        coarse_layout = bool((overlay_item or {}).get('ci_dmt_coarse_layout'))
        user_prefix = CI_DMT_OVERLAY_USER_PREFIX_COARSE if coarse_layout else CI_DMT_OVERLAY_USER_PREFIX

        # 手写占比 &lt;60%（粗粒度）：仅一次 Gemini 流式，不做初稿结构重试，不做第二遍 D 段复核
        if coarse_layout:
            draft_text = _collect_ci_dmt_overlay_first_pass(
                image_data_url, prompt_title, prompt_body, user_prefix=user_prefix,
            ).strip()
            output_text = _ensure_dmt_fixed_suffix(draft_text)
            _write_overlay_debug_text(paths, unit_id, 'dmt_prompt_mode', 'coarse:single_gemini_no_refine')
            if output_text:
                _write_overlay_debug_text(paths, unit_id, 'dmt_prompt_output', output_text)
                for i in range(0, len(output_text), 512):
                    yield output_text[i:i + 512].encode('utf-8')
            else:
                hint = (
                    '[DMT] 粗粒度单次调用未生成有效文本，请重试「DMT微版面化」或检查服务端日志。\n'
                    '（粗粒度模式：仅 1 次 Gemini、无 D 段复核）'
                )
                yield hint.encode('utf-8')
            return

        # 手写≥60%（细粒度）：保持原逻辑——初稿可多次重试 + 第二遍仅 D 段复核
        max_first = max(1, _DMT_FIRST_PASS_MAX_ATTEMPTS)
        draft_text = ''
        structure_ok = False
        for attempt in range(1, max_first + 1):
            draft_text = _collect_ci_dmt_overlay_first_pass(
                image_data_url, prompt_title, prompt_body, user_prefix=user_prefix,
            )
            structure_ok = _dmt_instruction_structure_complete(draft_text)
            if structure_ok:
                if attempt > 1:
                    print(f'[ci_overlay] DMT 初稿结构完整（第 {attempt}/{max_first} 次尝试）')
                break
            print(
                f'[ci_overlay] DMT 初稿结构不完整（缺 D/M/T 顺序段或条目），'
                f'第 {attempt}/{max_first} 次；{"将重试第一遍" if attempt < max_first else "已达上限，跳过 D 段复核"}'
            )
            _write_overlay_debug_text(
                paths,
                unit_id,
                f'dmt_prompt_draft_incomplete_try{attempt}',
                _truncate_text(draft_text, 24000) or '(empty)',
            )
            if attempt < max_first:
                time.sleep(1.0 * attempt)

        draft_text = _ensure_dmt_fixed_suffix(draft_text)
        final_text = ''
        if structure_ok:
            final_text = _ci_dmt_refine_d_coverage(
                image_data_url=image_data_url,
                draft_instruction=draft_text,
                card_title=prompt_title,
                card_content=prompt_body,
                coarse_layout=False,
            ).strip()
            final_text = _ensure_dmt_fixed_suffix(final_text)
        else:
            print('[ci_overlay] DMT 初稿多次仍缺完整 M/T 结构，不调用第二遍（仅 D 复核），避免误伤正文')

        output_text = (final_text or draft_text or '').strip()
        if output_text:
            _write_overlay_debug_text(paths, unit_id, 'dmt_prompt_output', output_text)
            if not structure_ok:
                _write_overlay_debug_text(
                    paths,
                    unit_id,
                    'dmt_prompt_incomplete_note',
                    'structure_incomplete_after_retries: refine_skipped',
                )
            for i in range(0, len(output_text), 512):
                yield output_text[i:i + 512].encode('utf-8')
        else:
            hint = (
                '[DMT] 未生成有效文本：Gemini 流式与 D 段复核均为空，请查看服务端日志或重试。\n'
                '（当前为细粒度模式；粗粒度请先点击「手写占比估算」且手写占比需小于 60%）'
            )
            yield hint.encode('utf-8')

    return _stream()


def _build_overlay_generation_instruction(iter_context: Dict[str, Any], instruction_text: str,
                                          include_tm_context: bool, overlay_level: str = '',
                                          coarse_layout: bool = False) -> str:
    user_block = ''
    if instruction_text and instruction_text.strip():
        normalized_level = _normalize_overlay_level(overlay_level)
        effective_instruction = (
            _build_single_level_overlay_requirement(instruction_text, normalized_level, coarse_layout=coarse_layout)
            if normalized_level else instruction_text
        )
        user_block = f'\n【用户当前填写的覆盖层要求】\n{effective_instruction.strip()[:5000]}\n'
    tm_block = ''
    if include_tm_context:
        tm_block = f'\n【当前 T/M 层理解补充】\n{_build_tm_context_text(iter_context)}\n'
    level_block = _build_overlay_generation_level_hint(overlay_level)
    output_rule = '只输出红/蓝/紫三类 D/M/T 闭合框线，不要输出任何标签、序号、字母、色块，不要画任何文字、原始线条、阴影、色块或任何其他颜色。'
    if _normalize_overlay_level(overlay_level):
        output_rule = '本次只输出指定层级的一种颜色闭合框线，其他层级不得出现；不要输出任何标签、序号、字母、色块，也不要画任何文字、原始线条、阴影、色块或任何其他颜色。'
    numbered_rules = [
        output_rule,
        _build_overlay_generation_label_rule(overlay_level),
        '颜色、线宽与层级关系，优先严格遵守【用户当前填写的覆盖层要求】中的描述；若其中未明确，默认沿用当前 DMT 微版面化要求中的红框/蓝框/紫框细线风格。',
        '背景必须纯白，边缘清晰，便于前端把白底视为透明进行叠加预览。',
        '若用户要求更细致的 D/M/T 拆分，优先遵守；若用户要求与当前 T/M 理解冲突，以当前图像结构和当前输入信息的交集为准。',
    ]
    numbered_rules.extend(_build_overlay_generation_structure_rules(overlay_level, coarse_layout=coarse_layout))
    rule_block = '\n'.join(f'{index}) {rule}' for index, rule in enumerate(numbered_rules, start=1))
    return f"""你是一个 DMT 覆盖层生成器。请基于输入的当前单图原草图，生成一张与输入图同宽高的 PNG 白底覆盖层，严格遵守：
{rule_block}
{level_block}{user_block}{tm_block}"""


def _generate_ci_overlay_image(sketch_abs: str, iter_context: Dict[str, Any], instruction_text: str,
                               reference_image_b64: Optional[str], reference_image_mime: str,
                               image_quality: str, include_tm_context: bool, overlay_level: str = '',
                               coarse_layout: bool = False):
    from PIL import Image

    base_im = Image.open(sketch_abs).convert('RGBA')
    bb = io.BytesIO()
    base_im.save(bb, format='PNG')
    repro_b64 = base64.b64encode(bb.getvalue()).decode('utf-8')
    instruction = _build_overlay_generation_instruction(
        iter_context, instruction_text, include_tm_context, overlay_level=overlay_level, coarse_layout=coarse_layout,
    )
    content_parts = [
        {'type': 'text', 'text': '【当前单图原草图】'},
        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{repro_b64}'}},
        {'type': 'text', 'text': instruction},
    ]
    native_parts = [
        {'text': '【当前单图原草图】'},
        {'inlineData': {'mimeType': 'image/png', 'data': repro_b64}},
        {'text': instruction},
    ]
    ref_b64 = (reference_image_b64 or '').strip()
    ref_mime = reference_image_mime or 'image/png'
    if not ref_b64:
        auto_ref_b64, auto_ref_mime = _load_overlay_style_reference_base64()
        if auto_ref_b64:
            ref_b64 = auto_ref_b64.strip()
            ref_mime = auto_ref_mime or ref_mime
    if ref_b64:
        ref = ref_b64
        ref_url = ref if ref.startswith('data:') else f'data:image/png;base64,{ref}'
        content_parts.append({'type': 'text', 'text': '【参考图】（仅参考框线组织方式和局部风格，不复制其内容）'})
        content_parts.append({'type': 'image_url', 'image_url': {'url': ref_url}})
        native_parts.append({'text': '【参考图】（仅参考框线组织方式和局部风格，不复制其内容）'})
        native_parts.append({'inlineData': {'mimeType': ref_mime, 'data': ref}})

    if str(image_quality).strip().lower() == 'high':
        b64 = _gemini_native_generate_image_from_parts(GEMINI_IMAGE_API_KEY_HIGH, native_parts, image_size='4K')
    else:
        client = OpenAI(
            api_key=GEMINI_IMAGE_API_KEY_SINGLE,
            base_url=GEMINI_IMAGE_BASE_URL,
            default_headers={'x-foo': 'true'},
            timeout=GEMINI_IMAGE_TIMEOUT,
        )
        response = client.chat.completions.create(
            model=_overlay_gemini_image_model(),
            messages=[{'role': 'user', 'content': content_parts}],
            temperature=0.25,
            max_tokens=8192,
        )
        txt = response.choices[0].message.content
        b64 = _extract_base64_from_response(txt) if txt else None
    if not b64:
        raise RuntimeError('模型未返回覆盖层图片')
    overlay = _pil_from_response_base64(b64)
    if overlay is None:
        raise RuntimeError('覆盖层图片解码失败')
    overlay = overlay.convert('RGBA')
    if overlay.size != base_im.size:
        overlay = overlay.resize(base_im.size, _resample_lanczos())
    return overlay


def _overlay_include_tm_context_for_level(level: str, include_tm_context: bool) -> bool:
    """并行分层生图：D 红框仅依赖「生成覆盖层要求」中的 D 段 + 原草图，避免 T/M 长文本干扰细红框质量；M/T 仍可按勾选附带 T/M 理解。"""
    if _normalize_overlay_level(level) == 'd':
        return False
    return bool(include_tm_context)


def _generate_ci_overlay_level_images(sketch_abs: str, iter_context: Dict[str, Any], instruction_text: str,
                                      reference_image_b64: Optional[str], reference_image_mime: str,
                                      image_quality: str, include_tm_context: bool,
                                      coarse_layout: bool = False) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(_OVERLAY_LEVELS)) as executor:
        future_to_level = {
            executor.submit(
                _generate_ci_overlay_image,
                sketch_abs,
                iter_context,
                instruction_text,
                reference_image_b64,
                reference_image_mime,
                image_quality,
                _overlay_include_tm_context_for_level(level, include_tm_context),
                level,
                coarse_layout,
            ): level
            for level in _OVERLAY_LEVELS
        }
        for future in as_completed(future_to_level):
            level = future_to_level[future]
            results[level] = future.result()
    return {level: results[level] for level in _OVERLAY_LEVELS if level in results}


def _iterate_ci_overlay_image(overlay_image_b64: str, instruction_text: str,
                              reference_image_b64: Optional[str], reference_image_mime: str,
                              image_quality: str):
    src = _pil_from_response_base64(overlay_image_b64)
    if src is None:
        raise RuntimeError('overlay image decode failed')
    src = src.convert('RGBA')
    src_bytes, src_comp = _encode_overlay_png_capped_bytes(src, max_bytes=2200000)
    src_b64 = base64.b64encode(src_bytes).decode('utf-8')
    user_block = ''
    if instruction_text and instruction_text.strip():
        user_block = f'\n【用户当前填写的覆盖层修改要求】\n{instruction_text.strip()[:5000]}\n'
    instruction = f"""你在迭代一张白底 DMT 覆盖层图片。请严格遵守：
1) 只能输出白底覆盖层，只保留 D/M/T 三类闭合框线，不得重新引入底图内容。
2) 颜色与线宽尽量保持当前覆盖层既有样式，并继续只使用红/蓝/紫三色的 D/M/T 闭合框线；不要输出任何标签、序号、字母、角标或色块。
3) 保持未被用户要求修改的区域尽量不变。
4) 除了红蓝紫三种框线外，不得出现其他颜色元素。
{user_block}
"""
    content_parts = [
        {'type': 'text', 'text': '【当前覆盖层】'},
        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{src_b64}'}},
        {'type': 'text', 'text': instruction},
    ]
    native_parts = [
        {'text': '【当前覆盖层】'},
        {'inlineData': {'mimeType': 'image/png', 'data': src_b64}},
        {'text': instruction},
    ]
    if reference_image_b64 and reference_image_b64.strip():
        ref = reference_image_b64.strip()
        ref_url = ref if ref.startswith('data:') else f'data:image/png;base64,{ref}'
        content_parts.append({'type': 'text', 'text': '【参考图】'})
        content_parts.append({'type': 'image_url', 'image_url': {'url': ref_url}})
        native_parts.append({'text': '【参考图】'})
        native_parts.append({'inlineData': {'mimeType': reference_image_mime or 'image/png', 'data': ref}})

    if str(image_quality).strip().lower() == 'high':
        out_b64 = _gemini_native_generate_image_from_parts(GEMINI_IMAGE_API_KEY_HIGH, native_parts, image_size='4K')
    else:
        client = OpenAI(
            api_key=GEMINI_IMAGE_API_KEY_SINGLE,
            base_url=GEMINI_IMAGE_BASE_URL,
            default_headers={'x-foo': 'true'},
            timeout=GEMINI_IMAGE_TIMEOUT,
        )
        response = client.chat.completions.create(
            model=_overlay_gemini_image_model(),
            messages=[{'role': 'user', 'content': content_parts}],
            temperature=0.25,
            max_tokens=8192,
        )
        txt = response.choices[0].message.content
        out_b64 = _extract_base64_from_response(txt) if txt else None
    if not out_b64:
        raise RuntimeError('模型未返回覆盖层图片')
    out = _pil_from_response_base64(out_b64)
    if out is None:
        raise RuntimeError('迭代覆盖层解码失败')
    out = out.convert('RGBA')
    if out.size != src_comp.size:
        out = out.resize(src_comp.size, _resample_lanczos())
    return out


def _call_ci_d_red_overlay_checker(card_image_b64: str, overlay_d_b64: str, instruction_text: str) -> str:
    """仅检查 D 层红框问题，输出规范化修正清单（或“没问题”）。"""
    client = _ci_dmt_gemini_client()
    system_text = (
        '你是覆盖层质检员，只检查 D 层红框。'
        '你只输出两种结果：'
        '1) 若无问题，仅输出“没问题”；'
        '2) 若有问题，仅输出“【修正清单】”与条目。'
    )
    user_text = (
        '任务：仅检查红框 D 层，不检查 M/T。\n'
        '检查项：\n'
        '1) 红框是否漏框、空框、明显偏移、未包住目标。\n'
        '2) **特别检查**：是否存在“有手写字迹但未加红框”的遗漏位置。\n'
        '3) 红框是否明显多框入无关内容。\n'
        '4) 红框是否存在不闭合、断裂或线条不清晰。\n'
        '输出格式：\n'
        '若无问题：仅输出“没问题”。\n'
        '若有问题：\n'
        '【修正清单】\n'
        '- [遗漏红框] 位置：...；现状：...；修改为：新增1个红框，包住...，框体范围...（绝对或相对位置）。\n'
        '- [位置偏差] 位置：...；现状：...；修改为：...\n'
        '每条必须可执行，位置需可定位。若是遗漏，必须写明该处应新增红框的数量（加几个）与每个红框大致范围/相对方位。\n'
        f'附加约束文本（可参考）：\n{(instruction_text or "").strip()[:4000]}'
    )
    content = [
        {'type': 'text', 'text': user_text},
        {'type': 'text', 'text': '【原草图】'},
        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{card_image_b64}'}},
        {'type': 'text', 'text': '【当前D层红框图】'},
        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{overlay_d_b64}'}},
    ]
    rsp = client.chat.completions.create(
        model=_overlay_dmt_gemini_model(),
        messages=[
            {'role': 'system', 'content': system_text},
            {'role': 'user', 'content': content},
        ],
        temperature=0.1,
        max_tokens=4096,
    )
    text = str((rsp.choices[0].message.content or '')).strip()
    return text or ''


def _postprocess_ci_overlay_from_card_helpers(paths: Dict[str, str], username: str, analysis_id: str, unit_id: str,
                                              sketch_abs: str, overlay_d, instruction_text: str,
                                              image_quality: str) -> Tuple[Any, Dict[str, Any], str]:
    _write_overlay_debug_image(paths, unit_id, 'overlay_d_raw', overlay_d)
    helper_cid = _ci_overlay_helper_cid(analysis_id, unit_id)
    det: Dict[str, Any] = {}
    check_text = ''
    try:
        det = _detect_overlay_red_boxes_for_pil(username, helper_cid, overlay_d)
        mask_path = os.path.join(_card_image_dir(username), det.get('mask_filename') or '')
        _copy_overlay_debug_file(paths, unit_id, 'overlay_d_redmask', mask_path)
        base_overlay = overlay_d.convert('RGBA')

        with open(sketch_abs, 'rb') as f:
            sketch_b64 = base64.b64encode(f.read()).decode('utf-8')
        inst_for_audit = ((instruction_text or '').strip() + '\n\n' if (instruction_text or '').strip() else '') + (
            '【CI D层红框硬约束】\n'
            '1. 只检查并修正 D 层红框，不处理 M/T。\n'
            '2. 红框必须闭合、连续、清晰，且应准确包住对应目标。\n'
            '3. 禁止生成任何标签、序号、角标、字母块或定位色块。'
        )
        _write_overlay_debug_text(paths, unit_id, 'overlay_d_audit_instruction', inst_for_audit)
        check_text = _call_ci_d_red_overlay_checker(
            card_image_b64=sketch_b64,
            overlay_d_b64=_overlay_pil_to_base64_png(base_overlay),
            instruction_text=inst_for_audit,
        )
        if check_text:
            _write_overlay_debug_text(paths, unit_id, 'overlay_d_audit_result', check_text)

        final_overlay = base_overlay
        if (check_text or '').strip() != '没问题':
            fix_instruction = ((instruction_text or '').strip() + '\n\n' if (instruction_text or '').strip() else '') + (
                '【Gemini检查结果（请优先修正）】\n'
                + (check_text or '请仅检查并修正 D 层红框的闭合性、连续性和框体位置，禁止生成任何标签或定位色块')
            )
            _write_overlay_debug_text(paths, unit_id, 'overlay_d_fix_instruction', fix_instruction)
            fixed = _iterate_overlay_test_layer_image(
                overlay_image_b64=_overlay_pil_to_base64_png(base_overlay),
                revision_instruction=fix_instruction,
                reference_image_b64=None,
                reference_image_mime='image/png',
                image_quality=image_quality,
                edit_region=None,
                card_image_b64=sketch_b64,
                card_image_label='原草图',
            )
            if fixed is not None:
                final_overlay = fixed.convert('RGBA')
                _write_overlay_debug_image(paths, unit_id, 'overlay_d_fixed', final_overlay)

        dark_ratio = _overlay_dark_neutral_pixel_ratio_rgba(final_overlay)
        cleanup_note = f'dark_ratio={dark_ratio:.4f}\ncleanup=skip'
        if dark_ratio > 0.018:
            final_overlay = _bleach_dark_neutral_pixels_on_overlay(final_overlay)
            cleanup_note = f'dark_ratio={dark_ratio:.4f}\ncleanup=bleach_dark_neutral'
        _write_overlay_debug_text(paths, unit_id, 'overlay_d_cleanup', cleanup_note)
        _write_overlay_debug_image(paths, unit_id, 'overlay_d_final', final_overlay)
        return final_overlay, det, check_text
    except Exception as ex:
        _write_overlay_debug_text(paths, unit_id, 'overlay_d_postprocess_error', str(ex))
        fallback = overlay_d.convert('RGBA')
        dark_ratio = _overlay_dark_neutral_pixel_ratio_rgba(fallback)
        if dark_ratio > 0.010:
            fallback = _bleach_overlay_ink_residual_pipeline(fallback)
        _write_overlay_debug_image(paths, unit_id, 'overlay_d_final', fallback)
        return fallback, det, check_text


def generate_ci_overlay(username: str, analysis_id: str, unit_id: str, instruction_text: str,
                        reference_image_b64: Optional[str], reference_image_mime: str,
                        image_quality: str, include_tm_context: bool = True,
                        dmt_generated: bool = False) -> Dict[str, Any]:
    paths, manifest, r_layer, r_item, overlay_item, repro_abs = _load_ci_context(username, analysis_id, unit_id)
    sketch_abs = _resolve_unit_sketch_abs_path(paths, manifest, unit_id, r_item, repro_abs)
    _clear_overlay_debug_dir(paths, unit_id)
    iter_context = _normalize_reproduction_iter_context(r_item.get('iter_context'))
    tm_text = _build_tm_context_text(iter_context) if include_tm_context else ''
    _write_overlay_debug_text(
        paths,
        unit_id,
        'overlay_generation_request',
        '\n'.join([
            f'include_tm_context={1 if include_tm_context else 0}',
            f'dmt_generated={1 if dmt_generated else 0}',
            f'image_quality={image_quality}',
            f'reference_image_provided={1 if (reference_image_b64 and str(reference_image_b64).strip()) else 0}',
            '',
            '【覆盖层要求】',
            (instruction_text or '').strip(),
            '',
            '【T/M理解补充】',
            tm_text or '（未附带）',
        ]),
    )
    coarse_layout = bool((overlay_item or {}).get('ci_dmt_coarse_layout'))
    overlay_layers = _generate_ci_overlay_level_images(
        sketch_abs=sketch_abs,
        iter_context=iter_context,
        instruction_text=instruction_text,
        reference_image_b64=reference_image_b64,
        reference_image_mime=reference_image_mime,
        image_quality=image_quality,
        include_tm_context=bool(include_tm_context),
        coarse_layout=coarse_layout,
    )
    overlay = _compose_overlay_level_images(overlay_layers)
    final_layer_images = _coerce_overlay_layer_images(overlay_layers, overlay.size)
    final_overlay = overlay
    det: Dict[str, Any] = {}
    # 细粒度（手写≥60%）：DMT 路径下对 D 层做红框质检 + 可能迭代修图。粗粒度仅并行三层生图后直接结束。
    if dmt_generated and not coarse_layout:
        postprocessed_d_overlay, det, _check_text = _postprocess_ci_overlay_from_card_helpers(
            paths=paths,
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
            sketch_abs=sketch_abs,
            overlay_d=final_layer_images.get('d') or _filter_overlay_image_to_level(overlay, 'd'),
            instruction_text=instruction_text,
            image_quality=image_quality,
        )
        final_layer_images['d'] = _filter_overlay_image_to_level(postprocessed_d_overlay, 'd')
        final_overlay = _compose_overlay_level_images(final_layer_images, size=postprocessed_d_overlay.size)
    elif dmt_generated and coarse_layout:
        _write_overlay_debug_text(
            paths,
            unit_id,
            'overlay_skip_d_postprocess',
            'coarse_layout:parallel_dmt_only_no_d_audit_iterate',
        )
    _cur_path, bbox, regions, regions_version, layers_state = _save_overlay_snapshot(
        paths,
        unit_id,
        final_overlay,
        final_layer_images,
    )
    updated = _update_overlay_item(
        paths,
        manifest,
        r_layer,
        unit_id,
        lambda current: {
            **current,
            'status': 'ready',
            'instruction_text': _truncate_text(instruction_text or '', 12000),
            'overlay_bbox': bbox,
            'regions': regions,
            'regions_version': regions_version,
            'layers': layers_state,
            'updated_at': _now_iso(),
            'error': '',
            'include_tm_context': bool(include_tm_context),
        },
    )
    payload = _overlay_item_to_response(paths, updated)
    if det:
        payload['auto_detect'] = det
    return payload


def iterate_ci_overlay(username: str, analysis_id: str, unit_id: str, overlay_image: Optional[str],
                       instruction_text: str, reference_image_b64: Optional[str], reference_image_mime: str,
                       image_quality: str) -> Dict[str, Any]:
    paths, manifest, r_layer, _r_item, _overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
    _clear_overlay_debug_dir(paths, unit_id)
    if overlay_image and isinstance(overlay_image, str) and overlay_image.strip():
        overlay_base = overlay_image.strip()
    else:
        cur_path, _prev_path = _overlay_item_paths(paths, unit_id)
        if not os.path.isfile(cur_path):
            raise ValueError('当前页尚无覆盖层，请先生成覆盖层')
        with open(cur_path, 'rb') as f:
            overlay_base = 'data:image/png;base64,' + base64.b64encode(f.read()).decode('utf-8')
    overlay = _iterate_ci_overlay_image(
        overlay_image_b64=overlay_base,
        instruction_text=instruction_text,
        reference_image_b64=reference_image_b64,
        reference_image_mime=reference_image_mime,
        image_quality=image_quality,
    )
    _cur_path, bbox, regions, regions_version, layers_state = _save_overlay_snapshot(
        paths,
        unit_id,
        overlay,
        _split_overlay_image_by_levels(overlay),
    )
    updated = _update_overlay_item(
        paths,
        manifest,
        r_layer,
        unit_id,
        lambda current: {
            **current,
            'status': 'ready',
            'instruction_text': _truncate_text(instruction_text or current.get('instruction_text', ''), 12000),
            'overlay_bbox': bbox,
            'regions': regions,
            'regions_version': regions_version,
            'layers': layers_state,
            'updated_at': _now_iso(),
            'error': '',
        },
    )
    return _overlay_item_to_response(paths, updated)


def save_ci_overlay_file(username: str, analysis_id: str, unit_id: str, overlay_image: str, target: str = 'current',
                         preserve_exact: bool = False, overlay_level: str = '',
                         regions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    save_t0 = time.perf_counter()
    print(
        f'[CI overlay save] save_ci_overlay_file start unit={unit_id} analysis={analysis_id} '
        f'preserve_exact={preserve_exact} regions_payload={len(regions) if isinstance(regions, list) else 0}',
        flush=True,
    )
    if not overlay_image or not isinstance(overlay_image, str):
        raise ValueError('缺少 overlay_image')
    manual_save = isinstance(regions, list)
    paths, manifest, r_layer, _r_item, _overlay_item, _repro_abs = _load_ci_context(
        username,
        analysis_id,
        unit_id,
        skip_overlay_ensure=manual_save,
    )
    clear_t0 = time.perf_counter()
    _clear_overlay_debug_dir(paths, unit_id)
    _ci_overlay_timing_log('clear_overlay_debug_dir', clear_t0)
    overlay_b64 = overlay_image.strip()
    if overlay_b64.startswith('data:') and 'base64,' in overlay_b64:
        overlay_b64 = overlay_b64.split('base64,', 1)[-1]
    decode_t0 = time.perf_counter()
    pil = _pil_from_response_base64(overlay_b64)
    if pil is None:
        raise ValueError('overlay image decode failed')
    _ci_overlay_timing_log(
        'decode_base64_image',
        decode_t0,
        f'size={pil.width}x{pil.height} b64_len={len(overlay_b64)}',
    )
    normalized_level = _normalize_overlay_level(overlay_level)
    regions_override = None
    if preserve_exact and regions is not None:
        norm_t0 = time.perf_counter()
        regions_override = _normalize_manual_regions_payload(regions, pil.width, pil.height)
        _ci_overlay_timing_log(
            'normalize_manual_regions',
            norm_t0,
            f'input={len(regions)} output={len(regions_override or [])}',
        )
    out_path, bbox, regions, regions_version, layers_state = _save_overlay_to_target(
        paths,
        unit_id,
        pil,
        'prev' if target == 'prev' else 'current',
        preserve_exact=bool(preserve_exact),
        overlay_level=normalized_level,
        regions_override=regions_override,
    )
    updated = _update_overlay_item(
        paths,
        manifest,
        r_layer,
        unit_id,
        lambda current: {
            **current,
            'status': 'ready' if target != 'prev' else current.get('status', 'not_started'),
            'overlay_bbox': bbox if target != 'prev' else current.get('overlay_bbox'),
            'regions': regions if target != 'prev' else current.get('regions', []),
            'regions_version': regions_version if target != 'prev' else current.get('regions_version', ''),
            'layers': layers_state if target != 'prev' else current.get('layers', {}),
            'updated_at': _now_iso(),
            'error': '',
        },
        skip_ensure=regions_override is not None,
    )
    resp_t0 = time.perf_counter()
    payload = _overlay_item_to_response(paths, updated)
    _ci_overlay_timing_log('_overlay_item_to_response', resp_t0)
    payload['target'] = target
    payload['overlay_level'] = normalized_level
    payload['overlay_path'] = _overlay_rel_path(paths, out_path)
    payload['overlay_bbox'] = bbox
    _ci_overlay_timing_log('save_ci_overlay_file total', save_t0, f'unit={unit_id}')
    return payload


def build_ci_overlay_result(username: str, analysis_id: str, manifest: Dict[str, Any], r_layer: Dict[str, Any], paths: Dict[str, str]) -> Tuple[Dict[str, Any], str]:
    layer = _ensure_overlay_layer(paths, manifest, r_layer)
    layer_path = _overlay_layer_path(paths)
    version = ''
    if os.path.exists(layer_path):
        try:
            version = str(int(os.path.getmtime(layer_path) * 1000))
        except Exception:
            version = ''
    return {
        'layer': layer.get('layer', 'OVERLAY'),
        'items': [_overlay_item_to_response(paths, item) for item in (layer.get('items') or []) if isinstance(item, dict)],
    }, version


def can_start_ci_overlay_job(username: str, analysis_id: str, unit_id: str) -> Tuple[bool, str]:
    if _is_ci_overlay_busy(username, analysis_id, unit_id):
        return False, 'generating'
    if _is_reproduction_iterating(username, analysis_id, unit_id):
        return False, 'reproduction_busy'
    return True, ''


def start_ci_overlay_generate_job(username: str, analysis_id: str, unit_id: str, instruction_text: str,
                                  reference_image_b64: Optional[str], reference_image_mime: str,
                                  image_quality: str, include_tm_context: bool = True,
                                  dmt_generated: bool = False) -> None:
    coarse_for_steps = False
    try:
        _paths, _manifest, _rl, _ri, overlay_for_steps, _ra = _load_ci_context(username, analysis_id, unit_id)
        coarse_for_steps = bool((overlay_for_steps or {}).get('ci_dmt_coarse_layout'))
    except Exception:
        coarse_for_steps = False
    # 细粒度+DMT：含 D 层质检与可能迭代，进度按 5 步；粗粒度+DMT：仅并行三层后结束，与未勾 DMT 同为 2 步
    total_steps = 2 if (not dmt_generated or coarse_for_steps) else 5

    def _job():
        try:
            _set_ci_overlay_progress(username, analysis_id, unit_id, 1, total_steps, '生成覆盖层')
            result = generate_ci_overlay(
                username=username,
                analysis_id=analysis_id,
                unit_id=unit_id,
                instruction_text=instruction_text,
                reference_image_b64=reference_image_b64,
                reference_image_mime=reference_image_mime,
                image_quality=image_quality,
                include_tm_context=include_tm_context,
                dmt_generated=dmt_generated,
            )
            _set_ci_overlay_job(username, analysis_id, unit_id, {
                'status': 'success',
                'msg': 'success',
                'overlay_path': result.get('overlay_path', ''),
                'overlay_bbox': result.get('overlay_bbox'),
                'overlay_item': result,
                'progress_step': total_steps,
                'progress_total': total_steps,
                'progress_msg': '完成',
            })
        except Exception as ex:
            traceback.print_exc()
            _set_ci_overlay_job(username, analysis_id, unit_id, {'status': 'error', 'msg': str(ex)})
        finally:
            _set_ci_overlay_busy(username, analysis_id, unit_id, False)

    _set_ci_overlay_job(username, analysis_id, unit_id, {
        'status': 'running',
        'msg': 'running',
        'progress_step': 0,
        'progress_total': total_steps,
        'progress_msg': '排队中',
    })
    _set_ci_overlay_busy(username, analysis_id, unit_id, True)
    threading.Thread(target=_job, daemon=True).start()


def start_ci_overlay_iterate_job(username: str, analysis_id: str, unit_id: str, overlay_image: Optional[str],
                                 instruction_text: str, reference_image_b64: Optional[str], reference_image_mime: str,
                                 image_quality: str) -> None:
    def _job():
        try:
            result = iterate_ci_overlay(
                username=username,
                analysis_id=analysis_id,
                unit_id=unit_id,
                overlay_image=overlay_image,
                instruction_text=instruction_text,
                reference_image_b64=reference_image_b64,
                reference_image_mime=reference_image_mime,
                image_quality=image_quality,
            )
            _set_ci_overlay_job(username, analysis_id, unit_id, {
                'status': 'success',
                'msg': 'overlay_iterate_success',
                'overlay_path': result.get('overlay_path', ''),
                'overlay_bbox': result.get('overlay_bbox'),
                'overlay_item': result,
            })
        except Exception as ex:
            traceback.print_exc()
            _set_ci_overlay_job(username, analysis_id, unit_id, {'status': 'error', 'msg': str(ex)})
        finally:
            _set_ci_overlay_busy(username, analysis_id, unit_id, False)

    _set_ci_overlay_job(username, analysis_id, unit_id, {'status': 'running', 'msg': 'overlay_iterating'})
    _set_ci_overlay_busy(username, analysis_id, unit_id, True)
    threading.Thread(target=_job, daemon=True).start()