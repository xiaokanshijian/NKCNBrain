# -*- coding: utf-8 -*-
"""
NK2026「梯子图·群组公能教学指向批改」场景：自动化文件列表与检索方式专用逻辑。
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

NK2026_SCENE_NAME = "NK2026梯子图·群组公能教学指向批改"

NK2026_CHUCHENGJIA_TWIN_FILENAME = "纸联体联除乘加正本清源完整摘录.md"
NK2026_CHUCHENGJIA_WEEK_MIN = 13

_WEEK_NUM_RE = re.compile(r"W(\d+)", re.I)
_WEEK_IN_TEXT_RE = re.compile(r"W\s*0*(\d+)(?!\d)", re.I)

# （4）四类：固定「获取全文」——与前端 FileCard 一致 left=0 right=0
_FULLTEXT_MARKERS = (
    "课设实验课后TA助教小结",
    "梯子图填写",
    "精进种子三线放空设计定版",
    "激励小组谈话实录",
)

# 场景预置 C 类（存在则参与前端自动勾选，默认相关搜索）
SCENE_BASE_DOC_NAMES = (
    "A0监控表.pdf",
    "课程设计中课设实验精进（相关文件的）必要补充说明.pdf",
    "NK2026嵌入式课程目标分解与实施框架(助教专用)-20260309.pdf",
    "真实目标.pdf",
    "嵌入式系统课设各主题助教&教师教研激荡.pdf",
)

_THEME_WORDS = ("车联", "纸联", "体联")


def is_nk2026_ladder_scene(scene_name: Optional[str]) -> bool:
    if not scene_name:
        return False
    return NK2026_SCENE_NAME in scene_name or scene_name.strip() == NK2026_SCENE_NAME


def text_references_course_week_at_least(
    text: str, min_week: int = NK2026_CHUCHENGJIA_WEEK_MIN
) -> bool:
    """文本中若出现 Wn 且 n >= min_week 则返回 True（用于 W13+ 正本清源注入判定）。"""
    if not text:
        return False
    for m in _WEEK_IN_TEXT_RE.finditer(text):
        if int(m.group(1)) >= int(min_week):
            return True
    return False


def chuchengjia_twin_md_path(username: str) -> str:
    base = os.path.normpath("./received_dir/user_raw_file/" + username.replace("\\", "/"))
    return os.path.join(base, "_twin", NK2026_CHUCHENGJIA_TWIN_FILENAME)


def read_nk2026_chuchengjia_twin_markdown(username: str) -> str:
    """读取本子 _twin 下「纸联体联除乘加正本清源完整摘录.md」全文。"""
    path = chuchengjia_twin_md_path(username)
    if not os.path.isfile(path):
        print(f"[NK2026 正本清源] 文件不存在 path={path!r}")
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            body = f.read().strip()
        if body:
            print(f"[NK2026 正本清源] 已读取全文 {len(body)} 字 path={path!r}")
        return body
    except Exception as e:
        print(f"[NK2026 正本清源] 读取失败 path={path!r}: {e}")
        return ""


def theme_keyword_in_text(text: str) -> Optional[str]:
    if not text:
        return None
    for w in _THEME_WORDS:
        if w in text:
            return w
    return None


def parse_target_ladder_meta(target_file: str) -> Optional[dict]:
    """
    从 target_file 解析周次 Wn、主题关键字（车联/纸联/体联）、组号数字。
    例：W9车联2组梯子图填写（上半部分）
    """
    if not target_file:
        return None
    wm = re.search(r"W(\d+)", target_file, re.I)
    if not wm:
        return None
    week = int(wm.group(1))
    tk = theme_keyword_in_text(target_file)
    if not tk:
        return None
    gid = None
    m = re.search(r"(?:车联|纸联|体联)[IVⅠⅡⅢ二三四五六七八九十]*\s*(\d+)\s*组", target_file)
    if m:
        gid = int(m.group(1))
    if gid is None:
        m = re.search(r"G(\d+)", target_file, re.I)
        if m:
            gid = int(m.group(1))
    if gid is None:
        m = re.search(r"(\d+)\s*组", target_file)
        if m:
            gid = int(m.group(1))
    if gid is None:
        return None
    return {"week": week, "theme_kw": tk, "group_id": gid, "target_file": target_file}


def parse_group_int_from_target_for_replace(target_file: str) -> Optional[int]:
    meta = parse_target_ladder_meta(target_file)
    return meta["group_id"] if meta else None


def group_display_from_target(target_file: str, group_int: int) -> str:
    """替换 filenames 时 Gxx / xx组 的数字格式尽量跟随 target_file 里同一组的写法。"""
    m = re.search(r"G(\d+)", target_file)
    if m:
        width = len(m.group(1))
        return str(group_int).zfill(width) if width > 1 else str(group_int)
    m = re.search(r"(?:车联|纸联|体联)[^\\d]{0,6}(\d+)\s*组", target_file)
    if m:
        width = len(m.group(1))
        return str(group_int).zfill(width) if width > 1 else str(group_int)
    m = re.search(r"(\d+)\s*组", target_file)
    if m:
        width = len(m.group(1))
        return str(group_int).zfill(width) if width > 1 else str(group_int)
    return str(group_int)


def _replace_g_marker(filename: str, gdisp: str) -> str:
    return re.sub(r"G\d+", "G" + gdisp, filename, flags=re.I)


def _replace_theme_group_suffix(filename: str, theme_kw: str, gdisp: str) -> str:
    pat = rf"({re.escape(theme_kw)})(?:[IVⅠⅡⅢ二三四五六七八九十]*)?\s*(\d+)\s*组"

    def _sub(m):
        return m.group(1) + gdisp + "组"

    return re.sub(pat, _sub, filename)


def _replace_plain_digit_group(filename: str, gdisp: str) -> str:
    """剩余 xx组（避免误伤 W10 中的周次）：不以字母 W/w 紧邻的数字组。"""
    return re.sub(r"(?<![Ww])(\d{1,3})\s*组", gdisp + "组", filename)


def _replace_hash_group(filename: str, gdisp: str) -> str:
    return re.sub(r"(\d+)\s*#", gdisp + "#", filename)


def nk2026_replace_names_in_question(text: str, target_file: str) -> str:
    """
    NK2026 自动化重放：仅按当前 target_file 中的组号，替换提问文案里的 Gxx / xx# / xx组 等。
    周次 Wn、主题（车联/纸联/体联）由用户在新周次录制时自行改好，此处不参与替换。
    """
    meta = parse_target_ladder_meta(target_file)
    if not meta:
        return text
    tk = meta.get("theme_kw") or theme_keyword_in_text(target_file)
    disp = group_display_from_target(target_file, meta["group_id"])
    out = nk2026_replace_group_markers_in_filename(text, target_file, tk)
    print(f"[NK2026 _replace_names] 仅组号替换 disp={disp!r}")
    return out


def nk2026_replace_group_markers_in_filename(filename: str, target_file: str, theme_kw: Optional[str]) -> str:
    """（3）Gxx、xx#、xx组 → 与 target 组号一致。"""
    gid = parse_group_int_from_target_for_replace(target_file)
    if gid is None:
        return filename
    disp = group_display_from_target(target_file, gid)
    out = filename
    out = _replace_g_marker(out, disp)
    if theme_kw:
        out = _replace_theme_group_suffix(out, theme_kw, disp)
    out = _replace_hash_group(out, disp)
    # xx组（泛化，在 G 与主题组之后）
    out = _replace_plain_digit_group(out, disp)
    return out


def nk2026_process_8xml_summary_filename(filename: str, target_file: str) -> str:
    """（1）Wn…车联…Gxx小组8XML&代码&需求文档&规划表汇总"""
    pat = r"W\d+(?:车联|纸联|体联).*?G(\d+)小组8XML"
    if not re.search(pat, filename):
        return filename
    gid = parse_group_int_from_target_for_replace(target_file)
    if gid is None:
        return filename
    disp = group_display_from_target(target_file, gid)

    def _repl(m):
        return re.sub(r"G\d+", "G" + disp, m.group(0), count=1)

    new_name = re.sub(pat, _repl, filename)
    print(f"[NK2026 8XML汇总替换] {filename} -> {new_name}")
    return new_name


def matches_incentive_talk_filename(name: str) -> bool:
    return "激励小组谈话实录" in name


def incentive_week_from_filename(name: str) -> Optional[int]:
    m = re.search(r"W(\d+)", name, re.I)
    return int(m.group(1)) if m else None


def incentive_group_from_filename(name: str) -> Optional[int]:
    m = re.search(r"G0*(\d+)(?!\d)", name, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(?<!\d)0*(\d+)\s*组", name)
    if m:
        return int(m.group(1))
    return None


def pick_best_incentive_file(
    notebook_filenames: Sequence[str],
    week: int,
    group_id: int,
) -> Optional[str]:
    """（2）周次 ∈ {W,W-1,W-2,W-3} 且组号与 target 一致，优先周次接近 target.week。"""
    allowed_weeks = {week, week - 1, week - 2, week - 3}
    candidates = []
    for fn in notebook_filenames:
        if not matches_incentive_talk_filename(fn):
            continue
        gw = incentive_week_from_filename(fn)
        gg = incentive_group_from_filename(fn)
        if gw is None or gg is None:
            continue
        if gw not in allowed_weeks:
            continue
        if gg != group_id:
            continue
        candidates.append((abs(gw - week), -gw, fn))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def nk2026_merge_incentive_file(
    file_list: List[str],
    notebook_filenames: Sequence[str],
    meta: dict,
) -> List[str]:
    """（2）去掉旧激励实录，换成本子中匹配的版本；本子无匹配则不追加。"""
    week = meta["week"]
    gid = meta["group_id"]
    best = pick_best_incentive_file(notebook_filenames, week, gid)
    out = [f for f in file_list if not matches_incentive_talk_filename(f)]
    if best:
        out.append(best)
    return out


def nk2026_matches_b_planning_xml_log_same_theme_week(
    name: str, theme_kw: str, week: Optional[int]
) -> bool:
    """
    与 B7（规划表+8XML+日志类）同类且主题、梯子周次 Wn 一致，不限组号。
    用于从自动化录制的文件列表中剔除「旧组」那条 B7，再按当前组追加正确文件。
    """
    if week is None:
        return False
    if not theme_kw or theme_kw not in name:
        return False
    if "规划表" not in name or "代码修改" not in name or "8XML" not in name:
        return False
    if "日志记录" not in name and "日志" not in name:
        return False
    return bool(re.search(rf"W0*{int(week)}(?!\d)", name, re.I))


def nk2026_merge_b_planning_xml_log_file(
    file_list: List[str],
    notebook_filenames: Sequence[str],
    meta: dict,
) -> List[str]:
    """按当前 target 的主题/周次/组号重选 B7：去掉同主题同周次下旧的 B7 项，再追加本子中匹配的一份（无则仅剔除）。"""
    week = meta.get("week")
    gid = int(meta["group_id"])
    tk = (meta.get("theme_kw") or "").strip()
    if week is None or not tk:
        return list(file_list)
    best = pick_nk2026_b_planning_xml_log_for_auto(notebook_filenames, tk, gid, week)
    out = [
        f
        for f in file_list
        if not nk2026_matches_b_planning_xml_log_same_theme_week(f, tk, week)
    ]
    if best:
        out.append(best)
    return out


# Gxx 生成时注入模型：各组角色名单（须原样写入成稿一行）
NK2026_GROUP_ROLE_LINES: Dict[int, str] = {
    2: "2组：组长王逸凌，需求员曹紫煜，周志员赵雨涵，优裁员任诗清，展示员张哲宇",
    3: "3组：组长艾思奇，需求员何熹淳，周志员王子卓，优裁员高家铭，展示员阳雨洁",
    4: "4组：组长牛雨萱，需求员刘芳希，周志员王睿瑜，优裁员王策，展示员邓耀飞",
    5: "5组：组长吕明诺，需求员林家熠，周志员贺翰林，优裁员林靖然，展示员杨珺童，组长助理李熙铭",
    7: "7组：组长邢陶清，需求员宋伯宸，周志员朱钟铭，优裁员胡博涵，展示员王春晓",
    8: "8组：组长邓佳怡，需求员罗元伟，周志员罗梓芮，优裁员郑志昊，展示员李梦涛",
    9: "9组：组长范珂祎，需求员刘思岑，周志员张欣妍，优裁员石欣哲，展示员吕旭婧",
    10: "10组：组长曾楚宁，需求员殷佳仪，周志员马翔宇，优裁员梁昊，展示员魏华阳，组长助理李卓霖",
    11: "11组：组长董朝阳，需求员王炳環，周志员卢苑，优裁员国峻赫，展示员陈铭宇",
    12: "12组：组长何美璇，需求员程子涵，周志员颜国庄，优裁员马诗渊，展示员李烁菲",
    13: "13组：组长缪臻，需求员冯鑫科，周志员王烨，优裁员贾申奥，展示员秦东杰",
    14: "14组：组长孟子玉，需求员韩东儒，周志员姜禧，优裁员张浩正，展示员国轩",
    15: "15组：组长王宣贺，需求员薛健，周志员路浩斌，优裁员黄国天，展示员胡欣如",
    16: "16组：组长刘翔宇，需求员王乐，周志员白诗雨，优裁员马禹翔，展示员鞠昀慧",
    17: "17组：组长张懿鸾，需求员李易桐，周志员张旗庭，优裁员张祎然，展示员王泽浩，组长助理李易洲",
    18: "18组：组长张龙飞，需求员张珈齐，周志员张书晗，优裁员石晨昊，展示员王雅枫",
    19: "19组：组长张煜坤，需求员王鹏钧，周志员李亚杰，优裁员刘宸旭，展示员王文韬",
    20: "20组：组长卢运宸，需求员滕鑫，周志员林子媛，优裁员王麒萱，展示员马传志",
    21: "21组：组长王朝阳，需求员李星泽，周志员刘蔚霖，优裁员章伟健，展示员孙唯源",
    22: "22组：组长赵亚鑫，需求员吴宇石，周志员杨鸿杰，优裁员梁靖泽，展示员冯义",
}


def nk2026_group_role_line(gid: int) -> str:
    """返回该组须在 Gxx.md 中输出的角色行；无预置名单时返回空串。"""
    return NK2026_GROUP_ROLE_LINES.get(int(gid), "")


def nk2026_force_fulltext(filename: str) -> bool:
    for mk in _FULLTEXT_MARKERS:
        if mk in filename:
            return True
    return False


def nk2026_matches_group(name: str, g: int) -> bool:
    """
    与前端 FileList.vue `nk2026MatchesGroup` 一致：G7/G07 或 xx组/0x 组，避免误伤周次里的数字。
    """
    gs = str(int(g))
    pad = gs.zfill(2)
    if re.search(rf"G(?:{re.escape(gs)}|{re.escape(pad)})(?!\d)", name, re.I):
        return True
    if re.search(rf"(?<!\d)(?:{re.escape(gs)}|{re.escape(pad)})\s*组", name):
        return True
    return False


def nk2026_matches_b_planning_xml_log(
    name: str, theme_kw: str, gid: int, week: Optional[int]
) -> bool:
    """
    B7（前端自动勾选 / 自动化勾选）：主题、组号、四类关键词与梯子一致，
    且文件名中含 Wn，其中 n 与梯子图 / target_file 的周次 week 相同。
    """
    if week is None:
        return False
    if not theme_kw or theme_kw not in name:
        return False
    if not nk2026_matches_group(name, gid):
        return False
    if "规划表" not in name or "代码修改" not in name or "8XML" not in name:
        return False
    if "日志记录" not in name and "日志" not in name:
        return False
    return bool(re.search(rf"W0*{int(week)}(?!\d)", name, re.I))


def nk2026_matches_b_planning_xml_log_gxx(name: str, theme_kw: str, gid: int) -> bool:
    """
    B7（生成 Gxx.md 选素材）：同主题、同组号、四类关键词；文件名须含至少一处 Wn。
    具体选哪一份由 pick_nk2026_b_planning_xml_log_for_gxx 按「文件名中周次数字最大」决定。
    """
    if not theme_kw or theme_kw not in name:
        return False
    if not nk2026_matches_group(name, gid):
        return False
    if "规划表" not in name or "代码修改" not in name or "8XML" not in name:
        return False
    if "日志记录" not in name and "日志" not in name:
        return False
    return bool(_WEEK_NUM_RE.search(name))


def max_week_markers_in_filename(name: str) -> int:
    """文件名中所有 Wn 的 n 取最大值（无则 -1）。"""
    ws = [int(x) for x in re.findall(r"W(\d+)", name, re.I)]
    return max(ws) if ws else -1


def nk2026_is_pdf_raster_sidecar_listing(name: str) -> bool:
    """
    与 stem.pdf 配套的 stem_image 目录（PDF 分页/图层产物，见 parse_input/util 等），
    会出现在 user_raw_file 的 listdir 里且不含扩展名；关键词与 stem.pdf 相同，
    若参与 max(文件名) 会字典序压过真正的 .pdf，故 B7 选取时必须排除。
    """
    if not name:
        return False
    low = name.lower()
    if low.endswith("_image") and not re.search(r"\.[a-z0-9]{2,8}$", low):
        return True
    return False


def pick_nk2026_b_planning_xml_log_for_auto(
    names: Sequence[str], theme_kw: str, gid: int, week: Optional[int]
) -> Optional[str]:
    """前端/自动化：周次与梯子一致；多份时按文件名中周次标记最大再比名字序（无 V 版本号）。"""
    if week is None:
        return None
    cand = [
        fn
        for fn in names
        if nk2026_matches_b_planning_xml_log(fn, theme_kw, gid, week)
        and not nk2026_is_pdf_raster_sidecar_listing(fn)
    ]
    if not cand:
        return None
    return max(cand, key=lambda fn: (max_week_markers_in_filename(fn), fn))


def pick_nk2026_b_planning_xml_log_for_gxx(
    names: Sequence[str], theme_kw: str, gid: int
) -> Optional[str]:
    """生成 Gxx：同主题同组+关键词；只取「文件名中周次标记最大」的一份（无 V 版本号）。"""
    cand = [
        fn
        for fn in names
        if nk2026_matches_b_planning_xml_log_gxx(fn, theme_kw, gid)
        and not nk2026_is_pdf_raster_sidecar_listing(fn)
    ]
    if not cand:
        return None
    return max(cand, key=lambda fn: (max_week_markers_in_filename(fn), fn))


def week_num_from_filename(name: str) -> Optional[int]:
    m = _WEEK_NUM_RE.search(name)
    return int(m.group(1)) if m else None


def _parse_vx_version_sort_key(name: str) -> Optional[int]:
    m = re.search(r"V(\d+)\.(\d+)", name, re.I)
    if not m:
        return None
    return int(m.group(1)) * 1000 + int(m.group(2))


def infer_week_for_theme_group(file_names: Sequence[str], theme_kw: str, gid: int) -> Optional[int]:
    """
    生成 Gxx 用周次推断（第 3 处）：

    1) **主规则**：在 `file_names` 全部文件名中，筛出「文件名能识别本组组号」
       （`nk2026_matches_group`，含 G07 / 7组 等）且「含 Wn」的，取其中 **n 最大** 的周次（最新周）。
    2) 若一个都没有：回退为 `parse_target_ladder_meta` 与本组 `theme_kw`、`gid` 一致的梯子图填写文件周次。
    3) 若仍无：再回退为「含主题名 + 梯子图填写 + 组号」的文件里，**第一个**解析到的 Wn。
    """
    max_w: Optional[int] = None
    for fn in file_names:
        if not nk2026_matches_group(fn, gid):
            continue
        wn = week_num_from_filename(fn)
        if wn is None:
            continue
        if max_w is None or wn > max_w:
            max_w = wn
    if max_w is not None:
        return max_w
    for fn in file_names:
        meta = parse_target_ladder_meta(fn)
        if meta and meta["theme_kw"] == theme_kw and int(meta["group_id"]) == gid:
            return int(meta["week"])
    for fn in file_names:
        if theme_kw not in fn or "梯子图填写" not in fn:
            continue
        if not nk2026_matches_group(fn, gid):
            continue
        wn = week_num_from_filename(fn)
        if wn is not None:
            return wn
    return None


def _ladder_half_matches(name: str, week: int, theme_kw: str, gid: int, half_kw: str) -> bool:
    if week_num_from_filename(name) != week:
        return False
    if theme_kw not in name:
        return False
    if not nk2026_matches_group(name, gid):
        return False
    if "梯子图填写" not in name:
        return False
    return (f"（{half_kw}）" in name) or (f"({half_kw})" in name)


def collect_nk2026_gxx_input_files(
    all_filenames: Sequence[str],
    theme_kw: str,
    gid: int,
    week: Optional[int],
) -> List[Tuple[str, bool]]:
    """
    生成 Gxx.md 时注入模型的 user_raw_file 素材，与前端 NK2026 A/B/C 自动勾选规则一致。

    返回 [(文件名, use_fulltext_snippet), ...] 已去重、稳定排序：
    - True：规则中要求「获取全文」的文档（梯子图上下半、B2/B3/B4/B5）
    - False：默认「相关搜索」（B1、B6 最近两版、B7 规划/XML 日志表（Gxx 取周次标记最新）、C 类预置 PDF）

    仅包含命中规则的文档，不再把目录下其余文件当作「共享补充」整批塞入。
    """
    names = sorted({str(x) for x in all_filenames if x})
    name_set: Set[str] = set(names)
    out: List[Tuple[str, bool]] = []
    seen: Set[str] = set()

    def add(fn: str, full: bool) -> None:
        if fn in seen or fn not in name_set:
            return
        out.append((fn, full))
        seen.add(fn)

    # A：梯子图填写上/下半，获取全文（与勾选一侧自动带上另一侧一致：此处两侧都纳入）
    if week is not None:
        for half_kw in ("上半部分", "下半部分"):
            for fn in names:
                if _ladder_half_matches(fn, week, theme_kw, gid, half_kw):
                    add(fn, True)

    if week is not None:
        b3_candidates: List[Tuple[str, int, int]] = []
        for fn in names:
            wn = week_num_from_filename(fn)
            # B1：智能纪要 + 周教研 + 同周次 Wn → 相关搜索
            if "智能纪要" in fn and "周教研" in fn and wn == week:
                add(fn, False)
            # B2：同周次 + 主题 + 精进种子定版 → 获取全文
            if wn == week and theme_kw in fn and "精进种子三线放空设计定版" in fn:
                add(fn, True)
            # B3：激励谈话实录（候选，下面统一取 |Wn−week| 最小的一份，与前端/自动化一致）
            if (
                wn is not None
                and (wn == week or wn == week - 1 or wn == week - 2 or wn == week - 3)
                and theme_kw in fn
                and "激励小组谈话实录" in fn
                and nk2026_matches_group(fn, gid)
            ):
                b3_candidates.append((fn, wn, abs(wn - week)))
            # B4：当周 TA 小结 → 获取全文
            if wn == week and "课设实验课后TA助教小结" in fn:
                add(fn, True)
            # B5：梯子图周次减 1 的 TA 小结 → 获取全文
            if wn == week - 1 and "课设实验课后TA助教小结" in fn:
                add(fn, True)
        if b3_candidates:
            b3_candidates.sort(key=lambda x: (x[2], -x[1]))
            add(b3_candidates[0][0], True)

    # B7（Gxx 素材）：同主题同组+四类关键词；取文件名中「所有 Wn」周次数字最大的一份（无 V 版本号）
    b7_pick = pick_nk2026_b_planning_xml_log_for_gxx(names, theme_kw, gid)
    if b7_pick:
        add(b7_pick, False)

    # B6：同主题 + 除乘加三法则；多版本时取版本号最高的两个 → 相关搜索
    sanfa: List[Tuple[str, int]] = []
    for fn in names:
        if theme_kw not in fn or "各组除乘加三法则分析填写" not in fn:
            continue
        vr = _parse_vx_version_sort_key(fn)
        if vr is not None:
            sanfa.append((fn, vr))
    sanfa.sort(key=lambda x: x[1])
    for fn, _ in sanfa[-2:]:
        add(fn, False)

    # C：场景预置基础文档 → 相关搜索
    for fn in names:
        if fn in SCENE_BASE_DOC_NAMES:
            add(fn, False)

    return out


def nk2026_retrieval_lists(file_list: Sequence[str]) -> Tuple[List[int], List[int]]:
    """（4）四类全文，其余默认相关搜索；left 与 FileCard 默认一致。"""
    left: List[int] = []
    right: List[int] = []
    for _ in file_list:
        left.append(1)
        right.append(3)
    for i, fn in enumerate(file_list):
        if nk2026_force_fulltext(fn):
            left[i] = 0
            right[i] = 0
    return left, right


def list_notebook_filenames(notebook_id: str) -> List[str]:
    base = os.path.join(".", "received_dir", "user_raw_file", notebook_id)
    if not os.path.isdir(base):
        return []
    try:
        return sorted(os.listdir(base))
    except OSError:
        return []


def latest_times_for_theme(notebook_id: str, target_file: str) -> Optional[int]:
    """（5）取 target 主题关键字最近一次录制的 times。"""
    from django.db.models import Max
    from app_chat.models import AutomationRecord

    tk = theme_keyword_in_text(target_file)
    if not tk:
        return AutomationRecord.objects.filter(notebook_id=notebook_id).aggregate(Max("times"))["times__max"]

    all_times = (
        AutomationRecord.objects.filter(notebook_id=notebook_id)
        .values_list("times", flat=True)
        .distinct()
        .order_by("-times")
    )
    for t in all_times:
        rec = (
            AutomationRecord.objects.filter(notebook_id=notebook_id, times=t)
            .order_by("step_number")
            .first()
        )
        if rec and rec.target_file and tk in rec.target_file:
            return t
    return AutomationRecord.objects.filter(notebook_id=notebook_id).aggregate(Max("times"))["times__max"]


def nk2026_ladder_meta_from_file_list(file_list: Sequence[str]) -> Tuple[Optional[str], Optional[dict]]:
    """从勾选文档列表中取第一张「梯子图填写」图，解析 Wn / 主题 / 组号。"""
    for name in file_list or []:
        if not name or "梯子图填写" not in name:
            continue
        meta = parse_target_ladder_meta(name)
        if meta:
            return name, meta
    return None, None


def nk2026_build_card_title_core(meta: dict, ladder_filename: str) -> str:
    """例：W13体联G22组（G 后组号格式与梯子图文件名一致）。"""
    week = int(meta["week"])
    theme_kw = meta["theme_kw"]
    gdisp = group_display_from_target(ladder_filename, int(meta["group_id"]))
    return f"W{week}{theme_kw}G{gdisp}组"


def nk2026_resolve_title_suffix(existing_title: str, default_suffix: str = "NK2026教学批改报告") -> str:
    """保留原标题中 Sn: 之后的固定后缀（若含 NK2026 / 教学批改），否则用默认。"""
    if not existing_title:
        return default_suffix
    m = re.match(r"^S\d+:(.*)$", existing_title.strip())
    rest = (m.group(1) if m else existing_title).strip()
    for marker in ("NK2026教学批改报告", "NK2026", "教学批改报告", "教学批改"):
        idx = rest.find(marker)
        if idx >= 0:
            return rest[idx:].strip()
    return default_suffix


def nk2026_apply_automation_card_title(
    card_id: int,
    file_list: Sequence[str],
    scene_name: Optional[str],
    existing_content_title: str = "",
) -> None:
    """
    自动化 create_card 后：用勾选文档中的梯子图文件名生成 contentTitle。
    例：S5:W13体联G22组NK2026教学批改报告；S5 卡默认四色 P、DMT M。
    """
    if not is_nk2026_ladder_scene(scene_name):
        return
    ladder_fn, meta = nk2026_ladder_meta_from_file_list(file_list)
    if not meta or not ladder_fn:
        print("[NK2026 card_title] 未在 file_list 中找到可解析的梯子图填写文件名，跳过")
        return
    try:
        from app_chat.models import Card
    except Exception as e:
        print(f"[NK2026 card_title] 导入 Card 失败: {e}")
        return

    try:
        card = Card.objects.get(cid=int(card_id))
    except Exception as e:
        print(f"[NK2026 card_title] 卡片不存在 cid={card_id}: {e}")
        return

    old_title = (existing_content_title or card.contentTitle or "").strip()
    prefix_m = re.match(r"^(S\d+:)", old_title)
    prefix = prefix_m.group(1) if prefix_m else "S5:"
    suffix = nk2026_resolve_title_suffix(old_title)
    core = nk2026_build_card_title_core(meta, ladder_fn)
    new_title = f"{prefix}{core}{suffix}"
    card.contentTitle = new_title
    update_fields = ["contentTitle"]
    if prefix.upper().startswith("S5:"):
        card.four_color_type = "P"
        card.dmt_level = "M"
        update_fields.extend(["four_color_type", "dmt_level"])
    card.save(update_fields=update_fields)
    print(f"[NK2026 card_title] cid={card_id} -> {new_title!r}")


def process_non_nk2026_summary_legacy(filename: str, target_file: str) -> str:
    """旧 NK2025-xx#-小组整体汇总 规则（非 NK2026 场景沿用）。"""
    group_summary_pattern = r"NK2025-(\d+)#-小组整体汇总"
    group_match = re.search(group_summary_pattern, filename)
    if not group_match:
        return filename
    target_match = re.search(r"(\d+)#", target_file)
    if not target_match:
        return filename
    new_number = target_match.group(1)
    old_number = group_match.group(1)
    new_filename = filename.replace(f"NK2025-{old_number}#", f"NK2025-{new_number}#")
    print(f"[文件名替换] {filename} -> {new_filename}")
    return new_filename
