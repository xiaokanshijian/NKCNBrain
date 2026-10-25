# -*- coding: utf-8 -*-
"""
四色卡片生图：为本子内有 four_color_type 的卡片调用 Gemini 文生图，保存到 cardImage 目录。
6 并发，避免同一张卡重复生图（已有图则跳过），失败重试一次。
"""
import nkcn_public_config as _public_config
import os
import re
import random
import time
import json
import threading
from urllib.parse import unquote
from datetime import datetime
import base64
import io
import shutil
import math
import warnings
import numpy as np
import cv2
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, StreamingHttpResponse

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

from app_chat.models import Card

# 四色卡片生图（批量）使用
GEMINI_IMAGE_API_KEY = _public_config.secret('NKCN_R_LAYER_GEMINI_REPRO_API_KEY')
# 高清（4K）native generateContent 使用的独立 key（避免 normal key 在 4K 返回中不稳定/不可用）
GEMINI_IMAGE_API_KEY_HIGH = _public_config.secret('NKCN_VIEWS_CARD_IMAGE_API_KEY')
# 卡片生图（单张）使用
# GEMINI_IMAGE_API_KEY_SINGLE = "[redacted]"
GEMINI_IMAGE_API_KEY_SINGLE = _public_config.secret('NKCN_R_LAYER_GEMINI_REPRO_API_KEY')
GEMINI_IMAGE_BASE_URL = _public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/')
GEMINI_IMAGE_NATIVE_BASE_URL = _public_config.endpoint('NKCN_MODEL_GATEWAY_URL', 'http://localhost:9999')
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image-preview-X"
GEMINI_IMAGE_MODEL_FALLBACK = "gemini-3.1-flash-image-preview"
GPT_IMAGE_MODEL = "gpt-image-2"
GPT_IMAGE_MODEL_FALLBACK = "gpt-image-2-all"
# 兼容旧名
CARD_INITIAL_IMAGE_MODEL = GPT_IMAGE_MODEL


def _sm(key, default):
    from app_chat.scene_models import get_scene_value
    return get_scene_value(key, default)


def _dmt_gemini_model():
    env = os.environ.get("NKCN_DMT_GEMINI_MODEL", "").strip()
    if env:
        return env
    return _sm('dmt_gemini', 'gemini-3.1-pro-preview')

_IMAGE_ASPECT_TO_SIZE = {
    "1:1": "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
}
GEMINI_IMAGE_TIMEOUT = 8 * 60  # 8 分钟超时

_card_image_generating = {}
_card_image_lock = threading.Lock()


def mark_card_image_generating(username, cid):
    cid = int(cid)
    with _card_image_lock:
        if username not in _card_image_generating:
            _card_image_generating[username] = set()
        _card_image_generating[username].add(cid)


def unmark_card_image_generating(username, cid):
    cid = int(cid)
    with _card_image_lock:
        s = _card_image_generating.get(username)
        if s is not None:
            s.discard(cid)
_overlay_test_jobs = {}
# DMT 质检前：用户上传「底图+覆盖层」对齐合成图后 set，生成线程 wait
_overlay_qa_align_events = {}

IMG_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp']

# 新生图时使用的信息图规范摘要，迭代图时告知模型「原图按此规范生成，必须保持」
ORIGINAL_IMAGE_SPEC = """
【原图生成规范（迭代时必须保持）】
当前这张图是按以下信息图规范生成的，迭代时**必须保持该结构与风格**，只做内容层面的局部更新：
- 整体布局：三层结构——顶部整体摘要区（大标题+副标题，横线/色带与中部隔开）、中部主体内容区（若干大板块，板块内可有子板块，推演箭头或留白区隔）、底部核心洞察区（横向关键词/短句+图标，深色底色）。
- 中部：大板块样式为 图标+板块名+情绪锚点（⚠💡❗🔑💬等）+彩色小标签；子板块为 核心观点句（≤15字）+2-4条短句要点（≤15字/条）；每板块可嵌入金句理解短句。
- 视觉：留白不少于内容区1/4，纯图形元素占视觉面积≥1/5；板块间推演用箭头+过渡词，并列用留白。
- 内容：按原文逻辑顺序，保留措辞习惯；重要关键词用颜色突出；轻重如实（着墨多的板块更大、更核心的更深）。
"""

# 原图为「后置索引关联」分支生成时的说明（非三层信息图模板）
RELATED_BLOCK_IMAGE_SPEC = """
【原图生成规范（迭代时必须保持）】
当前这张图是按「当前卡片 + 后置索引关联卡片」综合生成的图，要求体现本卡片内涵、关联卡片与当前卡片的关联及原因、以及综合后的指向与作者意图。迭代时**保持该综合图风格与关联呈现方式**，只做内容层面的局部更新，不要改成三层信息图模板。
"""

# 是否先由 Claude 分析卡片文本生成「详尽生图描述」再交给 Gemini 按描述出图（提升 DMT 层次感与构图质量）
ENABLE_CLAUDE_IMAGE_SPEC = True
# Claude 模型：用于生成生图描述（与飞书智能纪要图对标，先理解再出图）
# CLAUDE_IMAGE_SPEC_MODEL = "claude-sonnet-4-5-20250929"
CLAUDE_IMAGE_SPEC_MODEL = "claude-sonnet-4-6"
CLAUDE_IMAGE_SPEC_API_KEY = _public_config.secret('OPENAI_API_KEY')
CLAUDE_IMAGE_SPEC_BASE_URL = _public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/')

# NK2026 本子：contentTitle 含 S5 → 视同无四色/无后置索引，保留 Claude DMT；Gxx.md 仅喂 Claude，批改版式给生图模型
_S5_IN_TITLE_RE = re.compile(r"(?:^|[^\d])S\s*5(?:\s*[:：]|(?!\d))", re.I)


def _content_title_is_s5_card(title) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    return bool(_S5_IN_TITLE_RE.search(t)) or bool(re.search(r"\bS5\b", t, re.I))


def _username_in_nk2026_ladder_scene(username: str) -> bool:
    try:
        from app_chat.scene_context_helper import get_scene_info_from_username
        from app_chat.automation_nk2026 import is_nk2026_ladder_scene

        scene_name, _, _, _ = get_scene_info_from_username(username)
        return is_nk2026_ladder_scene(scene_name)
    except Exception:
        return False


def _is_nk2026_s5_card_image(username: str, content_title) -> bool:
    return _username_in_nk2026_ladder_scene(username) and _content_title_is_s5_card(content_title)


def _resolve_card_image_gen_options(username, card):
    """返回 (four_color_type, post_index_cids, use_claude_spec)。NK2026 S5：视同无四色、无后置索引，Claude DMT 保留。"""
    four_color = getattr(card, "four_color_type", None)
    post_index_cids = _parse_post_index(getattr(card, "postIndex", None) or "") or None
    use_claude_spec = True
    title = getattr(card, "contentTitle", None) or ""
    if _is_nk2026_s5_card_image(username, title):
        four_color = None
        post_index_cids = None
        print(
            f"[card_image] NK2026 S5 卡片 cid={getattr(card, 'cid', '?')} "
            "视同无四色/无后置索引，保留 Claude DMT；Gxx 仅 Claude，版式给生图模型"
        )
    return four_color, post_index_cids, use_claude_spec


_MANUAL_EDIT_MARKER_RE = re.compile(r"\*\*\*(.+?)\*\*\*", re.DOTALL)


def _nk2026_s5_footer_label(adjust_percent: int = 0) -> str:
    pct = max(0, min(100, int(adjust_percent or 0)))
    return f"NKCN批改，TAxxx已审核并调整{pct}%"


def _extract_answer_section_for_s5(content: str) -> str:
    text = content or ""
    m = re.search(r"回答[:：]", text)
    if m:
        return text[m.end():]
    return text


def _calc_nk2026_s5_manual_adjust_percent(content: str) -> int:
    """***手动修改*** 字数占「回答：」后正文字数的整数百分比。"""
    answer = _extract_answer_section_for_s5(content)
    if not answer.strip():
        return 0
    manual_chars = sum(len(m.group(1)) for m in _MANUAL_EDIT_MARKER_RE.finditer(answer))
    answer_plain = answer.replace("***", "")
    total = len(answer_plain.strip())
    if total <= 0:
        return 0
    return max(0, min(100, round(manual_chars * 100 / total)))


def _build_nk2026_s5_image_layout_spec(adjust_percent: int = 0) -> str:
    footer = _nk2026_s5_footer_label(adjust_percent)
    return f"""
【批改报告布局基本版式要求】（须遵守）
- 顶部：居中粗体主标题：Wnxx主题课设群组公能批改（Wn为周次，xx为主题）
- 主标题下方一行基本信息：主题｜组号｜周次及阶段｜七色分数｜红蓝公能颜色
- 再下一行居中列出小组成员（每人都必须：角色+姓名）
- 主体三栏左中右并列，栏间用虚线箭头从左→中→右串联
- 底部居中标注：{footer}（xxx是TA助教姓名，如果有必须加，这是责任明确）
"""


def _build_nk2026_s5_iterate_image_spec(adjust_percent: int = 0) -> str:
    footer = _nk2026_s5_footer_label(adjust_percent)
    return f"""
【原图生成规范（迭代时必须保持）】
当前图为 NK2026 群组公能批改报告信息图，须保持：
- 顶栏主标题「Wnxx主题课设群组公能批改」（Wn为周次，xx为主题）、基本信息行、成员行
- 主体三栏（推进链条 / 公能指向 / 综合评分）及虚线箭头串联
- 底栏「{footer}」（xxx是TA助教姓名，如果有必须加，这是责任明确）
- 专业文档风、浅底、留白与卡片式分区
迭代时只做内容局部更新，不得改成通用信息图或其它版式。
"""


def _prepend_nk2026_s5_layout_to_prompt(prompt: str, adjust_percent: int = 0) -> str:
    """S5 卡片：在发给生图模型的 prompt 前叠加批改版式（不含 Gxx）。"""
    base = (prompt or "").strip()
    layout = _build_nk2026_s5_image_layout_spec(adjust_percent).strip()
    if not base:
        return layout
    return layout + "\n\n" + base


def _normalize_image_aspect_ratio(raw) -> str:
    v = (raw or "1:1").strip()
    return v if v in _IMAGE_ASPECT_TO_SIZE else "1:1"


def _normalize_image_provider(raw) -> str:
    v = (raw or "gpt").strip().lower()
    return v if v in ("gpt", "gemini") else "gpt"


def _aspect_ratio_prompt_prefix(aspect_ratio: str) -> str:
    if aspect_ratio == "16:9":
        return "【画幅要求】横向 16:9 宽屏构图，画面宽度明显大于高度。\n\n"
    if aspect_ratio == "9:16":
        return "【画幅要求】竖向 9:16 构图，画面高度明显大于宽度。\n\n"
    return ""

_GXX_S5_CONTEXT_MAX_CHARS = 14000
_GXX_IN_TITLE_RE = re.compile(r"G0*(\d{1,2})(?!\d)", re.I)


def _parse_gxx_group_id_from_card_title(title: str):
    t = (title or "").strip()
    if not t:
        return None
    m = _GXX_IN_TITLE_RE.search(t)
    if not m:
        return None
    try:
        gid = int(m.group(1))
    except (TypeError, ValueError):
        return None
    return gid if 1 <= gid <= 99 else None


def _load_nk2026_s5_gxx_context_block(username: str, content_title: str) -> str:
    """S5 卡片标题含 Gxx 且存在 Gxx.md 时，返回供 Claude 写生图描述的补充上下文（不发给生图模型）。"""
    if not _is_nk2026_s5_card_image(username, content_title):
        return ""
    gid = _parse_gxx_group_id_from_card_title(content_title)
    if gid is None:
        return ""
    try:
        from app_chat.group_twin_gxx import read_twin_file, _strip_gxx_generated_footer
    except Exception:
        return ""
    twin_name = f"G{gid:02d}.md"
    raw = read_twin_file(username, twin_name)
    body = _strip_gxx_generated_footer(raw or "")
    if not body:
        return ""
    if len(body) > _GXX_S5_CONTEXT_MAX_CHARS:
        body = body[:_GXX_S5_CONTEXT_MAX_CHARS] + "\n…（Gxx.md 过长，此处截断）"
    print(f"[card_image] NK2026 S5 Claude 注入 {twin_name} 上下文 chars={len(body)}")
    return (
        f"【小组补充资料 · {twin_name}（仅供你撰写生图描述时理解组情，勿写入生图描述大段原文）】\n"
        "这是本卡片对应小组的相关补充资料；下方「卡片正文」是基于此资料整理得出的成稿。"
        "你输出的生图描述须以卡片正文为图中文字来源，Gxx 仅作背景理解。\n\n"
        f"{body}\n"
    )


# ---------- 文档摘要卡：会议类 → 图上文字风格 B（纪要精要）；其余保持现有风格 A ----------
# 兼容单文档【文件摘要】与多增量【综合摘要】
_FILE_SUMMARY_HEAD_RE = re.compile(r'^【(?:文件摘要|综合摘要)】\s*(.+?)(?:\r?\n|$)')
_PRESUMMARY_CONTEXT_MAX_TOKENS = 131072
_PRESUMMARY_COMPLETION_MAX_TOKENS = 4096
_PRESUMMARY_RESERVED_TOKENS = 6500
_PRESUMMARY_CHARS_PER_TOKEN = 1.50
_PRESUMMARY_SAFETY_FACTOR = 0.90

DOC_SUMMARY_IMAGE_TEXT_STYLE_B_ADDON = """
【仅「图上文字内容」组织要求 · 会议纪要精要版 · 对标飞书妙记意图主线复原】
当前输入是「会议语音转写/会议纪要」的**文档原文**（可能含智能章节、文字记录、关键决策等；不一定两者都有），**不是**文档摘要卡，也**不是** Presummary。
构图/配色/图标/留白/字体层级等视觉规范仍严格遵守上文既有「空间与构图」「视觉与风格」要求（保持 NKCN 现有视觉，不要换飞书皮肤）；本段只约束「选什么字上图、按什么顺序分块」。

一、目标（最高优先级）
- 复原「这场会按什么议题顺序讲、意图主线是什么」——让当事人一眼觉得：就是我们会上那条线。
- **会议推进还原感 / 顺序感要强**：自上而下=会议推进顺序；大段之间用箭头/序号标出先后；禁止按分析维度重排、禁止发散扩写。
- **信息密度必须下压**：少块、少条、短句；精准抽取意图主线，不要完备知识库。大标题/区标题/主张标题/关键短语保持准；**红框级「要点正文」每条必须是简短一句**。

二、分层分块（必有）+ 可选形态（必要时）
1) 顶层：大标题 +「核心结论/核心观点」约 2～3 条短句。
2) 主体：**分层分块必须始终存在**（大段 section + 子块 blocks，含主张标题与短要点）。段数/块数随会上真实议题走；常见参考（仅建议）约 2 大段、每段约 2～3 子块，勿僵化成固定模板。
   - 段与段、段内子块占比宜接近会上讨论比重，勿明显压薄某一充分讨论过的部分。
   - **大多时候**只要分层分块即可（默认并排卡呈现）。
   - **必要时**，在已有分层分块之上，可额外选用时间线或表格等呈现形式（阶段/路径→时间线；对照/映射→表）；这是可选增强，**不能用时间线/表格替代或取消分层分块**。
3) 不必强开「决策下一步」第三层；无明示决策可省略。

三、必须写准的「红框级」结构信息（对标飞书妙记精要图）
1. 全图大标题
2. 各大段区标题（如「商业模式核心特征」「竞争分析与未来规划」）
3. 各分卡的一句主张标题（如「与医院共生」「价值结果分成」「从辅助提效转向引领学科发展」）——若原文已有「核心特征为A、B、C」类自拟枚举，主张标题必须对齐该枚举，不得另换框架
4. 要点中的关键短语/关键词（高亮用；来自会上主线用语）

四、要点正文硬上限（下压密度的关键；标题已准时更要砍正文）
- 每张卡：主张标题 + **至多 2～3 条**要点；**每条=简短一句**，尽量 ≤16 字，禁止两行长解释、禁止堆案例数字与从句。
- 关键短语只从该句中点几处高亮，不要为塞标签另写长句。
- 全图不要再设「金句摘要 / 整体摘要长文 / 延伸思考」平级专区。

五、禁止事项（防发散）
- 禁止在图上直接出现会议录音时间戳（如 00:00、01:26、10:08、说话人旁的时间码等）；可用议题顺序表达先后，但不得写时间码。
- 禁止视角标签、D-M-T、第三方分析师口吻、会外发挥、补全会议上没讲清的推论。
- 禁止把原文结构改写成「概述 / 智能章节 / 全文详述」等摘要模板。
- 禁止堆砌具体账单数字、二级黑话、重复解释；数字/黑话默认删，除非它本身就是主线主张。
- 图上文字须是原文主线的忠实压缩，禁止虚构会议未出现的议题。
""".strip()

# 多文档【综合摘要】卡在风格 A 基础上的额外出图要求（单句）
DOC_SUMMARY_IMAGE_MULTI_INCREMENTAL_STYLE_A_ADDON = (
    "图中须同时体现主文档内容、各辅文档的补强信息，以及跨文档共识与关联，"
    "不可只画主文档一条线而忽略辅文档与综合部分。"
)


MEETING_MAINLINE_OUTLINE_SYSTEM = """你是会议纪要精要分析专家，对标飞书妙记「一眼准」的意图主线复原。
只根据用户给出的会议文档原文做**内容结构抽取**（不要写生图描述、不要写配色布局）。

任务：精准抽出会议主线议题，并确定分层/分块文字。这些文字将直接用于下一阶段生成信息图，因此必须正确、短、准。

【结构目标——主线推进感强；分层分块必有，形态可选】
会议推进还原感必须强：读者应一眼看出讨论先后与各大块内的子议题。
**分层分块（sections + blocks）是必须输出的骨架**，不可省略。
段数、每段子块数跟随会上真实议题与发言人自报骨架；**2 大段 × 每段约 3 子块只是常见参考（仅建议，禁止僵硬套模板）**。各大段占比宜接近会上讨论比重。
呈现形态：大多时候只要分层分块（layout 用 columns 即可）。**必要时**才把该段呈现为时间线（timeline）或表格（table）——这是可选，且时间线节点/表格行仍对应同一套 blocks，**禁止用 timeline/table 替代分层分块内容**。
典型好结构示例（仅示例，文字须来自本场会议，勿照抄）：
- 第一大段「商业模式核心特征」→ 3 个子部分：与医院共生 / 价值结果分成 / 从辅助提效转向引领
- 第二大段「竞争分析与未来规划」→ 3 个子部分：竞争优势分析 / 公司实践与组织重塑 / 未来发展规划
严禁：把靠前讨论写满，却把靠后、会上同样充分讨论的部分压成明显更薄的附录。

【说话人自拟骨架句 —— 提取优先级最高，胜过自行归纳】
先扫描原文/智能章节/关键决策中，发言人是否用一句总括把某大段拆成并列的 2～3 点，例如：
- 「核心特征为A、B、C」
- 「主要有三点：…」
- 「第一…第二…第三…」
- 「我的模式是…；第二个逻辑是…；第三个是…」
一旦出现这类「自报骨架」，对应大段的 blocks **必须逐条对应该枚举**，并按其原顺序落成 block_title（可略润为主张短句，但不得换题、不得合并、不得另起炉灶用你自行归纳的替代框架替换）。
例：原文写「核心特征为与医院共生、价值结果分成、从辅助提效转向引领学科发展」
→ 该大段子块主张标题就应围绕：①与医院共生 ②价值结果分成 ③从辅助提效转向引领学科发展
（而非自行改成「卖设备转型」「结果付费」之类错位结构）。
智能章节标题若本身是按该枚举展开的主张句，可作 block_title 的用语来源，但仍须对齐上述枚举条目，不得丢掉枚举中的任一点。

必须输出的信息层级：
1) main_title：全图大标题
2) core_conclusions：约 2～3 条核心结论短句（覆盖主要讨论重心）
3) sections：按会议推进顺序的大段列表（建议 1～3 段，常见为 2 段；勿为凑数硬拆）
   每个大段含：
   - section_title：大段区标题（优先用原文/章节范畴名，如「商业模式核心特征」「竞争分析与未来规划」）
   - layout：呈现方式。默认 "columns"（分层分块用并排卡即可）。仅当该段确需阶段流程或对照映射时，才分别用 "timeline" / "table"；无论取何值，**blocks 必须齐全**（时间线节点或表行=子块，不得只给 layout 不给 blocks）
   - blocks：该段内子块（建议每段 2～3 个；有自报枚举则块数=枚举点数）；每块含
     - block_title：一句主张标题（优先=说话人自拟枚举点 / 对应智能章节主张句）
     - points：1～3 条**极短**要点，**每条必须是简短一句**（尽量 ≤16 字；禁止长解释/案例堆砌）
     - key_phrases：该块应高亮的关键短语（2～4 个，来自原文主线用语；从短句里点出即可）

规则：
- 顺序必须忠实会议推进（优先沿智能章节时间序聚类）；禁止按分析师维度（如「定位→壁垒→路径」）重排会议真实讨论重心。
- **占比均衡**：按会上讨论份量（智能章节条数、发言篇幅、重复强调）分配各段与子块；充分讨论过的部分不得无故缩水。
- **密度优先砍 points**：标题/主张/关键短语求准；要点正文求短。宁可少写半句，也不要两行长句。
- 不得输出任何录音时间戳（00:00、01:26 等）；章节题意可吸收，时间码一律丢弃。
- 不要金句专区、不要会外补全、不要自创会上未出现的分析型元标签当 block_title。
- 只输出一个 JSON 对象，不要 Markdown 代码围栏，不要解释。

JSON 模式：
{
  "main_title": "...",
  "core_conclusions": ["...", "..."],
  "sections": [
    {
      "section_title": "...",
      "layout": "columns",
      "blocks": [
        {
          "block_title": "...",
          "points": ["...", "..."],
          "key_phrases": ["...", "..."]
        }
      ]
    }
  ]
}
""".strip()


def _call_claude_chat_text(system: str, user_content, *, temperature: float = 0.3, max_tokens: int = 4096,
                           label: str = 'Claude'):
    """统一 Claude 文本调用；user_content 可为 str 或 OpenAI 多模态 content list。失败返回 None。"""
    try:
        client = OpenAI(
            api_key=CLAUDE_IMAGE_SPEC_API_KEY,
            base_url=CLAUDE_IMAGE_SPEC_BASE_URL,
            default_headers={"x-foo": "true"},
            timeout=CLAUDE_IMAGE_SPEC_TIMEOUT,
        )
        resp = client.chat.completions.create(
            model=_sm('card_image_claude_spec', CLAUDE_IMAGE_SPEC_MODEL),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            print(f"[card_image] {label} 失败: 空输出")
            return None
        print(f"[card_image] {label} 成功: len={len(text)}")
        print(f"[card_image] {label} 内容:\n{text}")
        return text
    except Exception as e:
        print(f"[card_image] {label} 失败: {e}")
        return None


def _strip_json_fence(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.I)
        raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()


def _get_meeting_mainline_outline_from_claude(doc_text: str, title: str = "") -> str:
    """
    风格 B 第一遍 Claude：只做会议主线议题/分层分块文字抽取（JSON 文本）。
    失败返回空串。
    """
    body = (doc_text or "").strip()
    if not body:
        return ""
    user = """【参考标题】%s

【会议文档原文】
%s

请严格按系统要求只输出 JSON：
- **分层分块（sections+blocks）必须有**；2×3 仅常见建议，勿僵化；大多时候 layout=columns 即可；必要时才可选 timeline/table（layout 标明），且不能用它们替代 blocks；
- **先找发言人自拟骨架句**（如「核心特征为A、B、C」「第一…第二…第三…」）：对应大段 block_title 必须逐条对齐该枚举，禁止用自行归纳框架替换；
- 各大段占比均衡，符合会上讨论比重；
- **points 每条必须是简短一句**（尽量≤16字），下压信息密度、仍保持精准；
- 顺序=会议推进顺序；强化主线还原感；
- 确定大标题、核心结论、区标题、分卡主张标题、要点与关键短语；
- 禁止输出任何会议时间戳。""" % ((title or "")[:300], body)
    print(
        f"[card_image] Claude#1 会议主线分析 开始 chars={len(body)} title={(title or '')[:80]!r}"
    )
    outline = _call_claude_chat_text(
        MEETING_MAINLINE_OUTLINE_SYSTEM,
        user,
        temperature=0.2,
        max_tokens=4096,
        label='Claude#1 会议主线分析',
    )
    if not outline:
        return ""
    cleaned = _strip_json_fence(outline)
    # 轻量校验：像 JSON 且含关键字段；提示占比失衡（不强制 2×3）
    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict) or not data.get('main_title') or not data.get('core_conclusions'):
            print("[card_image] Claude#1 JSON 缺关键字段，仍把原文传给第二遍")
        else:
            sections = data.get('sections') or []
            block_counts = []
            point_lens = []
            for sec in sections if isinstance(sections, list) else []:
                if not isinstance(sec, dict):
                    continue
                blocks = sec.get('blocks') or []
                block_counts.append(len(blocks) if isinstance(blocks, list) else 0)
                for blk in blocks if isinstance(blocks, list) else []:
                    if not isinstance(blk, dict):
                        continue
                    for pt in (blk.get('points') or []):
                        if isinstance(pt, str):
                            point_lens.append(len(pt.strip()))
            n_sec = len(block_counts)
            cleaned = json.dumps(data, ensure_ascii=False, indent=2)
            print(
                f"[card_image] Claude#1 JSON 校验通过: sections={n_sec} "
                f"blocks_per_section={block_counts} layouts="
                f"{[ (s.get('layout') if isinstance(s, dict) else None) for s in (sections or []) ]}"
            )
            if n_sec >= 2 and block_counts and (max(block_counts) - min(block_counts) >= 2):
                print(
                    f"[card_image] Claude#1 占比失衡警告: blocks_per_section={block_counts} "
                    f"（某大段可能被压薄）"
                )
            long_pts = [n for n in point_lens if n > 18]
            if long_pts:
                print(
                    f"[card_image] Claude#1 要点偏长警告: {len(long_pts)}/{len(point_lens)} 条 "
                    f">18字 (max={max(point_lens) if point_lens else 0})"
                )
    except Exception as e:
        print(f"[card_image] Claude#1 非严格 JSON（仍继续第二遍）: {e}")
        cleaned = outline.strip()
    return cleaned


def _presummary_max_content_length() -> int:
    tokens_budget = max(
        0,
        _PRESUMMARY_CONTEXT_MAX_TOKENS
        - _PRESUMMARY_COMPLETION_MAX_TOKENS
        - _PRESUMMARY_RESERVED_TOKENS,
    )
    return int(tokens_budget * _PRESUMMARY_CHARS_PER_TOKEN * _PRESUMMARY_SAFETY_FACTOR)


def _truncate_content_like_presummary(full_content: str) -> str:
    """与 parse_input.process_document_pre_summary 相同的超长截断策略。"""
    text = full_content or ""
    max_len = _presummary_max_content_length()
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_paragraph_end = truncated.rfind('\n\n')
    if last_paragraph_end > max_len * 0.85:
        return text[:last_paragraph_end]
    return truncated


def _is_file_summary_card_content(content: str) -> bool:
    return bool(_FILE_SUMMARY_HEAD_RE.match((content or "").lstrip()))


def _is_multi_incremental_summary_card_content(content: str) -> bool:
    """多本子增量综合摘要卡（【综合摘要】头）。"""
    return (content or "").lstrip().startswith('【综合摘要】')


def _extract_file_summary_doc_name(content: str) -> str:
    m = _FILE_SUMMARY_HEAD_RE.match((content or "").lstrip())
    if not m:
        return ""
    rest = (m.group(1) or "").strip()
    # 综合摘要：主文档：《xxx》｜辅文档：…
    main_m = re.search(r'主文档：\s*《([^》]+)》', rest)
    if main_m:
        return (main_m.group(1) or "").strip()
    return rest


def _file_summary_body_for_fallback(content: str) -> str:
    """去掉【文件摘要】/【综合摘要】头后的摘要正文，原文加载失败时供判别兜底。"""
    text = (content or "").lstrip()
    m = _FILE_SUMMARY_HEAD_RE.match(text)
    if not m:
        return text
    return text[m.end():].lstrip()


def _load_source_doc_text_for_file_summary(username: str, docs_name: str) -> str:
    """尽量加载文档摘要卡对应的原文（PDF/TXT/OCR raw），逻辑对齐 Presummary 加载。"""
    docs_name = (docs_name or "").strip()
    if not username or not docs_name:
        return ""
    try:
        from llm_langchain import util as langchain_util
        from llm_langchain.parse_input import get_loader
    except Exception as e:
        print(f"[card_image] 加载文档工具失败: {e}")
        return ""

    try:
        file_path = langchain_util.construct_file_path(username, docs_name)
    except Exception as e:
        print(f"[card_image] construct_file_path 失败: {e}")
        return ""
    if not file_path or not os.path.exists(file_path):
        print(f"[card_image] 摘要源文件不存在: {file_path}")
        return ""

    all_docs = []
    try:
        lower = docs_name.lower()
        if lower.endswith('.pdf'):
            file_base = os.path.splitext(docs_name)[0]
            ocr_dir = os.path.join(os.path.dirname(file_path), f"{file_base}_ocr")
            txt_path = os.path.join(ocr_dir, f"{file_base}_raw.txt")
            pdf_type = None
            try:
                from app_chat import global_var
                from llm_langchain.pdf_ocr_utils import check_pdf_type_by_word
                file_key = f"{username}/{docs_name}"
                pdf_type = global_var.get_pdf_type(file_key)
                if pdf_type is None:
                    pdf_type = check_pdf_type_by_word(file_path)
                    global_var.set_pdf_type(file_key, pdf_type)
            except Exception:
                pdf_type = None
            if pdf_type == 'scanned' and os.path.exists(txt_path):
                from langchain.document_loaders import TextLoader
                all_docs = TextLoader(txt_path, encoding='utf-8').load()
            elif os.path.exists(txt_path) and (
                not os.path.exists(file_path) or os.path.getsize(file_path) == 0
            ):
                from langchain.document_loaders import TextLoader
                all_docs = TextLoader(txt_path, encoding='utf-8').load()
            else:
                loader = get_loader(file_path)
                all_docs = loader.load()
        else:
            loader = get_loader(file_path)
            all_docs = loader.load()
    except Exception as e:
        print(f"[card_image] 读取摘要源文档失败 {docs_name}: {e}")
        return ""

    parts = []
    for doc in all_docs or []:
        page_content = (getattr(doc, 'page_content', None) or "").strip()
        if not page_content:
            continue
        page_num = None
        try:
            meta = getattr(doc, 'metadata', None) or {}
            if isinstance(meta, dict) and meta.get('page') is not None:
                page_num = int(meta.get('page')) + 1
        except Exception:
            page_num = None
        if page_num is not None:
            parts.append(f"[页码：第{page_num}页]\n{page_content}")
        else:
            parts.append(page_content)
    return "\n\n".join(parts).strip()


def _parse_meeting_classify_label(raw: str):
    """
    解析 DeepSeek 判别输出。
    返回 True=会议类 / False=非会议 / None=无法解析（调用方按风格 A 兜底）。
    """
    text = (raw or "").strip()
    if not text:
        return None
    # 优先扫全文中的规范标签（防模型夹带解释）
    if re.search(r'\bNOT[_\-\s]*MEETING\b', text, re.I):
        return False
    if re.search(r'\bMEETING\b', text, re.I):
        return True
    # 中文仅看前两行，降低长解释误判
    head = "\n".join(text.splitlines()[:2])
    if re.search(r'非会议|不是会议|不属于会议', head):
        return False
    if re.search(r'是会议|属于会议', head):
        return True
    # 首行宽松匹配
    first = text.splitlines()[0].strip().upper()
    first_compact = re.sub(r'[^A-Z]', '', first)
    if first_compact == 'NOTMEETING':
        return False
    if first_compact == 'MEETING':
        return True
    return None


def _extract_deepseek_message_text(message) -> str:
    """取 DeepSeek 最终回复；v4-flash 默认 thinking 时 content 可能为空，需兜底 reasoning_content。"""
    if message is None:
        return ""
    content = (getattr(message, 'content', None) or "").strip()
    if content:
        return content
    reasoning = (getattr(message, 'reasoning_content', None) or "").strip()
    if reasoning:
        return reasoning
    # 少数 SDK/代理把字段放在 model_extra / dict
    extra = getattr(message, 'model_extra', None) or {}
    if isinstance(extra, dict):
        for key in ('reasoning_content', 'reasoning', 'thinking'):
            val = (extra.get(key) or "").strip() if isinstance(extra.get(key), str) else ""
            if val:
                return val
    return ""


def _classify_meeting_doc_via_deepseek(doc_text: str) -> bool:
    """
    用 deepseek-v4-flash 判别是否会议语音转写/会议纪要类。
    可能仅有转写、仅有智能章节纪要、或两者皆有。失败或解析失败 → False（风格 A）。
    """
    body = _truncate_content_like_presummary(doc_text or "")
    if not body.strip():
        print("[card_image] 会议类判别跳过: 待判别文本为空，兜底风格A")
        return False

    system = (
        "你是文档类型判别器。判断用户给出的文档原文是否属于："
        "「会议语音转文字/转写」或「会议纪要」（含飞书妙记智能章节式纪要）类。"
        "注意：文档可能只有语音转写全文、或只有智能章节/会议纪要（含时间戳）、或两者都有；"
        "属于会议记录类材料，即判为会议类。"
        "不要做摘要，不要解释。"
        "你必须且只能输出一行标签，二选一："
        "MEETING"
        " 或 "
        "NOT_MEETING"
    )
    user = "【待判别文档原文】\n" + body
    try:
        ds_key = os.environ.get('DEEPSEEK_API_KEY') or _public_config.secret('DEEPSEEK_API_KEY')
        model = os.environ.get('NKCN_DEEPSEEK_MODEL') or _sm('homework_deepseek', 'deepseek-v4-flash')
        client = OpenAI(api_key=ds_key, base_url='https://api.deepseek.com', timeout=90.0)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # v4-flash 默认 thinking：max_tokens 过小会导致 content 为空；分类任务关闭 thinking 更稳
        create_kwargs = dict(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=256,
            extra_body={"thinking": {"type": "disabled"}},
        )
        try:
            resp = client.chat.completions.create(**create_kwargs)
        except Exception as e_think:
            print(f"[card_image] 会议类判别关闭 thinking 失败，回退默认调用: {e_think}")
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=512,
            )
        choice = resp.choices[0] if resp.choices else None
        message = choice.message if choice else None
        finish = getattr(choice, 'finish_reason', None) if choice else None
        content_raw = (getattr(message, 'content', None) or "") if message else ""
        reasoning_raw = (getattr(message, 'reasoning_content', None) or "") if message else ""
        raw = _extract_deepseek_message_text(message)
        print(
            f"[card_image] 会议类判别 model={model} finish_reason={finish} "
            f"content_len={len(content_raw)} reasoning_len={len(reasoning_raw)} "
            f"used_len={len(raw)} raw={raw[:200]!r}"
        )
        parsed = _parse_meeting_classify_label(raw)
        if parsed is None:
            print("[card_image] 会议类判别结果无法解析，兜底按非会议（风格A）")
            return False
        return bool(parsed)
    except Exception as e:
        print(f"[card_image] 会议类 DeepSeek 判别失败，兜底风格A: {e}")
        return False


def _resolve_doc_summary_image_text_style(username: str, content: str, title: str = "") -> str:
    """
    返回 'A'（现有全景文字组织）或 'B'（会议纪要精要文字组织）。
    单文档【文件摘要】且判别为会议类时为 B；【综合摘要】固定 A；视觉/构图规范不变。
    """
    style, _src = _resolve_doc_summary_image_plan(username, content, title)
    return style


def _resolve_doc_summary_image_plan(username: str, content: str, title: str = ""):
    """
    返回 (text_style, source_doc_truncated)。
    - text_style: 'A' | 'B'
    - source_doc_truncated: 风格 B 且原文可用时，为与会议判别相同截断规则的文档原文；否则 ''。
      （风格 B 下 Claude 生图描述应只用该原文，不用摘要卡/Presummary。）
    """
    if not _is_file_summary_card_content(content):
        return 'A', ''
    if _is_multi_incremental_summary_card_content(content):
        print(
            f"[card_image] 多文档综合摘要卡：出图固定风格A title={(title or '')[:80]!r}"
        )
        return 'A', ''
    docs_name = _extract_file_summary_doc_name(content)
    source_raw = _load_source_doc_text_for_file_summary(username, docs_name) if docs_name else ""
    source_for_claude = ''
    if source_raw.strip():
        source_for_claude = _truncate_content_like_presummary(source_raw)
        print(
            f"[card_image] 摘要源原文已加载 doc={docs_name!r} "
            f"raw_chars={len(source_raw)} truncated_chars={len(source_for_claude)}"
        )
        classify_text = source_for_claude
    else:
        # 原文不可得时，仅用摘要卡正文做判别；风格 B 时 Claude 仍不应喂摘要（见调用方）
        classify_text = _file_summary_body_for_fallback(content)
        print(
            f"[card_image] 摘要源原文不可用，用摘要正文判别 doc={docs_name!r} "
            f"chars={len(classify_text)}"
        )
    is_meeting = _classify_meeting_doc_via_deepseek(classify_text)
    style = 'B' if is_meeting else 'A'
    if style != 'B':
        source_for_claude = ''
    print(
        f"[card_image] 文档摘要出图文字风格={style} title={(title or '')[:80]!r} "
        f"doc={docs_name!r} meeting={is_meeting} "
        f"style_b_source_chars={len(source_for_claude)}"
    )
    return style, source_for_claude


_GRADING_HUB_IMAGE_ADDON = """
【批改结果·枢纽图纪律】（本卡为批改诊断卡时强制）
- 先交叉摘要，再构图：图是「一句枢纽 + 分栏 + 边界」，禁止把报告栏目 1:1 复刻进图。
- 中心：一句枢纽判断（短、可扫读）。
- 三区各 1 个短标题 + 1 个下一步；不要铺满逐条三问墙。
- 底部一条边界（材料未纳入 / 不能推断的事）。
- 字要少到一屏读完；方法痕迹用判断取舍体现，禁止方法英文名与包名清单。
"""


def _is_grading_result_card_content(content: str, title: str = '') -> bool:
    text = content or ''
    t = title or ''
    return (
        '<!--nkcn_grading_card' in text
        or '批改·诊断' in text
        or '批改·诊断' in t
        or ('批改·' in t and '诊断' in t)
        or '批改·解释精要' in text
        or ('批改·' in t and '解释精要' in t)
    )


def _is_grading_excerpt_card_content(content: str, title: str = '') -> bool:
    text = content or ''
    t = title or ''
    return (
        '批改·解释精要' in text
        or '批改·解释精要' in t
        or ('解释精要' in t and '批改' in t)
        or '<!--nkcn_grading_card:批改·解释精要' in text
    )


def _grading_excerpt_image_brief(username: str, content: str, title: str = '') -> str:
    """解释精要生图：只喂总览+枢纽+各页整体，不喂逐题细节。"""
    try:
        from app_chat.homework_grading.excerpt_card_render import (
            build_excerpt_image_brief,
            build_excerpt_payload,
            strip_grading_card_marker,
        )
        analysis_id = ''
        run_id = None
        m = re.search(
            r'<!--nkcn_grading_card:批改·解释精要\|([^|>]+)\|([^>]+)-->',
            content or '',
        )
        if m:
            analysis_id, run_id = m.group(1).strip(), m.group(2).strip()
        if not analysis_id or not username:
            return strip_grading_card_marker(content or '')[:4000]
        from app_chat.homework_grading.service import prepare_homework_workspace
        from app_chat.homework_grading.result_cards import _load_json, _named_json, _sample_id
        paths = prepare_homework_workspace(
            username, analysis_id,
            None if run_id in (None, '', 'current') else run_id,
            create=False,
        )
        manifest = _load_json(paths.get('manifest') or '')
        fctx = manifest.get('feedback_context') or {}
        subject = str(manifest.get('subject') or fctx.get('subject_code') or 'chinese')
        sample_id = _sample_id(analysis_id)
        report = _named_json(paths.get('pass2_report') or '', subject, sample_id, '_report.json')
        ontology = _load_json(os.path.join(paths.get('base') or '', 'student_ontology.json'))
        assigned = None
        gc = manifest.get('grading_config') if isinstance(manifest.get('grading_config'), dict) else {}
        if gc.get('assigned_pages'):
            try:
                assigned = [int(p) for p in gc['assigned_pages']]
            except (TypeError, ValueError):
                assigned = None
        filename = (manifest.get('selected_files') or [''])[0]
        if not fctx and isinstance(ontology, dict):
            fctx = ontology.get('feedback_context') or {}
        payload = build_excerpt_payload(
            report, ontology,
            pass1_dir=paths.get('pass1_json') or '',
            subject=subject,
            assigned_pages=assigned,
            filename=filename,
            material_type=str(fctx.get('material_type') or 'homework'),
            feedback_context=fctx if isinstance(fctx, dict) else None,
        )
        brief = build_excerpt_image_brief(payload)
        return brief or strip_grading_card_marker(content or '')[:4000]
    except Exception as exc:
        print(f'[card_image] 解释精要生图摘要失败: {exc}')
        try:
            from app_chat.homework_grading.excerpt_card_render import strip_grading_card_marker
            return strip_grading_card_marker(content or '')[:4000]
        except Exception:
            return (content or '')[:4000]


def _build_v25_card_image_prompt(content, four_color_line, *, nk2026_s5=False, s5_adjust_percent: int = 0, text_style='A', multi_incremental_summary=False, grading_hub=False):
    """V2.5 通用生图 prompt；NK2026 S5 卡片叠加固定批改报告版式。"""
    if (text_style or 'A').upper() == 'B':
        # 风格 B：content 已是按 Presummary 规则截断的文档原文，不再二次砍到 6000
        body_part = content or ""
    else:
        # 批改卡用筛后 Markdown，不必喂满 6000 墙
        body_part = (content or "")[:4000 if grading_hub else 6000]
    extra_block = ""
    if (text_style or 'A').upper() == 'B':
        extra_block = "\n\n" + DOC_SUMMARY_IMAGE_TEXT_STYLE_B_ADDON + "\n"
    elif multi_incremental_summary:
        extra_block = "\n\n" + DOC_SUMMARY_IMAGE_MULTI_INCREMENTAL_STYLE_A_ADDON + "\n"
    if grading_hub:
        extra_block = (extra_block or "") + "\n" + _GRADING_HUB_IMAGE_ADDON + "\n"
    if nk2026_s5:
        layout_spec = _build_nk2026_s5_image_layout_spec(s5_adjust_percent).strip()
        return """你是一位专业的知识可视化设计师，擅长将复杂文字内容转化为清晰、专业、有层次感的结构化图表。请根据以下内容，生成一张高质量的内容可视化图。

%s

【第一步：读懂内容再动笔】
通读卡片正文全文，先识别：这段内容的顶层意图是什么？内容内部天然存在哪几个维度的分组（如：不同主题板块、问题与解法、现状与趋势、重要性/紧急度分类、时间序列……）？以此为骨架构建图的结构，区块名称直接来自内容本身，不套用通用词汇。

【整体构图】
- 顶部：大标题（统领核心意图）
- 中部：若干内容区块，区块数量、命名、排列方式（卡片组/表格/流程/混排）由内容决定，但不要简单铺开
- 底部：一条横幅式「核心结论/共识」，简短有力（不超过两行），深色或强调色背景收束全图
- 图整体画大一些，1400×1800，文字内容尽量小但清晰，这样就有足够空间来构图且不拥挤，能体现清晰、完整的逻辑/层次关系

【内容区块 · 卡片设计】
每张卡片：
  ① 浅色背景 + 顶部或左侧细色条区分板块 + 小图标 + 板块标题 + 右上角状态/类型标签（仅当内容中有状态信息时才加，如「正常推进」「急需改进」「进行中」）
  ② 核心观点句：加粗，置于要点上方，统领本板块
  ③ 要点列表：• 开头，每条精炼，控制在一行内
  ④ 若内容含对比、进度、时间线、多维度数据等，优先用表格呈现；若含状态信息，优先用彩色标签标注

【视觉风格】
- 专业文档风，参考高质量飞书会议纪要/项目报告等的排版美感：干净、克制、有呼吸感
- 背景：纯白或极浅灰；主色调：浅色系（浅蓝/浅绿/浅橙/浅紫等），用于卡片背景、色条、标签
- 充分留白：板块间距明确，内容不堆砌；图形元素（色块/线条/图标/箭头）占视觉面积不低于五分之一
- 字体层次分明：页面大标题 > 区块节标题 > 板块标题 > 核心观点句 > 要点条目，加粗有度
- 关键词/术语用颜色突出，少而精；原文着墨多的板块版面更大，不为视觉对称强行均分
%s
%s

【禁止】
- 禁止将任何字数限制、条数约束、设计规则等元指令文字出现在图面上
- 禁止深色/杂乱/高对比发光背景
- 禁止为了视觉对称虚构内容或重复冗余
- 禁止大段文字铺排，一眼全是字，但要尽可能保留原文或原话、原例子等，让作者看了都觉得有"回味感"
- 禁止不顾内容强行套用固定板块数量或固定模板名称

内容：
%s
""" % (layout_spec, four_color_line, extra_block, body_part)

    return """你是一位专业的知识可视化设计师，擅长将复杂文字内容转化为清晰、专业、有层次感的结构化图表。请根据以下内容，生成一张高质量的内容可视化图。

【第一步：读懂内容再动笔】
通读全文，先识别：这段内容的顶层意图是什么？内容内部天然存在哪几个维度的分组（如：不同主题板块、问题与解法、现状与趋势、重要性/紧急度分类、时间序列……）？以此为骨架构建图的结构，区块名称直接来自内容本身，不套用任何固定词汇。

【整体构图】
- 顶部：大标题（统领核心意图，不是原文标题的复制）+ 副标题摘要句（一句话点明这段内容在解决什么问题或表达什么立场）
- 中部：若干内容区块，区块数量、命名、排列方式（卡片组/表格/流程/混排）完全由内容决定，但不要简单铺开
- 底部：一条横幅式「核心结论/共识」，简短有力（不超过两行），深色或强调色背景收束全图
- 图整体画大一些，1400×1800，文字内容尽量小但清晰，这样就有足够空间来构图且不拥挤，能体现清晰、完整的逻辑/层次关系

【内容区块 · 卡片设计】
每张卡片：
  ① 浅色背景 + 顶部或左侧细色条区分板块 + 小图标 + 板块标题 + 右上角状态/类型标签（仅当内容中有状态信息时才加，如「正常推进」「急需改进」「进行中」）
  ② 核心观点句：加粗，置于要点上方，统领本板块
  ③ 要点列表：• 开头，每条精炼，控制在一行内
  ④ 若内容含对比、进度、时间线、多维度数据等，优先用表格呈现；若含状态信息，优先用彩色标签标注

【视觉风格】
- 专业文档风，参考高质量飞书会议纪要/项目报告等的排版美感：干净、克制、有呼吸感
- 背景：纯白或极浅灰；主色调：浅色系（浅蓝/浅绿/浅橙/浅紫等），用于卡片背景、色条、标签
- 充分留白：板块间距明确，内容不堆砌；图形元素（色块/线条/图标/箭头）占视觉面积不低于五分之一
- 字体层次分明：页面大标题 > 区块节标题 > 板块标题 > 核心观点句 > 要点条目，加粗有度
- 关键词/术语用颜色突出，少而精；原文着墨多的板块版面更大，不为视觉对称强行均分
%s
%s

【禁止】
- 禁止将任何字数限制、条数约束、设计规则等元指令文字出现在图面上
- 禁止深色/杂乱/高对比发光背景
- 禁止为了视觉对称虚构内容或重复冗余
- 禁止大段文字铺排，一眼全是字，但要尽可能保留原文或作者原话、原例子等，让作者看了都觉得有"回味感"
- 禁止不顾内容强行套用固定板块数量或固定模板名称

内容：
%s
""" % (four_color_line, extra_block, body_part)


CLAUDE_IMAGE_SPEC_TIMEOUT = 120

# 旧版方案：DMT 微版面化：生成「初始覆盖层」说明文字（Claude 4 Sonnet 流式）
DMT_OVERLAY_PROMPT_MODEL = "claude-sonnet-4-20250514"
DMT_OVERLAY_PROMPT_TIMEOUT = 180
# DMT 微版面化 / 检验优化 / 覆盖层并行质检：Gemini 3.1 Pro（OpenAI 兼容，dmxapi）
DMT_GEMINI_BASE_URL = os.environ.get("NKCN_DMT_GEMINI_BASE_URL", _public_config.endpoint('NKCN_REVIEW_GATEWAY_V1_URL', 'http://localhost:9999/v1'))
DMT_GEMINI_API_KEY = os.environ.get(
    "NKCN_DMT_GEMINI_API_KEY",
    _public_config.secret('NKCN_LLM_DMXAPI_API_KEY'),
)
DMT_GEMINI_MODEL = os.environ.get("NKCN_DMT_GEMINI_MODEL", "gemini-3.1-pro-preview")
DMT_GEMINI_TIMEOUT = 300
# 流式或非流式调用失败后的额外重试次数（不含首次）
DMT_GEMINI_MAX_RETRIES = 3
# 覆盖层 5 路专项 + 1 路汇总（dmxapi chat.completions）输出上限，避免长清单被 length 截断
DMT_OVERLAY_QA_MAX_OUTPUT_TOKENS = 8192

DMT_OVERLAY_SYSTEM = (
    "你是专业手稿/示意图版面分析助手。用户会给你一张图（卡片原图）和卡片文本（卡片文本很可能有很多错误，不要太相信卡片文本，以原图为准）。"
    "你必须只输出一段可直接复制给「文生图/生图AI」的完整中文指令正文，不要 Markdown 代码块、不要前言后语、不要解释。"
    "输出从「原图是一张手稿图」或「原图是一张手稿/示意图」起笔，直至用户要求的结尾句为止，结构完整。"
    "对【M级·蓝框】的每一条：除包含哪些图中元素外，必须写清版面相对位置，若相对位置实在不好描述，则写准绝对坐标范围；并写清蓝框边界形态；若原图有手绘横/竖/斜/曲线作为分隔，其两侧 M 蓝框的邻接边必须与该线同形贴合，蓝框外轮廓不必是矩形。"
)

DMT_OVERLAY_USER_PREFIX = """原图是一张手稿图，图中应该标注多个红、蓝、紫色框，具体如下：

【颜色规则】D=红框(#E53935,1.5px) M=蓝框(#1E88E5,1.5px) T=紫框(#8E24AA,1.5px)；红框/蓝框/紫框左上角分别加**红色底纯白字「D+序号」**标签、蓝色底纯白字「M+序号」标签、紫色底纯白字「T+序号」标签。嵌套关系：T⊃M⊃D。

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

我需要将上述所有的红蓝紫色框（含红/蓝/紫框左上角红底白字「D+序号」、蓝底白字「M+序号」、紫底白字「T+序号」标签，规格一致、用于定位）生成出来，底图内容（所有文字、线条、颜色等）全部清除不要，你生成出的图里应该只有红蓝紫框与标签上的白字序号，不要保留原图黑字正文或底色

风格严格按照参考图，红框+红底白字「D+序号」/蓝框+蓝色底白字「M+序号」/紫框+紫色底白字「T+序号」，仅参考样式风格

---

你最终输出必须严格采用上面的整体结构与措辞（对于【M级·蓝框】和【T级·紫框】中的「......」，请你主要根据原图（卡片文本很可能有不少错误，不要太相信卡片文本，以原图为准）理解并填写完善，可调整条目数量，但层级与颜色规则说明保持一致；【D级·红框】保持“......”占位不展开），输出可直接粘贴给其他生图AI的最终版本。务必注意：
1) 开头、【颜色规则】与结尾两段保持和上述格式、内容完全一致；
2) 【D级·红框】保持模板中的“......”占位，不展开具体内容，不补充D清单细节、不写具体字词，以免输出过长和误导后续生图；
3) 【M级·蓝框】每一条「......」展开时必须同时满足（表述须简洁、精炼、准确，切忌冗长）：(a)该 M 所含内容/元素要点；(b)该 M 在图中的相对位置或显著特征（如左上/右下/跨中部/被竖向长条手绘圈包住/左侧边缘是一条手绘曲线...等），若实在难以描述则给出准确的归一化坐标范围（以整图宽 W、高 H 为参照，例如「约 x/W∈[0.05,0.40]，y/H∈[0.10,0.38]」或等价描述），便于生图模型定位；(c)该 M **蓝框边界的形态**：「蓝框」仅表示蓝色描边区域，外轮廓不必是矩形，对特殊边要说明是斜边、折线边还是弧线边等，其他边默认水平或竖直；(d)不要写“包含Dxx-Dxx”。
4) M版面的划分粒度应该是中等（Middle），既不宜过大也不宜过小；像人一样读图：优先关注图中的圈画、箭头等标注——连续同向箭头涉及的内容优先划入同一 M；多箭头（含指入或指出）共中心时该中心与箭头指向/来源内容优先划入同一 M。与此同时，**凡原图中手绘长横线、长竖线、长斜线或曲线已明显起到分隔版面、使两侧内容相对独立时**：被其明确隔开的内容须划入**不同** M；且**该线两侧**相邻的两个 M，凡与该线相接的蓝框边，**必须与图中该线的走向、角度、弯折与曲率一致地贴合**（不可用与图不符的「标准矩形/横平竖直边」敷衍代替）；必须在文字中**点明**两侧 M 编号与该线的关系（例如「Mx 与 My 沿图中某手绘斜线分界，两侧蓝框邻接边须与该斜线同角度贴合」），便于直接粘贴给生图模型执行。关系密切且未被此类线隔开的元素/文字应在同一 M 内。

下面第一张图即待分析的原图。随后会给你与此图相关的卡片标题、正文（置信度不高，仅供参考，必须以原图为准），请综合理解，完成上述输出。
"""


def _dmt_overlay_parse_image_data_url(image_data_url: str):
    url = str(image_data_url or "").strip()
    if not url:
        return None, None
    b64 = url
    mime = "image/png"
    if url.startswith("data:") and "base64," in url:
        head, b64 = url.split("base64,", 1)
        try:
            mime = head.split(":", 1)[1].split(";")[0].strip() or mime
        except Exception:
            pass
    b64 = "".join(c for c in b64 if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    if not b64:
        return None, None
    return mime, b64


def _dmt_gemini_client():
    return OpenAI(
        api_key=DMT_GEMINI_API_KEY,
        base_url=DMT_GEMINI_BASE_URL.rstrip("/") + "/",
        default_headers={"x-foo": "true"},
        timeout=DMT_GEMINI_TIMEOUT,
    )


def _dmt_overlay_stream_generator(image_data_url: str, card_title: str, card_content: str):
    """Yields UTF-8 bytes chunks from Gemini 3.1 Pro 流式（失败自动重试）。"""
    parsed = _dmt_overlay_parse_image_data_url(image_data_url)
    if not parsed or not parsed[1]:
        return
    mime, b64 = parsed

    tail_text = (
        "【卡片标题】\n"
        + (card_title or "").strip()
        + "\n\n【卡片正文】\n"
        + (card_content or "").strip()
    )

    content_parts = [
        {"type": "text", "text": DMT_OVERLAY_USER_PREFIX},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        {"type": "text", "text": tail_text},
    ]

    max_attempts = 1 + int(max(0, DMT_GEMINI_MAX_RETRIES))
    for attempt in range(1, max_attempts + 1):
        try:
            client = _dmt_gemini_client()
            stream = client.chat.completions.create(
                model=_dmt_gemini_model(),
                messages=[
                    {"role": "system", "content": DMT_OVERLAY_SYSTEM},
                    {"role": "user", "content": content_parts},
                ],
                stream=True,
                max_tokens=8192,
                temperature=0.3,
            )
            for chunk in stream:
                try:
                    ch = chunk.choices[0]
                    delta = getattr(ch, "delta", None)
                    if delta is None:
                        continue
                    piece = getattr(delta, "content", None) or ""
                    if piece:
                        yield piece.encode("utf-8")
                except (IndexError, AttributeError, TypeError):
                    continue
            return
        except Exception as ex:
            print(f"[card_image] DMT 覆盖层说明流式失败 try={attempt}/{max_attempts}: {ex}")
            if attempt >= max_attempts:
                return
            time.sleep(1.2 * attempt)


DMT_OVERLAY_REFINE_SYSTEM = (
    "你是资深手稿/示意图版面分析助手。用户会给你卡片原图、卡片标题与正文，以及一份「生成覆盖层」的初稿说明文字。"
    "你必须只输出一版**优化后的完整说明正文**（可直接复制给生图 AI），结构与初稿同类、与 DMT 模板要求一致；"
    "不要 Markdown 代码块、不要前言后语、不要解释你改了什么。"
    "若初稿已合理，可在保持结构的前提下做轻微润色与补全，仍输出完整正文。"
    "优化时须重点核对：每个 M 版面是否写清了版面相对位置或归一化坐标范围（相对位置/绝对坐标有一个清楚即可）；蓝框边界形态是否写清（特别是有紧贴的原图手绘斜线/曲线分隔情况）；原图手绘横/竖/斜/曲分隔线两侧 M 的邻接边描述是否与线同形贴合（蓝框不必为矩形）。"
    "对于D清单不要具体展开，保持已有的......占位即可"
)


def _dmt_overlay_refine_stream_generator(
    image_data_url: str, card_title: str, card_content: str, draft_instruction: str
):
    """检验优化：Gemini 3.1 Pro 流式，对照原图优化初稿说明。"""
    parsed = _dmt_overlay_parse_image_data_url(image_data_url)
    if not parsed or not parsed[1]:
        return
    mime, b64 = parsed
    tail_text = (
        "【卡片标题】\n"
        + (card_title or "").strip()
        + "\n\n【卡片正文】\n"
        + (card_content or "").strip()
    )
    refine_block = (
        "【待检验优化的初稿（生成覆盖层说明）】\n"
        + (draft_instruction or "").strip()[:12000]
        +         "\n\n请对照原图检验：层级（T/M/D）、颜色规则、D 级占位；并**重点**核对每条 M 是否具备「位置/坐标范围 + 蓝框边界形态 + 与手绘横竖斜曲分隔线的贴合关系」（两侧 M 邻接边须与同形线一致，蓝框可为非矩形）；缺则补、误则改，但不要冗长，一定要简短精炼且准确。"
        "输出优化后的**完整**说明正文（从「原图是一张手稿图」或等价起笔至结尾要求句，结构完整）。"
    )
    content_parts = [
        {"type": "text", "text": refine_block},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        {"type": "text", "text": tail_text},
    ]
    max_attempts = 1 + int(max(0, DMT_GEMINI_MAX_RETRIES))
    for attempt in range(1, max_attempts + 1):
        try:
            client = _dmt_gemini_client()
            stream = client.chat.completions.create(
                model=_dmt_gemini_model(),
                messages=[
                    {"role": "system", "content": DMT_OVERLAY_REFINE_SYSTEM},
                    {"role": "user", "content": content_parts},
                ],
                stream=True,
                max_tokens=8192,
                temperature=0.25,
            )
            for chunk in stream:
                try:
                    ch = chunk.choices[0]
                    delta = getattr(ch, "delta", None)
                    if delta is None:
                        continue
                    piece = getattr(delta, "content", None) or ""
                    if piece:
                        yield piece.encode("utf-8")
                except (IndexError, AttributeError, TypeError):
                    continue
            return
        except Exception as ex:
            print(f"[card_image] DMT 检验优化流式失败 try={attempt}/{max_attempts}: {ex}")
            if attempt >= max_attempts:
                return
            time.sleep(1.2 * attempt)

# 构图结构参考图路径（与本文件同目录或 backend 根目录），若存在则一并传给 Claude 仿照构图
COMPOSITION_REFERENCE_IMAGE_NAMES = ("composition_reference.png", "构图结构参考图.png", "composition_reference.jpg")
OVERLAY_STYLE_REFERENCE_IMAGE_NAMES = ("版面DMT化覆盖层风格参考图.png",)

# 构图结构参考图「值得具体参考什么」——告知大模型此图好在哪里、应借鉴哪些点（导师评价：风格轻盈，文字样式丰富灵动有层次）
COMPOSITION_REFERENCE_WHY_GOOD = """
【构图结构参考图需要尽可能多借鉴的要点】（请在写生图描述时具体仿照参考图的以下方面，均为风格样式，严禁照抄参考图中文字内容！仅参考构图风格）
- **整体风格**：风格轻盈、版面有呼吸感，不沉重不堆砌；留白与内容比例得当，层次分明。
- **文字样式（丰富、灵动、有层次感）**：
  - 颜色：标题/副标题/正文/强调 用不同颜色区分层级与情绪；关键词或重点句用区别于正文的色相或深浅。
  - 字体大小：大标题 > 节标题 > 板块标题 > 正文/要点，层级清晰，一目了然。
  - 下划线：适度用下划线标出小标题或关键短语，增强可扫读性。
  - 文字底色高亮块：对核心观点、金句或关键词用浅色块（如浅黄、浅蓝、浅灰）做底色高亮，形成视觉锚点。
  - 反白字：在深色色块或色带上使用反白文字，形成对比、突出重点区域。
  - 虚实线：用实线划分主区块、虚线表示从属或关联；虚线也可用于引导视线或表示逻辑递进。
  - 图标与图文搭配：图文并茂、不单调；图标风格统一、不抢戏。
- **层次与节奏**：上中下分区、每区中的左中右细分区明确；有主从、有留白、有连接线或箭头，整体有节奏感而非平铺。
以上均应在你的「生图描述」中转化为可执行指令（例如：某区用浅黄底高亮、某处用反白字、某两区块间用虚线箭头连接等），内容仍严格以卡片原文为准，与参考图中文字无关！
"""


def _load_composition_reference_base64():
    """加载构图结构参考图，返回 (base64_string, mime) 或 (None, None)。"""
    for name in COMPOSITION_REFERENCE_IMAGE_NAMES:
        for base_dir in (os.path.dirname(os.path.abspath(__file__)), os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")):
            path = os.path.join(os.path.abspath(base_dir), name)
            if os.path.isfile(path):
                try:
                    with open(path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
                    return b64, mime
                except Exception as e:
                    print(f"[card_image] 读取构图参考图失败 {path}: {e}")
    return None, None


def _load_overlay_style_reference_base64():
    """加载覆盖层风格参考图（app_chat 目录下），返回 (base64_string, mime) 或 (None, None)。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for name in OVERLAY_STYLE_REFERENCE_IMAGE_NAMES:
        path = os.path.join(base_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
            return b64, mime
        except Exception as e:
            print(f"[card_image] 读取覆盖层风格参考图失败 {path}: {e}")
    return None, None


def _get_image_spec_from_claude(content, title, four_color_line, gxx_context_block="", *, text_style='A', multi_incremental_summary=False):
    """
    用 Claude 分析卡片文本，生成一份详尽、可执行的「生图描述」，供 Gemini 严格按描述出图。
    目标：体现 DMT 层次感、细分/灵动/升维，避免直接铺开；对标飞书智能纪要图质量。
    失败或超时返回 None，调用方将回退到通用 V2.5 prompt。
    text_style='B' 时：content 应为文档原文（已截断）；会先 Claude#1 抽取红框级主线结构，再 Claude#2
    用「原文+主线结构」生成生图描述（构图/视觉规范仍按 NKCN，不换飞书皮肤）。
    """
    if not content or not content.strip():
        return None
    is_style_b = (text_style or 'A').upper() == 'B'
    if is_style_b:
        # 风格 B：先分析主线文字（Claude#1），再写生图描述（Claude#2）
        source_body = (content or "").strip()
        outline = _get_meeting_mainline_outline_from_claude(source_body, title)
        if not outline:
            print("[card_image] Claude#1 无结果，Claude#2 将仅依据文档原文（降级）")
        system = """你是专业的信息图与会议纪要图设计专家，对标高质量「飞书妙记」类会议精要图：分层清楚、分块清楚、顺序感强、信息稀疏可扫读。
你的任务：根据「会议主线结构结果」+「文档原文」，输出一份**非常细致、可执行**的「生图描述」。
若另有「构图结构参考图」，只仿其构图层次与留白节奏，禁止套用参考图里的文字内容。
视觉（配色/图标/卡片色条等）遵守用户色调要求与 NKCN 既有专业文档风，不要换飞书皮肤。

【第一优先级：红框级结构文字必须来自「会议主线结构结果」且写准】
图上必须清晰落地这些文字（不得改写成空话、不得串段）：
1) 全图大标题 = main_title
2) 各大段区标题 = section_title
3) 各分卡一句主张标题 = block_title
4) 要点中的关键短语 = key_phrases（用加粗或色块高亮）
核心结论条 = core_conclusions。
文档原文仅用于核对与必要时极少量补全措辞；若与主线结构冲突，以主线结构为准。

【推进感与形态】
- 自上而下严格按 sections 顺序；大段之间用序号/箭头标出讨论先后；充分讨论过的段视觉权重接近，勿压成细窄附录。
- 按各段 layout 执行：columns=并排卡；timeline=横向时间线；table=表格。不要擅自改形态，也不要为「好看」强行统一成固定 2×3。
- 2×3 只是一种常见参考，不是必须模板。

【要点正文必须极短 — 下压信息密度】
- 结构标题已准时，重点砍 points：每条写进生图描述时必须是**简短一句**（尽量≤16字），禁止两行长解释、禁止扩写案例数字。
- 若 Claude#1 的 points 偏长，你在生图描述里须再压缩成短句，不得原样贴长文。

【生图描述必须包含】
1. 空间与构图：顶层标题+结论；其下按 sections 分层分块（columns/timeline/table 按 layout）；留白充足。
2. 文字内容：短、准、可扫读；每卡主张标题 + 极短要点。
3. 禁止：任何会议录音时间戳出现在图上；禁止金句专区、禁止发散、禁止双层高密度堆叠。
4. 图中全部中文；不要页码与元指令入图。

输出要求：直接输出一整份连贯的「生图描述」正文，不要分析过程、不要 Markdown 大标题分隔。描述长度建议 800～1600 字。"""
        system = system + "\n\n" + DOC_SUMMARY_IMAGE_TEXT_STYLE_B_ADDON
        print(
            f"[card_image] Claude#2 生图描述输入=文档原文+主线结构(风格B) "
            f"doc_chars={len(source_body)} outline_chars={len(outline or '')} "
            f"title={(title or '')[:80]!r}"
        )
        outline_block = outline.strip() if outline else "（无）请仅根据文档原文自行抽取，但仍须满足精要主线与禁止时间戳等要求。"
        user_text = """【色调要求】%s

【文档/卡片标题（仅参考）】%s

【会议主线结构结果（Claude#1，红框级文字以此为准）】
%s

【文档原文（核对用）】
%s

请生成可直接交给文生图模型执行的「生图描述」：
- 严格落实主线结构中的大标题、核心结论、区标题、分卡主张标题、关键短语；
- 按 sections 顺序与各段 layout（columns/timeline/table）构图，勿僵化强制 2×3；
- **要点正文每条压缩成简短一句**，下压密度仍保持精准；
- 图上不要出现任何会议时间戳；若附构图参考图：只仿构图与留白，禁止套用其文字。""" % (
            four_color_line,
            (title or "")[:300],
            outline_block,
            source_body,
        )
    else:
        system = """你是专业的信息图与会议纪要图设计专家，参考高质量飞书智能会议纪要图的风格与层次感。
你的任务：仅根据用户给出的「卡片原文」（若用户还提供了一张「构图结构参考图」则参考其构图布局，这是飞书生成的，但禁止参考其内容！），输出一份**非常细致、可执行**的「生图描述」。
若用户提供了构图结构参考图，请观察其版面布局、上中下/左中右层次、区块排布方式与视觉风格，在写生图描述时**适当仿照**这种构图结构（如顶部标题区、中部卡片/区块的排列与连接方式、底部收束区等），使输出描述能指导画图模型生成层次清晰、风格一致的图；但内容仍严格以卡片原文为准，禁止用参考图中的文字内容！！
这份描述将直接交给文生图模型（如 Gemini）按字面执行画图，因此必须事无巨细、无歧义。

【生图描述必须包含】
1. **空间与构图**
   - 明确上/中/下（T/M/D）的层次关系；每一层是什么、为什么这样分。
   - 各区块在画面中的大致位置、占比、与相邻区块的关系（箭头、留白、色带等）。
   - 若有战略引领→核心支柱→具体落地的逻辑，可用上中下构图，并配文关键词明确表达，切忌顺序平铺。

2. **文字内容**
   - 哪些位置放「大标题/副标题」、各段「板块标题」、「核心观点句」、要点列表；具体写清要出现的原文或浓缩句（特别注意保留原文中用到的具体例子，例如某人某事...）。
   - 总结性语句、金句、作者原话/原例子：哪些必须保留原样（若原句超过20字，可以是xxx...xxx这样略掉一些字）、哪些可浓缩，一一说明；确保作者看了都有回味感。
   - 图中所有文字须为中文。不要放页数信息、不要出现整段大段文字。

3. **视觉与风格**
   - 主色/辅色、卡片底色、标签色、图标风格；遵守用户给出的「色调要求」。
   - 适度留白、字体层级（大标题 > 节标题 > 板块标题 > 正文）、关键词高亮方式。
   - 禁止：深色/杂乱背景、元指令文字出现在图面、为对称而虚构内容、内容把图占满无留白呼吸感。

4. **内容忠实与层次**
   - 按原文逻辑顺序组织，不重新排序；通过版面大小、颜色深浅体现「轻重如实」。
   - 段落之间的逻辑（推演/并列/因果）用箭头或留白在描述中写明，便于画图执行。

输出要求：直接输出一整份连贯的「生图描述」正文，不要输出「分析过程」或「建议」，不要用 Markdown 标题分隔，让画图模型能从头到尾按一段话执行。描述长度建议 800～2000 字，确保足够细致，以及完全忠实卡片原文内容，不得缺漏或篡改。"""
        if multi_incremental_summary:
            system = system + "\n\n" + DOC_SUMMARY_IMAGE_MULTI_INCREMENTAL_STYLE_A_ADDON
        card_body = (content or "")[:6000]
        gxx = (gxx_context_block or "").strip()
        if gxx:
            card_section = (
                gxx + "\n\n【卡片正文（生图须展示的文字主体来源，仅此部分写入图中）】\n" + card_body
            )
        else:
            card_section = card_body
        print(
            f"[card_image] Claude 生图描述输入=卡片正文(风格A) chars={len(card_section)} "
            f"multi_incremental={multi_incremental_summary} title={(title or '')[:80]!r}"
        )
        user_text = """【色调要求】%s

【卡片标题】%s

【卡片正文】
%s

请根据以上卡片内容（若下方附有「构图结构参考图」，请结合其构图与层次感<禁止套用参考图中文字内容！！必须忠实卡片内容文本>），输出一份详尽、可执行的「生图描述」（见系统说明），直接用于文生图模型按描述出图。""" % (
            four_color_line,
            (title or "")[:300],
            card_section,
        )

    ref_b64, ref_mime = _load_composition_reference_base64()
    if ref_b64 and ref_mime:
        user_with_ref_hint = user_text + "\n\n" + COMPOSITION_REFERENCE_WHY_GOOD.strip()
        user_content = [
            {"type": "text", "text": user_with_ref_hint},
            {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (ref_mime, ref_b64)}},
        ]
    else:
        user_content = user_text
    try:
        client = OpenAI(
            api_key=CLAUDE_IMAGE_SPEC_API_KEY,
            base_url=CLAUDE_IMAGE_SPEC_BASE_URL,
            default_headers={"x-foo": "true"},
            timeout=CLAUDE_IMAGE_SPEC_TIMEOUT,
        )
        resp = client.chat.completions.create(
            model=_sm('card_image_claude_spec', CLAUDE_IMAGE_SPEC_MODEL),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            max_tokens=4096,
        )
        spec = (resp.choices[0].message.content or "").strip()
        spec_label = 'Claude#2 生图描述' if is_style_b else 'Claude 生图描述'
        if len(spec) < 200:
            print(
                f"[card_image] {spec_label}失败: 输出过短 len={len(spec)} "
                f"title={(title or '')[:80]!r} text_style={text_style}"
            )
            print(f"[card_image] {spec_label}原始输出:\n{spec}")
            return None
        print(
            f"[card_image] {spec_label}成功: len={len(spec)} "
            f"title={(title or '')[:80]!r} text_style={text_style}"
        )
        print(f"[card_image] {spec_label}内容:\n{spec}")
        return spec
    except Exception as e:
        spec_label = 'Claude#2 生图描述' if is_style_b else 'Claude 生图描述'
        print(f"[card_image] {spec_label}失败: {e} title={(title or '')[:80]!r} text_style={text_style}")
        return None


def _card_image_dir(username):
    return os.path.normpath(f"./received_dir/user_raw_file/{username}/cardImage").replace("\\", "/")


def _overlay_qa_composite_card_path(username: str, cid: int) -> str:
    """DMT 质检前用户确认的「底图+覆盖层」合成整卡图（仅本流程使用）。"""
    return os.path.join(_card_image_dir(username), f"{int(cid)}.overlay_qa_composite.png")


def _overlay_qa_composite_wait_key(username: str, cid: int) -> str:
    return f"{username}::{int(cid)}"


def _card_has_image(username, cid):
    d = _card_image_dir(username)
    for ext in IMG_EXTENSIONS:
        p = os.path.join(d, f"{cid}{ext}")
        if os.path.exists(p):
            return True
    return False


def get_cids_with_card_image(username):
    """返回该用户下已有附图的所有卡片 cid 集合（用于列表接口一次性标注）。"""
    out = set()
    d = _card_image_dir(username)
    if not os.path.isdir(d):
        return out
    for name in os.listdir(d):
        base, ext = os.path.splitext(name)
        if ext.lower() not in IMG_EXTENSIONS:
            continue
        try:
            out.add(int(base))
        except ValueError:
            pass
    return out


def _resample_lanczos():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def _normalize_response_base64_to_bytes(base64_string):
    """从模型返回的 base64 字符串得到图片字节；失败返回 None。"""
    try:
        if ',' in base64_string:
            base64_data = base64_string.split(',')[1]
        else:
            base64_data = base64_string
        # 兼容超大 dataURL 在链路中出现的 URL 编码与空格替换
        if "%" in base64_data:
            try:
                base64_data = unquote(base64_data)
            except Exception:
                pass
        base64_data = base64_data.replace(" ", "+")
        base64_data = ''.join(
            c for c in base64_data if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')
        if not base64_data:
            return None
        base64_data = base64_data.rstrip('=')
        pad = 4 - len(base64_data) % 4
        if pad != 4:
            base64_data += '=' * pad
        return base64.b64decode(base64_data)
    except Exception:
        return None


def _pil_from_response_base64(base64_string):
    """将模型返回的 base64 解码为 PIL Image；失败返回 None。"""
    raw = _normalize_response_base64_to_bytes(base64_string)
    if not raw:
        return None
    try:
        return Image.open(io.BytesIO(raw))
    except Exception:
        return None


def _save_base64_image(base64_string, output_path):
    """保存 API 返回的 base64 图片。若返回内容含非 ASCII（如中文说明），仅保留合法 base64 字符再解码。"""
    try:
        image_bytes = _normalize_response_base64_to_bytes(base64_string)
        if not image_bytes:
            print(f"[card_image] 保存失败 {output_path}: 无有效 base64 内容")
            return False
        image = Image.open(io.BytesIO(image_bytes))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        image.save(output_path)
        return True
    except Exception as e:
        print(f"[card_image] 保存失败 {output_path}: {e}")
        return False


def _save_gen_content(username, cid, content, content_title, used_related_block=False):
    """生图成功后保存当时使用的卡片内容及是否用了后置索引关联，供后续迭代对比。"""
    try:
        d = _card_image_dir(username)
        path = os.path.join(d, f"{int(cid)}.gen_content.json")
        os.makedirs(d, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                "content": content or "",
                "contentTitle": content_title or "",
                "used_related_block": bool(used_related_block),
            }, f, ensure_ascii=False)
    except Exception as e:
        print(f"[card_image] 保存 gen_content 失败 cid={cid}: {e}")


def _load_gen_content(username, cid):
    """读取生图时保存的卡片内容，若不存在返回 None。"""
    try:
        d = _card_image_dir(username)
        path = os.path.join(d, f"{int(cid)}.gen_content.json")
        if not os.path.isfile(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[card_image] 读取 gen_content 失败 cid={cid}: {e}")
        return None


def _get_card_image_path(username, cid):
    """返回该卡片已有图片的本地路径（任一种扩展名），不存在返回 None。"""
    d = _card_image_dir(username)
    for ext in IMG_EXTENSIONS:
        p = os.path.join(d, f"{int(cid)}{ext}")
        if os.path.exists(p):
            return os.path.normpath(p).replace("\\", "/")
    return None


def _iterate_backup_path(username, cid, source_abs_path: str) -> str:
    """迭代前备份路径：与当前主图同扩展名（如 3790.prev_iterate.png）。"""
    ext = os.path.splitext(source_abs_path)[1].lower() or '.png'
    if ext not in IMG_EXTENSIONS:
        ext = '.png'
    d = _card_image_dir(username)
    return os.path.normpath(os.path.join(d, f"{int(cid)}.prev_iterate{ext}")).replace("\\", "/")


def _backup_card_image_before_iterate(username, cid) -> bool:
    """在覆盖主图前备份当前图，供「图回退」恢复（仅保留一步）。"""
    cur = _get_card_image_path(username, cid)
    if not cur or not os.path.isfile(cur):
        return False
    try:
        bak = _iterate_backup_path(username, cid, cur)
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        shutil.copy2(cur, bak)
        print(f"[card_image] 迭代前已备份 cid={cid} -> {os.path.basename(bak)}")
        return True
    except Exception as e:
        print(f"[card_image] 迭代前备份失败 cid={cid}: {e}")
        return False


def _find_iterate_backup_path(username, cid):
    """查找是否存在迭代备份文件，返回绝对路径或 None。"""
    d = _card_image_dir(username)
    if not os.path.isdir(d):
        return None
    for ext in IMG_EXTENSIONS:
        p = os.path.join(d, f"{int(cid)}.prev_iterate{ext}")
        if os.path.isfile(p):
            return os.path.normpath(p).replace("\\", "/")
    return None


def _parse_edit_region(obj):
    """解析前端传来的框选区域：{x,y,w,h} 均为相对原图宽高的 0~1 比例。无效则返回 None。"""
    if not obj or not isinstance(obj, dict):
        return None
    try:
        x = float(obj.get('x', 0))
        y = float(obj.get('y', 0))
        w = float(obj.get('w', 0))
        h = float(obj.get('h', 0))
    except (TypeError, ValueError):
        return None

    def _clip(v):
        return max(0.0, min(1.0, float(v)))

    x, y, w, h = _clip(x), _clip(y), _clip(w), _clip(h)
    if x + w > 1.0:
        w = max(0.0, 1.0 - x)
    if y + h > 1.0:
        h = max(0.0, 1.0 - y)
    # 过小视为未选区
    if w < 0.01 or h < 0.01:
        return None
    return {'x': x, 'y': y, 'w': w, 'h': h}


def _format_edit_region_block(region: dict) -> str:
    x, y, w, h = region['x'], region['y'], region['w'], region['h']
    return """

【用户框定的可编辑区域】（坐标已归一化到**输入原图**：原点在左上角，x 向右、y 向下，取值 0~1，为相对整图宽/高的比例）
- 矩形左上角: (%.4f, %.4f)
- 矩形宽、高（占整图比例）: %.4f × %.4f

**硬约束（必须遵守）**：
- 仅在该矩形区域内落实「用户对本次迭代的具体修改要求」以及参考图（若有）所表达的修改意图。
- 该区域**以外**必须与输入原图保持视觉一致（像素级或人眼不可辨差异）：不得重绘、不得整体调色、不得对框外任何文字/图形/线条/色块/背景做修改。
- 输出仍为**完整整图**；框外必须与输入原图一致。
""" % (x, y, w, h)


def _region_to_pixel_box(img_w: int, img_h: int, region: dict):
    """归一化区域 -> 像素整数框 (left, top, right, bottom, crop_w, crop_h)。"""
    x, y, w, h = region['x'], region['y'], region['w'], region['h']
    left = int(round(x * img_w))
    top = int(round(y * img_h))
    cw = int(round(w * img_w))
    ch = int(round(h * img_h))
    left = max(0, min(left, max(0, img_w - 1)))
    top = max(0, min(top, max(0, img_h - 1)))
    cw = max(1, min(cw, img_w - left))
    ch = max(1, min(ch, img_h - top))
    right = left + cw
    bottom = top + ch
    return left, top, right, bottom, cw, ch


def _format_crop_iterate_region_block(region: dict, ow: int, oh: int, left: int, top: int, cw: int, ch: int) -> str:
    """框选裁切迭代：说明归一化坐标与像素框，约束模型只输出裁切同尺寸。"""
    x, y, w, h = region['x'], region['y'], region['w'], region['h']
    return """

【裁切区域在大图中的位置】（供你理解拼接关系）
- 归一化矩形（相对整图宽/高 0~1）：左上 (%.4f, %.4f)，宽 × 高 = %.4f × %.4f。
- 对应像素（整图尺寸 %d×%d）：left=%d, top=%d，裁切宽=%d、高=%d。

**输出硬约束**：
- 你必须输出**与第一张「局部裁切图」完全相同像素尺寸**的单张图片：即 **%d×%d 像素**，内容仅为修改后的该矩形局部。
- **禁止**输出完整大卡片；禁止改变画布宽高或宽高比。
- 修改时请参考第二张「完整原图」中该矩形**周围**的线条、颜色、字体与布局，使边缘在拼回大图时自然衔接、不突兀、无断裂感。
""" % (x, y, w, h, ow, oh, left, top, cw, ch, cw, ch)


def _composite_edited_crop_onto_original(original_path: str, left: int, top: int, crop_w: int, crop_h: int, edited_pil: Image.Image) -> Image.Image:
    """将模型返回的局部图缩放至 (crop_w,crop_h) 后贴回 original_path 对应图像的同一矩形，返回 RGB PIL 图（用于保存）。"""
    base = _open_image_rgba_relaxed(original_path)
    e = edited_pil.convert("RGBA")
    if e.size != (crop_w, crop_h):
        e = e.resize((crop_w, crop_h), _resample_lanczos())
    out = base.copy()
    out.paste(e, (left, top))
    return out.convert("RGB")


def _open_image_rgba_relaxed(path: str) -> Image.Image:
    """
    更稳妥地打开超大图片：
    - 临时放宽 PIL 的像素上限并忽略 DecompressionBombWarning
    - 若 PIL 仍失败，回退 OpenCV 解码
    """
    old_max = Image.MAX_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            Image.MAX_IMAGE_PIXELS = None
            return Image.open(path).convert("RGBA")
    except Exception:
        arr = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if arr is None:
            raise
        if len(arr.shape) == 2:
            rgba = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGBA)
        elif arr.shape[2] == 4:
            rgba = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGBA)
        else:
            rgba = cv2.cvtColor(arr, cv2.COLOR_BGR2RGBA)
        return Image.fromarray(rgba, mode="RGBA")
    finally:
        Image.MAX_IMAGE_PIXELS = old_max


# 四色 R/B/P/G 对应的中文与底色描述
_FOUR_COLOR_DESC = {'R': '红', 'B': '蓝', 'P': '紫', 'G': '绿'}


def _parse_post_index(post_index_str):
    """解析 postIndex 字符串为 cid 列表。"""
    if not post_index_str or not str(post_index_str).strip():
        return []
    try:
        raw = json.loads(post_index_str) if isinstance(post_index_str, str) else post_index_str
        return [int(x) for x in raw if x is not None] if isinstance(raw, list) else []
    except Exception:
        return []


def _snippet_from_content(content, take_middle=False):
    """从一段内容取前100字、后100字；若 take_middle 为 True 再取中间随机位置100字。"""
    s = (content or "").strip()
    if not s:
        return ""
    parts = [s[:100]]
    if len(s) > 100:
        parts.append(s[-100:])
    if take_middle and len(s) > 200:
        start = random.randint(100, max(100, len(s) - 101))
        parts.insert(1, s[start:start + 100])
    return " | ".join(parts)


def _format_gpt_pixel_size(width: int, height: int) -> str:
    w = max(1, int(width))
    h = max(1, int(height))
    return f"{w}x{h}"


def _generate_gpt_edit_image_payload(
    prompt: str,
    api_key: str,
    model: str,
    image_bytes: bytes,
    size: str,
    input_ext: str = "png",
) -> str:
    """OpenAI images.edit 图生图迭代，返回 base64；失败返回空串。"""
    p = (prompt or "").strip()
    if not p or not image_bytes:
        return ""
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=GEMINI_IMAGE_BASE_URL,
            default_headers={"x-foo": "true"},
            timeout=GEMINI_IMAGE_TIMEOUT,
        )
        file_obj = io.BytesIO(image_bytes)
        file_obj.name = f"input.{input_ext}"
        resp = client.images.edit(
            model=model,
            image=file_obj,
            prompt=p[:16000],
            size=size,
        )
        if not getattr(resp, "data", None):
            return ""
        item = resp.data[0]
        b64 = getattr(item, "b64_json", None) or ""
        if isinstance(b64, str) and b64.strip():
            return b64.strip()
        url = getattr(item, "url", None) or ""
        if isinstance(url, str) and url.strip():
            r = requests.get(url.strip(), timeout=min(GEMINI_IMAGE_TIMEOUT, 180))
            r.raise_for_status()
            return base64.b64encode(r.content).decode("ascii")
    except Exception as e:
        print(f"[card_image] {model} images.edit 迭代失败 size={size}: {e}")
    return ""


def _generate_gpt_image_payload(prompt: str, api_key: str, model: str, size: str) -> str:
    """OpenAI images.generate 文生图，返回 base64；失败返回空串。"""
    p = (prompt or "").strip()
    if not p:
        return ""
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=GEMINI_IMAGE_BASE_URL,
            default_headers={"x-foo": "true"},
            timeout=GEMINI_IMAGE_TIMEOUT,
        )
        resp = client.images.generate(
            model=model,
            prompt=p[:16000],
            n=1,
            size=size,
        )
        if not getattr(resp, "data", None):
            return ""
        item = resp.data[0]
        b64 = getattr(item, "b64_json", None) or ""
        if isinstance(b64, str) and b64.strip():
            return b64.strip()
        url = getattr(item, "url", None) or ""
        if isinstance(url, str) and url.strip():
            r = requests.get(url.strip(), timeout=min(GEMINI_IMAGE_TIMEOUT, 180))
            r.raise_for_status()
            return base64.b64encode(r.content).decode("ascii")
    except Exception as e:
        print(f"[card_image] {model} 文生图失败: {e}")
    return ""


def _generate_gemini_chat_image_payload(prompt: str, api_key: str, model: str) -> str:
    """Gemini 兼容 chat.completions 文生图，返回 message.content（多为 base64）。"""
    p = (prompt or "").strip()
    if not p:
        return ""
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=GEMINI_IMAGE_BASE_URL,
            default_headers={"x-foo": "true"},
            timeout=GEMINI_IMAGE_TIMEOUT,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": p}],
            temperature=0.3,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[card_image] {model} chat 文生图失败: {e}")
    return ""


def _generate_initial_card_image_by_provider(
    prompt: str,
    api_key: str,
    image_provider: str = "gpt",
    aspect_ratio: str = "1:1",
) -> str:
    """按用户选择的生图模型与长宽比出图，并按约定链路依次回退。"""
    provider = _normalize_image_provider(image_provider)
    aspect = _normalize_image_aspect_ratio(aspect_ratio)
    full_prompt = _aspect_ratio_prompt_prefix(aspect) + (prompt or "").strip()
    size = _IMAGE_ASPECT_TO_SIZE.get(aspect, "1024x1024")

    if provider == "gemini":
        for model in (_sm('card_image_gemini', GEMINI_IMAGE_MODEL), _sm('card_image_gemini_fallback', GEMINI_IMAGE_MODEL_FALLBACK)):
            res = _generate_gemini_chat_image_payload(full_prompt, api_key, model)
            if res:
                print(f"[card_image] 初次生图成功 provider=gemini model={model} aspect={aspect}")
                return res
        return ""

    for model in (_sm('card_image_gpt', GPT_IMAGE_MODEL), _sm('card_image_gpt_fallback', GPT_IMAGE_MODEL_FALLBACK), _sm('card_image_gpt', GPT_IMAGE_MODEL)):
        res = _generate_gpt_image_payload(full_prompt, api_key, model, size)
        if res:
            print(f"[card_image] 初次生图成功 provider=gpt model={model} aspect={aspect} size={size}")
            return res
    return ""


def _generate_initial_card_image_payload_via_gpt_image2(prompt: str, api_key: str) -> str:
    """兼容旧调用：默认 GPT + 1:1。"""
    return _generate_initial_card_image_by_provider(prompt, api_key, "gpt", "1:1")


def _generate_one_card_image(username, cid, title, content, out_path, use_single_key=False, four_color_type=None,
                             post_index_cids=None, image_quality: str = 'normal', use_claude_spec=None,
                             image_provider: str = 'gpt', image_aspect_ratio: str = '1:1'):
    """普通模式初次生图按 image_provider 选 GPT/Gemini 链路；高清仍走 Gemini native 4K。"""
    allow_claude_spec = ENABLE_CLAUDE_IMAGE_SPEC if use_claude_spec is None else bool(use_claude_spec)
    api_key = GEMINI_IMAGE_API_KEY_SINGLE if use_single_key else GEMINI_IMAGE_API_KEY
    is_s5 = _is_nk2026_s5_card_image(username, title)
    s5_adjust_pct = _calc_nk2026_s5_manual_adjust_percent(content) if is_s5 else 0
    if is_s5:
        print(f"[card_image] NK2026 S5 cid={cid} 手动调整比例={s5_adjust_pct}%")
    provider = _normalize_image_provider(image_provider)
    aspect = _normalize_image_aspect_ratio(image_aspect_ratio)
    four_color_line = ""
    if four_color_type and str(four_color_type).strip().upper() in ('R', 'B', 'P', 'G'):
        color_name = _FOUR_COLOR_DESC.get(str(four_color_type).strip().upper(), '')
        four_color_line = "整体用中浅色调；背景色以较浅的%s色为主。" % color_name
    else:
        four_color_line = "整体用中浅色调。"

    #     prompt = """根据如下文字内容，生成一张信息图/概念图，需同时满足内容与风格要求。
    #
    # 【内容要求】
    # - 完整呈现文字的字面内涵，不遗漏关键信息。
    # - 通过分区布局、结构层次与图示关系等体现文字背后的指向与作者意图/内涵。
    # - 以图为主、文字为辅，图上只保留少量精炼的关键词或短句，大段内容用视觉元素替代，让人一眼先看到的是绘图与结构而非满屏文字。
    #
    # 【风格要求】（必须严格遵守）
    # - 颜色与布局：清爽清晰。背景必须是浅色（白色、浅灰、浅米色或浅的纹理），禁止深色、深蓝深紫、杂乱或高对比的深色背景。主色使用克制、专业的浅色系（如浅蓝、浅绿、米色、灰、少量橙/棕作点缀），避免饱和度过高或大面积深色。
    # - 版式：分区明确、留白充足、逻辑清晰，类似学术或专业信息图、流程图，也可以是手绘风格，便于阅读和讨论。
    # - 整体观感：正式、专业，像高质量教材或汇报用图；不要卡通化、不要科幻发光/霓虹效果、不要抽象混乱或背景杂乱。
    #
    # 【禁止】
    # - 禁止深色或深蓝深紫为主背景。
    # - 禁止杂乱、混沌、高对比发光的视觉风格。
    # - 禁止不正式、不专业的随意或艺术化风格。
    # - 禁止整图以文字为主：禁止把长段文字、多条条目原样铺满画面，禁止「一眼看过去全是字」的排版。
    #
    # 标题：%s
    #
    # 内容：
    # %s
    # """ % ((title or "")[:200], (content or "")[:4000])

    # 后置索引关联卡片内容（若有）
    related_block = ""
    content_ratio_note = ""
    if post_index_cids:
        related_cards = list(
            Card.objects.filter(username=username, cid__in=post_index_cids).only('cid', 'contentTitle', 'content',
                                                                                 'keyWords'))
        take_middle = len(post_index_cids) < 3
        parts = []
        for rc in related_cards:
            snippet = _snippet_from_content(rc.content or "", take_middle=take_middle)
            kw = (getattr(rc, 'keyWords', None) or "").strip() or "（无）"
            if snippet:
                parts.append(
                    "[后置索引卡片 cid=%s 标题:%s 关键词:%s]\n%s" % (rc.cid, (rc.contentTitle or "")[:50], kw[:200], snippet))
        if parts:
            related_block = "\n\n【以下为与当前卡片在内容上存在前后/左右/上下等逻辑关联的后置索引卡片，其部分内容如下。请在图中体现：这些卡片与当前卡片为什么有关联、有什么关联；并将关联信息作为图的一部分。】\n\n" + "\n\n".join(
                parts)
            content_ratio_note = "\n\n【图中信息比例要求】本卡片文字内容基本内涵不遗漏 : 后置索引关联卡片信息 : 背后的指向与作者意图/味道 = 7 : 2 : 1。其中「背后的指向、还原写这段内容的人本身的意图和味道」须综合当前卡片与上述关联内容进行萃取与深化后体现。以图为主，文字只起辅助说明作用，用中文】"

    if related_block:
        prompt = """根据以下当前卡片及与其在内容上存在前后/左右/上下等逻辑关联的后置索引卡片的部分内容，生成一张既细致又综合的图。
要求：既体现当前卡片文字内容基本内涵不遗漏，又体现后置索引与当前卡片的关联及关联原因，并能综合当前卡片与关联内容体现背后的指向、还原写这段内容的人本身的意图和味道。%s%s

【当前卡片】
标题：%s

内容：
%s
%s
""" % (content_ratio_note, "\n" + four_color_line, (title or "")[:200], (content or "")[:6000], related_block)
        if is_s5:
            prompt = _prepend_nk2026_s5_layout_to_prompt(prompt, s5_adjust_pct)
    else:
        # 文档摘要卡：会议类单文档【文件摘要】用文字风格 B；【综合摘要】固定风格 A
        text_style, style_b_source = _resolve_doc_summary_image_plan(username, content, title)
        is_multi_summary = _is_multi_incremental_summary_card_content(content)
        prompt_content = content
        gen_text_style = text_style
        if _is_grading_excerpt_card_content(content, title):
            prompt_content = _grading_excerpt_image_brief(username, content, title)
            print(f"[card_image] 解释精要生图用摘要 chars={len(prompt_content or '')}")
        elif (text_style or 'A').upper() == 'B':
            if style_b_source.strip():
                prompt_content = style_b_source
                print(
                    f"[card_image] 风格B生图描述素材=文档原文 truncated_chars={len(prompt_content)}"
                )
            else:
                print(
                    "[card_image] 风格B但文档原文不可用，Claude/V2.5 仍只能用摘要卡正文（降级）"
                )
        # 可选：先由 Claude 生成详尽生图描述，再让 Gemini 严格按描述出图（提升 DMT 层次感与构图质量）
        prompt = None
        gxx_context = _load_nk2026_s5_gxx_context_block(username, title) if is_s5 else ""
        if allow_claude_spec:
            spec = _get_image_spec_from_claude(
                prompt_content,
                title,
                four_color_line,
                gxx_context_block=gxx_context if is_s5 else "",
                text_style=gen_text_style,
                multi_incremental_summary=is_multi_summary,
            )
            if spec:
                prompt = """你是一位严格按文字描述作图的专业信息图绘制员。请**严格按照**以下「生图描述」生成一张信息图，不要偏离描述中的任何布局、文字位置、层次关系和风格要求。图中所有文字必须为中文。

【生图描述】
%s""" % spec
                if is_s5:
                    prompt = _prepend_nk2026_s5_layout_to_prompt(prompt, s5_adjust_pct)
        if not prompt:
            prompt = _build_v25_card_image_prompt(
                prompt_content,
                four_color_line,
                nk2026_s5=is_s5,
                s5_adjust_percent=s5_adjust_pct,
                text_style=gen_text_style,
                multi_incremental_summary=is_multi_summary,
                grading_hub=_is_grading_result_card_content(content, title),
            )
        elif _is_grading_result_card_content(content, title):
            prompt = prompt.rstrip() + "\n\n" + _GRADING_HUB_IMAGE_ADDON

    try:
        if str(image_quality).strip().lower() == 'high':
            high_prompt = _aspect_ratio_prompt_prefix(aspect) + prompt
            res = _gemini_native_generate_image_from_prompt(GEMINI_IMAGE_API_KEY_HIGH, high_prompt, image_size='4K')
        else:
            res = _generate_initial_card_image_by_provider(
                prompt, api_key, image_provider=provider, aspect_ratio=aspect,
            )
        if not res:
            return False
        ok = _save_base64_image(res, out_path)
        if ok:
            _save_gen_content(username, cid, content, title, used_related_block=bool(related_block))
        return ok
    except Exception as e:
        print(f"[card_image] 生成失败 cid={cid}: {e}")
        return False


def _run_batch(username, cid_list, single_card=False, image_quality: str = 'normal',
               image_provider: str = 'gpt', image_aspect_ratio: str = '1:1'):
    """后台线程：6 并发，失败重试一次；完成后从 generating 中移除。single_card=True 时使用单卡 API Key。"""
    global _card_image_generating
    out_dir = _card_image_dir(username)
    cards_by_cid = {c.cid: c for c in
                    Card.objects.filter(username=username, cid__in=cid_list).only('cid', 'contentTitle', 'content',
                                                                                  'four_color_type', 'postIndex')}

    def do_one(cid):
        if cid not in cards_by_cid:
            with _card_image_lock:
                s = _card_image_generating.get(username)
                if s is not None and cid in s:
                    s.discard(cid)
            return
        card = cards_by_cid[cid]
        out_path = os.path.join(out_dir, f"{cid}.png")
        four_color, post_index_cids, use_claude_spec = _resolve_card_image_gen_options(username, card)
        ok = _generate_one_card_image(username, cid, card.contentTitle, card.content, out_path,
                                      use_single_key=single_card, four_color_type=four_color,
                                      post_index_cids=post_index_cids,
                                      image_quality=image_quality, use_claude_spec=use_claude_spec,
                                      image_provider=image_provider, image_aspect_ratio=image_aspect_ratio)
        if not ok:
            # 同 provider 再试一次
            ok = _generate_one_card_image(username, cid, card.contentTitle, card.content, out_path,
                                          use_single_key=single_card, four_color_type=four_color,
                                          post_index_cids=post_index_cids,
                                          image_quality=image_quality, use_claude_spec=use_claude_spec,
                                          image_provider=image_provider, image_aspect_ratio=image_aspect_ratio)
        # GPT 链路失败后兜底 Gemini（再失败再试一次 Gemini），生图全失败也不阻断后续 HTML
        if not ok and _normalize_image_provider(image_provider) == 'gpt':
            print(f"[card_image] GPT 生图失败，兜底 Gemini cid={cid}")
            ok = _generate_one_card_image(username, cid, card.contentTitle, card.content, out_path,
                                          use_single_key=single_card, four_color_type=four_color,
                                          post_index_cids=post_index_cids,
                                          image_quality=image_quality, use_claude_spec=use_claude_spec,
                                          image_provider='gemini', image_aspect_ratio=image_aspect_ratio)
            if not ok:
                print(f"[card_image] Gemini 兜底仍失败，最终再试 Gemini cid={cid}")
                ok = _generate_one_card_image(username, cid, card.contentTitle, card.content, out_path,
                                              use_single_key=single_card, four_color_type=four_color,
                                              post_index_cids=post_index_cids,
                                              image_quality=image_quality, use_claude_spec=use_claude_spec,
                                              image_provider='gemini', image_aspect_ratio=image_aspect_ratio)
        with _card_image_lock:
            s = _card_image_generating.get(username)
            if s is not None and cid in s:
                s.discard(cid)

    with ThreadPoolExecutor(max_workers=6) as ex:
        future_to_cid = {ex.submit(do_one, cid): cid for cid in cid_list}
        for f in as_completed(future_to_cid):
            try:
                f.result(timeout=GEMINI_IMAGE_TIMEOUT)
            except TimeoutError:
                cid = future_to_cid.get(f)
                with _card_image_lock:
                    s = _card_image_generating.get(username)
                    if s is not None and cid is not None and cid in s:
                        s.discard(cid)
                print(f"[card_image] 生图超时(>{GEMINI_IMAGE_TIMEOUT}s) cid={cid}，已从队列移除")


@csrf_exempt
def card_generate_four_color_images(request):
    """POST: 为本子内所有有 four_color_type 的卡片后台生图，6 并发，已有图跳过，失败重试一次。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        data = __import__('json').loads(request.body)
        username = data.get('username')
        if not username:
            return JsonResponse({'error_num': 1, 'msg': 'missing username'})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': str(e)})

    cards = Card.objects.filter(username=username).values_list('cid', 'four_color_type')
    four_color_cids = [c[0] for c in cards if c[1] and str(c[1]).strip() in ('R', 'B', 'P', 'G')]
    to_do = []
    for cid in four_color_cids:
        if not _card_has_image(username, cid):
            to_do.append(cid)

    with _card_image_lock:
        if username not in _card_image_generating:
            _card_image_generating[username] = set()
        _card_image_generating[username].update(to_do)

    if to_do:
        t = threading.Thread(target=_run_batch, args=(username, to_do), kwargs={"single_card": False})
        t.daemon = True
        t.start()

    return JsonResponse({'error_num': 0, 'msg': 'success', 'queued': len(to_do),
                         'generating_cids': list(_card_image_generating.get(username, set()))})


def card_get_image_generating_status(request):
    """GET: 查询当前正在生图的 cid 列表。params: username"""
    username = request.GET.get('username')
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'missing username'})
    with _card_image_lock:
        generating_cids = list(_card_image_generating.get(username, set()))
    return JsonResponse({'error_num': 0, 'generating_cids': generating_cids})


def _extract_base64_from_response(response_text):
    """从 Gemini 模型响应中提取 base64 图片数据。"""
    if not response_text:
        return None
    # data URI 格式
    pattern1 = r'data:image/[^;]+;base64,([A-Za-z0-9+/=\n]+)'
    match = re.search(pattern1, response_text, re.DOTALL)
    if match:
        return match.group(0).replace('\n', '').strip()
    # 纯 base64 大段
    cleaned = response_text.strip().replace('\n', '').replace(' ', '')
    if len(cleaned) > 1000 and re.match(r'^[A-Za-z0-9+/=]+$', cleaned):
        return cleaned
    return response_text


def _extract_inline_b64_from_gemini_native_json(resp_json: dict) -> str:
    """从 Gemini native generateContent 响应中提取 inlineData.data。"""
    # 尽量严格仿照你给的示例脚本解析路径：candidates[0].content.parts[*].inlineData.data
    candidates = (resp_json or {}).get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
    for part in parts:
        if isinstance(part, dict) and "inlineData" in part:
            inline = part.get("inlineData") or {}
            data_b64 = inline.get("data") or ""
            if data_b64:
                return data_b64
    # 兜底：深度扫描 inlineData.data（防止返回结构略有差异）
    import re as _re

    def _looks_like_b64(s: str) -> bool:
        s2 = s.strip()
        if len(s2) < 200:
            return False
        return bool(_re.match(r'^[A-Za-z0-9+/=\n\r]+$', s2))

    visited = set()

    def _walk(x) -> str:
        if id(x) in visited:
            return ""
        visited.add(id(x))
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "inlineData" and isinstance(v, dict):
                    data_b64 = v.get("data") or ""
                    if isinstance(data_b64, str) and _looks_like_b64(data_b64):
                        return data_b64
                res = _walk(v)
                if res:
                    return res
        elif isinstance(x, list):
            for it in x:
                res = _walk(it)
                if res:
                    return res
        return ""

    return _walk(resp_json) or ""


def _gemini_native_generate_image_from_prompt(api_key: str, prompt: str, image_size: str = "4K") -> str:
    """Gemini native：仅文字 prompt 出图，返回 base64（不带 data: 前缀）。"""
    endpoint = f"/v1beta/models/{_sm('card_image_gemini', GEMINI_IMAGE_MODEL)}:generateContent/"
    url = GEMINI_IMAGE_NATIVE_BASE_URL.rstrip("/") + endpoint

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]},
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"imageSize": image_size},
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=GEMINI_IMAGE_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini native HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    b64 = _extract_inline_b64_from_gemini_native_json(data)
    if not b64:
        try:
            snippet = json.dumps(data, ensure_ascii=False)[:2000]
        except Exception:
            snippet = str(type(data))
        print(f"[card_image] 高清模式未提取到 inlineData.data（仅文字prompt），响应摘要：{snippet}")
    return b64


def _gemini_native_generate_image_from_parts(api_key: str, parts: list, image_size: str = "4K") -> str:
    """Gemini native：文字 + inlineData（图片）组合出图，返回 base64（不带 data: 前缀）。"""
    endpoint = f"/v1beta/models/{_sm('card_image_gemini', GEMINI_IMAGE_MODEL)}:generateContent/"
    url = GEMINI_IMAGE_NATIVE_BASE_URL.rstrip("/") + endpoint

    payload = {
        "contents": [
            {"role": "user", "parts": parts},
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"imageSize": image_size},
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=GEMINI_IMAGE_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini native HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    b64 = _extract_inline_b64_from_gemini_native_json(data)
    if not b64:
        # 输出响应摘要，便于你对齐实际结构（避免刷屏，截断）
        try:
            snippet = json.dumps(data, ensure_ascii=False)[:2000]
        except Exception:
            snippet = str(type(data))
        print(f"[card_image] 高清模式未提取到 inlineData.data，响应摘要：{snippet}")
    return b64


def _iterate_card_image(
    username,
    cid,
    revision_instruction=None,
    reference_image_b64=None,
    reference_image_mime: str = 'image/png',
    image_quality: str = 'normal',
    edit_region=None,
    crop_iterate_include_full_image: bool = True,
    image_provider: str = 'gemini',
):
    """基于已有图片与新旧卡片内容差异，调用 Gemini/GPT 迭代修改图片并保存。
    revision_instruction: 用户点击迭代图时填写的具体修改要求（选填），如「去掉图中xx位置的章节页码信息」「修改图上方大标题变得更实际具体（其余保持不变）」等。
    reference_image_b64: 用户提供的参考图（选填，raw base64），如手绘草图，表示目标区域希望的大致效果或感觉，与文字要求配合使用。
    edit_region: 可选，dict {x,y,w,h} 均为 0~1 归一化框选区域。若提供有效区域：主输入为裁切局部图，可选附带完整原图作上下文，服务端将模型输出的局部图嵌回原图后保存。
    crop_iterate_include_full_image: 框选局部迭代时是否将完整原图一并输入模型（默认 True）。
    image_provider: gpt 或 gemini。GPT 迭代时输出尺寸与裁切图或原图像素一致。
    """
    img_path = _get_card_image_path(username, cid)
    if not img_path:
        print(f"[card_image] 迭代失败 cid={cid}: 无已有图片")
        return False
    # 覆盖主图前备份当前图，供用户「图回退」恢复（仅一步）
    _backup_card_image_before_iterate(username, cid)
    gen = _load_gen_content(username, cid)
    try:
        card = Card.objects.get(username=username, cid=cid)
    except Card.DoesNotExist:
        print(f"[card_image] 迭代失败 cid={cid}: 卡片不存在")
        return False
    current_content = (card.content or "").strip()
    current_title = (card.contentTitle or "").strip()
    old_content = (gen.get("content") or "").strip() if gen else ""
    old_title = (gen.get("contentTitle") or "").strip() if gen else ""

    four_color_type = getattr(card, 'four_color_type', None)
    if _is_nk2026_s5_card_image(username, current_title):
        four_color_type = None
    if four_color_type and str(four_color_type).strip().upper() in ('R', 'B', 'P', 'G'):
        color_name = _FOUR_COLOR_DESC.get(str(four_color_type).strip().upper(), '')
        color_preserve_note = "原图生成时的色调要求：整体用中浅色调；背景色以较浅的%s色为主。迭代时请保持该色调不变。" % color_name
    else:
        color_preserve_note = "原图生成时的色调要求：整体用中浅色调。迭代时请保持该色调不变。"

    use_crop_iterate = bool(edit_region and isinstance(edit_region, dict))
    include_full = bool(crop_iterate_include_full_image)
    left = top = cw = ch = 0
    crop_b64 = None
    full_png_b64 = None

    if use_crop_iterate:
        try:
            pil_orig = Image.open(img_path).convert("RGBA")
        except Exception as e:
            print(f"[card_image] 迭代失败 cid={cid}: 无法打开原图 {e}")
            return False
        ow, oh = pil_orig.size
        left, top, right, bottom, cw, ch = _region_to_pixel_box(ow, oh, edit_region)
        cropped = pil_orig.crop((left, top, right, bottom))
        cbuf = io.BytesIO()
        cropped.save(cbuf, format="PNG")
        crop_b64 = base64.b64encode(cbuf.getvalue()).decode("utf-8")
        if include_full:
            fbuf = io.BytesIO()
            pil_orig.save(fbuf, format="PNG")
            full_png_b64 = base64.b64encode(fbuf.getvalue()).decode("utf-8")
        crop_region_block = _format_crop_iterate_region_block(edit_region, ow, oh, left, top, cw, ch)
        print(
            f"[card_image] 迭代 cid={cid} 框选局部 {cw}x{ch} "
            f"include_full_image={include_full}"
        )
    else:
        try:
            pil_orig_full = Image.open(img_path).convert("RGBA")
            ow, oh = pil_orig_full.size
        except Exception as e:
            print(f"[card_image] 迭代失败 cid={cid}: 无法读取原图尺寸 {e}")
            return False
        with open(img_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')
        ext = os.path.splitext(img_path)[1].lower()
        mime = 'image/png' if ext == '.png' else ('image/jpeg' if ext in ('.jpg', '.jpeg') else 'image/png')
        edit_region_block = ""

    no_old_note = "（未找到历史记录时，请仅根据「当前最新的卡片内容」对原图做适度优化与一致性检查。）" if not gen else ""
    # 原图若是 related_block 分支生成的则用关联图规范，否则用三层信息图规范；无 gen 时默认三层
    used_related = gen and gen.get("used_related_block") is True
    if _is_nk2026_s5_card_image(username, current_title):
        layout_spec = _build_nk2026_s5_iterate_image_spec(
            _calc_nk2026_s5_manual_adjust_percent(current_content)
        )
    else:
        layout_spec = RELATED_BLOCK_IMAGE_SPEC if used_related else ORIGINAL_IMAGE_SPEC
    user_revision_block = ""
    if revision_instruction and (revision_instruction or "").strip():
        user_revision_block = """

【用户对本次迭代的具体修改要求】（请务必在改图时落实，其余部分按上述内容变化与规范处理）
%s
""" % (revision_instruction.strip()[:2000],)
    reference_image_block = ""
    if reference_image_b64 and (reference_image_b64 or "").strip():
        if use_crop_iterate:
            ref_ord = "第三张" if include_full else "第二张"
            reference_image_block = f"""

【用户提供的参考图】（在本模式中为**{ref_ord}图**，仅针对上述**局部裁切区域**）
用户希望该局部修改后大致呈现下图的效果或结构：请将下图视为结构/风格蓝本，结合上方文字要求，在**输出必须与第一张局部裁切图同像素尺寸**的前提下落实。若参考图为草图，请用正式信息图视觉语言重绘，严禁原封不动复制参考图中的文字内容。
"""
        else:
            reference_image_block = """

【用户提供的参考图】
情况1：用户希望图中某区域修改后大致呈现为下面参考图的构图效果，但严禁直接原封不动复制，参考图可能是草图，你需要将其看成“结构蓝本”并用标准的正式图片视觉语言（形状、颜色、线条等）把这个结构重新画出来，力求“复现”（而非“复制”！），请结合上方文字修改要求一起理解，参照并落实。
情况2：用户希望图中只有下面的参考图所在部分（下图是原图的局部截图）要被精准修改，若用户没有其他要求则其他位置内容均保持不变
"""

    if use_crop_iterate:
        if include_full:
            full_image_input_block = (
                "- **第二张图**为「完整原始卡片图」，仅供理解该局部在整版中的位置及与周围文字/线条/色块/底色的关系，使边界衔接自然；"
                "**不要**重画整张，也不要输出与第二张同尺寸的「整卡改版」。"
            )
            task_edge_note = "在**保持与原图该局部及与第二张图中邻接区域风格连续**的前提下落实修改；边缘处的线条与颜色应尽量与周围对齐，便于后端将该局部**无缝拼回**大图。"
        else:
            full_image_input_block = (
                "- 本次**未**附带完整原图：请仅依据第一张局部裁切图与下方文字要求修改；"
                "裁切边缘处的线条/色块/底色须自洽收束，便于服务端拼回原图。"
            )
            task_edge_note = "在**保持该局部内部与原裁切图风格连续**的前提下落实修改；注意裁切边界处视觉自然收束，便于后端无缝拼回。"
        instruction = """你是一位专业的信息图/内容可视化专家。

【输入说明（框选局部迭代）】
- **第一张图**为「局部裁切图」，是你**唯一需要修改并作为图像输出**的范围。请输出**与第一张图完全相同像素尺寸（宽×高 = %d×%d）**的单张图片；画面内容仅为修改后的该矩形局部。**禁止**输出完整大卡片，**禁止**改变画布宽高或宽高比。
%s

%s

【你的任务】
1. 若下方有「生成原图时使用的卡片内容」，则分析「当前内容」相较其有哪些变化（增删改）、这些变化对该**局部**在整图中应如何体现；若无历史内容，则仅根据当前内容判断该局部如何更新。
2. %s
3. **输出**：仅输出**一张**图，且必须与第一张裁切图**完全同像素尺寸**（%d×%d）。

%s
%s
%s
%s

【色调保持】%s

【生成原图时使用的卡片内容】

%s

【当前最新的卡片内容】

%s
""" % (
            cw,
            ch,
            full_image_input_block,
            crop_region_block,
            task_edge_note,
            cw,
            ch,
            user_revision_block,
            reference_image_block,
            no_old_note,
            layout_spec,
            color_preserve_note,
            (old_content or "")[:6000],
            (current_content or "")[:6000],
        )
    else:
        instruction = """你是一位专业的信息图/内容可视化专家。我提供一张**当前卡片已有的信息图**（见下方图片），以及该卡片**生成该图时使用的文字内容**（若有）与**当前最新的卡片文字内容**。

【你的任务】
1. 若下方有「生成原图时使用的卡片内容」，则分析「当前内容」相较其有哪些变化（增删改）、用户为什么这样修改、这些修改对卡片局部和全局的意义是什么；若无历史内容，则仅根据当前内容判断图中可优化之处。
2. 在**保持原图风格、配色与大体布局稳定**的前提下，对原图做**合理、自洽、幅度适中**的迭代修改：仅根据内容变化调整图中需要更新的部分，不要推翻重画，不要产生视觉振荡或底座动摇。
3. 直接输出修改后的**完整图片**（与输入同尺寸或比例一致），图中体现上述内容变化带来的必要更新，其余部分保持稳定。
%s
%s
%s
%s
%s

【色调保持】%s

【生成原图时使用的卡片内容】

%s

【当前最新的卡片内容】

%s

请据此对原图进行迭代修改，输出一张完整图片。""" % (
            user_revision_block,
            reference_image_block,
            edit_region_block,
            no_old_note,
            layout_spec,
            color_preserve_note,
            (old_content or "")[:6000],
            (current_content or "")[:6000],
        )

    if use_crop_iterate:
        content_parts = [
            {"type": "text", "text": "【局部裁切图】（主输入；请只输出与此图同像素尺寸的修改后局部图，不要输出整卡）："},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{crop_b64}"}},
            {"type": "text", "text": instruction},
        ]
        native_parts = [
            {"text": "【局部裁切图】（主输入；请只输出与此图同像素尺寸的修改后局部图，不要输出整卡）："},
            {"inlineData": {"mimeType": "image/png", "data": crop_b64}},
            {"text": instruction},
        ]
        if include_full and full_png_b64:
            content_parts.extend([
                {"type": "text", "text": "【完整原始卡片图】（上下文参考：理解该局部在图中的位置及与周围的线条/颜色/布局关系，便于拼回时自然融合；请勿按整张重绘输出）："},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{full_png_b64}"}},
            ])
            native_parts.extend([
                {"text": "【完整原始卡片图】（上下文参考：理解该局部在图中的位置及与周围的线条/颜色/布局关系，便于拼回时自然融合；请勿按整张重绘输出）："},
                {"inlineData": {"mimeType": "image/png", "data": full_png_b64}},
            ])
    else:
        content_parts = [
            {"type": "text", "text": "【当前卡片已有的信息图】（请基于此图做迭代修改，保持风格与布局稳定）："},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
            {"type": "text", "text": instruction},
        ]
        native_parts = [
            {"text": "【当前卡片已有的信息图】（请基于此图做迭代修改，保持风格与布局稳定）："},
            {"inlineData": {"mimeType": mime, "data": img_b64}},
            {"text": instruction},
        ]

    if reference_image_b64 and (reference_image_b64 or "").strip():
        ref_b64 = reference_image_b64.strip()
        if ref_b64.startswith("data:"):
            ref_url = ref_b64
        else:
            ref_url = f"data:image/png;base64,{ref_b64}"
        ref_label = (
            "【用户提供的参考图】（请结合上文对局部修改要求落实）："
            if use_crop_iterate
            else "【用户提供的参考图】（希望图中某区域修改后大致呈现为下图效果或感觉，请结合上方文字要求落实）："
        )
        content_parts.append({"type": "text", "text": ref_label})
        content_parts.append({"type": "image_url", "image_url": {"url": ref_url}})
        native_parts.append({"text": ref_label})
        native_parts.append({"inlineData": {"mimeType": reference_image_mime or 'image/png', "data": reference_image_b64.strip()}})

    out_path = os.path.join(_card_image_dir(username), f"{cid}.png")
    provider = _normalize_image_provider(image_provider)

    def _finalize_iterate_output(base64_content):
        if use_crop_iterate:
            edited_pil = _pil_from_response_base64(base64_content)
            if edited_pil is None:
                print(f"[card_image] 迭代 cid={cid}: 框选模式无法解码模型返回图片")
                return False
            try:
                final_im = _composite_edited_crop_onto_original(img_path, left, top, cw, ch, edited_pil)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                final_im.save(out_path, "PNG")
                ok = True
            except Exception as ex:
                print(f"[card_image] 迭代 cid={cid}: 框选模式拼回原图失败 {ex}")
                ok = False
        else:
            ok = _save_base64_image(base64_content, out_path)
        if ok:
            _save_gen_content(username, cid, current_content, current_title)
        return ok

    try:
        if provider == "gpt":
            if use_crop_iterate:
                input_bytes = base64.b64decode(crop_b64)
                gpt_size = _format_gpt_pixel_size(cw, ch)
                gpt_prompt = instruction
                input_ext = 'png'
            else:
                with open(img_path, 'rb') as f:
                    input_bytes = f.read()
                gpt_size = _format_gpt_pixel_size(ow, oh)
                gpt_prompt = instruction
                input_ext = 'jpg' if mime == 'image/jpeg' else 'png'
            api_key = GEMINI_IMAGE_API_KEY_SINGLE
            base64_content = ""
            for model in (_sm('card_image_gpt', GPT_IMAGE_MODEL), _sm('card_image_gpt_fallback', GPT_IMAGE_MODEL_FALLBACK), _sm('card_image_gpt', GPT_IMAGE_MODEL)):
                base64_content = _generate_gpt_edit_image_payload(
                    gpt_prompt, api_key, model, input_bytes, gpt_size, input_ext=input_ext,
                )
                if base64_content:
                    print(f"[card_image] 迭代 cid={cid} provider=gpt model={model} size={gpt_size}")
                    break
            if not base64_content:
                print(f"[card_image] 迭代 cid={cid}: GPT images.edit 未返回图片")
                return False
            return _finalize_iterate_output(base64_content)

        if str(image_quality).strip().lower() == 'high':
            # 4K 使用独立 key
            base64_content = _gemini_native_generate_image_from_parts(GEMINI_IMAGE_API_KEY_HIGH, native_parts, image_size='4K')
            if not base64_content:
                print(f"[card_image] 迭代 cid={cid}: 高清模式下未返回图片 base64")
                return False
            return _finalize_iterate_output(base64_content)

        # Gemini 普通：OpenAI 兼容 chat.completions 多模态链路
        client = OpenAI(
            api_key=GEMINI_IMAGE_API_KEY_SINGLE,
            base_url=GEMINI_IMAGE_BASE_URL,
            default_headers={"x-foo": "true"},
            timeout=GEMINI_IMAGE_TIMEOUT,
        )
        response = client.chat.completions.create(
            model=_sm('card_image_gemini', GEMINI_IMAGE_MODEL),
            messages=[
                {
                    "role": "user",
                    "content": content_parts,
                }
            ],
            temperature=0.3,
            max_tokens=8192,
        )
        res = response.choices[0].message.content
        if not res:
            print(f"[card_image] 迭代 cid={cid}: 模型未返回内容")
            return False
        base64_content = _extract_base64_from_response(res)
        if not base64_content:
            print(f"[card_image] 迭代 cid={cid}: 无法从响应提取图片")
            return False
        return _finalize_iterate_output(base64_content)
    except Exception as e:
        print(f"[card_image] 迭代失败 cid={cid}: {e}")
        return False


def _run_iterate(
    username,
    cid,
    revision_instruction=None,
    reference_image_b64=None,
    reference_image_mime: str = 'image/png',
    image_quality: str = 'normal',
    edit_region=None,
    crop_iterate_include_full_image: bool = True,
    image_provider: str = 'gemini',
):
    """后台执行迭代生图，完成后从 generating 中移除。"""
    global _card_image_generating
    try:
        _iterate_card_image(
            username,
            cid,
            revision_instruction=revision_instruction or "",
            reference_image_b64=reference_image_b64,
            reference_image_mime=reference_image_mime,
            image_quality=image_quality,
            edit_region=edit_region,
            crop_iterate_include_full_image=crop_iterate_include_full_image,
            image_provider=image_provider,
        )
    finally:
        with _card_image_lock:
            s = _card_image_generating.get(username)
            if s is not None and cid in s:
                s.discard(cid)


def _parse_bbox_norm(obj):
    """解析归一化 bbox，规则与 Card.vue 覆盖层拖拽一致（PAD=0.05 等），禁止再裁进 [0,1]。"""
    if not obj or not isinstance(obj, dict):
        return None
    try:
        x = float(obj.get('x', 0))
        y = float(obj.get('y', 0))
        w = float(obj.get('w', 0))
        h = float(obj.get('h', 0))
    except (TypeError, ValueError):
        return None
    pad = 0.05
    min_wh = 0.01
    max_wh = 1.0 + 2 * pad
    w = max(min_wh, min(max_wh, w))
    h = max(min_wh, min(max_wh, h))
    x = max(-pad, min(1.0 - w + pad, x))
    y = max(-pad, min(1.0 - h + pad, y))
    if w < 1e-6 or h < 1e-6:
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def _parse_bboxes_norm_list(obj):
    """解析归一化 bbox 列表（用于白色保留区）。"""
    if not obj or not isinstance(obj, list):
        return []
    out = []
    for it in obj:
        if not it or not isinstance(it, dict):
            continue
        try:
            x = float(it.get("x", 0))
            y = float(it.get("y", 0))
            w = float(it.get("w", 0))
            h = float(it.get("h", 0))
        except (TypeError, ValueError):
            continue
        # 保留区使用“精细坐标”解析：不使用 PAD，也不强制最小 0.01，避免小区域被放大导致偏移。
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        w = max(0.0, min(1.0 - x, w))
        h = max(0.0, min(1.0 - y, h))
        if w <= 1e-6 or h <= 1e-6:
            continue
        out.append({"x": x, "y": y, "w": w, "h": h})
    return out


def _bbox_norm_to_px(b, w, h):
    """归一化坐标转像素；不裁进图像边界（与前端按整图比例计算一致，避免与预览错位）。"""
    left = int(round(b["x"] * w))
    top = int(round(b["y"] * h))
    bw = max(1, int(round(b["w"] * w)))
    bh = max(1, int(round(b["h"] * h)))
    return left, top, bw, bh


def _load_base_image_for_overlay(username, cid, base_source="current", base_image_b64=None):
    """加载覆盖层测试所用底图：current/backup 或用户上传(base64)。返回 RGBA PIL。"""
    if base_image_b64 and str(base_image_b64).strip():
        raw = str(base_image_b64).strip()
        if raw.startswith("data:") and "base64," in raw:
            raw = raw.split("base64,", 1)[-1]
        im = _pil_from_response_base64(raw)
        if im is None:
            raise RuntimeError("base_image 解码失败")
        return im.convert("RGBA")
    src = (base_source or "current").strip().lower()
    if src == "custom_saved":
        p = os.path.join(_card_image_dir(username), f"{int(cid)}.overlay_base_custom.png")
        if not os.path.isfile(p):
            raise RuntimeError("无已保存的自定义底图，请先上传或粘贴底图")
        return _open_image_rgba_relaxed(p)
    if src == "custom":
        raise RuntimeError("自定义底图为空，请先上传或粘贴底图")
    if src == "backup":
        p = _find_iterate_backup_path(username, cid)
        if not p:
            raise RuntimeError("无迭代前备份图可用")
    else:
        p = _get_card_image_path(username, cid)
        if not p:
            raise RuntimeError("无当前卡片图可用")
    return _open_image_rgba_relaxed(p)


def _extract_nonwhite_bbox_norm(img_rgba: Image.Image, threshold: int = 240):
    arr = np.array(img_rgba.convert("RGB"))
    mask = np.any(arr < threshold, axis=2)
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return None
    h, w = arr.shape[:2]
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw = max(1, x1 - x0 + 1)
    bh = max(1, y1 - y0 + 1)
    return {
        "x": x0 / float(w),
        "y": y0 / float(h),
        "w": bw / float(w),
        "h": bh / float(h),
    }


def _overlay_history_paths(username, cid):
    d = _card_image_dir(username)
    cur = os.path.join(d, f"{int(cid)}.overlay_current.png")
    prev = os.path.join(d, f"{int(cid)}.overlay_prev.png")
    return cur, prev


def _encode_overlay_png_capped_bytes(overlay_img: Image.Image, max_bytes: int = 2200000):
    """
    将覆盖层图编码为 PNG 并尽量压到 max_bytes 以内。
    策略：optimize + 调色板量化；仍过大时轻微缩放后重试。
    返回: (png_bytes, encoded_pil_rgba)
    """
    src = overlay_img.convert("RGBA")

    def _save_png_bytes(im: Image.Image, optimize=True):
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=optimize)
        return buf.getvalue()

    def _save_quantized_bytes(im: Image.Image, colors: int):
        q = im.convert("RGBA").quantize(colors=max(2, min(256, int(colors))), method=Image.FASTOCTREE, dither=Image.NONE)
        buf = io.BytesIO()
        q.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        # 统一转回 RGBA，避免后续处理模式差异
        dec = Image.open(io.BytesIO(data)).convert("RGBA")
        return data, dec

    # 先原图 optimize
    best_data = _save_png_bytes(src, optimize=True)
    best_img = Image.open(io.BytesIO(best_data)).convert("RGBA")
    if len(best_data) <= max_bytes:
        return best_data, best_img

    # 量化尝试
    for c in (256, 192, 128, 96, 64, 48, 32, 24, 16):
        data, dec = _save_quantized_bytes(src, c)
        if len(data) < len(best_data):
            best_data, best_img = data, dec
        if len(data) <= max_bytes:
            return data, dec

    # 仍超限：轻微缩放 + 量化重试（最多 6 轮）
    work = src
    for _ in range(6):
        cur_size = len(best_data)
        if cur_size <= max_bytes:
            break
        ratio = math.sqrt(max_bytes / float(cur_size))
        ratio = max(0.85, min(0.97, ratio))
        nw = max(1, int(round(work.width * ratio)))
        nh = max(1, int(round(work.height * ratio)))
        if nw == work.width and nh == work.height:
            nw = max(1, work.width - 1)
            nh = max(1, work.height - 1)
        work = work.resize((nw, nh), _resample_lanczos())
        for c in (128, 96, 64, 48, 32, 24, 16):
            data, dec = _save_quantized_bytes(work, c)
            if len(data) < len(best_data):
                best_data, best_img = data, dec
            if len(data) <= max_bytes:
                return data, dec

    return best_data, best_img


# 覆盖层「按清单迭代」时附带卡片原图：体积上限（字节），略低于 1.5MB 便于网关容忍
CARD_IMAGE_OVERLAY_ITERATE_MAX_BYTES = 1_500_000
# 用户确认后的「叠图」作为卡片侧输入时：上限 2MB（质检与迭代共用该图）
CARD_IMAGE_OVERLAY_QA_COMPOSITE_MAX_BYTES = 2_000_000
# 初次生成覆盖层（_generate_overlay_test_layer）：模型未返回图或无有效解码时，固定入参重试（首次 + 下面次数）
OVERLAY_TEST_LAYER_NO_IMAGE_EXTRA_RETRIES = 2


def _sniff_image_mime_from_bytes(data: bytes) -> str:
    """根据文件头识别 PNG / JPEG（卡片原图多为 PNG，少数为 JPG）。"""
    if not data or len(data) < 3:
        return "image/png"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return "image/png"


def _card_file_bytes_to_iterate_b64_mime(
    raw: bytes, max_bytes: int = CARD_IMAGE_OVERLAY_ITERATE_MAX_BYTES
) -> tuple:
    """
    供「按清单迭代覆盖层」附带卡片图：未超限时原样传 PNG 或 JPEG；超限再压为 JPEG。
    返回 (base64_ascii, mime)，失败 ("", "").
    """
    if not raw:
        return "", ""
    try:
        if len(raw) <= max_bytes:
            mime = _sniff_image_mime_from_bytes(raw)
            return base64.b64encode(raw).decode("ascii"), mime
        im = Image.open(io.BytesIO(raw))
        jb = _pil_rgb_to_jpeg_bytes_capped(im.convert("RGB"), max_bytes)
        if not jb:
            return "", ""
        return base64.b64encode(jb).decode("ascii"), "image/jpeg"
    except Exception as ex:
        print(f"[card_image] card_file_to_iterate_b64 skip: {ex}")
        return "", ""


def _pil_rgb_to_jpeg_bytes_capped(im: Image.Image, max_bytes: int = CARD_IMAGE_OVERLAY_ITERATE_MAX_BYTES) -> bytes:
    """RGB 图压到 max_bytes 以内：先降 JPEG 质量，仍超限再略缩小，尽量保留分辨率与可读性。"""
    work = im.convert("RGB")
    last_data = b""
    for _ in range(28):
        for q in range(93, 32, -3):
            subs = 0 if q >= 78 else 2
            buf = io.BytesIO()
            work.save(buf, format="JPEG", quality=int(q), optimize=True, subsampling=subs)
            data = buf.getvalue()
            last_data = data
            if len(data) <= max_bytes:
                return data
        w, h = work.size
        if w <= 360 and h <= 360:
            break
        work = work.resize(
            (max(1, int(round(w * 0.91))), max(1, int(round(h * 0.91)))),
            _resample_lanczos(),
        )
    return last_data


def _extract_checklist_for_fix_prompt(merged_text: str) -> str:
    """汇总模型输出中只取「修正清单」段落给迭代生图，避免夹带前文。若无标记则退回全文。"""
    s = (merged_text or "").strip()
    if not s:
        return ""
    if s == "没问题" or re.match(r"^没问题\s*$", s):
        return "没问题"
    idx = s.find("【修正清单】")
    if idx >= 0:
        return s[idx:].strip()
    return s


def _save_overlay_history_snapshot(username, cid, overlay_img: Image.Image):
    """仅保留两个版本：current(最新) 与 prev(上一次)。"""
    cur, prev = _overlay_history_paths(username, cid)
    os.makedirs(os.path.dirname(cur), exist_ok=True)
    try:
        if os.path.isfile(cur):
            shutil.copy2(cur, prev)
    except Exception:
        pass
    data, _ = _encode_overlay_png_capped_bytes(overlay_img, max_bytes=2200000)
    with open(cur, "wb") as f:
        f.write(data)


def _write_overlay_slot_png(username, cid, overlay_img: Image.Image, slot: str):
    """
    只写入 prev 或 current 之一，不互相拷贝。
    slot: \"prev\" | \"current\"
    """
    cur, prev = _overlay_history_paths(username, cid)
    path = prev if slot == "prev" else cur
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data, _ = _encode_overlay_png_capped_bytes(overlay_img, max_bytes=2200000)
    with open(path, "wb") as f:
        f.write(data)


def _overlay_dark_neutral_pixel_ratio_rgba(im: Image.Image) -> float:
    """
    覆盖层上「待漂白」像素占比（较高不透明区域）。
    包含：① 近纯黑；② 空心描边字、浅灰线等低饱和墨迹（R/G/B 接近，整体偏暗到中灰）。
    仍靠色度跨度排除蓝/紫/红等彩色框线，避免误伤。
    """
    arr = np.array(im.convert("RGBA"))
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    opaque = a >= 200
    total = int(np.sum(opaque))
    if total <= 0:
        return 0.0
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    span = mx.astype(np.int16) - mn.astype(np.int16)
    pure_black = (r <= 36) & (g <= 36) & (b <= 36)
    # 略放宽上限以吃掉浅灰空心描边；span 收紧以免碰到浅彩边
    neutral_ink = (mx <= 138) & (span <= 30)
    ink = (pure_black | neutral_ink) & opaque
    return float(np.sum(ink)) / float(total)


def _bleach_dark_neutral_pixels_on_overlay(
    im: Image.Image,
    rgb_pure: int = 36,
    mx_neutral: int = 138,
    span_neutral: int = 30,
    a_min: int = 200,
) -> Image.Image:
    """
    将墨迹像素改为透明：纯黑 + 空心描边/浅灰线（低饱和）：与 ratio 使用同一套阈值。
    为去除字迹外沿残留，会对命中掩膜做轻微膨胀。
    """
    out = im.convert("RGBA").copy()
    arr = np.array(out)
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    span = mx.astype(np.int16) - mn.astype(np.int16)
    pure = (r <= rgb_pure) & (g <= rgb_pure) & (b <= rgb_pure)
    neutral = (mx <= mx_neutral) & (span <= span_neutral)
    mask = ((pure | neutral) & (a >= a_min)).astype(np.uint8) * 255
    # 扩一圈吃掉浅灰外沿（黑字轮廓常见抗锯齿残留）
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)
    mask_bool = mask > 0
    arr[:, :, 3] = np.where(mask_bool, 0, a)
    return Image.fromarray(arr, mode="RGBA")


def _bleach_overlay_ink_residual_pipeline(im: Image.Image) -> Image.Image:
    """两遍透明化：先清深/中灰墨迹，再提升阈值清掉更浅的黑灰外沿。"""
    out = _bleach_dark_neutral_pixels_on_overlay(im)
    return _bleach_dark_neutral_pixels_on_overlay(
        out, rgb_pure=64, mx_neutral=188, span_neutral=24
    )


CLAUDE_AUDIT_COLOR_RULE_LINE = (
    "【颜色规则】D=红框(#E53935,1.5px) M=蓝框(#1E88E5,1.5px) T=紫框(#8E24AA,1.5px)；"
    "红框/蓝框/紫框左上角为红色「D+序号」/蓝色「M+序号」/紫色「T+序号」标签。嵌套关系：T⊃M⊃D。"
)

CLAUDE_AUDIT_FIRST_LINE = (
    "下列为针对该手稿图一次性生成白底 DMT 标注覆盖层时应遵循的完整要求（仅保留框线与 T/M/D 标签，不含原图正文墨迹）："
)

CLAUDE_AUDIT_TAIL = (
    "\n\n---\n\n"
    "你应认为随图给出的覆盖层即为按上述说明一次性生成的结果。质检时对照本说明检查："
    "T/M/D 标签是否齐全、D/M/T 序号是否连续且无重复与漏号；"
    "若有问题，输出可直接粘贴给其他生图 AI 用于迭代修正的中文指令；"
    "若没有问题，仅输出三个字「没问题」，不要任何其它内容。"
)


def _overlay_instruction_strip_claude_qa_tail_for_image_iterate(inst_claude: str) -> str:
    """
    `_rewrite_overlay_instruction_for_claude_audit` 会在文末追加 CLAUDE_AUDIT_TAIL（含「仅输出三个字没问题」），
    那是给「文字质检」用的；若原样塞进文生图迭代的 revision_instruction，模型会照抄输出「没问题」而不出图。
    本函数在保留前文（颜色规则等改写）的前提下，去掉该尾段。
    """
    t = (inst_claude or "").strip()
    if not t:
        return ""
    # 与 _rewrite 注入的尾段对齐的常见切分点
    for sep in (
        "\n\n---\n\n你应认为随图给出的覆盖层",
        "\n---\n\n你应认为随图给出的覆盖层",
        "\n\n---\n\n你应认为",
        "你应认为随图给出的覆盖层即为按上述说明一次性生成的结果",
    ):
        i = t.find(sep)
        if i >= 0:
            return t[:i].rstrip()
    # 无标准分隔时：按质检尾句兜底截断
    j = t.find("若没有问题，仅输出三个字「没问题」")
    if j >= 0:
        return t[:j].rstrip()
    return t


def _rewrite_overlay_instruction_for_claude_audit(text: str) -> str:
    """
    仅用于发给 Claude 质检：与磁盘上的 overlay_instruction.latest.txt 语义对齐为「一步生成且红框带 D 字」，
    不写回文件。
    """
    s = (text or "").strip()
    if not s:
        return ""
    lines = s.splitlines()
    if lines:
        first = lines[0].strip()
        if first.startswith("原图是一张") or first.startswith("原图为一张"):
            lines[0] = CLAUDE_AUDIT_FIRST_LINE
            s = "\n".join(lines)
    s = re.sub(r"【颜色规则】[^\n\r]*", CLAUDE_AUDIT_COLOR_RULE_LINE, s, count=1)
    s = s.replace("红框左上角仅红色无字矩形块", "红框左上角红底白字D+序号标签")
    s = s.replace("仅红色无字矩形块", "红底白字D+序号标签")
    s = s.replace("不要嵌字", "内嵌纯白D+序号")
    # 兼容新版 DMT 文案中的等价表述
    s = s.replace("**红色底纯白字「D+序号」**标签", "红底白字D+序号标签")
    s = s.replace("红色底纯白字「D+序号」标签", "红底白字D+序号标签")
    s = s.replace(
        "红框左上角仅加红色矩形块（仅红色块，不要嵌字，大小和蓝色M/紫色T标签相同）",
        "红框左上角红底白字「D+序号」标签",
    )
    # 发给 Claude 时去掉「参考图」一句，避免引导联想参考图
    s = re.sub(r"(?m)^\s*风格类似参考图这样，[^\n]*\n?", "", s)
    tail_cut = re.search(r"\n---\s*\n[\s\S]*$", s)
    if tail_cut:
        s = s[: tail_cut.start()] + CLAUDE_AUDIT_TAIL
    else:
        tail2 = re.search(r"\n你最终输出必须[\s\S]*$", s)
        if tail2:
            s = s[: tail2.start()] + CLAUDE_AUDIT_TAIL
        else:
            s = s.rstrip() + CLAUDE_AUDIT_TAIL
    return s.strip()


def _overlay_file_to_payload(path):
    if not path or (not os.path.isfile(path)):
        return None
    im = Image.open(path).convert("RGBA")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
    bbox = _extract_nonwhite_bbox_norm(im, threshold=240) or {"x": 0.2, "y": 0.2, "w": 0.6, "h": 0.6}
    return {"image": data_url, "bbox": bbox}


def _load_overlay_history_payload(username, cid):
    cur, prev = _overlay_history_paths(username, cid)
    items = []
    p = _overlay_file_to_payload(prev)
    c = _overlay_file_to_payload(cur)
    if p:
        items.append(p)
    if c:
        items.append(c)
    return items


def _compose_overlay_by_bbox(
    base_img: Image.Image,
    overlay_img: Image.Image,
    src_bbox_norm: dict,
    dst_bbox_norm: dict,
    threshold: int = 240,
    overlay_alpha: float = 1.0,
    keep_white_regions=None,
):
    base = base_img.convert("RGBA")
    overlay = overlay_img.convert("RGBA")
    bw, bh = base.size
    ow, oh = overlay.size
    sx0, sy0, sw, sh = _bbox_norm_to_px(src_bbox_norm, ow, oh)
    tx0, ty0, tw, th = _bbox_norm_to_px(dst_bbox_norm, bw, bh)

    scale_x = tw / float(max(sw, 1))
    scale_y = th / float(max(sh, 1))
    new_w = max(1, int(round(ow * scale_x)))
    new_h = max(1, int(round(oh * scale_y)))
    transformed = overlay.resize((new_w, new_h), _resample_lanczos())
    place_x = int(round(tx0 - sx0 * scale_x))
    place_y = int(round(ty0 - sy0 * scale_y))

    # 画布为底图与缩放后覆盖层外接并集，避免 place_x/y 为负或超出时 PIL 静默裁切导致与预览不一致
    left = min(0, place_x)
    top = min(0, place_y)
    right = max(bw, place_x + new_w)
    bottom = max(bh, place_y + new_h)
    out_w = max(1, int(right - left))
    out_h = max(1, int(bottom - top))
    base_dx = int(-left)
    base_dy = int(-top)
    ov_dx = int(place_x - left)
    ov_dy = int(place_y - top)

    out_bg = Image.new("RGBA", (out_w, out_h), (255, 255, 255, 255))
    out_bg.paste(base, (base_dx, base_dy), base)

    canvas = Image.new("RGBA", (out_w, out_h), (255, 255, 255, 0))
    canvas.paste(transformed, (ov_dx, ov_dy), transformed)
    arr = np.array(canvas.convert("RGBA"))
    rgb = arr[:, :, :3]
    non_white = np.any(rgb < int(max(0, min(255, threshold))), axis=2)
    keep_mask = None
    if keep_white_regions:
        keep_mask = np.zeros((out_h, out_w), dtype=bool)
        for b in keep_white_regions:
            try:
                # 直接映射到“变换后覆盖层尺寸”，与 transformed/place_x/place_y 完全同坐标系
                dx = ov_dx + int(round(float(b.get("x", 0.0)) * new_w))
                dy = ov_dy + int(round(float(b.get("y", 0.0)) * new_h))
                dw = max(1, int(round(float(b.get("w", 0.0)) * new_w)))
                dh = max(1, int(round(float(b.get("h", 0.0)) * new_h)))
                x0 = max(0, min(out_w, dx))
                y0 = max(0, min(out_h, dy))
                x1 = max(0, min(out_w, dx + dw))
                y1 = max(0, min(out_h, dy + dh))
                if x1 > x0 and y1 > y0:
                    keep_mask[y0:y1, x0:x1] = True
            except Exception:
                continue
        non_white = non_white | keep_mask
    alpha_mul = max(0.0, min(1.0, float(overlay_alpha)))
    # 白色保留区内：
    # 1) 透明像素补成白色不透明；
    # 2) 特别浅（近白）像素提纯为纯白，避免灰白脏边；
    # 3) 其余非透明像素保持原颜色不变。
    if keep_mask is not None:
        light_thr = 244
        very_light_in_keep = (
            keep_mask
            & (arr[:, :, 3] > 0)
            & (arr[:, :, 0] >= light_thr)
            & (arr[:, :, 1] >= light_thr)
            & (arr[:, :, 2] >= light_thr)
        )
        transparent_in_keep = keep_mask & (arr[:, :, 3] <= 0)
        whiten_in_keep = transparent_in_keep | very_light_in_keep
        arr[:, :, 0] = np.where(whiten_in_keep, 255, arr[:, :, 0])
        arr[:, :, 1] = np.where(whiten_in_keep, 255, arr[:, :, 1])
        arr[:, :, 2] = np.where(whiten_in_keep, 255, arr[:, :, 2])
        src_alpha = np.where(transparent_in_keep, 255, arr[:, :, 3]).astype(np.float32)
    else:
        src_alpha = arr[:, :, 3].astype(np.float32)
    alpha = np.where(non_white, src_alpha, 0).astype(np.float32)
    alpha = np.clip(alpha * alpha_mul, 0, 255).astype(np.uint8)
    arr[:, :, 3] = alpha
    layer = Image.fromarray(arr, mode="RGBA")
    out = out_bg
    out.alpha_composite(layer)
    return out.convert("RGB")


def _generate_overlay_test_layer(
    username,
    cid,
    revision_instruction=None,
    reference_image_b64=None,
    reference_image_mime: str = "image/png",
    image_quality: str = "normal",
    base_source: str = "current",
    base_image_b64=None,
):
    base_im = _load_base_image_for_overlay(username, cid, base_source=base_source, base_image_b64=base_image_b64)
    bb = io.BytesIO()
    base_im.save(bb, format="PNG")
    base_b64 = base64.b64encode(bb.getvalue()).decode("utf-8")
    base_mime = "image/png"
    try:
        card = Card.objects.get(username=username, cid=cid)
        current_content = (card.content or "").strip()
    except Exception:
        current_content = ""

    user_block = ""
    if revision_instruction and str(revision_instruction).strip():
        user_block = "\n【用户具体要求】\n%s\n" % (str(revision_instruction).strip()[:2000],)

    instruction = """你是一个“标注覆盖层”提取器。基于输入卡片图，生成一张与输入图同宽高的 PNG 覆盖层，严格遵守：
1) 只保留用户要求保留的内容，去除所有其余的线条、文字、色块，严格按用户要求执行。严禁在覆盖层上编造原图没有的内容！
2) 覆盖层背景必须是纯白，并尽量让新增标注边缘清晰。
3) 提取出的位置、布局原封不动，便于后续叠加回清晰底图。
4) 注意【M级·蓝框】划分须与「用户具体要求」中的层级一致：粒度中等（Middle），不过大或过小。重视圈画、箭头、连线等标注，同方向的连续多个箭头涉及的内容应该划入同一个M，多个箭头指向一个中心或一个中心散出多个箭头所涉及的中心和周边指向及被指向的内容应该被划入同一个M，以及重视手绘草图常见的长横线、长斜线等分隔线——被此类线明显隔开的内容优先划入不同 M；当分隔线本身是斜线时，相关M蓝框边界可/应采用同趋势斜边而非强制横平竖直；关系密切且未被分隔线隔开的元素应落在同一 M 内。
5) 【D级·红框】为最小颗粒：每个独立格子、单个词语文字、圈注对象或一处潦草手写笔画簇等均对应一个独立红框，框线须完整包住目标、不偏移；每个红框左上角必须有红底白字「D+序号」标签（白字清晰、序号连续）；勿画无内容的空红框；勿在覆盖层上抄写原图黑字正文以免错字误导。
%s
【当前卡片内容（供理解）】
%s
""" % (user_block, (current_content or "")[:6000])

    content_parts = [
        {"type": "text", "text": "【原始卡片图】"},
        {"type": "image_url", "image_url": {"url": f"data:{base_mime};base64,{base_b64}"}},
        {"type": "text", "text": instruction},
    ]
    native_parts = [
        {"text": "【原始卡片图】"},
        {"inlineData": {"mimeType": base_mime, "data": base_b64}},
        {"text": instruction},
    ]
    if reference_image_b64 and str(reference_image_b64).strip():
        ref = str(reference_image_b64).strip()
        ref_url = ref if ref.startswith("data:") else f"data:image/png;base64,{ref}"
        content_parts.append({"type": "text", "text": "【参考图】（仅供新增标注样式和结构参考）"})
        content_parts.append({"type": "image_url", "image_url": {"url": ref_url}})
        native_parts.append({"text": "【参考图】（仅供新增标注样式和结构参考）"})
        native_parts.append({"inlineData": {"mimeType": reference_image_mime or "image/png", "data": ref}})

    use_high = str(image_quality).strip().lower() == "high"
    max_tries = 1 + int(max(0, OVERLAY_TEST_LAYER_NO_IMAGE_EXTRA_RETRIES))
    client = None
    if not use_high:
        client = OpenAI(
            api_key=GEMINI_IMAGE_API_KEY_SINGLE,
            base_url=GEMINI_IMAGE_BASE_URL,
            default_headers={"x-foo": "true"},
            timeout=GEMINI_IMAGE_TIMEOUT,
        )

    for attempt in range(max_tries):
        if use_high:
            b64 = _gemini_native_generate_image_from_parts(GEMINI_IMAGE_API_KEY_HIGH, native_parts, image_size="4K")
        else:
            response = client.chat.completions.create(
                model=_sm('card_image_gemini', GEMINI_IMAGE_MODEL),
                messages=[{"role": "user", "content": content_parts}],
                temperature=0.3,
                max_tokens=8192,
            )
            txt = response.choices[0].message.content
            b64 = _extract_base64_from_response(txt) if txt else None

        if b64:
            pil = _pil_from_response_base64(b64)
            if pil is not None:
                return pil.convert("RGBA")

        if attempt + 1 < max_tries:
            print(
                f"[card_image] _generate_overlay_test_layer no_image_or_decode_fail "
                f"retry {attempt + 1}/{max_tries} username={username} cid={cid}"
            )
            time.sleep(1.0 * (attempt + 1))
            continue

        if not b64:
            raise RuntimeError("模型未返回覆盖层图片")
        raise RuntimeError("覆盖层图片解码失败")


def _save_overlay_instruction_text(username, cid, text):
    """保存「生成覆盖层」时文本框内容到 cardImage，保留 latest + 带时间戳历史。"""
    body = (text or "").strip()
    if not body:
        return None
    out_dir = _card_image_dir(username)
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    latest = os.path.join(out_dir, f"{cid}.overlay_instruction.latest.txt")
    hist = os.path.join(out_dir, f"{cid}.overlay_instruction.{ts}.txt")
    for p in (latest, hist):
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
            f.write("\n")
    return {"latest": os.path.basename(latest), "history": os.path.basename(hist)}


def _to_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def _detect_overlay_red_boxes_for_pil(
    username,
    cid,
    pil_rgba: Image.Image,
    scan_min_run_vert=None,
    scan_min_run_horiz=None,
    scan_min_run_diag=None,
    scan_min_area_px=None,
):
    """
    复用“识别红框并编号”的后端流程：生成掩膜、提框、保存 {cid}.overlay_redmask.png。
    返回 dict: {boxes, image_width, image_height, mask_filename}
    """
    pil = pil_rgba.convert("RGBA")
    orig_w, orig_h = pil.size
    if orig_w < 1 or orig_h < 1:
        raise RuntimeError("invalid image size")

    # 大图须在**同一缩小图**上同时做掩膜与提框，否则 v2 路径的 mask_id 与缓存 red_clean 会对不上
    max_side = OVERLAY_REDBOX_MASK_MAX_SIDE
    if max(orig_w, orig_h) > max_side:
        sc = max_side / float(max(orig_w, orig_h))
        nw = max(1, int(round(orig_w * sc)))
        nh = max(1, int(round(orig_h * sc)))
        pil_work = pil.resize((nw, nh), Image.NEAREST)
    else:
        pil_work = pil
        nw, nh = orig_w, orig_h

    fill_mask_u8 = _red_fill_binary_mask_u8_from_rgba(
        pil_work,
        scan_min_run_vert=scan_min_run_vert,
        scan_min_run_horiz=scan_min_run_horiz,
        scan_min_run_diag=scan_min_run_diag,
        scan_min_area_px=scan_min_area_px,
    )
    boxes = _boxes_from_red_mask_filtered(fill_mask_u8, nw, nh)

    if nw != orig_w or nh != orig_h:
        sx = orig_w / float(nw)
        sy = orig_h / float(nh)
        scaled = []
        for b in boxes:
            x = int(round(b["x"] * sx))
            y = int(round(b["y"] * sy))
            w = int(round(b["w"] * sx))
            h = int(round(b["h"] * sy))
            x = max(0, min(x, orig_w - 1))
            y = max(0, min(y, orig_h - 1))
            w = max(1, min(w, orig_w - x))
            h = max(1, min(h, orig_h - y))
            scaled.append({"x": x, "y": y, "w": w, "h": h})
        boxes = scaled

    if (nw, nh) != (orig_w, orig_h):
        up = cv2.resize(fill_mask_u8, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
        mask_save = Image.fromarray(cv2.cvtColor(up, cv2.COLOR_GRAY2RGB), mode="RGB")
    else:
        mask_save = Image.fromarray(cv2.cvtColor(fill_mask_u8, cv2.COLOR_GRAY2RGB), mode="RGB")
    mask_filename = f"{cid}.overlay_redmask.png"
    mask_path = os.path.join(_card_image_dir(username), mask_filename)
    os.makedirs(os.path.dirname(mask_path), exist_ok=True)
    mask_save.save(mask_path, "PNG")
    return {
        "boxes": boxes,
        "image_width": orig_w,
        "image_height": orig_h,
        "mask_filename": mask_filename,
    }


def _paint_d_labels_on_overlay_pil(overlay_rgba: Image.Image, boxes, start_num: int = 1):
    """在覆盖层上按 boxes 直接回写红底白字 D 编号（与前端逻辑一致方向）。"""
    out = overlay_rgba.convert("RGBA").copy()
    dr = ImageDraw.Draw(out)
    font_cache = {}

    def _font(px):
        key = int(max(10, px))
        if key in font_cache:
            return font_cache[key]
        try:
            f = ImageFont.truetype("arial.ttf", key)
        except Exception:
            f = ImageFont.load_default()
        font_cache[key] = f
        return f

    ordered = sorted(
        boxes or [],
        key=lambda b: ((b.get("y", 0) + b.get("h", 0) * 0.5), (b.get("x", 0) + b.get("w", 0) * 0.5)),
    )
    n0 = max(1, int(start_num or 1))
    for i, b in enumerate(ordered):
        x = int(max(0, b.get("x", 0)))
        y = int(max(0, b.get("y", 0)))
        w = int(max(10, b.get("w", 10)))
        h = int(max(10, b.get("h", 10)))
        x1 = x + w
        y1 = y + h
        r = max(2, min(10, int(min(w, h) * 0.16)))
        dr.rounded_rectangle([x, y, x1, y1], radius=r, fill=(211, 52, 49, 255))
        txt = f"D{n0 + i}"
        font_px = max(15, int(h * 0.58))
        fnt = _font(font_px)
        try:
            bbox = dr.textbbox((0, 0), txt, font=fnt)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except Exception:
            tw, th = dr.textsize(txt, font=fnt)
        tx = x + (w - tw) / 2.0
        ty = y + (h - th) / 2.0
        # 按用户要求，文字纯白（不加阴影描边）
        dr.text((tx, ty), txt, font=fnt, fill=(255, 255, 255, 255))
    return out


def _pil_to_base64_png(pil_img: Image.Image) -> str:
    buf = io.BytesIO()
    pil_img.convert("RGBA").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _read_text_file_utf8(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _write_overlay_gemini_audit_log(username: str, cid: int, content: str):
    """写入 Gemini 覆盖层质检日志（latest + 时间戳备份）。"""
    if not username:
        return
    try:
        base_dir = _card_image_dir(username)
        os.makedirs(base_dir, exist_ok=True)
        latest_path = os.path.join(base_dir, f"{int(cid)}.overlay_gemini_audit.latest.txt")
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        hist_path = os.path.join(base_dir, f"{int(cid)}.overlay_gemini_audit.{ts}.txt")
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(content or "")
        with open(hist_path, "w", encoding="utf-8") as f:
            f.write(content or "")
    except Exception as e:
        print(f"[card_image] 写入 Gemini 质检日志失败 cid={cid}: {e}")


def _gemini_overlay_qa_output_incomplete(text: str) -> bool:
    """
    5 路专项 / 1 路汇总：空输出；或除「没问题」类短答复外，全文去尾空白后未以句号（。或英文 .）收尾 →
    视为输出未完成（多为 max_tokens 截断），应重试。
    """
    s = (text or "").strip()
    if not s:
        return True
    if re.match(r"^没问题[。.！!？?\s]*$", s):
        return False
    t = s.rstrip()
    return not (t.endswith("。") or t.endswith("."))


def _call_gemini_overlay_qa_with_retry(
    sys_prompt: str,
    user_text: str,
    card_image_b64: str,
    overlay_current_b64: str,
    tag: str = "overlay_checker",
    extra_max_attempts: int = 0,
    card_image_mime: str = "image/png",
    overlay_image_mime: str = "image/png",
    card_image_title: str = "卡片图",
):
    """Gemini 3.1 Pro 视觉质检（dmxapi）；异常或输出未完成（未以句号收尾）时重试；extra_max_attempts 为在默认次数上追加的次数（汇总【修正清单】多 1 次）。"""
    max_attempts = 1 + int(max(0, DMT_GEMINI_MAX_RETRIES)) + int(max(0, extra_max_attempts))
    for i in range(1, max_attempts + 1):
        try:
            print(f"[card_image] {tag} model={_dmt_gemini_model()} try={i}/{max_attempts}")
            client = _dmt_gemini_client()
            cm = (card_image_mime or "image/png").strip() or "image/png"
            om = (overlay_image_mime or "image/png").strip() or "image/png"
            ct = (card_image_title or "卡片图").strip() or "卡片图"
            content_parts = [
                {"type": "text", "text": user_text},
                {"type": "text", "text": f"【{ct}】"},
                {"type": "image_url", "image_url": {"url": f"data:{cm};base64,{card_image_b64}"}},
                {"type": "text", "text": "【当前覆盖层图】"},
                {"type": "image_url", "image_url": {"url": f"data:{om};base64,{overlay_current_b64}"}},
            ]
            rsp = client.chat.completions.create(
                model=_dmt_gemini_model(),
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": content_parts},
                ],
                temperature=0.1,
                max_tokens=DMT_OVERLAY_QA_MAX_OUTPUT_TOKENS,
            )
            choice = rsp.choices[0]
            fr = getattr(choice, "finish_reason", None)
            out = (choice.message.content or "").strip()
            if out and not _gemini_overlay_qa_output_incomplete(out):
                return out
            if out:
                print(
                    f"[card_image] {tag} incomplete_output(no_period_eof_or_truncated) try={i}/{max_attempts} "
                    f"finish_reason={fr!r} tail={out[-160:]!r}"
                )
        except Exception as e:
            print(f"[card_image] {tag} model={_dmt_gemini_model()} try={i} err={e}")
        if i < max_attempts:
            time.sleep(1.0 * i)
    return ""


def _call_gemini_overlay_checker(
    card_image_b64: str,
    overlay_current_b64: str,
    instruction_text: str,
    username: str = "",
    cid: int = 0,
    card_image_mime: str = "image/png",
    card_image_label: str = "卡片图",
):
    """
    并行 5 路专项质检，再由 1 路 Gemini 3.1 Pro 汇总为最终可贴给生图模型的修正清单。
    每一路均使用同一 Gemini 模型；HTTP 成功但输出为空、或未以句号收尾（「没问题」短答除外）视为截断，自动重试。
    汇总【修正清单】比专项多 1 次重试机会。
    """
    base_inst = (instruction_text or "").strip()[:7000]
    common_suffix_base = (
        "【生成覆盖层图时要求文本】\n" + base_inst + "\n\n"
        "输出规则：\n"
        "- 若该专项未发现问题，仅输出「没问题」；\n"
        "- 若有问题，仅输出条目清单；每条必须包含「位置：…；现状：…；修改为：…」。\n"
        "- 「位置」须写清在整张卡片原图中的相对方位（如：靠上/中下、偏左/偏右、靠近某栏分隔等）；"
        "优先结合「D+序号」红框、「M+序号」蓝框、「T+序号」紫框，说明在该框的哪一侧/角/内部何处。\n"
        "- 若相对位置仍难描述，须给出在原图上的绝对位置（推荐写像素坐标 x,y 及宽高 w,h，"
        "或写清相对整图宽高的归一化 0–1 小数与基准）；须自洽、可复现。\n"
        "- 涉及【D 级·红框 / 红底白字D+序号 】的问题：「位置」不得只写「某 D+序号」或「D 角标旁/右侧红框无标签」等脱离 M 语境的笼统表述；"
        "必须同时写明其所在的「M+序号」蓝框（哪一块 M 版面），以及在该 M 蓝框内的相对方位（如上区/中下区、偏左栏、跨栏中部、紧邻某分隔线一侧等），使读者能对应到具体 M 块内的笔迹或目标。\n"
    )
    common_suffix_mt_range = (
        "- 涉及蓝/紫 M/T 框时：除框内应含哪些元素与位置外，还须说明框边界应如何画；"
        "当边界应贴合原图手绘横线、竖线、斜线、曲线等版面分隔时，须明确写出「贴合哪一段手绘线」"
        "（可结合邻近圈画、箭头、线条等显著特征）；并检查 M 框住的范围是否不多不少：内部元素语义联系密切，"
        "不应漏掉应在同一 M 的 D，也不应把不相关 D 误并入。\n"
        "- 连续同向多个箭头涉及的元素；多个箭头指入/指出同一中心时该中心与箭头另一端多个元素；同一手绘圈内的多个元素："
        "通常应落在同一个 M 蓝框内；但若手绘圈内只有一个元素（如一块字迹簇）通常只需一个 D 红框而非单独 M 蓝框。\n"
        "- M 蓝框/T 紫框边线不要求规则方框，而是要按原图版面灵活采用任意多边形、弧边、局部突出或凹陷等形态，写清边界如何画。\n"
    )
    sys_special = (
        "你是覆盖层专项质检员。你只负责当前被分配的专项，不要扩展到其他专项。"
        "输出必须简洁、可执行；有问题时位置描述须满足用户给定的输出规则。"
    )
    tasks = [
        (
            "d_label",
            "【专项任务】只检查红框 D 标签：\n"
            "1) 是否大量缺失红底白字 D+序号标签；\n"
            "2) 是否出现“有红底块但无清晰 D+序号或字迹不可辨”的情况；\n"
            "3) 是否出现完全无红底 D 标签的情况。\n"
            "凡列出 D 相关问题，每条「位置」须写清：所属「M+序号」蓝框 + 在该 M 内的相对方位 +（若有助于定位）对应 D+序号或红框与邻接笔迹关系；禁止仅用「D+序号」或「D 角标旁」等不交代 M 块的描述。\n"
            + common_suffix_base,
        ),
        (
            "mt_seq",
            "【专项任务】只检查蓝/紫标签与序号：\n"
            "1) 蓝色 M+序号 标签遗漏；\n"
            "2) 紫色 T+序号 标签遗漏；\n"
            "3) M/T 序号重复；\n"
            "4) M/T 序号漏号或跳号。\n"
            "有问题时须点明在全图及（若可）对应 M/T 框附近的方位。\n"
            + common_suffix_base,
        ),
        (
            "bbox_pos",
            "【专项任务】只检查框体位置偏差：\n"
            "- 有无红色 D 框未完全包住目标元素（如一个字迹簇）/偏移明显/尺寸不合适；\n"
            "- 有无蓝色 M 框内应该多框入某个或某些Dxx（序号）/应该少框入某部分。\n"
            "每条须写清该框在全图及相对邻近 D/M/T 框或显著笔迹的位置关系。\n"
            + common_suffix_base
            + common_suffix_mt_range,
        ),
        (
            "empty_missing",
            "【专项任务】只检查框体有无冗余与缺失：\n"
            "- 多余空框（框内无应标注内容）；\n"
            "- 缺少框（该加框的位置没加）；\n"
            "- 有标签但没有对应颜色的框线。\n"
            "须用原图相对方位或可复现坐标描述「哪里多/哪里缺」。\n"
            + common_suffix_base,
        ),
        (
            "m_edge_line",
            "【专项任务】只检查 M 版面边界与原图分隔线的一致性 + M 框范围正确性：\n"
            "- 原图手绘斜线/横线/曲线所表示的分隔关系，是否被蓝框边界忠实表达；\n"
            "- 该斜边/横边/曲线是否贴合对应位置，不可明显错位。\n"
            "- M 框住的 D 范围是否不多不少（内部元素语义联系密切）；是否漏掉应并入同一 M 的 D，或误并入不相关 D。\n"
            "- 连续同向多个箭头、多箭头共中心、同一手绘圈中的多个元素，是否被归并到同一 M；若手绘圈仅单元素则应偏向 D 而非独立 M。\n"
            "- M/T 框线允许非矩形，应按原图采用多边形、弧边、局部突出/凹陷等形态。\n"
            "须明确蓝框边界应沿哪条手绘线走向、与邻近 M 序号或网格的关系；必要时写绝对坐标。\n"
            + common_suffix_base
            + common_suffix_mt_range,
        ),
    ]

    outputs = {}
    card_label = (card_image_label or "卡片图").strip() or "卡片图"
    card_tag = f"【{card_label}】"
    with ThreadPoolExecutor(max_workers=5) as ex:
        fut_map = {
            ex.submit(
                _call_gemini_overlay_qa_with_retry,
                sys_special,
                user_text,
                card_image_b64,
                overlay_current_b64,
                f"overlay_checker_{tag}",
                0,
                card_image_mime,
                "image/png",
                card_label,
            ): tag
            for tag, user_text in tasks
        }
        for fut in as_completed(fut_map):
            tag = fut_map[fut]
            try:
                outputs[tag] = (fut.result() or "").strip()
            except Exception as e:
                print(f"[card_image] overlay_checker_{tag} future err={e}")
                outputs[tag] = ""

    non_empty = [v for v in outputs.values() if v]
    if not non_empty:
        return ""
    if all(v.strip() == "没问题" for v in non_empty) and len(non_empty) == len(tasks):
        return "没问题"

    merge_sys = (
        f"你是覆盖层质检汇总助手。你已同时看到{card_tag}与【当前覆盖层图】。你只输出两种结果之一：\n"
        "1) 若对照原图与覆盖层后综合判断无明显问题，仅输出「没问题」；\n"
        "2) 否则，仅输出可直接粘贴给生图模型的「修正清单」（见用户消息中的格式骨架）。\n"
        f"汇总时须：逐条对照{card_tag}核验 5 路专项结论，筛除误报（专项误判、而对照原图与覆盖层实际正确者须删除不写入清单）；\n"
        "对确有问题项合并同类项、去冗余表述，每条仍须保留可执行细节（相对或绝对位置、现状、修改方式），禁止输出分析过程。\n"
        "硬性限量：【修正清单】下「1)～4)」每一大类中，以「-」开头的子项合计最多 3 条；要保留最明显、最重要、对版面影响最大的问题"
    )
    merge_user = (
        "请把下面 5 个专项质检结果汇总成一份最终修正清单。\n"
        f"你必须对照上方的{card_tag}与【当前覆盖层图】交叉验证：明显误报的专项结论不要写入清单；"
        "确有问题才写入，并合并同类、表述简洁但不丢关键细节（位置须含全图相对方位或 D/M/T 框参照等，"
        "难描述时写绝对坐标；M蓝框/T紫框须写清框线边界如何画、是否需贴合原图手绘分隔线等；"
        "各 M 框范围是否不多不少：语义联系密切元素应同框，不相关元素不应并入，连续同向多箭头、多箭头共中心、同一手绘圈内"
        "...多个元素通常应同一 M，单元素(例如单个字迹簇)圈注通常应仅 D 框。蓝色M/紫色T框线允许非矩形，如不规则多边形、弧边、局部突出/凹陷等）。\n"
        "【D 与 M 绑定】凡写到 D 红框 / 红底白字D+序号标签 ，必须同时写清「在哪个 M+序号蓝框里、该 M 内什么相对位置」；不得只写「Dxx」或「D+序号右侧红框无标签」等脱离 M 块的描述。\n"
        "【重要】每一大类（1)～4)）下以「-」开头的子项各不得超过 3 条，优先写最明显、最重要、最重大的问题；其余从略。\n"
        "最终格式严格为：\n"
        "【修正清单】\n"
        "1) 标签与样式修正\n"
        "- [问题类型] 位置：...；现状：...；修改为：...\n"
        "2) 序号修正\n"
        "- [问题类型] 位置：...；现状：...；修改为：...\n"
        "3) 框体修正（位置/多余/缺失）\n"
        "- [位置偏差] 位置：...；现状：...；修改为：...\n"
        "- [多余空框] 位置：...；现状：...；修改为：删除该框及对应标签\n"
        "- [缺少框] 位置：...；现状：...；修改为：补上对应颜色与序号标签并包住具体内容\n"
        "4) M版面边界与分隔线一致性修正\n"
        "- [M边界一致性] 位置：...；现状：...；修改为：...\n"
        "M蓝框边界需忠实体现原图分隔线（含斜线/横线/曲线等手绘分隔线）。\n"
        "若 5 个专项都等于「没问题」，或经你核验均无真实问题，最终仅输出「没问题」。\n\n"
        "【专项结果-1 红框D标签】\n" + (outputs.get("d_label") or "（空）") + "\n\n"
        "【专项结果-2 蓝/紫标签与序号】\n" + (outputs.get("mt_seq") or "（空）") + "\n\n"
        "【专项结果-3 框体位置偏差】\n" + (outputs.get("bbox_pos") or "（空）") + "\n\n"
        "【专项结果-4 多余空框/缺少框】\n" + (outputs.get("empty_missing") or "（空）") + "\n\n"
        "【专项结果-5 M边界与分隔线一致性】\n" + (outputs.get("m_edge_line") or "（空）")
    )
    merged = _call_gemini_overlay_qa_with_retry(
        merge_sys,
        merge_user,
        card_image_b64,
        overlay_current_b64,
        tag="overlay_checker_merge",
        extra_max_attempts=1,
        card_image_mime=card_image_mime,
        overlay_image_mime="image/png",
    )
    final_text = (merged or "").strip()
    try:
        log_text = (
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"CID: {int(cid) if cid else cid}\n"
            "流程: Gemini3.1并行5路专项质检 + 1路汇总\n"
            + "\n" + ("=" * 72) + "\n"
            + "【专项结果-1 红框D标签】\n"
            + (outputs.get("d_label") or "（空）")
            + "\n\n" + ("=" * 72) + "\n"
            + "【专项结果-2 蓝/紫标签与序号】\n"
            + (outputs.get("mt_seq") or "（空）")
            + "\n\n" + ("=" * 72) + "\n"
            + "【专项结果-3 框体位置偏差】\n"
            + (outputs.get("bbox_pos") or "（空）")
            + "\n\n" + ("=" * 72) + "\n"
            + "【专项结果-4 多余空框/缺少框】\n"
            + (outputs.get("empty_missing") or "（空）")
            + "\n\n" + ("=" * 72) + "\n"
            + "【专项结果-5 M边界与分隔线一致性】\n"
            + (outputs.get("m_edge_line") or "（空）")
            + "\n\n" + ("=" * 72) + "\n"
            + "【最终汇总清单（给 Gemini）】\n"
            + (final_text or "（空）")
            + "\n"
        )
        _write_overlay_gemini_audit_log(username, cid, log_text)
    except Exception as e:
        print(f"[card_image] 组装 Gemini 质检日志失败 cid={cid}: {e}")
    return final_text


def _iterate_overlay_test_layer_image(
    overlay_image_b64,
    revision_instruction=None,
    reference_image_b64=None,
    reference_image_mime: str = "image/png",
    image_quality: str = "normal",
    edit_region=None,
    card_image_b64=None,
    card_iterate_max_bytes=None,
    card_image_label: str = "卡片原图",
):
    src = _pil_from_response_base64(overlay_image_b64)
    if src is None:
        raise RuntimeError("overlay image decode failed")
    src = src.convert("RGBA")
    src_bytes, src_comp = _encode_overlay_png_capped_bytes(src, max_bytes=2200000)
    src_b64 = base64.b64encode(src_bytes).decode("utf-8")
    card_inline_b64 = ""
    card_inline_mime = "image/png"
    cap = (
        int(card_iterate_max_bytes)
        if card_iterate_max_bytes is not None
        else int(CARD_IMAGE_OVERLAY_ITERATE_MAX_BYTES)
    )
    if card_image_b64 and str(card_image_b64).strip():
        try:
            s = str(card_image_b64).strip()
            raw = _normalize_response_base64_to_bytes(s)
            if raw and len(raw) <= cap:
                card_inline_b64 = base64.b64encode(raw).decode("ascii")
                card_inline_mime = _sniff_image_mime_from_bytes(raw)
            elif raw:
                cp = Image.open(io.BytesIO(raw))
                jb = _pil_rgb_to_jpeg_bytes_capped(cp.convert("RGB"), cap)
                if jb:
                    card_inline_b64 = base64.b64encode(jb).decode("ascii")
                    card_inline_mime = "image/jpeg"
        except Exception as ex:
            print(f"[card_image] iterate_overlay card image prep skip: {ex}")
    use_crop_iterate = bool(edit_region and isinstance(edit_region, dict))
    left = top = cw = ch = 0
    crop_b64 = ""
    full_b64 = ""
    crop_region_block = ""
    if use_crop_iterate:
        ow, oh = src_comp.size
        left, top, right, bottom, cw, ch = _region_to_pixel_box(ow, oh, edit_region)
        crop = src_comp.crop((left, top, right, bottom))
        cbuf = io.BytesIO()
        crop.save(cbuf, format="PNG")
        crop_b64 = base64.b64encode(cbuf.getvalue()).decode("utf-8")
        fbuf = io.BytesIO()
        src_comp.save(fbuf, format="PNG")
        full_b64 = base64.b64encode(fbuf.getvalue()).decode("utf-8")
        crop_region_block = _format_crop_iterate_region_block(edit_region, ow, oh, left, top, cw, ch)
    user_block = ""
    if revision_instruction and str(revision_instruction).strip():
        user_block = "\n【用户对覆盖层的修改要求】\n%s\n" % (str(revision_instruction).strip()[:12000],)
    ref_block = ""
    if reference_image_b64 and str(reference_image_b64).strip():
        ref_block = "\n【参考图】请参考其标注样式与结构，但不要复制无关底图内容。\n"

    if use_crop_iterate:
        instruction = """你在迭代一张“白底标注覆盖层”图片（不是完整卡片底图）。请严格遵守：
【输入说明（框选局部迭代）】
- 第一张图为「局部裁切覆盖层」，是你唯一需要修改并作为图像输出的范围。输出必须与第一张图完全同像素尺寸（%d×%d）。
- 第二张图为「完整覆盖层图」，仅用于理解该局部在全局中的位置及与周围线条/框体/标签关系，禁止按整张重绘输出。

【任务约束】
1) 只迭代第一张图对应的局部覆盖层；输出仅为该局部，不得输出整图。
2) 不要引入底图正文与装饰；背景必须保持纯白，便于后续抠除白底。
3) 局部边缘要与第二张图中的邻接线条自然衔接，便于服务端无缝拼回。
4) 输出硬约束：必须是 %d×%d 像素，且保持覆盖层风格稳定（红蓝紫框线、标签风格一致）。
%s
%s
%s
""" % (cw, ch, cw, ch, user_block, ref_block, crop_region_block)
    else:
        instruction = """你在迭代一张“白底标注覆盖层”图片（不是完整卡片底图）。请严格遵守：
1) 仅输出白底覆盖层，保留/更新新增标注元素（框、箭头、标签、文字标注）。
2) 不要引入底图正文与装饰；背景必须保持纯白，便于后续抠除白底。
3) 若给定可编辑区域，只在该区域内调整，区域外尽量保持不变。
4) 输出仍应与输入覆盖层同尺寸或同比例。
%s
%s
%s
""" % (user_block, ref_block, "")

    if use_crop_iterate:
        content_parts = []
        native_parts = []
        if card_inline_b64:
            card_title = (card_image_label or "卡片原图").strip() or "卡片原图"
            content_parts.extend(
                [
                    {"type": "text", "text": f"【{card_title}】（对照位置与分隔线；输出仍以局部覆盖层为准）"},
                    {"type": "image_url", "image_url": {"url": f"data:{card_inline_mime};base64,{card_inline_b64}"}},
                ]
            )
            native_parts.extend(
                [
                    {"text": f"【{card_title}】（对照位置与分隔线；输出仍以局部覆盖层为准）"},
                    {"inlineData": {"mimeType": card_inline_mime, "data": card_inline_b64}},
                ]
            )
        content_parts.extend(
            [
                {"type": "text", "text": "【局部裁切覆盖层】（主输入；请仅输出同尺寸局部图）"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{crop_b64}"}},
                {"type": "text", "text": instruction},
                {"type": "text", "text": "【完整覆盖层图】（上下文参考；勿整图重绘输出）"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{full_b64}"}},
            ]
        )
        native_parts.extend(
            [
                {"text": "【局部裁切覆盖层】（主输入；请仅输出同尺寸局部图）"},
                {"inlineData": {"mimeType": "image/png", "data": crop_b64}},
                {"text": instruction},
                {"text": "【完整覆盖层图】（上下文参考；勿整图重绘输出）"},
                {"inlineData": {"mimeType": "image/png", "data": full_b64}},
            ]
        )
    else:
        content_parts = []
        native_parts = []
        if card_inline_b64:
            card_title = (card_image_label or "卡片原图").strip() or "卡片原图"
            content_parts.extend(
                [
                    {"type": "text", "text": f"【{card_title}】（对照版面位置、分隔线与圈注；迭代输出以「当前覆盖层」为准）"},
                    {"type": "image_url", "image_url": {"url": f"data:{card_inline_mime};base64,{card_inline_b64}"}},
                ]
            )
            native_parts.extend(
                [
                    {"text": f"【{card_title}】（对照版面位置、分隔线与圈注；迭代输出以「当前覆盖层」为准）"},
                    {"inlineData": {"mimeType": card_inline_mime, "data": card_inline_b64}},
                ]
            )
        content_parts.extend(
            [
                {"type": "text", "text": "【当前覆盖层】（白底标注图）"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{src_b64}"}},
                {"type": "text", "text": instruction},
            ]
        )
        native_parts.extend(
            [
                {"text": "【当前覆盖层】（白底标注图）"},
                {"inlineData": {"mimeType": "image/png", "data": src_b64}},
                {"text": instruction},
            ]
        )
    if reference_image_b64 and str(reference_image_b64).strip():
        ref = str(reference_image_b64).strip()
        ref_url = ref if ref.startswith("data:") else f"data:image/png;base64,{ref}"
        content_parts.append({"type": "text", "text": "【参考图】"})
        content_parts.append({"type": "image_url", "image_url": {"url": ref_url}})
        native_parts.append({"text": "【参考图】"})
        native_parts.append({"inlineData": {"mimeType": reference_image_mime or "image/png", "data": ref}})

    if str(image_quality).strip().lower() == "high":
        out_b64 = _gemini_native_generate_image_from_parts(GEMINI_IMAGE_API_KEY_HIGH, native_parts, image_size="4K")
    else:
        client = OpenAI(
            api_key=GEMINI_IMAGE_API_KEY_SINGLE,
            base_url=GEMINI_IMAGE_BASE_URL,
            default_headers={"x-foo": "true"},
            timeout=GEMINI_IMAGE_TIMEOUT,
        )
        response = client.chat.completions.create(
            model=_sm('card_image_gemini', GEMINI_IMAGE_MODEL),
            messages=[{"role": "user", "content": content_parts}],
            temperature=0.3,
            max_tokens=8192,
        )
        txt = response.choices[0].message.content
        out_b64 = _extract_base64_from_response(txt) if txt else None
    if not out_b64:
        raise RuntimeError("模型未返回覆盖层图片")
    out = _pil_from_response_base64(out_b64)
    if out is None:
        raise RuntimeError("迭代覆盖层解码失败")
    out = out.convert("RGBA")
    if use_crop_iterate:
        if out.size != (cw, ch):
            out = out.resize((cw, ch), _resample_lanczos())
        merged = src_comp.copy()
        merged.paste(out, (left, top))
        return merged.convert("RGBA")
    if out.size != src_comp.size:
        out = out.resize(src_comp.size, _resample_lanczos())
    return out


@csrf_exempt
def card_iterate_card_image(request):
    """POST: 基于已有图片迭代生图。body: username, cid。要求该卡片已有图且存在 gen_content（无则仍可迭代，用当前内容作对比）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        data = __import__('json').loads(request.body)
        username = data.get('username')
        cid = data.get('cid')
        revision_instruction = (data.get('revision_instruction') or "").strip() or None
        reference_image = data.get('reference_image')  # 选填，data URL 或 raw base64
        reference_image_mime = 'image/png'
        image_quality = (data.get('image_quality') or 'normal').strip().lower()
        if image_quality not in ('normal', 'high'):
            image_quality = 'normal'
        image_provider = _normalize_image_provider(data.get('image_provider') or 'gemini')
        if reference_image and isinstance(reference_image, str) and reference_image.strip():
            ref = reference_image.strip()
            if ref.startswith("data:") and "base64," in ref:
                reference_image_b64 = ref.split("base64,", 1)[-1]
                # data URL 形如：data:image/jpeg;base64,xxxx
                try:
                    prefix = ref.split("base64,", 1)[0]  # data:image/jpeg;base64
                    mime_part = prefix.split(":", 1)[1]  # image/jpeg;base64
                    reference_image_mime = mime_part.split(";")[0] or reference_image_mime
                except Exception:
                    pass
            else:
                reference_image_b64 = ref
        else:
            reference_image_b64 = None
        edit_region = _parse_edit_region(data.get('edit_region'))
        crop_iterate_include_full_image = True
        if data.get('crop_iterate_include_full_image') is not None:
            crop_iterate_include_full_image = _to_bool(data.get('crop_iterate_include_full_image'))
        elif data.get('include_full_image') is not None:
            crop_iterate_include_full_image = _to_bool(data.get('include_full_image'))
        if not username or cid is None:
            return JsonResponse({'error_num': 1, 'msg': 'missing username or cid'})
        cid = int(cid)
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': str(e)})

    if not _card_has_image(username, cid):
        return JsonResponse({'error_num': 1, 'msg': '该卡片暂无图片，请先使用「新生图」或「卡片生图」'})

    with _card_image_lock:
        if username not in _card_image_generating:
            _card_image_generating[username] = set()
        if cid in _card_image_generating[username]:
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

    with _card_image_lock:
        _card_image_generating[username].add(cid)
    t = threading.Thread(
        target=_run_iterate,
        args=(
            username,
            cid,
            revision_instruction,
            reference_image_b64,
            reference_image_mime,
            image_quality,
            edit_region,
            crop_iterate_include_full_image,
            image_provider,
        ),
        daemon=True,
    )
    t.start()
    return JsonResponse({
        'error_num': 0, 'msg': 'success',
        'generating_cids': list(_card_image_generating.get(username, set())),
    })


@csrf_exempt
def card_generate_overlay_test_layer(request):
    """独立测试模式：后台异步生成白底覆盖层，不影响现有迭代逻辑。"""
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        data = __import__("json").loads(request.body)
        username = data.get("username")
        cid = int(data.get("cid"))
        revision_instruction = (data.get("revision_instruction") or "").strip() or None
        reference_image = data.get("reference_image")
        dmt_generated = _to_bool(data.get("dmt_generated"))
        d_label_start = data.get("d_label_start")
        base_source = (data.get("base_source") or "current").strip().lower()
        base_image = data.get("base_image")
        image_quality = (data.get("image_quality") or "normal").strip().lower()
        if image_quality not in ("normal", "high"):
            image_quality = "normal"
        reference_image_mime = "image/png"
        if reference_image and isinstance(reference_image, str) and reference_image.strip():
            ref = reference_image.strip()
            if ref.startswith("data:") and "base64," in ref:
                reference_image_b64 = ref.split("base64,", 1)[-1]
                try:
                    prefix = ref.split("base64,", 1)[0]
                    mime_part = prefix.split(":", 1)[1]
                    reference_image_mime = mime_part.split(";")[0] or reference_image_mime
                except Exception:
                    pass
            else:
                reference_image_b64 = ref
        else:
            reference_image_b64 = None
        # 全局：若用户未提供参考图，兜底使用 app_chat/版面DMT化覆盖层风格参考图.png
        if not reference_image_b64:
            auto_ref_b64, auto_ref_mime = _load_overlay_style_reference_base64()
            if auto_ref_b64:
                reference_image_b64 = auto_ref_b64
                reference_image_mime = auto_ref_mime or reference_image_mime
                print(f"[card_image] overlay_generate cid={cid} ref_source=app_default")
            else:
                print(f"[card_image] overlay_generate cid={cid} ref_source=none_default_missing")
        else:
            print(f"[card_image] overlay_generate cid={cid} ref_source=user")
        d_label_start = 1 if d_label_start in (None, "") else max(1, int(d_label_start))
        print(
            f"[card_image] overlay_generate cid={cid} dmt_generated={1 if dmt_generated else 0} "
            f"d_label_start={d_label_start}"
        )
        if not username:
            return JsonResponse({"error_num": 1, "msg": "missing username"})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})

    try:
        saved_txt = _save_overlay_instruction_text(username, cid, revision_instruction or "")
        if saved_txt:
            print(
                f"[card_image] overlay_generate cid={cid} instruction_saved "
                f"latest={saved_txt.get('latest')} history={saved_txt.get('history')}"
            )
        else:
            print(f"[card_image] overlay_generate cid={cid} instruction_empty_skip")
    except Exception as e:
        print(f"[card_image] 保存覆盖层要求文本失败 cid={cid}: {e}")

    def _job():
        def _set_progress(step, total, msg):
            with _card_image_lock:
                cur = _overlay_test_jobs.get((username, cid), {"status": "running", "msg": "running"})
                cur.update(
                    {
                        "status": "running",
                        "msg": "running",
                        "progress_step": int(step),
                        "progress_total": int(total),
                        "progress_msg": str(msg),
                    }
                )
                _overlay_test_jobs[(username, cid)] = cur
        try:
            total_steps = 6 if dmt_generated else 2
            _set_progress(1, total_steps, "生成覆盖层")
            # 复用「无图/解码失败重试」同级的次数：对连接类错误再补一层外层重试，避免偶发网络抖动直接失败。
            conn_max_tries = 1 + int(max(0, OVERLAY_TEST_LAYER_NO_IMAGE_EXTRA_RETRIES))
            overlay = None
            for conn_try in range(1, conn_max_tries + 1):
                try:
                    overlay = _generate_overlay_test_layer(
                        username=username,
                        cid=cid,
                        revision_instruction=revision_instruction,
                        reference_image_b64=reference_image_b64,
                        reference_image_mime=reference_image_mime,
                        image_quality=image_quality,
                        base_source=base_source,
                        base_image_b64=base_image,
                    )
                    break
                except Exception as gen_ex:
                    msg = str(gen_ex or "").lower()
                    is_conn = (
                        ("connection" in msg)
                        or ("timeout" in msg)
                        or ("timed out" in msg)
                        or ("remoteprotocolerror" in msg)
                        or ("temporarily unavailable" in msg)
                    )
                    if (not is_conn) or conn_try >= conn_max_tries:
                        raise
                    print(
                        f"[card_image] overlay_generate cid={cid} connection_retry "
                        f"{conn_try}/{conn_max_tries} err={gen_ex}"
                    )
                    time.sleep(1.0 * conn_try)
            if overlay is None:
                raise RuntimeError("生成覆盖层失败：连接异常重试后仍失败")
            base_im = _load_base_image_for_overlay(username, cid, base_source=base_source, base_image_b64=base_image)
            if overlay.size != base_im.size:
                overlay = overlay.resize(base_im.size, _resample_lanczos())
            data_bytes, overlay_comp = _encode_overlay_png_capped_bytes(overlay, max_bytes=2200000)
            bbox = _extract_nonwhite_bbox_norm(overlay_comp, threshold=240) or {"x": 0.2, "y": 0.2, "w": 0.6, "h": 0.6}
            out_for_client = overlay
            det = None
            auto_msg = "success"
            data_url = "data:image/png;base64," + base64.b64encode(data_bytes).decode("utf-8")
            # 仅 DMT 触发场景：先做红框检测并编号；该阶段产物（去黑残留后）写入 prev，供前端对齐确认与前后对比
            if dmt_generated:
                try:
                    _set_progress(2, total_steps, "识别红框并编号")
                    print(f"[card_image] overlay_generate cid={cid} branch=dmt_autodetect start")
                    det = _detect_overlay_red_boxes_for_pil(username, cid, overlay)
                    labeled = _paint_d_labels_on_overlay_pil(overlay, det.get("boxes") or [], start_num=d_label_start)
                    labeled_for_qa = labeled
                    dark_ratio_labeled = _overlay_dark_neutral_pixel_ratio_rgba(labeled_for_qa)
                    if dark_ratio_labeled > 0.010:
                        print(f"[card_image] overlay_generate cid={cid} bleach_labeled dark_ratio={dark_ratio_labeled:.4f}")
                        labeled_for_qa = _bleach_overlay_ink_residual_pipeline(labeled_for_qa)
                    else:
                        print(f"[card_image] overlay_generate cid={cid} bleach_labeled_skip dark_ratio={dark_ratio_labeled:.4f} (<0.010)")
                    _write_overlay_slot_png(username, cid, labeled_for_qa, "prev")
                    print(f"[card_image] overlay_generate cid={cid} overlay_prev=write_after_d_label_bleach")

                    _set_progress(3, total_steps, "等待对齐并准备质检")
                    wait_key = _overlay_qa_composite_wait_key(username, cid)
                    composite_path = _overlay_qa_composite_card_path(username, cid)
                    await_bytes, await_comp = _encode_overlay_png_capped_bytes(labeled_for_qa, max_bytes=2200000)
                    await_data_url = "data:image/png;base64," + base64.b64encode(await_bytes).decode("utf-8")
                    await_bbox = _extract_nonwhite_bbox_norm(await_comp, threshold=240) or bbox
                    if os.path.isfile(composite_path):
                        try:
                            os.remove(composite_path)
                        except Exception:
                            pass
                    wait_event = threading.Event()
                    wait_secs = 8 * 60
                    with _card_image_lock:
                        _overlay_qa_align_events[wait_key] = wait_event
                        cur = _overlay_test_jobs.get((username, cid), {"status": "running", "msg": "running"})
                        cur.update(
                            {
                                "status": "awaiting_qa_composite",
                                "msg": "awaiting_qa_composite",
                                "progress_step": 3,
                                "progress_total": total_steps,
                                "progress_msg": "请先在弹窗对齐覆盖层并确认",
                                "overlay_image": await_data_url,
                                "overlay_bbox": await_bbox,
                            }
                        )
                        _overlay_test_jobs[(username, cid)] = cur
                    wait_event.wait(wait_secs)
                    with _card_image_lock:
                        _overlay_qa_align_events.pop(wait_key, None)

                    _set_progress(3, total_steps, "Gemini 并行专项质检并汇总")
                    card_img_path = _get_card_image_path(username, cid)
                    card_img_b64 = ""
                    card_img_mime = "image/png"
                    card_iterate_b64 = ""
                    card_source = "card_original"
                    card_label = "卡片图"
                    if os.path.isfile(composite_path):
                        try:
                            with open(composite_path, "rb") as f:
                                raw_comp = f.read()
                            if raw_comp:
                                card_img_b64 = base64.b64encode(raw_comp).decode("ascii")
                                card_img_mime = _sniff_image_mime_from_bytes(raw_comp)
                                card_iterate_b64, _ = _card_file_bytes_to_iterate_b64_mime(
                                    raw_comp, max_bytes=CARD_IMAGE_OVERLAY_QA_COMPOSITE_MAX_BYTES
                                )
                                card_source = "qa_composite"
                                card_label = "叠加当前覆盖层后的卡片图"
                        except Exception as comp_ex:
                            print(f"[card_image] overlay_generate cid={cid} read qa_composite failed: {comp_ex}")
                    if not card_img_b64 and card_img_path and os.path.isfile(card_img_path):
                        with open(card_img_path, "rb") as f:
                            raw_card = f.read()
                        card_img_b64 = base64.b64encode(raw_card).decode("utf-8")
                        card_img_mime = _sniff_image_mime_from_bytes(raw_card)
                        card_iterate_b64, _ = _card_file_bytes_to_iterate_b64_mime(raw_card)
                    if not card_iterate_b64:
                        print(f"[card_image] overlay_generate cid={cid} card_iterate_b64 empty source={card_source}")
                    overlay_current_b64 = _pil_to_base64_png(labeled_for_qa)
                    inst_latest = _read_text_file_utf8(
                        os.path.join(_card_image_dir(username), f"{cid}.overlay_instruction.latest.txt")
                    )
                    inst_for_claude = _rewrite_overlay_instruction_for_claude_audit(inst_latest)
                    check_text = _call_gemini_overlay_checker(
                        card_image_b64=card_img_b64 or overlay_current_b64,
                        overlay_current_b64=overlay_current_b64,
                        instruction_text=inst_for_claude,
                        username=username,
                        cid=cid,
                        card_image_mime=card_img_mime,
                        card_image_label=card_label,
                    )
                    final_overlay = labeled_for_qa
                    if (check_text or "").strip() != "没问题":
                        _set_progress(4, total_steps, "Gemini 迭代修正覆盖层")
                        # 绝不能用含 CLAUDE_AUDIT_TAIL 的 inst_for_claude 原文：其中「仅输出三个字没问题」是给文字质检的，会误导文生图迭代
                        inst_for_fix = _overlay_instruction_strip_claude_qa_tail_for_image_iterate(
                            inst_for_claude.strip() if inst_for_claude.strip() else inst_latest.strip()
                        )
                        if not inst_for_fix.strip():
                            inst_for_fix = (inst_latest or "").strip()
                        checklist_only = _extract_checklist_for_fix_prompt(check_text)
                        fix_instruction = (
                            (inst_for_fix + "\n\n" if inst_for_fix else "")
                            + "【重要约束】\n"
                            + "仅需要输出按下方清单迭代修正后的覆盖层图，不要输出任何文字说明。\n"
                            + "本次仅按检查结果修正问题，必须基于已有的覆盖层图修正，切忌另起炉灶。\n\n"
                            + "【Gemini检查结果：需修正清单】\n"
                            + (
                                checklist_only
                                if checklist_only
                                else (check_text or "请检查并修正 D/M/T 标签、序号、框体位置与 M 边界分隔线一致性问题")
                            )
                        )
                        try:
                            fixed = _iterate_overlay_test_layer_image(
                                overlay_image_b64=_pil_to_base64_png(labeled_for_qa),
                                revision_instruction=fix_instruction,
                                reference_image_b64=None,
                                reference_image_mime="image/png",
                                image_quality=image_quality,
                                edit_region=None,
                                card_image_b64=card_iterate_b64 or None,
                                card_image_label=("叠加当前覆盖层后的卡片图" if card_source == "qa_composite" else "卡片原图"),
                            )
                            if fixed is not None:
                                final_overlay = fixed.convert("RGBA")
                        except Exception as fix_e:
                            # 迭代失败不应被误记为“红框识别失败”，保留已完成的 labeled 继续后续流程
                            print(f"[card_image] overlay_generate cid={cid} gemini_fix_failed: {fix_e}; fallback=labeled")
                    _set_progress(5, total_steps, "清理残留并保存")
                    dark_ratio = _overlay_dark_neutral_pixel_ratio_rgba(final_overlay)
                    if dark_ratio > 0.010:
                        print(f"[card_image] overlay_generate cid={cid} bleach dark_ratio={dark_ratio:.4f}")
                        final_overlay = _bleach_overlay_ink_residual_pipeline(final_overlay)
                    else:
                        print(f"[card_image] overlay_generate cid={cid} bleach_skip dark_ratio={dark_ratio:.4f} (<0.010)")
                    # DMT：最后一步写入 overlay_current
                    _write_overlay_slot_png(username, cid, final_overlay, "current")
                    out_for_client = final_overlay
                    data_bytes, overlay_comp = _encode_overlay_png_capped_bytes(out_for_client, max_bytes=2200000)
                    data_url = "data:image/png;base64," + base64.b64encode(data_bytes).decode("utf-8")
                    bbox = _extract_nonwhite_bbox_norm(overlay_comp, threshold=240) or {"x": 0.2, "y": 0.2, "w": 0.6, "h": 0.6}
                    auto_msg = f"overlay_generate_success_with_autodetect:{len(det.get('boxes') or [])}"
                    print(
                        f"[card_image] overlay_generate cid={cid} branch=dmt_autodetect done "
                        f"boxes={len(det.get('boxes') or [])} prev=raw current=write2_final"
                    )
                except Exception as det_e:
                    print(f"[card_image] 覆盖层 DMT 后处理失败 cid={cid}: {det_e}")
                    # 失败时在末尾写回 current（同样按需漂白）
                    o_fb = overlay
                    if _overlay_dark_neutral_pixel_ratio_rgba(o_fb) > 0.010:
                        o_fb = _bleach_overlay_ink_residual_pipeline(o_fb)
                    try:
                        _write_overlay_slot_png(username, cid, o_fb, "current")
                    except Exception:
                        pass
                    out_for_client = o_fb
                    data_bytes, overlay_comp = _encode_overlay_png_capped_bytes(out_for_client, max_bytes=2200000)
                    data_url = "data:image/png;base64," + base64.b64encode(data_bytes).decode("utf-8")
                    bbox = _extract_nonwhite_bbox_norm(overlay_comp, threshold=240) or {"x": 0.2, "y": 0.2, "w": 0.6, "h": 0.6}
                    auto_msg = "overlay_generate_success_autodetect_failed"
                    print(f"[card_image] overlay_generate cid={cid} branch=dmt_autodetect fallback_plain_history=1")
            else:
                _set_progress(2, total_steps, "回写 overlay_prev/current")
                _save_overlay_history_snapshot(username, cid, overlay)
                print(f"[card_image] overlay_generate cid={cid} branch=plain_generate_history=1")
            _set_progress(total_steps, total_steps, "完成")
            with _card_image_lock:
                _overlay_test_jobs[(username, cid)] = {
                    "status": "success",
                    "msg": auto_msg,
                    "overlay_image": data_url,
                    "overlay_bbox": bbox,
                    "base_source": base_source,
                    "auto_detect": det,
                    "progress_step": total_steps,
                    "progress_total": total_steps,
                    "progress_msg": "完成",
                }
        except Exception as ex:
            with _card_image_lock:
                _overlay_test_jobs[(username, cid)] = {"status": "error", "msg": str(ex)}
            print(f"[card_image] 生成覆盖层失败 cid={cid}: {ex}")
        finally:
            with _card_image_lock:
                _overlay_qa_align_events.pop(_overlay_qa_composite_wait_key(username, cid), None)
                s = _card_image_generating.get(username)
                if s is not None and cid in s:
                    s.discard(cid)

    with _card_image_lock:
        if username not in _card_image_generating:
            _card_image_generating[username] = set()
        if cid in _card_image_generating[username]:
            return JsonResponse({"error_num": 1, "msg": "generating", "generating": True})
        total_steps = 6 if dmt_generated else 2
        _overlay_test_jobs[(username, cid)] = {
            "status": "running",
            "msg": "running",
            "progress_step": 0,
            "progress_total": total_steps,
            "progress_msg": "排队中",
        }
        _card_image_generating[username].add(cid)
    t = threading.Thread(target=_job, daemon=True)
    t.start()
    return JsonResponse({"error_num": 0, "msg": "queued"})


@csrf_exempt
def card_get_overlay_test_layer_status(request):
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "GET only"})
    try:
        username = request.GET.get("username")
        cid = int(request.GET.get("cid"))
        if not username:
            return JsonResponse({"error_num": 1, "msg": "missing username"})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    with _card_image_lock:
        job = _overlay_test_jobs.get((username, cid))
    if not job:
        return JsonResponse({"error_num": 0, "status": "idle"})
    return JsonResponse({"error_num": 0, **job})


@csrf_exempt
def card_overlay_submit_qa_composite(request):
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        data = __import__("json").loads(request.body)
        username = data.get("username")
        cid = int(data.get("cid"))
        image = (data.get("image") or "").strip()
        if not username:
            return JsonResponse({"error_num": 1, "msg": "missing username"})
        if not image:
            return JsonResponse({"error_num": 1, "msg": "missing image"})
        raw = _normalize_response_base64_to_bytes(image)
        if not raw:
            return JsonResponse({"error_num": 1, "msg": "invalid image"})
        if len(raw) > CARD_IMAGE_OVERLAY_QA_COMPOSITE_MAX_BYTES:
            try:
                rb = _pil_rgb_to_jpeg_bytes_capped(
                    Image.open(io.BytesIO(raw)).convert("RGB"),
                    CARD_IMAGE_OVERLAY_QA_COMPOSITE_MAX_BYTES,
                )
                if rb:
                    raw = rb
            except Exception as ex:
                print(f"[card_image] overlay qa composite compress failed cid={cid}: {ex}")
        out_path = _overlay_qa_composite_card_path(username, cid)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(raw)
        wkey = _overlay_qa_composite_wait_key(username, cid)
        with _card_image_lock:
            ev = _overlay_qa_align_events.get(wkey)
            if ev:
                ev.set()
            cur = _overlay_test_jobs.get((username, cid))
            if cur and cur.get("status") == "awaiting_qa_composite":
                cur.update({"status": "running", "msg": "running", "progress_msg": "已收到对齐图，继续质检"})
                _overlay_test_jobs[(username, cid)] = cur
        return JsonResponse({"error_num": 0, "msg": "success"})
    except Exception as ex:
        return JsonResponse({"error_num": 1, "msg": str(ex)})


@csrf_exempt
def card_overlay_skip_qa_composite(request):
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        data = __import__("json").loads(request.body)
        username = data.get("username")
        cid = int(data.get("cid"))
        if not username:
            return JsonResponse({"error_num": 1, "msg": "missing username"})
        wkey = _overlay_qa_composite_wait_key(username, cid)
        with _card_image_lock:
            ev = _overlay_qa_align_events.get(wkey)
            if ev:
                ev.set()
            cur = _overlay_test_jobs.get((username, cid))
            if cur and cur.get("status") == "awaiting_qa_composite":
                cur.update({"status": "running", "msg": "running", "progress_msg": "已取消对齐，回退原图继续质检"})
                _overlay_test_jobs[(username, cid)] = cur
        return JsonResponse({"error_num": 0, "msg": "success"})
    except Exception as ex:
        return JsonResponse({"error_num": 1, "msg": str(ex)})


@csrf_exempt
def card_get_overlay_test_base_image(request):
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "GET only"})
    try:
        username = request.GET.get("username")
        cid = int(request.GET.get("cid"))
        base_source = (request.GET.get("base_source") or "current").strip().lower()
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    try:
        base_im = _load_base_image_for_overlay(username, cid, base_source=base_source, base_image_b64=None)
        buf = io.BytesIO()
        base_im.convert("RGB").save(buf, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")
        return JsonResponse({"error_num": 0, "msg": "success", "base_image": data_url, "base_source": base_source})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})


@csrf_exempt
def card_save_overlay_custom_base_image(request):
    """保存自定义底图到 cardImage，供后续应用覆盖层时按文件读取。"""
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        # 1) 首选 multipart 文件上传（稳定，不受超长 base64 JSON 影响）
        f = request.FILES.get("base_file")
        if f is not None:
            username = request.POST.get("username")
            cid = int(request.POST.get("cid"))
            if not username:
                return JsonResponse({"error_num": 1, "msg": "missing username"})
            file_bytes = f.read()
            try:
                # 优先 PIL（标准格式）
                base_im = Image.open(io.BytesIO(file_bytes)).convert("RGBA")
            except Exception:
                # PIL 失败时尝试 OpenCV 兜底（对某些剪贴板图片更稳）
                base_im = None
                try:
                    arr = np.frombuffer(file_bytes, dtype=np.uint8)
                    cv_img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                    if cv_img is not None:
                        if len(cv_img.shape) == 2:
                            rgba = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2RGBA)
                        elif cv_img.shape[2] == 4:
                            rgba = cv2.cvtColor(cv_img, cv2.COLOR_BGRA2RGBA)
                        else:
                            rgba = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGBA)
                        base_im = Image.fromarray(rgba, mode="RGBA")
                except Exception:
                    base_im = None
                if base_im is None:
                    # 文件流仍失败时，回退使用同请求附带的 base_image（若有）
                    base_image = request.POST.get("base_image")
                    if base_image and isinstance(base_image, str):
                        base_im = _load_base_image_for_overlay(username, cid, base_source="custom", base_image_b64=base_image)
                    else:
                        return JsonResponse({"error_num": 1, "msg": "base_file 解码失败"})
        else:
            # 2) 兼容旧 JSON 模式
            username = request.POST.get("username")
            cid_raw = request.POST.get("cid")
            base_image = request.POST.get("base_image")
            if not username or not cid_raw or not base_image:
                try:
                    data = __import__("json").loads(request.body)
                    username = data.get("username")
                    cid_raw = data.get("cid")
                    base_image = data.get("base_image")
                except Exception:
                    pass
            try:
                cid = int(cid_raw)
            except Exception:
                return JsonResponse({"error_num": 1, "msg": "missing username/cid/base_image"})
            if not username or not base_image or not isinstance(base_image, str):
                return JsonResponse({"error_num": 1, "msg": "missing username/cid/base_image"})
            base_im = _load_base_image_for_overlay(username, cid, base_source="custom", base_image_b64=base_image)

        out_path = os.path.join(_card_image_dir(username), f"{int(cid)}.overlay_base_custom.png")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        base_im.save(out_path, "PNG")
        return JsonResponse(
            {
                "error_num": 0,
                "msg": "success",
                "base_source": "custom_saved",
                "base_image_file": os.path.basename(out_path),
            }
        )
    except Exception as e:
        print(f"[card_image] 保存自定义底图失败 cid={cid}: {e}")
        return JsonResponse({"error_num": 1, "msg": str(e)})


@csrf_exempt
def card_get_overlay_test_history(request):
    """读取覆盖层历史：仅返回 prev/current 两个版本（若存在）。"""
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "GET only"})
    try:
        username = request.GET.get("username")
        cid = int(request.GET.get("cid"))
        if not username:
            return JsonResponse({"error_num": 1, "msg": "missing username"})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    try:
        items = _load_overlay_history_payload(username, cid)
        return JsonResponse({"error_num": 0, "msg": "success", "items": items})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})


@csrf_exempt
def card_save_overlay_layer_file(request):
    """
    将前端编辑后的覆盖层 PNG 写回 cardImage 目录。
    target: prev -> {cid}.overlay_prev.png；current -> {cid}.overlay_current.png
    与「上一步/下一步」一致：历史长度为 2 且索引 0 表示上一版(prev)，索引 1 表示当前(current)；仅 1 条时写 current。
    """
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        data = __import__("json").loads(request.body)
        username = data.get("username")
        cid = int(data.get("cid"))
        overlay_image = data.get("overlay_image")
        target = (data.get("target") or "current").strip().lower()
        if target not in ("prev", "current"):
            target = "current"
        if not username or not overlay_image or not isinstance(overlay_image, str):
            return JsonResponse({"error_num": 1, "msg": "missing username or overlay_image"})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})

    if not _card_has_image(username, cid):
        return JsonResponse({"error_num": 1, "msg": "该卡片暂无图片"})

    cur_path, prev_path = _overlay_history_paths(username, cid)
    out_path = prev_path if target == "prev" else cur_path

    overlay_b64 = overlay_image.strip()
    if overlay_b64.startswith("data:") and "base64," in overlay_b64:
        overlay_b64 = overlay_b64.split("base64,", 1)[-1]

    with _card_image_lock:
        if username not in _card_image_generating:
            _card_image_generating[username] = set()
        if cid in _card_image_generating[username]:
            return JsonResponse({"error_num": 1, "msg": "generating", "generating": True})
        _card_image_generating[username].add(cid)

    try:
        pil = _pil_from_response_base64(overlay_b64)
        if pil is None:
            return JsonResponse({"error_num": 1, "msg": "overlay image decode failed"})
        data_bytes, out_comp = _encode_overlay_png_capped_bytes(pil.convert("RGBA"), max_bytes=2200000)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data_bytes)
        bbox = _extract_nonwhite_bbox_norm(out_comp, threshold=240) or {"x": 0.2, "y": 0.2, "w": 0.6, "h": 0.6}
        data_url = "data:image/png;base64," + base64.b64encode(data_bytes).decode("utf-8")
        return JsonResponse(
            {
                "error_num": 0,
                "msg": "success",
                "target": target,
                "overlay_image": data_url,
                "overlay_bbox": bbox,
            }
        )
    except Exception as e:
        print(f"[card_image] 保存覆盖层文件失败 cid={cid} target={target}: {e}")
        return JsonResponse({"error_num": 1, "msg": str(e)})
    finally:
        with _card_image_lock:
            s = _card_image_generating.get(username)
            if s is not None and cid in s:
                s.discard(cid)


@csrf_exempt
def card_dmt_overlay_prompt_stream(request):
    """
    流式生成「DMT 微版面化」覆盖层生图说明文字（Gemini 3.1 Pro + 视觉，dmxapi）。
    POST JSON: username, cid, card_content(可选), card_title(可选), image_data_url(可选；缺省则读本地 card 主图)
    可选 refine=true 且 draft_instruction=初稿全文：流式输出检验优化后的完整说明。
    响应：text/plain; charset=utf-8 流式 UTF-8 文本片段。
    """
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        data = json.loads(request.body)
        username = data.get("username")
        cid = int(data.get("cid"))
        card_content = (data.get("card_content") or "").strip()
        card_title = (data.get("card_title") or "").strip()
        image_data_url = (data.get("image_data_url") or "").strip()
        refine = bool(data.get("refine"))
        draft_instruction = (data.get("draft_instruction") or "").strip()
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})

    if not username:
        return JsonResponse({"error_num": 1, "msg": "missing username"})

    if not image_data_url:
        if not _card_has_image(username, cid):
            return JsonResponse({"error_num": 1, "msg": "该卡片暂无图片，请先在卡片上附图"})
        path = _get_card_image_path(username, cid)
        if not path or not os.path.isfile(path):
            return JsonResponse({"error_num": 1, "msg": "无法读取卡片图片"})
        try:
            with open(path, "rb") as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode("utf-8")
            ext = os.path.splitext(path)[1].lower()
            if ext in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ext == ".webp":
                mime = "image/webp"
            elif ext == ".gif":
                mime = "image/gif"
            else:
                mime = "image/png"
            image_data_url = f"data:{mime};base64,{b64}"
        except Exception as e:
            return JsonResponse({"error_num": 1, "msg": "读取图片失败: %s" % (e,)})

    try:
        if refine:
            if len(draft_instruction) < 40:
                return JsonResponse(
                    {"error_num": 1, "msg": "检验优化模式需要 draft_instruction（初稿全文，至少约40字）"}
                )
            stream_gen = _dmt_overlay_refine_stream_generator(
                image_data_url, card_title, card_content, draft_instruction
            )
        else:
            stream_gen = _dmt_overlay_stream_generator(image_data_url, card_title, card_content)
        resp = StreamingHttpResponse(
            stream_gen,
            content_type="text/plain; charset=utf-8",
        )
        resp["Cache-Control"] = "no-cache"
        resp["X-Accel-Buffering"] = "no"
        return resp
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})


@csrf_exempt
def card_iterate_overlay_test_layer(request):
    """测试覆盖层二次迭代：后台异步，不落盘，结果通过状态接口获取。"""
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        data = __import__("json").loads(request.body)
        username = data.get("username")
        cid = int(data.get("cid"))
        overlay_image = data.get("overlay_image")
        revision_instruction = (data.get("revision_instruction") or "").strip() or None
        reference_image = data.get("reference_image")
        image_quality = (data.get("image_quality") or "normal").strip().lower()
        if image_quality not in ("normal", "high"):
            image_quality = "normal"
        reference_image_mime = "image/png"
        if reference_image and isinstance(reference_image, str) and reference_image.strip():
            ref = reference_image.strip()
            if ref.startswith("data:") and "base64," in ref:
                reference_image_b64 = ref.split("base64,", 1)[-1]
                try:
                    prefix = ref.split("base64,", 1)[0]
                    mime_part = prefix.split(":", 1)[1]
                    reference_image_mime = mime_part.split(";")[0] or reference_image_mime
                except Exception:
                    pass
            else:
                reference_image_b64 = ref
        else:
            reference_image_b64 = None
        edit_region = _parse_edit_region(data.get("edit_region"))
        if not username or not overlay_image or not isinstance(overlay_image, str):
            return JsonResponse({"error_num": 1, "msg": "missing username/cid/overlay_image"})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})

    def _job():
        try:
            out = _iterate_overlay_test_layer_image(
                overlay_image_b64=overlay_image,
                revision_instruction=revision_instruction,
                reference_image_b64=reference_image_b64,
                reference_image_mime=reference_image_mime,
                image_quality=image_quality,
                edit_region=edit_region,
            )
            data_bytes, out_comp = _encode_overlay_png_capped_bytes(out, max_bytes=2200000)
            bbox = _extract_nonwhite_bbox_norm(out_comp, threshold=240) or {"x": 0.2, "y": 0.2, "w": 0.6, "h": 0.6}
            data_url = "data:image/png;base64," + base64.b64encode(data_bytes).decode("utf-8")
            _save_overlay_history_snapshot(username, cid, out)
            with _card_image_lock:
                _overlay_test_jobs[(username, cid)] = {
                    "status": "success",
                    "msg": "overlay_iterate_success",
                    "overlay_image": data_url,
                    "overlay_bbox": bbox,
                }
        except Exception as ex:
            with _card_image_lock:
                _overlay_test_jobs[(username, cid)] = {"status": "error", "msg": str(ex)}
        finally:
            with _card_image_lock:
                s = _card_image_generating.get(username)
                if s is not None and cid in s:
                    s.discard(cid)

    with _card_image_lock:
        if username not in _card_image_generating:
            _card_image_generating[username] = set()
        if cid in _card_image_generating[username]:
            return JsonResponse({"error_num": 1, "msg": "generating", "generating": True})
        _overlay_test_jobs[(username, cid)] = {"status": "running", "msg": "overlay_iterating"}
        _card_image_generating[username].add(cid)
    threading.Thread(target=_job, daemon=True).start()
    return JsonResponse({"error_num": 0, "msg": "queued"})


@csrf_exempt
def card_apply_overlay_test_layer(request):
    """独立测试模式：将用户拖拽/拉伸后的覆盖层叠加到当前卡片图。"""
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        data = __import__("json").loads(request.body)
        username = data.get("username")
        cid = int(data.get("cid"))
        overlay_image = data.get("overlay_image")
        base_source = (data.get("base_source") or "current").strip().lower()
        base_image = data.get("base_image") if base_source == "custom" else None
        keep_white_regions = _parse_bboxes_norm_list(data.get("keep_white_regions"))
        src_bbox = _parse_bbox_norm(data.get("source_bbox"))
        dst_bbox = _parse_bbox_norm(data.get("target_bbox"))
        threshold = int(data.get("white_threshold", 240))
        threshold = max(160, min(252, threshold))
        overlay_alpha = float(data.get("overlay_alpha", 1.0))
        overlay_alpha = max(0.0, min(1.0, overlay_alpha))
        if not username or not overlay_image or not src_bbox or not dst_bbox:
            return JsonResponse({"error_num": 1, "msg": "missing required fields"})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})

    if not _card_has_image(username, cid):
        return JsonResponse({"error_num": 1, "msg": "该卡片暂无图片"})
    with _card_image_lock:
        if username not in _card_image_generating:
            _card_image_generating[username] = set()
        if cid in _card_image_generating[username]:
            return JsonResponse({"error_num": 1, "msg": "generating", "generating": True})
        _card_image_generating[username].add(cid)
    try:
        base_im = _load_base_image_for_overlay(username, cid, base_source=base_source, base_image_b64=base_image)
        overlay_b64 = overlay_image.strip()
        if overlay_b64.startswith("data:") and "base64," in overlay_b64:
            overlay_b64 = overlay_b64.split("base64,", 1)[-1]
        overlay_pil = _pil_from_response_base64(overlay_b64)
        if overlay_pil is None:
            return JsonResponse({"error_num": 1, "msg": "overlay image decode failed"})
        _backup_card_image_before_iterate(username, cid)
        out = _compose_overlay_by_bbox(
            base_im,
            overlay_pil,
            src_bbox,
            dst_bbox,
            threshold=threshold,
            overlay_alpha=overlay_alpha,
            keep_white_regions=keep_white_regions,
        )
        out_path = os.path.join(_card_image_dir(username), f"{cid}.png")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        out.save(out_path, "PNG")
        try:
            card = Card.objects.get(username=username, cid=cid)
            _save_gen_content(username, cid, (card.content or "").strip(), (card.contentTitle or "").strip())
        except Exception:
            pass
        return JsonResponse({"error_num": 0, "msg": "success"})
    except Exception as e:
        print(f"[card_image] 覆盖层合成失败 cid={cid}: {e}")
        return JsonResponse({"error_num": 1, "msg": str(e)})
    finally:
        with _card_image_lock:
            s = _card_image_generating.get(username)
            if s is not None and cid in s:
                s.discard(cid)


@csrf_exempt
def card_revert_iterate_card_image(request):
    """POST: 将卡片主图恢复为上一次「迭代图」覆盖前的备份（{cid}.prev_iterate.*）。body: username, cid"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        data = __import__('json').loads(request.body)
        username = data.get('username')
        cid = data.get('cid')
        if not username or cid is None:
            return JsonResponse({'error_num': 1, 'msg': 'missing username or cid'})
        cid = int(cid)
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': str(e)})

    if not _card_has_image(username, cid):
        return JsonResponse({'error_num': 1, 'msg': '该卡片暂无图片'})

    with _card_image_lock:
        if username not in _card_image_generating:
            _card_image_generating[username] = set()
        if cid in _card_image_generating[username]:
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

    bak = _find_iterate_backup_path(username, cid)
    if not bak:
        return JsonResponse({
            'error_num': 1,
            'msg': '暂无可回退的迭代前图片，请先成功完成一次「迭代图」',
        })

    cur = _get_card_image_path(username, cid)
    if not cur:
        return JsonResponse({'error_num': 1, 'msg': '当前卡片无图片路径'})

    try:
        shutil.copy2(bak, cur)
        print(f"[card_image] 图回退成功 cid={cid} <- {os.path.basename(bak)}")
        return JsonResponse({'error_num': 0, 'msg': 'success'})
    except Exception as e:
        print(f"[card_image] 图回退失败 cid={cid}: {e}")
        return JsonResponse({'error_num': 1, 'msg': str(e)})


OVERLAY_REDBOX_MASK_MAX_SIDE = 2048
# 红块检测 v3：自动区分「纯红填充小块」与「红底白字 D 标签」，掩膜与提框见 _red_fill_binary_mask_u8_from_rgba / _boxes_from_red_mask_filtered。
_last_red_clean_cache = {"mask_id": None, "red_clean": None}
_last_algo_used = {"algo": None, "mask_id": None}


def _prune_short_runs_on_indices(work: np.ndarray, ys: np.ndarray, xs: np.ndarray, min_len: int) -> None:
    """沿已排序的像素序列 (ys[i], xs[i]) 将长度 < min_len 的前景连续段清零。"""
    n = int(ys.size)
    if n < 1 or min_len <= 0:
        return
    vals = (work[ys, xs] > 127).astype(np.int8)
    padded = np.zeros(n + 2, dtype=np.int8)
    padded[1 : n + 1] = vals
    d = np.diff(padded)
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    for s, e in zip(starts, ends):
        if e - s < min_len:
            work[ys[s:e], xs[s:e]] = 0


def _scanline_prune_short_red_runs_u8(
    mask_u8: np.ndarray,
    min_keep_vert: int = None,
    min_keep_horiz: int = None,
    min_keep_diag: int = None,
) -> np.ndarray:
    """
    二值掩膜（非零=红前景），宽 a 列、高 b 行（numpy shape 为 (b, a)）：
    1) 逐列 x，自上而下：短竖向段清除（横穿细线）；
    2) 逐行 y，自左而右：短横向段清除（竖穿细线）；
    3) 45° 左斜：x+y 为常数的斜线（副对角方向），沿 y 递增遍历像素链；
    4) 45° 右斜：x−y 为常数的斜线（主对角方向），沿 y 递增遍历像素链。
    每遍规则与列/行相同：沿该线连续前景长度不足则整段去除。
    """
    if mask_u8 is None or mask_u8.size == 0:
        return mask_u8
    m = np.asarray(mask_u8)
    if m.ndim == 3:
        m = m[:, :, 0]
    if m.ndim != 2:
        raise ValueError("_scanline_prune_short_red_runs_u8 expects HxW or HxWx1")
    binm = m > 127
    h, w = binm.shape
    if h < 1 or w < 1:
        return np.asarray(mask_u8, dtype=np.uint8)

    auto_vert = max(4, min(18, max(1, h // 120)))
    auto_horiz = max(4, min(18, max(1, w // 120)))
    min_keep_vert = int(min_keep_vert) if min_keep_vert is not None else auto_vert
    min_keep_horiz = int(min_keep_horiz) if min_keep_horiz is not None else auto_horiz
    min_keep_vert = max(1, min(64, min_keep_vert))
    min_keep_horiz = max(1, min(64, min_keep_horiz))
    # 斜向默认取横竖较大值；支持前端单独覆盖
    if min_keep_diag is None:
        min_keep_diag = max(min_keep_vert, min_keep_horiz)
    else:
        min_keep_diag = max(1, min(64, int(min_keep_diag)))
    work = (binm.astype(np.uint8) * 255).copy()

    for x in range(w):
        col = work[:, x] > 127
        if not np.any(col):
            continue
        padded = np.zeros(h + 2, dtype=np.int8)
        padded[1 : h + 1] = col.astype(np.int8)
        d = np.diff(padded)
        starts = np.where(d == 1)[0]
        ends = np.where(d == -1)[0]
        for s, e in zip(starts, ends):
            if e - s < min_keep_vert:
                work[s:e, x] = 0

    for y in range(h):
        row = work[y, :] > 127
        if not np.any(row):
            continue
        padded = np.zeros(w + 2, dtype=np.int8)
        padded[1 : w + 1] = row.astype(np.int8)
        d = np.diff(padded)
        starts = np.where(d == 1)[0]
        ends = np.where(d == -1)[0]
        for s, e in zip(starts, ends):
            if e - s < min_keep_horiz:
                work[y, s:e] = 0

    # 左斜：x + y = s 常数，y 从 0 递增 → x = s - y 递减
    for s in range(0, w + h - 1):
        ys = np.arange(h, dtype=np.int32)
        xs = (s - ys).astype(np.int32)
        msk = (xs >= 0) & (xs < w)
        ys = ys[msk]
        xs = xs[msk]
        if ys.size:
            _prune_short_runs_on_indices(work, ys, xs, min_keep_diag)

    # 右斜：x - y = d 常数，y 从 0 递增 → x = y + d
    for d in range(-(h - 1), w):
        ys = np.arange(h, dtype=np.int32)
        xs = (ys + d).astype(np.int32)
        msk = (xs >= 0) & (xs < w)
        ys = ys[msk]
        xs = xs[msk]
        if ys.size:
            _prune_short_runs_on_indices(work, ys, xs, min_keep_diag)

    return work


def _get_red_pixel_mask(pil_rgba: Image.Image):
    """检测红色像素（HSV+RGB）。返回 uint8 掩膜 255/0。"""
    arr = np.asarray(pil_rgba.convert("RGBA"))
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = (arr[:, :, 3].astype(np.float32) / 255.0)[:, :, None]
    comp = np.clip(rgb * alpha, 0, 255).astype(np.uint8)

    hsv = cv2.cvtColor(comp, cv2.COLOR_RGB2HSV)
    m_hsv = cv2.bitwise_or(
        cv2.inRange(hsv, np.array([0, 35, 35], np.uint8), np.array([12, 255, 255], np.uint8)),
        cv2.inRange(hsv, np.array([158, 35, 35], np.uint8), np.array([179, 255, 255], np.uint8)),
    )
    r = comp[:, :, 0].astype(np.int16)
    g = comp[:, :, 1].astype(np.int16)
    b = comp[:, :, 2].astype(np.int16)
    m_rgb = (
        (comp[:, :, 0] > 55) & ((r - g) > 12) & ((r - b) > 12)
    ).astype(np.uint8) * 255
    return cv2.bitwise_or(m_hsv, m_rgb)


def _detect_red_label_type(pil_rgba: Image.Image) -> str:
    """
    自动路由：'solid' 纯红填充小块（扫描线）；'text_bearing' 红底白字 D 标签（v2 距离变换）。
    """
    red_mask = _get_red_pixel_mask(pil_rgba)
    h, w = red_mask.shape[:2]
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    red_clean = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, k3)

    dist = cv2.distanceTransform(red_clean, cv2.DIST_L2, 5)
    _, core = cv2.threshold(dist, 6.0, 255, cv2.THRESH_BINARY)
    core = core.astype(np.uint8)
    num_cores, _, core_stats, _ = cv2.connectedComponentsWithStats(core, connectivity=8)

    widths = []
    heights = []
    for i in range(1, num_cores):
        area = int(core_stats[i, cv2.CC_STAT_AREA])
        bw = int(core_stats[i, cv2.CC_STAT_WIDTH])
        bh = int(core_stats[i, cv2.CC_STAT_HEIGHT])
        if area < 10 or bw < 3 or bh < 3:
            continue
        widths.append(bw)
        heights.append(bh)

    if len(widths) < 5:
        return "solid"

    tiny_count = sum(1 for ww, hh in zip(widths, heights) if ww < 15 or hh < 8)
    tiny_ratio = tiny_count / len(widths)

    w_arr = np.array(widths, dtype=float)
    w_cv = np.std(w_arr) / max(1e-6, np.mean(w_arr))

    if tiny_ratio > 0.08 or w_cv > 0.40:
        return "solid"
    return "text_bearing"


def _red_fill_mask_v2(pil_rgba: Image.Image, scan_min_area_px=None):
    """v2：红底白字标签类覆盖层掩膜；缓存 red_clean 供提框。"""
    global _last_red_clean_cache

    red_mask = _get_red_pixel_mask(pil_rgba)
    h, w = red_mask.shape[:2]

    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    red_clean = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, k3)

    dist = cv2.distanceTransform(red_clean, cv2.DIST_L2, 5)
    core_threshold = 6.0
    _, core = cv2.threshold(dist, core_threshold, 255, cv2.THRESH_BINARY)
    core = core.astype(np.uint8)
    num_cores, _, core_stats, _ = cv2.connectedComponentsWithStats(core, connectivity=8)

    max_expand = int(core_threshold) + 2
    min_strip_fill = 0.45
    result_mask = np.zeros_like(red_clean)

    for i in range(1, num_cores):
        cx = int(core_stats[i, cv2.CC_STAT_LEFT])
        cy = int(core_stats[i, cv2.CC_STAT_TOP])
        cw = int(core_stats[i, cv2.CC_STAT_WIDTH])
        ch = int(core_stats[i, cv2.CC_STAT_HEIGHT])
        area = int(core_stats[i, cv2.CC_STAT_AREA])
        if area < 10 or cw < 3 or ch < 3:
            continue

        bx, by, bw, bh = cx, cy, cw, ch
        for direction in range(4):
            for _ in range(max_expand):
                if direction == 0:
                    nx = bx - 1
                    if nx < 0:
                        break
                    strip = red_clean[by : by + bh, nx : nx + 1]
                    if np.count_nonzero(strip) / max(1, strip.size) < min_strip_fill:
                        break
                    bx = nx
                    bw += 1
                elif direction == 1:
                    nx = bx + bw
                    if nx >= w:
                        break
                    strip = red_clean[by : by + bh, nx : nx + 1]
                    if np.count_nonzero(strip) / max(1, strip.size) < min_strip_fill:
                        break
                    bw += 1
                elif direction == 2:
                    ny = by - 1
                    if ny < 0:
                        break
                    strip = red_clean[ny : ny + 1, bx : bx + bw]
                    if np.count_nonzero(strip) / max(1, strip.size) < min_strip_fill:
                        break
                    by = ny
                    bh += 1
                elif direction == 3:
                    ny = by + bh
                    if ny >= h:
                        break
                    strip = red_clean[ny : ny + 1, bx : bx + bw]
                    if np.count_nonzero(strip) / max(1, strip.size) < min_strip_fill:
                        break
                    bh += 1

        roi = red_clean[by : by + bh, bx : bx + bw]
        result_mask[by : by + bh, bx : bx + bw] = np.maximum(
            result_mask[by : by + bh, bx : bx + bw], roi
        )

    if scan_min_area_px is None:
        min_area_cc = max(12, int(h * w * 0.000015))
    else:
        min_area_cc = max(1, min(20000, int(scan_min_area_px)))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(result_mask, connectivity=8)
    final = np.zeros_like(result_mask)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) >= min_area_cc:
            final[labels == i] = 255

    _last_red_clean_cache = {"mask_id": id(final), "red_clean": red_clean}

    return final


def _boxes_from_red_clean_independent(red_clean, tw: int, th: int):
    """v2 提框：独立 bbox，避免相邻红底标签在掩膜上粘连导致漏检。"""
    h, w = red_clean.shape[:2]

    dist = cv2.distanceTransform(red_clean, cv2.DIST_L2, 5)
    core_threshold = 6.0
    _, core = cv2.threshold(dist, core_threshold, 255, cv2.THRESH_BINARY)
    core = core.astype(np.uint8)
    num_cores, _, core_stats, _ = cv2.connectedComponentsWithStats(core, connectivity=8)

    max_expand = int(core_threshold) + 2
    min_strip_fill = 0.45
    boxes = []

    for i in range(1, num_cores):
        cx = int(core_stats[i, cv2.CC_STAT_LEFT])
        cy = int(core_stats[i, cv2.CC_STAT_TOP])
        cw = int(core_stats[i, cv2.CC_STAT_WIDTH])
        ch = int(core_stats[i, cv2.CC_STAT_HEIGHT])
        area = int(core_stats[i, cv2.CC_STAT_AREA])
        if area < 10 or cw < 3 or ch < 3:
            continue

        bx, by, bw, bh = cx, cy, cw, ch
        for d_name in ("left", "right", "top", "bottom"):
            for _ in range(max_expand):
                if d_name == "left":
                    nx = bx - 1
                    if nx < 0:
                        break
                    strip = red_clean[by : by + bh, nx : nx + 1]
                    if np.count_nonzero(strip) / max(1, strip.size) < min_strip_fill:
                        break
                    bx = nx
                    bw += 1
                elif d_name == "right":
                    nx = bx + bw
                    if nx >= w:
                        break
                    strip = red_clean[by : by + bh, nx : nx + 1]
                    if np.count_nonzero(strip) / max(1, strip.size) < min_strip_fill:
                        break
                    bw += 1
                elif d_name == "top":
                    ny = by - 1
                    if ny < 0:
                        break
                    strip = red_clean[ny : ny + 1, bx : bx + bw]
                    if np.count_nonzero(strip) / max(1, strip.size) < min_strip_fill:
                        break
                    by = ny
                    bh += 1
                elif d_name == "bottom":
                    ny = by + bh
                    if ny >= h:
                        break
                    strip = red_clean[ny : ny + 1, bx : bx + bw]
                    if np.count_nonzero(strip) / max(1, strip.size) < min_strip_fill:
                        break
                    bh += 1

        fill_area = int(np.count_nonzero(red_clean[by : by + bh, bx : bx + bw]))
        fill_ratio = fill_area / max(1, bw * bh)
        boxes.append(
            {
                "x": bx,
                "y": by,
                "w": bw,
                "h": bh,
                "_area": fill_area,
                "_solidity": fill_ratio,
            }
        )

    max_bw = max(80, int(tw * 0.08))
    max_bh = max(60, int(th * 0.08))
    filtered = [
        b
        for b in boxes
        if b["w"] >= 12
        and b["h"] >= 10
        and b["w"] <= max_bw
        and b["h"] <= max_bh
        and b["_solidity"] >= 0.40
        and 0.3 <= b["w"] / max(1, b["h"]) <= 3.5
    ]

    filtered.sort(key=lambda b: -b["_area"])

    kept = []
    for b in filtered:
        bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]
        dup = False
        for k in kept:
            kx, ky, kw, kh = k["x"], k["y"], k["w"], k["h"]
            x1 = max(bx, kx)
            y1 = max(by, ky)
            x2 = min(bx + bw, kx + kw)
            y2 = min(by + bh, ky + kh)
            inter = max(0, x2 - x1) * max(0, y2 - y1)
            u = bw * bh + kw * kh - inter
            if u > 0 and inter / u > 0.3:
                dup = True
                break
        if not dup:
            kept.append({"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]})

    if len(kept) >= 5:
        ws = sorted([b["w"] for b in kept])
        hs = sorted([b["h"] for b in kept])
        med_w = ws[len(ws) // 2]
        med_h = hs[len(hs) // 2]
        max_w2 = med_w * 1.8
        max_h2 = med_h * 1.8
        kept = [b for b in kept if b["w"] <= max_w2 and b["h"] <= max_h2]

    kept.sort(key=lambda b: (b["y"] + b["h"] * 0.5, b["x"] + b["w"] * 0.5))
    return kept


def _red_fill_binary_mask_u8_from_rgba(
    pil_rgba: Image.Image,
    scan_min_run_vert: int = None,
    scan_min_run_horiz: int = None,
    scan_min_run_diag: int = None,
    scan_min_area_px: int = None,
) -> np.ndarray:
    """
    二值掩膜 255=红前景（replacement_functions_v3 路由）：
    - 红底白字「D+序号」类 → v2 距离变换；
    - 纯红填充小块类 → 原扫描线算法（scan_min_run_* 仅在此路径生效）。
    """
    global _last_algo_used

    label_type = _detect_red_label_type(pil_rgba)

    if label_type == "text_bearing":
        mask = _red_fill_mask_v2(pil_rgba, scan_min_area_px=scan_min_area_px)
        _last_algo_used = {"algo": "v2", "mask_id": id(mask)}
        return mask

    arr = np.asarray(pil_rgba.convert("RGBA"))
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = (arr[:, :, 3].astype(np.float32) / 255.0)[:, :, None]
    comp = np.clip(rgb * alpha, 0, 255).astype(np.uint8)
    h, w0 = comp.shape[:2]
    hsv = cv2.cvtColor(comp, cv2.COLOR_RGB2HSV)
    m_hsv = cv2.bitwise_or(
        cv2.inRange(hsv, np.array([0, 35, 35], np.uint8), np.array([12, 255, 255], np.uint8)),
        cv2.inRange(hsv, np.array([158, 35, 35], np.uint8), np.array([179, 255, 255], np.uint8)),
    )
    r = comp[:, :, 0].astype(np.int16)
    g = comp[:, :, 1].astype(np.int16)
    b = comp[:, :, 2].astype(np.int16)
    m_rgb = (
        (comp[:, :, 0] > 55) & ((r - g) > 12) & ((r - b) > 12)
    ).astype(np.uint8) * 255
    m = cv2.bitwise_or(m_hsv, m_rgb)

    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k3)

    m = _scanline_prune_short_red_runs_u8(
        m,
        min_keep_vert=scan_min_run_vert,
        min_keep_horiz=scan_min_run_horiz,
        min_keep_diag=scan_min_run_diag,
    )

    if scan_min_area_px is None:
        min_area_cc = max(12, int(h * w0 * 0.000015))
    else:
        min_area_cc = max(1, min(20000, int(scan_min_area_px)))
    num, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(m.shape, dtype=np.uint8)
    for i in range(1, num):
        if int(stats[i, cv2.CC_STAT_AREA]) >= min_area_cc:
            keep[labels == i] = 255

    _last_algo_used = {"algo": "scanline", "mask_id": id(keep)}
    return keep


def _boxes_from_red_mask_filtered(mask_u8: np.ndarray, tw: int, th: int):
    """
    从掩膜提红块框：v2 路径用独立 bbox；扫描线路径用原轮廓规则。
    """
    global _last_red_clean_cache, _last_algo_used

    if mask_u8 is None or tw < 2 or th < 2:
        return []

    if _last_algo_used.get("mask_id") == id(mask_u8) and _last_algo_used.get("algo") == "v2":
        red_clean = None
        if _last_red_clean_cache.get("mask_id") == id(mask_u8):
            red_clean = _last_red_clean_cache.get("red_clean")
        if red_clean is not None:
            return _boxes_from_red_clean_independent(red_clean, tw, th)

    bw = mask_u8 if mask_u8.ndim == 2 else mask_u8[:, :, 0]
    fc = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(fc) == 3:
        _, cnts, _ = fc
    else:
        cnts, _ = fc
    min_area = max(40, int(tw * th * 0.000035))
    max_area = int(max(900, tw * th * 0.022) * 1.2)
    min_w = 8
    min_h = 8
    max_w = max(28, int(tw * 0.32))
    max_h = max(24, int(th * 0.16))
    # 严格限制长宽比：仅允许 1:4 ~ 4:1
    min_aspect = 0.25
    max_aspect = 4.0
    raw = []
    for c in cnts:
        area = float(cv2.contourArea(c))
        x, y, w, h = cv2.boundingRect(c)
        if area < min_area or area > max_area:
            continue
        if w < min_w or h < min_h or w > max_w or h > max_h:
            continue
        ar = w / max(1, h)
        if ar < min_aspect or ar > max_aspect:
            continue
        extent = area / max(1.0, float(w * h))
        if extent < 0.14:
            continue
        # 细长条：短边仍偏小但长边很长（表格线、连接线）
        if min(w, h) < 12 and max(w, h) >= min(w, h) * 6:
            continue
        raw.append(
            {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "_area": area,
            }
        )
    raw.sort(key=lambda b: -b["_area"])
    kept = []
    for b in raw:
        dup = False
        bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]
        for k in kept:
            kx, ky, kw, kh = k["x"], k["y"], k["w"], k["h"]
            x1 = max(bx, kx)
            y1 = max(by, ky)
            x2 = min(bx + bw, kx + kw)
            y2 = min(by + bh, ky + kh)
            inter = max(0, x2 - x1) * max(0, y2 - y1)
            u = bw * bh + kw * kh - inter
            if u > 0 and inter / u > 0.45:
                dup = True
                break
        if not dup:
            kept.append({"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]})
    kept.sort(key=lambda b: (b["y"] + b["h"] * 0.5, b["x"] + b["w"] * 0.5))
    return kept


def _boxes_from_white_mask_pil(mask_pil: Image.Image, tw: int, th: int, min_area: int = 16):
    """将二值掩膜（白=前景）缩放到 tw×th 后提外接矩形；返回 [{x,y,w,h},...] 画布坐标。"""
    rgb = mask_pil.convert("RGB")
    rgb = rgb.resize((max(1, tw), max(1, th)), Image.NEAREST)
    arr = np.asarray(rgb)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    _, bw = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    fc = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(fc) == 3:
        _, cnts, _ = fc
    else:
        cnts, _ = fc
    boxes = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < min_area:
            continue
        x = max(0, min(int(x), tw - 1))
        y = max(0, min(int(y), th - 1))
        w = max(1, min(int(w), tw - x))
        h = max(1, min(int(h), th - y))
        boxes.append({"x": x, "y": y, "w": w, "h": h})
    boxes.sort(key=lambda b: (b["y"] + b["h"] * 0.5, b["x"] + b["w"] * 0.5))
    return boxes


@csrf_exempt
def card_overlay_detect_red_boxes_json(request):
    """
    从覆盖层用 OpenCV 提取「原图中红色实心填充」二值掩膜（排除细红框线），落盘 cardImage 并由掩膜提框。
    不调用生图模型，避免在框线内侧「填色」或臆造网格等非原图红像素。
    POST JSON: username, cid, overlay_image(data URL 或纯 base64)
    返回: error_num, boxes, image_width, image_height, mask_filename（相对 cardImage 目录的文件名）
    """
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        data = json.loads(request.body)
        username = data.get("username")
        cid = data.get("cid")
        overlay_image = data.get("overlay_image")
        scan_min_run_vert = data.get("scan_min_run_vert")
        scan_min_run_horiz = data.get("scan_min_run_horiz")
        scan_min_run_diag = data.get("scan_min_run_diag")
        scan_min_area_px = data.get("scan_min_area_px")
        missing = []
        if not username:
            missing.append("username")
        if cid is None or cid == "":
            missing.append("cid")
        if overlay_image is None:
            missing.append("overlay_image")
        if missing:
            return JsonResponse(
                {"error_num": 1, "msg": "missing: " + ", ".join(missing)}
            )
        cid = int(cid)
        scan_min_run_vert = (
            None
            if scan_min_run_vert in (None, "") or int(scan_min_run_vert) <= 0
            else max(1, min(64, int(scan_min_run_vert)))
        )
        scan_min_run_horiz = (
            None
            if scan_min_run_horiz in (None, "") or int(scan_min_run_horiz) <= 0
            else max(1, min(64, int(scan_min_run_horiz)))
        )
        scan_min_run_diag = (
            None
            if scan_min_run_diag in (None, "") or int(scan_min_run_diag) <= 0
            else max(1, min(64, int(scan_min_run_diag)))
        )
        scan_min_area_px = (
            None
            if scan_min_area_px in (None, "") or int(scan_min_area_px) <= 0
            else max(1, min(20000, int(scan_min_area_px)))
        )
        if not isinstance(overlay_image, str) or not overlay_image.strip():
            return JsonResponse({"error_num": 1, "msg": "invalid overlay_image"})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})

    overlay_b64 = overlay_image.strip()
    if overlay_b64.startswith("data:") and "base64," in overlay_b64:
        overlay_b64 = overlay_b64.split("base64,", 1)[-1]

    pil = _pil_from_response_base64(overlay_b64)
    if pil is None:
        return JsonResponse({"error_num": 1, "msg": "overlay image decode failed"})

    pil = pil.convert("RGBA")
    orig_w, orig_h = pil.size
    if orig_w < 1 or orig_h < 1:
        return JsonResponse({"error_num": 1, "msg": "invalid image size"})

    max_side = OVERLAY_REDBOX_MASK_MAX_SIDE
    if max(orig_w, orig_h) > max_side:
        sc = max_side / float(max(orig_w, orig_h))
        nw = max(1, int(round(orig_w * sc)))
        nh = max(1, int(round(orig_h * sc)))
        pil_work = pil.resize((nw, nh), Image.NEAREST)
    else:
        pil_work = pil
        nw, nh = orig_w, orig_h

    fill_mask_u8 = _red_fill_binary_mask_u8_from_rgba(
        pil_work,
        scan_min_run_vert=scan_min_run_vert,
        scan_min_run_horiz=scan_min_run_horiz,
        scan_min_run_diag=scan_min_run_diag,
        scan_min_area_px=scan_min_area_px,
    )
    boxes = _boxes_from_red_mask_filtered(fill_mask_u8, nw, nh)

    if nw != orig_w or nh != orig_h:
        sx = orig_w / float(nw)
        sy = orig_h / float(nh)
        scaled = []
        for b in boxes:
            x = int(round(b["x"] * sx))
            y = int(round(b["y"] * sy))
            w = int(round(b["w"] * sx))
            h = int(round(b["h"] * sy))
            x = max(0, min(x, orig_w - 1))
            y = max(0, min(y, orig_h - 1))
            w = max(1, min(w, orig_w - x))
            h = max(1, min(h, orig_h - y))
            scaled.append({"x": x, "y": y, "w": w, "h": h})
        boxes = scaled

    if (nw, nh) != (orig_w, orig_h):
        up = cv2.resize(fill_mask_u8, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
        mask_save = Image.fromarray(cv2.cvtColor(up, cv2.COLOR_GRAY2RGB), mode="RGB")
    else:
        mask_save = Image.fromarray(cv2.cvtColor(fill_mask_u8, cv2.COLOR_GRAY2RGB), mode="RGB")
    mask_filename = f"{cid}.overlay_redmask.png"
    mask_path = os.path.join(_card_image_dir(username), mask_filename)
    try:
        os.makedirs(os.path.dirname(mask_path), exist_ok=True)
        mask_save.save(mask_path, "PNG")
    except Exception as e:
        print(f"[card_image] 保存红框掩膜失败 path={mask_path}: {e}")
        return JsonResponse({"error_num": 1, "msg": f"掩膜保存失败: {e}"})

    return JsonResponse(
        {
            "error_num": 0,
            "msg": "success",
            "boxes": boxes,
            "image_width": orig_w,
            "image_height": orig_h,
            "mask_filename": mask_filename,
        }
    )


@csrf_exempt
def card_generate_single_card_image(request):
    """POST: 为单张卡片生图。body: username, cid, regenerate(可选)。若正在生图则返回不可用。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        data = __import__('json').loads(request.body)
        username = data.get('username')
        cid = data.get('cid')
        regenerate = data.get('regenerate', False)
        image_quality = (data.get('image_quality') or 'normal').strip().lower()
        if image_quality not in ('normal', 'high'):
            image_quality = 'normal'
        image_provider = _normalize_image_provider(data.get('image_provider'))
        image_aspect_ratio = _normalize_image_aspect_ratio(data.get('image_aspect_ratio'))
        if not username or cid is None:
            return JsonResponse({'error_num': 1, 'msg': 'missing username or cid'})
        cid = int(cid)
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': str(e)})

    with _card_image_lock:
        if username not in _card_image_generating:
            _card_image_generating[username] = set()
        if cid in _card_image_generating[username]:
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

    if not regenerate and _card_has_image(username, cid):
        return JsonResponse({'error_num': 0, 'msg': 'success', 'skipped': True})

    with _card_image_lock:
        _card_image_generating[username].add(cid)

    t = threading.Thread(
        target=_run_batch,
        args=(username, [cid]),
        kwargs={"single_card": True, "image_quality": image_quality,
                "image_provider": image_provider, "image_aspect_ratio": image_aspect_ratio},
    )
    t.daemon = True
    t.start()

    return JsonResponse(
        {'error_num': 0, 'msg': 'success', 'generating_cids': list(_card_image_generating.get(username, set()))})
