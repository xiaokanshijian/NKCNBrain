# -*- coding: utf-8 -*-
"""梯子图批改卡片 HTML：访问/作答遥测（JSONL 落盘 + 注入脚本）。"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings

from app_chat.automation_nk2026 import nk2026_group_role_line
from app_chat.models import Card

_TELEMETRY_JS_CACHE: Optional[str] = None

_ROLE_NAME_RE = re.compile(
    r"(组长助理|组长|需求员|周志员|优裁员|展示员)([^，,、\s]+)"
)


def _card_html_dir(username: str) -> str:
    return os.path.normpath(f"./received_dir/user_raw_file/{username}/cardHtml").replace("\\", "/")


def _user_raw_dir(username: str) -> str:
    return os.path.normpath("./received_dir/user_raw_file/" + username.replace("\\", "/"))


def _read_twin_gxx_md(username: str, name: str) -> Optional[str]:
    """与 group_twin_gxx.read_twin_file 同路径；本模块不 import group_twin_gxx 以免循环依赖。"""
    if not re.match(r"^G\d{1,2}\.md$", name, re.I):
        return None
    path = os.path.join(_user_raw_dir(username), "_twin", name)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


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


def _feedback_jsonl_path(username: str, cid: int) -> str:
    d = _card_html_dir(username)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{int(cid)}.feedback.jsonl")


def parse_roster_from_role_line(line: str) -> List[Dict[str, str]]:
    if not line:
        return []
    out: List[Dict[str, str]] = []
    for role, name in _ROLE_NAME_RE.findall(line):
        name = (name or "").strip()
        if name:
            out.append({"role": role, "name": name})
    return out


def infer_group_id_for_card(username: str, cid: int) -> Optional[int]:
    try:
        card = Card.objects.get(username=username, cid=int(cid))
    except Card.DoesNotExist:
        return None
    for blob in (
        (card.contentTitle or ""),
        (card.title or ""),
        (card.content or "")[:1200],
    ):
        gid = _parse_group_id_from_card_title(blob)
        if gid is not None:
            return gid
    return None


def resolve_group_roster(username: str, gid: int) -> List[Dict[str, str]]:
    """NK2026 预置角色行 + Gxx.md 首段组行。"""
    roster = parse_roster_from_role_line(nk2026_group_role_line(int(gid)))
    if roster:
        return roster
    gxx = _read_twin_gxx_md(username, f"G{int(gid):02d}.md") or ""
    for line in gxx.splitlines()[:40]:
        line = line.strip().lstrip("#").strip()
        if "组" in line and "：" in line:
            parsed = parse_roster_from_role_line(line.split("：", 1)[-1])
            if not parsed:
                parsed = parse_roster_from_role_line(line)
            if parsed:
                return parsed
    return []


def build_telemetry_config(
    username: str,
    cid: int,
    *,
    submit_url: str = "/api/card_html_feedback_submit",
    summary_url: str = "/api/card_html_feedback_summary",
    force_pick: bool = False,
    html_text: str = "",
) -> Dict[str, Any]:
    gid: Optional[int] = None
    roster: List[Dict[str, str]] = []
    card_title = ""
    content_week: Optional[int] = None
    try:
        gid = infer_group_id_for_card(username, cid)
        roster = resolve_group_roster(username, gid) if gid is not None else []
        try:
            card = Card.objects.get(username=username, cid=int(cid))
            card_title = (card.contentTitle or card.title or "").strip()
        except Card.DoesNotExist:
            pass
        content_week = infer_week_for_telemetry(card_title, html_text)
    except Exception as e:
        print(f"[card_html_feedback] build_telemetry_config partial fail: {e}")
    return {
        "username": username,
        "cid": int(cid),
        "groupId": gid,
        "cardTitle": card_title,
        "contentWeek": content_week,
        "roster": roster,
        "submitUrl": submit_url,
        "summaryUrl": summary_url,
        "storageKey": telemetry_storage_key(username, int(cid), content_week),
        "forcePick": bool(force_pick),
    }


def append_feedback_event(username: str, cid: int, event: Dict[str, Any]) -> None:
    path = _feedback_jsonl_path(username, cid)
    row = dict(event)
    row.setdefault("server_ts", time.time())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_feedback_events(username: str, cid: int) -> List[Dict[str, Any]]:
    path = _feedback_jsonl_path(username, cid)
    if not os.path.isfile(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


DEFAULT_TIZITU_NOTEBOOK = "testlyf_2026tizitu-group"

_WEEK_IN_TITLE_RE = re.compile(r"W\s*0*(\d+)(?!\d)", re.I)
_S5_IN_TITLE_RE = re.compile(r"(?:^|[^\d])S\s*5(?:\s*[:：]|(?!\d))", re.I)


def parse_week_param(week_raw: str) -> Optional[int]:
    s = (week_raw or "").strip()
    if not s:
        return None
    m = re.match(r"^W\s*(\d+)$", s, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def parse_week_from_text(text: str) -> Optional[int]:
    """从卡片标题 / HTML <title> 等文本中提取 Wn 周次（避免误伤无关数字时优先 W 前缀）。"""
    s = (text or "").strip()
    if not s:
        return None
    m = _WEEK_IN_TITLE_RE.search(s)
    return int(m.group(1)) if m else None


def infer_week_for_telemetry(card_title: str = "", html_text: str = "") -> Optional[int]:
    """遥测身份缓存按周隔离：优先 HTML <title>，其次卡片 contentTitle。"""
    if html_text:
        m = re.search(r"<title[^>]*>([^<]{0,240})</title>", html_text, re.I | re.S)
        if m:
            w = parse_week_from_text(m.group(1))
            if w is not None:
                return w
        w = parse_week_from_text(html_text[:4000])
        if w is not None:
            return w
    return parse_week_from_text(card_title)


def telemetry_storage_key(username: str, cid: int, week: Optional[int] = None) -> str:
    base = f"nkcn_card_html_{username}_{int(cid)}"
    if week is not None:
        return f"{base}_W{int(week)}"
    return base


def parse_group_param(group_raw: str) -> Optional[int]:
    s = (group_raw or "").strip()
    if not s:
        return None
    m = re.search(r"[Gg]\s*0*(\d{1,2})(?!\d)", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,2})\s*组", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", s)
    return int(m.group(1)) if m else None


def parse_subject_theme(subject_raw: str) -> Optional[str]:
    s = (subject_raw or "").strip()
    for key in ("车联", "纸联", "体联"):
        if key in s:
            return key
    return None


def subject_match_tokens(subject_raw: str) -> List[str]:
    """主题匹配词：纸联III / 纸联3 / 纸联 等。"""
    s = (subject_raw or "").strip()
    if not s:
        return []
    tokens = [s]
    theme = parse_subject_theme(s)
    if theme:
        tokens.append(theme)
        roman_map = {"纸联": "III", "车联": "II", "体联": "IV"}
        arabic_map = {"纸联": "3", "车联": "2", "体联": "4"}
        if theme in roman_map:
            tokens.append(f"{theme}{roman_map[theme]}")
            tokens.append(f"{theme}{arabic_map[theme]}")
    out: List[str] = []
    seen = set()
    for tk in tokens:
        v = tk.strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def title_matches_week(title: str, week_int: int) -> bool:
    if not title or week_int is None:
        return False
    return bool(re.search(rf"W0*{int(week_int)}(?!\d)", title, re.I))


def title_matches_group(title: str, group_int: int) -> bool:
    if not title or group_int is None:
        return False
    pats = [
        rf"\b[Gg]\s*0*{group_int}(?!\d)",
        rf"#\s*0*{group_int}(?!\d)",
        rf"\b0*{group_int}\s*#\b",
        rf"第\s*0*{group_int}\s*组",
        rf"(?<![Ww])0*{group_int}\s*组",
    ]
    return any(re.search(p, title) for p in pats)


def title_matches_s5(title: str) -> bool:
    if not title:
        return False
    return bool(_S5_IN_TITLE_RE.search(title)) or bool(re.search(r"\bS5\b", title))


def title_matches_subject(title: str, subject_tokens: Sequence[str]) -> bool:
    if not title:
        return False
    if not subject_tokens:
        return True
    return any(tk and tk in title for tk in subject_tokens)


def _card_html_file_path(username: str, cid: int) -> str:
    return os.path.join(_card_html_dir(username), f"{int(cid)}.html")


def card_matches_ladder_s5(
    title: str,
    *,
    week_int: int,
    group_int: int,
    subject_tokens: Sequence[str],
) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    return (
        title_matches_week(t, week_int)
        and title_matches_group(t, group_int)
        and title_matches_s5(t)
        and title_matches_subject(t, subject_tokens)
    )


def find_ladder_s5_feedback_cards(
    notebook_username: str,
    *,
    week_int: int,
    group_int: int,
    subject_tokens: Sequence[str],
    limit: int = 20,
) -> List[Card]:
    """在本子中找 contentTitle 含 Wn、主题、组号、S5 的卡片（按时间倒序）。"""
    wk = f"W{int(week_int)}"
    qs = (
        Card.objects.filter(username=notebook_username)
        .filter(contentTitle__icontains=wk)
        .filter(contentTitle__icontains="S5")
        .order_by("-datetime", "-cid")
    )
    matched: List[Card] = []
    for card in qs[: max(limit * 8, 40)]:
        title = (card.contentTitle or card.title or "").strip()
        if card_matches_ladder_s5(
            title,
            week_int=week_int,
            group_int=group_int,
            subject_tokens=subject_tokens,
        ):
            matched.append(card)
        if len(matched) >= limit:
            break
    return matched


def _event_ts(ev: Dict[str, Any]) -> float:
    return float(ev.get("client_ts") or ev.get("clientTs") or ev.get("server_ts") or 0)


def _normalize_attempt_record(ev: Dict[str, Any]) -> Dict[str, Any]:
    """单条 JSONL 事件的标准化（尽量保留 jsonl 原字段供飞书/分析使用）。"""
    selected = ev.get("selected") or ev.get("selected_labels") or []
    if isinstance(selected, str):
        selected = [selected]
    st = ev.get("selected_text") or ev.get("selectedText") or []
    if isinstance(st, str):
        st = [st]
    client_ts = _event_ts(ev)
    server_ts = ev.get("server_ts")
    try:
        server_ts_f = float(server_ts) if server_ts is not None else None
    except (TypeError, ValueError):
        server_ts_f = None
    return {
        "event": (ev.get("event") or ev.get("type") or "").strip(),
        "attempt": int(ev.get("attempt") or 1),
        "qid": (ev.get("qid") or "").strip(),
        "question_label": (ev.get("question_label") or ev.get("questionLabel") or "").strip(),
        "member_name": (ev.get("member_name") or ev.get("memberName") or "").strip(),
        "member_role": (ev.get("member_role") or ev.get("memberRole") or "").strip(),
        "selected": selected,
        "selected_text": st,
        "outcome": (ev.get("outcome") or "").strip(),
        "client_ts": client_ts,
        "server_ts": server_ts_f,
        "session_id": (ev.get("session_id") or ev.get("sessionId") or "").strip(),
        "username": (ev.get("username") or "").strip(),
        "cid": ev.get("cid"),
    }


def _round_content_key(g: Dict[str, Any]) -> Tuple[Any, ...]:
    sel = tuple(str(x) for x in (g.get("selected") or []))
    st = tuple(str(x) for x in (g.get("selected_text") or []))
    oc = (g.get("outcome") or "").strip()
    return (sel, st, oc)


def _dedupe_consecutive_round_groups(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """去掉相邻完全相同的提交（重复上报时常见）。"""
    out: List[Dict[str, Any]] = []
    prev_key: Optional[Tuple[Any, ...]] = None
    for g in groups:
        key = _round_content_key(g)
        if prev_key is not None and key == prev_key and key[0]:
            continue
        out.append(dict(g))
        prev_key = key
    for i, g in enumerate(out, 1):
        g["attempt"] = i
    return out


def _is_resolved_outcome(outcome: str) -> bool:
    return bool(outcome) and outcome != "pending"


def _build_submit_round_groups(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    一轮 = 一次提交：
    - 题目有「提交/判定」按钮时，只统计 event=submit 且已有判定结果的记录；
    - 单选题点选即判时，统计带判定结果的 select/answer；
    - 不含 select_partial、pending、纯点选未判定。
    """
    if not events:
        return []
    ordered = sorted(events, key=lambda x: (x.get("client_ts") or 0, x.get("attempt") or 0))
    has_explicit_submit = any((e.get("event") or "").strip() == "submit" for e in ordered)

    picked: List[Dict[str, Any]] = []
    for ev in ordered:
        et = (ev.get("event") or "").strip()
        oc = (ev.get("outcome") or "").strip()
        if not _is_resolved_outcome(oc):
            continue
        if has_explicit_submit:
            if et != "submit":
                continue
        elif et not in ("select", "answer"):
            continue
        picked.append(ev)

    if not picked:
        return []

    groups = _build_attempt_groups(picked)
    return _dedupe_consecutive_round_groups(groups)


def build_submit_display_rounds(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """对外：由原始 jsonl 事件得到「按提交计轮」的轮次列表（供本地脚本复用）。"""
    return _build_submit_round_groups(events)


def _build_attempt_groups(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    按 attempt 轮次分组（原始事件粒度，含 select_partial 等）。
    对外展示「提交轮次」请用 _build_submit_round_groups。
    """
    if not events:
        return []
    ordered = sorted(events, key=lambda x: (x.get("attempt") or 1, x.get("client_ts") or 0))
    buckets: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for ev in ordered:
        buckets[int(ev.get("attempt") or 1)].append(ev)

    groups: List[Dict[str, Any]] = []
    for attempt_no in sorted(buckets.keys()):
        evs = buckets[attempt_no]
        final = evs[-1]
        final_outcome = (final.get("outcome") or "").strip()
        # 该轮最后一条「有结果」的事件（submit 后的 wrong_hint / correct_flip）
        resolved = final
        for ev in reversed(evs):
            oc = (ev.get("outcome") or "").strip()
            if oc and oc != "pending":
                resolved = ev
                final_outcome = oc
                break
        groups.append(
            {
                "attempt": attempt_no,
                "outcome": final_outcome,
                "is_correct": final_outcome == "correct_flip",
                "is_wrong": final_outcome in ("wrong_hint", "wrong"),
                "selected": resolved.get("selected") or [],
                "selected_text": resolved.get("selected_text") or [],
                "event_count": len(evs),
                "events": evs,
            }
        )
    return groups


def _question_status_from_attempts(
    attempts: List[Dict[str, Any]],
    *,
    detail_full: bool = True,
) -> Dict[str, Any]:
    if not attempts:
        base = {
            "status": "not_started",
            "last_outcome": "",
            "last_event": "",
            "attempt_count": 0,
            "submit_rounds": 0,
            "ever_correct": False,
            "wrong_rounds": [],
        }
        if detail_full:
            base["event_timeline"] = []
            base["attempt_groups"] = []
            base["attempts"] = []
        return base

    attempts = sorted(attempts, key=lambda x: (x.get("attempt") or 0, x.get("client_ts") or 0))
    attempt_groups = _build_submit_round_groups(attempts)
    last = attempts[-1]
    last_outcome = (last.get("outcome") or "").strip()
    for ev in reversed(attempts):
        oc = (ev.get("outcome") or "").strip()
        if oc and oc != "pending":
            last_outcome = oc
            last = ev
            break
    ever_correct = any((a.get("outcome") or "") == "correct_flip" for a in attempts)
    if last_outcome == "correct_flip":
        status = "correct"
    elif last_outcome in ("wrong_hint", "wrong"):
        status = "wrong"
    elif last_outcome == "pending":
        status = "in_progress"
    else:
        status = "answered"

    wrong_rounds = [
        {
            "attempt": g["attempt"],
            "selected": g.get("selected") or [],
            "selected_text": g.get("selected_text") or [],
            "outcome": g.get("outcome") or "",
        }
        for g in attempt_groups
        if g.get("is_wrong")
    ]

    out: Dict[str, Any] = {
        "status": status,
        "last_outcome": last_outcome,
        "last_event": last.get("event") or "",
        "attempt_count": max((a.get("attempt") or 1) for a in attempts),
        "submit_rounds": len(attempt_groups),
        "ever_correct": ever_correct,
        "wrong_rounds": wrong_rounds,
    }
    if detail_full:
        out["event_timeline"] = attempts
        out["attempt_groups"] = attempt_groups
        out["attempts"] = attempts
    else:
        out["attempts"] = attempt_groups
    return out


def is_feedback_guest_member(name: str) -> bool:
    """遥测「访客 / 暂不登记」身份，组级统计与可视化应排除。"""
    n = (name or "").strip()
    return n == "访客" or n.startswith("访客")


def _member_name_from_event(ev: Dict[str, Any]) -> str:
    return (ev.get("member_name") or ev.get("memberName") or "").strip() or "（未登记）"


def filter_feedback_events_for_stats(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """统计用事件：排除访客身份。"""
    return [
        ev
        for ev in events
        if not is_feedback_guest_member(_member_name_from_event(ev))
    ]


def _process_feedback_events(
    events: List[Dict[str, Any]],
) -> Tuple[
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[Tuple[str, str], List[Dict[str, Any]]],
]:
    visitors: Dict[str, Dict[str, Any]] = {}
    questions: Dict[str, Dict[str, Any]] = {}
    member_attempts: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

    for ev in events:
        member = _member_name_from_event(ev)
        if is_feedback_guest_member(member):
            continue
        role = (ev.get("member_role") or ev.get("memberRole") or "").strip()
        session = (ev.get("session_id") or ev.get("sessionId") or "").strip()
        et = (ev.get("event") or ev.get("type") or "").strip()
        ts = _event_ts(ev)

        vk = f"{member}\0{role}"
        if vk not in visitors:
            visitors[vk] = {
                "member_name": member,
                "member_role": role,
                "sessions": set(),
                "first_at": ts,
                "last_at": ts,
                "visited": False,
                "answered": False,
            }
        v = visitors[vk]
        v["last_at"] = max(v["last_at"], ts)
        if v["first_at"]:
            v["first_at"] = min(v["first_at"], ts)
        else:
            v["first_at"] = ts
        if session:
            v["sessions"].add(session)

        if et == "visit":
            v["visited"] = True
            continue

        if et in ("select", "select_partial", "submit", "answer"):
            v["answered"] = True
            qid = (ev.get("qid") or "unknown").strip()
            qlabel = (ev.get("question_label") or ev.get("questionLabel") or "").strip()
            if qid not in questions:
                questions[qid] = {"qid": qid, "question_label": qlabel, "by_member": {}}
            elif qlabel and not questions[qid]["question_label"]:
                questions[qid]["question_label"] = qlabel
            member_attempts[(member, qid)].append(_normalize_attempt_record(ev))

    for (member, qid), attempts in member_attempts.items():
        questions[qid]["by_member"].setdefault(member, []).extend(attempts)

    return visitors, questions, member_attempts


def aggregate_feedback_summary(username: str, cid: int) -> Dict[str, Any]:
    gid = infer_group_id_for_card(username, cid)
    roster = resolve_group_roster(username, gid) if gid is not None else []
    events = filter_feedback_events_for_stats(load_feedback_events(username, cid))
    visitors, questions, _member_attempts = _process_feedback_events(events)

    visitor_list = []
    for v in visitors.values():
        visitor_list.append(
            {
                "member_name": v["member_name"],
                "member_role": v["member_role"],
                "visited": v["visited"],
                "answered": v["answered"],
                "session_count": len(v["sessions"]),
                "first_at": v["first_at"],
                "last_at": v["last_at"],
            }
        )
    visitor_list.sort(key=lambda x: (not x["answered"], x["member_name"]))

    q_list = sorted(questions.values(), key=lambda x: x["qid"])
    seen_names = {v["member_name"] for v in visitor_list}
    for r in roster:
        if r["name"] not in seen_names:
            visitor_list.append(
                {
                    "member_name": r["name"],
                    "member_role": r["role"],
                    "visited": False,
                    "answered": False,
                    "session_count": 0,
                    "first_at": None,
                    "last_at": None,
                }
            )

    return {
        "username": username,
        "cid": int(cid),
        "group_id": gid,
        "roster": roster,
        "visitor_count": len([x for x in visitor_list if x.get("visited")]),
        "answered_count": len([x for x in visitor_list if x.get("answered")]),
        "visitors": visitor_list,
        "questions": q_list,
        "event_count": len(events),
    }


def aggregate_group_card_html_feedback(
    notebook_username: str,
    *,
    week_int: int,
    group_int: int,
    subject_raw: str = "",
    cid: Optional[int] = None,
    include_events: bool = False,
    include_legacy_summary: bool = False,
    detail_full: bool = True,
) -> Dict[str, Any]:
    """
    按周次+主题+组号定位 S5 梯子图批改卡片，汇总本子 cardHtml 下对应 cid 的 JSONL 作答。
    """
    subject_tokens = subject_match_tokens(subject_raw)
    week_label = f"W{int(week_int)}"
    group_label = f"G{int(group_int):02d}"

    card: Optional[Card] = None
    candidates: List[Dict[str, Any]] = []
    if cid is not None:
        try:
            card = Card.objects.get(username=notebook_username, cid=int(cid))
        except Card.DoesNotExist:
            return {
                "ok": False,
                "error": f"卡片 cid={cid} 不存在于本子 {notebook_username}",
            }
    else:
        matched = find_ladder_s5_feedback_cards(
            notebook_username,
            week_int=week_int,
            group_int=group_int,
            subject_tokens=subject_tokens,
        )
        for c in matched:
            candidates.append(
                {
                    "cid": c.cid,
                    "contentTitle": (c.contentTitle or "").strip(),
                    "datetime": str(c.datetime) if c.datetime else "",
                }
            )
        if not matched:
            return {
                "ok": False,
                "error": (
                    f"未找到匹配卡片：{week_label} / 主题{subject_tokens or ['任意']} / "
                    f"{group_label} / S5（本子 {notebook_username}）"
                ),
                "query": {
                    "notebook": notebook_username,
                    "week": week_label,
                    "week_int": week_int,
                    "subject": subject_raw,
                    "subject_tokens": subject_tokens,
                    "group_int": group_int,
                    "group_label": group_label,
                },
            }
        card = matched[0]

    assert card is not None
    resolved_cid = int(card.cid)
    card_title = (card.contentTitle or card.title or "").strip()
    gid = infer_group_id_for_card(notebook_username, resolved_cid) or group_int
    roster = resolve_group_roster(notebook_username, gid)

    jsonl_path = _feedback_jsonl_path(notebook_username, resolved_cid)
    html_path = _card_html_file_path(notebook_username, resolved_cid)
    jsonl_exists = os.path.isfile(jsonl_path)
    html_exists = os.path.isfile(html_path)
    jsonl_mtime = os.path.getmtime(jsonl_path) if jsonl_exists else None
    jsonl_bytes = os.path.getsize(jsonl_path) if jsonl_exists else 0

    events = filter_feedback_events_for_stats(load_feedback_events(notebook_username, resolved_cid))
    visitors, questions, _ = _process_feedback_events(events)

    qids = sorted(questions.keys(), key=lambda x: (len(x), x))
    question_count = len(qids)

    members_out: List[Dict[str, Any]] = []
    visitor_by_name: Dict[str, Dict[str, Any]] = {}
    for v in visitors.values():
        visitor_by_name[v["member_name"]] = v

    def _build_member_row(name: str, role: str, vinfo: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        q_rows: List[Dict[str, Any]] = []
        correct_n = 0
        answered_n = 0
        for qid in qids:
            qmeta = questions[qid]
            attempts = list((qmeta.get("by_member") or {}).get(name) or [])
            qstat = _question_status_from_attempts(attempts, detail_full=detail_full)
            if qstat["status"] == "correct":
                correct_n += 1
            if qstat["status"] not in ("not_started",):
                answered_n += 1
            q_rows.append(
                {
                    "qid": qid,
                    "question_label": qmeta.get("question_label") or "",
                    **qstat,
                }
            )
        visited = bool(vinfo and vinfo.get("visited"))
        answered = bool(vinfo and vinfo.get("answered"))
        return {
            "member_name": name,
            "member_role": role,
            "visited": visited,
            "answered": answered,
            "session_count": len(vinfo.get("sessions", set())) if vinfo else 0,
            "first_at": vinfo.get("first_at") if vinfo else None,
            "last_at": vinfo.get("last_at") if vinfo else None,
            "questions_total": question_count,
            "questions_answered": answered_n,
            "questions_correct": correct_n,
            "completion": f"{correct_n}/{question_count}" if question_count else "0/0",
            "all_correct": question_count > 0 and correct_n >= question_count,
            "questions": q_rows,
        }

    seen = set()
    for r in roster:
        name = r["name"]
        seen.add(name)
        vinfo = visitor_by_name.get(name)
        members_out.append(_build_member_row(name, r.get("role") or "", vinfo))

    for name, vinfo in visitor_by_name.items():
        if name in seen or is_feedback_guest_member(name):
            continue
        members_out.append(_build_member_row(name, vinfo.get("member_role") or "", vinfo))

    members_out.sort(key=lambda x: (not x["answered"], not x["visited"], x["member_name"]))

    questions_global: List[Dict[str, Any]] = []
    for qid in qids:
        qmeta = questions[qid]
        by_member_summary: Dict[str, Any] = {}
        for member, attempts in (qmeta.get("by_member") or {}).items():
            if is_feedback_guest_member(member):
                continue
            by_member_summary[member] = _question_status_from_attempts(
                attempts, detail_full=detail_full
            )
        questions_global.append(
            {
                "qid": qid,
                "question_label": qmeta.get("question_label") or "",
                "by_member": by_member_summary,
            }
        )

    visited_count = len([m for m in members_out if m.get("visited")])
    answered_count = len([m for m in members_out if m.get("answered")])
    all_done_count = len([m for m in members_out if m.get("all_correct")])

    payload: Dict[str, Any] = {
        "ok": True,
        "query": {
            "notebook": notebook_username,
            "week": week_label,
            "week_int": week_int,
            "subject": subject_raw,
            "subject_tokens": subject_tokens,
            "group_int": group_int,
            "group_label": group_label,
        },
        "card": {
            "cid": resolved_cid,
            "contentTitle": card_title,
            "title": (card.title or "").strip(),
            "datetime": str(card.datetime) if card.datetime else "",
            "group_id": gid,
        },
        "paths": {
            "feedback_jsonl": jsonl_path.replace("\\", "/"),
            "html": html_path.replace("\\", "/"),
            "jsonl_exists": jsonl_exists,
            "html_exists": html_exists,
            "jsonl_bytes": jsonl_bytes,
            "jsonl_mtime": jsonl_mtime,
        },
        "roster": roster,
        "question_count": question_count,
        "stats": {
            "roster_size": len(roster),
            "visitor_count": visited_count,
            "answered_count": answered_count,
            "all_questions_correct_count": all_done_count,
            "event_count": len(events),
        },
        "members": members_out,
        "questions": questions_global,
        "candidates": candidates,
    }
    payload["detail"] = "full" if detail_full else "summary"
    if include_events:
        payload["events_raw"] = events
    if include_legacy_summary:
        payload["legacy_summary"] = aggregate_feedback_summary(notebook_username, resolved_cid)
    return payload


def _slim_round(g: Dict[str, Any]) -> Dict[str, Any]:
    """单轮提交摘要（不含 events 明细，供飞书/可视化列表每一轮选了什么）。"""
    outcome = (g.get("outcome") or "").strip()
    is_correct = bool(g.get("is_correct")) or outcome == "correct_flip"
    is_wrong = bool(g.get("is_wrong")) or outcome in ("wrong_hint", "wrong")
    return {
        "attempt": int(g.get("attempt") or 0),
        "outcome": outcome,
        "is_correct": is_correct,
        "is_wrong": is_wrong,
        "selected": g.get("selected") if isinstance(g.get("selected"), list) else [],
        "selected_text": g.get("selected_text") if isinstance(g.get("selected_text"), list) else [],
    }


def format_group_feedback_api_response(
    report: Dict[str, Any],
    *,
    include_events: bool = False,
    include_rounds: bool = False,
) -> Dict[str, Any]:
    """
    按《梯子图批改小组作答状态获取api说明》输出飞书约定字段（不含 query/card/paths/questions 等扩展项）。
    """
    empty_stats = {
        "roster_size": 0,
        "visitor_count": 0,
        "answered_count": 0,
        "all_questions_correct_count": 0,
    }
    if not report.get("ok"):
        return {
            "roster": [],
            "question_count": 0,
            "stats": empty_stats,
            "members": [],
        }

    def _slim_wr(wr: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "attempt": int(wr.get("attempt") or 0),
            "outcome": (wr.get("outcome") or "").strip(),
            "selected": wr.get("selected") if isinstance(wr.get("selected"), list) else [],
            "selected_text": wr.get("selected_text") if isinstance(wr.get("selected_text"), list) else [],
        }

    def _slim_question(qrow: Dict[str, Any]) -> Dict[str, Any]:
        sq: Dict[str, Any] = {
            "qid": (qrow.get("qid") or "").strip(),
            "question_label": (qrow.get("question_label") or "").strip(),
            "status": (qrow.get("status") or "not_started").strip(),
            "submit_rounds": int(qrow.get("submit_rounds") or 0),
            "ever_correct": bool(qrow.get("ever_correct")),
            "wrong_rounds": [_slim_wr(w) for w in (qrow.get("wrong_rounds") or [])],
        }
        if include_rounds:
            ag = qrow.get("attempt_groups") or qrow.get("rounds") or []
            sq["rounds"] = [_slim_round(g) for g in ag]
        return sq

    roster_out: List[Dict[str, str]] = []
    for r in report.get("roster") or []:
        if isinstance(r, dict):
            roster_out.append(
                {
                    "角色": (r.get("角色") or r.get("role") or "").strip(),
                    "姓名": (r.get("姓名") or r.get("name") or "").strip(),
                }
            )

    stats_in = report.get("stats") or {}
    data: Dict[str, Any] = {
        "roster": roster_out,
        "question_count": int(report.get("question_count") or 0),
        "stats": {
            "roster_size": int(stats_in.get("roster_size") or 0),
            "visitor_count": int(stats_in.get("visitor_count") or 0),
            "answered_count": int(stats_in.get("answered_count") or 0),
            "all_questions_correct_count": int(
                stats_in.get("all_questions_correct_count") or 0
            ),
        },
        "members": [
            {
                "member_name": (m.get("member_name") or "").strip(),
                "member_role": (m.get("member_role") or "").strip(),
                "visited": bool(m.get("visited")),
                "answered": bool(m.get("answered")),
                "completion": (m.get("completion") or "0/0").strip(),
                "all_correct": bool(m.get("all_correct")),
                "questions": [_slim_question(q) for q in (m.get("questions") or [])],
            }
            for m in (report.get("members") or [])
            if not is_feedback_guest_member((m.get("member_name") or "").strip())
        ],
    }
    if include_events:
        data["events_raw"] = report.get("events_raw") or []
    return data


# 飞书「响应配置 → Raw JSON」可整段粘贴的示例结构（字段名须与线上一致）
FEISHU_RESPONSE_BODY_SCHEMA_EXAMPLE: Dict[str, Any] = {
    "error_num": 0,
    "msg": "success",
    "data": {
        "roster": [{"角色": "组长", "姓名": "张三"}],
        "question_count": 6,
        "stats": {
            "roster_size": 6,
            "visitor_count": 4,
            "answered_count": 4,
            "all_questions_correct_count": 2,
        },
        "members": [
            {
                "member_name": "张三",
                "member_role": "组长",
                "visited": True,
                "answered": True,
                "completion": "5/6",
                "all_correct": False,
                "questions": [
                    {
                        "qid": "q0",
                        "question_label": "题干摘要",
                        "status": "wrong",
                        "submit_rounds": 2,
                        "ever_correct": False,
                        "wrong_rounds": [
                            {
                                "attempt": 1,
                                "outcome": "wrong_hint",
                                "selected": ["B"],
                                "selected_text": ["选项B文字摘要"],
                            }
                        ],
                    }
                ],
            }
        ],
    },
}


_STATUS_ICON = {
    "correct": "✓",
    "wrong": "✗",
    "in_progress": "…",
    "answered": "?",
    "not_started": "—",
}


def format_group_feedback_as_text(report: Dict[str, Any]) -> str:
    """生成适合飞书消息/审批展示的纯文本摘要。"""
    if not report.get("ok"):
        return report.get("error") or "查询失败"
    q = report.get("query") or {}
    card = report.get("card") or {}
    st = report.get("stats") or {}
    lines = [
        f"【{q.get('week', '')} {q.get('subject', '')} {q.get('group_label', '')} 梯子图 S5 助记作答】",
        f"卡片 cid={card.get('cid')} | {card.get('contentTitle', '')[:80]}",
        (
            f"名册 {st.get('roster_size', 0)} 人 | 已访问 {st.get('visitor_count', 0)} | "
            f"已作答 {st.get('answered_count', 0)} | 全对 {st.get('all_questions_correct_count', 0)} | "
            f"题数 {report.get('question_count', 0)}"
        ),
        "",
        "成员进度（对/总）：",
    ]
    for m in report.get("members") or []:
        role = m.get("member_role") or ""
        name = m.get("member_name") or ""
        comp = m.get("completion") or "0/0"
        flags = []
        if m.get("all_correct"):
            flags.append("全对")
        elif not m.get("visited"):
            flags.append("未访问")
        elif not m.get("answered"):
            flags.append("未作答")
        tag = f" ({'，'.join(flags)})" if flags else ""
        lines.append(f"  {_STATUS_ICON.get('correct' if m.get('all_correct') else 'not_started', '·')} "
                       f"{name}({role}) {comp}{tag}")
    qids = sorted(
        {(qrow.get("qid") or "") for m in (report.get("members") or []) for qrow in (m.get("questions") or [])},
        key=lambda x: (len(x), x),
    )
    if qids:
        lines.append("")
        lines.append("题目矩阵（行=成员，列=题）：")
        header = "成员".ljust(10) + "".join(f"{qid:^4}" for qid in qids)
        lines.append(header)
        for m in report.get("members") or []:
            name = (m.get("member_name") or "")[:8]
            row = name.ljust(10)
            qmap = {x.get("qid"): x for x in (m.get("questions") or [])}
            for qid in qids:
                stt = (qmap.get(qid) or {}).get("status") or "not_started"
                row += (_STATUS_ICON.get(stt, "·")).center(4)
            lines.append(row)
    lines.append("")
    lines.append("图例：✓对 ✗错 …进行中 —未开始")
    return "\n".join(lines)


def _telemetry_js_candidates() -> List[str]:
    """与部署目录无关的多路径探测（避免只传了 js 但 Python 仍读不到）。"""
    base = os.path.dirname(os.path.abspath(__file__))
    name = "card_html_telemetry.js"
    raw_dirs = [
        os.path.join(base, "static"),
        os.path.join(base, "..", "static"),
        os.path.join(os.getcwd(), "app_chat", "static"),
        os.path.join(os.getcwd(), "static"),
    ]
    try:
        raw_dirs.append(str(settings.BASE_DIR / "app_chat" / "static"))
        raw_dirs.append(str(settings.BASE_DIR / "static"))
    except Exception:
        pass
    out: List[str] = []
    for d in raw_dirs:
        p = os.path.normpath(os.path.join(d, name))
        if p not in out:
            out.append(p)
    return out


def resolve_telemetry_js_path() -> str:
    for path in _telemetry_js_candidates():
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "未找到 card_html_telemetry.js，请将文件部署到 app_chat/static/ 目录。"
        " 已尝试: " + "; ".join(_telemetry_js_candidates())
    )


def load_telemetry_script() -> str:
    global _TELEMETRY_JS_CACHE
    if _TELEMETRY_JS_CACHE is not None:
        return _TELEMETRY_JS_CACHE
    path = resolve_telemetry_js_path()
    with open(path, "r", encoding="utf-8") as f:
        _TELEMETRY_JS_CACHE = f.read()
    return _TELEMETRY_JS_CACHE


def telemetry_js_diag() -> Dict[str, Any]:
    candidates = _telemetry_js_candidates()
    exists = {p: os.path.isfile(p) for p in candidates}
    resolved = None
    err = None
    try:
        resolved = resolve_telemetry_js_path()
    except Exception as e:
        err = str(e)
    return {
        "module_file": os.path.abspath(__file__),
        "cwd": os.getcwd(),
        "candidates": candidates,
        "exists": exists,
        "resolved": resolved,
        "error": err,
    }


def _json_embedded_in_html(obj: Any) -> str:
    """避免标题/姓名里的 </script> 截断 HTML 中的 script 块。"""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


TA_FEEDBACK_IDENTITIES: Tuple[str, ...] = (
    "教师",
    "课程TA梁依枫",
    "车联TA杨谦",
    "纸联TA石轹文",
    "体联TA刘叙增",
)


def _ta_feedback_dir(username: str) -> str:
    d = os.path.join(_card_html_dir(username), "TAfeedback")
    os.makedirs(d, exist_ok=True)
    return d


def ta_feedback_path(username: str, cid: int) -> str:
    return os.path.join(_ta_feedback_dir(username), f"{int(cid)}.json")


def read_ta_feedback(username: str, cid: int) -> Dict[str, Any]:
    path = ta_feedback_path(username, cid)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[card_html_feedback] read_ta_feedback fail cid={cid}: {e}")
        return {}


def write_ta_feedback(username: str, cid: int, *, author: str, content: str) -> Dict[str, Any]:
    author = (author or "").strip()
    if author not in TA_FEEDBACK_IDENTITIES:
        raise ValueError(f"无效身份，须为: {', '.join(TA_FEEDBACK_IDENTITIES)}")
    row = {
        "username": username,
        "cid": int(cid),
        "author": author,
        "content": (content or "").strip(),
        "updated_at": time.time(),
    }
    path = ta_feedback_path(username, cid)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(row, f, ensure_ascii=False, indent=2)
    return row


def build_ta_feedback_config(
    username: str,
    cid: int,
    *,
    get_url: str,
    save_url: str,
) -> Dict[str, Any]:
    return {
        "username": username,
        "cid": int(cid),
        "getUrl": get_url,
        "saveUrl": save_url,
        "identities": list(TA_FEEDBACK_IDENTITIES),
        "studentHint": "学生只查看，不编辑",
    }


def _ta_feedback_js_candidates() -> List[str]:
    base = os.path.dirname(os.path.abspath(__file__))
    static = os.path.join(base, "static", "card_html_ta_feedback.js")
    return [
        static,
        os.path.join(os.getcwd(), "app_chat", "static", "card_html_ta_feedback.js"),
    ]


def resolve_ta_feedback_js_path() -> str:
    for path in _ta_feedback_js_candidates():
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "未找到 card_html_ta_feedback.js，请将文件部署到 app_chat/static/ 目录。"
    )


def load_ta_feedback_script() -> str:
    path = resolve_ta_feedback_js_path()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def inject_card_html_ta_feedback(
    html: str,
    cfg: Dict[str, Any],
    *,
    script_url: str,
) -> str:
    cfg_json = _json_embedded_in_html(cfg)
    marker = "<!-- nkcn-ta-feedback-injected -->\n"
    cfg_script = (
        marker
        + f'<script id="nkcn-ta-feedback-cfg" type="application/json">{cfg_json}</script>\n'
        + "<script>window.__NKCN_TA_FEEDBACK__=JSON.parse("
        + "document.getElementById('nkcn-ta-feedback-cfg').textContent);</script>\n"
    )
    esc_url = script_url.replace('"', "%22")
    bundle = cfg_script + f'<script id="nkcn-ta-feedback-js" src="{esc_url}" defer></script>\n'
    if re.search(r"</body>", html, re.I):
        return re.sub(r"</body>", bundle + "</body>", html, count=1, flags=re.I)
    if re.search(r"</html>", html, re.I):
        return re.sub(r"</html>", bundle + "</html>", html, count=1, flags=re.I)
    return html + bundle


def inject_card_html_telemetry(
    html: str,
    cfg: Dict[str, Any],
    *,
    telemetry_script_url: str,
) -> str:
    cfg_json = _json_embedded_in_html(cfg)
    marker = "<!-- nkcn-telemetry-injected -->\n"
    cfg_script = (
        marker
        + f'<script id="nkcn-card-html-cfg" type="application/json">{cfg_json}</script>\n'
        + "<script>window.__NKCN_CARD_HTML__=JSON.parse("
        + "document.getElementById('nkcn-card-html-cfg').textContent);</script>\n"
    )
    esc_url = telemetry_script_url.replace('"', "%22")
    telemetry = (
        f'<script id="nkcn-card-html-telemetry" src="{esc_url}" defer></script>\n'
    )
    bundle = cfg_script + telemetry
    if re.search(r"</body>", html, re.I):
        return re.sub(r"</body>", bundle + "</body>", html, count=1, flags=re.I)
    if re.search(r"</html>", html, re.I):
        return re.sub(r"</html>", bundle + "</html>", html, count=1, flags=re.I)
    return html + bundle
