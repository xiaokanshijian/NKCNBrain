# -*- coding: utf-8 -*-
"""
飞书工作流调用 NKCN 能力：深度课设精进种子（S4:共生方案）打点评审接口。

GET 请求（示例）：
  username=张三-组长&group=1&subject=纸联III&Q1=...&A1=...&Q2=...&A2=...
Header：
  link（可选）

核心逻辑：
1) 识别 subject 主题，映射到场景/本子；
2) 计算当周 Wn，读取该本子中 S4 子场景配置；
3) 在本子文档中筛选文件名含「代码/四主题/除乘加/种子」任一关键词的文档；
4) 对每份文档做均匀截取，并控制总长度 <= 8000 字；
5) 抓取当周 Wn 且标题含「放空」「定版」的最新卡片内容；
6) 拼装用户 prompt，调用 make_claude_text_requests_feishu_ta_chain 返回结构化文本。
"""
import json
import os
import re
import time
from collections import defaultdict
from datetime import date

from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from app_chat.models import Card

SEED_SCENE_BY_SUBJECT = {
    "纸联": {
        "scene_name": "NK2026精进种子",
        "book_name": "demoIIISeed",
    },
    "车联": {
        "scene_name": "NK2026精进种子",
        "book_name": "demoIIISeed",
    },
    "体联": {
        "scene_name": "NK2026精进种子",
        "book_name": "demoIIISeed",
    },
}
SEED_SUB_SCENE_NAME = "S4:共生方案"
SEED_DOC_KEYWORDS = ("代码", "四主题", "除乘加", "种子")
SEED_DOC_TOTAL_MAX_CHARS = 8000
SEED_GROUP_OTHER_DOC_MAX_CHARS = 5500
LOAD_USER_WAIT_TIMEOUT = 120
LOAD_USER_POLL_INTERVAL = 2
_EMBEDDED_W4_START = date(2026, 3, 23)

# 近两周 W9/W10 各组组型判别（助教侧记录；共生打点打分可作软参考，仍以逐题内容质量为最高准则）
# 尺度：橄榄-＜橄榄型＜橄榄+＜萝卜-＜萝卜型＜萝卜+＜苹果-＜苹果型＜苹果+（苹果+为最优）
GROUP_ARCHETYPE_W9W10 = {
    ("车联", 2): "萝卜型",
    ("车联", 3): "萝卜+",
    ("车联", 4): "苹果-",
    ("车联", 5): "苹果-",
    ("纸联", 7): "苹果型",
    ("纸联", 8): "萝卜+",
    ("纸联", 9): "萝卜+",
    ("纸联", 10): "苹果-",
    ("纸联", 11): "萝卜+",
    ("纸联", 12): "苹果-",
    ("纸联", 13): "萝卜型",
    ("纸联", 14): "萝卜+",
    ("体联", 15): "萝卜+",
    ("体联", 16): "萝卜型",
    ("体联", 17): "苹果-",
    ("体联", 18): "苹果-",
    ("体联", 19): "萝卜-",
    ("体联", 20): "萝卜+",
    ("体联", 21): "萝卜型",
    ("体联", 22): "苹果-",
}


def _safe_str(v):
    if v is None:
        return ""
    try:
        if isinstance(v, float) and v != v:
            return ""
    except Exception:
        pass
    return str(v)


def _embedded_course_week_number(today):
    """
    返回课设周次整数 Wn（n>=1）。W4 起为实验课设第一周；更早为 W1–W3 近似；远早于学期则 None。
    """
    if today < _EMBEDDED_W4_START:
        days_before = (_EMBEDDED_W4_START - today).days
        w = 4 - (days_before + 6) // 7
        if w < 1:
            return None
        return w
    days = (today - _EMBEDDED_W4_START).days
    return 4 + days // 7


def _parse_subject_theme(subject):
    s = _safe_str(subject).strip()
    for key in SEED_SCENE_BY_SUBJECT.keys():
        if key in s:
            return key
    return None


def _group_archetype_w9w10_block(subject, group):
    """返回注入 prompt 的组型参考段；无命中则说明未命中表。"""
    theme = _parse_subject_theme(subject)
    gid = _parse_group_int(group)
    lines = [
        "【近两周组型参考（助教判别）】",
        "尺度：橄榄-＜橄榄型＜橄榄+＜萝卜-＜萝卜型＜萝卜+＜苹果-＜苹果型＜苹果+（苹果+为最优）。",
    ]
    if theme and gid is not None:
        label = GROUP_ARCHETYPE_W9W10.get((theme, gid))
        if label:
            lines.append(f"本组判别：{theme}、G{gid:02d} 组为「{label}」。")
        else:
            lines.append(
                f"本组 subject/group 为 {subject or '?'}/G{gid:02d}，未在组型表中命中（请以逐题内容为准）。"
            )
    else:
        lines.append("未能从 subject/group 解析主题或组号，略过组型对照（请以逐题内容为准）。")
    lines.append(
        "红蓝打分时可作软参考：苹果系整体协同较好时，若逐题内容已扎实可略倾向不压低；"
        "萝卜/橄榄偏弱时，若逐题仍空泛则略保守；禁止无逐题依据仅凭组型抬压超过约半档。"
    )
    return "\n".join(lines)


def _subject_match_tokens(subject):
    """
    将 subject 归一化为一组可用于标题/文件名匹配的候选词。
    例如：纸联III -> [纸联III, 纸联3, 纸联]
    """
    s = _safe_str(subject).strip()
    if not s:
        return []

    tokens = [s]
    theme = _parse_subject_theme(s)
    if theme:
        tokens.append(theme)
        roman_map = {"纸联": "III", "车联": "II", "体联": "IV"}
        arabic_map = {"纸联": "3", "车联": "2", "体联": "4"}
        if theme in roman_map:
            tokens.append(f"{theme}{roman_map[theme]}")
            tokens.append(f"{theme}{arabic_map[theme]}")

    # 保序去重
    out = []
    seen = set()
    for tk in tokens:
        v = _safe_str(tk).strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _flatten_segments(obj):
    out = []
    if obj is None:
        return out
    if isinstance(obj, (list, tuple)):
        for it in obj:
            out.extend(_flatten_segments(it))
        return out
    if hasattr(obj, "page_content"):
        return [obj]
    return out


def _segment_source(seg):
    meta = getattr(seg, "metadata", None) or {}
    return meta.get("source") or ""


def _ensure_user_loaded(user_name):
    from llm_langchain import global_var, parse_input

    if (
        user_name in global_var.store_memory
        and global_var.store_memory[user_name].get("vector_store")
        and (global_var.store_memory[user_name].get("split_file") or [])
    ):
        return True
    parse_input.load_user(user_name)
    deadline = time.time() + LOAD_USER_WAIT_TIMEOUT
    while time.time() < deadline:
        if (
            user_name in global_var.store_memory
            and global_var.store_memory[user_name].get("vector_store")
            and (global_var.store_memory[user_name].get("split_file") or [])
        ):
            return True
        time.sleep(LOAD_USER_POLL_INTERVAL)
    raise RuntimeError("等待本子加载超时，请稍后重试")


def _set_scene_prompt_and_params(user_name, scene_name, sub_scene_name):
    from llm_langchain import parse_input
    from app_chat.utils import prompt_to_ghp, read_prompt_from_file

    scene_dir = os.path.join("./received_dir", "scene_excel", scene_name)
    if not os.path.isdir(scene_dir):
        raise FileNotFoundError(f"场景目录不存在: {scene_dir}")

    sub_names = [sub_scene_name, sub_scene_name.replace("：", ":"), sub_scene_name.replace(":", "：")]
    prompt_path = None
    for sub in sub_names:
        path = os.path.join(scene_dir, sub, "prompt.xlsx")
        if os.path.isfile(path):
            prompt_path = path
            break
    if not prompt_path:
        raise FileNotFoundError(f"未找到子场景 prompt.xlsx: {scene_dir} 下 {sub_names}")

    res = read_prompt_from_file(prompt_path)
    prompt_dict, params_dict = prompt_to_ghp(res)
    parse_input.set_user_prompt(user_name=user_name, prompt=prompt_dict)
    parse_input.set_user_params(user_name=user_name, params=params_dict)


def _extract_qa_pairs_from_get(get_obj):
    qs = {}
    ans = {}
    for k in get_obj.keys():
        key = _safe_str(k)
        m_q = re.match(r"^[Qq](\d+)$", key)
        if m_q:
            idx = int(m_q.group(1))
            qs[idx] = _safe_str(get_obj.get(k)).strip()
            continue
        m_a = re.match(r"^[Aa](\d+)$", key)
        if m_a:
            idx = int(m_a.group(1))
            ans[idx] = _safe_str(get_obj.get(k)).strip()

    pairs = []
    for idx in sorted(set(qs.keys()) | set(ans.keys())):
        q = qs.get(idx, "")
        a = ans.get(idx, "")
        if q or a:
            pairs.append((idx, q, a))
    return pairs


def _get_request_params(request):
    """
    统一提取请求参数：
    - GET: request.GET
    - POST(form): request.POST
    - POST(JSON): request.body 解析后的 dict
    """
    if request.method != "POST":
        return request.GET

    content_type = _safe_str(request.META.get("CONTENT_TYPE") or "").lower()
    if "application/json" in content_type:
        try:
            raw = _safe_str(request.body.decode("utf-8"))
            data = json.loads(raw) if raw.strip() else {}
            if isinstance(data, dict):
                return data
            print("[seed_gongsheng] invalid JSON body type, fallback to request.POST")
        except Exception as e:
            print(f"[seed_gongsheng] parse JSON body failed, fallback to request.POST | err={e}")
    return request.POST


def _is_seed_doc_name(filename):
    fn = _safe_str(filename)
    if not fn:
        return False
    return any(kw in fn for kw in SEED_DOC_KEYWORDS)


def _parse_group_int(group_str):
    s = _safe_str(group_str).strip()
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def _filename_has_group_tag(filename, group_int):
    if group_int is None:
        return False
    fn = _safe_str(filename)
    if not fn:
        return False
    pats = [
        # 兼容 G1 / G01 / G001
        rf"\b[Gg]\s*0*{group_int}\b",
        # 兼容 #1 / #01
        rf"#\s*0*{group_int}\b",
        # 兼容 1# / 01#
        rf"\b0*{group_int}\s*#\b",
        # 兼容 第1组 / 第01组 / 1组 / 01组
        rf"第\s*0*{group_int}\s*组",
        rf"\b0*{group_int}\s*组\b",
    ]
    return any(re.search(p, fn) for p in pats)


def _is_group_critical_doc_name(filename, group_int):
    fn = _safe_str(filename)
    if not fn:
        return False
    has_group = _filename_has_group_tag(fn, group_int)
    has_rule = ("除乘加" in fn) or ("三法则" in fn)
    return bool(has_group and has_rule)


def _is_group_other_doc_name(filename):
    fn = _safe_str(filename)
    if not fn:
        return False
    return ("除乘加" in fn) or ("四主题" in fn) or ("种子" in fn)


def _is_subject_group_analysis_doc_name(filename, subject):
    fn = _safe_str(filename)
    if not fn:
        return False
    tokens = _subject_match_tokens(subject)
    if not tokens:
        return False
    if not any(tk in fn for tk in tokens):
        return False
    # 主题总表：优先识别“各组除乘加三法则分析填写”，兼容关键语义词兜底
    return (
        ("各组除乘加三法则分析填写" in fn)
        or (("除乘加" in fn) and ("三法则" in fn) and ("分析" in fn) and ("填写" in fn))
    )


def _subject_analysis_doc_rank(filename):
    """
    主题总表候选文档排序键：
    1) txt 优先于 pdf（同主题同时存在时强制优先 txt）
    2) 同扩展名内按版本号 Vx.x 倒序
    """
    fn = _safe_str(filename).lower()
    is_txt = fn.endswith(".txt")
    version = _extract_version_tuple(filename)
    return (1 if is_txt else 0, version[0], version[1])


def _extract_version_tuple(filename):
    """
    从文件名中提取版本号 Vx.x，返回可比较元组 (major, minor)。
    未命中返回 (-1, -1)。
    """
    fn = _safe_str(filename)
    m = re.search(r"[Vv](\d+)(?:\.(\d+))?", fn)
    if not m:
        return (-1, -1)
    major = int(m.group(1))
    minor = int(m.group(2) or 0)
    return (major, minor)


def _extract_group_section_from_analysis_text(text, group_int):
    """
    从“各组除乘加三法则分析填写”总表文本中，仅抽取目标组段落。
    兼容段首变体：G10 / G 10 / 第10组 / 10组 / 下面为G10组...
    直到下一组段首或文本结束。
    """
    raw = _safe_str(text)
    if not raw.strip() or group_int is None:
        return ""
    # 第一优先级：精确锚句（与“组分隔标注版.txt”一致）
    target_literals = []
    for gtxt in (str(group_int), f"{group_int:02d}"):
        target_literals.append(f"下面为G{gtxt}组各组员填写的对主题内涵的除乘加三法则分析")
    # 保序去重
    target_literals = list(dict.fromkeys(target_literals))
    starts = [raw.find(s) for s in target_literals]
    starts = [p for p in starts if p >= 0]
    if starts:
        start = min(starts)
        next_anchor_pat = re.compile(r"下面为G0?\d+组各组员填写的对主题内涵的除乘加三法则分析")
        m_next = next_anchor_pat.search(raw, start + 1)
        end = m_next.start() if m_next else len(raw)
        candidate = raw[start:end].strip()
        # 在PDF重排文本里，下一组锚点可能被错误提前，导致只截到很短片段
        # 过短时继续走组号块聚合兜底。
        if len(candidate) >= 400:
            return candidate

    # 第一层：宽松组标记扫描（不依赖行首，兼容 G10 / G 10 / 第10组 / 10组）
    marker_pat = re.compile(
        r"(?i)(?:下面为\s*)?(?:G\s*0*(\d+)|第\s*0*(\d+)\s*组|(?<!\d)0*(\d+)\s*组)"
    )
    markers = []
    for m in marker_pat.finditer(raw):
        gi = next((g for g in m.groups() if g), None)
        if gi is None:
            continue
        try:
            gnum = int(gi)
        except Exception:
            continue
        markers.append((m.start(), m.end(), gnum))

    if not markers:
        # 第二层：精确短语兜底，兼容字符间空白/换行（PDF/OCR 常见）
        target_pat = re.compile(
            rf"下\s*面\s*为\s*G\s*0*{group_int}\s*组\s*各\s*组\s*员\s*填\s*写\s*的\s*对\s*主\s*题\s*内\s*涵\s*的\s*除\s*乘\s*加\s*三\s*法\s*则\s*分\s*析",
            re.I,
        )
        any_group_pat = re.compile(
            r"下\s*面\s*为\s*G\s*0*(\d+)\s*组\s*各\s*组\s*员\s*填\s*写\s*的\s*对\s*主\s*题\s*内\s*涵\s*的\s*除\s*乘\s*加\s*三\s*法\s*则\s*分\s*析",
            re.I,
        )
        m_target = target_pat.search(raw)
        if not m_target:
            return ""
        m_next = any_group_pat.search(raw, m_target.end())
        end = m_next.start() if m_next else len(raw)
        return raw[m_target.start() : end].strip()

    for i, (start_pos, _end_pos, gnum) in enumerate(markers):
        if gnum != group_int:
            continue
        end = markers[i + 1][0] if i + 1 < len(markers) else len(raw)
        candidate = raw[start_pos:end].strip()
        if len(candidate) >= 400:
            return candidate
        print(
            "[seed_gongsheng_group_rule] marker extraction too short, fallback by group-member blocks | "
            f"target=G{group_int:02d} candidate_len={len(candidate)}"
        )
        break
    # 诊断：识别到了组标记但没有目标组，便于线上排查
    preview_groups = [m[2] for m in markers[:8]]
    print(
        "[seed_gongsheng_group_rule] group section not found in markers | "
        f"target=G{group_int:02d} marker_groups={preview_groups}"
    )

    # 第三层：按“姓名块 + 组号: Gxx”聚合，适配PDF重排导致锚点错序/错位
    member_group_pat = re.compile(rf"组号\s*[:：]\s*G\s*0*{group_int}\b", re.I)
    person_blocks = re.split(r"(?=姓名\s*[:：])", raw)
    hit_blocks = [blk.strip() for blk in person_blocks if member_group_pat.search(blk)]
    if hit_blocks:
        # 尝试补一个本组锚句作为块头（若存在）
        anchor_head = ""
        for literal in target_literals:
            pos = raw.find(literal)
            if pos >= 0:
                # 回溯一点，尽量带上分隔线与“较好组标注”等行
                head_start = max(0, pos - 140)
                anchor_head = raw[head_start:pos + len(literal)].strip()
                break
        joined = "\n\n".join(hit_blocks)
        out = f"{anchor_head}\n\n{joined}".strip() if anchor_head else joined
        print(
            "[seed_gongsheng_group_rule] group section built by member blocks | "
            f"target=G{group_int:02d} hit_blocks={len(hit_blocks)} len={len(out)}"
        )
        return out
    return ""


def _uniform_extract_text(text, target_len):
    text = _safe_str(text)
    if target_len <= 0:
        return ""
    if len(text) <= target_len:
        return text

    marker = "\n...[均匀截取]...\n"
    piece_count = max(3, min(8, target_len // 320))
    if piece_count <= 1:
        return text[:target_len]

    sep_total = len(marker) * (piece_count - 1)
    body_budget = max(1, target_len - sep_total)
    piece_len = max(20, body_budget // piece_count)

    max_start = max(0, len(text) - piece_len)
    starts = []
    if piece_count == 1:
        starts = [0]
    else:
        for i in range(piece_count):
            pos = int(round(i * max_start / (piece_count - 1)))
            starts.append(pos)

    parts = [text[s : s + piece_len] for s in starts]
    out = marker.join(parts)
    if len(out) > target_len:
        out = out[: target_len - 1] + "…"
    return out


def _build_seed_reference_context(selected_docs):
    if not selected_docs:
        return "（未匹配到文件名含「代码/四主题/除乘加/种子」的文档）"
    blocks = []
    for d in selected_docs:
        blocks.append(f"《{d['filename']}》\n{d['sampled']}")
    return "\n\n---\n\n".join(blocks)


def _gather_s4_seed_reference_and_card(user_name, subject, group, username, link, w_curr):
    """
    与 feishu_seed_gongsheng 相同策略：筛选种子相关文档、均匀截取、拼装 reference_ctx，并取当周种子卡片。
    成功：return (reference_ctx, seed_card, None)
    失败：return (None, None, {"error_num": 1, "msg": "..."})
    """
    from llm_langchain import global_var, util as llm_util

    docs_name = list(global_var.store_memory[user_name].get("split_file") or [])
    if not docs_name:
        return None, None, {"error_num": 1, "msg": "本子内暂无文档，请先上传文档"}
    print(f"[seed_gongsheng] split_file count={len(docs_name)}")

    selected_doc_names = [d for d in docs_name if _is_seed_doc_name(os.path.basename(d))]
    print(
        "[seed_gongsheng] selected by filename keywords | "
        f"count={len(selected_doc_names)} keywords={SEED_DOC_KEYWORDS}"
    )
    if not selected_doc_names:
        return None, None, {
            "error_num": 1,
            "msg": "未找到文件名含「代码/四主题/除乘加/种子」的文档",
        }

    segs_raw = llm_util.get_docs_all_split(
        user_name,
        selected_doc_names,
        [1] * len(selected_doc_names),
        text_for_search=f"{subject}\n{group}\n{username}\n{link}".strip(),
    )
    segs = _flatten_segments(segs_raw)
    print(f"[seed_gongsheng] segments fetched | flat_count={len(segs)}")
    grouped = defaultdict(list)
    grouped_by_basename = defaultdict(list)
    for seg in segs:
        src = _segment_source(seg)
        txt = _safe_str(getattr(seg, "page_content", ""))
        grouped[src].append(txt)
        grouped_by_basename[os.path.basename(src)].append(txt)
    print(
        "[seed_gongsheng] segment grouping | "
        f"source_keys={len(grouped)} basename_keys={len(grouped_by_basename)}"
    )

    docs_payload = []
    for src in selected_doc_names:
        # 兼容 split_file 与 segment.source 的路径格式差异：
        # 1) 先按完整 source 匹配；2) 再按 basename 匹配。
        parts = grouped.get(src) or grouped_by_basename.get(os.path.basename(src)) or []
        raw = "\n\n".join(p for p in parts if p.strip())
        if not raw.strip():
            continue
        docs_payload.append(
            {
                "source": src,
                "filename": os.path.basename(src),
                "raw": raw,
                "raw_len": len(raw),
            }
        )

    # 兜底：若仍为空，说明 source 命名体系完全不一致，按文件名关键词在 basename 维度重建一次。
    if not docs_payload and grouped_by_basename:
        print("[seed_gongsheng] docs_payload empty after source/basename matching, fallback rebuild by basename")
        for fn, parts in grouped_by_basename.items():
            if not _is_seed_doc_name(fn):
                continue
            raw = "\n\n".join(p for p in parts if p.strip())
            if not raw.strip():
                continue
            docs_payload.append(
                {
                    "source": fn,
                    "filename": fn,
                    "raw": raw,
                    "raw_len": len(raw),
                }
            )
    if not docs_payload:
        return None, None, {"error_num": 1, "msg": "匹配文档无可用文本切片"}
    print(f"[seed_gongsheng] docs_payload built | count={len(docs_payload)}")

    n = len(docs_payload)
    base_share = max(240, SEED_DOC_TOTAL_MAX_CHARS // max(1, n))
    for d in docs_payload:
        d["budget"] = base_share
    print(
        "[seed_gongsheng] budget init | "
        f"doc_count={n} total_max={SEED_DOC_TOTAL_MAX_CHARS} base_share={base_share}"
    )

    used = sum(min(d["raw_len"], d["budget"]) for d in docs_payload)
    remain = max(0, SEED_DOC_TOTAL_MAX_CHARS - used)
    if remain > 0:
        expandable = [d for d in docs_payload if d["raw_len"] > d["budget"]]
        while remain > 0 and expandable:
            per = max(1, remain // len(expandable))
            changed = False
            for d in list(expandable):
                cap = d["raw_len"] - d["budget"]
                add = min(cap, per, remain)
                if add > 0:
                    d["budget"] += add
                    remain -= add
                    changed = True
                if d["budget"] >= d["raw_len"]:
                    expandable.remove(d)
                if remain <= 0:
                    break
            if not changed:
                break

    for d in docs_payload:
        d["sampled"] = _uniform_extract_text(d["raw"], d["budget"])
    total_raw = sum(d["raw_len"] for d in docs_payload)
    total_sampled = sum(len(d.get("sampled") or "") for d in docs_payload)
    print(
        "[seed_gongsheng] sampling done | "
        f"total_raw={total_raw} total_sampled={total_sampled}"
    )

    docs_payload.sort(key=lambda x: x["filename"])
    for i, d in enumerate(docs_payload, 1):
        print(
            f"[seed_gongsheng] doc#{i} file={d['filename']!r} "
            f"raw_len={d['raw_len']} budget={d['budget']} sampled_len={len(d['sampled'])}"
        )
    reference_ctx = _build_seed_reference_context(docs_payload)
    seed_card_content = _pick_latest_week_seed_card_content(user_name, w_curr, subject)
    print(
        "[seed_gongsheng] seed card / reference | "
        f"seed_card_len={len(seed_card_content)} reference_len={len(reference_ctx)}"
    )
    return reference_ctx, seed_card_content, None


def _build_group_rule_reference_context(critical_docs, other_docs):
    lines = [
        "【关键文档（全文）】文件名需同时满足：包含 Gxx（xx=group）且包含「除乘加」或「三法则」。",
    ]
    if critical_docs:
        for d in critical_docs:
            note = d.get("critical_note") or ""
            if note:
                lines.append(f"\n《{d['filename']}》\n【关键说明】{note}\n{d['sampled']}")
            else:
                lines.append(f"\n《{d['filename']}》\n{d['sampled']}")
    else:
        lines.append("（未命中关键文档）")

    lines.append("\n【其他文档（均匀截取，总长上限 5500）】文件名包含：除乘加 / 四主题 / 种子。")
    if other_docs:
        for d in other_docs:
            lines.append(f"\n《{d['filename']}》\n{d['sampled']}")
    else:
        lines.append("（未命中其他文档）")
    return "\n".join(lines)


def _build_group_rule_user_prompt(
    subject,
    group,
    username,
    w_curr,
    seed_card_content,
    qa_pairs,
):
    wk = f"W{w_curr}" if w_curr is not None else "W?"
    lines = [
        "【飞书问卷提交上下文】",
        f"- 主题 subject：{subject or '未提供'}",
        f"- 小组 group：{group or '未提供'}",
        f"- 提交者 username（含姓名与角色）：{username or '未提供'}",
        f"- 当周周次：{wk}",
        "",
        "【助教当周精进种子（Wn+放空+定版+主题，最新卡片）】",
        seed_card_content or "（未找到符合条件的当周卡片）",
        "",
        "【本组打点问题与回答】",
    ]
    for idx, q, a in qa_pairs:
        lines.append(f"Q{idx}: {q or '（空）'}")
        lines.append(f"A{idx}: {a or '（空）'}")

    lines.extend(
        [
            "",
            "【必须完整执行的任务要求】",
            "你必须严格依据给定材料，尤其特别注意关键文档【主题各组除乘加三法则分析填写汇总中抽取出的Gxx组填写部分】中体现的该组特色除乘加分析理解，给出自洽建议。",
            "这是小组根据教师/助教示范的除乘加分析自行讨论后修改形成的组特色分析结果（示范内容可能在《xx主题宏观微观三法则分析对齐》、《...四主题助教&教师教研激荡》、《...四主题愿景指向》等其他文档里）；评审时优先以该组结果为准，但若不自洽或偏离助教示范太多，要指出矫正。",
            "",
            "（1）15字以内复述提交者是哪个主题哪个小组的，代表小组提交各打点问题回答。",
            "",
            "（2）根据当周精进种子、该组整体及逐题回答，并特别结合关键文档，严格按该组特色除乘加理解，自洽输出三部分：",
            "① 判断对齐（<=100字）：",
            "  - A. 真实目标是否对齐该组除乘加分析，50字左右并给简单理由；",
            "  - B. 上中下线具体任务设定是否对齐该组除乘加分析，50字左右并给简单理由。",
            "  - A与B都必须同时指出优点与不足；严禁“符合组内除乘加分析”、“契合除法边界与协同分工”这类空泛说法，必须写清“符合/不符合/体现不充分具体哪里的什么”。",
            "  - 必须引用原话证据：至少各给1处“该组除乘加分析原话”+“该组打点回答原话（目标类/任务类/分工类）”，再据此判断。",
            "② 真实目标改进（<=120字，建议控制110字）：",
            "  - 必须紧贴该组除乘加分析；",
            "  - 分课程目标、组织目标两部分；",
            "  - 每部分都分三层且复合共振：行业宏观目标-主题学期目标-当前版本目标；",
            "  - 每层最多20字，总计不超过120字；",
            "  - 真实目标必须具体有用：记得住、说得出、内心渴望，禁止“深刻理解本元拆分”这类不具体、无判据、不能产生兴趣驱动的无效空话；",
            "  - 当前版本按周次确定（2026 当前学年）：W8-W10=V2.x前中期（除本元/乘放大法则设计实现）；W11=V2.x综合提升收尾周；"
            "W12-W13=V3.x（加法则，可靠可包容回滚）；W14-W15=V4.x（软硬件裁剪、功耗等可优化）。",
            "③ Issue链与Board工单建议（<=150字）：",
            "  - 必须具体写出“Gitlab Issue问题链建议”（链式递进问题，例如：1.如何...2.如何...3.如何...）；",
            "  - 必须分解出3-4个子任务，表述语境优先使用主题内涵语境，不要写成通用技术流水账；",
            "  - 子任务必须对应到当周精进种子中的具体下线代码模块或中/上线说明路径，并结合本组除乘加与真实目标灵活调整；",
            "  - 必须给出如何均衡分工给各成员。",
            "",
            "①②③总字数不超过370字（100+120+150），最多400字，禁止任何不错但没用的废话。",
            "",
            "【输出格式（必须严格一致，便于飞书解析）】",
            "【提交者复述】：<15字内>",
            "【A真实目标对齐判断】：<50字内，含理由>",
            "【B任务设定对齐判断】：<50字内，含理由>",
            "【课程目标三层】：<主题所属行业宏观目标>/<主题课设学期目标>/<当前版本目标>",
            "【组织目标三层】：<本组组织进化宏观目标>/<扩长化短学期目标>/<当前版本目标>",
            "【Issue问题链与Board建议】：",
            "1.如何...？",
            "2.如何...？",
            "3.如何...？",
            "...",
            "子任务拆分：",
            "- （可分工子任务1）...",
            "- （可分工子任务2）...",
            "- ...",
            "...",
            "（以上整段<=150字，含Issue链+3-4个主题内涵导向的涉及具体代码/注释的子任务+分工）",
            "【总字数自检】：<填写①②③实际总字数数字>",
        ]
    )
    return "\n".join(lines)


def _pick_latest_week_seed_card_content(user_name, w_curr, subject=None):
    """
    选取当周精进种子卡片：contentTitle 同时包含 Wn、放空、定版；
    若提供 subject（飞书请求主题字符串），则优先要求 contentTitle 也包含该 subject 子串，
    避免三主题共用同一场景/本子时取错卡片；若无命中则回退到不含 subject 的旧规则。
    """
    if w_curr is None:
        return ""
    wk = f"W{w_curr}"
    subj = (_safe_str(subject)).strip()
    subj_tokens = _subject_match_tokens(subj)

    base_q = (
        Q(username=user_name)
        & Q(contentTitle__contains=wk)
        & Q(contentTitle__contains="放空")
        & Q(contentTitle__contains="定版")
    )

    if subj_tokens:
        subject_q = Q()
        for tk in subj_tokens:
            subject_q |= Q(contentTitle__contains=tk)
        card = (
            Card.objects.filter(base_q & subject_q)
            .order_by("-datetime", "-cid")
            .first()
        )
        if card:
            print(
                "[seed_gongsheng] seed card picked | "
                f"mode=subject_strict subject={subj!r} subject_tokens={subj_tokens} wk={wk} cid={card.cid}"
            )
            return _safe_str(card.content)

        print(
            "[seed_gongsheng] seed card no match with subject, fallback | "
            f"subject={subj!r} subject_tokens={subj_tokens} wk={wk}"
        )

    card = Card.objects.filter(base_q).order_by("-datetime", "-cid").first()
    if card:
        print(
            "[seed_gongsheng] seed card picked | "
            f"mode=fallback_no_subject_filter wk={wk} cid={card.cid}"
        )
    return _safe_str(card.content) if card else ""


def _build_incremental_user_prompt(subject, group, username, w_curr, seed_card_content, qa_pairs):
    lines = [
        "【飞书问卷提交上下文】",
        f"- 主题 subject：{subject or '未提供'}",
        f"- 小组 group：{group or '未提供'}",
        f"- 提交者 username（含姓名与角色）：{username or '未提供'}",
        f"- 当周周次：W{w_curr}" if w_curr is not None else "- 当周周次：未能识别",
        "",
        _group_archetype_w9w10_block(subject, group),
        "",
        "【助教当周精进种子（Wn+放空+定版+主题，最新卡片）】",
        seed_card_content or "（未找到符合条件的当周卡片）",
        "",
        "【本组打点问题与回答】",
    ]
    if qa_pairs:
        for idx, q, a in qa_pairs:
            lines.append(f"Q{idx}: {q or '（空）'}")
            lines.append(f"A{idx}: {a or '（空）'}")
    else:
        lines.append("（未提供 Qn/An）")

    lines.extend(
        [
            "",
            "【输出格式要求（严格按此模板输出，便于飞书解析）】",
            "【提交者复述】：<15字内，复述是哪个主题哪个组的哪个角色，代表小组提交>",
            "【逐题点评】：",
            "- Q1：<50字内，给出“种子位置-具体问题-回答位置”依据链，指出优缺点>",
            "- Q2：<50字内，给出“种子位置-具体问题-回答位置”依据链，指出优缺点>",
            "- ...（按实际题量输出）",
            "【总点评字数约束】：逐题点评总字数不超过300字",
            "【红蓝卡标打分】：",
            "- Q1：【红蓝卡标打分】：x分",
            "- Q2：【红蓝卡标打分】：x分",
            "- ...（按实际题量输出）",
            "",
            "【打分规则】",
            "- 先确定基准分（红蓝融合五层，1~5分，0.2步长），以内容质量为准，下述为尽量遵守的判分倾向：",
            "  1分=内容完整、完成作答、无胡言乱语；2分=体现认知与行动融合；3分=有组内进一步讨论价值；",
            "  4分=对目标/任务/边界有清晰、可对照材料的理解（非“写得多”就行）；",
            "  5分=在4分基础上仍有明显洞见，或明确体现建堤坝（边界）与起洪流（微创新）层次（极少给）。",
            "- 4分及以上要克制：仅当对种子、问题与组内除乘加脉络理解非常到位、论证与材料强关联时才可给≥4；多数完成度尚可但理解一般的回答宜落在约2.4~3.6。",
            "- 字数≠高分：不得因篇幅长就抬分；短而准、切中要点可高于长而空、堆字。",
            "- 多题稍有些区分度：各题得分应反映该题实际优劣差异，避免多题最高分与最低分挤在同一档；尽量不要机械地全部挤在极窄分数带。",
            "- 可对照上文「前两周组型参考」与逐题依据一并考虑，仍以逐题文本为最高准则。",
            "- 再根据逐题点评对基准分做微调，保持可解释性与一致性。",
        ]
    )
    return "\n".join(lines)


def _build_seed_system_prompt(subject_theme, w_curr):
    wk = f"W{w_curr}" if w_curr is not None else "W?"
    return f"""你是 NKCN 深度课设阶段的精进种子助教评审助手。

当前主题：{subject_theme}；当前周次：{wk}。
你会收到：
1）按文件名规则筛出的共生方案参考文档；
2）当周精进种子（放空+定版）卡片；
3）学生小组提交的逐题回答。

要求：
- 仅围绕给定材料点评，禁止空泛夸赞与无依据否定；
- 每题点评必须尽量体现“此问题对应种子中的哪里-具体问题-回答中的哪里”的依据链；
- 对回答优缺点都要点明，语言简洁直接；
- 红蓝卡标打分时：≥4分（特别是4分以上）须谨慎，以理解是否真正到位为准，不以篇幅定高低；多题打分时在内容质量允许范围内保持题间区分度，避免整体分数差挤得过窄。
- 若用户消息含「前两周组型参考」，打分可与之软对齐（见用户消息中的约束），不得脱离逐题材料硬套组型。
- 输出必须严格遵守用户消息中给出的解析模板。"""


def _infer_subject_label_from_group_int(group_int):
    """由组号推断课设主题标注（与车联/纸联/体联组号段一致）。"""
    if group_int is None:
        return ""
    if 2 <= group_int <= 5:
        return "车联II"
    if 7 <= group_int <= 14:
        return "纸联III"
    if 15 <= group_int <= 22:
        return "体联IV"
    return ""


def _parse_request_week_int(week_raw, fallback_w):
    """解析请求中的 week：支持 11、W11 等；空则回退 fallback_w。"""
    s = _safe_str(week_raw).strip()
    if not s:
        return fallback_w
    m = re.match(r"^W\s*(\d+)$", s, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", s)
    if m:
        return int(m.group(1))
    return fallback_w


def _version_cadence_line_for_prompt():
    return (
        "深度课设版本节奏（2026 当前学年）：W8-W10=V2.x前中期；W11=V2.x综合提升收尾周；"
        "W12-W13=V3.x（加法则，可靠可包容回滚）；W14-W15=V4.x（软硬件裁剪、功耗等可优化）。"
    )


def _quantize_score_02(x):
    """0~5 分，步长 0.2。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    v = max(0.0, min(5.0, v))
    steps = int(round(v / 0.2))
    steps = max(0, min(25, steps))
    return round(steps * 0.2, 1)


def _parse_object_scores_from_answer(text):
    """从模型输出解析课程/组织目标评分。"""
    t = _safe_str(text)
    pat_c = re.compile(r"【\s*课程目标评分\s*】\s*[:：]\s*([0-5](?:\.\d)?)\s*分?", re.I)
    pat_o = re.compile(r"【\s*组织目标评分\s*】\s*[:：]\s*([0-5](?:\.\d)?)\s*分?", re.I)
    mc = pat_c.search(t)
    mo = pat_o.search(t)
    if not mc or not mo:
        return None, None
    qc = _quantize_score_02(mc.group(1))
    qo = _quantize_score_02(mo.group(1))
    if qc is None or qo is None:
        return None, None
    return qc, qo


def _build_object_score_user_prompt(
    group, group_int, subject_label, w_curr, red_o, blue_o, archetype_block, reference_ctx, seed_card
):
    wk = f"W{w_curr}" if w_curr is not None else "W?"
    sl = subject_label or "（未能由组号推断主题，请仍基于材料判断）"
    gline = (
        f"- 小组 group：{group or '未提供'}（解析组号 G{group_int:02d}）"
        if group_int is not None
        else f"- 小组 group：{group or '未提供'}"
    )
    lines = [
        "【飞书请求上下文】",
        gline,
        f"- 推断/标注主题：{sl}",
        f"- 本周周次（请求参数 week）：{wk}",
        _version_cadence_line_for_prompt(),
        "",
        archetype_block,
        "",
        "【本周修改的课程目标 redO（三层：行业宏观-主题学期-当前版本；每层最多20字，本段合计≤60字）】",
        red_o or "（空）",
        "",
        "【本周修改的组织目标 blueO（三层：组织宏观-扩长化短学期-当前版本；每层最多20字，本段合计≤60字）】",
        blue_o or "（空）",
        "",
        "【助教当周精进种子（放空+定版）】",
        seed_card or "（未找到符合条件的当周卡片）",
        "",
        "【S4参考资料（均匀截取）】",
        reference_ctx or "（无）",
        "",
        "【任务】",
        "请综合：组型参考、当周周次与版本节奏、精进种子与参考资料，分别评价 redO（课程目标）与 blueO（组织目标）是否相符合、是否具体可执行；",
        "课程目标与组织目标两段合计建议控制在120字以内（各段≤60字），若提交超长仍以内容质量为准，但过长且空泛须在点评中点明。",
        "判分以「是否符合、是否说到点子上」为主：不要为了显得严格而刻意挑刺扣分；明显空泛、与材料或周次版本明显冲突再从严。",
        "",
        "【输出格式（严格一致，便于解析）】",
        "【课程目标点评】：<40字内，一句说明主要依据>",
        "【组织目标点评】：<40字内，一句说明主要依据>",
        "【课程目标评分】：x.x分",
        "【组织目标评分】：x.x分",
        "其中 x.x 须为 0~5 之间、步长 0.2 的分值（如 3.4、4.0）；禁止用其它格式表示分数。",
    ]
    return "\n".join(lines)


def _build_object_score_system_prompt(subject_theme, w_curr):
    wk = f"W{w_curr}" if w_curr is not None else "W?"
    return f"""你是 NKCN 深度课设共生方案助教，负责给小组「修改后的课程目标（redO）」与「修改后的组织目标（blueO）」分别打分。

当前推断主题：{subject_theme}；请求周次：{wk}。

判分原则：
- 两段目标各独立给分，0~5 分、步长 0.2；内涵与共生打点红蓝卡标相近：1=完成且无胡言；2=认知与行动有连接；3=可讨论且部分落到主题与周次；4=与种子/版本节奏及组脉络较契合且表述较具体；5=高度契合且有清晰可检验的抓手（极少）。
- 以「是否符合当周与材料语境」为主：写得长但空洞不加分；短而贴切可给高分。不要为了扣分而扣分。
- 用户消息中的前两周组型仅作软参考，不得脱离目标文本硬套。
- 必须按用户消息末尾模板输出两行分数，便于程序解析。"""


@csrf_exempt
@require_http_methods(["GET", "POST"])
def feishu_object_score(request):
    """
    飞书：小组本周修改的课程目标（redO）与组织目标（blueO）分别评分。
    参数：group, week, redO, blueO（GET 或 POST；JSON body 亦支持）。
    返回：error_num, redO_score, blueO_score（0~5，步长 0.2）, answer（完整模型输出便于核对）。
    """
    try:
        req_t0 = time.time()
        req_params = _get_request_params(request)
        group = (_safe_str(req_params.get("group"))).strip()
        week_raw = req_params.get("week")
        red_o = _safe_str(req_params.get("redO"))
        blue_o = _safe_str(req_params.get("blueO"))
        group_int = _parse_group_int(group)
        today = timezone.localdate()
        w_fallback = _embedded_course_week_number(today)
        w_curr = _parse_request_week_int(week_raw, w_fallback)
        subject_label = _infer_subject_label_from_group_int(group_int)
        subject_for_card = subject_label or "纸联III"
        subject_theme = _parse_subject_theme(subject_for_card) or "纸联"

        print(
            "[feishu_object_score] request in | "
            f"group={group!r} group_int={group_int!r} week_raw={week_raw!r} w_curr={w_curr} "
            f"redO_len={len(red_o)} blueO_len={len(blue_o)}"
        )

        if not red_o.strip() and not blue_o.strip():
            return JsonResponse({"error_num": 1, "msg": "redO 与 blueO 不能同时为空"})
        if group_int is None:
            return JsonResponse({"error_num": 1, "msg": "参数 group 无法解析小组编号"})
        if not subject_label:
            return JsonResponse(
                {
                    "error_num": 1,
                    "msg": "group 不在车联(2-5)/纸联(7-14)/体联(15-22)已知组号段，无法绑定本子与组型",
                }
            )
        conf = SEED_SCENE_BY_SUBJECT.get(subject_theme) or {}
        user_name = f"testlyf_{conf.get('book_name', '')}".strip("_")
        scene_name = conf.get("scene_name") or ""
        if not user_name or not scene_name:
            return JsonResponse({"error_num": 1, "msg": f"主题 {subject_theme} 暂无场景/本子配置"})

        _ensure_user_loaded(user_name)
        _set_scene_prompt_and_params(user_name, scene_name, SEED_SUB_SCENE_NAME)
        print("[feishu_object_score] user/prompt ready")

        from llm_langchain import global_var
        from app_chat import claude_api

        global_var.store_memory[user_name]["model_num"] = 5
        reference_ctx, seed_card_content, err = _gather_s4_seed_reference_and_card(
            user_name,
            subject_for_card,
            group,
            "",
            "",
            w_curr,
        )
        if err:
            return JsonResponse(err)

        arch = _group_archetype_w9w10_block(subject_for_card, group)
        user_prompt = _build_object_score_user_prompt(
            group=group,
            group_int=group_int,
            subject_label=subject_label,
            w_curr=w_curr,
            red_o=red_o,
            blue_o=blue_o,
            archetype_block=arch,
            reference_ctx=reference_ctx,
            seed_card=seed_card_content,
        )
        system_prompt = _build_object_score_system_prompt(subject_theme, w_curr)
        print(
            f"[feishu_object_score] calling claude | "
            f"user_len={len(user_prompt)} sys_len={len(system_prompt)}"
        )
        call_t0 = time.time()
        answer = claude_api.make_claude_text_requests_feishu_ta_chain(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
        ) or ""
        print(
            f"[feishu_object_score] claude returned | len={len(answer)} "
            f"elapsed={time.time() - call_t0:.2f}s total={time.time() - req_t0:.2f}s"
        )
        if not answer:
            return JsonResponse({"error_num": 1, "msg": "Claude 未返回有效回答"})

        sc, so = _parse_object_scores_from_answer(answer)
        if sc is None or so is None:
            return JsonResponse(
                {
                    "error_num": 1,
                    "msg": "无法从模型输出解析【课程目标评分】【组织目标评分】，请检查模板",
                    "answer": answer,
                }
            )
        return JsonResponse(
            {
                "error_num": 0,
                "redO_score": sc,
                "blueO_score": so,
                "answer": answer,
            }
        )
    except FileNotFoundError as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    except RuntimeError as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JsonResponse({"error_num": 1, "msg": f"服务异常: {e}"})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def feishu_seed_gongsheng(request):
    try:
        req_t0 = time.time()
        req_params = _get_request_params(request)
        username = (_safe_str(req_params.get("username"))).strip()
        group = (_safe_str(req_params.get("group"))).strip()
        subject = (_safe_str(req_params.get("subject"))).strip()
        link = request.headers.get("link") or ""
        qa_pairs = _extract_qa_pairs_from_get(req_params)
        print(
            "[seed_gongsheng] request in | "
            f"method={request.method} "
            f"subject={subject!r} group={group!r} username={username!r} "
            f"qa_pairs={len(qa_pairs)} link={'Y' if link else 'N'}"
        )

        if not subject:
            return JsonResponse({"error_num": 1, "msg": "缺少参数 subject"})
        if not qa_pairs:
            return JsonResponse({"error_num": 1, "msg": "缺少打点问题参数（Qn/An）"})

        subject_theme = _parse_subject_theme(subject)
        if not subject_theme:
            return JsonResponse({"error_num": 1, "msg": "subject 未识别主题（需含 车联/纸联/体联）"})
        conf = SEED_SCENE_BY_SUBJECT.get(subject_theme) or {}
        user_name = f"testlyf_{conf.get('book_name', '')}".strip("_")
        scene_name = conf.get("scene_name") or ""
        print(
            "[seed_gongsheng] theme mapped | "
            f"subject_theme={subject_theme!r} scene={scene_name!r} user_name={user_name!r}"
        )

        if not user_name or not scene_name:
            return JsonResponse({"error_num": 1, "msg": f"主题 {subject_theme} 暂无场景/本子配置"})

        today = timezone.localdate()
        w_curr = _embedded_course_week_number(today)
        print(f"[seed_gongsheng] week computed | today={today.isoformat()} w_curr={w_curr}")

        _ensure_user_loaded(user_name)
        _set_scene_prompt_and_params(user_name, scene_name, SEED_SUB_SCENE_NAME)
        print("[seed_gongsheng] user/prompt ready")

        from llm_langchain import global_var
        from app_chat import claude_api

        global_var.store_memory[user_name]["model_num"] = 5

        reference_ctx, seed_card_content, err = _gather_s4_seed_reference_and_card(
            user_name, subject, group, username, link, w_curr
        )
        if err:
            return JsonResponse(err)

        qa_prompt = (
            (((global_var.store_memory.get(user_name) or {}).get("prompt") or {}).get("LUI2") or {}).get("qa")
            or ""
        )
        increment_user_prompt = _build_incremental_user_prompt(
            subject=subject,
            group=group,
            username=username,
            w_curr=w_curr,
            seed_card_content=seed_card_content,
            qa_pairs=qa_pairs,
        )
        final_user_prompt = (
            f"{qa_prompt}\n\n"
            f"【S4参考资料（均匀截取，总长<=8000）】\n{reference_ctx}\n\n"
            f"{increment_user_prompt}\n"
        )
        print(
            "[seed_gongsheng] prompt ready | "
            f"qa_prompt_len={len(qa_prompt)} final_user_prompt_len={len(final_user_prompt)}"
        )

        system_prompt = _build_seed_system_prompt(subject_theme, w_curr)
        call_t0 = time.time()
        print("[seed_gongsheng] calling claude chain ...")
        answer = claude_api.make_claude_text_requests_feishu_ta_chain(
            user_prompt=final_user_prompt,
            system_prompt=system_prompt,
        ) or ""
        print(
            "[seed_gongsheng] claude returned | "
            f"answer_len={len(answer)} model_call_elapsed={time.time() - call_t0:.2f}s "
            f"total_elapsed={time.time() - req_t0:.2f}s"
        )
        if not answer:
            return JsonResponse({"error_num": 1, "msg": "Claude 未返回有效回答"})
        return JsonResponse({"error_num": 0, "answer": answer})
    except FileNotFoundError as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    except RuntimeError as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JsonResponse({"error_num": 1, "msg": f"服务异常: {e}"})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def feishu_seed_gongsheng_group_rule(request):
    """
    第二接口：组特色除乘加规则版。
    文档策略：
    - 关键文档（全文）：文件名包含 Gxx 且包含「除乘加」或「三法则」；
    - 其他文档（均匀截取）：文件名包含「除乘加」或「四主题」或「种子」，总长 <= 5500。
    """
    try:
        req_t0 = time.time()
        req_params = _get_request_params(request)
        username = (_safe_str(req_params.get("username"))).strip()
        group = (_safe_str(req_params.get("group"))).strip()
        subject = (_safe_str(req_params.get("subject"))).strip()
        link = request.headers.get("link") or ""
        qa_pairs = _extract_qa_pairs_from_get(req_params)
        group_int = _parse_group_int(group)
        print(
            "[seed_gongsheng_group_rule] request in | "
            f"method={request.method} subject={subject!r} group={group!r} "
            f"group_int={group_int!r} username={username!r} qa_pairs={len(qa_pairs)}"
        )

        if not subject:
            return JsonResponse({"error_num": 1, "msg": "缺少参数 subject"})
        if group_int is None:
            return JsonResponse({"error_num": 1, "msg": "group 无法解析小组编号"})
        if not qa_pairs:
            return JsonResponse({"error_num": 1, "msg": "缺少打点问题参数（Qn/An）"})

        subject_theme = _parse_subject_theme(subject)
        if not subject_theme:
            return JsonResponse({"error_num": 1, "msg": "subject 未识别主题（需含 车联/纸联/体联）"})
        conf = SEED_SCENE_BY_SUBJECT.get(subject_theme) or {}
        user_name = f"testlyf_{conf.get('book_name', '')}".strip("_")
        scene_name = conf.get("scene_name") or ""
        print(
            "[seed_gongsheng_group_rule] theme mapped | "
            f"subject_theme={subject_theme!r} scene={scene_name!r} user_name={user_name!r}"
        )

        today = timezone.localdate()
        w_curr = _embedded_course_week_number(today)
        print(f"[seed_gongsheng_group_rule] week computed | today={today.isoformat()} w_curr={w_curr}")
        _ensure_user_loaded(user_name)
        _set_scene_prompt_and_params(user_name, scene_name, SEED_SUB_SCENE_NAME)
        print("[seed_gongsheng_group_rule] user/prompt ready")

        from llm_langchain import global_var, util as llm_util
        from app_chat import claude_api

        global_var.store_memory[user_name]["model_num"] = 5
        docs_name = list(global_var.store_memory[user_name].get("split_file") or [])
        if not docs_name:
            return JsonResponse({"error_num": 1, "msg": "本子内暂无文档，请先上传文档"})
        print(f"[seed_gongsheng_group_rule] split_file count={len(docs_name)}")

        critical_doc_names = []
        other_doc_names = []
        subject_analysis_doc_names = []
        for src in docs_name:
            fn = os.path.basename(src)
            if _is_group_critical_doc_name(fn, group_int):
                critical_doc_names.append(src)
            elif _is_subject_group_analysis_doc_name(fn, subject):
                subject_analysis_doc_names.append(src)
            elif _is_group_other_doc_name(fn):
                other_doc_names.append(src)

        fallback_subject_doc = None
        if not critical_doc_names and subject_analysis_doc_names:
            subject_analysis_doc_names.sort(
                key=lambda x: _subject_analysis_doc_rank(os.path.basename(x)),
                reverse=True,
            )
            fallback_subject_doc = subject_analysis_doc_names[0]
            critical_doc_names = [fallback_subject_doc]
            selected_fn = os.path.basename(fallback_subject_doc)
            print(
                "[seed_gongsheng_group_rule] no Gxx critical doc, fallback to latest subject analysis doc | "
                f"selected={selected_fn!r} ext={os.path.splitext(selected_fn)[1].lower()} "
                f"rank={_subject_analysis_doc_rank(selected_fn)}"
            )

        selected_doc_names = critical_doc_names + other_doc_names
        print(
            "[seed_gongsheng_group_rule] doc selected | "
            f"critical={len(critical_doc_names)} other={len(other_doc_names)} total={len(selected_doc_names)} "
            f"subject_analysis_candidates={len(subject_analysis_doc_names)}"
        )
        if subject_analysis_doc_names:
            cand_info = [
                (os.path.basename(x), _subject_analysis_doc_rank(os.path.basename(x)))
                for x in subject_analysis_doc_names
            ]
            print(f"[seed_gongsheng_group_rule] subject analysis candidates(sorted by txt-first): {cand_info}")
        if fallback_subject_doc:
            print(
                "[seed_gongsheng_group_rule] fallback mode enabled | "
                f"doc={os.path.basename(fallback_subject_doc)!r} group=G{group_int:02d}"
            )
        if not selected_doc_names:
            return JsonResponse({"error_num": 1, "msg": "未找到符合规则的文档"})

        # 关键文档（含fallback主题总表）强制走“全文读取能力”（segment_get_way=0），
        # 不走相似检索切片。
        critical_grouped = defaultdict(list)
        critical_grouped_by_basename = defaultdict(list)
        critical_full_segments = 0
        critical_segs_raw = []
        if critical_doc_names:
            try:
                critical_segs_raw = llm_util.get_docs_all_split(
                    user_name,
                    critical_doc_names,
                    [0] * len(critical_doc_names),
                    text_for_search=f"{subject}\n{group}\n{username}\n{link}".strip(),
                )
            except Exception as e:
                print(
                    "[seed_gongsheng_group_rule] critical full fetch failed | "
                    f"docs={len(critical_doc_names)} err={e}"
                )
                critical_segs_raw = []
        critical_segs = _flatten_segments(critical_segs_raw)
        critical_full_segments = len(critical_segs)
        for seg in critical_segs:
            seg_src = _segment_source(seg)
            txt = _safe_str(getattr(seg, "page_content", ""))
            critical_grouped[seg_src].append(txt)
            critical_grouped_by_basename[os.path.basename(seg_src)].append(txt)
        print(
            "[seed_gongsheng_group_rule] critical full fetch done | "
            f"docs={len(critical_doc_names)} segments={critical_full_segments}"
        )

        # 其他文档仍走现有切片逻辑（用于长度可控抽样）
        other_grouped = defaultdict(list)
        other_grouped_by_basename = defaultdict(list)
        other_flat_count = 0
        if other_doc_names:
            other_segs_raw = llm_util.get_docs_all_split(
                user_name,
                other_doc_names,
                [1] * len(other_doc_names),
                text_for_search=f"{subject}\n{group}\n{username}\n{link}".strip(),
            )
            other_segs = _flatten_segments(other_segs_raw)
            other_flat_count = len(other_segs)
            for seg in other_segs:
                seg_src = _segment_source(seg)
                txt = _safe_str(getattr(seg, "page_content", ""))
                other_grouped[seg_src].append(txt)
                other_grouped_by_basename[os.path.basename(seg_src)].append(txt)
        print(
            "[seed_gongsheng_group_rule] segments fetched | "
            f"critical_full={critical_full_segments} other_flat={other_flat_count}"
        )

        docs_payload = []
        for src in selected_doc_names:
            is_critical_src = src in critical_doc_names
            if is_critical_src:
                parts = critical_grouped.get(src) or critical_grouped_by_basename.get(os.path.basename(src)) or []
            else:
                parts = other_grouped.get(src) or other_grouped_by_basename.get(os.path.basename(src)) or []
            raw = "\n\n".join(p for p in parts if p.strip())
            if not raw.strip():
                print(
                    "[seed_gongsheng_group_rule] doc skipped(empty after fetch) | "
                    f"file={os.path.basename(src)!r} mode={'critical_full' if is_critical_src else 'other_slice'}"
                )
                continue
            is_fallback_src = bool(fallback_subject_doc and src == fallback_subject_doc)
            docs_payload.append(
                {
                    "source": src,
                    "filename": os.path.basename(src),
                    "raw": raw,
                    "raw_len": len(raw),
                    # fallback 主题总表应走关键文档链路，而不是 other 链路
                    "is_critical": is_critical_src or is_fallback_src,
                    "is_subject_analysis_fallback": is_fallback_src,
                }
            )

        if not docs_payload:
            return JsonResponse({"error_num": 1, "msg": "匹配文档无可用文本切片"})
        print(
            "[seed_gongsheng_group_rule] docs_payload built | "
            f"count={len(docs_payload)} critical_full={critical_full_segments} other_flat={other_flat_count}"
        )

        critical_docs = [d for d in docs_payload if d["is_critical"]]
        other_docs = [d for d in docs_payload if not d["is_critical"]]
        print(
            "[seed_gongsheng_group_rule] docs split | "
            f"critical={len(critical_docs)} other={len(other_docs)}"
        )

        for d in critical_docs:
            if d.get("is_subject_analysis_fallback"):
                section = _extract_group_section_from_analysis_text(d["raw"], group_int)
                d["sampled"] = section or d["raw"]
                d["critical_note"] = (
                    f"来源为主题总表，已抽取 G{group_int:02d} 组段落"
                    if section
                    else "来源为主题总表，未识别到组分隔段落，回退为整文"
                )
                print(
                    "[seed_gongsheng_group_rule] fallback section extraction | "
                    f"file={d['filename']!r} section_found={bool(section)} "
                    f"sampled_len={len(d['sampled'])} raw_len={d['raw_len']}"
                )
            else:
                d["sampled"] = d["raw"]  # 原规则关键文档：全文
                d["critical_note"] = "来源为Gxx且含除乘加/三法则文档，全文纳入"
                print(
                    "[seed_gongsheng_group_rule] direct critical fulltext | "
                    f"file={d['filename']!r} sampled_len={len(d['sampled'])}"
                )

        if other_docs:
            n = len(other_docs)
            base_share = max(180, SEED_GROUP_OTHER_DOC_MAX_CHARS // max(1, n))
            for d in other_docs:
                d["budget"] = base_share
            print(
                "[seed_gongsheng_group_rule] other docs budget init | "
                f"n={n} total_cap={SEED_GROUP_OTHER_DOC_MAX_CHARS} base_share={base_share}"
            )
            used = sum(min(d["raw_len"], d["budget"]) for d in other_docs)
            remain = max(0, SEED_GROUP_OTHER_DOC_MAX_CHARS - used)
            if remain > 0:
                expandable = [d for d in other_docs if d["raw_len"] > d["budget"]]
                while remain > 0 and expandable:
                    per = max(1, remain // len(expandable))
                    changed = False
                    for d in list(expandable):
                        cap = d["raw_len"] - d["budget"]
                        add = min(cap, per, remain)
                        if add > 0:
                            d["budget"] += add
                            remain -= add
                            changed = True
                        if d["budget"] >= d["raw_len"]:
                            expandable.remove(d)
                        if remain <= 0:
                            break
                    if not changed:
                        break
            for d in other_docs:
                d["sampled"] = _uniform_extract_text(d["raw"], d["budget"])
            print(
                "[seed_gongsheng_group_rule] other docs sampled | "
                f"total_sampled={sum(len(d['sampled']) for d in other_docs)} "
                f"total_raw={sum(d['raw_len'] for d in other_docs)}"
            )
        else:
            print("[seed_gongsheng_group_rule] no other docs matched")

        critical_docs.sort(key=lambda x: x["filename"])
        other_docs.sort(key=lambda x: x["filename"])
        reference_ctx = _build_group_rule_reference_context(critical_docs, other_docs)
        seed_card_content = _pick_latest_week_seed_card_content(user_name, w_curr, subject)
        print(
            "[seed_gongsheng_group_rule] seed card / reference | "
            f"seed_card_len={len(seed_card_content)} reference_len={len(reference_ctx)}"
        )

        qa_prompt = (
            (((global_var.store_memory.get(user_name) or {}).get("prompt") or {}).get("LUI2") or {}).get("qa")
            or ""
        )
        inc_prompt = _build_group_rule_user_prompt(
            subject=subject,
            group=group,
            username=username,
            w_curr=w_curr,
            seed_card_content=seed_card_content,
            qa_pairs=qa_pairs,
        )
        final_user_prompt = (
            f"{qa_prompt}\n\n"
            f"【S4参考资料（关键文档全文+其他文档均匀截取）】\n{reference_ctx}\n\n"
            f"{inc_prompt}\n"
        )
        system_prompt = _build_seed_system_prompt(subject_theme, w_curr)
        print(
            "[seed_gongsheng_group_rule] prompt ready | "
            f"critical={len(critical_docs)} other={len(other_docs)} "
            f"reference_len={len(reference_ctx)} final_user_prompt_len={len(final_user_prompt)}"
        )

        print("[seed_gongsheng_group_rule] calling claude chain ...")
        answer = claude_api.make_claude_text_requests_feishu_ta_chain(
            user_prompt=final_user_prompt,
            system_prompt=system_prompt,
        ) or ""
        print(
            "[seed_gongsheng_group_rule] claude returned | "
            f"answer_len={len(answer)} total_elapsed={time.time() - req_t0:.2f}s"
        )
        if not answer:
            return JsonResponse({"error_num": 1, "msg": "Claude 未返回有效回答"})
        return JsonResponse({"error_num": 0, "answer": answer})
    except FileNotFoundError as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    except RuntimeError as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JsonResponse({"error_num": 1, "msg": f"服务异常: {e}"})
