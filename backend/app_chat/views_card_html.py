# -*- coding: utf-8 -*-
"""
卡片 HTML 助记交互版：生成（Claude Opus 4.7）、落盘 cardHtml、按需查看。
与 cardImage 同级目录：received_dir/user_raw_file/<username>/cardHtml/<cid>.html
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

_card_html_generating = {}
_card_html_lock = threading.Lock()


def mark_card_html_generating(username, cid):
    cid = int(cid)
    with _card_html_lock:
        if username not in _card_html_generating:
            _card_html_generating[username] = set()
        _card_html_generating[username].add(cid)


def unmark_card_html_generating(username, cid):
    cid = int(cid)
    with _card_html_lock:
        s = _card_html_generating.get(username)
        if s is not None:
            s.discard(cid)

from django.http import HttpResponse, JsonResponse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI

from app_chat.config.config_manager import config_manager
from app_chat.models import Card
from app_chat.scene_context_helper import get_scene_info_from_username
from app_chat.automation_nk2026 import (
    NK2026_CHUCHENGJIA_WEEK_MIN,
    is_nk2026_ladder_scene,
    read_nk2026_chuchengjia_twin_markdown,
    text_references_course_week_at_least,
)

NK2026_HTML_SCENE_WHITELIST = (
    "飞书TA答疑",
    "NK2026精进种子",
    "NK2026梯子图·群组公能教学指向批改",
)
from app_chat.card_html_feedback import (
    DEFAULT_TIZITU_NOTEBOOK,
    aggregate_feedback_summary,
    aggregate_group_card_html_feedback,
    append_feedback_event,
    build_telemetry_config,
    format_group_feedback_api_response,
    format_group_feedback_as_text,
    infer_week_for_telemetry,
    build_ta_feedback_config,
    inject_card_html_ta_feedback,
    inject_card_html_telemetry,
    load_ta_feedback_script,
    load_telemetry_script,
    read_ta_feedback,
    resolve_ta_feedback_js_path,
    write_ta_feedback,
    parse_group_param,
    parse_week_param,
    resolve_telemetry_js_path,
    telemetry_js_diag,
    telemetry_storage_key,
)

_OPUS_CFG_DEFAULT = "claude-opus-4.7"


def _opus_cfg_name() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('card_html', _OPUS_CFG_DEFAULT)

# 生成卡片 HTML 时「勾选文档向量/分块 + 可选 Gxx」总字数上限（梯子图多为位图走三层理解，单段不宜过大）
_CARD_HTML_DOC_BUNDLE_CAP_DEFAULT = 45000
_CARD_HTML_DOC_BUNDLE_CAP_LADDER = 60000
_CARD_HTML_GXX_BODY_CAP = 28000


def _card_html_dir(username: str) -> str:
    return os.path.normpath(f"./received_dir/user_raw_file/{username}/cardHtml").replace("\\", "/")


def _card_html_path(username: str, cid: int) -> str:
    d = _card_html_dir(username)
    return os.path.join(d, f"{int(cid)}.html")


def _card_html_last_version_dir(username: str) -> str:
    return os.path.join(_card_html_dir(username), "lastVersion")


def _card_html_last_version_path(username: str, cid: int) -> str:
    return os.path.join(_card_html_last_version_dir(username), f"{int(cid)}.html")


def _backup_card_html_before_overwrite(username: str, cid: int) -> bool:
    """覆盖前将当前 cid.html 留存到 lastVersion/{cid}.html。无现文件则跳过。"""
    src = _card_html_path(username, cid)
    if not os.path.isfile(src):
        return False
    dst_dir = _card_html_last_version_dir(username)
    os.makedirs(dst_dir, exist_ok=True)
    dst = _card_html_last_version_path(username, cid)
    try:
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
        with open(dst, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[card_html] 已备份 {cid}.html -> lastVersion/{cid}.html")
        return True
    except Exception as e:
        print(f"[card_html] 备份 lastVersion 失败 cid={cid}: {e}")
        return False


def _has_card_html_last_version(username: str, cid: int) -> bool:
    return os.path.isfile(_card_html_last_version_path(username, cid))


def _read_card_html_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_body_inner(html: str) -> str:
    m = re.search(r"<body[^>]*>([\s\S]*?)</body>", html or "", re.I)
    return (m.group(1) if m else "").strip()


def _replace_body_inner(html: str, new_body_inner: str) -> str:
    source = html or ""
    m = re.search(r"(<body[^>]*>)([\s\S]*?)(</body>)", source, re.I)
    if not m:
        raise ValueError("无法定位 body 标签")
    inner = (new_body_inner or "").strip()
    return source[: m.start(2)] + inner + source[m.end(2) :]


def _normalize_iterate_body_output(raw: str) -> str:
    """迭代场景：模型应只返回 body 内层；兼容误输出完整 HTML 或 Markdown 围栏。"""
    s = (raw or "").strip()
    if not s:
        return ""
    m = re.search(r"```(?:html)?\s*([\s\S]*?)```", s, re.I)
    if m:
        s = m.group(1).strip()
    if re.search(r"<body[\s>]", s, re.I):
        inner = _extract_body_inner(s if re.search(r"</body>", s, re.I) else f"{s}</body>")
        if inner:
            return inner
    if re.search(r"<!doctype|<html[\s>]", s, re.I):
        inner = _extract_body_inner(s if re.search(r"</body>", s, re.I) else f"{s}</body>")
        if inner:
            return inner
    return s


def _card_feedback_html_path(username: str, cid: int) -> str:
    """小组作答可视化报告（只读），与交互助记 {cid}.html 分文件存放。"""
    d = _card_html_dir(username)
    return os.path.join(d, f"{int(cid)}.feedback.html")


def _card_image_path(username: str, cid: int) -> Optional[str]:
    base = os.path.normpath(f"./received_dir/user_raw_file/{username}/cardImage").replace("\\", "/")
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        p = os.path.join(base, f"{int(cid)}{ext}")
        if os.path.isfile(p):
            return p
    return None


def _read_image_as_data_url(path: str) -> Tuple[str, str]:
    ext = os.path.splitext(path)[1].lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return mime, b64


def _parse_file_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            arr = json.loads(s)
            return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in s.split(",") if x.strip()]


def _text_from_split_docs(username: str, doc_name: str, cap: int = 12000) -> str:
    from llm_langchain import parse_input

    try:
        docs = parse_input.get_split_by_user_docs(username, [doc_name])
    except Exception as e:
        print(f"[card_html] get_split_by_user_docs fail {doc_name}: {e}")
        return ""
    buf: List[str] = []
    n = 0
    for doc in docs or []:
        meta = getattr(doc, "metadata", None) or {}
        if meta.get("type") == "image":
            continue
        t = (getattr(doc, "page_content", None) or "").strip()
        if not t:
            continue
        buf.append(t)
        n += len(t)
        if n >= cap:
            break
    out = "\n\n".join(buf)
    return out[:cap]


def _is_ladder_fill_image_filename(fn: str) -> bool:
    """文件名含「梯子图填写」且为常见位图后缀（与 NK2026 A 类一致）。"""
    if not fn or "梯子图填写" not in fn:
        return False
    low = fn.lower()
    return low.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))


def _file_list_has_ladder_fill_image(file_names: Sequence[str]) -> bool:
    return any(_is_ladder_fill_image_filename(x) for x in (file_names or []) if x)


def _image_layers_text(
    username: str,
    doc_name: str,
    cap: int = 14000,
    *,
    max_seq: int = 48,
) -> str:
    from llm_langchain import parse_input

    low = doc_name.lower()
    if not (
        low.endswith(".pdf")
        or low.endswith(".png")
        or low.endswith(".jpg")
        or low.endswith(".jpeg")
        or low.endswith(".webp")
    ):
        return ""
    parts: List[str] = []
    total = 0
    for seq in range(max(1, max_seq)):
        try:
            chunk = parse_input.get_pdf_image_sum(username, doc_name, seq)
        except Exception as e:
            print(f"[card_html] get_pdf_image_sum {doc_name} seq={seq}: {e}")
            break
        chunk = (chunk or "").strip()
        if not chunk or "图片分析结果暂未可用" in chunk or "未能获取到第" in chunk:
            if seq == 0:
                continue
            break
        block = f"【文档「{doc_name}」第{seq + 1}页/张·三层理解】\n{chunk}"
        parts.append(block)
        total += len(block)
        if total >= cap:
            break
    return "\n\n".join(parts)[:cap]


def _parse_int_id_list(raw: Any) -> List[int]:
    if raw is None:
        return []
    if isinstance(raw, list):
        out: List[int] = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out
    s = str(raw).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            arr = json.loads(s)
            return _parse_int_id_list(arr)
        except Exception:
            pass
    return _parse_int_id_list([x.strip() for x in s.split(",") if x.strip()])


def _build_choosed_cards_bundle(username: str, main_cid: int, other_cids: Sequence[int]) -> str:
    """主卡片正文已在 card.content；此处仅拼接其它勾选卡片全文。"""
    ids = sorted({int(x) for x in other_cids if int(x) != int(main_cid)})
    if not ids:
        return ""
    blocks: List[str] = []
    total = 0
    cap = 80000
    for oc in ids:
        try:
            c = Card.objects.get(username=username, cid=oc)
        except Card.DoesNotExist:
            blocks.append(f"### 勾选卡片 cid={oc}\n（不存在或无权访问）")
            continue
        title = (c.contentTitle or "").strip() or f"卡片{oc}"
        body = (c.content or "").strip()
        sec = f"### 勾选卡片 cid={oc} · {title}\n{body}"
        if total + len(sec) > cap:
            blocks.append(sec[: max(0, cap - total)] + "\n…(勾选卡片总长度截断)")
            break
        blocks.append(sec)
        total += len(sec)
    return "\n\n---\n\n".join(blocks)


def _build_doc_bundle(username: str, file_names: Sequence[str]) -> str:
    blocks: List[str] = []
    has_ladder_img = _file_list_has_ladder_fill_image(file_names)
    max_out = _CARD_HTML_DOC_BUNDLE_CAP_LADDER if has_ladder_img else _CARD_HTML_DOC_BUNDLE_CAP_DEFAULT
    for fn in file_names:
        if not fn:
            continue
        low = fn.lower()
        sec: List[str] = [f"### 勾选文档：{fn}"]
        ladder_fill = "梯子图填写" in fn
        # 梯子图填写：仍多取几页/张三层理解，但总 bundle 仅数万字，避免单次拉取过大
        vec_cap = min(52000, max_out) if ladder_fill else 14000
        vec_seq = 160 if ladder_fill else 48
        if low.endswith(".pdf") or low.endswith(".txt") or low.endswith(".md"):
            tx = _text_from_split_docs(username, fn)
            if tx:
                sec.append("【正文/摘录】\n" + tx)
            im = _image_layers_text(username, fn, cap=vec_cap, max_seq=vec_seq)
            if im:
                sec.append("【图片类·向量库三层理解】\n" + im)
        elif low.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            im = _image_layers_text(username, fn, cap=vec_cap, max_seq=vec_seq)
            if im:
                sec.append("【图片类·向量库三层理解】\n" + im)
            else:
                sec.append("（该图片文档暂无三层理解文本）")
        else:
            tx = _text_from_split_docs(username, fn)
            if tx:
                sec.append(tx)
        blocks.append("\n".join(sec))
    return "\n\n---\n\n".join(blocks)[:max_out]


def _user_raw_base_for_twin(username: str) -> str:
    return os.path.normpath("./received_dir/user_raw_file/" + username.replace("\\", "/"))


def _merge_doc_bundle_reserving_gxx_tail(
    doc_bundle: str,
    gxx_body: str,
    gid: int,
    max_total: int,
) -> str:
    """总额不超过 max_total。若 Gxx 非空则必进入上下文：优先截短勾选文档，仅在 Gxx 超长时截短 Gxx。"""
    doc = (doc_bundle or "").strip()
    gxx = (gxx_body or "").strip()
    if not gxx:
        return doc[:max_total]
    marker = f"\n\n---\n\n### 卡片标题关联组 twin（G{int(gid):02d}.md 全文摘录）\n"
    tail = marker + gxx
    if len(doc) + len(tail) <= max_total:
        return (doc + tail)[:max_total]
    keep = max_total - len(tail)
    if keep >= 400:
        doc_trim = doc[:keep] + "\n…（勾选文档已为保留下方 Gxx 摘要截断）"
        return (doc_trim + tail)[:max_total]
    gxx_room = max(0, max_total - len(marker) - 120)
    gxx2 = (gxx[:gxx_room] + "\n…（Gxx 过长已截断）") if len(gxx) > gxx_room else gxx
    tail2 = marker + gxx2
    doc_room = max(0, max_total - len(tail2))
    doc2 = (doc[:doc_room] + "\n…（截断）") if doc_room > 80 else ""
    return (doc2 + tail2)[:max_total]


def _merge_doc_bundle_reserving_zhengben_tail(
    doc_bundle: str,
    zhengben_body: str,
    max_total: int,
) -> str:
    """总额不超过 max_total；正本清源摘录非空时必进入上下文（优先截短勾选文档）。"""
    doc = (doc_bundle or "").strip()
    body = (zhengben_body or "").strip()
    if not body:
        return doc[:max_total]
    marker = "\n\n---\n\n### 纸联体联除乘加正本清源（W13+ 必读）\n"
    tail = marker + body
    if len(doc) + len(tail) <= max_total:
        return (doc + tail)[:max_total]
    keep = max_total - len(tail)
    if keep >= 400:
        doc_trim = doc[:keep] + "\n…（勾选文档已为保留正本清源摘录截断）"
        return (doc_trim + tail)[:max_total]
    body_room = max(0, max_total - len(marker) - 120)
    body2 = (body[:body_room] + "\n…（正本清源过长已截断）") if len(body) > body_room else body
    tail2 = marker + body2
    doc_room = max(0, max_total - len(tail2))
    doc2 = (doc[:doc_room] + "\n…（截断）") if doc_room > 80 else ""
    return (doc2 + tail2)[:max_total]


def _read_gxx_twin_markdown(username: str, gid: int, cap: int = _CARD_HTML_GXX_BODY_CAP) -> str:
    """读取用户 _twin/Gxx.md（与 group_twin_gxx 落盘路径一致）；避免循环 import。"""
    path = os.path.join(_user_raw_base_for_twin(username), "_twin", f"G{int(gid):02d}.md")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()[:cap]
    except Exception as e:
        print(f"[card_html] read twin G{int(gid):02d}.md fail: {e}")
        return ""


def _content_title_suggests_gxx_context(title: str) -> bool:
    """标题中含「N组」或 Gxx 形态时，尝试附加对应 Gxx.md。"""
    t = title or ""
    if re.search(r"G0*\d{1,2}(?!\d)", t, re.I):
        return True
    if re.search(r"(?<![Ww])(\d{1,2})\s*组", t):
        return True
    return False


def _parse_group_id_from_card_title(title: str) -> Optional[int]:
    if not title:
        return None
    m = re.search(r"G0*(\d{1,2})(?!\d)", title, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(?<![Ww])(\d{1,2})\s*组", title)
    if m:
        return int(m.group(1))
    return None


def _extract_html_from_model_output(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    m = re.search(r"```html\s*([\s\S]*?)```", s, re.I)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```\s*([\s\S]*?)```", s)
    if m2 and ("<html" in m2.group(1).lower() or "<!doctype" in m2.group(1).lower()):
        return m2.group(1).strip()
    if "<html" in s.lower() or "<!doctype" in s.lower():
        return s
    return s


def _opus_client_and_model() -> Tuple[OpenAI, str, int]:
    mc = config_manager.get_model_config(_opus_cfg_name())
    cfg = mc.config_data.get("config") or {}
    api_key = (cfg.get("openai_api_key") or "").strip()
    base = (cfg.get("openai_api_base") or "").strip().rstrip("/") + "/"
    model = (cfg.get("model_name") or "").strip()
    if not api_key or not model:
        raise RuntimeError("claude-opus-4.7 配置缺失（openai_api_key / model_name）")
    hp = mc.get_hyper_para().to_dict()
    max_tokens = int(hp.get("max_tokens") or 32000)
    client = OpenAI(api_key=api_key, base_url=base, default_headers=cfg.get("default_headers") or {"x-foo": "true"}, timeout=900.0)
    return client, model, max_tokens


# W11 G12/G17 经 card_html_telemetry.js 验证；最小 DOM 契约，内容优先
_NK2026_LADDER_HTML_TELEMETRY_SPEC = (
    "\n10) 写法上的一些硬性要求："
    "用 `const CARDS`/`DATA` 数组 + forEach **动态渲染** 6 张助记卡（五角色各 1 题 + 小组整体 1 题）。"
    "每题一个 `.card`，题面 `.face.front` 须含："
    "① class `.role` 写「角色·姓名」（**勿**只用 `.role-name`/`.who` 替代）；"
    "② `.q` 或 `.qtitle` 放题干；"
    "③ `ul.opts` 内 4 个 `li.opt[data-i=0..3]`，子元素 `.k`/`.letter` 标 A-D（最多到E，选项不宜过多）；"
    "④ `.tip` 或 `.feedback` 作错/对提示，显示时加 class `show`（勿仅用 style.display）。"
    "单选：点选即判或点选后点「提交判分」，误选加 `.wrong`、正确加 `.correct`/`.right`；"
    "多选：勾选时 li 加 `chosen`/`picked`/`sel`，**须**有 `button.submit`（文案含提交/判分）再统一判分。"
    "答对后给 `.card` 加 `flipped`，或 tip 以 ✓ 开头再翻面；背面 `.face.back` 只放 2～3 条张力路径精准建议，**选项不要放在 back 面**。\n"
)


def card_html_route(scene_name: str, notebook_description: str = "", card_title: str = "", extra: Optional[Dict[str, Any]] = None) -> str:
    extra = extra or {}
    sn = (scene_name or "").strip()
    title = card_title or ""
    book = notebook_description or ""
    if sn in NK2026_HTML_SCENE_WHITELIST or is_nk2026_ladder_scene(sn):
        route = "R0"
    elif (
        extra.get("grading_result")
        or "批改·" in title
        or "<!--nkcn_grading_card" in str(extra.get("card_content") or "")
        or "批改" in sn
        or "批改" in book
    ):
        route = "R1"
    else:
        route = "R2"
    if extra.get("grading_result") or "批改·" in title or "<!--nkcn_grading_card" in str(extra.get("card_content") or ""):
        try:
            from app_chat.homework_grading.yangqian_debug import debug_log
            debug_log(f'[card_html] 路由={route} scene={sn} title={title[:80]}')
        except Exception:
            pass
    return route


def _synthesis_prompts(
    notebook_description: str,
    scene_name: str,
    card_title: str,
    card_content: str,
    doc_bundle: str,
    choosed_cards_bundle: str,
    has_card_image: bool,
    route: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    extra = dict(extra or {})
    grading = route == "R1"
    workspace = ""
    if grading:
        try:
            from app_chat.homework_grading.result_cards import build_html_workspace_bundle
            workspace = build_html_workspace_bundle(
                str(extra.get("username") or ""), extra, extra.get("card_content") or card_content,
            )
        except Exception as exc:
            workspace = f"【批改工作区】本次未纳入（{exc}）。禁止编造课标或方法包全文。"
    duty = (
        "这是一份作业/试卷/作文/笔记的批改结果综述页，不是出题。"
        "页面一打开先见一句枢纽判断；再分栏：白话三问支撑该枢纽、认知三区（少而硬短卡片）、"
        "本子方法如何改变了判断（禁止报名清单）；开放材料若出现只写事实链（线），勿与诊断（面）复述。"
        "对错个数、错因频次、材料画像数字等循证信息一律放在页面后部「依据」区。"
        "禁止助记选择题、禁止编造课标句、禁止把方法包全文糊进去、禁止复刻报告栏目墙。"
        "主素材优先用筛后卡片 Markdown；工作区只作补证。"
        if grading else
        "根据本卡正文、配图理解（若有）、勾选文档摘录（若有）做整理、综合、梳理，输出层次清晰的单文件 HTML。"
        "禁止做成助记选择题翻面卡。"
    )
    system = (
        "你是资深学习内容编辑与前端设计方向的专家，只输出一份完整、可独立打开的 HTML5。\n"
        f"{duty}\n"
        "硬性要求：\n"
        "1) 单个 HTML：<!DOCTYPE html>、<html lang=\"zh-CN\">、内联 style/script，不要外链 CDN。\n"
        "2) 栏目用白话。若正文已有【看到了什么】【这说明什么】【下一步做什么】，HTML 里保留并展开，不要改成暗号标题。\n"
        "3) 结构要有枢纽 + 分栏 + 边界（什么能判断、什么材料未纳入）。\n"
        "4) 核心判断与方法贯穿放在视觉中心；统计数字克制地放后部。禁止 AI 腔、禁止鸡汤、禁止一面墙。\n"
        "5) 若提供了卡片配图，结合版面重点，但不要把大图嵌入 HTML。\n"
        "6) 美学克制，系统中文字体，CSS 变量色板。\n"
    )
    # 批改卡已有筛后 Markdown，正文截断收紧，避免再喂 24k 墙
    body_limit = 10000 if grading else 24000
    user = (
        f"【本子中文名/描述】\n{notebook_description or '（未提供）'}\n\n"
        f"【场景名】\n{scene_name or '（未提供）'}\n\n"
        f"【卡片标题】\n{card_title or '（无标题）'}\n\n"
        f"【卡片正文】\n{(card_content or '')[:body_limit]}\n\n"
        f"【其它勾选卡片】\n{choosed_cards_bundle or '（无）'}\n\n"
        f"【勾选文档补充】\n{doc_bundle or '（无）'}\n\n"
        f"【是否已提供卡片配图】\n{'是' if has_card_image else '否'}\n\n"
        + (f"【批改工作区（缺项已标明未纳入，禁止补造）】\n{workspace}\n\n" if grading else "")
        + "请直接输出完整 HTML，必须以 <!DOCTYPE html> 开头，不要 Markdown 包裹。"
    )
    return system, user


def _system_and_user_prompts(
    notebook_description: str,
    scene_name: str,
    card_title: str,
    card_content: str,
    doc_bundle: str,
    choosed_cards_bundle: str,
    has_card_image: bool,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    extra = dict(extra or {})
    extra.setdefault("card_content", card_content)
    route = card_html_route(scene_name, notebook_description, card_title, extra)
    if route != "R0":
        return _synthesis_prompts(
            notebook_description, scene_name, card_title, card_content,
            doc_bundle, choosed_cards_bundle, has_card_image, route, extra,
        )
    system = (
        "你是资深学习体验与前端设计方向的专家，只输出「一份完整、可独立打开的 HTML5 内容」。\n"
        "若涉及NK2026 梯子图批改等，则批改对象为**本科二年级课设小组**；若素材未提具体人物，则针对内容隐含的作者/叙述者视角：语言与认知负荷须匹配该阶段和对象主体，**禁止**出「一眼排除错误项」的低幼题目。\n"
        "硬性要求：\n"
        "1) 输出必须是单个 HTML 内容：含 <!DOCTYPE html>、<html lang=\"zh-CN\">、内联 <style> 与 <script>，不要外链 CDN（避免离线无法打开）。\n"
        "2) 综合理解「本子描述 + 场景名 + 当前卡片 + 其它勾选卡片 + 勾选文档/向量摘录/配图」**综合**学习情境；助记卡主题与设问应**跨块取材**，不得只复述当前卡片正文或只围绕一段摘抄打转。把核心/重要的内容放在页面视觉与阅读的中心区；其余信息作为补充/发散区，篇幅克制\n"
        "3) 强交互：助记卡（选择题 + 翻面）。**数量**：若素材能明确**本组多名成员及角色**（如组长、需求员、周志员、展示员、优裁员、组长助理等），则**尽量每位在材料中有据可查的核心角色各 1 张助记卡，并另设 1 张针对「小组整体」的助记卡**；\n"
        "卡片总数可随角色数调整（例如 5～8 张），仍须单文件、交互简洁。若无法识别具体人名与角色，则维持 **3～5 张**。"
        "每张卡先有选择题（单选或多选均可）。**题型与答案分布**：整套助记卡中**最好同时包含单选题与多选题**；各题**正确答案对应字母（A/B/C/D）须交叉分布**，避免多题正确答案均为同一字母（如全是 B）。**干扰项必须与正确项处于同一认知层次**：表述都要像「本组在当周真实会纠结的取舍」，针对素材中涉及的对象及其记录/填写/周边相关内容"
        "错误项应是**看似合理、需结合材料中的具体事实/原话/角色分工/周次语境**才能排除的那种；禁止用敷衍交差、明显摆烂、与课设常识相悖的弱智选项当陪衬**。"
        "题干和选项均要指向**盲区发现、内耗排除、双目标张力紧密结合前序除乘加分析和后续问题链Issue、组织/操作/精进/目标关的缝隙、认知易误点...**等；要涉及就近发展区，**无材料依据处不要牵强硬说**。\n"
        "4) 判分：选错时给**短而准**的提示（点出错因与材料中哪类依据被忽略，各错误选项不可共用相同的错误提示牵引），允许重试；选对后翻转助记卡：背面给 **2～3 条可立刻执行的张力路径**（动词开头、可检查的小步），"
        "每条须**锚定输入里出现的具体事实**：至少一条用 <q> 或引号**直接引用**某段原文短句（注明来自哪处素材，勿虚构）；"
        "禁止「加强沟通」「多反思」「注意平衡」等换组也成立的空话；禁止鸡汤式排比与 AI 腔套话，这会引起读者排斥，一定要真正能够帮助其发现盲区、走出内耗区（不要牵强硬说反而增加内耗，可以抓苗头提前规避）、找到就近发展区的问题、选项、选错后的提醒和选对后卡片翻面后的张力路径建议，具体再具体让人觉得非常贴近。另外用语要自然，不要生造自创词汇，也不要用过重的语气。"
        "多选题选后若有错选，重试须能清除 `.wrong`，即重试时错选的选项红色要能取消。\n"
        "5) 总阅读+交互时长控制在几分钟内，禁止臃肿长文与大量装饰废话。\n"
        "6) 美学：避免通用 AI 审美（拒绝 Inter/Roboto/Arial 为主字体、拒绝俗套紫白渐变）。自选一组有辨识度的字体栈（系统字体+中文衬线/黑体组合即可，字体要清晰美观避免浮夸艺术字），"
        "用 CSS 变量控制色板，可有克制的入场动画（纯 CSS）。\n"
        "7) 若下方提供了卡片配图，请结合图像理解版面与重点，但 HTML 中不要嵌入该大图（体积过大），仅在文案中引用其结构感知即可。\n"
        "8) **内联 `<script>` 中的 JavaScript 字符串**：凡在英文双引号 \"...\" 内书写中文引语、术语需要套引号时，**必须**使用中文弯引号「“」(U+201C) 与「”」(U+201D)，**禁止**在串内再嵌未转义的 ASCII 英文双引号 \\u0022，否则整段脚本语法错误、交互失效；"
        "更推荐外层字符串统一用英文单引号 '...' 包裹，内层用中文「“」「”」表示引语。\n"
        "9) **助记卡题面高度**：每张选择题卡的外层**禁止用过小的固定 height 裁切内容**（避免出现靠后选项只露一截、无法阅读）；用 **min-height:auto** 或显式足够 **min-height**、充足 **padding**、**overflow:visible**（或等价布局），保证题干与 A～D 四选项在翻面/判分前**完整落在卡内可见**。\n"
    )
    if is_nk2026_ladder_scene(scene_name):
        system += _NK2026_LADDER_HTML_TELEMETRY_SPEC

    user = (
        f"【本子中文名/描述 bookdescription】\n{notebook_description or '（未提供）'}\n\n"
        f"【场景名】\n{scene_name or '（未提供）'}\n\n"
        f"【卡片标题】\n{card_title or '（无标题）'}\n\n"
        f"【卡片正文（核心素材之一；勿作为唯一出题来源）】\n{(card_content or '')[:20000]}\n\n"
        f"【其它勾选卡片全文（若有；与当前卡、文档一并作为出题与翻面依据）】\n{choosed_cards_bundle or '（无）'}\n\n"
        f"【勾选文档补充（向量分块 / 图片三层理解 / twin Gxx 等；与上文合并使用）】\n{doc_bundle or '（无）'}\n\n"
        f"【是否已提供卡片配图给多模态模型】\n{'是' if has_card_image else '否'}\n\n"
        "【选择题与翻面（注意事项）】\n"
        "- 每张助记卡：四个选项在语气上**并列可信**，错误项不得像故意摆烂或中小学生恶作剧。\n"
        "- **题型**：整套中尽量**既有单选又有多选**；**正确答案字母**在题与题之间**不要雷同**（勿多题全为同一正确项）。\n"
        "- **版式**：题卡容器须能**完整容纳题干+四选项**；翻面后背面文案同样不可被裁切。\n"
        "- 翻面建议：2～3 条，每条 ≤50 字为宜；必须含**至少一处带引号的原文**（来自上述任一输入块，描述来自哪处素材时，不要说是某卡片/文档，要说清是此组梯子图哪些区域填写<不要说Dxx，要说其实际内涵如V2.x目标填写区、精进关心得等>/除乘加分析/问题链Issue/飞书I&II类问题/精进种子打点/涌现微创新/代码注释修改/规划表需求/8XML日志记录/小组激励谈话等具体来源里的具体什么原文/原话内容，这样读者才能懂）。\n"
        "- 每条都要以素材依据的真实情况为出发点，在此基础上自洽且有说服力。\n"
        "- **脚本内文案引号**：`tips`、选项文案、提示语等写入 JS 字符串时，串内套引号须用中文弯引号 “ ”，勿用英文 \" 嵌在英文双引号串内。\n"
        "- **角色与题量**：能识别具体组员与角色时，按「每角色一题 + 小组整体一题」分配助记卡；整体题要落在协作、除乘加-目标-问题链紧密打通、破除多张皮、产生主题涌现微创新等组级张力上。\n\n"
        "请直接输出完整 HTML 正文，不要用 Markdown 包裹，你的回答必须以“<!DOCTYPE html>”开头；如需标注可对关键段用 HTML 注释。不可分多轮完成，需一次性完成，直接开始输出HTML正文（禁止生成文件create file，而是将html内容文本直接输出出来）！"
    )
    return system, user


# 迭代时告知模型：初版 HTML 是按下列要求生成的，须继续遵守并做得更好
_HTML_GEN_SPEC_SUMMARY_FOR_ITERATE = (
    "【初版生成时的要求摘要（迭代须继续遵守并优于初版；结构/交互/答案不动，内容与表达要更贴近下列标准）】\n"
    "1) **单文件 HTML**：<!DOCTYPE html>、<html lang=\"zh-CN\">、内联 <style> 与 <script>。\n"
    "2) **综合取材**：须综合本子描述、场景名、当前卡、其它勾选卡片、勾选文档/向量摘录/配图/三层理解等**与此组相关的**学习情境出题和写依据。\n"
    "3) **助记卡数量与角色**：素材能识别本组成员与角色（组长、需求员、周志员、展示员、优裁员等）时，"
    "**每位有据可查的核心角色各 1 题 + 小组整体 1 题**（通常 6 张）；无法识别时 3～5 张。\n"
    "4) **题型与选项质量**：单选/多选并存；各题正确答案字母（A/B/C/D）宜交叉分布，避免多题同字母。"
    "干扰项须与正确项同认知层次，像本组当周真实会纠结的取舍，需结合材料具体事实/原话/角色分工才能排除；"
    "禁止敷衍摆烂、一眼可排除的低幼项。题干指向盲区发现、内耗排除、除乘加与 Issue 链/各关填写缝隙、认知易误点等，以主题除乘加为核心源头，关联周边所有相关素材。\n"
    "5) **判分与翻面**：错选给短而准的提示（各错项提示不可雷同），允许重试；选对后翻面，背面 **2～3 条可立刻执行的张力路径**"
    "（动词开头、可检查小步），每条须引用输入素材中的具体事实，至少一处用 <q> 或引号直接引用原文并说明来源"
    "（梯子图哪类填写区、除乘加分析、Issue、飞书 I/II/III 类问题、8XML、激励谈话、代码注释等，勿说 Dxx 代号而说实际内涵）。"
    "禁止「加强沟通」「多反思」等换组也成立的空话与 AI 腔套话。\n"
    "6) **脚本引号**：JS 字符串内中文引语用弯引号 “ ”，勿在英文双引号串内嵌未转义 ASCII \"；推荐外层单引号包裹。\n"
)


def _system_and_user_prompts_iterate(
    notebook_description: str,
    scene_name: str,
    card_title: str,
    card_content: str,
    doc_bundle: str,
    choosed_cards_bundle: str,
    has_card_image: bool,
    existing_body_inner: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    extra = dict(extra or {})
    extra.setdefault("card_content", card_content)
    route = card_html_route(scene_name, notebook_description, card_title, extra)
    sys_p, user_base = _system_and_user_prompts(
        notebook_description,
        scene_name,
        card_title,
        card_content,
        doc_bundle,
        choosed_cards_bundle,
        has_card_image,
        extra,
    )
    if route != "R0":
        sys_p = (
            "你在精修一份综述型卡片 HTML 的 <body> 内部。"
            "只输出 body 内部片段，不要 <!DOCTYPE>/<html>/<body> 外壳，不要 Markdown。"
            "保持枢纽+分栏+边界的综述结构，禁止改成助记选择题翻面卡。"
            "前部必须是批改判断、三问、三区建议与方法贯穿；对错统计放到后部依据区。"
            "可把层次写得更清楚；材料里没有的课标、年级、主体不要编。"
        )
        user_p = (
            f"【卡片标题】{card_title}\n【卡片正文】\n{(card_content or '')[:12000]}\n\n"
            "【现有 body 主体】\n" + (existing_body_inner or "")[:80000]
        )
        return sys_p, user_p
    nk2026 = is_nk2026_ladder_scene(scene_name)
    if nk2026:
        iterate_rules = (
            "【迭代任务 · NK2026 梯子图批改场景】\n"
            "你收到的是**已有**助记 HTML 的 `<body>` 主体。"
            "**仅输出**微调精修后的这个 `<body>` **片段**"
            "（不要输出 `<!DOCTYPE>`、`<html>`、`<head>`、`<body>`/`</body>` 标签，也不要 Markdown 代码块）。\n"
            "`<body>` 内 DOM/JS 结构、题型（单选/多选及其写法）、正确答案索引、"
            "选项个数与顺序、渲染/判分/翻面逻辑、HTML 标签名与 class/id 等等均须**原样保留**。\n"
            "仅允许**微调精修**下列**显示文字**：`CARDS` 内各题题干、选项文案、"
            "各选项判别后的提示牵引句（数组或对象形态须保持，空串占位须保留）、`back` 即答对翻面后的2-3条张力路径建议；"
            "**大致意思不要变，只精修优化表达，若有明显更好的内容可以适当改写，但要保证满足下面的比例要求**。"
            " 上述几处文字合计修改量不得超过原文对应部分字数的 **15%～20%**（不是占整个 body 的比例）。\n\n"
            "迭代是**微调、精修**，主要注意下面四点：\n\n"
            "1. **事实与课程词必须准，不能编造**\n"
            "- 8XML 日志、issue/commit 趋势、代码注释、角色、梯子图填写区名及内容、除/乘/加法则分析……等基本信息，"
            "若有则须与当周本组素材信息一致。\n"
            "- 代码注释/硬件/工具细节只写素材里出现过的；不把 OpenClaw（大模型赋能是可以的，讲清如何辅助强化主题内涵即可，OpenClaw 过头了）"
            "等未证实属于本小组的内容塞进正确选项/给学生建议的路径里。\n\n"
            "2. **小组相关各类素材之间的关系和课设标杆流程要清楚，这样才能给好路径建议**\n"
            "各小组要以本组的所属主题除乘加分析为源头，课设实验课前开好小组会，根据新一周对助教精进种子的理解，"
            "吸取上一周小组激励谈话、TA 助教小结、给本组的综合批改建议中的经验，考虑承接本组前序周次所做精进，"
            "确立小组新一周要给当前版本双 O 做什么修正，以此更新本组需求规划表，并确立本周小组 Issue 递进问题链和分工 Board，"
            "在课设实验课上分工做的过程中遇到问题优先组内或结伴组间化解，可飞书提交 III/II/I 类问题（III 类多转化到 II 类和 I 类），"
            "最终力求做出本组的蛙鸣涌现/微创新，验收达到下/中/上线水准，并在 8XML（含小组整体和各角色）做好记录，"
            "上传提交的代码中写好段注释、行注释、行内注释（行内注释用于且仅用于标注人/机生成情况），"
            "上述除乘加浓缩、当前版本课程+组织双目标、组织关/操作关/精进关/目标关/角色职责公份/每人都需做私份心得、"
            "涌现/微创新点等都要在梯子图上随周随时记录更新。"
            "（上述相关素材每个组除了自己的以外也基本都可以横向看到本主题内其他组的，关注但不仅限于自己组的结伴组，"
            "有些也可以看到其他主题的，都可以吸取优点做本组化吸收。）\n\n"
            "3. **不要用 AI 诊断式不自然腔调和用语**\n"
            "调整不适合大二小组学生阅读、描述过度/夸张（如「极佳」「很差」等要改为「较优」「偏弱」等平和的描述）、"
            "AI 味太重不像人话（如「落盘、痛点、锚点、锚定、锚、下沉、上提、前压、回流、起跳、收口、抓手、黑箱、防线、对冲"
            "孤岛、困境、错位、空转、漂移、留痕、审计、指认」等让学生看不懂的明显 AI 黑话）的空泛描述，"
            "改为直白、具体、易懂的描述，且依然符合课程语境，保留并写准素材里的课程词。\n\n"
            "4. **保持迭代前内容里已有的优点并更加符合前面的 1、2、3 点**\n"
            "整体及细节都精准针对此小组及其各角色，让学生觉得「是真的看了我们组的东西，不是模板套出来的、"
            "不是拿给其他组也适用的，而是细心针对我们小组的」。"
            "能够把与这组相关的各类文档、谈话、内容填写、代码注释、日志等信息都收拢起来并注意到它们之间的联系；"
            "能够横向迁移优秀经验，包括课设主题内涵上的、组织协作上的、各种知识/方法/思路上的；"
            "能够精准此组找到不足问题、发现亮点、给出合适学生的就近发展建议，"
            "建议有多种视角、张力路径给各不同角色/小组整体，且分别都有与此组相关内容的原文原话、来源依据，"
            "并非空谈或模板套路，能真正为此小组和各角色降阻而不是增负。\n"
        )
    else:
        iterate_rules = (
            "【迭代任务 · 一般场景】\n"
            "你收到的是**已有**助记 HTML 的 `<body>` 主体。"
            "**仅输出**微调精修后的 `<body>` **内部 HTML 片段**"
            "（不要输出完整 HTML 文档或 `<body>`/`</body>` 外层标签，也不要 Markdown 代码块）。\n"
            "`<body>` 内的 HTML/CSS/JS **代码结构与布局须完全不变**，仅精准化、深化、优化**显示给用户看的文字内容**；"
            "标签名、class、id、脚本逻辑、交互流程均不得改动。\n"
        )
    system = sys_p + "\n\n" + iterate_rules
    user = (
        user_base
        + "\n\n"
        + _HTML_GEN_SPEC_SUMMARY_FOR_ITERATE
        + "\n\n【现有 HTML 的 body 主体（迭代基准；结构勿动，仅按上文规则微调精修文字）】\n"
        + (existing_body_inner or "（未能解析 body 内容）")[:80000]
        + "\n\n请直接输出微调后的 body 内片段，不要用 Markdown 包裹，不要输出 body 以外的内容。"
    )
    return system, user


def _collect_card_html_context(
    username: str,
    cid: int,
    data: Dict[str, Any],
    *,
    inject_chuchengjia_zhengben: bool = False,
) -> Dict[str, Any]:
    file_list = _parse_file_list(data.get("filenamelist") or data.get("fileNameList"))
    choosed_ids = _parse_int_id_list(
        data.get("choosedCardIdList")
        or data.get("choosed_card_id_list")
        or data.get("cardIndexList")
    )
    card = Card.objects.get(username=username, cid=cid)
    scene_name, _sub, _summary, notebook_description = get_scene_info_from_username(username)
    doc_bundle = _build_doc_bundle(username, file_list)
    max_doc = (
        _CARD_HTML_DOC_BUNDLE_CAP_LADDER
        if _file_list_has_ladder_fill_image(file_list)
        else _CARD_HTML_DOC_BUNDLE_CAP_DEFAULT
    )
    title = (card.contentTitle or "").strip()
    if _content_title_suggests_gxx_context(title):
        gid_card = _parse_group_id_from_card_title(title)
        if gid_card is not None:
            gxx_body = _read_gxx_twin_markdown(username, gid_card)
            if gxx_body.strip():
                doc_bundle = _merge_doc_bundle_reserving_gxx_tail(
                    doc_bundle, gxx_body.strip(), gid_card, max_doc
                )
    if (
        inject_chuchengjia_zhengben
        and is_nk2026_ladder_scene(scene_name or "")
        and text_references_course_week_at_least(title, NK2026_CHUCHENGJIA_WEEK_MIN)
    ):
        zhengben = read_nk2026_chuchengjia_twin_markdown(username)
        if zhengben.strip():
            doc_bundle = _merge_doc_bundle_reserving_zhengben_tail(
                doc_bundle, zhengben.strip(), max_doc
            )
            print(f"[card_html] 已注入正本清源摘录 {len(zhengben.strip())} 字")
    cards_bundle = _build_choosed_cards_bundle(username, cid, choosed_ids)
    img_path = _card_image_path(username, cid)
    mime_b64: Optional[Tuple[str, str]] = None
    if img_path:
        try:
            mime_b64 = _read_image_as_data_url(img_path)
        except Exception as e:
            print(f"[card_html] read card image fail: {e}")
    return {
        "card": card,
        "scene_name": scene_name or "",
        "notebook_description": notebook_description or "",
        "doc_bundle": doc_bundle,
        "cards_bundle": cards_bundle,
        "mime_b64": mime_b64,
        "file_list": file_list,
        "choosed_ids": choosed_ids,
    }


def _opus_stream_html_completion(messages: List[Dict[str, Any]], *, max_attempts: int = 2) -> str:
    client, model, max_tokens = _opus_client_and_model()
    last_err: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=min(max_tokens, 60000),
                stream=True,
            )
            parts: List[str] = []
            for chunk in stream:
                if not chunk.choices:
                    continue
                ch0 = chunk.choices[0]
                delta = getattr(ch0, "delta", None)
                if delta is None:
                    continue
                piece = getattr(delta, "content", None) or ""
                if piece:
                    parts.append(piece)
            raw = "".join(parts).strip()
            print(f"[card_html] opus 原始输出内容：{raw}")
            html = _extract_html_from_model_output(raw)
            if html and len(html) >= 80:
                return html
            last_err = RuntimeError("模型未返回可用 HTML")
            print(f"[card_html] opus 第{attempt}次输出无效，重试…")
        except Exception as e:
            last_err = e
            print(f"[card_html] opus 第{attempt}次调用失败: {e}")
    raise RuntimeError(str(last_err or "模型调用失败"))


def _save_card_html(username: str, cid: int, html: str, *, backup_before: bool) -> str:
    if backup_before:
        _backup_card_html_before_overwrite(username, cid)
    out_dir = _card_html_dir(username)
    os.makedirs(out_dir, exist_ok=True)
    out_path = _card_html_path(username, cid)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def _build_card_html_messages(
    sys_p: str,
    user_p: str,
    mime_b64: Optional[Tuple[str, str]],
) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = [{"role": "system", "content": sys_p}]
    if mime_b64:
        mime, b64 = mime_b64
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_p + "\n\n【以下为当前卡片配图，请结合理解】"},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": user_p})
    return messages


@csrf_exempt
def card_html_exists(request):
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "只支持 GET"})
    username = (request.GET.get("username") or "").strip()
    cid_raw = request.GET.get("cid") or ""
    if not username or cid_raw == "":
        return JsonResponse({"error_num": 1, "msg": "缺少 username 或 cid"})
    try:
        cid = int(cid_raw)
    except ValueError:
        return JsonResponse({"error_num": 1, "msg": "cid 非法"})
    p = _card_html_path(username, cid)
    exists = os.path.isfile(p)
    has_last = _has_card_html_last_version(username, cid)
    return JsonResponse({
        "error_num": 0,
        "msg": "success",
        "has_html": exists,
        "has_last_version": has_last,
    })


@csrf_exempt
def card_html_raw(request):
    """返回已保存的 HTML 原文（JSON），供复制/下载。"""
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "只支持 GET"})
    username = (request.GET.get("username") or "").strip()
    cid_raw = request.GET.get("cid") or ""
    if not username or cid_raw == "":
        return JsonResponse({"error_num": 1, "msg": "缺少 username 或 cid"})
    try:
        cid = int(cid_raw)
    except ValueError:
        return JsonResponse({"error_num": 1, "msg": "cid 非法"})
    p = _card_html_path(username, cid)
    if not os.path.isfile(p):
        return JsonResponse({"error_num": 1, "msg": "暂无 HTML 文件"})
    try:
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    return JsonResponse({"error_num": 0, "msg": "success", "html": html})


@csrf_exempt
@xframe_options_exempt
def card_html_view(request):
    """浏览器/iframe 直接打开（text/html）。

    前端 dev 常为 localhost:8080、API 为 localhost:8000，属跨源嵌入；若不加 exempt，
    Django 默认 X-Frame-Options: SAMEORIGIN 会阻止 iframe，浏览器常表现为「拒绝连接」类空白；
    新窗口直接打开 :8000 则不受此限制。本视图内容为用户自己的助记 HTML，允许被嵌入预览。
    """
    if request.method != "GET":
        return HttpResponse("Method Not Allowed", status=405)
    username = (request.GET.get("username") or "").strip()
    cid_raw = request.GET.get("cid") or ""
    if not username or cid_raw == "":
        return HttpResponse("Bad Request", status=400)
    try:
        cid = int(cid_raw)
    except ValueError:
        return HttpResponse("Bad Request", status=400)
    p = _card_html_path(username, cid)
    if not os.path.isfile(p):
        return HttpResponse("<!DOCTYPE html><html><body><p>未找到该卡片的 HTML 文件。</p></body></html>", status=404, content_type="text/html; charset=utf-8")
    try:
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        return HttpResponse(f"<pre>读取失败: {e}</pre>", status=500, content_type="text/html; charset=utf-8")

    if (request.GET.get("telemetry") or "1").strip().lower() not in ("0", "false", "no", "off"):
        pick_q = (request.GET.get("pick") or "").strip().lower()
        force_pick = pick_q in ("1", "true", "yes", "force")
        inj_err = None
        try:
            cfg = build_telemetry_config(
                username,
                cid,
                submit_url=request.build_absolute_uri("/api/card_html_feedback_submit"),
                summary_url=request.build_absolute_uri("/api/card_html_feedback_summary"),
                force_pick=force_pick,
                html_text=html,
            )
        except Exception as cfg_e:
            print(f"[card_html_view] telemetry cfg fail: {cfg_e}")
            inj_err = f"cfg: {cfg_e}"
            _w = infer_week_for_telemetry("", html)
            cfg = {
                "username": username,
                "cid": int(cid),
                "groupId": None,
                "cardTitle": "",
                "contentWeek": _w,
                "roster": [],
                "submitUrl": request.build_absolute_uri("/api/card_html_feedback_submit"),
                "summaryUrl": request.build_absolute_uri("/api/card_html_feedback_summary"),
                "storageKey": telemetry_storage_key(username, int(cid), _w),
                "forcePick": force_pick,
            }
        try:
            js_url = request.build_absolute_uri("/api/card_html_telemetry.js")
            html = inject_card_html_telemetry(html, cfg, telemetry_script_url=js_url)
        except Exception as inj_e:
            print(f"[card_html_view] telemetry inject fail: {inj_e}")
            inj_err = inj_err or str(inj_e)
            err_js = json.dumps(str(inj_e), ensure_ascii=False)
            html = (
                html
                + f"\n<!-- nkcn-telemetry-inject-failed: {inj_err} -->\n"
                + f"<script>console.error('[NKCN] 遥测注入失败，作答不会落盘:', {err_js});</script>\n"
            )

    resp = HttpResponse(html, content_type="text/html; charset=utf-8")
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@csrf_exempt
@xframe_options_exempt
def card_feedback_html_view(request):
    """浏览器打开小组作答可视化 HTML（{cid}.feedback.html），不注入遥测。

    GET /api/card_feedback_html_view?username=...&cid=...
    文件路径：received_dir/user_raw_file/<username>/cardHtml/<cid>.feedback.html
    """
    if request.method != "GET":
        return HttpResponse("Method Not Allowed", status=405)
    username = (request.GET.get("username") or "").strip()
    cid_raw = request.GET.get("cid") or ""
    if not username or cid_raw == "":
        return HttpResponse("Bad Request", status=400)
    try:
        cid = int(cid_raw)
    except ValueError:
        return HttpResponse("Bad Request", status=400)
    p = _card_feedback_html_path(username, cid)
    if not os.path.isfile(p):
        return HttpResponse(
            "<!DOCTYPE html><html><body><p>未找到该卡片的小组作答可视化 HTML（"
            f"{int(cid)}.feedback.html）。</p></body></html>",
            status=404,
            content_type="text/html; charset=utf-8",
        )
    try:
        with open(p, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        return HttpResponse(f"<pre>读取失败: {e}</pre>", status=500, content_type="text/html; charset=utf-8")
    try:
        ta_cfg = build_ta_feedback_config(
            username,
            int(cid),
            get_url=request.build_absolute_uri("/api/card_ta_feedback"),
            save_url=request.build_absolute_uri("/api/card_ta_feedback"),
        )
        js_url = request.build_absolute_uri("/api/card_html_ta_feedback.js")
        html = inject_card_html_ta_feedback(html, ta_cfg, script_url=js_url)
    except Exception as inj_e:
        print(f"[card_feedback_html_view] TA feedback inject fail: {inj_e}")
        err_js = json.dumps(str(inj_e), ensure_ascii=False)
        html = (
            html
            + f"\n<!-- nkcn-ta-feedback-inject-failed: {inj_e} -->\n"
            + f"<script>console.error('[NKCN] TA 批注区注入失败:', {err_js});</script>\n"
        )
    resp = HttpResponse(html, content_type="text/html; charset=utf-8")
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@csrf_exempt
def card_ta_feedback(request):
    """TA/教师对小组作答可视化报告的批注（读写 TAfeedback/{cid}.json）。

    GET  ?username=&cid=
    POST JSON: username, cid, author, content
    """
    if request.method == "GET":
        username = (request.GET.get("username") or "").strip()
        cid_raw = request.GET.get("cid") or ""
    elif request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"error_num": 1, "msg": "JSON 解析失败"})
        username = (data.get("username") or "").strip()
        cid_raw = data.get("cid")
    else:
        return JsonResponse({"error_num": 1, "msg": "只支持 GET / POST"})

    if not username or cid_raw in ("", None):
        return JsonResponse({"error_num": 1, "msg": "缺少 username 或 cid"})
    try:
        cid = int(cid_raw)
    except (TypeError, ValueError):
        return JsonResponse({"error_num": 1, "msg": "cid 非法"})

    if request.method == "GET":
        row = read_ta_feedback(username, cid)
        return JsonResponse({"error_num": 0, "msg": "success", "data": row})

    author = (data.get("author") or "").strip()
    content = data.get("content")
    if content is None:
        return JsonResponse({"error_num": 1, "msg": "缺少 content"})
    try:
        row = write_ta_feedback(username, cid, author=author, content=str(content))
    except ValueError as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": f"写入失败: {e}"})
    return JsonResponse({"error_num": 0, "msg": "success", "data": row})


def card_html_ta_feedback_js(request):
    """TA 批注区脚本（card_feedback_html_view 注入）。"""
    if request.method != "GET":
        return HttpResponse("Method Not Allowed", status=405)
    try:
        body = load_ta_feedback_script()
        path = resolve_ta_feedback_js_path()
    except FileNotFoundError as e:
        return HttpResponse(
            f"/* NKCN ta feedback missing: {e} */\n",
            status=404,
            content_type="application/javascript; charset=utf-8",
        )
    resp = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "public, max-age=300"
    try:
        resp["Last-Modified"] = time.strftime(
            "%a, %d %b %Y %H:%M:%S GMT", time.gmtime(os.path.getmtime(path))
        )
    except Exception:
        pass
    return resp


def card_html_telemetry_diag(request):
    """排查遥测 js 是否在服务器可读（GET /api/card_html_telemetry_diag）。"""
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "只支持 GET"})
    info = telemetry_js_diag()
    try:
        info["script_bytes"] = len(load_telemetry_script())
    except Exception as e:
        info["script_bytes"] = 0
        info["load_error"] = str(e)
    return JsonResponse({"error_num": 0, "data": info})


def card_html_telemetry_js(request):
    """供 card_html_view 注入的遥测脚本（避免内联读文件失败时整页无遥测）。"""
    if request.method != "GET":
        return HttpResponse("Method Not Allowed", status=405)
    try:
        body = load_telemetry_script()
        path = resolve_telemetry_js_path()
    except FileNotFoundError as e:
        return HttpResponse(
            f"/* NKCN telemetry missing: {e} */\nconsole.error('[NKCN] card_html_telemetry.js not found on server');\n",
            status=404,
            content_type="application/javascript; charset=utf-8",
        )
    resp = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    resp["Cache-Control"] = "public, max-age=300"
    try:
        resp["Last-Modified"] = time.strftime(
            "%a, %d %b %Y %H:%M:%S GMT", time.gmtime(os.path.getmtime(path))
        )
    except Exception:
        pass
    return resp


@csrf_exempt
def card_html_feedback_submit(request):
    """助记 HTML 访问/作答事件上报（JSONL 追加）。"""
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "只支持 POST"})
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error_num": 1, "msg": "JSON 解析失败"})
    username = (data.get("username") or "").strip()
    cid_raw = data.get("cid")
    if not username or cid_raw is None:
        return JsonResponse({"error_num": 1, "msg": "缺少 username 或 cid"})
    try:
        cid = int(cid_raw)
    except (TypeError, ValueError):
        return JsonResponse({"error_num": 1, "msg": "cid 非法"})
    event = (data.get("event") or data.get("type") or "").strip()
    if not event:
        return JsonResponse({"error_num": 1, "msg": "缺少 event"})
    try:
        append_feedback_event(username, cid, data)
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": f"写入失败: {e}"})
    return JsonResponse({"error_num": 0, "msg": "success"})


def card_html_feedback_summary(request):
    """助教查看：本组谁访问/作答、各题尝试与选项（含历史 HTML）。"""
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "只支持 GET"})
    username = (request.GET.get("username") or "").strip()
    cid_raw = request.GET.get("cid") or ""
    if not username or cid_raw == "":
        return JsonResponse({"error_num": 1, "msg": "缺少 username 或 cid"})
    try:
        cid = int(cid_raw)
    except ValueError:
        return JsonResponse({"error_num": 1, "msg": "cid 非法"})
    try:
        summary = aggregate_feedback_summary(username, cid)
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    return JsonResponse({"error_num": 0, "msg": "success", "data": summary})


def _card_html_group_feedback_params(request) -> Dict[str, Any]:
    """GET / POST(JSON|form) 统一取参，供飞书 HTTP 节点调用。"""
    if request.method == "POST":
        ct = (request.META.get("CONTENT_TYPE") or "").lower()
        if "application/json" in ct:
            try:
                raw = request.body.decode("utf-8")
                data = json.loads(raw) if raw.strip() else {}
                if isinstance(data, dict):
                    params = data
                else:
                    params = request.POST
            except Exception:
                params = request.POST
        else:
            params = request.POST
    else:
        params = request.GET

    def _g(*keys: str) -> str:
        for k in keys:
            v = params.get(k)
            if v is not None and str(v).strip() != "":
                return str(v).strip()
        return ""

    return {
        "week_raw": _g("week", "Wxx", "w", "周次"),
        "subject_raw": _g("subject", "theme", "主题"),
        "group_raw": _g("group", "gid", "组号"),
        "notebook": _g("username", "notebook") or DEFAULT_TIZITU_NOTEBOOK,
        "cid_raw": _g("cid"),
        "format": _g("format").lower(),
        "detail": _g("detail").lower() or "full",
        "include_events": _g("include_events"),
        "include_legacy_summary": _g("include_legacy_summary"),
    }


@csrf_exempt
def card_html_group_feedback(request):
    """
    按周次 + 主题 + 组号汇总本子内 S5 梯子图 HTML 助记作答（JSONL）。

    支持 GET 与 POST（飞书「HTTP 请求」节点可用 JSON Body，与同项目 feishu_seed_gongsheng 一致）。

    参数（别名均可）：
      - week / Wxx：如 W11、11
      - subject / theme / 主题：如 纸联III、车联II、体联
      - group / gid / 组号：G07、7组、14
      - username / notebook：默认 testlyf_2026tizitu-group
      - cid：可选，直接指定卡片
      - format=text：额外返回 text 字段（飞书消息可直接展示）
      - detail=full（默认）| summary：full 含每题 event_timeline、attempt_groups（历次错选选项）
      - include_events=1：额外返回 data.events_raw（整份 jsonl 原样数组）
      - include_legacy_summary=1
    """
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error_num": 1, "msg": "只支持 GET / POST"})

    p = _card_html_group_feedback_params(request)
    week_int = parse_week_param(p["week_raw"])
    group_int = parse_group_param(p["group_raw"])
    if week_int is None:
        return JsonResponse({"error_num": 1, "msg": "缺少或无法解析 week（如 W11）"})
    if group_int is None:
        return JsonResponse({"error_num": 1, "msg": "缺少或无法解析 group（如 G07、7组）"})

    cid_override: Optional[int] = None
    if p["cid_raw"]:
        try:
            cid_override = int(p["cid_raw"])
        except ValueError:
            return JsonResponse({"error_num": 1, "msg": "cid 非法"})

    def _truthy(s: str) -> bool:
        return (s or "").lower() in ("1", "true", "yes")

    inc_events = _truthy(p["include_events"])
    try:
        detail_full = (p["detail"] or "full") != "summary"
        report = aggregate_group_card_html_feedback(
            p["notebook"],
            week_int=week_int,
            group_int=group_int,
            subject_raw=p["subject_raw"],
            cid=cid_override,
            include_events=inc_events,
            include_legacy_summary=_truthy(p["include_legacy_summary"]),
            detail_full=detail_full,
        )
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})

    api_data = format_group_feedback_api_response(
        report,
        include_events=inc_events,
        include_rounds=detail_full,
    )

    if not report.get("ok"):
        err_text = format_group_feedback_as_text(report)
        body: Dict[str, Any] = {
            "error_num": 1,
            "msg": report.get("error") or "未找到匹配卡片",
            "data": api_data,
        }
        if p["format"] in ("text", "feishu"):
            body["text"] = err_text
        return JsonResponse(body)

    resp: Dict[str, Any] = {"error_num": 0, "msg": "success", "data": api_data}
    if p["format"] in ("text", "feishu"):
        resp["text"] = format_group_feedback_as_text(report)
    return JsonResponse(resp)


@csrf_exempt
def card_get_html_generating_status(request):
    username = request.GET.get('username')
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'missing username'})
    with _card_html_lock:
        generating_cids = list(_card_html_generating.get(username, set()))
    return JsonResponse({'error_num': 0, 'generating_cids': generating_cids})


def generate_card_html_for_card(username: str, cid: int, extra: Optional[Dict[str, Any]] = None) -> str:
    data = dict(extra or {})
    ctx = _collect_card_html_context(username, int(cid), data, inject_chuchengjia_zhengben=True)
    card = ctx["card"]
    extra = dict(data)
    extra["card_content"] = card.content or ""
    extra["username"] = username

    # 解释精要卡：结构化信息量大，用模板填入，不调模型
    try:
        from app_chat.homework_grading.excerpt_card_render import (
            build_excerpt_html,
            build_excerpt_payload,
            is_excerpt_grading_card,
            strip_grading_card_marker,
        )
        title = card.contentTitle or ""
        content = card.content or ""
        if extra.get("grading_excerpt") or is_excerpt_grading_card(content, title):
            analysis_id = str(extra.get("analysis_id") or "").strip()
            run_id = extra.get("run_id")
            if not analysis_id:
                m = re.search(
                    r"<!--nkcn_grading_card:批改·解释精要\|([^|>]+)\|([^>]+)-->",
                    content,
                )
                if m:
                    analysis_id, run_id = m.group(1).strip(), m.group(2).strip()
            payload = None
            if analysis_id:
                from app_chat.homework_grading.service import prepare_homework_workspace
                from app_chat.homework_grading.result_cards import _load_json, _named_json, _sample_id
                paths = prepare_homework_workspace(
                    username, analysis_id,
                    None if run_id in (None, "", "current") else run_id,
                    create=False,
                )
                manifest = _load_json(paths.get("manifest") or "")
                fctx = manifest.get("feedback_context") or {}
                subject = str(manifest.get("subject") or fctx.get("subject_code") or "chinese")
                sample_id = _sample_id(analysis_id)
                report = _named_json(paths.get("pass2_report") or "", subject, sample_id, "_report.json")
                ontology = _load_json(os.path.join(paths.get("base") or "", "student_ontology.json"))
                assigned = None
                gc = manifest.get("grading_config") if isinstance(manifest.get("grading_config"), dict) else {}
                if gc.get("assigned_pages"):
                    try:
                        assigned = [int(p) for p in gc["assigned_pages"]]
                    except (TypeError, ValueError):
                        assigned = None
                filename = (manifest.get("selected_files") or [""])[0]
                if not isinstance(fctx, dict):
                    fctx = {}
                if not fctx and isinstance(ontology, dict):
                    fctx = ontology.get("feedback_context") or {}
                payload = build_excerpt_payload(
                    report, ontology,
                    pass1_dir=paths.get("pass1_json") or "",
                    subject=subject,
                    assigned_pages=assigned,
                    filename=filename,
                    material_type=str(fctx.get("material_type") or "homework"),
                    feedback_context=fctx,
                    analysis_id=analysis_id,
                    run_id=str(run_id or ""),
                )
                try:
                    from app_chat.homework_grading.verify_suggestions import suggestions_for_html
                    payload["verify_suggestions"] = suggestions_for_html(paths)
                except Exception:
                    payload["verify_suggestions"] = {}
            if payload is not None:
                html = build_excerpt_html(payload)
                backup = os.path.isfile(_card_html_path(username, int(cid)))
                return _save_card_html(username, int(cid), html, backup_before=backup)
    except Exception as exc:
        try:
            from app_chat.homework_grading.yangqian_debug import debug_log
            debug_log(f"[card_html] 解释精要模板失败，回退模型: {exc}")
        except Exception:
            pass

    sys_p, user_p = _system_and_user_prompts(
        ctx["notebook_description"],
        ctx["scene_name"],
        (card.contentTitle or "")[:500],
        card.content or "",
        ctx["doc_bundle"],
        ctx["cards_bundle"],
        bool(ctx["mime_b64"]),
        extra,
    )
    messages = _build_card_html_messages(sys_p, user_p, ctx["mime_b64"])
    html = _opus_stream_html_completion(messages, max_attempts=2)
    backup = os.path.isfile(_card_html_path(username, int(cid)))
    return _save_card_html(username, int(cid), html, backup_before=backup)


@csrf_exempt
def card_html_generate(request):
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "只支持 POST"})
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error_num": 1, "msg": "JSON 解析失败"})
    username = (data.get("username") or "").strip()
    cid = data.get("cid")
    if not username or cid is None:
        return JsonResponse({"error_num": 1, "msg": "缺少 username 或 cid"})
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return JsonResponse({"error_num": 1, "msg": "cid 非法"})

    try:
        out_path = generate_card_html_for_card(username, cid, extra=data)
    except Card.DoesNotExist:
        return JsonResponse({"error_num": 1, "msg": "卡片不存在"})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})

    return JsonResponse({
        "error_num": 0,
        "msg": "success",
        "path": str(out_path).replace("\\", "/"),
        "backed_up": True,
    })


@csrf_exempt
def card_html_iterate(request):
    """基于现有 cid.html 的 body 主体微调，覆盖前备份到 lastVersion。"""
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "只支持 POST"})
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error_num": 1, "msg": "JSON 解析失败"})
    username = (data.get("username") or "").strip()
    cid = data.get("cid")
    if not username or cid is None:
        return JsonResponse({"error_num": 1, "msg": "缺少 username 或 cid"})
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return JsonResponse({"error_num": 1, "msg": "cid 非法"})

    html_path = _card_html_path(username, cid)
    if not os.path.isfile(html_path):
        return JsonResponse({"error_num": 1, "msg": "暂无 HTML 文件，请先生成"})

    try:
        existing_html = _read_card_html_file(html_path)
        body_inner = _extract_body_inner(existing_html)
        if not body_inner:
            return JsonResponse({"error_num": 1, "msg": "无法解析现有 HTML 的 body 内容"})
        ctx = _collect_card_html_context(username, cid, data)
    except Card.DoesNotExist:
        return JsonResponse({"error_num": 1, "msg": "卡片不存在"})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})

    card = ctx["card"]
    sys_p, user_p = _system_and_user_prompts_iterate(
        ctx["notebook_description"],
        ctx["scene_name"],
        (card.contentTitle or "")[:500],
        card.content or "",
        ctx["doc_bundle"],
        ctx["cards_bundle"],
        bool(ctx["mime_b64"]),
        body_inner,
        extra=data,
    )
    messages = _build_card_html_messages(sys_p, user_p, ctx["mime_b64"])

    try:
        raw = _opus_stream_html_completion(messages, max_attempts=2)
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": f"模型调用失败: {e}"})

    new_body_inner = _normalize_iterate_body_output(raw)
    if not new_body_inner or len(new_body_inner) < 20:
        return JsonResponse({"error_num": 1, "msg": "模型未返回有效 body 内容"})

    try:
        merged_html = _replace_body_inner(existing_html, new_body_inner)
        out_path = _save_card_html(username, cid, merged_html, backup_before=True)
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": f"写入失败: {e}"})

    return JsonResponse({
        "error_num": 0,
        "msg": "success",
        "path": out_path.replace("\\", "/"),
        "backed_up": True,
    })


@csrf_exempt
def card_html_revert(request):
    """将 cid.html 回退为 lastVersion 中留存的上一版。"""
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "只支持 POST"})
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error_num": 1, "msg": "JSON 解析失败"})
    username = (data.get("username") or "").strip()
    cid = data.get("cid")
    if not username or cid is None:
        return JsonResponse({"error_num": 1, "msg": "缺少 username 或 cid"})
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return JsonResponse({"error_num": 1, "msg": "cid 非法"})

    last_path = _card_html_last_version_path(username, cid)
    if not os.path.isfile(last_path):
        return JsonResponse({"error_num": 1, "msg": "无可回退的上一版 HTML"})

    try:
        prev_html = _read_card_html_file(last_path)
        out_path = _card_html_path(username, cid)
        os.makedirs(_card_html_dir(username), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(prev_html)
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": f"回退失败: {e}"})

    return JsonResponse({"error_num": 0, "msg": "success", "path": out_path.replace("\\", "/")})
