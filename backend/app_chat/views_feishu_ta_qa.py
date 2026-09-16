# -*- coding: utf-8 -*-
"""
飞书工作流调用 NKCN 能力：飞书TA答疑接口。
GET 请求，参数：username, group, subject, question, description(可选)；Header：link。
根据调用日期推算 2026 嵌入式课设周次（W4 起算，2026-03-23～03-29 为第一次实验周），
将情境、组号/周次/角色与文档文件名规则注入 prompt；强相关文档（组号 + 当周或上周周次）
优先引用（强相关=与发问人认知/衔接背景相关，非等同于「与当周任务知识点最相关」）；
整段用户 prompt 总长不超过 MAX_FEISHU_TA_PROMPT_CHARS。
若请求带有效 group，文件名中若出现其它小组编号（G4、4# 等）且不含本组号，则整份文档不进入参考资料。
等效于：在「飞书TA答疑」场景下打开本子 feishuAnswer（用户 testlyf），
在子场景「S1:问解通道答疑>>」下勾选本子内所有文档片段，用 Claude 无历史问答，返回结果。
"""
import os
import re
import time
from collections import defaultdict
from datetime import date, timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

# 固定：飞书TA答疑场景下的本子对应用户名（realName_bookName）
FEISHU_TA_USERNAME = "testlyf_demoFeis"
FEISHU_TA_SCENE_NAME = "飞书TA答疑"
FEISHU_TA_SUB_SCENE_NAME = "S1:问解通道答疑>>"
LOAD_USER_WAIT_TIMEOUT = 120
LOAD_USER_POLL_INTERVAL = 2

# 2026 嵌入式课设：W4 为第一次实验周（2026-03-23～03-29），此前按「课前」近似推算 W1–W3
_EMBEDDED_W4_START = date(2026, 3, 23)
# 发给模型的用户侧 prompt 总长度上限（字符数，含中文）
MAX_FEISHU_TA_PROMPT_CHARS = 30000
# 参考资料内部：总长受限时，为「其余参考资料」预留下限，避免强相关块独占、其他文档被严重挤压
FEISHU_REF_MIN_REST_CHARS = 4000
FEISHU_REF_MIN_REST_FRAC = 0.28

# 五人角色：文件名/username 子串匹配（优才/优裁 兼容）
_ROLE_KEYWORDS = ("组长", "需求员", "周志员", "优才员", "优裁员", "展示员")


def _flatten_segments(obj):
    """将 get_docs_all_split 可能返回的嵌套 list 展开为 Document 列表。"""
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


def _safe_str(v):
    if v is None:
        return ""
    # 兼容 pandas 的 NaN（float('nan')）
    try:
        if isinstance(v, float) and v != v:  # NaN
            return ""
    except Exception:
        pass
    return str(v)


def _parse_group_int(group_str):
    if not group_str or not str(group_str).strip():
        return None
    m = re.search(r"(\d+)", str(group_str))
    return int(m.group(1)) if m else None


def _parse_role_from_username(username):
    if not username:
        return None
    for r in _ROLE_KEYWORDS:
        if r in username:
            return r
    return None


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


def _week_date_span_display(w):
    if w is None or w < 4:
        return ""
    start = _EMBEDDED_W4_START
    d0 = start + timedelta(days=(w - 4) * 7)
    d1 = d0 + timedelta(days=6)
    return f"{d0.isoformat()}～{d1.isoformat()}"


def _week_task_line(w):
    if w is None:
        return "当前日期早于可识别的课设周次，请以教师安排为准。"
    if w < 4:
        return f"W{w}：第一次课设实验尚未开始（W4 起为 2026-03-23～03-29 初级 UI 群组点名周）。"
    if w == 4:
        return "W4（2026-03-23～03-29）：浅度课设—初级 UI 群组点名。"
    if w == 5:
        return "W5：浅度课设—中级 UI 群组点名。"
    if w == 6:
        return "W6：浅度课设—高级 UI 群组点名。"
    if w == 7:
        return "W7：浅度课设可能收尾周（部分浅度持续至 W7）；随后进入深度课设。"
    deep_tail = "车联用旧 A53 实验箱，纸联/体联用新树莓派+Arduino 盒。"
    if 8 <= w <= 10:
        return (
            f"W{w}：深度课设—V2.x 前、中期阶段（除本元/乘放大法则设计实现）；"
            f"W11 为 V2.x 综合提升收尾周；随后 W12-W13=V3.x，W14-W15=V4.x；{deep_tail}"
        )
    if w == 11:
        return (
            "W11：深度课设—V2.x 综合提升收尾周（除本元/乘放大法则整合提升与收束）；"
            f"随后 W12-W13=V3.x（加法则），W14-W15=V4.x；{deep_tail}"
        )
    if w in (12, 13):
        return (
            f"W{w}：深度课设—V3.x 阶段（加法则：可靠、可包容、回滚）；"
            f"W8-W10 为 V2.x，W11 为 V2.x 收尾；W14-W15=V4.x；{deep_tail}"
        )
    if w in (14, 15):
        return (
            f"W{w}：深度课设—V4.x 阶段（软硬件裁剪、功耗等可优化）；"
            f"此前 W12-W13=V3.x（加法则：可靠、可包容、回滚），W8-W11 为 V2.x（W11 为收尾周）；{deep_tail}"
        )
    return (
        f"W{w}：深度课设阶段，围绕所属主题（subject）开展设计与实现；"
        f"学年深度版本节奏：W8-W10=V2.x，W11=V2.x 收尾，W12-W13=V3.x，W14-W15=V4.x（超出以教师当周说明为准）；{deep_tail}"
    )


def _should_drop_source_for_alien_group(filename, group_int):
    """
    若请求中解析出本组号 group_int，且文件名里能解析出「小组编号」集合，
    且其中不包含本组号，则视为它组专用材料，整源丢弃（不进入参考资料）。
    文件名中完全未出现 Gn / n# 等组标记的文档保留（课程通用资料）。
    """
    if group_int is None:
        return False
    ids = _filename_group_ids(filename)
    if not ids:
        return False
    return group_int not in ids


def _filename_group_ids(filename):
    ids = set()
    if not filename:
        return ids
    for m in re.finditer(r"#(\d+)#", filename):
        ids.add(int(m.group(1)))
    for m in re.finditer(r"(\d+)#", filename):
        ids.add(int(m.group(1)))
    for m in re.finditer(r"#(\d+)", filename):
        ids.add(int(m.group(1)))
    for m in re.finditer(r"[Gg](\d+)", filename):
        ids.add(int(m.group(1)))
    return ids


def _filename_week_numbers(filename):
    if not filename:
        return set()
    return {int(m.group(1)) for m in re.finditer(r"[Ww](\d+)", filename)}


def _filename_has_role_keyword(filename):
    if not filename:
        return False
    return any(r in filename for r in _ROLE_KEYWORDS)


def _filename_matches_role(filename, role):
    return bool(role and role in filename)


def _filename_has_dadian(filename):
    """过程/打点类文档：文件名含「打点」。"""
    return bool(filename and "打点" in filename)


def _filename_stem(filename):
    """去掉扩展名后的文件名（basename 去掉 .pdf 等后缀），避免在后缀里误匹配英文标记。"""
    if not filename:
        return ""
    base = os.path.basename(filename)
    return os.path.splitext(base)[0]


def _filename_has_10min_ppt_mark(filename):
    """10 分钟课堂 PPT 类（多为 PPT 转 PDF）：仅在主文件名中匹配指定子串。"""
    stem = _filename_stem(filename)
    if not stem:
        return False
    markers = (
        "10minPPT",
        "10min PPT",
        "10min ppt",
        "10分钟PPT",
        "10分钟ppt",
    )
    return any(m in stem for m in markers)


def _filename_has_weekly_meeting_mark(filename):
    """周例会 / 教研会 / 周教研类材料（在去掉扩展名后的文件名中匹配）。"""
    stem = _filename_stem(filename)
    if not stem:
        return False
    return "周例会" in stem or "教研会" in stem or "周教研" in stem


def _filename_has_seed_mark(filename):
    """精进种子类材料（在去掉扩展名后的文件名中匹配）。"""
    stem = _filename_stem(filename)
    if not stem:
        return False
    return "精进种子" in stem


def _filename_matches_subject(filename, subject):
    fn = _safe_str(filename)
    sub = _safe_str(subject)
    if not fn or not sub:
        return False
    return sub in fn


def _segment_source(seg):
    meta = getattr(seg, "metadata", None) or {}
    return meta.get("source") or ""


def _classify_source_file(filename, group_int, w_curr, w_prev, role, subject):
    """
    返回 (critical, boost, flags_dict)。
    critical：
      ① 组号命中且周次为 W_curr 或 W_prev；
      ② 周次为 W_curr/W_prev 且（打点 / 10minPPT / 周例会或教研会或周教研）任一文件名特征命中；
      ③ 周次命中且同时命中 subject 与「精进种子」。
    （英文类标记在去掉扩展名后的文件名中匹配）
    boost：在「组 / 当周或上周周次 / 角色」三项中至少命中两项（且 critical 为假）。
    """
    gids = _filename_group_ids(filename)
    weeks = _filename_week_numbers(filename)
    role_hit = _filename_matches_role(filename, role)
    dadian_hit = _filename_has_dadian(filename)
    ppt10_hit = _filename_has_10min_ppt_mark(filename)
    meeting_hit = _filename_has_weekly_meeting_mark(filename)
    seed_hit = _filename_has_seed_mark(filename)
    subject_hit = _filename_matches_subject(filename, subject)

    g_hit = group_int is not None and group_int in gids
    w_hit = False
    if w_curr is not None and w_curr in weeks:
        w_hit = True
    if w_prev is not None and w_prev in weeks:
        w_hit = True

    critical_group_week = bool(group_int is not None and g_hit and w_hit)
    week_named_hit = dadian_hit or ppt10_hit or meeting_hit
    critical_week_named = bool(w_hit and week_named_hit)
    critical_seed_subject_week = bool(w_hit and subject_hit and seed_hit)
    critical = critical_group_week or critical_week_named or critical_seed_subject_week

    cond_g = g_hit
    cond_w = w_hit
    cond_r = bool(role and role_hit)
    score = int(cond_g) + int(cond_w) + int(cond_r)
    boost = (not critical) and score >= 2

    return critical, boost, {
        "g_hit": cond_g,
        "w_hit": cond_w,
        "role_hit": cond_r,
        "weeks": weeks,
        "gids": gids,
        "dadian_hit": dadian_hit,
        "ppt10_hit": ppt10_hit,
        "meeting_hit": meeting_hit,
        "seed_hit": seed_hit,
        "subject_hit": subject_hit,
        "critical_group_week": critical_group_week,
        "critical_week_named": critical_week_named,
        "critical_seed_subject_week": critical_seed_subject_week,
        "critical_dadian_week": bool(w_hit and dadian_hit),
    }


def _critical_reason_sentence(filename, group_int, w_curr, w_prev, flags):
    parts = []
    if group_int is not None and flags["g_hit"]:
        parts.append(f"文件名命中小组编号 {group_int}")
    if flags["w_hit"] and w_curr is not None:
        hit_ws = sorted(flags["weeks"] & ({w_curr, w_prev} - {None}))
        if hit_ws:
            parts.append(f"周次标记为 W{hit_ws[0]}，与本次调用当周或刚结束的上一周一致")
    if flags.get("dadian_hit"):
        parts.append("文件名含「打点」")
    if flags.get("ppt10_hit"):
        parts.append("文件名含 10 分钟课堂 PPT 类标记")
    if flags.get("meeting_hit"):
        parts.append("文件名含「周例会」或「教研会」或「周教研」")
    if flags.get("subject_hit"):
        parts.append("文件名命中请求主题 subject")
    if flags.get("seed_hit"):
        parts.append("文件名含「精进种子」")

    if flags.get("critical_group_week"):
        return (
            "该资料与当前发问小组及课设周次高度对齐，"
            + ("、".join(parts) if parts else "与请求参数一致")
            + "，应结合其内容判断小组进度与责任分工。"
        )

    if flags.get("critical_week_named"):
        tags = []
        if flags.get("dadian_hit"):
            tags.append("打点/过程记录")
        if flags.get("ppt10_hit"):
            tags.append("10 分钟 PPT 助教讲解")
        if flags.get("meeting_hit"):
            tags.append("周例会或教研会材料")
        tag_str = "、".join(tags) if tags else "课设过程类标记"
        return (
            f"该资料周次与本次发问当周或上周一致，且体现{tag_str}，"
            "与课堂要求或教学安排强相关，应优先结合其内容作答。"
        )

    if flags.get("critical_seed_subject_week"):
        return (
            "该资料周次与本次发问当周或上周一致，且文件名同时命中主题与「精进种子」，"
            "与当前阶段种子任务强相关，应优先结合其内容作答。"
        )

    return (
        "该资料与当前课设情境高度相关，"
        + ("、".join(parts) if parts else "与请求参数一致")
        + "，应优先结合其内容判断小组进度与责任分工。"
    )


def _boost_reason_line(filename, flags):
    bits = []
    if flags["g_hit"]:
        bits.append("组号")
    if flags["w_hit"]:
        bits.append("当周或上周周次")
    if flags["role_hit"]:
        bits.append("与 username 一致的角色")
    elif _filename_has_role_keyword(filename):
        bits.append("角色相关字样")
    return "、".join(bits) if bits else "多项文件名特征"


def _build_situation_block(
    today, w_curr, w_prev, username, group, subject, role, link
):
    w_prev_line = _week_task_line(w_prev) if w_prev is not None else "上周周次不详。"
    span_curr = _week_date_span_display(w_curr)
    span_prev = _week_date_span_display(w_prev) if w_prev is not None else ""
    w_curr_label = f"W{w_curr}" if w_curr is not None else "未定/课前"
    w_prev_label = f"W{w_prev}" if w_prev is not None else "无"
    lines = [
        "【课设情境与发问人上下文】（由发问时间推算周次，请在回答中综合参考）",
        f"- 调用日期：{today.isoformat()}",
        f"- 当前课设周次：{w_curr_label}" + (f"（约 {span_curr}）" if span_curr else ""),
        f"- 当周主要任务：{_week_task_line(w_curr)}",
        f"- 上一周 {w_prev_label}：" + (f"约 {span_prev}；" if span_prev else "") + w_prev_line,
        "- 浅度课设约 W4–W6（或至 W7）：W4 初级 / W5 中级 / W6 高级 UI 群组点名；深度阶段围绕 subject 四大主题推进。",
        "- 深度课设版本节奏（2026 当前学年）：W8-W10=V2.x前、中期；W11=V2.x 综合提升收尾周；W12-W13=V3.x；W14-W15=V4.x（更后周次以教师当周说明为准）。",
        "- 主题与平台提示：车联用旧 A53 实验箱；纸联、体联用新树莓派+Arduino 盒。",
        "- 小组五人角色（公份职能）：组长—方向与底线、氛围；需求员—需求汇总与组内讨论；周志员—问题采集分类与进度；优裁员—代码文档优化与软硬件裁剪；展示员—成果展示与 PPT/剧本整合。",
    ]
    if username:
        lines.append(f"- 首次发问人（username，可能含角色名）：{username}")
    if role:
        lines.append(f"- 从 username 推断角色：{role}（请结合其职责评估）")
    if group:
        lines.append(f"- 小组编号 group：{group}（请兼顾该组整体情况）")
    if subject:
        lines.append(f"- 课设主题 subject：{subject}")
    lines.append(
        "- 作答要求：【强相关必读】侧重发问人认知与衔接背景，非等同于「当周任务主知识点」；"
        "若其中有具体内容须结合其要点把握状态，技术要点仍以当周任务与课程资料为准。"
        "并综合 subject、小组整体、username 中角色职责与当周/上周任务评估发问人认知状态，进行精准回答。"
    )
    return "\n".join(lines)


def _ordered_sources_and_meta(segments, group_int, w_curr, w_prev, role, subject):
    """保持文档首次出现顺序，按 critical < boost < other 排序文档优先级。"""
    source_order = []
    seen = set()
    groups = defaultdict(list)
    dropped_seg_count = 0
    dropped_sources = set()
    for seg in segments or []:
        src = _segment_source(seg)
        fn = os.path.basename(src) if src else ""
        if _should_drop_source_for_alien_group(fn, group_int):
            dropped_seg_count += 1
            dropped_sources.add(src)
            continue
        groups[src].append(seg)
        if src not in seen:
            seen.add(src)
            source_order.append(src)
    if dropped_seg_count and group_int is not None:
        print(
            "[feishu_ta_qa] 已跳过它组专用材料: 独立来源数=",
            len(dropped_sources),
            "| 片段数=",
            dropped_seg_count,
            "| 本组 group_int=",
            group_int,
        )

    meta_by_src = {}
    for src in source_order:
        fn = os.path.basename(src) if src else ""
        crit, boost, fl = _classify_source_file(fn, group_int, w_curr, w_prev, role, subject)
        meta_by_src[src] = (crit, boost, fl, fn)

    def sort_key(src):
        crit, boost, _, _ = meta_by_src[src]
        if crit:
            tier = 0
        elif boost:
            tier = 1
        else:
            tier = 2
        idx = source_order.index(src)
        return (tier, idx)

    ordered = sorted(source_order, key=sort_key)
    return ordered, groups, meta_by_src


def _build_feishu_reference_catalogue(critical_docs, other_docs, w_curr, w_prev):
    """置于参考资料最前：文档名清单 + 禁止编造；便于模型对齐可引用范围。"""
    lines = [
        "【参考资料目录与使用约束】",
        "下列为本轮实际送入的文档文件名。回答中若提及资料，仅可使用下列名称；禁止编造未出现的文档名或虚构「资料原文」内容。",
    ]
    if w_curr is not None:
        wprev_s = f"上周为 W{w_prev}" if w_prev is not None else "上周周次见情境"
        lines.append(f"周次：当周主体为 W{w_curr}（{wprev_s}；上周内容仅作衔接背景）。")
    lines.append("")
    lines.append("【强相关文档】")
    lines.append(
        "说明：下列「强相关」指与发问人本人的认知状态、过程痕迹、周次衔接背景高度相关（如本组打点、"
        "本组与当周/上周周次同名的材料等），用于判断「谁在什么阶段、卡在哪里」；"
        "并不一定表示这些文档与「当周课设任务知识点」比其余文档更贴题（例如它们可能都是上周的），仅表示这些文档与发问人高度相关。"
        "当周任务与知识点仍以【课设情境】及【其余参考资料】中的课程/通用文档为主。"
    )
    if critical_docs:
        for d in critical_docs:
            lines.append(f"- {d.get('file') or '（未命名）'}")
    else:
        lines.append("- （本轮无）")
    lines.append("")
    lines.append("【其余参考资料】")
    if other_docs:
        for d in other_docs:
            tier = d.get("tier") or "other"
            label = "较高关联" if tier == "boost" else "通用/其他"
            lines.append(f"- [{label}] {d.get('file') or '（未命名）'}")
    else:
        lines.append("- （本轮无）")
    return "\n".join(lines)


def _fair_share_join_blocks(blocks, max_total_len, block_sep="\n\n---\n\n"):
    """
    在总长度上限内拼接多个文档块：先给每块保底前缀，再在预算内轮询加码，
    避免「只保留列表前几份、后面文档整份丢失」的尾部暴力截断。
    返回 (拼接串, 每块元数据列表)。
    """
    if not blocks:
        return "", []
    n = len(blocks)
    if max_total_len <= 0:
        return "…", [{"packed": 1, "trunc": True, "full": len(blocks[0])}]
    if n == 1:
        b0 = blocks[0]
        if len(b0) <= max_total_len:
            return b0, [{"packed": len(b0), "trunc": False, "full": len(b0)}]
        return b0[: max_total_len - 1] + "…", [
            {"packed": max_total_len, "trunc": True, "full": len(b0)}
        ]

    overhead = len(block_sep) * (n - 1)
    if overhead >= max_total_len:
        b0 = blocks[0]
        cut = max(1, max_total_len - 1)
        return b0[:cut] + "…", [{"packed": len(b0[:cut] + "…"), "trunc": True, "full": len(b0)}]

    budget = max_total_len - overhead
    lens = [len(b) for b in blocks]
    if sum(lens) <= budget:
        return block_sep.join(blocks), [
            {"packed": lens[i], "trunc": False, "full": lens[i]} for i in range(n)
        ]

    alloc = [0] * n
    rem = budget
    min_each = max(120, min(650, rem // max(2 * n, 1)))
    for i in range(n):
        take = min(lens[i], min_each, rem)
        alloc[i] = take
        rem -= take
    while rem > 0:
        progressed = False
        for i in range(n):
            if rem <= 0:
                break
            add = min(lens[i] - alloc[i], rem, 550)
            if add <= 0:
                continue
            alloc[i] += add
            rem -= add
            progressed = True
        if not progressed:
            break

    suffix = "…【本轮字数预算内未展开后文】"
    parts = []
    metas = []
    for i, b in enumerate(blocks):
        if alloc[i] >= lens[i]:
            parts.append(b)
            metas.append({"packed": lens[i], "trunc": False, "full": lens[i]})
        else:
            eff = max(0, alloc[i] - len(suffix))
            if eff < 40:
                piece = b[: max(1, min(lens[i], alloc[i]) - 1)] + "…"
            else:
                piece = b[:eff] + suffix
            parts.append(piece)
            metas.append({"packed": len(piece), "trunc": True, "full": lens[i]})

    out = block_sep.join(parts)
    if len(out) > max_total_len:
        out = out[: max_total_len - 1] + "…"
    return out, metas


def _pack_reference_context(ordered_sources, groups, meta_by_src, group_int, w_curr, w_prev, max_chars):
    """
    拼装参考资料：最前为【参考资料目录】（文档名清单+禁止编造）；
    其次强相关块；再其次其余文档。总长不超过 max_chars。
    超长时对其余多文档采用按文档公平分块截取（每份均有前缀），避免仅保留列表前几项。

    返回 (reference_ctx 字符串, debug 字典)。
    """
    critical_blocks = []
    other_blocks = []
    critical_docs = []
    other_docs = []

    def _src_tail(s, n=100):
        if not s:
            return ""
        s = str(s)
        return s if len(s) <= n else "…" + s[-n:]

    for src in ordered_sources:
        segs = groups.get(src) or []
        text = "\n\n".join(_safe_str(s.page_content) for s in segs if _safe_str(s.page_content))
        if not text.strip():
            continue
        crit, boost, flags, fn = meta_by_src[src]
        header = f"《{fn or os.path.basename(src) or '未命名文档'}》"
        if src:
            header += f"\n来源：{src}"

        base_info = {
            "file": fn,
            "source_tail": _src_tail(src, 120),
            "segment_count": len(segs),
            "body_chars": len(text),
        }

        if crit:
            reason = _critical_reason_sentence(fn, group_int, w_curr, w_prev, flags)
            block = f"{header}\n【为何本次必看】{reason}\n\n{text}"
            critical_blocks.append(block)
            critical_docs.append(
                {
                    **base_info,
                    "block_chars": len(block),
                    "critical_group_week": bool(flags.get("critical_group_week")),
                    "critical_week_named": bool(flags.get("critical_week_named")),
                    "flag_dadian": bool(flags.get("dadian_hit")),
                    "flag_ppt10": bool(flags.get("ppt10_hit")),
                    "flag_meeting": bool(flags.get("meeting_hit")),
                }
            )
        elif boost:
            why = _boost_reason_line(fn, flags)
            block = f"{header}\n【较高关联】文件名同时体现：{why}。\n\n{text}"
            other_blocks.append(block)
            other_docs.append({**base_info, "tier": "boost", "block_chars": len(block)})
        else:
            block = f"{header}\n\n{text}"
            other_blocks.append(block)
            other_docs.append({**base_info, "tier": "other", "block_chars": len(block)})

    mandatory = (
        "【强相关必读资料】（须优先考虑，可能是：① 文件名同时命中本次发问者所属组号 group 与当周周次 W"
        + (str(w_curr) if w_curr is not None else "?")
        + " 或上周周次 W"
        + (str(w_prev) if w_prev is not None else "?")
        + "；② 上述当周或上周的学生课前「打点」结果；③ 当周或上周的「10分钟ppt助教讲解」记录；"
        "④ 当周或上周的「周例教研会」记录）\n\n"
        + (
            "\n\n---\n\n".join(critical_blocks)
            if critical_blocks
            else "（本次无文件名命中上述强相关规则；仍请结合下列资料与情境作答。）"
        )
    )
    rest_header = "【其余参考资料】（也要综合考量）\n\n"
    if other_blocks:
        rest_body_full = "\n\n---\n\n".join(other_blocks)
    else:
        rest_body_full = "（无）"
    rest = rest_header + rest_body_full

    sep = "\n\n"
    inner_wo_cat = mandatory + sep + rest

    catalogue = _build_feishu_reference_catalogue(critical_docs, other_docs, w_curr, w_prev)
    cat_prefix = catalogue + "\n\n"
    inner_max = max_chars - len(cat_prefix)
    if inner_max < 400:
        cat_prefix = (catalogue[:800] + "…\n\n") if len(catalogue) > 800 else cat_prefix
        inner_max = max_chars - len(cat_prefix)

    full = cat_prefix + inner_wo_cat

    debug = {
        "ref_budget_max_chars": max_chars,
        "w_curr": w_curr,
        "w_prev": w_prev,
        "group_int": group_int,
        "critical_doc_count": len(critical_docs),
        "critical_docs": critical_docs,
        "other_doc_count": len(other_docs),
        "other_docs": other_docs,
        "catalogue_len": len(cat_prefix),
        "mandatory_len_raw": len(mandatory),
        "rest_len_raw": len(rest),
        "combined_len_raw": len(full),
        "truncated": False,
        "truncation_note": "",
        "out_len": 0,
        "other_fair_share": None,
    }

    def _finish_pack(mandatory_s, rest_s, **extra):
        out = cat_prefix + mandatory_s + sep + rest_s
        debug["out_len"] = len(out)
        debug.update(extra)
        return out, debug

    def _build_rest_for_budget(budget_for_rest_block):
        """budget_for_rest_block：整段「其余参考资料」标题+正文的上限。"""
        if not other_blocks:
            return rest_header + "（无）", [], False
        if budget_for_rest_block <= len(rest_header) + 10:
            return rest_header + "（预算不足）", [], True
        body_cap = budget_for_rest_block - len(rest_header)
        packed, metas = _fair_share_join_blocks(other_blocks, body_cap)
        return rest_header + packed, metas, True

    if len(full) <= max_chars:
        return _finish_pack(
            mandatory,
            rest,
            truncated=False,
            truncation_note="参考资料未超过 ref 预算，全文入 prompt",
            mandatory_len_final=len(mandatory),
            rest_len_final=len(rest),
        )

    has_other = bool(other_blocks)
    if has_other:
        min_rest_keep = min(
            len(rest),
            max(
                FEISHU_REF_MIN_REST_CHARS,
                int(inner_max * FEISHU_REF_MIN_REST_FRAC),
            ),
        )
        mandatory_cap = inner_max - len(sep) - min_rest_keep
        if mandatory_cap < 200:
            min_rest_keep = max(0, min(min_rest_keep, inner_max - len(sep) - 200))
            mandatory_cap = inner_max - len(sep) - min_rest_keep
        mandatory_truncated = False
        mandatory_s = mandatory
        if len(mandatory_s) > max(0, mandatory_cap):
            mc = max(0, mandatory_cap - 1)
            mandatory_s = (mandatory_s[:mc] + "…") if mc > 0 else "…"
            mandatory_truncated = True
        budget_rest = inner_max - len(mandatory_s) - len(sep)
        if budget_rest <= 0:
            rest_fallback = rest_header + "（无预算）"
            room_m = inner_max - len(sep) - len(rest_fallback)
            if room_m < 80:
                ms = "…"
            else:
                ms = mandatory[: max(0, room_m - 1)] + "…"
            return _finish_pack(
                ms,
                rest_fallback,
                truncated=True,
                truncation_note="内层预算耗尽，压缩强相关并暂不放其余正文",
                mandatory_truncated=True,
                rest_truncated=True,
                mandatory_len_final=len(ms),
                rest_len_final=len(rest_fallback),
            )
        if len(rest) <= budget_rest:
            note = "强相关曾截断后其余全文纳入" if mandatory_truncated else "内层未超预算，其余全文纳入"
            return _finish_pack(
                mandatory_s,
                rest,
                truncated=mandatory_truncated,
                truncation_note=note,
                mandatory_len_final=len(mandatory_s),
                rest_len_final=len(rest),
                mandatory_truncated=mandatory_truncated,
                rest_truncated=False,
            )
        rest_out, fair_meta, _ = _build_rest_for_budget(budget_rest)
        debug["other_fair_share"] = fair_meta
        return _finish_pack(
            mandatory_s,
            rest_out,
            truncated=True,
            truncation_note="强相关可能已截断 + 其余按文档公平分块截取（每份均有前缀）",
            mandatory_len_final=len(mandatory_s),
            rest_len_final=len(rest_out),
            mandatory_truncated=mandatory_truncated,
            rest_truncated=True,
        )

    if len(mandatory) >= inner_max:
        out_m = mandatory[: max(0, inner_max - 1)] + "…"
        return _finish_pack(
            out_m,
            rest_header + "（无）",
            truncated=True,
            truncation_note="无其余文档且强相关超内层预算",
            mandatory_len_final=len(out_m),
            rest_len_final=len(rest_header + "（无）"),
        )

    budget_rest = inner_max - len(mandatory) - len(sep)
    if budget_rest <= 0:
        return _finish_pack(
            mandatory[: max(0, inner_max - 1)] + "…",
            rest_header + "（无）",
            truncated=True,
            truncation_note="预算异常压缩",
            mandatory_len_final=min(len(mandatory), inner_max),
            rest_len_final=len(rest_header + "（无）"),
        )
    if len(rest) <= budget_rest:
        return _finish_pack(
            mandatory,
            rest,
            truncated=False,
            truncation_note="无多文档其余块或其余未超预算，未触发公平截取",
            mandatory_len_final=len(mandatory),
            rest_len_final=len(rest),
        )
    rest_out, fair_meta, _ = _build_rest_for_budget(budget_rest)
    debug["other_fair_share"] = fair_meta
    return _finish_pack(
        mandatory,
        rest_out,
        truncated=True,
        truncation_note="无 has_other 分支下对其余公平截取",
        mandatory_len_final=len(mandatory),
        rest_len_final=len(rest_out),
    )


def _print_feishu_ta_reference_pack_debug(debug):
    """服务端控制台诊断：强相关是否纳入、各文档片段体量。"""
    print("\n========== [feishu_ta_qa] 参考资料拼装 ==========")
    print(
        f"W_curr={debug.get('w_curr')!s} | W_prev={debug.get('w_prev')!s} | "
        f"group_int={debug.get('group_int')!r}"
    )
    print(
        f"本段参考资料预算 ref_budget_max_chars={debug.get('ref_budget_max_chars')} | "
        f"目录 catalogue_len={debug.get('catalogue_len')}"
    )
    print(
        f"强相关文档数: {debug.get('critical_doc_count')} | "
        f"其余(含较高关联+普通)文档数: {debug.get('other_doc_count')}"
    )
    print(
        f"拼装前: mandatory_len_raw={debug.get('mandatory_len_raw')} | "
        f"rest_len_raw={debug.get('rest_len_raw')} | "
        f"combined_len_raw={debug.get('combined_len_raw')}"
    )
    print(
        f"拼装后入 prompt 的参考资料总长 out_len={debug.get('out_len')} | "
        f"truncated={debug.get('truncated')} | {debug.get('truncation_note')}"
    )
    if "mandatory_len_final" in debug:
        print(
            f"分拆后约: mandatory_len_final={debug.get('mandatory_len_final')} | "
            f"rest_len_final={debug.get('rest_len_final')}"
        )

    for i, d in enumerate(debug.get("critical_docs") or [], 1):
        print(
            f"  [强相关 #{i}] {d.get('file')!r} | "
            f"片段数={d.get('segment_count')} | 正文body_chars={d.get('body_chars')} | "
            f"整块block_chars={d.get('block_chars')} | "
            f"group+周={d.get('critical_group_week')} week_named={d.get('critical_week_named')} | "
            f"打点={d.get('flag_dadian')} ppt10={d.get('flag_ppt10')} 例会教研={d.get('flag_meeting')}"
        )
        print(f"      source… {d.get('source_tail')}")

    boost_n = sum(1 for x in (debug.get("other_docs") or []) if x.get("tier") == "boost")
    other_n = sum(1 for x in (debug.get("other_docs") or []) if x.get("tier") == "other")
    print(f"其余文档: 较高关联 {boost_n} 个 | 普通 {other_n} 个（各文档 body/block 见下）")
    for i, d in enumerate(debug.get("other_docs") or [], 1):
        print(
            f"  [{d.get('tier')} #{i}] {d.get('file')!r} | "
            f"片段={d.get('segment_count')} | body_chars={d.get('body_chars')} | "
            f"block_chars={d.get('block_chars')}"
        )
    fair = debug.get("other_fair_share")
    if fair:
        print("  [公平截取] 其余各文档本轮纳入字数（trunc=True 表示未吃满全文）:")
        for i, pair in enumerate(zip(debug.get("other_docs") or [], fair), 1):
            d, m = pair
            print(
                f"    #{i} {d.get('file')!r} | packed={m.get('packed')} | "
                f"full={m.get('full')} | trunc={m.get('trunc')}"
            )
    print("========== [feishu_ta_qa] 参考资料拼装 结束 ==========\n")


def _print_feishu_ta_final_prompt_ref_stats(
    final_prompt, reference_ctx, qa_prompt, situation, question, limit
):
    """终稿里「参考资料」相对总 prompt 的长度（可能与 reference_ctx 不同若二次截断）。"""
    head = f"{_safe_str(qa_prompt)}\n\n{situation}\n\n【参考资料】\n"
    tail = f"\n\n【问题】\n{question}\n"
    room = limit - len(head) - len(tail)
    marker_q = "\n\n【问题】\n"
    idx_ref = final_prompt.find("【参考资料】\n")
    idx_q = final_prompt.find(marker_q)
    ref_body_len = None
    if idx_ref != -1 and idx_q != -1 and idx_q > idx_ref:
        ref_body = final_prompt[idx_ref + len("【参考资料】\n") : idx_q]
        ref_body_len = len(ref_body)
    print("[feishu_ta_qa] 终稿: final_prompt 总字数 =", len(final_prompt), "/", limit)
    print(
        "[feishu_ta_qa] 终稿: 参考资料区预算 room =",
        room,
        "| 拼装后 reference_ctx 长 =",
        len(reference_ctx),
        "| 是否大于 room:",
        len(reference_ctx) > room,
    )
    if ref_body_len is not None:
        print("[feishu_ta_qa] 终稿: 实际送入模型的「参考资料」正文约", ref_body_len, "字（不含标题行）")


def _assemble_feishu_prompt(qa_prompt, situation, reference_ctx, question, limit):
    head = f"{_safe_str(qa_prompt)}\n\n{situation}\n\n【参考资料】\n"
    tail = f"\n\n【问题】\n{question}\n"
    room = limit - len(head) - len(tail)
    if room < 200:
        ref = reference_ctx[: max(0, room - 1)] + ("…" if reference_ctx else "")
    elif len(reference_ctx) <= room:
        ref = reference_ctx
    else:
        ref = reference_ctx[: room - 1] + "…"
    out = head + ref + tail
    if len(out) > limit:
        return out[: limit - 1] + "…"
    return out


def _week_instruction_for_answer(w_curr, w_prev):
    """供 system prompt：当周 vs 上周，避免把上周实验当本周主体。"""
    if w_curr is None:
        return "周次未定时以情境块为准；区分「当周任务」与「上周回顾」。"
    if w_curr == 4:
        return "当周 W4：浅度课设—初级 UI 群组点名（LED、蜂鸣器等）；勿把后续周次任务提前当成本周。"
    if w_curr == 5:
        return (
            "当周 W5：浅度课设—中级 UI 群组点名为主：拨码开关作输入，点阵与数码管作主要输出，"
            "并兼容初级 UI 的 IO（如蜂鸣器、LED）；W4 初级流程仅作上周背景，勿把 W4 当作本周主任务复述。"
        )
    if w_curr == 6:
        return "当周 W6：浅度课设—高级 UI 群组点名（引入屏幕）；W4/W5 为已完成阶段，仅作衔接背景。"
    if w_curr == 7:
        return "当周 W7：浅度可能收尾；随后深度课设以 subject 为主，上周内容作背景。"
    if 8 <= w_curr <= 10:
        tail = f"W{w_prev} 为上周仅作背景。" if w_prev is not None else "以情境当周任务为准。"
        return (
            f"当周 W{w_curr}：深度课设 V2.x 阶段；W11 为 V2.x 综合提升收尾周；"
            f"随后 W12-W13=V3.x、W14-W15=V4.x；{tail}"
        )
    if w_curr == 11:
        tail = f"W{w_prev} 为上周仅作背景。" if w_prev is not None else "以情境当周任务为准。"
        return (
            "当周 W11：深度课设 V2.x 综合提升收尾周；随后 W12-W13=V3.x、W14-W15=V4.x；"
            f"{tail}"
        )
    if w_curr in (12, 13):
        tail = f"W{w_prev} 为上周仅作背景。" if w_prev is not None else "以情境当周任务为准。"
        return (
            f"当周 W{w_curr}：深度课设 V3.x 阶段；W8-W11 为 V2.x；W14-W15=V4.x；"
            f"{tail}"
        )
    if w_curr in (14, 15):
        tail = f"W{w_prev} 为上周仅作背景。" if w_prev is not None else "以情境当周任务为准。"
        return (
            f"当周 W{w_curr}：深度课设 V4.x 阶段；此前 W12-W13=V3.x，W8-W11 为 V2.x；"
            f"{tail}"
        )
    tail = f"W{w_prev} 为上周仅作背景。" if w_prev is not None else "以情境当周任务为准。"
    return (
        f"当周 W{w_curr}：深度课设阶段，以情境与 subject 为准；"
        f"学年深度版本节奏：W8-W10=V2.x、W11=V2.x 收尾、W12-W13=V3.x、W14-W15=V4.x；"
        f"{tail}"
    )


def _build_feishu_ta_claude_system_prompt(subject, group, username, role, w_curr, w_prev):
    """
    飞书实时答疑：固定开场白结构 + 极短主体；强调周次主次与本组资料表述。
    """
    subj = (subject or "").strip() or "未注明主题"
    grp = (group or "").strip() or "未注明组号"
    who = (username or "").strip() or "发问同学"
    if role:
        role_line = f"角色为「{role}」"
    else:
        role_line = (
            "角色：请根据 username 是否含组长、需求员、周志员、优才员/优裁员、展示员等写出；"
            "无法判断则写「同学（角色未标注）」"
        )
    wk = _week_instruction_for_answer(w_curr, w_prev)
    w_prev_s = str(w_prev) if w_prev is not None else "?"
    w_curr_s = str(w_curr) if w_curr is not None else "?"

    return f"""你是 NKCN 嵌入式课设在飞书侧的答疑助手，回答将直接展示给学生。

【资料与引用边界】
- 用户消息最前有【参考资料目录与使用约束】：仅可引用其中列出的文件名；禁止编造未列出文档或虚构原文。
- 【强相关必读资料】在此流程中的含义是「与发问人认知状态、周次衔接背景强相关」，**不一定是**「与当周课设任务知识点比其余文档更贴题」；答操作与知识点时须以当周任务与课程通用资料为主，强相关块主要用于先把握「谁、处于什么阶段、上周痕迹如何」。
- 若含该组上周打点、需求/代码等：这是**发问人本人小组的产出与过程记录**；不要说成「请去参考某外部 G 组文档」，应表述为「结合你们组上周文档及代码修改情况/打点可见…/其中你做了…/你（你们）仍有…卡点」等，你的回答中须包含这部分内容。
- 周次主次：{wk}

【绝对禁止】
- 禁止以「我是 Anthropic 的 Claude」「我是 AI 助手」等与题目无关的自我介绍或套话开头。
- 禁止在开场白三句之前输出任何其他句子。

【开场白：必须恰好三句，且为全文最前三句】
1）第一句：必须复述并定格发问者上下文，语义骨架为「你是{{课设主题}}{{组号}}组的{{谁}}（{{角色说明}}）」。
   以下为本请求已给出的要素，须自然写入第一句且不得与参数矛盾：
   - 课设主题：{subj}
   - 小组编号：{grp}
   - 发问人（username）：{who}
   - {role_line}
2）第二句：用你自己的理解概括学生的提问，不超过 20 个汉字（尽量少用标点，不计空格）。
3）第三句：必须以「本周 W{w_curr_s}」或「本周为 W{w_curr_s}」点明周次，再概括当周课设/课堂目标与任务（与情境一致）；全句宜短，为容纳周次信息总长可至约 28 个汉字；可顺带用极短词点出「上周 W{w_prev_s}」仅作背景，勿把上周当成本周主体。

三句写完后空一行，再写主体。

【主体部分（开场白之后）】
- 总长度严格控制在 100～200 个汉字之间（以汉字为主；英文、数字可按字符计入总长度）。
- 用 2～4 条列出（如「1.」「2.」或「-」），忌整段黏连，也忌条数过多。
- 须先**用 1～2 句极短话**根据【强相关】等资料概括发问人/小组**上周（W{w_prev_s}）**可见的基本情况或卡点（若资料不足则一句带过「资料未显式体现」），再针对**本周 W{w_curr_s}** 给可操作建议；建议中实验步骤、硬件与任务描述须与**当周**一致，勿大段复述上周流程当作本周任务。
- 内容比例：约 70%～80% 直接回答提问；约 10% 点出提问反映的认知状态并给近期发展区式一句引导；约 10% 教如何把问题问得更具体（熵减），可取 8:1:1 或 7:2:1。
- 难度须贴合主题、小组、角色、周次与参考资料，给「略努力可实现」的就近发展区帮助和建议，避免内耗。

【再次强调】除上述三句开场白外，主体仅一段且必须在 100～200 字内，因学生在飞书实时阅读，略长易放弃。"""


def _ensure_user_loaded(user_name):
    """确保 store_memory 中已加载该用户（本子）。若未加载则启动 load_user（异步）并轮询等待。"""
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


def _set_feishu_ta_prompt_and_params(user_name):
    """设置飞书TA答疑子场景的 prompt 与 params。"""
    from llm_langchain import parse_input
    from app_chat.utils import read_prompt_from_file, prompt_to_ghp

    scene_dir = os.path.join("./received_dir", "scene_excel", FEISHU_TA_SCENE_NAME)
    if not os.path.isdir(scene_dir):
        raise FileNotFoundError(f"场景目录不存在: {scene_dir}")

    sub_names = [
        FEISHU_TA_SUB_SCENE_NAME,
        "S1:问解通道答疑",
    ]
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


@csrf_exempt
@require_http_methods(["GET"])
def feishu_ta_qa(request):
    """
    飞书工作流 TA 答疑接口。
    GET 参数：username（首次发问人）, group（小组编号）, subject（课设主题）, question（问题描述）,
    description（可选，图片文字描述，不传图本身）。
    Header：link（记录链接，可选）。
    返回 JSON：{ "error_num": 0, "answer": "..." } 或 { "error_num": 1, "msg": "..." }。
    """
    try:
        username = (request.GET.get("username") or "").strip()
        group = (request.GET.get("group") or "").strip()
        subject = (request.GET.get("subject") or "").strip()
        question_param = (request.GET.get("question") or "").strip()
        description = (request.GET.get("description") or "").strip()
        link = request.headers.get("link") or ""

        if not question_param:
            return JsonResponse({"error_num": 1, "msg": "缺少参数 question"})

        today = timezone.localdate()
        w_curr = _embedded_course_week_number(today)
        w_prev = (w_curr - 1) if w_curr is not None else None
        group_int = _parse_group_int(group)
        role = _parse_role_from_username(username)

        user_name = FEISHU_TA_USERNAME
        _ensure_user_loaded(user_name)

        from llm_langchain import global_var, util as llm_util
        from app_chat import claude_api

        _set_feishu_ta_prompt_and_params(user_name)
        global_var.store_memory[user_name]["model_num"] = 5

        docs_name = list(global_var.store_memory[user_name].get("split_file") or [])
        if not docs_name:
            return JsonResponse({"error_num": 1, "msg": "本子内暂无文档，请先上传文档"})

        question_parts = [
            f"首次发问人：{username}" if username else "",
            f"小组编号：{group}" if group else "",
            f"课设主题：{subject}" if subject else "",
            f"图片描述（关键信息之一，需关注）：\n{description}" if description else "",
            f"问题描述：\n{question_param}",
        ]
        question = "\n".join(p for p in question_parts if p).strip()

        situation = _build_situation_block(
            today, w_curr, w_prev, username, group, subject, role, link
        )

        # 等效“勾选全部文档”：按文档取片段后，再按「组号/周次/角色」重排并控制总字数
        qa_prompt = (
            (((global_var.store_memory.get(user_name) or {}).get("prompt") or {}).get("LUI2") or {}).get("qa")
            or ""
        )
        search_query = f"{question_param}\n{description}".strip() if description else question
        segments_raw = llm_util.get_docs_all_split(
            user_name,
            docs_name,
            [1] * len(docs_name),
            text_for_search=search_query,
        )
        segments = _flatten_segments(segments_raw)
        ordered_sources, groups, meta_by_src = _ordered_sources_and_meta(
            segments, group_int, w_curr, w_prev, role, subject
        )
        print(
            "[feishu_ta_qa] 输入统计: 扁平片段数=",
            len(segments),
            "| 有内容的独立来源数=",
            len(ordered_sources),
        )
        head_for_budget = (
            f"{_safe_str(qa_prompt)}\n\n{situation}\n\n【参考资料】\n"
        )
        tail_for_budget = f"\n\n【问题】\n{question}\n"
        ref_budget = MAX_FEISHU_TA_PROMPT_CHARS - len(head_for_budget) - len(tail_for_budget)
        if ref_budget < 800:
            ref_budget = 800
        reference_ctx, ref_pack_debug = _pack_reference_context(
            ordered_sources,
            groups,
            meta_by_src,
            group_int,
            w_curr,
            w_prev,
            max(800, ref_budget),
        )
        _print_feishu_ta_reference_pack_debug(ref_pack_debug)
        final_prompt = _assemble_feishu_prompt(
            qa_prompt,
            situation,
            reference_ctx,
            question,
            MAX_FEISHU_TA_PROMPT_CHARS,
        )
        _print_feishu_ta_final_prompt_ref_stats(
            final_prompt,
            reference_ctx,
            qa_prompt,
            situation,
            question,
            MAX_FEISHU_TA_PROMPT_CHARS,
        )

        system_prompt = _build_feishu_ta_claude_system_prompt(
            subject, group, username, role, w_curr, w_prev
        )
        answer = claude_api.make_claude_text_requests_feishu_ta_chain(
            user_prompt=final_prompt,
            system_prompt=system_prompt,
        ) or ""
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
