# -*- coding: utf-8 -*-
"""班级多人合订作业批改：页→学生映射、版面复刻、跨生边界、报告/记忆/精要卡。

约定：一个 PDF = 一个班 × 一次作业拼接；第 i 个学生占连续 pages_per_assignment 页。
单人批改路径不受影响；仅配置卡标注「批改模式：班级多人」时启用。
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .utils import safe_json_dump, safe_json_load

CLASS_MODE_KEYS = ("班级多人", "多人", "class_multi", "class")
RUBRIC_DIR_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "docs" / "反馈·微批" / "班级多人批改测试" / "知引素养量规",
)


def is_class_multi_material(material: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(material, dict):
        return False
    if material.get("class_multi"):
        return True
    mode = str(material.get("grading_mode") or material.get("批改模式") or "").strip()
    # 勿仅凭「班级」二字触发；须明确多人模式或 class_multi 标记
    return mode in CLASS_MODE_KEYS or "多人" in mode


def page_to_student_index(page_1based: int, pages_per: int) -> int:
    """1-based 学生序号。"""
    if pages_per <= 0 or page_1based <= 0:
        return 0
    return (page_1based - 1) // pages_per + 1


def student_page_range(student_index: int, pages_per: int) -> Tuple[int, int]:
    """闭区间 [start, end]，1-based。"""
    start = (student_index - 1) * pages_per + 1
    return start, start + pages_per - 1


_DEFAULT_STUDENT_NAME_RE = re.compile(r"^学生\s*\d+$")
# 配置卡占位：学生xx / 学生xxx / 学生XXX / 学生×× 等 → 转为序号「学生n」
_ROSTER_PLACEHOLDER_RE = re.compile(r"^学生\s*[xX×✕ｘＸ]{1,}$")
_NAME_LABEL_RE = re.compile(
    r"(?:姓名|名字|学生姓名|署名)[：:\s]*([一-龥·]{2,4})"
)
_CLASS_MARK_RE = re.compile(
    r"(?:"
    r"[一二三四五六七八九十百]+年级\s*[（(]?\s*[一二三四五六七八九十\d]+\s*[）)]?\s*班?"
    r"|[1-9]\s*年级\s*[（(]?\s*[1-9一二三四五六七八九十]\s*[）)]?\s*班?"
    r"|[七八九]\s*[（(]\s*[一二三四五六七八九十1-9]\s*[）)]"
    r"|[1-9]\s*[\.．·、]\s*[1-9一二三四五六七八九十]"
    r"|[七八九]\s*[\.．·、]\s*[1-9一二三四五六七八九十]"
    r")"
)
_BARE_NAME_RE = re.compile(r"^[一-龥]{2,4}$")
_NON_NAME_TOKENS = frozenset({
    "姓名", "名字", "班级", "学号", "得分", "分数", "作业", "练习", "语文", "数学", "英语",
    "正确", "错误", "解答", "填空", "选择", "阅读", "作文", "计算", "应用", "单位",
    "有理数", "代数式", "整式", "方程", "方程式", "小数", "整数", "无理数", "实数",
    "负数", "正数", "绝对值", "科学记数", "因式", "多项式", "单项式", "几何", "函数",
    "统计", "概率", "应用题", "计算题", "乘方", "开方", "不等式", "物理", "化学",
    "历史", "地理", "生物", "政治", "复习", "测验",
})
_PRINTED_SECTION_RE = re.compile(
    r"^\s*(?:第\s*)?\d+(?:\s*[\.．]\s*\d+){1,3}(?:\s|$|[一-龥])"
)


def _is_default_student_label(name: Any) -> bool:
    text = str(name or "").strip()
    return (not text) or bool(_DEFAULT_STUDENT_NAME_RE.match(text))


def _is_roster_placeholder(name: Any) -> bool:
    """配置卡「学生xx/学生xxx」等占位，或已是「学生n」。"""
    text = str(name or "").strip()
    if not text:
        return True
    if _is_default_student_label(text):
        return True
    return bool(_ROSTER_PLACEHOLDER_RE.match(text))


def _normalize_roster_entry(name: Any, student_index: int) -> str:
    """名单项：真名保留；占位/空 → 学生{序号}。"""
    sid = int(student_index or 0)
    text = str(name or "").strip()
    if not text or _is_roster_placeholder(text):
        return f"学生{sid}" if sid else "学生"
    return text


def _clean_person_name_candidate(raw: str) -> str:
    text = str(raw or "").strip()
    text = _CLASS_MARK_RE.sub("", text)
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    text = re.sub(r"\s+", "", text)
    text = text.strip("：:·.,，。；;、|/\\-—_")
    if text.endswith("同学"):
        text = text[:-2]
    if text in _NON_NAME_TOKENS:
        return ""
    if _BARE_NAME_RE.match(text) and text not in _NON_NAME_TOKENS:
        return text
    return ""


def _guess_name_from_labeled_text(blob: str) -> str:
    """只认「姓名：张三」类显式标注，避免从题干误抽。"""
    text = str(blob or "")
    if not text.strip():
        return ""
    for m in _NAME_LABEL_RE.finditer(text):
        hit = _clean_person_name_candidate(m.group(1))
        if hit:
            return hit
    return ""


def _guess_name_from_header_line(blob: str) -> str:
    """页眉里的印刷节号标题不当成姓名。手写的「七.1 姓名」仍可认出。"""
    text = str(blob or "").strip()
    if not text:
        return ""
    labeled = _guess_name_from_labeled_text(text)
    if labeled:
        return labeled
    if _PRINTED_SECTION_RE.match(text):
        return ""
    stripped = _CLASS_MARK_RE.sub(" ", text)
    stripped = re.sub(r"\s+", "", stripped)
    stripped = stripped.strip("：:·.,，。；;、|/\\-—_#*")
    return _clean_person_name_candidate(stripped)


def printed_page_header(raw: Any) -> str:
    """页眉就是检测阶段写下的印刷标题，这里不再猜哪些字是姓名。"""
    return str(raw or "").strip()


def _collect_name_candidates_from_page(page_data: Dict[str, Any]) -> List[Tuple[str, str]]:
    """返回 [(candidate, source_hint), ...]，高置信在前。"""
    hits: List[Tuple[str, str]] = []
    if not isinstance(page_data, dict):
        return hits
    for key in ("page_header", "page_title", "header", "title"):
        val = page_data.get(key)
        if not val:
            continue
        for fn, hint in (
            (_guess_name_from_labeled_text, f"{key}:label"),
            (_guess_name_from_header_line, f"{key}:line"),
        ):
            hit = fn(str(val))
            if hit:
                hits.append((hit, hint))
    for q in page_data.get("questions") or []:
        if not isinstance(q, dict):
            continue
        stem = " ".join(
            str(q.get(k) or "")
            for k in ("stem_excerpt", "parent_stem_excerpt", "printed_text", "label", "content", "text")
        )
        # 题干像姓名栏时，才采信短作答为姓名
        if re.search(r"姓名|名字|署名", stem):
            labeled = _guess_name_from_labeled_text(stem)
            if labeled:
                hits.append((labeled, "q:stem_label"))
            ans = str(q.get("student_answer") or "").strip()
            if isinstance(q.get("student_answer"), dict):
                ans = str(
                    q["student_answer"].get("text")
                    or q["student_answer"].get("value")
                    or q["student_answer"].get("raw")
                    or ""
                ).strip()
            hit = _clean_person_name_candidate(ans)
            if hit:
                hits.append((hit, "q:answer_near_name"))
        else:
            # 无姓名栏时，仅当作答本身带「姓名：」字样
            ans_raw = q.get("student_answer")
            ans_text = ""
            if isinstance(ans_raw, str):
                ans_text = ans_raw
            elif isinstance(ans_raw, dict):
                ans_text = str(ans_raw.get("text") or ans_raw.get("value") or ans_raw.get("raw") or "")
            labeled = _guess_name_from_labeled_text(ans_text)
            if labeled:
                hits.append((labeled, "q:answer_label"))
    return hits


def _page_file_needles(page_num: int) -> List[str]:
    """兼容 _page1 / _page01 / _page001 及 page1 命名。"""
    n = int(page_num)
    return [
        f"_page{n:03d}",
        f"_page{n:02d}",
        f"_page{n}",
        f"page{n:03d}",
        f"page{n:02d}",
        f"page{n}",
    ]


def _name_matches_page(filename: str, page_num: int) -> bool:
    name = str(filename or "")
    # 避免 page10 误匹配 page1：用边界（非数字）截断
    for needle in _page_file_needles(page_num):
        idx = name.find(needle)
        if idx < 0:
            continue
        end = idx + len(needle)
        if end < len(name) and name[end].isdigit():
            continue
        return True
    return False


def _find_clean_page_image(clean_dir: str, page_num: int) -> str:
    if not clean_dir or not os.path.isdir(clean_dir):
        return ""
    for name in sorted(os.listdir(clean_dir)):
        if not name.lower().endswith(".png"):
            continue
        if _name_matches_page(name, page_num):
            return os.path.join(clean_dir, name)
    return ""


def _load_pass1_page_payload(pass1_dir: str, page_num: int) -> Dict[str, Any]:
    if not pass1_dir or not os.path.isdir(pass1_dir):
        return {}
    merged: Dict[str, Any] = {}
    for name in os.listdir(pass1_dir):
        if not _name_matches_page(name, page_num):
            continue
        if not (name.endswith(".json") or name.endswith(".detect.json") or name.endswith(".grade.json")):
            continue
        if name.endswith(".review.json"):
            continue
        # 只要主 json / grade / detect，跳过 thinking/error 旁路
        if ".thinking." in name or ".error." in name or ".responses." in name:
            continue
        path = os.path.join(pass1_dir, name)
        try:
            data = safe_json_load(path)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        # grade / 合并 json 优先叠在 detect 上
        if name.endswith(".detect.json") and merged:
            continue
        if not merged:
            merged = dict(data)
        else:
            for k, v in data.items():
                if v in (None, "", [], {}):
                    continue
                merged[k] = v
    return merged


def _vision_header_crop_path(image_path: str) -> str:
    """裁出页眉/姓名栏附近（上约 42%）供视觉抽取，避免整页题面干扰。"""
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            w, h = im.size
            if w < 32 or h < 32:
                return image_path
            top = im.crop((0, 0, w, max(48, int(h * 0.42))))
            cache_dir = os.path.join(os.path.dirname(image_path), "_name_crops")
            os.makedirs(cache_dir, exist_ok=True)
            out = os.path.join(cache_dir, f"hdr_{os.path.basename(image_path)}")
            top.save(out, format="PNG")
            return out
    except Exception:
        return image_path


def _vision_guess_student_name(image_path: str) -> str:
    if not image_path or not os.path.isfile(image_path):
        return ""
    try:
        from openai import OpenAI
        from .llm_clients import (
            _resolve_qwen_api_key,
            _HOMEWORK_QWEN_BASE_URL_DEFAULT,
            homework_qwen_model,
        )
        from .utils import image_to_data_uri
        crop = _vision_header_crop_path(image_path)
        client = OpenAI(api_key=_resolve_qwen_api_key(), base_url=_HOMEWORK_QWEN_BASE_URL_DEFAULT)
        prompt = (
            "这是班级合订作业某一学生首页的上方区域。"
            "请找手写/填写的学生个人姓名（通常在「姓名」旁，或年级/班级旁空白处，2–4个汉字）。"
            "常见干扰：年级如7.1、七（1）班、学科名、题目标题——这些都不是姓名。"
            "只输出JSON：{\"name\":\"张三\"}；找不到则 {\"name\":\"\"}"
        )
        resp = client.chat.completions.create(
            model=homework_qwen_model(),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_to_data_uri(crop)}},
                ],
            }],
            temperature=0,
            extra_body={"enable_thinking": False},
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return _guess_name_from_labeled_text(raw) or _guess_name_from_header_line(raw)
        data = json.loads(m.group(0))
        return _clean_person_name_candidate(str((data or {}).get("name") or ""))
    except Exception:
        return ""


def enrich_class_map_student_names(
    *,
    paths: Dict[str, str],
    class_map: Dict[str, Any],
    use_vision_fallback: bool = True,
) -> Dict[str, Any]:
    """定名优先级：

    1) 配置卡本材料有「学生名单」→ 名单第一优先（「学生xx/xxx」占位转为学生n）；
    2) 无名单 → Pass1 文本 / 视觉识别；
    3) 仍无 → 学生n。

    不再用前序次同序位已认出姓名回填（各次提交人数/名单可能不一致）。
    """
    if not isinstance(class_map, dict):
        return {}
    students = list(class_map.get("students") or [])
    if not students:
        return class_map
    pass1_dir = paths.get("pass1_json") or ""
    clean_dir = paths.get("clean") or ""
    raw_roster = [str(x).strip() for x in (class_map.get("roster") or []) if str(x).strip()]
    has_config_roster = bool(raw_roster)
    if has_config_roster:
        # 规范化写入 class_map，占位统一成学生n，后续报告/记忆同源
        class_map["roster"] = [
            _normalize_roster_entry(n, i + 1) for i, n in enumerate(raw_roster)
        ]
    used_names: Set[str] = set()
    changed = False

    for stu in students:
        if not isinstance(stu, dict):
            continue
        sid = int(stu.get("student_index") or 0)
        pages = [int(p) for p in (stu.get("pages") or [])]
        ordered_pages = sorted(pages)
        if ordered_pages:
            first = ordered_pages[0]
            ordered_pages = [first] + [p for p in ordered_pages if p != first]

        cur = str(stu.get("display_name") or "")
        prior_extracted = str(stu.get("extracted_name") or "").strip()
        prior_source = str(stu.get("name_source") or "").strip()
        extracted = ""
        source = ""

        if has_config_roster:
            roster_name = _normalize_roster_entry(
                raw_roster[sid - 1] if 0 < sid <= len(raw_roster) else "",
                sid,
            )
            if not _is_default_student_label(roster_name):
                new_name = roster_name
                source = "roster"
            else:
                new_name = ""
        else:
            new_name = ""
        if not new_name:
            # 无名单：Pass1 → 视觉 → 保留本轮已识别真名 → 学生n
            for p in ordered_pages:
                payload = _load_pass1_page_payload(pass1_dir, p)
                for hit, hint in _collect_name_candidates_from_page(payload):
                    if hit and hit not in used_names:
                        extracted, source = hit, f"pass1_text:p{p}:{hint}"
                        break
                if extracted:
                    break
            need_vision = (
                not extracted
                and use_vision_fallback
                and ordered_pages
                and clean_dir
                and _is_default_student_label(cur)
                and (not prior_extracted or _is_default_student_label(prior_extracted))
            )
            if need_vision:
                page_num = ordered_pages[0]
                img = _find_clean_page_image(clean_dir, page_num)
                hit = _vision_guess_student_name(img)
                if hit and hit not in used_names:
                    extracted, source = hit, f"vision:p{page_num}"

            if extracted:
                new_name = extracted
            elif cur and not _is_default_student_label(cur) and not _is_roster_placeholder(cur):
                new_name = cur
                source = prior_source or source or "kept"
            elif (
                prior_extracted
                and not _is_default_student_label(prior_extracted)
                and not _is_roster_placeholder(prior_extracted)
                and prior_source.startswith(("pass1_text", "vision", "kept"))
            ):
                new_name = prior_extracted
                source = prior_source or "extracted_stale"
            else:
                new_name = f"学生{sid}" if sid else (cur or "学生")
                source = source or "default"

            # 抽取撞名：后者退回学生n（无名单可退）
            if new_name in used_names and source.startswith(("pass1_text", "vision", "extracted_stale", "kept")):
                if cur and not _is_default_student_label(cur) and cur not in used_names:
                    new_name, source = cur, "kept_dedupe"
                else:
                    new_name, source = f"学生{sid}", "default_dedupe"

        # 名单撞名：后者改为学生n，避免两人同名糊在一起
        if new_name in used_names and not _is_default_student_label(new_name):
            new_name, source = f"学生{sid}", f"{source}_dedupe"

        old = str(stu.get("display_name") or "")
        stu["display_name"] = new_name
        stu["name_source"] = source
        if extracted:
            stu["extracted_name"] = extracted
        if old != new_name:
            changed = True
        used_names.add(new_name)

    class_map["students"] = students
    if changed:
        class_map["names_enriched"] = True
    return class_map


def apply_enriched_names_to_session_map(
    session_map: Optional[Dict[str, Any]],
    class_map: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not isinstance(session_map, dict) or not isinstance(class_map, dict):
        return session_map
    by_idx = {
        int(s.get("student_index")): str(s.get("display_name") or "")
        for s in (class_map.get("students") or [])
        if isinstance(s, dict) and s.get("student_index")
    }
    sessions = session_map.get("sessions")
    if isinstance(sessions, list):
        for sess in sessions:
            if not isinstance(sess, dict):
                continue
            idx = int(sess.get("student_index") or sess.get("session_index") or 0)
            name = by_idx.get(idx)
            if not name:
                continue
            title = f"{class_map.get('class_id')}·第{class_map.get('homework_index')}次·{name}"
            sess["display_name"] = name
            sess["session_title"] = title
            sess["unit_title"] = title
            sess["module_title"] = title
    if isinstance(session_map.get("class_multi"), dict):
        session_map["class_multi"] = class_map
    return session_map


def build_class_page_map(
    *,
    student_count: int,
    pages_per_assignment: int,
    roster: Optional[Sequence[str]] = None,
    class_id: str = "",
    homework_index: int = 1,
    total_pages: int = 0,
) -> Dict[str, Any]:
    if student_count <= 0:
        raise ValueError("班级人数必须为正整数")
    if pages_per_assignment <= 0:
        raise ValueError("本次布置页数必须为正整数")
    expected = student_count * pages_per_assignment
    if total_pages and total_pages < expected:
        raise ValueError(
            f"文档仅 {total_pages} 页，不足 人数{student_count}×每生{pages_per_assignment}页={expected}"
        )
    raw_names = [str(x).strip() for x in (roster or []) if str(x).strip()]
    names = [_normalize_roster_entry(n, i + 1) for i, n in enumerate(raw_names)]
    students: List[Dict[str, Any]] = []
    page_to_student: Dict[int, int] = {}
    for i in range(1, student_count + 1):
        start, end = student_page_range(i, pages_per_assignment)
        pages = list(range(start, end + 1))
        for p in pages:
            page_to_student[p] = i
        label = _normalize_roster_entry(raw_names[i - 1] if i - 1 < len(raw_names) else "", i)
        students.append({
            "student_index": i,
            "display_name": label,
            "pages": pages,
            "page_start": start,
            "page_end": end,
            "name_source": "roster" if (i - 1 < len(raw_names) and not _is_roster_placeholder(raw_names[i - 1])) else (
                "roster_placeholder" if raw_names else "default"
            ),
        })
    # 跨学生相邻页：不跨页（如每生2页时 2|3、4|5…）
    student_boundaries: List[Tuple[int, int]] = []
    for i in range(1, student_count):
        _s, end_i = student_page_range(i, pages_per_assignment)
        start_next, _e = student_page_range(i + 1, pages_per_assignment)
        student_boundaries.append((end_i, start_next))
    return {
        "class_id": str(class_id or "").strip() or "未命名班级",
        "student_count": student_count,
        "pages_per_assignment": pages_per_assignment,
        "homework_index": int(homework_index or 1),
        "roster": names,
        "expected_pages": expected,
        "students": students,
        "page_to_student": page_to_student,
        "student_boundary_pairs": student_boundaries,
        "template_student_index": 1,
        "template_pages": list(range(1, pages_per_assignment + 1)),
    }


def build_session_map_for_class(
    material: Dict[str, Any],
    *,
    subject: str,
    sample_id: str,
    total_pages: int,
) -> Dict[str, Any]:
    cmap = material.get("class_page_map") or build_class_page_map(
        student_count=int(material.get("student_count") or 0),
        pages_per_assignment=int(material.get("pages_per_assignment") or 0),
        roster=material.get("roster") or [],
        class_id=str(material.get("class_id") or ""),
        homework_index=int(material.get("homework_index") or 1),
        total_pages=total_pages,
    )
    sessions: List[Dict[str, Any]] = []
    for stu in cmap["students"]:
        pages = [p for p in stu["pages"] if 1 <= int(p) <= total_pages]
        if not pages:
            continue
        i = int(stu["student_index"])
        title = f"{cmap['class_id']}·第{cmap['homework_index']}次·{stu['display_name']}"
        sessions.append({
            "session_index": i,
            "order_index": i,
            "session_id": f"{sample_id}_stu{i:02d}",
            "page_start": min(pages),
            "page_end": max(pages),
            "pages": pages,
            "session_title": title,
            "unit_title": title,
            "module_title": title,
            "submodules": [],
            "boundary_signal": "class_multi_grading",
            "boundary_reason": "班级多人合订：按学生切分，学生间不跨页",
            "split_source": "class_multi_grading",
            "confidence": 1.0,
            "student_index": i,
            "display_name": stu["display_name"],
            "class_id": cmap["class_id"],
            "homework_index": cmap["homework_index"],
            "pages_per_assignment": cmap["pages_per_assignment"],
        })
    assigned = sorted({p for s in sessions for p in s["pages"]})
    unassigned = [p for p in range(1, total_pages + 1) if p not in set(assigned)]
    return {
        "subject": subject,
        "sample_id": sample_id,
        "total_pages": total_pages,
        "session_count": len(sessions),
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "session_granularity": "class_multi_student",
        "split_source": "class_multi_grading",
        "class_multi": cmap,
        "grading_config": {
            "filename": material.get("filename"),
            "config_card_id": material.get("config_card_id"),
            "assigned_pages": assigned,
            "unassigned_pages": unassigned,
            "description": material.get("description") or "",
            "class_multi": True,
            "class_id": cmap["class_id"],
            "student_count": cmap["student_count"],
            "pages_per_assignment": cmap["pages_per_assignment"],
            "homework_index": cmap["homework_index"],
            "roster": cmap.get("roster") or [],
        },
        "sessions": sessions,
    }


def student_page_runs(class_map: Dict[str, Any]) -> List[List[int]]:
    return [list(stu["pages"]) for stu in (class_map.get("students") or [])]


def clear_cross_student_boundaries(
    pass1_dir: str,
    boundary_pairs: Sequence[Tuple[int, int]],
) -> int:
    """清除跨学生相邻页的 continues_*，避免 Pass1.5 把学生边界当跨页。"""
    from .utils import parse_page_num, sorted_json_pages

    pair_set = {(int(a), int(b)) for a, b in boundary_pairs}
    if not pair_set:
        return 0
    changed = 0
    for json_path in sorted_json_pages(pass1_dir):
        try:
            data = safe_json_load(json_path)
        except Exception:
            continue
        page = int(data.get("page") or parse_page_num(os.path.basename(json_path)) or 0)
        boundary = data.get("boundary")
        if not isinstance(boundary, dict):
            continue
        dirty = False
        if any(a == page for a, _b in pair_set) and boundary.get("continues_to_next"):
            boundary["continues_to_next"] = False
            boundary["description_next"] = "班级多人：下一页为另一名学生，不跨页衔接"
            dirty = True
        if any(b == page for _a, b in pair_set) and boundary.get("continues_from_prev"):
            boundary["continues_from_prev"] = False
            boundary["description_prev"] = "班级多人：上一页为另一名学生，不跨页衔接"
            dirty = True
        if dirty:
            data["boundary"] = boundary
            # 页缘题也不应再标跨页跨学生
            for q in data.get("questions") or []:
                if isinstance(q, dict) and q.get("cross_page"):
                    # 仅当本页是边界页时保守清理
                    if any(a == page or b == page for a, b in pair_set):
                        q["cross_page"] = False
            safe_json_dump(json_path, data)
            changed += 1
    return changed


def _remap_detect_payload(detect: Dict[str, Any], target_page: int) -> Dict[str, Any]:
    out = copy.deepcopy(detect)
    out["page"] = target_page
    out["class_multi_layout_replicated"] = True
    out["layout_template_page"] = detect.get("page")
    for key in ("page_header", "page_title", "header", "title"):
        if key in out:
            out[key] = printed_page_header(out.get(key))
    for q in out.get("questions") or []:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id") or q.get("qid") or "").strip()
        if qid:
            # 保持题内 id，全局题号按页改写
            q["qid_global"] = f"p{target_page}:{qid}"
        # 清除模板学生作答痕迹字段，留给理解/三区重算
        for key in (
            "student_answer", "answer", "verdict", "error_type", "feedback",
            "white_gray_black", "wgb", "confidence", "recurrence_hint",
        ):
            if key in q:
                q.pop(key, None)
    return out


def replicate_layout_from_template(
    *,
    paths: Dict[str, str],
    pages: List[Dict[str, Any]],
    class_map: Dict[str, Any],
    subject: str,
    page_detect_path_fn,
    question_json_path_fn,
    merge_detect_only_fn,
) -> Dict[str, Any]:
    """仅第一名学生跑过 detect 后，将其版面结构复刻到其余学生对应偏移页。"""
    pages_per = int(class_map.get("pages_per_assignment") or 0)
    template_idx = int(class_map.get("template_student_index") or 1)
    pages_by_num = {int(p["page"]): p for p in pages}
    replicated = []
    missing_templates = []
    for stu in class_map.get("students") or []:
        si = int(stu["student_index"])
        if si == template_idx:
            continue
        for offset, target_page in enumerate(stu["pages"]):
            src_page = offset + 1  # 模板生页 = 1..pages_per
            src = pages_by_num.get(src_page)
            dst = pages_by_num.get(int(target_page))
            if not src or not dst:
                missing_templates.append({"src": src_page, "dst": target_page, "student": si})
                continue
            src_detect = page_detect_path_fn(paths, src)
            if not os.path.isfile(src_detect):
                missing_templates.append({"src": src_page, "dst": target_page, "student": si, "reason": "no_detect"})
                continue
            detect = safe_json_load(src_detect)
            remapped = _remap_detect_payload(detect, int(target_page))
            dst_detect = page_detect_path_fn(paths, dst)
            safe_json_dump(dst_detect, remapped)
            merge_detect_only_fn(
                dst_detect,
                question_json_path_fn(paths["pass1_json"], dst["clean_abs_path"]),
                subject,
                int(target_page),
            )
            replicated.append({"from": src_page, "to": int(target_page), "student": si})
    return {
        "replicated_count": len(replicated),
        "replicated": replicated,
        "missing": missing_templates,
        "pages_per_assignment": pages_per,
        "template_student_index": template_idx,
    }


def load_rubric_guidance(max_chars: int = 12000) -> str:
    """从知引素养量规 HTML 抽纯文本，供班级报告语境。"""
    texts: List[str] = []
    for base in RUBRIC_DIR_CANDIDATES:
        if not base.is_dir():
            continue
        for name in (
            "深圳知引素养量规.html",
            "知引素养量规_机理总图.html",
            "知引素养量规_五性图解_总图加五分图.html",
        ):
            path = base / name
            if not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
            plain = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.I)
            plain = re.sub(r"<style[\s\S]*?</style>", " ", plain, flags=re.I)
            plain = re.sub(r"<[^>]+>", " ", plain)
            plain = re.sub(r"\s+", " ", plain).strip()
            if plain:
                texts.append(f"【{name}】{plain[:4000]}")
        break
    joined = "\n\n".join(texts)
    return joined[:max_chars] if joined else (
        "请严格使用课标与素养量规语境：区分知识问题、技能错误、能力/认知盲区；"
        "盲区指认知盲区（不含错别字或粗心算错）；内耗区指时对时错且多数时候不行；"
        "最近发展区指跳一跳够得着的发展空间。表述须写出具体考查内容，页码题号仅作括号补充。"
    )


def _question_figure(question: Dict[str, Any]) -> str:
    for key in ("figure_desc", "diagram_desc", "image_description", "visual_context", "chart_note", "figure"):
        value = question.get(key)
        if isinstance(value, str) and value.strip():
            return re.sub(r"\s+", " ", value).strip()[:200]
    return ""


def _page_question_briefs(pass1_dir: str, pages: Sequence[int]) -> List[Dict[str, Any]]:
    from .utils import parse_page_num, sorted_json_pages

    want = set(int(p) for p in pages)
    briefs = []
    for json_path in sorted_json_pages(pass1_dir):
        try:
            data = safe_json_load(json_path)
        except Exception:
            continue
        page = int(data.get("page") or parse_page_num(os.path.basename(json_path)) or 0)
        if page not in want:
            continue
        for q in data.get("questions") or []:
            if not isinstance(q, dict):
                continue
            stem = str(q.get("stem") or q.get("stem_excerpt") or q.get("text") or "").strip()
            parent = str(q.get("parent_stem_excerpt") or "").strip()
            if parent and parent in stem:
                parent = ""
            answer = q.get("student_answer") if q.get("student_answer") not in (None, "") else q.get("answer")
            if isinstance(answer, dict):
                answer = answer.get("text") or answer.get("value") or answer.get("raw") or ""
            briefs.append({
                "page": page,
                "qid": q.get("id") or q.get("qid"),
                "qid_global": q.get("qid_global") or f"p{page}:{q.get('id') or ''}",
                "stem": re.sub(r"\s+", " ", stem).strip()[:420],
                "parent_stem": re.sub(r"\s+", " ", parent).strip()[:180],
                "figure": _question_figure(q),
                "reading": re.sub(r"\s+", " ", str(q.get("understanding") or "")).strip()[:180],
                "verdict": q.get("verdict"),
                "error_type": q.get("error_type"),
                "knowledge_point": q.get("knowledge_point") or q.get("kp"),
                "student_answer": re.sub(r"\s+", " ", str(answer or "")).strip()[:160],
            })
    return briefs


def _layer_label_for_brief(brief: Dict[str, Any]) -> str:
    """轻量归入知识问题 / 技能错误 / 能力缺陷（不硬套，供单生报告用语）。"""
    blob = " ".join(
        str(brief.get(k) or "")
        for k in ("error_type", "knowledge_point", "stem", "verdict")
    ).lower()
    # 粗心/错别字：不升格为认知盲区，仍可标为技能执行层
    if any(x in blob for x in ("错别字", "笔误", "抄写", "粗心", "计算失误", "看错", "漏写单位")):
        return "技能错误"
    if any(x in blob for x in ("审题", "步骤", "运算", "格式", "书写", "作图", "表达", "列式", "计算")):
        return "技能错误"
    if any(x in blob for x in ("概念", "定义", "性质", "公式", "定理", "词汇", "语法点", "知识点", "识记")):
        return "知识问题"
    if any(x in blob for x in ("推理", "迁移", "策略", "方法", "分析", "综合", "建模", "概括", "能力")):
        return "能力缺陷"
    v = str(brief.get("verdict") or "").lower()
    if v in ("uncertain", "灰", "gray", "grey"):
        return "待核验"
    return "知识问题"


def _zone_hint_for_brief(brief: Dict[str, Any], *, recurring: bool = False) -> str:
    """轻量认知分区提示：盲区/内耗区/就近发展区；错别字粗心不算盲区。"""
    blob = " ".join(
        str(brief.get(k) or "")
        for k in ("error_type", "stem", "verdict")
    )
    if any(x in blob for x in ("错别字", "笔误", "粗心", "计算失误", "看错")):
        return "宜归为执行疏漏，不作认知盲区"
    v = str(brief.get("verdict") or "").lower()
    if recurring:
        return "倾向内耗区（时对时错、需巩固）"
    if v in ("uncertain", "灰", "gray", "grey"):
        return "可对照就近发展区，核验后再定"
    if _layer_label_for_brief(brief) == "能力缺陷":
        return "可能涉及认知盲区，需结合作答过程判断"
    return "可对照就近发展区，布置一道相近的题目"


def _build_student_report_template(
    *,
    student: Dict[str, Any],
    class_map: Dict[str, Any],
    pass1_dir: str,
    prior_memory: Optional[Dict[str, Any]] = None,
    homework_index: int = 1,
) -> Dict[str, Any]:
    """规则模板底稿（LLM 失败时兜底；也作 LLM 的结构化证据）。"""
    pages = student.get("pages") or []
    briefs = _page_question_briefs(pass1_dir, pages)
    wrong = [b for b in briefs if str(b.get("verdict") or "").lower() in ("wrong", "incorrect", "false", "错误")]
    uncertain = [b for b in briefs if str(b.get("verdict") or "").lower() in ("uncertain", "灰", "gray", "grey")]
    short_mode = int(homework_index or 1) <= 1 and len(pages) <= 2
    points: List[str] = []
    if not briefs:
        points.append("该生本次页面中未解析到可核验的题目，请结合逐页批改图确认。")
    else:
        tally = _brief_tally(briefs)
        blank_bit = f"，未作答 {tally['blank']}" if tally["blank"] else ""
        points.append(
            f"这一步：卷面上共 {tally['total'] or len(briefs)} 处，较稳 {tally['ok']}，"
            f"需关注 {tally['weak']}，待核验 {tally['unc']}{blank_bit}。先看还没完成的那一层，不要先列知识点。"
        )
    for b in (wrong + uncertain)[: (4 if short_mode else 8)]:
        content = (b.get("stem") or b.get("parent_stem") or "（题干未抽出）").strip()
        loc = f"第{b['page']}页"
        if b.get("qid"):
            loc += f"·题{b['qid']}"
        answer = str(b.get("student_answer") or "").strip()
        wrote = f"写下「{answer[:40]}」" if answer else "没有写下答案"
        figure = str(b.get("figure") or "").strip()
        fig = f"；图上是{figure[:40]}" if figure else ""
        et = str(b.get("error_type") or "").strip() or (
            "待核验" if str(b.get("verdict") or "").lower() in ("uncertain", "灰", "gray", "grey") else "与题目要求不符"
        )
        points.append(
            f"卷面：「{content[:90]}」{wrote}，{et}{fig}（{loc}）。"
        )
    if prior_memory:
        prev = prior_memory.get("summary_points") or prior_memory.get("points") or []
        if prev:
            label = "前序纵向" if not short_mode else "前序提示"
            points.append(f"{label}：" + "；".join(str(x)[:72] for x in prev[: (2 if short_mode else 3)]))
    if short_mode:
        points = points[:7]
    return {
        "student_index": student.get("student_index"),
        "display_name": student.get("display_name"),
        "pages": pages,
        "homework_index": homework_index,
        "class_id": class_map.get("class_id"),
        "short_mode": short_mode,
        "points": points,
        "question_briefs": briefs,
        "wrong_count": len(wrong),
        "uncertain_count": len(uncertain),
        "report_source": "template",
    }


def build_student_assignment_report(
    *,
    student: Dict[str, Any],
    class_map: Dict[str, Any],
    pass1_dir: str,
    prior_memory: Optional[Dict[str, Any]] = None,
    homework_index: int = 1,
) -> Dict[str, Any]:
    """单生报告底稿；批量润色见 enrich_student_reports_with_llm。"""
    return _build_student_report_template(
        student=student,
        class_map=class_map,
        pass1_dir=pass1_dir,
        prior_memory=prior_memory,
        homework_index=homework_index,
    )


_STUDENT_REPORT_BATCH = 8


def _student_report_evidence(report: Dict[str, Any]) -> Dict[str, Any]:
    """送进个人报告的是卷面、全班对照和已经写好的这一步，不把模板句子再送进去。"""
    return {
        "student_index": report.get("student_index"),
        "display_name": report.get("display_name"),
        "pages": report.get("pages"),
        "wrong_count": report.get("wrong_count"),
        "uncertain_count": report.get("uncertain_count"),
        "expectation": report.get("expectation") or "",
        "notable": list(report.get("notable") or []),
        "sample_items": [
            {
                "content": brief.get("stem"),
                "parent": brief.get("parent_stem"),
                "answer": brief.get("student_answer"),
                "figure": brief.get("figure"),
                "reading": brief.get("reading"),
                "page": brief.get("page"),
                "qid": brief.get("qid"),
                "verdict": brief.get("verdict"),
                "error": brief.get("error_type"),
                "label_unchecked": brief.get("knowledge_point"),
            }
            for brief in (report.get("question_briefs") or [])
            if isinstance(brief, dict)
        ],
    }


def _pick_student_report_item(
    report: Dict[str, Any],
    by_sid: Dict[str, Dict[str, Any]],
    by_name: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """序号和姓名都对上才采用。对不上就留模板，避免把别人的话填到这个人身上。"""
    sid = str(report.get("student_index") or "").strip()
    name = str(report.get("display_name") or "").strip()
    by_index = by_sid.get(sid) if sid else None
    by_person = by_name.get(name) if name else None
    if by_index is not None:
        item_name = str(by_index.get("display_name") or "").strip()
        if not item_name or not name or item_name == name:
            return by_index
        return by_person
    return by_person


def _apply_student_report_item(report: Dict[str, Any], item: Dict[str, Any], model_tag: str) -> None:
    pts = [str(point).strip() for point in (item.get("points") or []) if str(point).strip()]
    if len(pts) >= 2:
        report["points"] = pts[:8]
        report["report_source"] = f"llm:{model_tag}"
    highs: List[str] = []
    for highlight in item.get("highlights") or []:
        text = str(highlight or "").strip()
        if 1 < len(text) <= 16 and text not in highs:
            highs.append(text)
    if highs:
        report["highlights"] = highs[:10]


def enrich_student_reports_with_llm(
    student_reports: List[Dict[str, Any]],
    *,
    class_map: Dict[str, Any],
    subject_label: str = "",
    trace_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """按完整的人分批写个人报告。某一批失败只留这几人的模板，已写好的不丢。"""
    if not student_reports:
        return student_reports
    from .semantic_feedback_brief import paper_situation

    situation = paper_situation(student_reports)
    by_student = situation.get("by_student") or {}
    paper = situation.get("questions") or []
    for report in student_reports:
        report["notable"] = by_student.get(str(report.get("student_index"))) or []
        report["paper"] = paper
    batch_size = _STUDENT_REPORT_BATCH
    for start in range(0, len(student_reports), batch_size):
        batch = student_reports[start:start + batch_size]
        payload = {
            "class_id": class_map.get("class_id"),
            "homework_index": class_map.get("homework_index"),
            "subject": subject_label,
            "paper": paper,
            "students": [_student_report_evidence(report) for report in batch],
        }
        names = "、".join(str(report.get("display_name") or "") for report in batch)
        try:
            _write_student_report_batch(
                batch, payload, names, trace_dir, start=start,
                subject_label=subject_label,
            )
        except Exception as exc:
            print(
                f"[class-multi] 个人报告本批未写成，保留模板 "
                f"students={start + 1}-{start + len(batch)}: {exc}",
                flush=True,
            )
    return student_reports


def _write_student_report_batch(
    batch: List[Dict[str, Any]],
    payload: Dict[str, Any],
    names: str,
    trace_dir: Optional[str],
    *,
    start: int,
    subject_label: str = "",
) -> None:
    from .semantic_feedback_brief import competency_context_block

    prompt = f"""请为下列每位学生各写一份「本次作业批改报告」分点。突出该生和全班的差别，禁止全班套同一套话，也禁止把 expectation 再抄一遍。

{competency_context_block(subject_label)}

这一批只有这些学生：{names}。reports 里每人一条，用 student_index 和 display_name 对应，不要漏人，也不要写这批以外的人。

expectation 里已经写过这一步、学、家长和档位。教和育只在班级期望里，这里不要再写。
paper 是全班逐题内容和人数。sample_items 里 content 是题干，answer 是该生写下的，figure 有图才有，reading 是批改时记下的题意。label_unchecked 只是已有标签，与 content 不一致时以 content 为准，不要用标签造一个新名称。
notable 已经标出「多数人做对而该生没有」和「同一类里有的做对有的没有」。这些必须写进卷面，不要改成另一种说法。

每人按这个顺序写，先一句几十个字，再说开：
- 这一步：该生在 expectation 那一层上停在哪里。不重写班级的教、育和三档定义。
- 档位：达到、基本达到、尚未达到中的哪一档。差距在这一步下面的知识事实，还是还不能说明这一步对应的能力。
- 素养链：这一步做到哪 → 课标里的学科素养名称及在该生哪一处作答看得出来 → 人的变化看得出或还看不出。三截用「 → 」分开。不要把第一截写成题号或知识点清单。
- 画像：本次体现几种正式能力就写几种。用19项原名，能力名后写 1 到 5 的素养分，一位小数，再写支撑这个分数的考查内容和步骤，括号里写36项中能够对应的行为。依据不能写成同一句。每项用「；」隔开。
- 卷面：先写考查的知识、情境、这一步要做什么。做错、空着、部分做对分开。同类内容有的做对有的没有，对照着写。多数人会而该生不会或空着，写明。有 figure 就写图上是什么；没有 figure 时，reading 里若写了图，就用那句。都没有就不要编。题号只放括号。
- 下一步：对学生说的一种做法（说出步骤、与某同学对照同一步骤、在一个小任务中使用一次；本次确有阅读时才写读完一段再回来做题）。不要并列多种。

不要写学、教、育。不要自造题干和课标里没有的概括名词。错别字和粗心不要升成认知盲区。
禁止写出四色、DMT、象限、共识区、温度计、螺旋、主体本体。
另给出 highlights：3～6 个需加粗的短词（2～12字），如「基本达到」「运算能力」。
只输出 JSON：
{{"reports":[{{"student_index":1,"display_name":"姓名","points":["这一步：…","档位：…","素养链：…","画像：…","卷面：…","下一步：…"],"highlights":["基本达到","运算能力"]}},…]}}

【证据】
{json.dumps(payload, ensure_ascii=False)}
"""
    text, model_tag, data = _call_class_multi_json_step(
        prompt,
        step="student_reports",
        system="你是班级多人批改中的单生诊断写作者。只写这一批学生。输出必须是合法 JSON。",
        max_tokens=12000,
        timeout_s=400.0,
        min_chars=40,
        trace_dir=trace_dir,
        expect_key="reports",
    )
    if text.startswith("（班级报告生成暂降级") or "failed:" in model_tag or "reports" not in data:
        print(
            f"[class-multi] 个人报告本批未写成，保留模板 "
            f"students={start + 1}-{start + len(batch)}",
            flush=True,
        )
        return
    by_sid: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for item in data.get("reports") or []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("student_index") or "").strip()
        name = str(item.get("display_name") or "").strip()
        if sid:
            by_sid[sid] = item
        if name:
            by_name[name] = item
    filled = 0
    for report in batch:
        item = _pick_student_report_item(report, by_sid, by_name)
        if not item:
            continue
        _apply_student_report_item(report, item, model_tag)
        if str(report.get("report_source") or "").startswith("llm:"):
            filled += 1
    print(
        f"[class-multi] 个人报告本批 {filled}/{len(batch)} 人已写 "
        f"students={start + 1}-{start + len(batch)}",
        flush=True,
    )


def _apply_point_highlights(text: str, highlights: Optional[Sequence[str]] = None) -> str:
    """按模型给出的短词加粗着色；无列表时用内置关键词兜底。"""
    raw = str(text or "")
    if not raw:
        return ""
    keys = [str(x).strip() for x in (highlights or []) if str(x).strip()]
    if not keys:
        keys = [
            "知识问题", "技能错误", "能力缺陷", "认知盲区", "盲区", "内耗区", "就近发展区",
            "把握较稳", "需关注", "待核验", "乘方", "符号错误", "运算顺序", "新定义",
        ]
    # 长词优先，避免短词先吃掉长词
    keys = sorted(set(keys), key=len, reverse=True)
    # 先整体转义，再仅替换命中词为 mark
    escaped = (
        raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    for k in keys:
        if k not in raw:
            continue
        ek = k.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        escaped = escaped.replace(ek, f'<mark class="hl">{ek}</mark>')
    # 保留已有 **加粗**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _issue_key(brief: Dict[str, Any]) -> str:
    stem = str(brief.get("stem") or "").strip()
    kp = str(brief.get("knowledge_point") or "").strip()
    et = str(brief.get("error_type") or "").strip()
    return (stem or kp or et or "未命名考查点")[:80]


def enrich_student_reports_with_peer_horizontal(
    student_reports: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """单生报告以本生+前序为主，仍须有轻量班内横向（弱于班级报告）。"""
    from collections import defaultdict

    issue_to_names: Dict[str, List[str]] = defaultdict(list)
    for r in student_reports:
        name = str(r.get("display_name") or f"学生{r.get('student_index')}")
        seen = set()
        for b in r.get("question_briefs") or []:
            v = str(b.get("verdict") or "").lower()
            if v not in ("wrong", "incorrect", "false", "错误", "uncertain", "灰", "gray", "grey"):
                continue
            key = _issue_key(b)
            if key in seen:
                continue
            seen.add(key)
            issue_to_names[key].append(name)

    for r in student_reports:
        name = str(r.get("display_name") or f"学生{r.get('student_index')}")
        short_mode = bool(r.get("short_mode"))
        points = list(r.get("points") or [])
        peer_lines: List[str] = []
        for b in r.get("question_briefs") or []:
            v = str(b.get("verdict") or "").lower()
            if v not in ("wrong", "incorrect", "false", "错误", "uncertain", "灰", "gray", "grey"):
                continue
            key = _issue_key(b)
            peers = [n for n in issue_to_names.get(key, []) if n != name]
            if peers:
                shown = "、".join(peers[:3])
                more = f"等{len(peers)}人" if len(peers) > 3 else f"（{len(peers)}人）"
                peer_lines.append(
                    f"班内横向：考查「{key}」同需关注还有{shown}{more}，偏班级共性；配对与分区建议见班级报告。"
                )
            else:
                peer_lines.append(
                    f"班内横向：考查「{key}」本次偏本生个性突出，宜在班级报告中对照共性项与就近发展区建议。"
                )
            if short_mode and peer_lines:
                break
            if len(peer_lines) >= (1 if short_mode else 2):
                break
        if peer_lines:
            # 插在前序之后、避免完全没有横向
            points.extend(peer_lines[: (1 if short_mode else 2)])
        r["points"] = points
        r["peer_horizontal"] = peer_lines[:2]
    return student_reports


def _call_qwen_text(prompt: str, *, max_tokens: int = 2500, system: str = "") -> str:
    try:
        from openai import OpenAI
        from .llm_clients import _resolve_qwen_api_key, _HOMEWORK_QWEN_BASE_URL_DEFAULT, homework_qwen_model
        client = OpenAI(api_key=_resolve_qwen_api_key(), base_url=_HOMEWORK_QWEN_BASE_URL_DEFAULT)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=homework_qwen_model(),
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens,
            extra_body={"enable_thinking": False},
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        return f"（班级报告生成暂降级：{type(exc).__name__}）"


def _append_class_report_llm_trace(trace_dir: Optional[str], record: Dict[str, Any]) -> None:
    """把这一次模型的原文留在班级报告目录，供事后核对。"""
    if not trace_dir:
        return
    try:
        os.makedirs(trace_dir, exist_ok=True)
        path = os.path.join(trace_dir, "class_report_llm_trace.json")
        data = safe_json_load(path) if os.path.isfile(path) else {}
        if not isinstance(data, dict):
            data = {}
        calls = data.get("calls")
        if not isinstance(calls, list):
            calls = []
        calls.append(record)
        data["calls"] = calls
        safe_json_dump(path, data)
    except Exception as exc:
        print(f"[class-multi] 模型输出留存失败 {exc}", flush=True)


def _call_class_multi_llm(
    prompt: str,
    *,
    system: str = "",
    max_tokens: int = 3200,
    timeout_s: float = 200.0,
    min_chars: int = 40,
    step: str = "",
    trace_dir: Optional[str] = None,
) -> Tuple[str, str]:
    """班级多人报告：cloudapi 流式 Claude 5.5→4.8，失败再降级当前 Qwen。

    同一次调用失败后先再试一次，再换下一个模型。每次尝试的原文都留存。
    返回 (text, model_tag)。
    """
    from app_chat.cross_reorganize_skills import _client_for_abbr, _collect_stream_text

    sys_msg = system or (
        "你是熟悉义务教育课标与一线教研的班级作业诊断助手。"
        "写作须具体、有层次、避免套话同质化；只用中文。"
    )
    chain = [
        ("claude-opus-5.5", "opus"),
        ("claude-opus-4.8", "opus"),
    ]
    errors: List[str] = []

    def _record(abbr: str, attempt: int, *, model: str, output: str, ok: bool, error: str = "") -> None:
        _append_class_report_llm_trace(trace_dir, {
            "at": datetime.now().isoformat(timespec="seconds"),
            "step": step or "class_multi",
            "attempt": attempt,
            "abbr": abbr,
            "model": model,
            "ok": ok,
            "error": error,
            "chars": len(output or ""),
            "output": output or "",
        })

    for abbr, mode in chain:
        for attempt in (1, 2):
            text = ""
            model_name = ""
            try:
                print(
                    f"[class_multi] LLM abbr={abbr} attempt={attempt} stream=1 timeout={timeout_s}s",
                    flush=True,
                )
                client, model_name, create_extra = _client_for_abbr(abbr)
                try:
                    client = client.with_options(timeout=float(timeout_s))
                except Exception:
                    pass
                kwargs: Dict[str, Any] = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": int(max_tokens),
                    "temperature": 0.35,
                    "stream": True,
                }
                kwargs.update(create_extra or {})
                text = _collect_stream_text(client.chat.completions.create(**kwargs))
                text = re.sub(r"\s+\n", "\n", (text or "").strip())
                if len(text) < min_chars:
                    raise ValueError(f"输出过短 chars={len(text)}")
                print(f"[class_multi] LLM ok mode={mode} model={model_name} chars={len(text)}", flush=True)
                _record(abbr, attempt, model=model_name, output=text, ok=True)
                return text, model_name
            except Exception as exc:
                errors.append(f"{abbr}#{attempt}: {exc}")
                print(f"[class_multi] LLM fail abbr={abbr} attempt={attempt}: {exc}", flush=True)
                _record(abbr, attempt, model=model_name, output=text, ok=False, error=str(exc))
                if attempt == 1:
                    continue
                break
    fallback = ""
    for attempt in (1, 2):
        fallback = _call_qwen_text(prompt, max_tokens=max_tokens, system=sys_msg)
        degraded = fallback.startswith("（班级报告生成暂降级") or len(fallback) < min_chars
        _record(
            "qwen",
            attempt,
            model="qwen_fallback",
            output=fallback,
            ok=not degraded,
            error="降级或过短" if degraded else "",
        )
        if not degraded:
            print(f"[class_multi] LLM qwen fallback chars={len(fallback)}", flush=True)
            return fallback, "qwen_fallback"
        if attempt == 1:
            print("[class_multi] LLM qwen fallback 失败，再试一次", flush=True)
            continue
    return fallback, f"failed:{'|'.join(errors)[:160]}"


def _level_band(wrong_count: Any, uncertain_count: Any = 0) -> str:
    try:
        w = int(wrong_count or 0)
    except (TypeError, ValueError):
        w = 0
    try:
        u = int(uncertain_count or 0)
    except (TypeError, ValueError):
        u = 0
    if w <= 0 and u <= 1:
        return "把握较稳"
    if w <= 2:
        return "中等波动"
    return "需重点关注"


def _extract_prior_highlights(prior: Dict[str, Any], *, limit: int = 6) -> List[str]:
    """从前序班级报告抽取要点，不喂全文。"""
    if not isinstance(prior, dict):
        return []
    ready = prior.get("highlights")
    if isinstance(ready, list) and ready:
        return [str(x).strip() for x in ready if str(x).strip()][:limit]
    text = str(prior.get("summary") or prior.get("markdown") or "")
    hits: List[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith(("- ", "* ", "> ")):
            s = s[2:].strip()
        elif re.match(r"^\d+[\.、]\s+", s):
            s = re.sub(r"^\d+[\.、]\s+", "", s).strip()
        else:
            continue
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        if len(s) < 8:
            continue
        hits.append(s[:120])
        if len(hits) >= limit:
            break
    if not hits and text.strip():
        chunk = re.sub(r"\s+", " ", text).strip()[:180]
        if chunk:
            hits.append(chunk)
    return hits


def _theme_tokens_from_points(points: Sequence[Any], *, limit: int = 4) -> List[str]:
    themes: List[str] = []
    for p in points or []:
        s = str(p or "")
        m = re.search(r"考查「([^」]{2,40})」", s)
        if m:
            themes.append(m.group(1).strip())
        elif "前序" not in s and "班内横向" not in s and "学情概览" not in s:
            themes.append(s[:36].strip())
        if len(themes) >= limit:
            break
    # 去重保序
    out: List[str] = []
    seen = set()
    for t in themes:
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def build_class_longitudinal_digest(
    *,
    homework_index: int,
    student_reports: List[Dict[str, Any]],
    prior_class_reports: Optional[List[Dict[str, Any]]] = None,
    prior_student_histories: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """近最多 3 次：重要变化信号（特色/水平分层 + 趋势），供班级报告纵向用。"""
    priors = sorted(
        [p for p in (prior_class_reports or []) if isinstance(p, dict)],
        key=lambda x: int(x.get("homework_index") or 0),
    )[-3:]
    prior_pack = [
        {
            "homework_index": p.get("homework_index"),
            "highlights": _extract_prior_highlights(p, limit=5),
        }
        for p in priors
    ]
    hist_map = prior_student_histories if isinstance(prior_student_histories, dict) else {}
    bands: Dict[str, List[str]] = {"把握较稳": [], "中等波动": [], "需重点关注": []}
    trajectories: List[Dict[str, Any]] = []
    improving: List[str] = []
    slipping: List[str] = []
    stable_weak: List[str] = []
    for r in student_reports:
        name = str(r.get("display_name") or f"学生{r.get('student_index')}")
        sid = str(r.get("student_index"))
        band = _level_band(r.get("wrong_count"), r.get("uncertain_count"))
        bands[band].append(name)
        themes_now = _theme_tokens_from_points(r.get("points") or [], limit=3)
        mem = hist_map.get(sid) if isinstance(hist_map.get(sid), dict) else {}
        hist = [
            h for h in (mem.get("history") or [])
            if isinstance(h, dict) and int(h.get("homework_index") or 0) < int(homework_index or 1)
        ]
        hist = sorted(hist, key=lambda x: int(x.get("homework_index") or 0))[-3:]
        if not hist:
            trajectories.append({
                "name": name,
                "band_now": band,
                "trend": "本次为可参照起点或暂无同生前序",
                "themes_now": themes_now,
                "wrong_now": r.get("wrong_count"),
            })
            continue
        prev = hist[-1]
        try:
            prev_w = int(prev.get("wrong_count") or 0)
        except (TypeError, ValueError):
            prev_w = 0
        try:
            now_w = int(r.get("wrong_count") or 0)
        except (TypeError, ValueError):
            now_w = 0
        delta = now_w - prev_w
        if delta <= -2:
            trend = "近次需关注项明显减少，倾向进步"
            improving.append(name)
        elif delta >= 2:
            trend = "近次需关注项明显增加，需警惕回落或新难点"
            slipping.append(name)
        elif now_w >= 3 and prev_w >= 3:
            trend = "近几次持续偏弱，宜查是否同一考查点内耗或知识问题固着"
            stable_weak.append(name)
        else:
            trend = "近次波动不大，维持当前分层观察"
        themes_prev = _theme_tokens_from_points(prev.get("points") or [], limit=3)
        recurring = [t for t in themes_now if any(t[:10] in tp or tp[:10] in t for tp in themes_prev)]
        trajectories.append({
            "name": name,
            "band_now": band,
            "trend": trend,
            "wrong_now": now_w,
            "wrong_prev": prev_w,
            "prev_homework_index": prev.get("homework_index"),
            "themes_now": themes_now,
            "recurring_themes": recurring[:3],
        })
    return {
        "has_prior": bool(prior_pack) or any(
            isinstance(hist_map.get(str(r.get("student_index"))), dict)
            and (hist_map.get(str(r.get("student_index"))) or {}).get("history")
            for r in student_reports
        ),
        "prior_homework_indexes": [p.get("homework_index") for p in prior_pack],
        "prior_class_highlights": prior_pack,
        "level_bands_now": {k: v for k, v in bands.items() if v},
        "improving": improving,
        "slipping": slipping,
        "stable_weak": stable_weak,
        "student_trajectories": trajectories[:40],
    }


def _class_report_highlights_from_markdown(markdown: str, *, limit: int = 8) -> List[str]:
    return _extract_prior_highlights({"markdown": markdown or ""}, limit=limit)


def _build_class_report_fallback(
    *,
    class_map: Dict[str, Any],
    student_reports: List[Dict[str, Any]],
    subject_label: str,
    longitudinal: Dict[str, Any],
    degrade_note: str = "",
) -> str:
    """规则兜底：保留横向分层 + 纵向变化要点，质量高于纯占位句。"""
    hw = class_map.get("homework_index")
    bands = longitudinal.get("level_bands_now") or {}
    focuses: List[str] = []
    for report in student_reports:
        for brief in report.get("question_briefs") or []:
            if not isinstance(brief, dict):
                continue
            label = _kp_label(brief).split("、")[0].strip()
            if label and label not in focuses:
                focuses.append(label)
            if len(focuses) >= 4:
                break
        if len(focuses) >= 4:
            break
    focus = "、".join(focuses) if focuses else "本次题目"
    lines = [
        "## 素养归属",
        f"这一步先看{focus}里要完成的那一层。下面只写谁更接近哪一档，不重复期望水准里的学、教、育。",
        "",
        "## 学情概览",
        f"{class_map.get('class_id')} 第{hw}次{subject_label}作业，共 {len(student_reports)} 名学生。"
        f"按本次需关注项粗分为："
        + "；".join(f"{k} {len(v)}人（{'、'.join(v[:4])}{'…' if len(v) > 4 else ''}）" for k, v in bands.items())
        + "。",
        "",
        "## 共性与个性",
    ]
    # 共性：多人同考查点
    from collections import Counter
    theme_counter: Counter = Counter()
    for r in student_reports:
        for t in _theme_tokens_from_points(r.get("points") or [], limit=4):
            theme_counter[t] += 1
    common = [t for t, n in theme_counter.most_common(5) if n >= 2]
    if common:
        lines.append(
            "- **班级共性考查点**："
            + "；".join(f"「{t}」({theme_counter[t]}人)" for t in common)
            + "。"
        )
    else:
        lines.append("- 本次尚未形成明显「多人同错」共性考查点，个性差异更大，宜个案对照。")
    for r in student_reports:
        name = r.get("display_name")
        band = _level_band(r.get("wrong_count"), r.get("uncertain_count"))
        themes = _theme_tokens_from_points(r.get("points") or [], limit=2)
        tip = "；".join(themes) if themes else "；".join((r.get("points") or [])[:2])
        lines.append(f"- **{name}**（{band}）：{tip or '详见该生报告'}")
    lines.extend(["", "## 前序次纵向变化"])
    if not longitudinal.get("has_prior"):
        lines.append(
            f"- 本次为可参照的首次/当前次序（第{hw}次）；尚无可靠前序班级信号。"
            "后续次第将在此基础上对照不同水平学生的变化。"
        )
    else:
        idxs = longitudinal.get("prior_homework_indexes") or []
        lines.append(f"- 对照前序次第：{('、'.join(str(i) for i in idxs) if idxs else '近次学生画像')}。")
        if longitudinal.get("improving"):
            lines.append(
                "- **进步倾向**："
                + "、".join(longitudinal["improving"][:6])
                + "——近次需关注项减少，宜巩固就近发展区，避免回潮。"
            )
        if longitudinal.get("slipping"):
            lines.append(
                "- **回落/新难点风险**："
                + "、".join(longitudinal["slipping"][:6])
                + "——区分知识问题固着、技能错误与执行疏漏（错别字/粗心不算盲区）。"
            )
        if longitudinal.get("stable_weak"):
            lines.append(
                "- **持续偏弱**："
                + "、".join(longitudinal["stable_weak"][:6])
                + "——优先排查是否同一考查点进入内耗区（时对时错）。"
            )
        for pack in (longitudinal.get("prior_class_highlights") or [])[-2:]:
            hs = pack.get("highlights") or []
            if hs:
                lines.append(
                    f"- 第{pack.get('homework_index')}次班级要点回顾："
                    + "；".join(str(h)[:70] for h in hs[:3])
                )
        # 代表性轨迹（不同水平各抽一点）
        by_band: Dict[str, List[Dict[str, Any]]] = {"把握较稳": [], "中等波动": [], "需重点关注": []}
        for tr in longitudinal.get("student_trajectories") or []:
            by_band.setdefault(str(tr.get("band_now") or ""), []).append(tr)
        for band_name in ("把握较稳", "中等波动", "需重点关注"):
            for tr in (by_band.get(band_name) or [])[:2]:
                rec = tr.get("recurring_themes") or []
                rec_txt = f"；反复出现：{'、'.join(rec)}" if rec else ""
                lines.append(
                    f"- **{tr.get('name')}**（{band_name}）：{tr.get('trend')}{rec_txt}。"
                )
        if not (longitudinal.get("improving") or longitudinal.get("slipping") or longitudinal.get("stable_weak")):
            lines.append("- 近次整体分层变化不剧烈；继续按共性考查点与个性轨迹分别跟进。")
    lines.extend([
        "",
        "## 认知分区建议（盲区·内耗区·就近发展区）",
        "### 盲区（认知盲区）",
        "- 对「持续不会」且非错别字/粗心算错的考查点，先补概念或关键步骤理解，再练。",
        "### 内耗区",
        "- 近几次同一考查点时对时错者，用变式小步练，减少无效重复刷题。",
        "### 就近发展区",
        "- 把握较稳者可带教邻近技能；中等波动者对准共性问题做对比讲解。",
        "",
        "## 配对与教学建议",
    ])
    steady = bands.get("把握较稳") or []
    weak = bands.get("需重点关注") or []
    mid = bands.get("中等波动") or []
    if steady and weak:
        lines.append(
            f"- 互助配对示例：{steady[0]}（较稳）↔ {weak[0]}（需关注），围绕共性考查点互讲题意与步骤，勿只报题号。"
        )
    if len(mid) >= 2:
        lines.append(f"- 对照配对示例：{mid[0]} ↔ {mid[1]}，比较同一考查点上的技能错误差异。")
    if not steady and not weak:
        lines.append("- 可按错因相近结对互查；已掌握者讲解具体考查内容与步骤。")
    lines.append("- 教学上先处理全班这一步上的共同差距，再看少数人的差别。")
    if degrade_note:
        lines.append(f"\n> 说明：模型生成暂降级（{degrade_note}），本段为规则增强兜底，请教师结合逐页图复核。")
    return "\n".join(lines)


def _ensure_expectation_first(markdown: str, expectation: str) -> str:
    text = str(markdown or "").lstrip()
    expect = str(expectation or "").strip()
    if not expect:
        return text
    if "期望" not in (expect.splitlines()[0] if expect else ""):
        expect = "## 本次期望水准\n" + expect
    text = re.sub(
        r"(?ms)^##[^\n]*期望[^\n]*\n.*?(?=^## |\Z)",
        "",
        text,
    ).lstrip()
    return expect.rstrip() + "\n\n" + text


def _loads_model_json_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _call_class_multi_json_step(
    prompt: str,
    *,
    step: str,
    system: str,
    max_tokens: int,
    timeout_s: float,
    min_chars: int,
    trace_dir: Optional[str],
    expect_key: str,
) -> Tuple[str, str, Dict[str, Any]]:
    """要 JSON 的那一步。原文留存；解析不到指定字段时再调用一次。"""
    text, tag = "", ""
    data: Dict[str, Any] = {}
    for attempt in (1, 2):
        text, tag = _call_class_multi_llm(
            prompt,
            system=system,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
            min_chars=min_chars,
            step=step if attempt == 1 else f"{step}_retry",
            trace_dir=trace_dir,
        )
        data = _loads_model_json_object(text)
        if expect_key in data and not str(tag).startswith("failed:"):
            return text, tag, data
        print(f"[class-multi] {step} 未得到可用 JSON，attempt={attempt}", flush=True)
        if attempt == 1:
            continue
    return text, tag, data


def _brief_verdict_bucket(verdict: Any) -> str:
    value = str(verdict or "").strip().lower()
    if value in ("wrong", "incorrect", "false", "错误"):
        return "wrong"
    if value in ("unanswered", "blank", "empty", "未作答"):
        return "unanswered"
    if value in ("partial", "部分正确"):
        return "partial"
    return ""


def _class_report_fact_sheet(student_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """用逐页判题汇总人数。检验时以这份为准，不再让模型重新估计。"""
    students: List[Dict[str, Any]] = []
    by_question: Dict[str, Dict[str, Any]] = {}
    for report in student_reports:
        name = str(report.get("display_name") or "").strip()
        if not name:
            continue
        buckets = {"wrong": [], "unanswered": [], "partial": []}
        for brief in report.get("question_briefs") or []:
            if not isinstance(brief, dict):
                continue
            kind = _brief_verdict_bucket(brief.get("verdict"))
            if not kind:
                continue
            qid = str(brief.get("qid") or brief.get("id") or "").strip() or "未编号"
            buckets[kind].append(qid)
            slot = by_question.setdefault(qid, {"wrong": [], "unanswered": [], "partial": [], "content": ""})
            slot[kind].append(name)
            if not slot["content"]:
                slot["content"] = str(brief.get("stem") or brief.get("parent_stem") or "")[:90]
        students.append({
            "name": name,
            "wrong_count": len(buckets["wrong"]),
            "unanswered_count": len(buckets["unanswered"]),
            "partial_count": len(buckets["partial"]),
            "wrong_questions": buckets["wrong"],
            "unanswered_questions": buckets["unanswered"],
            "partial_questions": buckets["partial"],
        })
    questions = [
        {
            "id": qid,
            "wrong_count": len(bucket["wrong"]),
            "wrong_students": bucket["wrong"],
            "unanswered_count": len(bucket["unanswered"]),
            "unanswered_students": bucket["unanswered"],
            "partial_count": len(bucket["partial"]),
            "partial_students": bucket["partial"],
            "content": bucket.get("content") or "",
        }
        for qid, bucket in sorted(by_question.items(), key=lambda item: item[0])
    ]
    return {"student_count": len(students), "students": students, "questions": questions}


def _apply_unique_replacements(
    markdown: str,
    replacements: List[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, str]], List[Dict[str, str]]]:
    text = markdown
    applied: List[Dict[str, str]] = []
    failed: List[Dict[str, str]] = []
    for item in replacements:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original") or "")
        replacement = str(item.get("replacement") or "")
        if not original or not replacement or original == replacement:
            continue
        count = text.count(original)
        if count == 1:
            text = text.replace(original, replacement, 1)
            applied.append({"original": original, "replacement": replacement})
        else:
            failed.append({
                "original": original,
                "replacement": replacement,
                "reason": "not_found" if count == 0 else "multiple",
            })
    return text, applied, failed


def _fact_question_rows(fact_sheet: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for question in fact_sheet.get("questions") or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get("id") or "").strip().replace("－", "-")
        if qid:
            rows[qid] = question
    return rows


def _mentioned_question_ids(text: str) -> List[str]:
    found = re.findall(r"题\s*([0-9]+(?:\s*[-－]\s*[0-9]+)?)", text or "")
    ids: List[str] = []
    for item in found:
        qid = re.sub(r"\s+", "", item).replace("－", "-")
        if qid not in ids:
            ids.append(qid)
    return ids


def _focus_subquestion(text: str, rows: Dict[str, Dict[str, Any]]) -> str:
    mentioned = [qid for qid in _mentioned_question_ids(text) if "-" in qid and qid in rows]
    if not mentioned:
        return ""
    for item in re.findall(r"尤其题\s*([0-9]+(?:\s*[-－]\s*[0-9]+)?)", text or ""):
        qid = re.sub(r"\s+", "", item).replace("－", "-")
        if qid in mentioned:
            return qid
    if len(mentioned) == 1:
        return mentioned[0]
    return ""


def _subquestion_merge_reason(
    markdown: str,
    original: str,
    replacement: str,
    fact_sheet: Dict[str, Any],
) -> str:
    """小题只准用自己那一行。把同一大题各小问的名单合并后写进其中一问，就退回。"""
    rows = _fact_question_rows(fact_sheet)
    before = ""
    idx = markdown.find(original) if original else -1
    if idx > 0:
        line_start = markdown.rfind("\n", 0, idx)
        prev_start = markdown.rfind("\n", 0, line_start) if line_start > 0 else 0
        before = markdown[max(0, prev_start):idx]
    focus = _focus_subquestion(before + original, rows) or _focus_subquestion(replacement, rows)
    if not focus or "-" not in focus:
        return ""
    parent = focus.rsplit("-", 1)[0]
    siblings = [qid for qid in rows if "-" in qid and qid.rsplit("-", 1)[0] == parent]
    if len(siblings) < 2:
        return ""
    if re.search(r"两问合计|两小问合计|各小问合计", replacement or ""):
        return ""
    named = set(_mentioned_question_ids(replacement))
    if len([qid for qid in siblings if qid in named]) >= 2:
        return ""
    own = int(rows[focus].get("wrong_count") or 0) + int(rows[focus].get("unanswered_count") or 0)
    merged_counts = set()
    for include_partial in (False, True):
        names: Set[str] = set()
        for qid in siblings:
            row = rows[qid]
            names.update(row.get("wrong_students") or [])
            names.update(row.get("unanswered_students") or [])
            if include_partial:
                names.update(row.get("partial_students") or [])
        if len(names) != own:
            merged_counts.add(len(names))
    for num in (int(item) for item in re.findall(r"(\d+)\s*人", replacement or "")):
        if num in merged_counts:
            return f"题{focus}这一行是{own}人，替换写成了{num}人，这是同一大题各小问合在一起的人数"
    return ""


def _keep_subquestion_replacements(
    markdown: str,
    replacements: List[Dict[str, Any]],
    fact_sheet: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, str]] = []
    for item in replacements:
        if not isinstance(item, dict):
            continue
        reason = _subquestion_merge_reason(
            markdown,
            str(item.get("original") or ""),
            str(item.get("replacement") or ""),
            fact_sheet,
        )
        if reason:
            rejected.append({
                "original": str(item.get("original") or ""),
                "replacement": str(item.get("replacement") or ""),
                "reason": reason,
            })
        else:
            kept.append(item)
    return kept, rejected


def _strip_report_fence(text: str) -> str:
    body = str(text or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:markdown|md)?\s*", "", body)
        body = re.sub(r"\s*```$", "", body).strip()
    return body


def _report_opening(text: str) -> str:
    for line in str(text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _strip_report_preamble(original: str, revised: str) -> str:
    """模型若先写核对过程，只保留从报告原文第一行到最后一行的正文。"""
    body = _strip_report_fence(revised)
    kept = [line.strip() for line in str(original or "").splitlines() if line.strip()]
    if not kept:
        return body.strip()
    opening = kept[0]
    closing = kept[-1]
    idx = body.find(opening)
    if idx > 0:
        body = body[idx:]
    end = body.rfind(closing)
    if end >= 0:
        body = body[:end + len(closing)]
    return body.strip()


def _report_block_kinds(markdown: str) -> List[str]:
    """卡片解析用的行类型。空行和分隔线不参与，标题必须单独成行且标题文字不变。"""
    kinds: List[str] = []
    for line in str(markdown or "").splitlines():
        s = line.strip()
        if not s or s == "---":
            continue
        if s.startswith("#### "):
            kinds.append("h4:" + s[5:].strip())
        elif s.startswith("### "):
            kinds.append("h3:" + s[4:].strip())
        elif s.startswith("## "):
            kinds.append("h2:" + s[3:].strip())
        elif s.startswith("# "):
            kinds.append("h1:" + s[2:].strip())
        elif re.match(r"^\d+[\.、]\s+", s):
            kinds.append("ol")
        elif s.startswith("- ") or s.startswith("* "):
            kinds.append("ul")
        else:
            kinds.append("p")
    return kinds


def _report_structure_reason(original: str, revised: str) -> str:
    """改后若卡片无法按原结构显示，返回原因；能显示则返回空串。"""
    body = _strip_report_fence(revised)
    if len(body) < max(200, int(len(original) * 0.75)):
        return "short"
    if _report_block_kinds(original) != _report_block_kinds(body):
        return "layout"
    if [title for title, _ in _split_md_sections(original)] != [title for title, _ in _split_md_sections(body)]:
        return "sections"
    orig_zones: List[str] = []
    new_zones: List[str] = []
    for title, section in _split_md_sections(original):
        if "认知分区" in title or ("盲区" in title and "内耗" in title):
            orig_zones.extend(re.findall(r"class='zone-card ([^']+)'", _zone_cards_from_section(section)))
    for title, section in _split_md_sections(body):
        if "认知分区" in title or ("盲区" in title and "内耗" in title):
            new_zones.extend(re.findall(r"class='zone-card ([^']+)'", _zone_cards_from_section(section)))
    if orig_zones != new_zones:
        return "zones"
    return ""


def _revise_class_report_facts(
    markdown: str,
    fact_sheet: Dict[str, Any],
    trace_dir: Optional[str] = None,
) -> Tuple[str, List[Dict[str, str]]]:
    """生成后一次改完：按口径和范围改差得明显的事实，其余逐行照抄。"""
    prompt = f"""下面是已经写好的班级报告，以及由程序从逐页判题算出的事实表。请直接改报告，并完整输出改后的整篇。以【班级报告】为底稿逐行抄写：没有事实问题的行，连标点、换行、空行都不要动。不要把标题和下一行并成一行，不要删空行，不要重排段落。

以「学：」「教：」「育：」「素养链：」「这一步：」「条目」「学科能力」「学科素养」「核心素养」开头的行，只要没有写错人数或名单，就原样保留，不要收成纯知识复述，也不要删掉这些分点。一句只有题号、去掉题号就不知道在说什么时，只用该题 content 里已有的说法补在题号前面。不要自造 content 里没有的概括名词。没有事实问题的句子不要为了补内容而改写。

先给每一句定口径，再定范围，然后决定改不改。三步都定了再动手。

口径只有三种，互不计入：
- 写错、失分、出错：只用该行 wrong_count、wrong_students。
- 空题、未作答：只用 unanswered_count、unanswered_students。
- 部分正确：只用 partial_count、partial_students。不要写成写错，也不要写成空题。
原文只说失分或出错时，不要改成「失分或空题」，不要把空题学生补进人数或名单。只有原文已经在说「失分或空题」「未做对」「含空题」时，人数才等于 wrong_count 加 unanswered_count，名单两边都写，并写明谁是空题。部分正确只有原文在说「未完全做对」时才加进去。

范围只有两种：
- 全题：合计、失分者有、多少人在这题出错、这一题全部失分。只写「受影响约N人」、而 N 与紧邻这一组的名单人数一致时，按分组处理，不要改成全题总数。
- 其中一组：这组、这类、盲区、内耗区、就近发展区、其余各题基本稳定、只错这一处，以及「见甲、乙等」「例如」这种举例。
分组句只核这一组自己的名单和自己写出的人数，不要改成全题总数。全题的数字改完以后，分组句保持原来的人数。两组人数不同可以同时留在文中。

什么情况下改人数：
- 用了「约」「大约」「左右」，和本口径、本范围只差 1 人，而且名单没有多出人或漏掉本口径的人：不改。先把范围定死再算差几人。不许改用更大的范围去凑一个只差 1 人的数，然后留下原文。
- 没有「约」「大约」「左右」，写出的是确定数字，和事实差 1 人：改成准确人数。
- 差 2 人及以上：改。改了就必须写成该口径的准确人数，不要写成另一个仍差 1 人的约数。失分就写成 wrong_count，不要顺手加上空题人数。
- 「失分者有甲、乙、丙，合计约N人」这种没有「等」「例如」「见」的，是完整名单。漏了本口径里的人时，即使只差 1 人并且用了约，也要补上这个人，人数改成准确人数。这是漏人，不是四舍五入。只补本口径的人：失分名单不补空题的人，空题名单不补写错的人。
- 有「等」「例如」「见」的是举例，不必把名单补全。点到的每个人必须属于这个口径，不属于的删掉。人数仍按上面的差数规则决定改不改。

同一句里的人数和完整名单要一起改，改完两边都等于事实。不要只改数字、留着旧名单，也不要只改名单、留着旧数字。

同一题、同一口径、同一范围在文中每出现一次，改了一处，其余各处都改成同一个准确数字。后文用的是另一个旧数字，也要改，不能只改第一处。分组句不要跟着全题的新数字改。改完通读：不能前面是新数字，后面仍是旧说法。

人的说法：
- 「全对」「N题全对」「全科全对」点到的每个人，wrong_count、unanswered_count、partial_count 都必须是 0。有空题、错题或部分正确的人从全对里分开，写明这个人错了哪几题、空了哪几题。原文下一句已经写了这个人有空题的，前一句也不能再把这个人算进全对，两句改到不再互相矛盾。不要因此给全班重分档位，不要改「达到（N人）」这种档位人数，除非这个人数就是用错误的全对人数加出来的。
- 一句用同一个数字说两个人或更多人：这几个人在这句话的口径上必须都等于这个数字。对不上就按人分开写各自的数。不要改成「以上」「左右」来含糊带过。原文说的是失分，这几个人的 wrong_count 相同，只是其中有人另外有空题：不改。
- 某人「N处失分」对这个人的 wrong_count；原文写明含空题时，再加上 unanswered_count。不要把另一人的题数写到这个人身上。
- 写错写成空题、空题写成写错、部分正确写成二者之一：改回正确归属，人数按新口径重算。
- 题号不要张冠李戴。某一问做对、另一问做错，不能写成两问都错。「两问都错」只包括两行名单里都有的人。「至少有一问未做对」才是两行名单的并集，而且原文必须是在把两问合起来说。

小题：带「-」的各算各的。不要把 8-1 和 8-2 的人数相加，相加会把两问都错的人算两次；也不要把两行名单合并、取并集后再写成其中一问的人数。原句没写题号时，看它紧上面的小标题。小标题或本句写了「尤其题8-2」，这一句只用 8-2 那一行，失分就用这一行的 wrong_count。不要先把 8-1 和 8-2 的人并成一个人数，再拿这个并集和原文比；并集就算和原文只差 1 人，也必须按 8-2 这一行改。

其余边界：全班人数等于 student_count，对的不改。「一半」「绝大多数」「少数人」只有和事实明显相反才改，差得不明显不改。同一个人前后被写成两个档位时，两处改成同一个档：错题、空题、部分正确都是 0，并且有一处写了达到，就用达到；有错题或空题却被写成全对的，改掉全对这句。不要给没有这种矛盾的人改档。不要新增题目段落，不要把每个学生再写成一段，不要增删标题。

对照例（按规则判断，不要把例子里的数字抄进报告）：
- 全题写错 15 人，另有 1 人空题。原文「约10人在这题出错（甲、乙等）」。差 5 人，人数改成 15。举例不必补成 15 人，但甲、乙必须在写错名单里。不要写成 16，不要把空题的人算进出错。
- 原文「失分者有甲、乙，合计约8人」，写错名单里还有丙，丁是空题。补上丙，人数改为写错人数。不要补丁。
- 原文「失分者有……合计约12人」，点名的人正好是全部写错的人，另有 1 人空题。不改，不要把空题的人加进去。
- 全题失分改成 26 人之后，后文另一句仍是这题全部失分、写着约22人。这句也改成 26。同题的分组句「这组学生……（约6人）」名单就是这 6 人，保持约6人。
- 「甲、乙、丙、丁。四人9题全对」，丁有空题。改成三人全对，丁写明空了哪几题。不要重分全班档位。
- 「两人均有6处失分」，两人写错都是 6 处，其中一人另外有空题。不改，不要写成「6处以上」。
- 小标题写着「尤其题8-2」，下一句是「失分者约若干人」。范围只能是 8-2 这一行的写错人数。不要改用两问名单的并集。并集就算和原文只差 1 人，也不能因此不改；和 8-2 的 wrong_count 差够 2 人，就改成这个 wrong_count。

输出前再对全文查一遍：该改的每处都已改成准确事实，同一范围的各处数字一致；不该改的约数、分组句、举例名单仍是原句。然后从报告第一行开始输出整篇，不要先写说明，不要索要正文。

【事实表】
{json.dumps(fact_sheet, ensure_ascii=False)}

【班级报告】
{markdown}
"""
    opening = _report_opening(markdown)
    last = ""
    fail_reason = ""
    for attempt in (1, 2):
        attempt_prompt = prompt
        if attempt == 2:
            if fail_reason in ("layout", "sections", "zones"):
                attempt_prompt += (
                    "\n上一次把标题和下一行粘在一起，或改动了章节结构，卡片无法按原来的布局显示。"
                    "这次每个标题必须单独占一行，章节顺序、小标题、列表行和空行都保持原样，只改事实有误的句子。\n"
                )
            else:
                attempt_prompt += (
                    "\n上一次没有从报告第一行写起，或没有输出完整报告。"
                    "这次不要写核对过程、清单或说明。输出的第一行必须与【班级报告】的第一行相同。\n"
                )
        text, tag = _call_class_multi_llm(
            attempt_prompt,
            system="你在改正文里的事实。先定口径和范围，不许改用更大的范围把差距凑成1人。约且只差1人、名单也没漏人，就不改。尤其题8-2只用8-2那一行。改人数时，同一句的完整名单和同一范围的其他句子一起改成准确数字。分组句不要改成全题总数。空题和写错互不计入。不要写核对过程，从报告第一行直接输出整篇。标题必须单独成行。",
            max_tokens=16000,
            timeout_s=600.0,
            min_chars=max(200, len(markdown) // 2),
            step="fact_fix" if attempt == 1 else "fact_fix_retry",
            trace_dir=trace_dir,
        )
        last = text
        body = _strip_report_preamble(markdown, text)
        starts = (not opening) or body.startswith(opening)
        fail_reason = "" if starts else "start"
        if starts and not str(tag).startswith("failed:"):
            fail_reason = _report_structure_reason(markdown, body)
        if not fail_reason and not str(tag).startswith("failed:"):
            changed = body != markdown
            print(
                f"[class-multi] 事实改写 {'有改动' if changed else '无需增改'} chars={len(body)}",
                flush=True,
            )
            note = "changed" if changed else "unchanged"
            return body, [{"status": note, "chars": str(len(body))}]
        if str(tag).startswith("failed:") and not fail_reason:
            fail_reason = "failed"
        print(f"[class-multi] 事实改写未采用 attempt={attempt} reason={fail_reason}", flush=True)
    print("[class-multi] 事实改写失败，保留原稿", flush=True)
    return markdown, [{"status": "failed", "reason": fail_reason or "failed", "chars": str(len(last or ""))}]


def build_class_assignment_report(
    *,
    class_map: Dict[str, Any],
    student_reports: List[Dict[str, Any]],
    subject_label: str,
    prior_class_reports: Optional[List[Dict[str, Any]]] = None,
    material_label: str = "",
    prior_student_histories: Optional[Dict[str, Any]] = None,
    class_expectation: str = "",
    trace_dir: Optional[str] = None,
) -> Dict[str, Any]:
    from .semantic_feedback_brief import competency_context_block, paper_situation

    rubric = load_rubric_guidance()
    context_block = competency_context_block(subject_label)
    hw = int(class_map.get("homework_index") or 1)
    longitudinal = build_class_longitudinal_digest(
        homework_index=hw,
        student_reports=student_reports,
        prior_class_reports=prior_class_reports,
        prior_student_histories=prior_student_histories,
    )
    situation = paper_situation(student_reports)
    by_student = situation.get("by_student") or {}
    payload = {
        "class_id": class_map.get("class_id"),
        "homework_index": hw,
        "subject": subject_label,
        "material": material_label,
        "student_count": len(student_reports),
        "paper": situation.get("questions") or [],
        "students": [
            {
                "name": r.get("display_name"),
                "index": r.get("student_index"),
                "band_line": next(
                    (
                        str(point).strip()[:180]
                        for point in (r.get("points") or [])
                        if str(point).strip().startswith("档位")
                    ),
                    "",
                ),
                "notable": list(r.get("notable") or by_student.get(str(r.get("student_index"))) or []),
                "wrong_count": r.get("wrong_count"),
                "uncertain_count": r.get("uncertain_count"),
                "sample_items": [
                    {
                        "qid": b.get("qid"),
                        "content": b.get("stem"),
                        "parent": b.get("parent_stem"),
                        "answer": b.get("student_answer"),
                        "figure": b.get("figure"),
                        "reading": b.get("reading"),
                        "page": b.get("page"),
                        "verdict": b.get("verdict"),
                        "error": b.get("error_type"),
                        "label_unchecked": b.get("knowledge_point"),
                    }
                    for b in (r.get("question_briefs") or [])
                    if isinstance(b, dict)
                ],
            }
            for r in student_reports
        ],
        "longitudinal_digest": longitudinal,
    }
    prompt = f"""你是一线教研向的班级作业诊断助手。请根据结构化证据写「班级本次作业批改报告」。

{context_block}

paper 是全班逐题的考查内容和人数。sample_items 里 content 是题干，answer 是该生写下的，figure 有图才有；没有 figure 时用 reading 里已写的图，都没有就不要编。label_unchecked 与 content 不一致时以 content 为准，不要用标签造一个新名称。
个人报告已经写过每人的这一步、素养链、画像和卷面。班级报告不要把那些分点再抄进来。档位以 band_line 为准；band_line 为空时，错题和空着都没有才写达到。

硬性要求：
1. 「## 本次期望水准」只写一行「见文首已锁定的期望水准」，不要重写这一步、学、教、育、家长和三档。程序会用已写好的全文替换这一节。
2. 「## 素养归属」不重写素养链。先用几十字写出全班在这一步上最集中的差距，再用达到、基本达到、尚未达到列出人名。三档人数之和等于 {len(student_reports)}。依据写卷面内容，题号放括号。不要再写条目、学科能力、学科素养、核心素养、画像能力、可观察行为。
3. 「## 学情概览」只写人数和档，不逐人复述。这 {len(student_reports)} 人都要归进档，不要把全班人数写成更少。同一人前后只有一个档。
4. 「## 共性与个性」写同一考查内容上多数人与少数人的差别。做错、空着、部分做对分开。多数人做对而个别人没有，写出来。先写内容，再括号题号。
5. 「## 前序次纵向变化」只用 longitudinal_digest 里近最多 3 次的变化。没有前序就只写「本次是可以参照的首次」，不要编以前的失分。
6. 「## 认知分区建议（盲区·内耗区·就近发展区）」三个分区各先用几十字说清，再分点。错别字、粗心不作盲区。内耗区是同一内容时对时错。就近发展区只写离这一步最近的一件事。
7. 「## 配对与教学建议」不要再写教和育，那两段已在期望水准。只写谁和谁对照同一步骤，对教师有什么用。
8. 每节先用几十字说清，再分点。不要为了完整把同一意思再写一遍。不要自造题干和课标里没有的概括名词。禁止写出四色、DMT、象限、共识区、温度计、螺旋、主体本体。
9. 输出 Markdown，只用 ## 。顺序为：本次期望水准 / 素养归属 / 学情概览 / 共性与个性 / 前序次纵向变化 / 认知分区建议（盲区·内耗区·就近发展区） / 配对与教学建议。
   各节正文用「- 」分点。不要输出单独成行的 ---。不要写「达到档」。
   认知分区的三个标题必须原样为：
   ### 盲区（认知盲区）
   ### 内耗区
   ### 就近发展区

【已写好的本次期望水准，不要改写，只供对照这一步】
{class_expectation or "（尚未单写。这一步按 paper 里的考查内容写，不要先列题号。）"}

【素养量规摘录，只作把概括写成可观察行为的方法，不要把它当成这次的题目】
{rubric[:1600]}

【结构化证据】
{json.dumps(payload, ensure_ascii=False)}
"""
    markdown, model_tag = _call_class_multi_llm(
        prompt,
        max_tokens=16000,
        timeout_s=600.0,
        step="class_report",
        trace_dir=trace_dir,
    )
    degrade = ""
    if not markdown or markdown.startswith("（班级报告生成暂降级") or model_tag.startswith("failed:"):
        degrade = (
            markdown.replace("（班级报告生成暂降级：", "").rstrip("）")
            if markdown and markdown.startswith("（班级报告生成暂降级")
            else (model_tag if model_tag.startswith("failed:") else "empty")
        )
        markdown = _ensure_expectation_first(
            _build_class_report_fallback(
                class_map=class_map,
                student_reports=student_reports,
                subject_label=subject_label,
                longitudinal=longitudinal,
                degrade_note=degrade,
            ),
            class_expectation,
        )
        model_tag = f"fallback:{model_tag}"
    elif "## 前序次纵向变化" not in markdown and "前序次纵向" not in markdown:
        # 模型漏写纵向段时，用规则段补上，避免有横向无纵向
        extra = _build_class_report_fallback(
            class_map=class_map,
            student_reports=student_reports,
            subject_label=subject_label,
            longitudinal=longitudinal,
        )
        m = re.search(r"## 前序次纵向变化\n[\s\S]*?(?=\n## |\Z)", extra)
        if m:
            markdown = markdown.rstrip() + "\n\n" + m.group(0).strip() + "\n"
    markdown = _ensure_expectation_first(markdown, class_expectation)
    fact_revisions: List[Dict[str, str]] = []
    if not str(model_tag).startswith("fallback"):
        markdown, fact_revisions = _revise_class_report_facts(
            markdown,
            _class_report_fact_sheet(student_reports),
            trace_dir=trace_dir,
        )
    highlights = _class_report_highlights_from_markdown(markdown, limit=8)
    return {
        "class_id": class_map.get("class_id"),
        "homework_index": hw,
        "subject_label": subject_label,
        "markdown": markdown,
        "summary": markdown[:500],
        "highlights": highlights,
        "longitudinal_digest": longitudinal,
        "fact_revisions": fact_revisions,
        "model": model_tag,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def notebook_class_memory_path(username: str) -> str:
    root = os.path.normpath(f"./received_dir/user_raw_file/{username}/.feedback_class_multi")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, "class_student_memories.json")


def load_notebook_class_memories(username: str) -> Dict[str, Any]:
    path = notebook_class_memory_path(username)
    if not os.path.isfile(path):
        return {}
    data = safe_json_load(path)
    return data if isinstance(data, dict) else {}


def update_student_memory_portraits(
    *,
    out_dir: str,
    class_map: Dict[str, Any],
    student_reports: List[Dict[str, Any]],
    subject: str,
    username: str = "",
) -> Dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "class_student_memories.json")
    shared = load_notebook_class_memories(username) if username else {}
    local = safe_json_load(path) if os.path.isfile(path) else {}
    store = shared if isinstance(shared, dict) and shared else (local if isinstance(local, dict) else {})
    subject_n = _normalize_subject_code(subject) or str(subject or "unknown").strip() or "unknown"
    key_cands = _subject_memory_key_candidates(class_map.get("class_id"), subject)
    key = key_cands[0] if key_cands else f"{class_map.get('class_id')}::{subject_n}"
    bucket = None
    for k in key_cands:
        if isinstance(store.get(k), dict):
            bucket = store.get(k)
            # 读到旧中文键时，后续写回规范 key
            key = key_cands[0]
            break
    if not isinstance(bucket, dict):
        bucket = {"students": {}}
    students = bucket.setdefault("students", {})
    hw = int(class_map.get("homework_index") or 1)
    for r in student_reports:
        sid = str(r.get("student_index"))
        cur = students.get(sid) if isinstance(students.get(sid), dict) else {
            "display_name": r.get("display_name"),
            "history": [],
        }
        cur["display_name"] = r.get("display_name")
        hist = [h for h in (cur.get("history") or []) if int(h.get("homework_index") or 0) != hw]
        hist.append({
            "homework_index": hw,
            "points": r.get("points") or [],
            "wrong_count": r.get("wrong_count"),
            "uncertain_count": r.get("uncertain_count"),
            "unit_total": r.get("unit_total"),
            "correct_count": r.get("correct_count"),
            "score": r.get("score"),
            "literacy_score": r.get("literacy_score"),
            "pages": r.get("pages"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        hist.sort(key=lambda x: int(x.get("homework_index") or 0))
        cur["history"] = hist
        cur["summary_points"] = (r.get("points") or [])[:5]
        students[sid] = cur
    bucket["students"] = students
    bucket["updated_at"] = datetime.now().isoformat(timespec="seconds")
    store[key] = bucket
    safe_json_dump(path, store)
    if username:
        safe_json_dump(notebook_class_memory_path(username), store)
    return store


def build_class_excerpt_card_markdown(
    *,
    filename: str,
    class_map: Dict[str, Any],
    student_reports: List[Dict[str, Any]],
    class_report: Dict[str, Any],
    material_label: str = "",
    pass1_dir: str = "",
    subject: str = "math",
    material_type: str = "homework",
    pages_per_card_page: int = 1,
) -> str:
    """多人解释精要卡正文：与 HTML 同信息源（总览/各生/班级/逐页留存），过长用 CARD_PAGE_BREAK 分页。"""
    from .excerpt_card_render import (
        CARD_PAGE_BREAK,
        _build_rich_overview,
        _collect_units,
        _format_question_block,
    )

    mtype = str(material_type or "homework")
    subj = str(subject or "math")
    report_by_sid = {
        str(r.get("student_index")): r
        for r in (student_reports or [])
        if isinstance(r, dict)
    }

    units: List[Dict[str, Any]] = []
    pages_meta: List[Dict[str, Any]] = []
    if pass1_dir and os.path.isdir(pass1_dir):
        try:
            units, pages_meta = _collect_units(
                pass1_dir, subj, {}, material_type=mtype,
            )
        except Exception:
            units, pages_meta = [], []
    page_by_num = {
        int(p.get("page") or 0): p for p in pages_meta if isinstance(p, dict)
    }

    head_lines = [
        "# 班级多人批改·解释精要",
        "",
        f"- 材料：{filename}",
        f"- 画像：{material_label or '（见材料设置）'}",
        f"- 班级：{class_map.get('class_id')}；人数：{class_map.get('student_count')}；"
        f"第{class_map.get('homework_index')}次作业；每生{class_map.get('pages_per_assignment')}页",
        "",
        "## 页码索引（按学生）",
        "",
    ]
    for stu in class_map.get("students") or []:
        if not isinstance(stu, dict):
            continue
        pages = "、".join(str(p) for p in (stu.get("pages") or []))
        head_lines.append(
            f"- **{stu.get('display_name')}**：第{pages}页（详见下方该生报告与逐页留存）"
        )
    overview = _build_rich_overview(units, subj, material_type=mtype) if units else ""
    page1_parts = ["\n".join(head_lines).rstrip()]
    if overview:
        page1_parts.append(overview.strip())
    page1_parts.append(
        "\n".join(
            [
                "",
                "> 图表化总览、交叉比例条、核验芯片见本卡 HTML；此处为同口径文字版，便于卡片内通读与分页。",
            ]
        ).strip()
    )

    stu_lines = ["## 各学生本次作业批改报告", ""]
    for stu in class_map.get("students") or []:
        if not isinstance(stu, dict):
            continue
        sid = stu.get("student_index")
        name = str(stu.get("display_name") or f"学生{sid}")
        pages_label = "、".join(str(p) for p in (stu.get("pages") or [])) or "—"
        r = report_by_sid.get(str(sid)) or {}
        briefs = r.get("question_briefs") or []
        tally = _brief_tally(briefs)
        if tally["total"]:
            ok_n, wrong_n, unc_n, blank_n, total_n = (
                tally["ok"], tally["weak"], tally["unc"], tally["blank"], tally["total"],
            )
        else:
            ok_n = wrong_n = unc_n = total_n = "—"
            blank_n = 0
        stu_lines.append(f"### {name}（序位{sid} · 第{pages_label}页）")
        expect = str(r.get("expectation") or "").strip()
        if expect:
            stu_lines.append("")
            stu_lines.append("**本次期望水准**")
            stu_lines.append("")
            stu_lines.append(expect)
            stu_lines.append("")
        blank_bit = f"；未作答 {blank_n}" if blank_n else ""
        stu_lines.append(f"- 把握较稳 {ok_n}/{total_n}；需关注 {wrong_n}；待核验 {unc_n}{blank_bit}")
        for p in r.get("points") or []:
            if str(p).strip():
                stu_lines.append(f"- {p}")
        stu_lines.append("")
    if len(stu_lines) <= 2:
        for r in student_reports or []:
            if not isinstance(r, dict):
                continue
            stu_lines.append(
                f"### {r.get('display_name')}（学生{r.get('student_index')}）"
            )
            for p in r.get("points") or []:
                stu_lines.append(f"- {p}")
            stu_lines.append("")

    class_md = (
        class_report.get("markdown")
        or class_report.get("summary")
        or "（班级报告缺失）"
    )
    class_page = "\n".join(
        [
            "## 班级本次作业批改报告",
            "",
            str(class_md).strip(),
            "",
            "## 人机交互核验",
            "",
            "请对照逐页批改图与本卡 HTML 核验灰/黑与关键判断；核验确认后可迭代更新本卡与相关报告、学生记忆画像。",
            "",
            # 元数据注释：勿写成 nkcn_grading_card:批改·解释精要|…，以免与钉卡 analysis_id|run_id 混淆
            f"<!--nkcn_class_multi_meta:{class_map.get('class_id')}|hw{class_map.get('homework_index')}-->",
        ]
    ).strip()

    page_chunks: List[str] = []
    students = [s for s in (class_map.get("students") or []) if isinstance(s, dict)]
    if not students and pages_meta:
        # 无名单时退化为按材料页
        note = f"共 {len(pages_meta)} 页"
        page_chunks.append(f"## 逐页留存（{note}）")
        for meta in pages_meta:
            block = [
                f"### 第 {meta.get('page')} 页"
                + (f" · {meta['header']}" if meta.get("header") else ""),
                "",
                f"- 本页置信：版面 {meta.get('layout_line')}；理解 {meta.get('understanding_line')}；批改 {meta.get('grading_line')}",
                "",
            ]
            for unit in meta.get("units") or []:
                block.append(_format_question_block(unit))
            page_chunks.append("\n".join(block).rstrip() + "\n")
    else:
        for stu in students:
            sid = stu.get("student_index")
            name = str(stu.get("display_name") or f"学生{sid}")
            pages = [int(p) for p in (stu.get("pages") or [])]
            pages_label = "、".join(str(p) for p in pages) or "—"
            stu_header = f"## 逐页留存 · {name}（第{pages_label}页）"
            content_blocks: List[str] = []
            for pn in pages:
                meta = page_by_num.get(pn)
                if not meta:
                    content_blocks.append(
                        f"### 第 {pn} 页\n\n- （暂无该页单元数据，请对照批改图）\n"
                    )
                    continue
                block = [
                    f"### 第 {meta.get('page')} 页"
                    + (f" · {meta['header']}" if meta.get("header") else ""),
                    "",
                    f"- 本页置信：版面 {meta.get('layout_line')}；理解 {meta.get('understanding_line')}；批改 {meta.get('grading_line')}",
                    "",
                ]
                units_in = meta.get("units") or []
                if not units_in:
                    block.append("- （本页未切出教学单元）")
                    block.append("")
                else:
                    for unit in units_in:
                        block.append(_format_question_block(unit))
                content_blocks.append("\n".join(block).rstrip() + "\n")
            if not content_blocks:
                page_chunks.append(stu_header + "\n\n- 暂无该生页数据\n")
            else:
                step = max(1, int(pages_per_card_page or 1))
                for i in range(0, len(content_blocks), step):
                    group = content_blocks[i : i + step]
                    if i == 0:
                        page_chunks.append(
                            (stu_header + "\n\n" + "\n\n".join(group)).strip()
                        )
                    else:
                        page_chunks.append("\n\n".join(group).strip())

    card_pages = [
        "\n\n".join(page1_parts).strip(),
        "\n".join(stu_lines).strip(),
        class_page,
    ]
    card_pages.extend(page_chunks)
    return CARD_PAGE_BREAK.join(p for p in card_pages if p)


def _report_point_class(text: str) -> str:
    """给分点加上可扫读的样式类。基本达到要先于达到判断。"""
    t = str(text or "").strip().lstrip("-* ").strip()
    if t.startswith("尚未达到"):
        return "band band-low"
    if t.startswith("基本达到"):
        return "band band-mid"
    if t.startswith("达到"):
        return "band band-ok"
    if t.startswith("学：") or t.startswith("学:"):
        return "triad triad-learn"
    if t.startswith("教：") or t.startswith("教:"):
        return "triad triad-teach"
    if t.startswith("育：") or t.startswith("育:"):
        return "triad triad-grow"
    if t.startswith("素养链") or t.startswith("条目"):
        return "chain chain-1"
    if t.startswith("学科能力"):
        return "chain chain-2"
    if t.startswith("学科素养"):
        return "chain chain-3"
    if t.startswith("核心素养"):
        return "chain chain-4"
    if t.startswith("综合交叉") or t.startswith("内容联系"):
        return "chain chain-x"
    if t.startswith("档位"):
        return "band band-mid"
    if t.startswith("下一步"):
        return "triad triad-learn"
    return ""


def _xml_text(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _plain_piece(text: str) -> str:
    raw = re.sub(r"`+", "", str(text or ""))
    raw = re.sub(r"\*{2,}", "", raw)
    return re.sub(r"\s+", " ", raw).strip(" ：:　")


def _clip_evidence(text: str, limit: int = 72) -> str:
    raw = _plain_piece(text)
    if len(raw) <= limit:
        return raw
    cut = raw[:limit]
    for mark in ("。", "；", "，", "、"):
        pos = cut.rfind(mark)
        if pos >= int(limit * 0.55):
            return cut[:pos + 1]
    return cut.rstrip() + "…"


def _rank_from_line(line: str) -> int:
    """1 尚未达到，2 基本达到，3 达到。定义句和没写档的句子返回 0。"""
    text = str(line or "")
    if "尚未达到" in text:
        return 1
    if "基本达到" in text:
        return 2
    if "达到" in text:
        return 3
    return 0


_ABILITY_WORDS = (
    "运算能力", "推理意识", "推理能力", "语言运用", "语言能力",
    "数感", "量感", "符号意识", "几何直观", "空间观念", "创新意识",
    "数据意识", "数据观念", "模型意识", "模型观念", "应用意识",
    "阅读与鉴赏", "表达与交流", "梳理与探究", "识字与写字",
    "思维品质", "学习能力", "文化意识", "文化自信", "审美创造", "思维能力",
)
_RANK_LABEL = {1: "尚未达到", 2: "基本达到", 3: "达到"}


def _looks_from_points(points: Sequence[str]) -> List[Tuple[str, int, str]]:
    """从已经写好的分点里抽出这次证据够得着的分项。抽不出就不编。"""
    lines = [str(p).strip() for p in points if str(p).strip()]
    blob = "\n".join(lines)
    found: List[Tuple[str, int, str]] = []

    band = next((line for line in lines if line.startswith("档位")), "")
    rank = _rank_from_line(band)
    if rank:
        found.append(("知识是否正确", rank, _clip_evidence(band)))

    chain = next((line for line in lines if line.startswith("素养链")), "")
    ability_unclear = bool(re.search(r"(能力|它).{0,12}(说不清|对不上)|说不清.{0,8}能力", chain))
    if chain and ability_unclear:
        found.append(("能力是否明确", 1, _clip_evidence(chain)))
    elif chain and any(word in chain for word in _ABILITY_WORDS):
        if "能说出" in blob:
            level = 3
        elif rank:
            level = rank
        else:
            level = 2
        found.append(("能力是否明确", level, _clip_evidence(chain)))

    if re.search(r"一变就断|换个问法就断|一换就断|问法一变就", blob):
        evidence = next((line for line in lines if re.search(r"一变就断|换个|问法", line)), blob)
        found.append(("能否迁移", 1, _clip_evidence(evidence)))
    elif re.search(r"换个相近|还站得住|还做得成|还能用", blob):
        evidence = next(
            (line for line in lines if re.search(r"换个相近|还站得住|还做得成|还能用", line)),
            "",
        )
        if evidence and not evidence.startswith("达到"):
            found.append(("能否迁移", 3, _clip_evidence(evidence)))

    observed = [
        line for line in lines
        if re.search(r"自己写|独立完成|只等|听讲|动手", line) and not line.startswith("下一步")
    ]
    nxt = next((line for line in lines if line.startswith("下一步")), "")
    if observed:
        text = observed[0]
        if re.search(r"只等|没有自己|没自己", text):
            level = 1
        elif re.search(r"已经|独立完成|自己写完", text):
            level = 3
        else:
            level = 2
        found.append(("学习方式", level, _clip_evidence(text)))
    elif re.search(r"先自己|自己把", nxt):
        found.append(("学习方式", 1, _clip_evidence(nxt)))

    cross = next((line for line in lines if re.search(r"交叉|同一件事|铰", line)), "")
    if cross:
        if re.search(r"尚未|没有|看不出|未形成", cross):
            found.append(("内容联系", 1, _clip_evidence(cross)))
        elif re.search(r"同一件事|铰", cross):
            found.append(("内容联系", 3, _clip_evidence(cross)))
        else:
            found.append(("内容联系", 2, _clip_evidence(cross)))

    grow = next((line for line in lines if line.startswith("育")), "")
    change_text = grow or (chain if "人的变化" in chain else "")
    if change_text and re.search(r"说不清|停在|先不谈|先不往下|还只是", change_text):
        found.append(("人的变化", 1, _clip_evidence(change_text)))
    elif change_text:
        found.append(("人的变化", 2, _clip_evidence(change_text)))

    seen = set()
    out: List[Tuple[str, int, str]] = []
    for name, level, evidence in found:
        if name in seen or level not in (1, 2, 3):
            continue
        seen.add(name)
        out.append((name, level, evidence))
    return out


def _looks_from_judgment(text: str) -> List[Tuple[str, int, str]]:
    """单人诊断用三问里的判断，不用前面那几条水准定义。"""
    raw = str(text or "").strip()
    if not raw:
        return []
    points: List[str] = []
    for piece in re.split(r"[\n]+", raw):
        line = piece.strip().lstrip("-* ").strip()
        if not line:
            continue
        if line.startswith("档位") or line.startswith("素养链") or line.startswith("下一步") or line.startswith("育"):
            points.append(line)
            continue
        if _rank_from_line(line) or any(word in line for word in _ABILITY_WORDS) or re.search(r"交叉|同一件事|铰|自己|问法", line):
            if _rank_from_line(line) and not line.startswith("档位"):
                points.append("档位：" + line)
            elif "学科能力" in line or any(word in line for word in _ABILITY_WORDS):
                points.append(line if line.startswith("素养链") else "素养链：" + line)
            else:
                points.append(line)
    return _looks_from_points(points)


def _split_chain(text: str) -> List[Tuple[str, str]]:
    raw = _plain_piece(re.sub(r"^素养链[：:]\s*", "", str(text or "").strip()))
    if "→" not in raw and "->" not in raw:
        return []
    labels = (
        ("条目", ("条目",)),
        ("学科能力", ("学科能力",)),
        ("学科素养", ("学科素养",)),
        ("人的变化", ("人的变化", "核心素养", "人的核心素养")),
    )
    steps: List[Tuple[str, str]] = []
    for part in re.split(r"\s*(?:→|->)\s*", raw):
        part = part.strip(" 。")
        if not part:
            continue
        label, body = "环节", part
        for name, keys in labels:
            hit = next((key for key in keys if part.startswith(key)), "")
            if hit:
                label = name
                body = re.sub(rf"^{re.escape(hit)}[是为：:\s]*", "", part).strip()
                break
        if "人的变化" in body and not body.startswith("人的变化"):
            before, after = body.split("人的变化", 1)
            before = before.strip(" 。；;")
            after = after.strip(" ：:，,。")
            if before:
                steps.append((label, _clip_evidence(before, 140)))
            if after:
                steps.append(("人的变化", _clip_evidence(after, 140)))
            continue
        if body:
            steps.append((label, _clip_evidence(body, 140)))
    return steps


def _chain_figure_from_md(body: str) -> str:
    """素养归属小图。标题单独成行时，把后面的正文接上，不把标题再抄一遍。"""
    heads = (
        ("条目", ("条目",)),
        ("学科能力", ("学科能力",)),
        ("学科素养", ("学科素养",)),
        ("人的变化", ("人的核心素养", "核心素养", "人的变化")),
        ("内容联系", ("内容联系", "综合交叉")),
    )
    bare = {
        "条目", "学科能力", "学科素养", "核心素养", "人的核心素养",
        "人的变化", "内容联系", "综合交叉",
    }

    def _open(text: str) -> Tuple[str, str]:
        for name, keys in heads:
            for key in sorted(keys, key=len, reverse=True):
                if text.startswith(key):
                    rest = re.sub(rf"^{re.escape(key)}[是为：:\s]*", "", text).strip(" ：:。")
                    return name, rest
        return "", ""

    def _usable(rest: str) -> str:
        rest = (rest or "").strip(" ：:。")
        if not rest or rest in bare or re.search(r"不另造|不要把|全部抄", rest):
            return ""
        return rest

    order: List[str] = []
    bag: Dict[str, List[str]] = {}
    current = ""
    for line in str(body or "").splitlines():
        text = _plain_piece(re.sub(r"^[-•*]\s*", "", line.strip()))
        if not text or re.fullmatch(r"[-_*]{3,}", text):
            continue
        if text.startswith("画像") or text.startswith("可观察行为"):
            current = ""
            continue
        name, rest = _open(text)
        if name:
            current = name
            if name not in bag:
                bag[name] = []
                order.append(name)
            piece = _usable(rest)
            if piece:
                bag[name].append(piece)
            continue
        if current:
            piece = _usable(text)
            if piece:
                bag[current].append(piece)
    steps: List[Tuple[str, str]] = []
    cross = ""
    for name in order:
        chunks = bag.get(name) or []
        value = ""
        for piece in chunks:
            value += piece if piece.endswith(("。", "；", "，")) else piece + "。"
        value = _clip_evidence(value.strip("。"), 220)
        if not _usable(value):
            continue
        if name == "内容联系":
            cross = value
        else:
            steps.append((name, value))
    return _chain_html(steps, cross)


def _chain_html(steps: Sequence[Tuple[str, str]], cross: str = "") -> str:
    if len(steps) < 2:
        return ""
    bits = []
    for index, (label, value) in enumerate(steps):
        if index:
            bits.append("<span class='chain-arrow'>→</span>")
        bits.append(
            f"<div class='chain-step s{index + 1}'><b>{_xml_text(label)}</b><span>{_xml_text(value)}</span></div>"
        )
    note = ""
    if cross:
        note = f"<p class='chain-cross'>内容联系：{_xml_text(_clip_evidence(cross, 120))}</p>"
    return f"<div class='chain-fig'>{''.join(bits)}</div>{note}"


def _literacy_base(level: int) -> float:
    """三档落到 5 分制上的素养分。报告里写了明确分数时，以那个数为准。"""
    return {1: 2.2, 2: 3.6, 3: 4.6}.get(int(level or 2), 3.6)


def _level_of_score(score: float) -> int:
    if score < 3.0:
        return 1
    if score < 4.2:
        return 2
    return 3


def _text_span(text: str, font: int) -> float:
    width = 0.0
    for ch in text:
        if ch == " ":
            width += font * 0.35
        elif ord(ch) > 127:
            width += font * 1.08
        else:
            width += font * 0.62
    return width


def _radar_svg(items: Sequence[Tuple[str, int, Any]]) -> str:
    """三项及以上用雷达。半径按该项素养分（满分 5）。"""
    if len(items) < 3:
        return ""
    import math

    n = len(items)
    if n <= 6:
        cx, cy = 210, 148
        outer = 92
        label_r = 132
        font = 12
        stagger = 0
    else:
        cx, cy = 320, 230
        outer = 110
        label_r = 148
        font = 11
        stagger = 24
    rings = tuple(outer * step / 5 for step in (1, 2, 3, 4, 5))

    def point(index: int, radius: float) -> Tuple[float, float]:
        angle = -math.pi / 2 + 2 * math.pi * index / n
        return cx + radius * math.cos(angle), cy + radius * math.sin(angle)

    ring_shapes = []
    for radius in rings:
        coords = " ".join(f"{point(i, radius)[0]:.1f},{point(i, radius)[1]:.1f}" for i in range(n))
        ring_shapes.append(f"<polygon points='{coords}' class='radar-ring'/>")
    spokes = []
    labels = []
    data = []
    marks: List[float] = []
    extents: List[Tuple[float, float, float, float]] = []
    for index, (name, level, extra) in enumerate(items):
        score = float(extra) if isinstance(extra, (int, float)) else _literacy_base(int(level))
        score = min(5.0, max(1.0, score))
        marks.append(score)
        x, y = point(index, rings[-1])
        spokes.append(f"<line x1='{cx}' y1='{cy}' x2='{x:.1f}' y2='{y:.1f}' class='radar-spoke'/>")
        lx, ly = point(index, label_r + (stagger if index % 2 else 0))
        anchor = "middle"
        if lx < cx - 20:
            anchor = "end"
        elif lx > cx + 20:
            anchor = "start"
        labels.append(
            f"<text x='{lx:.1f}' y='{ly:.1f}' text-anchor='{anchor}' "
            f"class='radar-label lv-{level}' style='font-size:{font}px'>"
            f"{_xml_text(name)} {score:.1f}</text>"
        )
        text = f"{name} {score:.1f}"
        span = _text_span(text, font)
        if anchor == "end":
            extents.append((lx - span, lx, ly - font, ly + 4))
        elif anchor == "start":
            extents.append((lx, lx + span, ly - font, ly + 4))
        else:
            extents.append((lx - span / 2, lx + span / 2, ly - font, ly + 4))
        dx, dy = point(index, outer * score / 5.0)
        data.append(f"{dx:.1f},{dy:.1f}")
    average = round(sum(marks) / len(marks), 1) if marks else 0
    score_span = _text_span(f"{average:.1f}", 18)
    extents.append((cx - score_span / 2, cx + score_span / 2, cy + 5 - 18, cy + 8))
    extents.append((cx - outer, cx + outer, cy - outer, cy + outer))
    pad = 16
    min_x = min(item[0] for item in extents) - pad
    max_x = max(item[1] for item in extents) + pad
    min_y = min(item[2] for item in extents) - pad
    max_y = max(item[3] for item in extents) + pad
    return (
        f"<svg class='radar' viewBox='{min_x:.1f} {min_y:.1f} {max_x - min_x:.1f} {max_y - min_y:.1f}' "
        f"role='img' aria-label='素养得分'>"
        + "".join(ring_shapes)
        + "".join(spokes)
        + f"<polygon points='{' '.join(data)}' class='radar-shape'/>"
        + "".join(labels)
        + f"<text x='{cx}' y='{cy + 5}' text-anchor='middle' class='radar-score'>{average:.1f}</text>"
        + "</svg>"
        + "<div class='radar-legend'>满分 5 · 中心是这次这些能力的平均素养得分</div>"
    )


def _meters_html(items: Sequence[Tuple[str, int, Any]]) -> str:
    rows = []
    for name, level, extra in items:
        if isinstance(extra, (int, float)):
            score = min(5.0, max(1.0, float(extra)))
            width = max(8, round(100 * score / 5))
            label = f"{score:.1f}/5"
        else:
            width = {1: 34, 2: 66, 3: 100}[level]
            label = _RANK_LABEL[level]
        rows.append(
            f"<div class='look-meter'><span class='look-name'>{_xml_text(name)}</span>"
            f"<span class='look-track'><i class='lv-{level}' style='width:{width}%'></i></span>"
            f"<span class='look-lv'>{label}</span></div>"
        )
    return "".join(rows)


# 19项是正式能力，36项是其下可观察行为。只有正文写出正式能力名，或在该能力后的括号里写明行为时，才纳入图表。
_PORTRAIT: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("问题解决能力", ("发现问题", "分析问题", "提出问题", "设计方案", "评估方案")),
    ("学习动力与自我调节能力", ("设定目标", "情绪识别", "反馈")),
    ("自主学习能力", ("制定学习计划", "自我修订")),
    ("实践与劳动能力", ("劳动认知", "原型设计与试验")),
    ("团队协作能力", ("团队目标和角色", "团队效能")),
    ("创新设计能力", ("设计方案", "原型设计与试验")),
    ("科学理解能力", ("物质与结构认知", "规则")),
    ("系统思考能力", ("系统性思考反思迁移", "联系生活实际")),
    ("反思改进能力", ("反思能力", "自我修订")),
    ("信息处理能力", ("选择相关原始资料", "综合多种原始资料")),
    ("证据分析与判断能力", ("证据选择", "构建解释", "收集证据")),
    ("数理思考能力", ("创造模型", "建立与运用模型", "估算结论")),
    ("审美与艺术创造能力", ("艺术鉴赏", "艺术创作")),
    ("社会责任与公共参与能力", ("规则",)),
    ("表达沟通能力", ("表达媒介", "用词选择与积极沟通", "口头表达与朗读背诵", "信息性与解释性文本创作")),
    ("文化理解与交流能力", ("主题与中心思想",)),
    ("探究研究能力", ("提出问题", "发现问题")),
    ("数据分析能力", ("数据", "数据整理分析与应用")),
    ("健康与运动能力", ("情绪识别",)),
)
_LINKS: Tuple[Tuple[Tuple[str, ...], str, Tuple[str, ...]], ...] = (
    (("运算能力", "数感", "量感", "符号意识", "推理意识", "推理能力", "几何直观", "空间观念"),
     "数理思考能力", ("估算结论", "分析问题", "建立与运用模型")),
    (("数据意识", "数据观念", "数据分析"), "数据分析能力", ("数据", "数据整理分析与应用")),
    (("模型意识", "模型观念"), "数理思考能力", ("建立与运用模型", "创造模型")),
    (("应用意识",), "系统思考能力", ("联系生活实际", "系统性思考反思迁移")),
    (("语言运用", "表达与交流", "识字与写字"), "表达沟通能力", ("用词选择与积极沟通", "口头表达与朗读背诵")),
    (("阅读与鉴赏", "梳理与探究", "语篇", "整本书"), "信息处理能力", ("选择相关原始资料", "主题与中心思想")),
    (("文化自信", "文化意识"), "文化理解与交流能力", ("主题与中心思想",)),
    (("审美创造",), "审美与艺术创造能力", ("艺术鉴赏", "艺术创作")),
)


def _line_level(line: str, default_level: int) -> int:
    if "尚未达到" in line and "基本达到" not in line:
        return 1
    if re.search(r"站不住|一变就断|先不谈|先不往下", line):
        return 1
    if default_level == 1:
        return 1
    if re.search(r"能说出|还站得住|还做得成|同一件事", line):
        return 3
    return default_level or 2


def _collect_portrait(lines: Sequence[str], default_level: int) -> Dict[str, Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}

    def add(ability: str, behaviors: Sequence[str], level: int) -> None:
        slot = found.setdefault(ability, {"level": level, "behaviors": []})
        if level == 1 or (slot["level"] != 1 and level == 3):
            slot["level"] = level
        owned = slot["behaviors"]
        for behavior in behaviors:
            if behavior and behavior not in owned and len(owned) < 4:
                owned.append(behavior)

    official = {ability for ability, _behaviors in _PORTRAIT}
    for raw in lines:
        line = str(raw or "").strip()
        if not line:
            continue
        level = _line_level(line, default_level)
        explicit = set()
        for match in re.finditer(
            r"([^\s；;，,：:（）()]{2,16})(?:\s*[1-5](?:\.\d)?)?（([^）]+)）",
            line,
        ):
            ability = match.group(1)
            if ability not in official:
                continue
            behaviors = [part.strip() for part in re.split(r"[、,，]", match.group(2)) if part.strip()]
            explicit.update(behaviors)
            add(ability, behaviors, level)
        for ability, _behaviors in _PORTRAIT:
            if ability in line:
                add(ability, [], level)
    return found


def _explicit_literacy(lines: Sequence[str]) -> Dict[str, float]:
    """能力名后面紧跟的 1–5 分，例如「数理思考能力 3.6」。"""
    marks: Dict[str, float] = {}
    names = [ability for ability, _behaviors in _PORTRAIT]
    for line in lines:
        for name in names:
            match = re.search(
                re.escape(name) + r"\s*([1-5](?:\.\d)?)\s*(?:/\s*5(?:\.0)?)?",
                line,
            )
            if not match:
                continue
            marks[name] = round(min(5.0, max(1.0, float(match.group(1)))), 1)
    return marks


def _literacy_from_points(points: Sequence[Any]) -> Optional[Dict[str, Any]]:
    """这次的素养分：每项能力一个 5 分制分数，再取这些项的平均。没有对上的能力就不编分。"""
    lines = [str(point).strip() for point in points if str(point).strip()]
    if not lines:
        return None
    band = next((line for line in lines if line.startswith("档位")), "")
    default_level = _rank_from_line(band) or 2
    found = _collect_portrait(lines, default_level)
    if not found:
        return None
    written = _explicit_literacy(lines)
    marks: List[float] = []
    for name, slot in found.items():
        score = written.get(name, _literacy_base(int(slot["level"])))
        slot["score"] = score
        marks.append(score)
    return {"score": round(sum(marks) / len(marks), 1), "abilities": found}


def _ability_evidence(name: str, lines: Sequence[str]) -> str:
    """取出只属于这一项能力的那一句，避免两项共用同一段开头。"""
    official = [ability for ability, _behaviors in _PORTRAIT]
    pieces: List[str] = []
    for line in lines:
        if name not in line:
            continue
        for chunk in re.split(r"[。；;]", str(line)):
            if name not in chunk:
                continue
            cut = chunk
            name_at = cut.find(name)
            for other in official:
                if other == name or other not in cut:
                    continue
                pos = cut.find(other)
                if pos > name_at:
                    cut = cut[:pos]
                    name_at = cut.find(name)
            cut = re.sub(r"^.*?(?:画像|画像能力|可观察行为)[：:]\s*", "", cut)
            cut = cut.strip(" ：:，,、")
            if cut and cut not in pieces:
                pieces.append(cut)
    if not pieces:
        return ""
    return _clip_evidence("；".join(pieces), 140)


def _portrait_charts_html(found: Dict[str, Dict[str, Any]], lines: Sequence[str] = ()) -> str:
    if not found:
        return ""
    abilities = [
        (name, int(slot["level"]), float(slot.get("score") or _literacy_base(int(slot["level"]))))
        for name, slot in found.items()
    ]
    radar = _radar_svg(abilities)
    bars = f"<div class='look-meters'>{_meters_html(abilities)}</div>"
    judgments = []
    texts = [str(line).strip() for line in lines if str(line).strip()]
    for name, _level, score in abilities:
        seen = _ability_evidence(name, texts)
        judgments.append(
            f"<tr><td>{_xml_text(name)}</td><td>{score:.1f}/5</td><td>{_xml_text(seen or '报告未写出这一项的题目依据')}</td></tr>"
        )
    table = (
        "<table class='lite'><tr><th>素养</th><th>得分</th><th>本次依据</th></tr>"
        + "".join(judgments)
        + "</table>"
    )
    ability_body = (
        f"<div class='look-grid'><div>{bars}{table}</div><div class='radar-wrap'>{radar}</div></div>"
        if radar else f"{bars}{table}"
    )
    groups = []
    for name, slot in found.items():
        behaviors = [(behavior, int(slot["level"]), "") for behavior in slot["behaviors"]]
        if not behaviors:
            continue
        seen = _ability_evidence(name, texts)
        groups.append(
            f"<div class='beh-group'><b>{_xml_text(name)}</b>"
            + (f"<p class='look-note'>{_xml_text(seen)}</p>" if seen else "")
            + f"<div class='look-meters'>{_meters_html(behaviors)}</div></div>"
        )
    behavior_html = (
        "<div class='fig-block'><div class='fig-cap'>可观察行为</div>"
        + "".join(groups)
        + "</div>"
    ) if groups else ""
    return (
        "<div class='fig-block'><div class='fig-cap'>相关能力与素养得分（满分 5）</div>"
        f"{ability_body}</div>{behavior_html}"
    )


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_literacy(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and 0 < float(value) <= 5:
        return round(float(value), 1)
    return None


def _literacy_of_record(raw: Dict[str, Any]) -> Optional[float]:
    saved = _as_literacy(raw.get("literacy_score"))
    if saved is not None:
        return saved
    pack = _literacy_from_points(raw.get("points") or [])
    return pack["score"] if pack else None


def _attach_score_series(
    student_reports: Sequence[Dict[str, Any]],
    prior_bucket: Optional[Dict[str, Any]],
    homework_index: int,
) -> None:
    """折线用各次素养分。更早的次数从当时的分点重算，不再用做对题数。"""
    hw = _as_int(homework_index, 1)
    bucket = prior_bucket if isinstance(prior_bucket, dict) else {}
    for report in student_reports:
        if not isinstance(report, dict):
            continue
        prior = bucket.get(str(report.get("student_index")))
        hist = []
        if isinstance(prior, dict):
            for item in prior.get("history") or []:
                if not isinstance(item, dict):
                    continue
                index = _as_int(item.get("homework_index"), 0)
                if 0 < index < hw:
                    hist.append(item)
        hist.sort(key=lambda item: _as_int(item.get("homework_index"), 0))
        mark = _literacy_of_record(report)
        report["literacy_score"] = mark
        report["score"] = mark
        series = []
        for item in hist[-5:]:
            earlier = _literacy_of_record(item)
            if earlier is None:
                continue
            series.append({
                "homework_index": _as_int(item.get("homework_index"), 0),
                "literacy_score": earlier,
                "score": earlier,
            })
        if mark is not None:
            series.append({
                "homework_index": hw,
                "literacy_score": mark,
                "score": mark,
                "current": True,
            })
        report["score_series"] = series


def _trend_svg(points: Sequence[Dict[str, Any]], *, caption: str = "") -> str:
    """纵轴是素养分，满分 5。至少两次有素养分才连线。"""
    usable = []
    for item in points:
        if not isinstance(item, dict) or _as_int(item.get("homework_index"), 0) <= 0:
            continue
        score = _as_literacy(item.get("literacy_score"))
        if score is None:
            score = _as_literacy(item.get("score"))
        if score is None:
            continue
        usable.append((item, score))
    if len(usable) < 2:
        return ""
    title = caption or "历次素养得分"
    width, height = 560, 196
    left, right, top, bottom = 42, 16, 26, 34
    plot_w = width - left - right
    plot_h = height - top - bottom
    last = len(usable) - 1
    y_max = 5.0

    def xpos(index: int) -> float:
        return left + plot_w * index / last

    def ypos(value: float) -> float:
        return top + plot_h * (1 - value / y_max)

    guides = []
    for mark in (0, 2.5, 5):
        y = ypos(mark)
        label = f"{mark:.0f}" if mark in (0, 5) else "2.5"
        guides.append(
            f"<line x1='{left}' y1='{y:.1f}' x2='{width - right}' y2='{y:.1f}' class='trend-guide'/>"
            f"<text x='{left - 6}' y='{y + 3:.1f}' text-anchor='end' class='trend-axis'>{label}</text>"
        )
    coords = []
    dots = []
    for index, (item, value) in enumerate(usable):
        x, y = xpos(index), ypos(value)
        coords.append(f"{x:.1f},{y:.1f}")
        now = " now" if item.get("current") else ""
        name = "本次" if item.get("current") else f"第{item.get('homework_index')}次"
        dots.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3.5' class='trend-dot{now}'/>"
            f"<text x='{x:.1f}' y='{y - 8:.1f}' text-anchor='middle' class='trend-label'>{value:.1f}</text>"
            f"<text x='{x:.1f}' y='{height - 12}' text-anchor='middle' class='trend-axis'>{name}</text>"
        )
    return (
        "<div class='fig-block'>"
        f"<div class='fig-cap'>{_xml_text(title)}</div>"
        f"<svg class='trend' viewBox='0 0 {width} {height}' role='img' aria-label='{_xml_text(title)}'>"
        + "".join(guides)
        + f"<polyline points='{' '.join(coords)}' class='trend-line'/>"
        + "".join(dots)
        + "</svg></div>"
    )


def _score_pill_html(report: Dict[str, Any]) -> str:
    mark = _literacy_of_record(report)
    if mark is None:
        return ""
    return f"<span class='pill score'>素养得分 {mark:.1f}/5.0</span>"


def _student_trend_html(report: Dict[str, Any]) -> str:
    series = report.get("score_series") if isinstance(report.get("score_series"), list) else []
    if len(series) < 2:
        return ""
    return _trend_svg(series, caption="历次素养得分")


def _class_score_html(student_reports: Sequence[Dict[str, Any]]) -> str:
    scores = []
    for report in student_reports:
        if not isinstance(report, dict):
            continue
        mark = _literacy_of_record(report)
        if mark is not None:
            scores.append(mark)
    if not scores:
        return ""
    avg = round(sum(scores) / len(scores), 1)
    return f"<p class='score-now'>本次全班平均素养得分 {avg:.1f}/5.0（{len(scores)}人）</p>"


def _class_trend_html(student_reports: Sequence[Dict[str, Any]], *, caption: str) -> str:
    by_score: Dict[int, List[float]] = {}
    has_prior = False
    for report in student_reports:
        if not isinstance(report, dict):
            continue
        series = [item for item in (report.get("score_series") or []) if isinstance(item, dict)]
        if len(series) >= 2:
            has_prior = True
        for item in series:
            index = _as_int(item.get("homework_index"), 0)
            mark = _as_literacy(item.get("literacy_score"))
            if mark is None:
                mark = _as_literacy(item.get("score"))
            if index <= 0 or mark is None:
                continue
            by_score.setdefault(index, []).append(mark)
    indexes = sorted(by_score)
    if not has_prior or len(indexes) < 2:
        return ""
    series = [
        {
            "homework_index": index,
            "literacy_score": round(sum(by_score[index]) / len(by_score[index]), 1),
            "current": index == indexes[-1],
        }
        for index in indexes
    ]
    return _trend_svg(series, caption=f"{caption}素养得分")


def _student_charts_html(points: Sequence[str]) -> str:
    lines = [str(point).strip() for point in points if str(point).strip()]
    if not lines:
        return ""
    pack = _literacy_from_points(lines)
    found = pack["abilities"] if pack else {}
    chain = next((line for line in lines if line.startswith("素养链")), "")
    chain_html = _chain_html(_split_chain(chain))
    portrait = _portrait_charts_html(found, lines)
    if chain_html:
        chain_html = f"<div class='fig-block'><div class='fig-cap'>课标对应关系</div>{chain_html}</div>"
    if not chain_html and not portrait:
        return ""
    return f"<div class='chart-embed'>{chain_html}{portrait}</div>"


def _diagnosis_figure_html(judgment: str) -> str:
    lines = [line.strip() for line in str(judgment or "").splitlines() if line.strip()]
    if not lines:
        return ""
    pack = _literacy_from_points(lines)
    found = pack["abilities"] if pack else {}
    chain = next((line for line in lines if "素养链" in line or "→" in line), "")
    chain_html = _chain_html(_split_chain(chain))
    portrait = _portrait_charts_html(found, lines)
    if chain_html:
        chain_html = f"<div class='fig-block'><div class='fig-cap'>课标对应关系</div>{chain_html}</div>"
    if not chain_html and not portrait:
        return ""
    return f"<div class='chart-embed'>{chain_html}{portrait}</div>"


def _result_of(brief: Dict[str, Any]) -> str:
    value = str(brief.get("verdict") or "").strip().lower()
    if value in ("wrong", "incorrect", "false", "错误"):
        return "需关注"
    if value in ("uncertain", "灰", "gray", "grey"):
        return "待核验"
    if value in ("partial", "部分正确"):
        return "部分做对"
    if value in ("unanswered", "blank", "empty", "未作答"):
        return "未作答"
    if not value:
        return ""
    return "做对"


def _kp_source(brief: Dict[str, Any]) -> str:
    kp = str(brief.get("knowledge_point") or "").strip()
    if kp and kp.lower() not in ("未知", "无", "none"):
        return kp
    stem = str(brief.get("stem") or "").strip()
    if stem:
        return stem
    qid = str(brief.get("qid") or "").strip()
    return f"题{qid}" if qid else ""


def _kp_canon(text: str) -> str:
    raw = _plain_piece(text)
    raw = re.sub(r"[，,；;、]+", "、", raw)
    return re.sub(r"、{2,}", "、", raw).strip("、 ")


def _kp_label(brief: Dict[str, Any]) -> str:
    canon = _kp_canon(_kp_source(brief))
    return _clip_evidence(canon, 24) if canon else ""


def _brief_tally(briefs: Sequence[Any]) -> Dict[str, int]:
    ok = weak = unc = blank = 0
    for brief in briefs or []:
        if not isinstance(brief, dict):
            continue
        result = _result_of(brief)
        if result == "做对":
            ok += 1
        elif result in ("需关注", "部分做对"):
            weak += 1
        elif result == "待核验":
            unc += 1
        elif result == "未作答":
            blank += 1
    return {"ok": ok, "weak": weak, "unc": unc, "blank": blank, "total": ok + weak + unc + blank}


def _knowledge_rows(briefs: Sequence[Any]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, int]] = {}
    for brief in briefs:
        if not isinstance(brief, dict):
            continue
        canon = _kp_canon(_kp_source(brief))
        result = _result_of(brief)
        # 待核验先不计。布置了但未作答计入未掌握。顿号并列的几点分别计入，避免一整串标签单独变成一条 0%。
        if not canon or result in ("", "待核验"):
            continue
        parts = [part.strip() for part in canon.split("、") if len(part.strip()) >= 2] or [canon]
        for part in parts:
            slot = grouped.setdefault(part, {"ok": 0, "weak": 0, "blank": 0})
            if result == "做对":
                slot["ok"] += 1
            elif result == "未作答":
                slot["blank"] += 1
            else:
                slot["weak"] += 1
    redirect: Dict[str, str] = {}
    for short in sorted(grouped, key=len):
        for long in grouped:
            if long == short or long in redirect:
                continue
            if long.startswith(short) and 0 < len(long) - len(short) <= 4:
                redirect[long] = short
    merged: Dict[str, Dict[str, int]] = {}
    for key, slot in grouped.items():
        dest = redirect.get(key, key)
        while dest in redirect:
            dest = redirect[dest]
        bucket = merged.setdefault(dest, {"ok": 0, "weak": 0, "blank": 0})
        bucket["ok"] += slot["ok"]
        bucket["weak"] += slot["weak"]
        bucket["blank"] += slot.get("blank", 0)
    rows = []
    for label, slot in merged.items():
        blank = slot.get("blank", 0)
        denom = slot["ok"] + slot["weak"] + blank
        if denom <= 0:
            continue
        pct = round(100 * slot["ok"] / denom)
        if blank and slot["weak"] == 0 and slot["ok"] == 0:
            state, level = "未作答", 1
            follow = "布置了但没有写，计入未掌握。先分辨是不会，还是畏难、嫌字多不愿写"
        elif pct >= 85:
            state, level = "掌握", 3
            follow = "巩固已掌握的内容"
        elif pct >= 70:
            state, level = "良好", 2
            follow = "换一道相近的题目"
        elif blank:
            state, level = "待提升", 1
            follow = "做错和未作答都计入未掌握。未作答要分辨是不会，还是畏难、嫌字多"
        else:
            state, level = "待提升", 1
            follow = "先完成这一关键步骤"
        rows.append({
            "label": label if len(label) <= 36 else _clip_evidence(label, 36),
            "pct": pct,
            "state": state,
            "level": level,
            "follow": follow,
        })
    rows.sort(key=lambda item: (item["pct"], item["label"]))
    if len(rows) > 8:
        rows = rows[:4] + rows[-4:]
    return rows


def _knowledge_rate(briefs: Sequence[Any]) -> Optional[int]:
    ok = weak = 0
    for brief in briefs:
        if not isinstance(brief, dict):
            continue
        result = _result_of(brief)
        if result == "做对":
            ok += 1
        elif result in ("需关注", "部分做对", "未作答"):
            weak += 1
    if ok + weak <= 0:
        return None
    return round(100 * ok / (ok + weak))


def _knowledge_figure_html(briefs: Sequence[Any], *, caption: str, note: str = "") -> str:
    rows = _knowledge_rows(briefs)
    if not rows:
        return ""
    bars = []
    table = [
        "<table class='lite'><tr><th>考查点</th><th>掌握</th><th>状态</th><th>接下来</th></tr>"
    ]
    for row in rows:
        bars.append(
            f"<div class='look-meter'><span class='look-name'>{_xml_text(row['label'])}</span>"
            f"<span class='look-track'><i class='lv-{row['level']}' style='width:{max(8, row['pct'])}%'></i></span>"
            f"<span class='look-lv'>{row['pct']}%</span></div>"
        )
        table.append(
            "<tr>"
            f"<td>{_xml_text(row['label'])}</td>"
            f"<td>{row['pct']}%</td>"
            f"<td>{row['state']}</td>"
            f"<td>{row['follow']}</td>"
            "</tr>"
        )
    table.append("</table>")
    weak = [row["label"] for row in rows if row["state"] in ("待提升", "未作答")]
    blankish = any(row["state"] == "未作答" or "未作答" in row["follow"] for row in rows)
    blank_note = "。未作答计入未掌握" if blankish else ""
    weak_line = f"<p class='look-note'>本次较薄弱：{_xml_text('、'.join(weak[:3]))}{blank_note}</p>" if weak else ""
    rate = _knowledge_rate(briefs)
    head = f"<p class='score-now'>知识掌握 {rate}%</p>" if rate is not None else ""
    return (
        "<div class='fig-block'>"
        f"<div class='fig-cap'>{_xml_text(caption)}</div>"
        f"{head}{weak_line}"
        "<div class='look-meters'>"
        + "".join(bars)
        + "</div>"
        + "".join(table)
        + (f"<p class='look-note'>{_xml_text(note)}</p>" if note else "")
        + "</div>"
    )


def _attempt_rows_html(briefs: Sequence[Any]) -> str:
    rows = []
    for brief in briefs:
        if not isinstance(brief, dict):
            continue
        result = _result_of(brief)
        label = _kp_label(brief)
        if not result or not label:
            continue
        seen = str(brief.get("error_type") or "").strip()
        if not seen and result == "做对":
            seen = "这一步做对了"
        rows.append((label, result, _clip_evidence(seen, 28) if seen else "—"))
        if len(rows) >= 5:
            break
    if not rows:
        return ""
    body = "".join(
        f"<tr><td>{_xml_text(label)}</td><td>{_xml_text(result)}</td><td>{_xml_text(seen)}</td></tr>"
        for label, result, seen in rows
    )
    return (
        "<div class='fig-block'><div class='fig-cap'>本次作答情况</div>"
        "<table class='lite'><tr><th>考查点</th><th>完成</th><th>批改所见</th></tr>"
        f"{body}</table></div>"
    )


def _focus_html(points: Sequence[str]) -> str:
    lines = [str(point).strip() for point in points if str(point).strip()]
    chain = next((line for line in lines if line.startswith("素养链") or "条目" in line), "")
    item = ""
    for label, body in _split_chain(chain):
        if label == "条目" and body:
            item = body
            break
    pack = _literacy_from_points(lines)
    names = list(pack["abilities"]) if pack else []
    cells = []
    if item:
        cells.append(("考查条目", item))
    if names:
        cells.append(("重点素养", "、".join(names)))
    if cells:
        cells.append(("证据", "这份作业的作答和错因"))
    if not cells:
        return ""
    body = "".join(
        f"<tr><th>{_xml_text(key)}</th><td>{_xml_text(value)}</td></tr>"
        for key, value in cells
    )
    return (
        "<div class='fig-block'><div class='fig-cap'>本次考查内容</div>"
        f"<table class='lite'>{body}</table></div>"
    )


def _overview_kpis_html(report: Dict[str, Any]) -> str:
    points = [str(point) for point in (report.get("points") or []) if str(point).strip()]
    briefs = report.get("question_briefs") or []
    mark = _literacy_of_record(report)
    pack = _literacy_from_points(points)
    ability_n = len(pack["abilities"]) if pack else 0
    rate = _knowledge_rate(briefs)
    total = len([item for item in briefs if isinstance(item, dict)])
    done = len([item for item in briefs if isinstance(item, dict) and _result_of(item) == "做对"])
    cells = []
    if mark is not None:
        cells.append(("素养得分", f"{mark:.1f}/5"))
    if rate is not None:
        cells.append(("知识掌握", f"{rate}%"))
    if ability_n:
        cells.append(("关键素养", f"{ability_n}项"))
    if total:
        cells.append(("作答完成", f"{done}/{total}"))
    if not cells:
        return ""
    body = "".join(
        f"<div class='kpi'><b>{_xml_text(value)}</b><span>{_xml_text(label)}</span></div>"
        for label, value in cells
    )
    return f"<div class='kpi-row'>{body}</div>"


def _assignment_workup_html(report: Dict[str, Any]) -> str:
    points = [str(point) for point in (report.get("points") or []) if str(point).strip()]
    briefs = report.get("question_briefs") or []
    nxt = next((line for line in points if line.startswith("下一步")), "")
    note = _clip_evidence(re.sub(r"^下一步[：:]\s*", "", nxt), 42) if nxt else ""
    parts = [
        _focus_html(points),
        _overview_kpis_html(report),
        _knowledge_figure_html(briefs, caption="考查点掌握", note=note),
        _attempt_rows_html(briefs),
    ]
    body = "".join(part for part in parts if part)
    return f"<div class='workup'>{body}</div>" if body else ""


def _class_knowledge_html(student_reports: Sequence[Dict[str, Any]]) -> str:
    briefs = []
    for report in student_reports:
        if isinstance(report, dict):
            briefs.extend(report.get("question_briefs") or [])
    return _knowledge_figure_html(briefs, caption="本次各考查点掌握情况")


def _class_ability_html(student_reports: Sequence[Dict[str, Any]], prose: str = "") -> str:
    scores: Dict[str, List[float]] = {}
    for report in student_reports:
        if not isinstance(report, dict):
            continue
        lines = [str(point).strip() for point in (report.get("points") or []) if str(point).strip()]
        pack = _literacy_from_points(lines)
        if not pack:
            continue
        for name, slot in pack["abilities"].items():
            scores.setdefault(name, []).append(float(slot.get("score") or _literacy_base(int(slot["level"]))))
    if not scores:
        return ""
    evidence: Dict[str, str] = {}
    prose_lines = [re.sub(r"^[-•]\s*", "", line).strip() for line in str(prose or "").splitlines() if line.strip()]
    for name in scores:
        seen = _ability_evidence(name, prose_lines)
        if seen:
            evidence[name] = seen
    for report in student_reports:
        if not isinstance(report, dict):
            continue
        who = str(report.get("display_name") or "").strip()
        lines = [str(point).strip() for point in (report.get("points") or []) if str(point).strip()]
        for name in scores:
            if evidence.get(name):
                continue
            seen = _ability_evidence(name, lines)
            if seen:
                evidence[name] = f"{who}：{seen}" if who else seen
    rows = []
    ordered = sorted(scores.items(), key=lambda item: (-sum(item[1]) / len(item[1]), item[0]))
    radar_items = []
    for name, marks in ordered:
        avg = round(sum(marks) / len(marks), 1)
        width = max(8, round(100 * avg / 5))
        radar_items.append((name, _level_of_score(avg), avg))
        note = evidence.get(name) or ""
        rows.append(
            f"<div class='look-meter'><span class='look-name'>{_xml_text(name)}</span>"
            f"<span class='look-track'><i class='count-bar' style='width:{width}%'></i></span>"
            f"<span class='look-lv'>{avg:.1f}/5 · {len(marks)}人</span></div>"
            + (f"<p class='look-note'>{_xml_text(note)}</p>" if note else "")
        )
    radar = _radar_svg(radar_items)
    radar_html = (
        "<div class='fig-block'><div class='fig-cap'>本次班级素养概况</div>"
        f"<div class='radar-wrap'>{radar}</div></div>"
    ) if radar else ""
    return (
        radar_html
        + "<div class='fig-block'><div class='fig-cap'>本次相关素养（满分 5）</div>"
        + "<div class='look-meters'>"
        + "".join(rows)
        + "</div></div>"
    )


def _band_distribution_html(student_reports: Sequence[Dict[str, Any]]) -> str:
    groups: Dict[int, List[str]] = {1: [], 2: [], 3: []}
    for report in student_reports:
        if not isinstance(report, dict):
            continue
        band = next(
            (str(point) for point in (report.get("points") or []) if str(point).strip().startswith("档位")),
            "",
        )
        rank = _rank_from_line(band)
        if rank:
            groups[rank].append(str(report.get("display_name") or "").strip())
    if not any(groups.values()):
        return ""
    total = sum(len(names) for names in groups.values()) or 1
    rows = []
    for rank, label in ((3, "达到"), (2, "基本达到"), (1, "尚未达到")):
        names = [name for name in groups[rank] if name]
        width = round(100 * len(names) / total) if names else 0
        who = "、".join(names) if names else "没有人落在这一档"
        rows.append(
            f"<div class='band-row'><span class='band-name'>{label}</span>"
            f"<span class='look-track'><i class='lv-{rank}' style='width:{width}%'></i></span>"
            f"<span class='band-who'>{len(names)}人 · {_xml_text(who)}</span></div>"
        )
    return (
        "<div class='band-fig'>"
        "<div class='look-kicker'>这次各档人数</div>"
        "<p class='look-note'>按每人报告里写下的档位归。不另打分，也不做素养排名。</p>"
        + "".join(rows)
        + "</div>"
    )


_POINT_LABEL = re.compile(
    r"^((?:素养链|画像能力|画像|档位|下一步|学|教|育|学科能力|学科素养|"
    r"核心素养|人的核心素养|可观察行为|内容联系|条目)[：:])\s*"
)


def _split_dense_line(text: str) -> List[str]:
    """长段拆成短点。短句和表格行保持原样。"""
    s = str(text or "").strip()
    if not s or s.startswith("|"):
        return []
    body = _POINT_LABEL.sub("", s).strip() or s
    parts: List[str] = []
    if "→" in body or "->" in body:
        parts = [p.strip(" ；;") for p in re.split(r"\s*(?:→|->)\s*", body) if len(p.strip()) >= 6]
    if len(parts) < 2 and body.count("；") >= 1 and len(body) >= 48:
        parts = [p.strip() for p in body.split("；") if len(p.strip()) >= 8]
    if len(parts) < 2 and len(body) >= 70 and body.count("。") >= 2:
        parts = [p.strip() for p in re.split(r"(?<=。)", body) if len(p.strip()) >= 8]
    return parts if len(parts) >= 2 else []


def _dense_block_html(text: str, inline=None) -> str:
    """一条里有多截时，标题留在外面，里面再分点。"""
    parts = _split_dense_line(text)
    if len(parts) < 2:
        return ""
    render = inline or _md_inline_to_html
    matched = _POINT_LABEL.match(str(text or "").strip())
    label = f"<b class='point-label'>{render(matched.group(1))}</b>" if matched else ""
    items = "".join(f"<li>{render(part)}</li>" for part in parts)
    return f"{label}<ul class='inner-points'>{items}</ul>"


def _md_inline_to_html(text: str) -> str:
    t = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


def _class_report_md_to_html(markdown: str) -> str:
    """班级报告 Markdown → HTML：含表格、有序/无序列表、标题（不原样贴 |---|）。"""
    lines = (markdown or "").splitlines()
    blocks: List[str] = []
    i = 0
    in_ul = False
    in_ol = False

    def _close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            blocks.append("</ul>")
            in_ul = False
        if in_ol:
            blocks.append("</ol>")
            in_ol = False

    def _is_table_sep(line: str) -> bool:
        s = line.strip()
        if "|" not in s:
            return False
        body = s.strip("|").replace(":", "").replace("-", "").replace("|", "").replace(" ", "")
        return body == "" and "-" in s

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s or re.fullmatch(r"[-_*]{3,}", s):
            _close_lists()
            i += 1
            continue
        # GFM 表格
        if s.startswith("|") and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            _close_lists()
            rows: List[List[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if _is_table_sep(lines[i]):
                    i += 1
                    continue
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            if rows:
                blocks.append('<div class="md-table-wrap"><table class="md-table">')
                blocks.append(
                    "<thead><tr>"
                    + "".join(f"<th>{_md_inline_to_html(c)}</th>" for c in rows[0])
                    + "</tr></thead><tbody>"
                )
                for r in rows[1:]:
                    blocks.append(
                        "<tr>" + "".join(f"<td>{_md_inline_to_html(c)}</td>" for c in r) + "</tr>"
                    )
                blocks.append("</tbody></table></div>")
            continue
        if s.startswith("# ") and not s.startswith("## "):
            _close_lists()
            blocks.append(f"<h3 class='md-h1'>{_md_inline_to_html(s[2:])}</h3>")
            i += 1
            continue
        if s.startswith("## "):
            _close_lists()
            blocks.append(f"<h3>{_md_inline_to_html(s[3:])}</h3>")
            i += 1
            continue
        if s.startswith("### "):
            _close_lists()
            blocks.append(f"<h4>{_md_inline_to_html(s[4:])}</h4>")
            i += 1
            continue
        if s.startswith("#### "):
            _close_lists()
            blocks.append(f"<h4 class='md-h4'>{_md_inline_to_html(s[5:])}</h4>")
            i += 1
            continue
        m_ol = re.match(r"^(\d+)[\.、]\s+(.+)$", s)
        if m_ol:
            if in_ul:
                blocks.append("</ul>")
                in_ul = False
            if not in_ol:
                blocks.append("<ol>")
                in_ol = True
            blocks.append(f"<li>{_md_inline_to_html(m_ol.group(2))}</li>")
            i += 1
            continue
        if s.startswith("- ") or s.startswith("* "):
            if in_ol:
                blocks.append("</ol>")
                in_ol = False
            if not in_ul:
                blocks.append("<ul>")
                in_ul = True
            item = s[2:].strip()
            kind = _report_point_class(item)
            cls = f" class='{kind}'" if kind else ""
            dense = _dense_block_html(item)
            blocks.append(
                f"<li{cls}>{dense or _md_inline_to_html(item)}</li>"
            )
            i += 1
            continue
        _close_lists()
        dense = _dense_block_html(s)
        if dense:
            kind = _report_point_class(s)
            cls = f" class='{kind}'" if kind else ""
            blocks.append(f"<ul class='split-points'><li{cls}>{dense}</li></ul>")
        else:
            blocks.append(f"<p>{_md_inline_to_html(s)}</p>")
        i += 1
    _close_lists()
    return "\n".join(blocks) if blocks else "<p>（班级报告缺失）</p>"


def _split_md_sections(markdown: str) -> List[Tuple[str, str]]:
    """按 ## 切段，返回 [(title, body), ...]。"""
    text = (markdown or "").strip()
    if not text:
        return []
    parts = re.split(r"\n(?=##\s+)", text)
    out: List[Tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("## "):
            lines = part.splitlines()
            title = lines[0][3:].strip()
            body = "\n".join(lines[1:]).strip()
            out.append((title, body))
        elif part.startswith("# "):
            lines = part.splitlines()
            title = lines[0][2:].strip()
            body = "\n".join(lines[1:]).strip()
            out.append((title, body))
        else:
            out.append(("", part))
    return out


def _commonality_chart_html(student_reports: List[Dict[str, Any]]) -> str:
    """共性与个性：用各生需关注/待核验柱状对照。"""
    rows = []
    max_v = 1
    for r in student_reports:
        if not isinstance(r, dict):
            continue
        name = str(r.get("display_name") or f"学生{r.get('student_index')}")
        wrong = int(r.get("wrong_count") or 0)
        unc = int(r.get("uncertain_count") or 0)
        briefs = r.get("question_briefs") or []
        ok = max(0, len(briefs) - wrong - unc) if briefs else 0
        max_v = max(max_v, wrong + unc + ok, 1)
        rows.append((name, ok, wrong, unc))
    if not rows:
        return ""
    bars = []
    for name, ok, wrong, unc in rows:
        def pct(n: int) -> int:
            return max(4, int(round(100.0 * n / max_v))) if n else 0
        bars.append(
            f"<div class='cm-bar-row'>"
            f"<div class='cm-bar-name'>{_md_inline_to_html(name)}</div>"
            f"<div class='cm-bar-track'>"
            f"<i class='ok' style='width:{pct(ok)}%' title='较稳 {ok}'></i>"
            f"<i class='bad' style='width:{pct(wrong)}%' title='需关注 {wrong}'></i>"
            f"<i class='wait' style='width:{pct(unc)}%' title='待核验 {unc}'></i>"
            f"</div>"
            f"<div class='cm-bar-num'>稳{ok} · 关{wrong} · 核{unc}</div>"
            f"</div>"
        )
    return (
        "<div class='cm-chart'>"
        "<div class='cm-chart-legend'>"
        "<span class='pill ok'>较稳</span>"
        "<span class='pill bad'>需关注</span>"
        "<span class='pill wait'>待核验</span>"
        "</div>"
        + "".join(bars)
        + "</div>"
    )


def _zone_cards_from_section(body: str) -> str:
    """把认知分区建议拆成盲区/内耗/就近三张卡；口径「说明」挂回标题下作灰注，不当成盲区卡。"""
    text = (body or "").strip()
    if not text:
        return ""
    note_html = ""
    # 段首口径说明（「说明：…」或「以下…不列盲区」）：挂到分区标题下作灰注
    _zone_head = r"(?:\d+[\.、]\s+|###\s+|\*\*(?:盲区|内耗|就近))"
    m_note = re.match(
        rf"^((?:(?:说明|口径|备注)[：:].*?|以下.*?(?:不列|不计入|技能错误).*?))(?=\n{_zone_head}|\Z)",
        text,
        flags=re.S,
    )
    if m_note:
        note_raw = m_note.group(1).strip()
        note_html = f"<p class='zone-note'>{_md_inline_to_html(note_raw)}</p>"
        text = text[m_note.end() :].strip()
    # ### 标题 或 **盲区**/**内耗**/**就近** 粗体小标题都拆成卡
    chunks = re.split(rf"\n(?={_zone_head})", text)
    cards = []
    palette = [
        ("就近", "zone-zpd", "就近发展区"),
        ("内耗", "zone-friction", "内耗区"),
        ("盲区", "zone-blind", "认知盲区"),
    ]
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        title = lines[0][:80]
        body_txt = "\n".join(lines[1:]).strip()
        # 残漏口径句（含「不列为盲区」——勿因字面含「盲区」当成盲区卡）
        if (
            re.match(r"^(说明|口径|备注)[：:]", title)
            or (
                re.match(r"^以下", title)
                and ("不列" in title or "不计入" in title or "技能错误" in title)
            )
            or (body_txt.startswith("说明") and "待验证" in body_txt and len(body_txt) < 280)
        ):
            note_html = f"<p class='zone-note'>{_md_inline_to_html(body_txt or title)}</p>"
            continue
        matched = None
        for key, cname, nice in palette:
            if key in title:
                matched = (cname, nice)
                break
        if not matched:
            continue
        # 非标题行误命中（如正文「不列为盲区」）：跳过
        if not re.match(r"^(?:\d+[\.、]\s+|###\s+|\*\*)", title):
            if matched[1] == "认知盲区" and ("不列" in title or "不计入" in title):
                note_html = f"<p class='zone-note'>{_md_inline_to_html(title)}</p>"
                continue
            continue
        # 标题像盲区、正文却几乎只有口径说明 → 并入 note
        if matched[1] == "认知盲区" and body_txt and len(body_txt) < 320:
            if (
                re.match(r"^说明[：:]", body_txt)
                and ("待验证" in body_txt or "不列" in body_txt)
                and not re.search(r"[一-龥]{2,4}[：:].{4,}", body_txt)
            ) or (
                re.match(r"^以下", body_txt)
                and ("不列" in body_txt or "不计入" in body_txt or "技能错误" in body_txt)
                and not re.search(r"\|.+\|", body_txt)
                and body_txt.count("\n") < 4
            ):
                note_html = f"<p class='zone-note'>{_md_inline_to_html(body_txt)}</p>"
                continue
        cname, nice = matched
        body_html = _class_report_md_to_html(body_txt or chunk)
        cards.append(
            f"<article class='zone-card {cname}'><h4>{_md_inline_to_html(nice)}</h4>{body_html}</article>"
        )
    if cards:
        return f"{note_html}<div class='zone-grid'>{''.join(cards)}</div>"
    return note_html + _class_report_md_to_html(text)


def _render_class_report_rich(
    markdown: str,
    student_reports: List[Dict[str, Any]],
) -> Dict[str, str]:
    """班级报告分区渲染。期望水准、素养归属与其余班级报告分开，便于按阅读顺序排列。"""
    sections = _split_md_sections(markdown)
    if not sections:
        return {"expect": "", "ladder": "", "rest": "<p>（班级报告缺失）</p>"}
    expect_parts: List[str] = []
    ladder_parts: List[str] = []
    rest_parts: List[str] = []
    for title, body in sections:
        t = (title or "").strip()
        body = (body or "").strip()
        # 顶层报告大标题（# …批改报告）且正文为空：跳过，避免假「班级报告缺失」
        if not body and ("批改报告" in t or t.endswith("报告")):
            continue
        if not body and not t:
            continue
        if not body:
            continue
        if not t:
            t = "说明"
        if "期望" in t:
            expect_parts.append(
                f"<div class='cr-block expect' id='cr-expect'>"
                f"<h3>{_md_inline_to_html(t)}</h3>"
                f"<div class='cr-body'>{_class_report_md_to_html(body)}</div></div>"
            )
        elif "素养归属" in t or "素养链" in t:
            ladder_parts.append(
                f"<div class='cr-block ladder' id='cr-ladder'>"
                f"<h3>{_md_inline_to_html(t)}</h3>"
                f"{_chain_figure_from_md(body)}"
                f"{_class_ability_html(student_reports, body)}"
                f"<div class='cr-body'>{_class_report_md_to_html(body)}</div></div>"
            )
        elif "学情" in t:
            rest_parts.append(
                f"<div class='cr-block' id='cr-overview'>"
                f"<h3>{_md_inline_to_html(t)}</h3>"
                f"{_class_score_html(student_reports)}"
                f"{_class_knowledge_html(student_reports)}"
                f"{_band_distribution_html(student_reports)}"
                f"<div class='cr-body'>{_class_report_md_to_html(body)}</div></div>"
            )
        elif "共性" in t or "个性" in t:
            chart = _commonality_chart_html(student_reports)
            rest_parts.append(
                f"<div class='cr-block' id='cr-common'>"
                f"<h3>{_md_inline_to_html(t)}</h3>"
                f"{chart}"
                f"<div class='cr-body'>{_class_report_md_to_html(body)}</div></div>"
            )
        elif "前序" in t or "纵向" in t:
            rest_parts.append(
                f"<div class='cr-block' id='cr-trend'>"
                f"<h3>{_md_inline_to_html(t)}</h3>"
                f"{_class_trend_html(student_reports, caption='全班历次平均')}"
                f"<div class='cr-body'>{_class_report_md_to_html(body)}</div></div>"
            )
        elif "认知分区" in t or ("盲区" in t and "内耗" in t):
            rest_parts.append(
                f"<div class='cr-block' id='cr-zone'>"
                f"<h3>{_md_inline_to_html(t)}</h3>"
                f"{_zone_cards_from_section(body)}</div>"
            )
        elif "配对" in t or "教学建议" in t:
            rest_parts.append(
                f"<div class='cr-block' id='cr-pair'>"
                f"<h3>{_md_inline_to_html(t)}</h3>"
                f"<div class='cr-body'>{_class_report_md_to_html(body)}</div></div>"
            )
        else:
            rest_parts.append(
                f"<div class='cr-block'>"
                f"<h3>{_md_inline_to_html(t)}</h3>"
                f"<div class='cr-body'>{_class_report_md_to_html(body)}</div></div>"
            )
    rest = "\n".join(rest_parts)
    if not rest and not expect_parts and not ladder_parts:
        rest = "<p>（班级报告缺失）</p>"
    return {
        "expect": "\n".join(expect_parts),
        "ladder": "\n".join(ladder_parts),
        "rest": rest,
    }


def build_class_multi_excerpt_html(
    bundle: Dict[str, Any],
    *,
    analysis_id: str = "",
    run_id: str = "",
    user_verification: Optional[Dict[str, Any]] = None,
    verify_suggestions: Optional[Dict[str, Any]] = None,
    material_type: str = "homework",
) -> str:
    """班级多人解释精要：对齐单人 4087（三步骤×白灰黑、核验、逐页留存按生），并强化班级报告展示。"""
    from .excerpt_html_views import (
        build_verify_interaction_embed,
        _overview_visual_html,
        _page_conf_chips,
        _shade_dot_html,
    )
    from .excerpt_card_render import (
        _collect_units,
        _esc,
        _verdict_badge_html,
        _comment_html,
        _unit_heading,
    )

    class_map = bundle.get("class_map") or {}
    student_reports = bundle.get("student_reports") or []
    class_report = bundle.get("class_report") or {}
    filename = str(bundle.get("filename") or "").strip()
    material_label = str(bundle.get("material_label") or "").strip()
    subject = str(bundle.get("subject") or "math").strip() or "math"
    pass1_dir = str(bundle.get("pass1_json") or "").strip()
    aid = str(analysis_id or bundle.get("analysis_id") or "").strip()
    rid = str(run_id or bundle.get("run_id") or "current").strip() or "current"
    uv = user_verification if isinstance(user_verification, dict) else bundle.get("user_verification")
    sug = verify_suggestions if isinstance(verify_suggestions, dict) else (bundle.get("verify_suggestions") or {})
    mtype = str(material_type or bundle.get("material_type") or "homework")
    verify_ui = build_verify_interaction_embed(
        uv if isinstance(uv, dict) else None,
        material_type=mtype,
        verify_suggestions=sug if isinstance(sug, dict) else {},
        analysis_id=aid,
        run_id=rid,
    )

    units: List[Dict[str, Any]] = []
    pages_meta: List[Dict[str, Any]] = []
    if pass1_dir and os.path.isdir(pass1_dir):
        try:
            report_stub: Dict[str, Any] = {}
            try:
                # 尝试读 pass2 报告以带批语
                from .result_cards import _named_json, _sample_id
                sample_id = _sample_id(aid) if aid else ""
                p2 = ""
                # pass1 同级常见 pass2_report
                cand = os.path.join(os.path.dirname(pass1_dir), "pass2_report")
                if os.path.isdir(cand) and sample_id:
                    report_stub = _named_json(cand, subject, sample_id, "_report.json") or {}
            except Exception:
                report_stub = {}
            units, pages_meta = _collect_units(
                pass1_dir, subject, report_stub if isinstance(report_stub, dict) else {},
                material_type=mtype,
            )
        except Exception:
            units, pages_meta = [], []

    # 核验块已由 _cross_visual_html 内嵌（与 4087 一致），勿再额外塞 verify_ui banner，否则会嵌套两遍
    overview_html = ""
    if units:
        overview_html = _overview_visual_html(
            units, "",
            material_type=mtype,
            user_verification=uv if isinstance(uv, dict) else None,
        )
    else:
        from .excerpt_html_views import _verify_banner_html
        overview_html = (
            '<section class="panel overview-visual" id="sec-overview">'
            '<div class="panel-head"><h2>总览：三步骤 × 白灰黑</h2></div>'
            '<p class="hint">暂无单元置信度数据，请对照逐页批改图。</p>'
            f"{_verify_banner_html(uv if isinstance(uv, dict) else None, material_type=mtype)}"
            "</section>"
        )

    page_by_num = {int(p.get("page") or 0): p for p in pages_meta if isinstance(p, dict)}
    report_by_sid = {
        str(r.get("student_index")): r
        for r in student_reports
        if isinstance(r, dict)
    }

    def _render_page_block(meta: Dict[str, Any]) -> str:
        qs_html = []
        for u in meta.get("units") or []:
            und_bits = []
            if u.get("student"):
                und_bits.append(f'学生作答「{u["student"]}」')
            if u.get("understanding"):
                und_bits.append(str(u["understanding"]))
            und_text = "；".join(und_bits) or "已完成识别与题意理解"
            grade_bits = []
            if u.get("correct"):
                grade_bits.append(f'参考「{u["correct"]}」')
            if u.get("zone"):
                grade_bits.append(f'学习分区·{u["zone"]}')
            grade_text = "；".join(grade_bits)
            stem_fallback = "题框已切出"
            qs_html.append(
                f'<article class="q">'
                f'<div class="q-head">'
                f'<h4>{_esc(_unit_heading(u))}</h4>'
                f'{_verdict_badge_html(u.get("verdict") or "")}'
                f"</div>"
                f'<div class="step">'
                f'<div class="step-head">{_shade_dot_html(u.get("layout_shade") or "gray_mid", "版面·" + (u.get("layout_label") or ""))}'
                f'<span class="step-name">无损版面</span></div>'
                f'<p>{_esc(u.get("stem") or stem_fallback)}</p></div>'
                f'<div class="step">'
                f'<div class="step-head">{_shade_dot_html(u.get("understanding_shade") or "gray_mid", "理解·" + (u.get("understanding_label") or ""))}'
                f'<span class="step-name">无损理解</span></div>'
                f'<p>{_esc(und_text)}</p></div>'
                f'<div class="step">'
                f'<div class="step-head">{_shade_dot_html(u.get("grading_shade") or "gray_mid", "批改·" + (u.get("grading_label") or ""))}'
                f'<span class="step-name">三区批改</span>'
                f'{_verdict_badge_html(u.get("verdict") or "")}</div>'
                + (f'<p>{_esc(grade_text)}</p>' if grade_text else "")
                + _comment_html(u.get("comment") or "")
                + "</div></article>"
            )
        return (
            f'<section class="page-block" id="page-{meta["page"]}" data-page="{meta["page"]}">'
            f'<h3>第 {_esc(meta["page"])} 页'
            + (f' · {_esc(meta["header"])}' if meta.get("header") else "")
            + "</h3>"
            + _page_conf_chips(meta)
            + "".join(qs_html)
            + "</section>"
        )

    stu_nav: List[str] = []
    stu_sections: List[str] = []
    page_by_student: List[str] = []
    for stu in class_map.get("students") or []:
        if not isinstance(stu, dict):
            continue
        sid = stu.get("student_index")
        name = str(stu.get("display_name") or f"学生{sid}")
        pages = [int(p) for p in (stu.get("pages") or [])]
        pages_label = "、".join(str(p) for p in pages) or "—"
        r = report_by_sid.get(str(sid)) or {}
        briefs = r.get("question_briefs") or []
        tally = _brief_tally(briefs)
        if tally["total"]:
            ok_n, wrong_n, unc_n, blank_n, total_n = (
                tally["ok"], tally["weak"], tally["unc"], tally["blank"], tally["total"],
            )
        else:
            ok_n = wrong_n = unc_n = total_n = "—"
            blank_n = 0
        points = [str(p) for p in (r.get("points") or []) if str(p).strip()]
        highs = r.get("highlights") if isinstance(r.get("highlights"), list) else []
        stu_nav.append(
            f"<a class='sub' href='#stu-{sid}' data-goto='stu-{sid}'>{_md_inline_to_html(name)}</a>"
        )
        charts = _student_charts_html(points)
        point_bits: List[str] = []
        placed_chart = False
        for point in points:
            kind = _report_point_class(point)
            cls = f" class='{kind}'" if kind else ""
            rendered = _dense_block_html(
                point, lambda piece, _highs=highs: _apply_point_highlights(piece, _highs)
            )
            point_bits.append(
                f"<li{cls}>{rendered or _apply_point_highlights(point, highs)}</li>"
            )
            if charts and point.strip().startswith("素养链"):
                point_bits.append(f"<li class='chart-embed'>{charts}</li>")
                placed_chart = True
        if charts and not placed_chart:
            point_bits.append(f"<li class='chart-embed'>{charts}</li>")
        point_lis = "".join(point_bits) or "<li>暂无分点</li>"
        expect = str(r.get("expectation") or "").strip()
        expect_html = ""
        if expect:
            expect_html = (
                f"<div class='expect' id='expect-stu-{sid}'>"
                f"<div class='expect-kicker'>本次期望水准</div>"
                f"<div class='expect-body'>{_class_report_md_to_html(expect)}</div>"
                f"</div>"
            )
        stu_sections.append(
            f"<article class='panel stu' id='stu-{sid}'>"
            f"<div class='panel-head'>"
            f"<h3>{_md_inline_to_html(name)}"
            f"<span class='muted'> · 序位{sid} · 第{pages_label}页</span></h3>"
            f"<div class='stat-row'>"
            f"<span class='pill ok'>较稳 {ok_n}/{total_n}</span>"
            f"<span class='pill bad'>需关注 {wrong_n}</span>"
            f"<span class='pill wait'>待核验 {unc_n}</span>"
            + (f"<span class='pill wait'>未作答 {blank_n}</span>" if blank_n else "")
            + f"{_score_pill_html(r)}"
            f"</div></div>"
            f"{_student_trend_html(r)}"
            f"{expect_html}"
            f"{_assignment_workup_html(r)}"
            f"<ul class='point-list'>{point_lis}</ul>"
            f"<p class='muted'><a href='#pages-stu-{sid}'>查看该生逐页留存 ↓</a></p>"
            f"</article>"
        )
        page_chunks = []
        for pn in pages:
            meta = page_by_num.get(pn)
            if meta:
                page_chunks.append(_render_page_block(meta))
        page_by_student.append(
            f"<div class='stu-pages' id='pages-stu-{sid}'>"
            f"<div class='panel' style='margin-bottom:10px;padding-bottom:10px;'>"
            f"<h3>{_md_inline_to_html(name)} · 逐页留存"
            f"<span class='muted'>（第{pages_label}页）</span></h3></div>"
            + ("".join(page_chunks) or "<div class='panel'><p>暂无该生页数据</p></div>")
            + "</div>"
        )

    class_parts = _render_class_report_rich(
        str(class_report.get("markdown") or class_report.get("summary") or ""),
        student_reports,
    )
    nav_items: List[str] = []
    if class_parts.get("expect"):
        nav_items.append('<a href="#cr-expect" data-goto="cr-expect">本次期望水准</a>')
    if class_parts.get("ladder"):
        nav_items.append('<a href="#cr-ladder" data-goto="cr-ladder">素养归属</a>')
    nav_items.extend([
        '<a href="#sec-class" data-goto="sec-class">班级报告</a>',
        '<a href="#sec-students" data-goto="sec-students">各生报告</a>',
        *stu_nav,
        '<a href="#sec-overview" data-goto="sec-overview">总览·白灰黑</a>',
        '<a href="#sec-pages" data-goto="sec-pages">逐页留存</a>',
    ])
    class_id = str(class_map.get("class_id") or "—")
    hw = class_map.get("homework_index") or "—"
    stu_n = class_map.get("student_count") or len(student_reports) or "—"
    pages_per = class_map.get("pages_per_assignment") or "—"
    sub_bits = [f"班级 {class_id}", f"第{hw}次作业", f"{stu_n}人", f"每生{pages_per}页"]
    if filename:
        sub_bits.append(filename)
    if material_label:
        sub_bits.append(material_label)
    sub = " · ".join(sub_bits)

    # 4087 同款总览/逐页样式（节选）
    shared_css = """
.view-tabs{display:flex;flex-wrap:wrap;gap:6px;}
.view-tabs .tab{appearance:none;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:6px;padding:6px 12px;cursor:pointer;font-size:13px;}
.view-tabs .tab.active{background:var(--accent);color:#fff;border-color:var(--accent);}
.view-pane{display:none;margin-top:12px;}
.view-pane.active{display:block;}
.legend{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;}
.bars{display:flex;flex-direction:column;gap:12px;}
.bar-row{display:grid;grid-template-columns:88px 1fr;gap:10px;align-items:center;}
.bar-label{font-size:13px;color:var(--muted);}
.stack{display:flex;height:28px;border-radius:6px;overflow:hidden;border:1px solid var(--line);background:#fff;}
.stack .seg{display:flex;align-items:center;justify-content:center;font-size:11px;min-width:0;padding:0 4px;white-space:nowrap;overflow:hidden;}
.shade-chip{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:2px 8px 2px 4px;border-radius:4px;border:1px solid var(--bd);background:#fff;color:#1c2430!important;margin:2px 4px 2px 0;}
.shade-dot{width:12px;height:12px;border-radius:50%;background:var(--dot);border:1px solid var(--bd);display:inline-block;flex:0 0 auto;}
.pat-bars{display:flex;flex-direction:column;gap:8px;margin:10px 0 16px;}
.pat-row{display:grid;grid-template-columns:150px 1fr 88px;gap:8px;align-items:center;}
.pat-label{font-size:12px;color:var(--muted);}
.pat-track{height:10px;background:#efe8db;border-radius:4px;overflow:hidden;}
.pat-fill{display:block;height:100%;border-radius:4px;}
.pat-num{font-size:12px;text-align:right;}
.cross-subtabs{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 10px;}
.cross-subtab{appearance:none;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:6px;padding:6px 12px;cursor:pointer;font-size:13px;}
.cross-subtab.active{background:var(--accent);color:#fff;border-color:var(--accent);}
.cross-pane{display:none;margin-top:4px;}
.cross-pane.active{display:block;}
.cross-block{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:0 0 10px;}
.cross-block-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:8px;}
.cross-block-title{font-weight:600;font-size:14px;}
.cross-block-n{color:var(--muted);font-size:12px;}
.stat-grid,.curr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;}
.stat-card,.curr-card,.composite-card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 14px;border-left:4px solid var(--accent, var(--accent));}
.stat-card header{display:flex;justify-content:space-between;gap:8px;align-items:baseline;}
.stat-title{font-weight:600;font-size:14px;}
.stat-count{color:var(--accent);font-size:13px;white-space:nowrap;}
.stat-hint{color:var(--muted);font-size:12px;margin:4px 0 8px;}
.stat-card .meta{font-size:12px;margin:4px 0;}
.curr-row{display:grid;grid-template-columns:1fr 90px 64px;gap:6px;align-items:center;margin:6px 0;font-size:12px;}
.curr-track{height:8px;background:#efe8db;border-radius:4px;overflow:hidden;}
.curr-track i{display:block;height:100%;background:#2c6b5a;}
.loc-list,.loc-short,.loc-all{display:inline-flex;flex-wrap:wrap;align-items:center;gap:6px;vertical-align:middle;}
/* 必须盖过上面的 display，否则 [hidden] 失效 → 短列表+全列表叠在一起像「重复」 */
.loc-short[hidden],.loc-all[hidden]{display:none!important;}
.loc-wrap{display:inline-flex;flex-wrap:wrap;align-items:center;gap:6px;}
.loc-jump{display:inline-flex;align-items:center;padding:3px 10px;margin:0;border-radius:6px;background:#e8eef5;color:#3b6ea5;text-decoration:none!important;font-size:12px;line-height:1.4;border:1px solid #d0dbe8;cursor:pointer;white-space:nowrap;}
.loc-jump:hover{background:#dce7f4;color:#2a5685;border-color:#b8cce0;}
.loc-chip{display:inline-block;padding:2px 8px;border-radius:999px;background:#e8eef5;border:1px solid #d0dbe8;color:#3b6ea5;text-decoration:none;font-size:12px;}
.loc-toggle{appearance:none;display:inline-flex;align-items:center;gap:4px;margin:0;padding:3px 10px;border-radius:6px;cursor:pointer;font-size:12px;background:#f3f4f6;color:#5c6573;border:1px dashed #b8c0cc;text-decoration:none;white-space:nowrap;}
.loc-toggle:hover{background:#e8eaee;color:#3d4654;border-color:#9aa3b0;}
.page-block{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0;}
.conf-block{display:flex;flex-direction:column;gap:6px;margin:0 0 12px;}
.conf-line{display:flex;flex-wrap:wrap;align-items:center;gap:4px;}
.conf-k{width:42px;color:var(--muted);font-size:12px;}
.q{border-top:1px dashed var(--line);padding:16px 0 8px;margin-top:8px;}
.q-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:10px;}
.step{margin:12px 0 16px;padding:10px 12px;background:#faf7f1;border-radius:8px;border:1px solid #efe8db;}
.step-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:6px;}
.step-name{font-size:12px;color:var(--muted);}
.verdict{display:inline-flex;align-items:center;gap:4px;font-size:12px;padding:2px 8px;border-radius:4px;margin:0 6px 0 0;border:1px solid var(--line);}
.verdict-ok{color:var(--ok);background:#e8f5ec;}
.verdict-bad{color:var(--bad);background:#f8ecea;}
.verdict-half{color:var(--half);background:#f8efdf;}
.verdict-empty,.verdict-wait{color:var(--empty);background:#f1f1ef;}
.comment-layers{margin-top:10px;border-left:3px solid var(--accent);padding-left:10px;}
.layer-title{font-size:12px;color:var(--muted);margin-bottom:4px;}
.cm-chart{margin:10px 0 16px;padding:12px;background:#fff;border:1px solid var(--line);border-radius:10px;}
.cm-chart-legend{display:flex;gap:8px;margin-bottom:10px;}
.cm-bar-row{display:grid;grid-template-columns:72px 1fr 120px;gap:8px;align-items:center;margin:8px 0;}
.cm-bar-name{font-size:13px;}
.cm-bar-track{display:flex;height:16px;border-radius:4px;overflow:hidden;background:#efe8db;}
.cm-bar-track i{display:block;height:100%;}
.cm-bar-track i.ok{background:#7bc396;}
.cm-bar-track i.bad{background:#e09a93;}
.cm-bar-track i.wait{background:#c5cad1;}
.cm-bar-num{font-size:12px;color:var(--muted);text-align:right;}
.zone-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:10px 0;}
.zone-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;border-top:4px solid var(--accent);}
.zone-card.zone-blind{border-top-color:#b4453b;background:linear-gradient(180deg,#fbf1f0,#fffcf7);}
.zone-card.zone-friction{border-top-color:#c27a22;background:linear-gradient(180deg,#fbf6ee,#fffcf7);}
.zone-card.zone-zpd{border-top-color:#2c6b5a;background:linear-gradient(180deg,#eef7f1,#fffcf7);}
.zone-card h4{margin:0 0 8px;color:var(--accent);}
.zone-blind h4{color:#b4453b;}
.zone-friction h4{color:#c27a22;}
.zone-note{font-size:12.5px;color:var(--muted);background:#f7f4ee;border:1px dashed var(--line);border-radius:8px;padding:8px 10px;margin:0 0 10px;}
.md-table-wrap{overflow:auto;margin:10px 0 14px;border:1px solid var(--line);border-radius:10px;background:#fff;}
.md-table{width:100%;border-collapse:collapse;}
.md-table th,.md-table td{border-bottom:1px solid var(--line);padding:10px 12px;text-align:left;font-size:13px;vertical-align:top;}
.md-table th{background:rgba(44,107,90,.08);color:var(--accent);font-weight:600;}
.md-table tr:last-child td{border-bottom:0;}
.cr-block{margin:0 0 18px;padding:14px 16px;background:#fff;border:1px solid var(--line);border-radius:12px;}
.cr-block>h3{margin:0 0 10px;color:var(--accent);font-size:16px;}
.cr-body ul,.cr-body ol,.expect-body ul,.point-list{margin:6px 0 12px;padding-left:0;list-style:none;}
.cr-body li,.expect-body li,.point-list li{margin:6px 0;padding:8px 10px 8px 12px;background:#fff;border:1px solid var(--line);border-radius:8px;line-height:1.55;}
.point-label{display:block;margin-bottom:4px;}
ul.inner-points{margin:4px 0 0;padding:0;list-style:none;}
.cr-body li .inner-points>li,.expect-body li .inner-points>li,.point-list li .inner-points>li{margin:4px 0;padding:6px 8px;background:rgba(255,255,255,.72);border:0;border-left:3px solid rgba(90,74,48,.35);border-radius:4px;font-size:13.5px;}
li.band-ok{background:#eef7f1;border-left:4px solid #2c6b5a;}
li.band-mid{background:#fff8ec;border-left:4px solid #8a5a14;}
li.band-low{background:#fbf1f0;border-left:4px solid #b4453b;}
li.triad-learn{background:#f3f7fb;border-left:4px solid #2f5f8a;}
li.triad-teach{background:#f7f3fb;border-left:4px solid #6a4c93;}
li.triad-grow{background:#f3f8f4;border-left:4px solid #2c6b5a;}
li.chain{background:#fff;border-left:4px solid #8a5a14;}
li.chain-1{border-left-color:#8a5a14;}
li.chain-2{border-left-color:#2f5f8a;}
li.chain-3{border-left-color:#6a4c93;}
li.chain-4{border-left-color:#2c6b5a;}
li.chain-x{border-left-color:#3d6b62;background:#f4faf8;}
.cr-block.ladder{border-top:4px solid #8a5a14;background:linear-gradient(180deg,#fff8ec,#fff);}
.split-points{margin-top:4px;}
.pill{display:inline-block;min-width:1.6em;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--line);background:#fff;}
.pill.ok{color:var(--ok);border-color:#b7d7c2;background:#eef7f1;}
.pill.bad{color:var(--bad);border-color:#e6bfba;background:#fbf1f0;}
.pill.wait{color:var(--wait);border-color:#cfd3d8;background:#f3f4f6;}
.stat-row{display:flex;flex-wrap:wrap;gap:6px;}
.pill.score{color:#1a4d40;border-color:#9ec7b4;background:#e7f4ee;font-size:13px;}
.score-now{margin:0 0 8px;font-weight:700;color:#1a4d40;}
.workup{margin:8px 0 12px;}
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(108px,1fr));gap:8px;margin:8px 0 12px;}
.kpi{background:#fff;border:1px solid var(--line);border-radius:10px;padding:8px 10px;}
.kpi b{display:block;font-size:18px;color:#1a4d40;line-height:1.2;}
.kpi span{font-size:12px;color:var(--muted);}
table.lite{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px;}
table.lite th,table.lite td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;}
table.lite th{background:#f7f4ee;font-weight:600;}
.trend{width:100%;height:auto;display:block;}
.trend-line{fill:none;stroke:#2c6b5a;stroke-width:2;}
.trend-guide{stroke:#efe8db;stroke-width:1;}
.trend-dot{fill:#2c6b5a;}
.trend-dot.now{fill:#8a5a14;}
.trend-label{font-size:11px;fill:#1c2430;}
.trend-axis{font-size:11px;fill:#6b7280;}
.point-list{margin:8px 0 0;padding-left:0;list-style:none;}
.expect{margin:4px 0 12px;padding:12px 14px;border-radius:10px;border:1px solid #d7c4a2;border-left:4px solid #8a5a14;background:linear-gradient(180deg,#fff8ec,#fffdf8);}
.expect-kicker{font-size:13px;font-weight:700;color:#8a5a14;letter-spacing:.04em;margin-bottom:6px;}
.expect-body{font-size:14.5px;}
.cr-block.expect{border-left:4px solid #8a5a14;background:linear-gradient(180deg,#fff8ec,#fffdf8);}
mark.hl{background:linear-gradient(180deg,rgba(44,107,90,.18),rgba(44,107,90,.08));color:#1a4d40;font-weight:700;padding:0 2px;border-radius:3px;}
.chart-embed,.point-list li.chart-embed{padding:4px 0 2px;border:0;background:transparent;}
.fig-block{margin:8px 0 12px;}
.fig-cap{font-size:12px;font-weight:700;color:#8a5a14;letter-spacing:.04em;margin-bottom:4px;}
.beh-group{margin:6px 0 8px;}
.beh-group>b{display:block;font-size:12px;color:#2f5f8a;margin-bottom:4px;}
.count-bar{background:#7aa89a;}
.look-kicker{font-size:13px;font-weight:700;color:#8a5a14;letter-spacing:.04em;}
.look-note{margin:4px 0 8px;font-size:12px;color:var(--muted);}
.look-grid{display:grid;grid-template-columns:minmax(280px,420px) minmax(0,1fr);gap:16px;align-items:center;}
.radar{width:100%;height:auto;display:block;}
.radar-ring{fill:none;stroke:#e2dccf;stroke-width:1;}
.radar-spoke{stroke:#e2dccf;stroke-width:1;}
.radar-shape{fill:rgba(44,107,90,.22);stroke:#2c6b5a;stroke-width:2;}
.radar-label{font-size:12px;fill:#1c2430;}
.radar-label.lv-1{fill:#b4453b;}
.radar-label.lv-2{fill:#8a5a14;}
.radar-label.lv-3{fill:#2c6b5a;}
.radar-score{font-size:18px;font-weight:700;fill:#1c2430;}
.radar-legend{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px;color:var(--muted);margin-top:4px;}
.radar-legend i,.look-track i{display:inline-block;height:8px;border-radius:4px;}
.radar-legend i{width:18px;}
.lv-1{background:#e09a93;}
.lv-2{background:#e2c48a;}
.lv-3{background:#7bc396;}
.look-meters{display:flex;flex-direction:column;gap:8px;}
.look-meter,.band-row{display:grid;grid-template-columns:minmax(10em,18em) 1fr auto;gap:8px;align-items:center;}
.look-name,.band-name{font-size:13px;line-height:1.35;}
.look-track{display:block;height:10px;border-radius:5px;background:#efe8db;overflow:hidden;}
.look-track i{display:block;height:100%;}
.look-lv,.band-who{font-size:12px;color:var(--muted);}
.band-fig{margin:0 0 12px;}
.band-row{margin:6px 0;}
.chain-fig{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px;margin:10px 0 4px;}
.chain-step{flex:1 1 160px;background:#fbf6ee;border:1px solid #eadcc4;border-radius:8px;padding:8px 10px;border-top:3px solid #8a5a14;}
.chain-step.s2{border-top-color:#2f5f8a;background:#f4f7fb;border-color:#d5e0ec;}
.chain-step.s3{border-top-color:#6a4c93;background:#f7f4fa;border-color:#e3dced;}
.chain-step.s4{border-top-color:#2c6b5a;background:#f3f8f4;border-color:#d3e4da;}
.chain-step b{display:block;font-size:12px;color:var(--muted);font-weight:600;}
.chain-step span{font-size:13px;}
.chain-arrow{align-self:center;color:#8a5a14;font-size:16px;}
.chain-cross{margin:4px 0 8px;font-size:13px;color:#3d6b62;}
.look-evidence{margin:8px 0 0;padding:0;list-style:none;}
.look-evidence li{margin:4px 0;padding:0;border:0;background:transparent;font-size:12.5px;color:var(--muted);}
.stu:target,.stu-pages:target{outline:2px solid rgba(44,107,90,.35);outline-offset:2px;}
.more{margin-top:12px;font-size:13px;color:var(--muted);}
.more summary{cursor:pointer;color:var(--accent);}
/* 人机核验：对齐 4087 暖红样式（覆盖 embed 里偏黄的默认） */
.uv-banner{margin:14px 0 10px;padding:12px 14px;border:1px solid #e8b4b0;border-left:4px solid #c45c54;border-radius:8px;background:linear-gradient(180deg,#fff6f5 0%,#fffaf8 100%);color:#5a2e2a;}
.uv-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:6px;}
.uv-head strong{font-size:14px;}
.uv-counts{display:flex;gap:8px;font-size:12px;}
.uv-counts em{font-style:normal;padding:1px 8px;border-radius:999px;background:#f8e4e2;color:#a33d36;}
.uv-counts .uv-c-i{background:#f8e4e2;color:#a33d36;}
.uv-counts .uv-c-ii{background:#fff4e5;color:#8a5a14;}
.uv-counts .uv-c-iii{background:#f4f1ea;color:#5c5346;}
.uv-tier{margin:0 0 8px;}
.uv-tier-name{font-size:12px;font-weight:700;margin:2px 0 4px;color:#5a2e2a;}
.uv-tier-name em{font-style:normal;font-weight:600;margin-left:4px;}
.uv-chip.is-i{background:#fdecea;border-color:#ecc0bc;color:#a5342c;}
.uv-chip.is-ii{background:#fff4e5;border-color:#edd2a8;color:#8a5a14;}
.uv-chip.is-iii{background:#f4f1ea;border-color:#ddd4c4;color:#5c5346;}
.uv-summary{margin:0 0 10px;font-size:13px;line-height:1.55;color:#6b3f3a;}
.uv-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px;}
.uv-chip{appearance:none;border:1px solid #d0dbe8;background:#e8eef5;color:#3b6ea5;border-radius:999px;padding:3px 10px;font-size:12px;text-decoration:none;}
.uv-verify-btn{appearance:none;border:1px solid #c45c54;background:#fff;color:#c45c54;border-radius:6px;padding:3px 10px;font-size:12px;cursor:pointer;}
.uv-iterate-btn{appearance:none;border:1px solid #c45c54;background:#c45c54;color:#fff;border-radius:8px;padding:7px 12px;font-size:13px;cursor:pointer;}
.uv-iterate-hint{font-size:12px;color:#8a5a54;}
"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>班级多人批改·解释精要</title>
<style>
:root {{
  --bg:#f3efe6; --card:#fffcf7; --ink:#1c2430; --muted:#5c6573;
  --line:#e2dccf; --accent:#2c6b5a;
  --ok:#2f7d4a; --bad:#b4453b; --half:#c27a22; --empty:#7a7f88; --wait:#5b6472;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  color:var(--ink); background:
    radial-gradient(1200px 500px at 10% -10%, #e7efe8 0%, transparent 55%),
    radial-gradient(900px 420px at 100% 0%, #efe6d6 0%, transparent 50%),
    linear-gradient(180deg,#efe8db,#f6f3ec);
  line-height:1.7;
}}
.shell {{ display:grid; grid-template-columns:200px minmax(0,1fr); gap:0; min-height:100vh; }}
.sidenav {{
  position:sticky; top:0; align-self:start; height:100vh; padding:22px 14px;
  border-right:1px solid var(--line); background:rgba(255,252,247,.88); overflow:auto;
}}
.sidenav .brand {{ font-size:13px; color:var(--accent); letter-spacing:.06em; margin:0 0 14px; }}
.sidenav a {{
  display:block; text-decoration:none; color:var(--ink); font-size:14px;
  padding:8px 10px; border-radius:6px; margin-bottom:4px;
}}
.sidenav a.sub {{ margin-left:12px; padding:5px 10px; font-size:13px; color:#3d4a44; }}
.sidenav a:hover {{ background:#ebe4d6; }}
.wrap {{ max-width:980px; margin:0 auto; padding:28px 22px 96px; }}
.hero {{ margin-bottom:18px; }}
.eyebrow {{ color:var(--accent); letter-spacing:.08em; font-size:13px; margin:0 0 6px; }}
h1 {{ font-size:28px; margin:0 0 8px; letter-spacing:.02em; }}
.sub {{ color:var(--muted); margin:0; font-size:14px; }}
h2 {{ font-size:20px; margin:0 0 12px; }}
h3 {{ font-size:17px; margin:0; }}
h4 {{ font-size:15px; margin:12px 0 6px; }}
p {{ margin:8px 0; }}
.panel {{
  background:rgba(255,252,247,.9); border:1px solid var(--line); border-radius:12px;
  padding:16px 18px 18px; margin:0 0 16px;
}}
.panel-head {{ display:flex; flex-wrap:wrap; gap:10px; justify-content:space-between; align-items:center; margin-bottom:8px; }}
.hint {{ color:var(--muted); font-size:13px; margin:0 0 12px; }}
.shade-table {{ width:100%; border-collapse:collapse; }}
.shade-table th,.shade-table td {{ border-bottom:1px solid var(--line); padding:8px 10px; text-align:center; font-size:13px; }}
.shade-table th:first-child,.shade-table td:first-child {{ text-align:left; }}
.shade-table th {{ color:var(--accent); font-weight:600; background:rgba(44,107,90,.06); }}
.muted {{ color:var(--muted); font-weight:400; font-size:13px; }}
.footer-note {{ font-size:12px; color:var(--muted); margin-top:8px; }}
{shared_css}
@media (max-width:860px) {{
  .shell {{ grid-template-columns:1fr; }}
  .sidenav {{ position:relative; height:auto; display:flex; flex-wrap:wrap; gap:4px; border-right:0; border-bottom:1px solid var(--line); }}
  .sidenav a {{ margin:0; }}
  .cm-bar-row {{ grid-template-columns:1fr; }}
  .look-grid,.look-meter,.band-row {{ grid-template-columns:1fr; }}
  .pat-row {{ grid-template-columns:1fr; }}
  h1 {{ font-size:24px; }}
}}
{verify_ui['css']}
/* 再压一次：保证人机核验视觉与 4087 一致，不被 embed 黄底覆盖 */
.uv-banner{{margin:14px 0 10px;padding:12px 14px;border:1px solid #e8b4b0;border-left:4px solid #c45c54;border-radius:8px;background:linear-gradient(180deg,#fff6f5 0%,#fffaf8 100%);color:#5a2e2a;}}
.uv-iterate-btn{{appearance:none;border:1px solid #c45c54;background:#c45c54;color:#fff;border-radius:8px;padding:7px 12px;font-size:13px;cursor:pointer;}}
.uv-verify-btn{{appearance:none;border:1px solid #c45c54;background:#fff;color:#c45c54;border-radius:6px;padding:3px 10px;font-size:12px;cursor:pointer;}}
</style>
</head>
<body {verify_ui['body_attrs']}>
<div class="shell">
<aside class="sidenav">
  <div class="brand">CLASS · 多人精要</div>
  {''.join(nav_items)}
</aside>
<div class="wrap">
  <header class="hero">
    <p class="eyebrow">CLASS FEEDBACK · 班级多人</p>
    <h1>班级多人批改·解释精要</h1>
    <p class="sub">{_md_inline_to_html(sub)}</p>
  </header>

  {class_parts.get("expect") or ""}
  {class_parts.get("ladder") or ""}

  <section class="panel" id="sec-class">
    <div class="panel-head"><h2>班级本次作业批改报告</h2></div>
    <p class="hint">学情、共性与个性、前序变化、认知分区和配对建议。</p>
    <div class="class-report">{class_parts.get("rest") or ""}</div>
  </section>

  <section id="sec-students">
    <div class="panel" style="padding-bottom:8px;margin-bottom:10px;">
      <div class="panel-head"><h2>各学生本次报告</h2></div>
      <p class="hint">每人开头是本次期望水准。下面的分点对照这个水准，写明该生更接近哪一档、差距在哪里、下一步如何保持或进一步提高。点击可跳到该生逐页留存。</p>
    </div>
    {''.join(stu_sections) or '<div class="panel"><p>暂无学生报告</p></div>'}
  </section>

  {overview_html}

  <section id="sec-pages">
    <div class="panel" style="padding-bottom:8px;margin-bottom:10px;">
      <div class="panel-head"><h2>逐页留存（按学生）</h2></div>
      <p class="hint">与单人精要同款三步留存；多人按学生分段，便于对照批改图核验。</p>
    </div>
    {''.join(page_by_student) or '<div class="panel"><p>暂无逐页数据</p></div>'}
    <p class="footer-note">用语对齐课标与素养量规语境。错别字、粗心算错不作认知盲区。</p>
  </section>
</div>
</div>
{verify_ui['tail']}
<script>
  document.querySelectorAll('.sidenav a[data-goto]').forEach(function(a){{
    a.addEventListener('click', function(e){{
      var id = a.getAttribute('data-goto');
      var el = id && document.getElementById(id);
      if (el) {{ e.preventDefault(); el.scrollIntoView({{behavior:'smooth', block:'start'}}); }}
    }});
  }});
  document.querySelectorAll('.overview-visual').forEach(function(box){{
    var tabs=box.querySelectorAll('.tab');
    var panes=box.querySelectorAll('.view-pane');
    tabs.forEach(function(tab){{
      tab.addEventListener('click', function(){{
        var v=tab.getAttribute('data-view');
        tabs.forEach(function(t){{ t.classList.toggle('active', t===tab); }});
        panes.forEach(function(p){{ p.classList.toggle('active', p.getAttribute('data-view')===v); }});
      }});
    }});
  }});
  document.querySelectorAll('.view-pane[data-view="cross"]').forEach(function(box){{
    var subs=box.querySelectorAll('.cross-subtab');
    var panes=box.querySelectorAll('.cross-pane');
    subs.forEach(function(tab){{
      tab.addEventListener('click', function(){{
        var v=tab.getAttribute('data-cross-view');
        subs.forEach(function(t){{ t.classList.toggle('active', t===tab); }});
        panes.forEach(function(p){{ p.classList.toggle('active', p.getAttribute('data-cross-view')===v); }});
      }});
    }});
  }});
  document.addEventListener('click', function(e){{
    var t = e.target;
    if(!t) return;
    if(t.classList && t.classList.contains('loc-toggle')){{
      e.preventDefault();
      var wrap = t.closest('.loc-wrap');
      if(!wrap) return;
      var folded = wrap.getAttribute('data-folded') !== '0';
      var shortEl = wrap.querySelector('.loc-short');
      var allEl = wrap.querySelector('.loc-all');
      if(folded){{
        if(shortEl) shortEl.hidden = true;
        if(allEl) allEl.hidden = false;
        wrap.setAttribute('data-folded','0');
        t.setAttribute('aria-expanded','true');
        t.textContent = '收起';
      }} else {{
        if(shortEl) shortEl.hidden = false;
        if(allEl) allEl.hidden = true;
        wrap.setAttribute('data-folded','1');
        t.setAttribute('aria-expanded','false');
        var n = (allEl && allEl.querySelectorAll('.loc-jump').length) || 0;
        t.textContent = '展开全部 ' + n;
      }}
      return;
    }}
  }});
</script>
</body>
</html>
"""


def is_class_multi_excerpt_card(content: str = "", title: str = "") -> bool:
    text = content or ""
    t = title or ""
    return (
        "班级多人" in t
        or "<!--nkcn_class_multi_meta:" in text
        or "<!--nkcn_grading_card:批改·解释精要|class_multi|" in text  # 旧正文尾标兼容
        or ("班级多人批改·解释精要" in text)
    )


def finalize_class_multi_outputs(
    *,
    paths: Dict[str, str],
    manifest: Dict[str, Any],
    class_map: Dict[str, Any],
    subject: str,
    subject_label: str,
    material_label: str = "",
    prior_student_memories: Optional[Dict[str, Any]] = None,
    prior_class_reports: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    out_dir = os.path.join(paths.get("pass2_report") or paths.get("base") or "", "class_multi")
    os.makedirs(out_dir, exist_ok=True)
    pass1_dir = paths.get("pass1_json") or ""
    # 卷面姓名 > 配置名单 > 学生n；同步回 manifest / sessions
    class_map = enrich_class_map_student_names(paths=paths, class_map=class_map, use_vision_fallback=True)
    if isinstance(manifest, dict):
        manifest["class_multi"] = {
            **(manifest.get("class_multi") if isinstance(manifest.get("class_multi"), dict) else {}),
            **class_map,
        }
    try:
        sessions_path = os.path.join(paths.get("base") or "", "sessions.json")
        if os.path.isfile(sessions_path):
            sm = safe_json_load(sessions_path)
            sm = apply_enriched_names_to_session_map(sm if isinstance(sm, dict) else None, class_map)
            if isinstance(sm, dict):
                safe_json_dump(sessions_path, sm)
    except Exception:
        pass
    hw = int(class_map.get("homework_index") or 1)
    username = str(manifest.get("username") or "").strip()
    subject_n = _normalize_subject_code(subject) or str(subject or "unknown").strip() or "unknown"
    key = f"{class_map.get('class_id')}::{subject_n}"
    analysis_id = str(manifest.get("analysis_id") or "").strip()
    run_id = str(manifest.get("run_id") or "current").strip() or "current"
    ctx = manifest.get("feedback_context") if isinstance(manifest.get("feedback_context"), dict) else {}
    material_type = str(ctx.get("material_type") or "homework")
    user_verification = None
    verify_suggestions: Dict[str, Any] = {}
    try:
        from .result_cards import _named_json, _sample_id
        from .verify_suggestions import suggestions_for_html
        sample_id = _sample_id(analysis_id) if analysis_id else ""
        if sample_id:
            report = _named_json(paths.get("pass2_report") or "", subject, sample_id, "_report.json")
            if isinstance(report, dict) and isinstance(report.get("user_verification"), dict):
                user_verification = report.get("user_verification")
        verify_suggestions = suggestions_for_html(paths) or {}
    except Exception:
        pass

    # 从头重做：开链首文件清空本班本学科前序，后续次第再自然累积
    if username and manifest.get("class_multi_reset_prior"):
        try:
            clear_notebook_class_prior(
                username,
                class_id=str(class_map.get("class_id") or ""),
                subject_code=subject,
            )
        except Exception:
            pass
        try:
            manifest["class_multi_reset_prior"] = False
            mpath = paths.get("manifest") or ""
            if mpath:
                safe_json_dump(mpath, manifest)
        except Exception:
            pass

    # 本子级共享记忆优先（跨多次作业文件），参数传入次之；刚 reset 时为空
    merged_prior: Dict[str, Any] = {}
    if username:
        merged_prior.update(load_notebook_class_memories(username) or {})
    if isinstance(prior_student_memories, dict):
        for k, v in prior_student_memories.items():
            if k not in merged_prior:
                merged_prior[k] = v
    prior_pack = None
    for k in _subject_memory_key_candidates(class_map.get("class_id"), subject_n or subject):
        if isinstance(merged_prior.get(k), dict):
            prior_pack = merged_prior.get(k)
            break
    prior_bucket = ((prior_pack or {}).get("students") or {}) if prior_pack else {}
    # 注意：各次提交人数/名单可能不一致，不再用前序同序位姓名回填未识别位

    student_reports = []
    for stu in class_map.get("students") or []:
        sid = str(stu.get("student_index"))
        prior = prior_bucket.get(sid) if isinstance(prior_bucket.get(sid), dict) else None
        student_reports.append(
            build_student_assignment_report(
                student=stu,
                class_map=class_map,
                pass1_dir=pass1_dir,
                prior_memory=prior,
                homework_index=hw,
            )
        )
    student_reports = enrich_student_reports_with_peer_horizontal(student_reports)
    class_expectation = ""
    try:
        from .semantic_feedback_brief import compose_expectation_pack

        pack = compose_expectation_pack(
            username=username,
            subject_label=subject_label,
            material_label=material_label,
            filename=str((manifest.get("selected_files") or [""])[0] or ""),
            class_map=class_map,
            student_reports=student_reports,
        )
        class_expectation = str(pack.get("class_markdown") or "")
        by_student = pack.get("by_student") if isinstance(pack.get("by_student"), dict) else {}
        for report in student_reports:
            text = str(by_student.get(str(report.get("student_index"))) or "").strip()
            if text:
                report["expectation"] = text
    except Exception as exc:
        print(f"[class_multi] expectation pack fail: {exc}", flush=True)
    try:
        student_reports = enrich_student_reports_with_llm(
            student_reports,
            class_map=class_map,
            subject_label=subject_label,
            trace_dir=out_dir,
        )
    except Exception:
        pass
    _attach_score_series(student_reports, prior_bucket, hw)
    # 前序班级报告（本子共享）+ 学生历史摘要，供纵向比对（重要信号，非全文）
    prior_reports = list(prior_class_reports or [])
    if username:
        shared_reports_path = os.path.join(
            os.path.dirname(notebook_class_memory_path(username)),
            "class_reports.json",
        )
        if os.path.isfile(shared_reports_path):
            shared_reports = safe_json_load(shared_reports_path)
            if isinstance(shared_reports, dict):
                for item in shared_reports.get(key) or []:
                    if int(item.get("homework_index") or 0) < hw:
                        prior_reports.append(item)
    if not prior_reports and prior_bucket:
        # 无班级级前序时，用各生前序要点合成弱信号（仍作 highlights，不进全文）
        by_hw: Dict[int, List[str]] = {}
        for sid, stu_mem in prior_bucket.items():
            if not isinstance(stu_mem, dict):
                continue
            for h in (stu_mem.get("history") or []):
                if not isinstance(h, dict):
                    continue
                h_idx = int(h.get("homework_index") or 0)
                if h_idx < hw:
                    by_hw.setdefault(h_idx, []).extend(
                        _theme_tokens_from_points(h.get("points") or [], limit=2)
                    )
        for h_idx in sorted(by_hw.keys())[-3:]:
            themes = []
            seen = set()
            for t in by_hw[h_idx]:
                if t in seen:
                    continue
                seen.add(t)
                themes.append(t)
            prior_reports.append({
                "homework_index": h_idx,
                "summary": "；".join(themes[:5]),
                "highlights": [f"班内曾关注：{t}" for t in themes[:5]],
            })
    class_report = build_class_assignment_report(
        class_map=class_map,
        student_reports=student_reports,
        subject_label=subject_label,
        prior_class_reports=prior_reports,
        material_label=material_label,
        prior_student_histories=prior_bucket,
        class_expectation=class_expectation,
        trace_dir=out_dir,
    )
    update_student_memory_portraits(
        out_dir=out_dir,
        class_map=class_map,
        student_reports=student_reports,
        subject=subject,
        username=username,
    )
    filename = (manifest.get("selected_files") or [""])[0]
    excerpt_md = build_class_excerpt_card_markdown(
        filename=filename,
        class_map=class_map,
        student_reports=student_reports,
        class_report=class_report,
        material_label=material_label,
        pass1_dir=pass1_dir,
        subject=subject,
        material_type=material_type,
    )
    artifact = {
        "class_map": class_map,
        "student_reports": student_reports,
        "class_report": class_report,
        "excerpt_markdown": excerpt_md,
        "filename": filename,
        "material_label": material_label,
        "memories_key": key,
        "analysis_id": analysis_id,
        "run_id": run_id,
        "material_type": material_type,
        "subject": subject,
        "subject_label": subject_label,
        "pass1_json": pass1_dir,
        "user_verification": user_verification,
        "verify_suggestions": verify_suggestions,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    safe_json_dump(os.path.join(out_dir, "class_assignment_bundle.json"), artifact)
    safe_json_dump(os.path.join(out_dir, "class_report.json"), class_report)
    safe_json_dump(os.path.join(out_dir, f"student_reports_hw{hw}.json"), {"students": student_reports})
    (Path(out_dir) / "excerpt_card.md").write_text(excerpt_md, encoding="utf-8")
    try:
        (Path(out_dir) / "excerpt_card.html").write_text(
            build_class_multi_excerpt_html(
                artifact,
                analysis_id=analysis_id,
                run_id=run_id,
                user_verification=user_verification if isinstance(user_verification, dict) else None,
                verify_suggestions=verify_suggestions,
                material_type=material_type,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    # 班级报告也写入本子共享，供后续次第纵向引用
    if username:
        shared_reports_path = os.path.join(
            os.path.dirname(notebook_class_memory_path(username)),
            "class_reports.json",
        )
        shared_reports = safe_json_load(shared_reports_path) if os.path.isfile(shared_reports_path) else {}
        if not isinstance(shared_reports, dict):
            shared_reports = {}
        lst = list(shared_reports.get(key) or [])
        lst = [x for x in lst if int(x.get("homework_index") or 0) != hw]
        lst.append({
            "homework_index": hw,
            "summary": class_report.get("summary"),
            "highlights": class_report.get("highlights") or [],
            "markdown": class_report.get("markdown"),
            "filename": filename,
        })
        lst.sort(key=lambda x: int(x.get("homework_index") or 0))
        shared_reports[key] = lst
        safe_json_dump(shared_reports_path, shared_reports)
    manifest["class_multi"] = {
        **(manifest.get("class_multi") if isinstance(manifest.get("class_multi"), dict) else {}),
        **class_map,
        "outputs_dir": out_dir,
        "excerpt_ready": True,
    }
    return artifact


# 材料设置中文名 ↔ 流水线 subject code；旧记忆键可能仍用中文
_SUBJECT_CODE_ALIASES = {
    "数学": "math",
    "math": "math",
    "mathematics": "math",
    "语文": "chinese",
    "chinese": "chinese",
    "语文科": "chinese",
    "英语": "english",
    "english": "english",
    "物理": "physics",
    "physics": "physics",
    "化学": "chemistry",
    "chemistry": "chemistry",
    "生物": "biology",
    "biology": "biology",
    "历史": "history",
    "history": "history",
    "地理": "geography",
    "geography": "geography",
    "政治": "politics",
    "politics": "politics",
}
_SUBJECT_CODE_TO_CN = {
    "math": "数学",
    "chinese": "语文",
    "english": "英语",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "history": "历史",
    "geography": "地理",
    "politics": "政治",
}


def _normalize_subject_code(raw: str) -> str:
    """材料设置「数学/语文/英语…」与流水线记忆键 math/chinese/english… 对齐。"""
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    if s in _SUBJECT_CODE_ALIASES:
        return _SUBJECT_CODE_ALIASES[s]
    for token, code in (
        ("数学", "math"),
        ("语文", "chinese"),
        ("英语", "english"),
        ("物理", "physics"),
        ("化学", "chemistry"),
        ("生物", "biology"),
        ("历史", "history"),
        ("地理", "geography"),
        ("政治", "politics"),
    ):
        if token in s:
            return code
    return s


def _subject_memory_key_candidates(class_id: Any, subject_code: Any) -> List[str]:
    """同班同科记忆/报告键：规范 code + 历史中文名 + 原始未归一化串。"""
    cid = str(class_id or "").strip()
    raw = str(subject_code or "").strip()
    code = _normalize_subject_code(raw) or (raw.lower() if raw else "unknown") or "unknown"
    keys: List[str] = []
    for part in (code, _SUBJECT_CODE_TO_CN.get(code, ""), raw, raw.lower()):
        p = str(part or "").strip()
        if not p or not cid:
            continue
        k = f"{cid}::{p}"
        if k not in keys:
            keys.append(k)
    return keys


def _subject_from_saved_material(saved: Dict[str, Any], filename: str, description: str = "") -> str:
    overrides = (saved or {}).get("feedback_overrides") if isinstance(saved, dict) else {}
    if not isinstance(overrides, dict):
        overrides = {}
    for k in ("subject_code", "subject", "学科"):
        if overrides.get(k):
            return _normalize_subject_code(str(overrides.get(k)))
    blob = f"{filename} {description}"
    return _normalize_subject_code(blob) if any(
        t in blob for t in ("语文", "数学", "英语", "物理", "化学", "生物")
    ) else ""


def _portrait_sig(saved: Dict[str, Any]) -> Tuple[str, ...]:
    overrides = (saved or {}).get("feedback_overrides") if isinstance(saved, dict) else {}
    if not isinstance(overrides, dict):
        overrides = {}
    keys = ("stage", "grade", "subject", "subject_code", "material_type", "学段", "年级", "学科", "材料类型")
    return tuple(str(overrides.get(k) or "") for k in keys)


def discover_class_multi_siblings(
    username: str,
    *,
    class_id: str,
    subject_code: str,
    current_filename: str,
) -> Dict[str, Any]:
    """从最新批改配置卡中找同班同科其它次第的多人材料，并比对材料设置一致性。"""
    from app_chat.grading_config_card import find_latest_grading_config_card, parse_grading_config
    from app_chat.feedback_material_settings import load_saved_material_settings

    card = find_latest_grading_config_card(username)
    if not card:
        return {"siblings": [], "current": None, "warnings": ["未找到批改配置卡"]}
    data, errors = parse_grading_config(card.content or "")
    if not data:
        return {"siblings": [], "current": None, "warnings": errors or ["配置卡解析失败"]}

    subject_code_n = str(subject_code or "").strip().lower()
    siblings = []
    current = None
    portraits = []
    for mat in data.get("materials") or []:
        if not is_class_multi_material(mat):
            continue
        if str(mat.get("class_id") or "").strip() != str(class_id).strip():
            continue
        fn = mat.get("filename") or ""
        saved, _exists = {}, False
        try:
            saved, _exists = load_saved_material_settings(username, fn)
        except Exception:
            saved, _exists = {}, False
        subj = _subject_from_saved_material(saved or {}, fn, mat.get("description") or "")
        if subject_code_n and subj and subj != subject_code_n:
            continue
        # 当前文件有明确学科时：未保存学科的同班材料不列入「同科」列表，避免串科
        if subject_code_n and not subj and fn != current_filename:
            continue
        # portrait_sig 用 list 写入响应（JSON 友好）；比对时再转成 tuple
        sig = list(_portrait_sig(saved or {}))
        item = {
            "filename": fn,
            "homework_index": int(mat.get("homework_index") or 0),
            "student_count": mat.get("student_count"),
            "pages_per_assignment": mat.get("pages_per_assignment"),
            "class_id": mat.get("class_id"),
            "roster": mat.get("roster") or [],
            "subject_code": subj or subject_code_n,
            "material_saved": bool(_exists),
            "portrait_sig": sig,
        }
        if fn == current_filename:
            current = item
        else:
            siblings.append(item)
        portraits.append(item)

    siblings.sort(key=lambda x: int(x.get("homework_index") or 0))
    warnings = []
    sigs = {tuple(p.get("portrait_sig") or ()) for p in portraits}
    if len(sigs) > 1:
        detail = "；".join(
            f"{p.get('filename')}=学段/年级/学科/类型{p.get('portrait_sig')}" for p in portraits
        )
        warnings.append(
            "同班同科多次作业的材料设置尚未统一（学段/年级/学科/材料类型）。"
            "只改当前这次可直接开始；若要「按次第依次完成多次」，建议先对下列文件右键统一设置。"
            f"明细：{detail}"
        )
    return {
        "config_card_id": card.cid,
        "current": current,
        "siblings": siblings,
        "all_same_class_subject": sorted(portraits, key=lambda x: int(x.get("homework_index") or 0)),
        "warnings": warnings,
    }


def _prior_completed_homework_indexes(
    username: str,
    *,
    class_id: str,
    subject_code: str,
    before_homework_index: int,
) -> List[Dict[str, Any]]:
    """检测本班本学科、当前次第之前是否已有完成的批改记忆/班级报告。"""
    hw_cur = int(before_homework_index or 0)
    if hw_cur <= 1 or not username or not class_id:
        return []
    subject = _normalize_subject_code(subject_code) or "unknown"
    key_candidates = _subject_memory_key_candidates(class_id, subject_code)
    found: Dict[int, Dict[str, Any]] = {}
    shared = load_notebook_class_memories(username) or {}
    buckets = []
    if isinstance(shared, dict):
        for k in key_candidates:
            b = shared.get(k)
            if isinstance(b, dict):
                buckets.append(b)
        # 同班任意学科键兜底：仅当 class_id 前缀匹配且只有一个候选桶
        if not buckets:
            prefix = f"{class_id}::"
            same_class = [v for kk, v in shared.items() if str(kk).startswith(prefix) and isinstance(v, dict)]
            if len(same_class) == 1:
                buckets = same_class
    for bucket in buckets:
        for sid, stu in (bucket.get("students") or {}).items():
            if not isinstance(stu, dict):
                continue
            for h in stu.get("history") or []:
                if not isinstance(h, dict):
                    continue
                idx = int(h.get("homework_index") or 0)
                if 0 < idx < hw_cur:
                    slot = found.setdefault(idx, {
                        "homework_index": idx,
                        "source": "student_memory",
                        "student_hits": 0,
                    })
                    slot["student_hits"] = int(slot.get("student_hits") or 0) + 1
    try:
        reports_path = os.path.join(
            os.path.dirname(notebook_class_memory_path(username)),
            "class_reports.json",
        )
        if os.path.isfile(reports_path):
            reports = safe_json_load(reports_path)
            if isinstance(reports, dict):
                report_lists = []
                for k in key_candidates:
                    lst = reports.get(k)
                    if isinstance(lst, list):
                        report_lists.append(lst)
                if not report_lists:
                    prefix = f"{class_id}::"
                    same = [v for kk, v in reports.items() if str(kk).startswith(prefix) and isinstance(v, list)]
                    if len(same) == 1:
                        report_lists = same
                for lst in report_lists:
                    for item in lst:
                        if not isinstance(item, dict):
                            continue
                        idx = int(item.get("homework_index") or 0)
                        if 0 < idx < hw_cur:
                            slot = found.setdefault(idx, {
                                "homework_index": idx,
                                "source": "class_report",
                                "student_hits": 0,
                            })
                            slot["has_class_report"] = True
                            if slot.get("source") == "student_memory":
                                slot["source"] = "memory+report"
    except Exception:
        pass
    return [found[k] for k in sorted(found.keys())]


def clear_notebook_class_prior(
    username: str,
    *,
    class_id: str,
    subject_code: str,
) -> bool:
    """从头重做：清空本班本学科共享记忆与班级报告前序。"""
    if not username or not class_id:
        return False
    keys = set(_subject_memory_key_candidates(class_id, subject_code))
    changed = False
    try:
        path = notebook_class_memory_path(username)
        store = load_notebook_class_memories(username) or {}
        if isinstance(store, dict):
            for key in list(keys):
                if key in store:
                    store.pop(key, None)
                    changed = True
            if changed:
                safe_json_dump(path, store)
        reports_path = os.path.join(os.path.dirname(path), "class_reports.json")
        if os.path.isfile(reports_path):
            reports = safe_json_load(reports_path)
            if isinstance(reports, dict):
                r_changed = False
                for key in list(keys):
                    if key in reports:
                        reports.pop(key, None)
                        r_changed = True
                if r_changed:
                    safe_json_dump(reports_path, reports)
                    changed = True
    except Exception:
        return False
    return changed


def plan_class_multi_grading(username: str, filename: str) -> Dict[str, Any]:
    """开改弹窗用：当前文件是否班级多人 + 同班同科多次列表。"""
    from app_chat.grading_config_card import resolve_material_for_filename
    from app_chat.feedback_material_settings import load_saved_material_settings

    mat = resolve_material_for_filename(username, filename)
    if not mat or not is_class_multi_material(mat):
        return {
            "is_class_multi": False,
            "filename": filename,
            "assignments": [],
            "warnings": [],
            "prior_completed": [],
            "has_prior_results": False,
        }
    saved, _ = {}, False
    try:
        saved, _ = load_saved_material_settings(username, filename)
    except Exception:
        saved = {}
    subject = _subject_from_saved_material(saved or {}, filename, mat.get("description") or "")
    disc = discover_class_multi_siblings(
        username,
        class_id=str(mat.get("class_id") or ""),
        subject_code=subject,
        current_filename=filename,
    )
    assignments = list(disc.get("all_same_class_subject") or [])
    if not any(a.get("filename") == filename for a in assignments):
        assignments.append({
            "filename": filename,
            "homework_index": int(mat.get("homework_index") or 0),
            "student_count": mat.get("student_count"),
            "pages_per_assignment": mat.get("pages_per_assignment"),
            "class_id": mat.get("class_id"),
            "roster": mat.get("roster") or [],
            "subject_code": subject,
        })
        assignments.sort(key=lambda x: int(x.get("homework_index") or 0))
    hw = int(mat.get("homework_index") or 0)
    prior_completed = _prior_completed_homework_indexes(
        username,
        class_id=str(mat.get("class_id") or ""),
        subject_code=subject,
        before_homework_index=hw,
    )
    # 标记各 assignment 是否已有完成记忆（供前端列表展示）
    done_idxs = {int(p.get("homework_index") or 0) for p in prior_completed}
    # 当前次第若已写入记忆，也标已完成
    try:
        shared = load_notebook_class_memories(username) or {}
        key_cands = _subject_memory_key_candidates(mat.get("class_id"), subject)
        buckets = []
        if isinstance(shared, dict):
            for k in key_cands:
                b = shared.get(k)
                if isinstance(b, dict):
                    buckets.append(b)
        for bucket in buckets:
            for stu in (bucket.get("students") or {}).values():
                if not isinstance(stu, dict):
                    continue
                for h in stu.get("history") or []:
                    done_idxs.add(int((h or {}).get("homework_index") or 0))
    except Exception:
        pass
    for a in assignments:
        a["has_completed_result"] = int(a.get("homework_index") or 0) in done_idxs
    return {
        "is_class_multi": True,
        "filename": filename,
        "class_id": mat.get("class_id"),
        "homework_index": mat.get("homework_index"),
        "student_count": mat.get("student_count"),
        "pages_per_assignment": mat.get("pages_per_assignment"),
        "roster": mat.get("roster") or [],
        "subject_code": subject,
        "assignments": assignments,
        "warnings": disc.get("warnings") or [],
        "config_card_id": disc.get("config_card_id"),
        "prior_completed": prior_completed,
        "has_prior_results": bool(prior_completed),
    }
