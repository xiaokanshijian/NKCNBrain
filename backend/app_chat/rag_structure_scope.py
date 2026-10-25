# -*- coding: utf-8 -*-
"""
用户问题提到「第x章/节/小节」时，用 DocStructure 定位页码范围，
供 RAG 相似检索收窄（个数与篇幅不变）。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from app_chat import skills_store as store
from app_chat.socratic_probe import PROBE_MODEL_ABBR

# 门禁：问题里明确出现章/节/小节指称才触发（避免每问都多一次 LLM）
_STRUCTURE_REF_RE = re.compile(
    r"(?:"
    r"第\s*[零〇一二三四五六七八九十百两\d]+\s*[章节篇部]"
    r"|第\s*[零〇一二三四五六七八九十百两\d]+\s*小节"
    r"|Chapter\s*\d+"
    r")",
    re.I,
)

LOCATE_SYSTEM = """你是文档结构定位助手。根据用户问题与各文档的 DocStructure MAP，
判断问题聚焦到哪一章，以及是否进一步聚焦到节/小节。页码 1-based，与 MAP 的 p起-p止 一致，不要自行大幅扩页。

只输出 JSON，禁止前言后语、代码围栏：
{"scopes":[{
  "doc":"<文档名原样>",
  "focus":"chapter|section|subsection",
  "chapter_title":"<章标题>",
  "chapter_p0":201,
  "chapter_p1":256,
  "section_title":"",
  "section_p0":0,
  "section_p1":0,
  "subsection_title":"",
  "subsection_p0":0,
  "subsection_p1":0,
  "confidence":"high|mid|low"
}],"note":""}

规则：
1. 只问「第x章」：focus=chapter；section/subsection 的 p0、p1 填 0，title 留空。chapter 必须是该章整章页码。
2. 问到「第x章第x节」（或章内某一节）：focus=section。必须同时给出该节所属章的 chapter_p0-p1，以及该节 section_p0-p1。不要只给节、不给章。
3. 问到小节：focus=subsection。必须同时给出所属章、所属节、该小节三层页码。
4. 只勾选 1 个文档时，用户常不写文档名，归到该文档。勾选多个时，只为问题明确点名的文档出 scope。
5. 同一文档多个目标 → 多条 scopes。无法定位则 scopes=[]。
6. doc 必须用输入里的文档名。标题用 MAP 原文。
"""


def should_locate_structure_scope(
    message: str,
    file_list: Optional[List[str]] = None,
) -> bool:
    """门禁：问题含章/节指称，且勾选了至少一个非 zip 文档。"""
    text = (message or "").strip()
    if not text or not _STRUCTURE_REF_RE.search(text):
        return False
    docs = [
        f for f in (file_list or [])
        if f and not str(f).lower().endswith(".zip")
    ]
    return bool(docs)


def _load_structure_maps(
    username: str,
    file_list: List[str],
) -> List[Dict[str, str]]:
    from app_chat.doc_structure import parse_doc_structure_md

    out: List[Dict[str, str]] = []
    for fn in file_list:
        if not fn or str(fn).lower().endswith(".zip"):
            continue
        path = store.doc_structure_path(username, fn)
        if not os.path.isfile(path):
            continue
        try:
            raw = open(path, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        parsed = parse_doc_structure_md(raw)
        if not parsed:
            continue
        map_text = (parsed.get("map_text") or "").strip()
        if not map_text:
            continue
        # 控制长度，避免定位调用过重
        if len(map_text) > 12000:
            map_text = map_text[:12000] + "\n…(MAP truncated)"
        out.append({
            "doc": fn,
            "source": str(parsed.get("source") or ""),
            "confidence": str(parsed.get("confidence") or ""),
            "map": map_text,
        })
    return out


def _call_locate_model(system: str, user: str) -> str:
    from app_chat.scene_models import resolve_openai_cfg_from_abbr
    from app_chat.config.config_manager import config_manager

    cfg = resolve_openai_cfg_from_abbr(PROBE_MODEL_ABBR)
    headers = {"x-foo": "true"}
    model_name = str(cfg.get("model") or PROBE_MODEL_ABBR)
    try:
        mc = config_manager.get_model_config(PROBE_MODEL_ABBR)
        if mc:
            cur = mc.get_config() or {}
            if cur.get("default_headers"):
                headers = cur.get("default_headers")
            if cur.get("model_name"):
                model_name = str(cur.get("model_name"))
    except Exception:
        pass
    client = OpenAI(
        api_key=cfg.get("api_key"),
        base_url=cfg.get("base_url"),
        default_headers=headers,
        timeout=25.0,
    )
    rsp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=800,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return ((rsp.choices[0].message.content or "") if rsp.choices else "").strip()


def _align_doc(doc_raw: str, allowed_docs: List[str]) -> str:
    allowed_set = {d: d for d in allowed_docs}
    by_base = {os.path.basename(d): d for d in allowed_docs}
    by_stem = {
        os.path.splitext(os.path.basename(d))[0]: d for d in allowed_docs
    }
    doc = (
        allowed_set.get(doc_raw)
        or by_base.get(os.path.basename(doc_raw))
        or by_stem.get(os.path.splitext(os.path.basename(doc_raw))[0])
    )
    if not doc and len(allowed_docs) == 1:
        doc = allowed_docs[0]
    return doc or ""


def _pair(item: Dict[str, Any], k0: str, k1: str) -> Optional[Tuple[int, int]]:
    try:
        p0 = int(item.get(k0) or 0)
        p1 = int(item.get(k1) or 0)
    except Exception:
        return None
    if p0 <= 0 or p1 <= 0:
        return None
    if p1 < p0:
        p0, p1 = p1, p0
    return p0, p1


def _parse_scopes(
    raw: str,
    allowed_docs: List[str],
) -> List[Dict[str, Any]]:
    text = (raw or "").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return []
    scopes_in = obj.get("scopes") if isinstance(obj, dict) else None
    if not isinstance(scopes_in, list):
        return []

    out: List[Dict[str, Any]] = []
    for item in scopes_in:
        if not isinstance(item, dict):
            continue
        doc = _align_doc(str(item.get("doc") or "").strip(), allowed_docs)
        if not doc:
            continue
        # 新格式：chapter_p0/p1；兼容旧格式 p0/p1
        chapter = _pair(item, "chapter_p0", "chapter_p1") or _pair(item, "p0", "p1")
        if not chapter:
            continue
        focus = str(item.get("focus") or "").strip().lower()
        if focus not in ("chapter", "section", "subsection"):
            if _pair(item, "subsection_p0", "subsection_p1"):
                focus = "subsection"
            elif _pair(item, "section_p0", "section_p1"):
                focus = "section"
            else:
                focus = "chapter"
        section = _pair(item, "section_p0", "section_p1") if focus in ("section", "subsection") else None
        subsection = _pair(item, "subsection_p0", "subsection_p1") if focus == "subsection" else None
        if focus == "section" and not section:
            focus = "chapter"
        if focus == "subsection" and not subsection:
            focus = "section" if section else "chapter"
        # 不向外扩页。章界以模型给出的闭区间为准，对上本地 MAP 后再改成目录页码。
        cp0, cp1 = chapter
        out.append({
            "doc": doc,
            "focus": focus,
            "chapter": (cp0, cp1),
            "chapter_title": str(item.get("chapter_title") or item.get("matched") or "")[:120],
            "section": section,
            "section_title": str(item.get("section_title") or "")[:120],
            "subsection": subsection,
            "subsection_title": str(item.get("subsection_title") or "")[:120],
            "confidence": str(item.get("confidence") or "mid"),
            # 兼容旧日志字段
            "p0": cp0,
            "p1": cp1,
            "matched": str(item.get("chapter_title") or item.get("matched") or "")[:120],
        })
    return out


def _group_l1(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    cur_l2: Optional[Dict[str, Any]] = None
    for n in nodes:
        lv = int(n.get("level") or 0)
        if lv == 1:
            cur = {"node": n, "l2": []}
            groups.append(cur)
            cur_l2 = None
        elif lv == 2 and cur is not None:
            cur_l2 = {"node": n, "l3": []}
            cur["l2"].append(cur_l2)
        elif lv >= 3 and cur_l2 is not None:
            cur_l2["l3"].append(n)
    return groups


def _best_overlap(groups: List[Dict[str, Any]], p0: int, p1: int) -> Optional[Dict[str, Any]]:
    best = None
    best_score = -1
    for g in groups:
        a, b = int(g["node"]["p0"]), int(g["node"]["p1"])
        ov = max(0, min(b, p1) - max(a, p0) + 1)
        if ov > best_score:
            best_score = ov
            best = g
    return best if best_score > 0 else (groups[0] if len(groups) == 1 else None)


def _match_child(children: List[Dict[str, Any]], rng: Optional[Tuple[int, int]], title: str):
    if not children:
        return None, -1
    if rng:
        p0, p1 = rng
        best_i, best_ov = -1, -1
        for i, c in enumerate(children):
            node = c["node"] if isinstance(c, dict) and "node" in c else c
            a, b = int(node["p0"]), int(node["p1"])
            ov = max(0, min(b, p1) - max(a, p0) + 1)
            if ov > best_ov:
                best_ov, best_i = ov, i
        if best_i >= 0 and best_ov > 0:
            return children[best_i], best_i
    if title:
        t = title.strip()
        for i, c in enumerate(children):
            node = c["node"] if isinstance(c, dict) and "node" in c else c
            if t and t in (node.get("title") or ""):
                return c, i
    return None, -1


def enrich_plans(username: str, scopes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """用本地 DocStructure 补齐节列表、章首、相邻节，供配额取样。"""
    from app_chat.doc_structure import parse_doc_structure_md

    cache: Dict[str, List[Dict[str, Any]]] = {}
    plans: List[Dict[str, Any]] = []
    for s in scopes:
        doc = s["doc"]
        if doc not in cache:
            path = store.doc_structure_path(username, doc)
            nodes: List[Dict[str, Any]] = []
            if os.path.isfile(path):
                try:
                    raw = open(path, "r", encoding="utf-8", errors="ignore").read()
                    parsed = parse_doc_structure_md(raw)
                    nodes = (parsed or {}).get("nodes") or []
                except Exception:
                    nodes = []
            cache[doc] = _group_l1(nodes)
        groups = cache[doc]
        cp0, cp1 = s["chapter"]
        g = _best_overlap(groups, cp0, cp1)
        l2_list = []
        if g:
            # 以本地 MAP 的章页为准，不再向外扩，避免把上一章末页当成章首
            node = g["node"]
            cp0, cp1 = int(node["p0"]), int(node["p1"])
            for block in g["l2"]:
                n2 = block["node"]
                l3 = [
                    (int(x["p0"]), int(x["p1"]), x.get("title") or "")
                    for x in block.get("l3") or []
                ]
                l2_list.append({
                    "p0": int(n2["p0"]),
                    "p1": int(n2["p1"]),
                    "title": n2.get("title") or "",
                    "l3": l3,
                })
        intro = None
        if l2_list and l2_list[0]["p0"] > cp0:
            # 右端闭到第一节首页：该页上半常常仍是章首，标题多在中下部才出现
            intro = (cp0, min(cp1, l2_list[0]["p0"]))

        focus_l2 = None
        focus_l2_i = -1
        if s["focus"] in ("section", "subsection") and l2_list:
            wrapped = [{"node": {"p0": x["p0"], "p1": x["p1"], "title": x["title"]}} for x in l2_list]
            hit, focus_l2_i = _match_child(wrapped, s.get("section"), s.get("section_title") or "")
            if hit is not None and focus_l2_i >= 0:
                focus_l2 = l2_list[focus_l2_i]
                s["section"] = (focus_l2["p0"], focus_l2["p1"])
                s["section_title"] = focus_l2["title"]

        focus_l3 = None
        focus_l3_i = -1
        if s["focus"] == "subsection" and focus_l2 and focus_l2.get("l3"):
            l3_wrap = [{"node": {"p0": a, "p1": b, "title": t}} for a, b, t in focus_l2["l3"]]
            hit3, focus_l3_i = _match_child(l3_wrap, s.get("subsection"), s.get("subsection_title") or "")
            if hit3 is not None and focus_l3_i >= 0:
                a, b, t = focus_l2["l3"][focus_l3_i]
                focus_l3 = (a, b, t)
                s["subsection"] = (a, b)
                s["subsection_title"] = t

        adj_l2 = []
        if focus_l2_i >= 0:
            if focus_l2_i - 1 >= 0:
                prev = l2_list[focus_l2_i - 1]
                adj_l2.append((prev["p0"], prev["p1"], prev["title"]))
            if focus_l2_i + 1 < len(l2_list):
                nxt = l2_list[focus_l2_i + 1]
                adj_l2.append((nxt["p0"], nxt["p1"], nxt["title"]))

        section_intro = None
        adj_l3 = []
        if focus_l3 and focus_l2:
            if focus_l2["p0"] < focus_l3[0]:
                section_intro = (focus_l2["p0"], focus_l3[0])
            if focus_l3_i - 1 >= 0:
                adj_l3.append(focus_l2["l3"][focus_l3_i - 1])
            if focus_l3_i + 1 < len(focus_l2["l3"]):
                adj_l3.append(focus_l2["l3"][focus_l3_i + 1])

        plans.append({
            "doc": doc,
            "focus": s["focus"],
            "chapter": (cp0, cp1),
            "chapter_title": s.get("chapter_title") or "",
            "intro": intro,
            "l2": [(x["p0"], x["p1"], x["title"]) for x in l2_list],
            "section": s.get("section"),
            "section_title": s.get("section_title") or "",
            "subsection": s.get("subsection"),
            "subsection_title": s.get("subsection_title") or "",
            "section_intro": section_intro,
            "adjacent_l2": adj_l2,
            "adjacent_l3": adj_l3,
            "confidence": s.get("confidence") or "mid",
        })
        print(
            f"[RAG-Scope] plan {doc} focus={s['focus']} "
            f"chapter=p{cp0}-p{cp1} l2={len(l2_list)} intro={intro} "
            f"section={s.get('section')} subsection={s.get('subsection')}",
            flush=True,
        )
    return plans


def scopes_to_page_map(
    scopes: List[Dict[str, Any]],
) -> Dict[str, List[Tuple[int, int]]]:
    """doc_name -> 章级页码闭区间（取样池）。"""
    m: Dict[str, List[Tuple[int, int]]] = {}
    for s in scopes:
        doc = s["doc"]
        p0, p1 = s["chapter"] if "chapter" in s and isinstance(s["chapter"], tuple) else (s["p0"], s["p1"])
        m.setdefault(doc, []).append((int(p0), int(p1)))
    return m


_PAGE_IN_TEXT_RE = re.compile(r"第\s*(\d+)\s*页")


def pages_of_segment(doc) -> List[int]:
    pages: List[int] = []
    meta = getattr(doc, "metadata", None) or {}
    if meta.get("page") is not None:
        try:
            pages.append(int(meta["page"]) + 1)
        except Exception:
            pass
    content = getattr(doc, "page_content", None) or ""
    for m in _PAGE_IN_TEXT_RE.finditer(content):
        try:
            pages.append(int(m.group(1)))
        except Exception:
            pass
    seen = set()
    out = []
    for p in pages:
        if p > 0 and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _seg_fp(doc) -> str:
    return (getattr(doc, "page_content", None) or "")[:240]


def _in_range(doc, p0: int, p1: int) -> bool:
    return any(p0 <= p <= p1 for p in pages_of_segment(doc))


def _spread_pick(cands: List[Any], n: int, used: set) -> List[Any]:
    fresh = [d for d in cands if _seg_fp(d) and _seg_fp(d) not in used]
    if n <= 0 or not fresh:
        return []
    fresh.sort(key=lambda d: (pages_of_segment(d)[:1] or [10**9], _seg_fp(d)))
    if len(fresh) <= n:
        for d in fresh:
            used.add(_seg_fp(d))
        return fresh
    picked = []
    if n == 1:
        idxs = [0]
    else:
        idxs = []
        for i in range(n):
            idxs.append(int(round(i * (len(fresh) - 1) / (n - 1))))
    seen_i = set()
    for i in idxs:
        if i in seen_i:
            continue
        seen_i.add(i)
        d = fresh[i]
        fp = _seg_fp(d)
        if fp in used:
            continue
        used.add(fp)
        picked.append(d)
    if len(picked) < n:
        for d in fresh:
            if len(picked) >= n:
                break
            fp = _seg_fp(d)
            if fp in used:
                continue
            used.add(fp)
            picked.append(d)
    return picked


def _alloc_even(n_buckets: int, k: int, weights: Optional[List[int]] = None) -> List[int]:
    if n_buckets <= 0 or k <= 0:
        return [0] * max(0, n_buckets)
    if k >= n_buckets:
        counts = [1] * n_buckets
        left = k - n_buckets
        order = list(range(n_buckets))
        if weights and len(weights) == n_buckets:
            order.sort(key=lambda i: (-weights[i], i))
        i = 0
        while left > 0:
            counts[order[i % n_buckets]] += 1
            left -= 1
            i += 1
        return counts
    # 槽位少于桶：头尾必留，中间均匀挑
    idxs = [0, n_buckets - 1] if n_buckets > 1 else [0]
    mid_need = k - len(set(idxs))
    if mid_need > 0 and n_buckets > 2:
        for i in range(1, mid_need + 1):
            idxs.append(int(round(i * (n_buckets - 1) / (mid_need + 1))))
    idxs = sorted(set(idxs))[:k]
    counts = [0] * n_buckets
    for i in idxs:
        counts[i] = 1
    return counts


def _quotas_for_plan(plan: Dict[str, Any], k: int) -> List[Tuple[str, int, int, int]]:
    """返回 [(label, p0, p1, count), ...]。"""
    focus = plan.get("focus") or "chapter"
    cp0, cp1 = plan["chapter"]
    intro = plan.get("intro")
    l2 = plan.get("l2") or []

    if focus == "chapter":
        section_buckets: List[Tuple[str, int, int, int]] = []
        if l2:
            for p0, p1, title in l2:
                section_buckets.append(
                    (f"节:{title}"[:40], p0, p1, max(1, p1 - p0 + 1))
                )
        else:
            section_buckets.append(("整章", cp0, cp1, max(1, cp1 - cp0 + 1)))
        intro_n = 1 if intro and k > 1 and l2 else 0
        remain = k - intro_n
        weights = [b[3] for b in section_buckets]
        counts = _alloc_even(len(section_buckets), remain, weights=weights)
        out: List[Tuple[str, int, int, int]] = []
        if intro_n and intro:
            out.append(("章首", intro[0], intro[1], 1))
        for b, c in zip(section_buckets, counts):
            if c > 0:
                out.append((b[0], b[1], b[2], c))
        return out

    # 节 / 小节：焦点占大头，章首与相邻各留 1
    slots: List[Tuple[str, int, int, int]] = []
    reserved = 0
    if intro:
        slots.append(("章首", intro[0], intro[1], 1))
        reserved += 1
    if focus == "subsection":
        si = plan.get("section_intro")
        if si:
            slots.append(("节首", si[0], si[1], 1))
            reserved += 1
        for rng in plan.get("adjacent_l3") or []:
            slots.append((f"邻小节:{rng[2]}"[:40], rng[0], rng[1], 1))
            reserved += 1
        sub = plan.get("subsection")
        if sub:
            slots.append(("焦点小节", sub[0], sub[1], max(1, k - reserved)))
        return [(a, b, c, n) for a, b, c, n in slots if n > 0]

    for rng in plan.get("adjacent_l2") or []:
        slots.append((f"邻节:{rng[2]}"[:40], rng[0], rng[1], 1))
        reserved += 1
    sec = plan.get("section")
    if sec:
        slots.append(("焦点节", sec[0], sec[1], max(1, k - reserved)))
    elif slots:
        return slots
    else:
        return [("整章", cp0, cp1, k)]
    return [(a, b, c, n) for a, b, c, n in slots if n > 0]


def select_segments_for_plans(pooled: List[Any], plans: List[Dict[str, Any]], k: int) -> List[Any]:
    """按结构配额从章内池取样。pooled 已限于相关文档。"""
    if not pooled or not plans or k <= 0:
        return []
    # 多文档时按文档均分 k
    by_doc: Dict[str, List[Dict[str, Any]]] = {}
    for p in plans:
        by_doc.setdefault(p["doc"], []).append(p)
    n_docs = max(1, len(by_doc))
    base = max(1, k // n_docs)
    chosen: List[Any] = []
    used: set = set()

    def _doc_match(seg, doc_name: str) -> bool:
        meta = getattr(seg, "metadata", None) or {}
        src = (meta.get("source") or meta.get("file_path") or "").replace("\\", "/")
        base_name = os.path.basename(src)
        return (
            doc_name in src
            or base_name == os.path.basename(doc_name)
            or os.path.splitext(base_name)[0] == os.path.splitext(os.path.basename(doc_name))[0]
        )

    for doc_name, doc_plans in by_doc.items():
        pool = [d for d in pooled if _doc_match(d, doc_name)] or list(pooled)
        per = base if n_docs > 1 else k
        # 同一文档多条 plan 再分
        sub_k = max(1, per // max(1, len(doc_plans)))
        for plan in doc_plans:
            quotas = _quotas_for_plan(plan, sub_k if len(doc_plans) > 1 else per)
            print(
                f"[RAG-Scope] 配额 {doc_name} focus={plan.get('focus')} "
                + ", ".join(f"{lb}:{n}" for lb, _a, _b, n in quotas),
                flush=True,
            )
            for label, p0, p1, n in quotas:
                cands = [d for d in pool if _in_range(d, p0, p1)]
                got = _spread_pick(cands, n, used)
                chosen.extend(got)
    # 不足 k：从已选文档的章池里按页序补
    if len(chosen) < k:
        rest = [d for d in pooled if _seg_fp(d) not in used]
        rest.sort(key=lambda d: (pages_of_segment(d)[:1] or [10**9]))
        extra = _spread_pick(rest, k - len(chosen), used)
        chosen.extend(extra)
    chosen.sort(key=lambda d: (pages_of_segment(d)[:1] or [10**9], _seg_fp(d)))
    return chosen[:k]


def run_structure_scope_locate(
    username: str,
    message: str,
    file_list: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    调用 deepseek-v4-flash，根据 DocStructure 定位章/节/小节页码。
    返回 page_scopes（章级池）、plans（配额取样）、map_prompt（目录全文给回答模型）。
    """
    file_list = list(file_list or [])
    docs = [f for f in file_list if f and not str(f).lower().endswith(".zip")]
    empty = {
        "ok": True,
        "triggered": False,
        "page_scopes": None,
        "plans": [],
        "scopes": [],
        "map_prompt": "",
        "note": "",
    }
    if not should_locate_structure_scope(message, docs):
        return empty

    maps = _load_structure_maps(username, docs)
    if not maps:
        print(
            "[RAG-Scope] 问题含章/节指称，但勾选文档无可用 DocStructure，跳过收窄",
            flush=True,
        )
        return {
            **empty,
            "triggered": True,
            "note": "no_doc_structure",
        }

    user_parts = [
        f"用户问题：{(message or '')[:1500]}",
        f"勾选文档数：{len(docs)}",
        "勾选文档：" + " | ".join(docs[:20]),
        "",
        "【各文档 DocStructure MAP】",
    ]
    for item in maps:
        user_parts.append(
            f"\n--- doc={item['doc']} source={item['source']} "
            f"confidence={item['confidence']} ---\n{item['map']}"
        )
    user_prompt = "\n".join(user_parts)

    try:
        raw = _call_locate_model(LOCATE_SYSTEM, user_prompt)
    except Exception as e:
        print(f"[RAG-Scope] 定位调用失败: {e}", flush=True)
        return {
            **empty,
            "triggered": True,
            "ok": False,
            "note": f"locate_error:{e}",
        }

    scopes = _parse_scopes(raw, docs)
    plans = enrich_plans(username, scopes) if scopes else []
    # page_scopes 用补齐后的章范围
    page_scopes = None
    if plans:
        page_scopes = {}
        for p in plans:
            page_scopes.setdefault(p["doc"], []).append(tuple(p["chapter"]))
    note = ""
    try:
        obj = json.loads(re.search(r"\{[\s\S]*\}", raw).group(0))  # type: ignore
        note = str((obj or {}).get("note") or "")[:200]
    except Exception:
        pass

    involved = {p["doc"] for p in plans}
    map_chunks = []
    for item in maps:
        if involved and item["doc"] not in involved:
            continue
        map_chunks.append(f"【文档目录 · {item['doc']}】\n{item['map']}")
    map_prompt = "\n\n".join(map_chunks)

    print(
        f"[RAG-Scope] 定位完成 scopes={len(scopes)} plans={len(plans)} "
        f"docs={list((page_scopes or {}).keys())} note={note!r}",
        flush=True,
    )
    for p in plans:
        ch = p.get("chapter") or (0, 0)
        print(
            f"[RAG-Scope]   {p['doc']} focus={p.get('focus')} "
            f"chapter=p{ch[0]}-p{ch[1]} intro={p.get('intro')} "
            f"section={p.get('section')} subsection={p.get('subsection')} "
            f"conf={p.get('confidence')}",
            flush=True,
        )

    return {
        "ok": True,
        "triggered": True,
        "page_scopes": page_scopes,
        "plans": plans,
        "scopes": scopes,
        "map_prompt": map_prompt,
        "note": note,
        "raw_preview": (raw or "")[:300],
    }
