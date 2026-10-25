# -*- coding: utf-8 -*-
"""Skill 挑选（deepseek-v4-flash）与注入块组装。"""
from __future__ import annotations

import json
import re
import traceback
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from app_chat import skills_store as store
from app_chat.socratic_probe import PROBE_MODEL_ABBR

SKILL_ROLE_HINT = (
    "Skill = 怎么想 / 怎么答 / 怎么做（方法与约束）；"
    "RAG 检索片段 = 原文证据。请用 Skill 组织思路与步骤，用 RAG 提供可引用的事实与出处；"
    "二者互补，不要互相替代。"
)

# 勾选卡片时，前端把卡片正文拼在问题前，用这句切开。选择 Skill 只用后半（输入框问题）。
_CARD_SPLICE_MARK = (
    "上面的重要素材文本是你完成下面的问题或请求需要参考的重点内容，"
    "也可能含有待修改的目标内容，请你回答："
)

# 第 2、3 个 Skill 不注全文，只带这些小节的开头
_PARTIAL_SECTIONS = (
    ("## 核心主张", 300),
    ("## 怎么做（工作流）", 400),
    ("## 关键锚点", 300),
    ("## 约束与输出期望", 300),
    ("## 自检（用前过一遍）", 200),
)


def question_for_skill_select(message: str) -> str:
    """去掉卡片拼接，只留用户输入框里的问题。"""
    text = (message or "").strip()
    idx = text.rfind(_CARD_SPLICE_MARK)
    if idx >= 0:
        text = text[idx + len(_CARD_SPLICE_MARK):].strip()
    return text


def _section_head(body: str, heading: str, limit: int) -> str:
    if not body or limit <= 0:
        return ""
    m = re.search(
        rf"(?m)^{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)",
        body,
        re.S,
    )
    if not m:
        return ""
    chunk = (m.group(1) or "").strip()
    if not chunk:
        return ""
    return f"{heading}\n{chunk[:limit]}"


def run_skill_select(
    username: str,
    message: str,
    file_list: Optional[List[str]] = None,
    *,
    mode: str = "normal",
) -> Dict[str, Any]:
    """返回 selected_skills / injection_block / log。"""
    mode = (mode or "normal").strip().lower()
    if mode in ("iteration", "merge"):
        print(f"[Skill] 本轮选用: (skipped: {mode})", flush=True)
        return {
            "ok": True,
            "skipped": True,
            "skip_reason": mode,
            "selected_skills": [],
            "injection_block": "",
            "candidates": [],
        }

    file_list = file_list or []
    disabled_notice = build_disabled_skills_notice(username, file_list)
    candidates = store.candidates_from_checked_files(username, file_list)
    hub = store.get_notebook_hub_meta(username)
    role_counts: Dict[str, int] = {}
    for c in candidates:
        r = str(c.get("role") or "?")
        role_counts[r] = role_counts.get(r, 0) + 1
    print(
        f"[Skill] 候选汇总: total={len(candidates)} by_role={role_counts} "
        f"files={len(file_list)}",
        flush=True,
    )
    if not candidates:
        print("[Skill] 本轮选用: (none)", flush=True)
        return {
            "ok": True,
            "selected_skills": [],
            "injection_block": disabled_notice or "",
            "candidates": [],
            "disabled_notice": bool(disabled_notice),
        }

    # build select prompt
    lines = [
        "你是 NKCN Skill 路由器。根据用户问题，从候选 Skill 中选择 0～3 个最相关的 name。",
        "只输出 JSON：{\"selected\":[\"name1\",...],\"reason\":\"≤40字\"}",
        "可空选。优先具体可执行的成员 Skill；必要时可带上 pack_hub 或 notebook-hub。",
        "",
        f"用户问题：{question_for_skill_select(message)[:1500]}",
        "",
    ]
    if hub and hub.get("description"):
        lines.append("【本子总入口 notebook-hub 总地图】")
        lines.append(hub["description"][:1024])
        lines.append("")

    # pack short routes for checked zips
    for fn in file_list:
        if str(fn).lower().endswith(".zip"):
            table = store.pack_short_route_table(username, fn)
            if table:
                lines.append(f"【包短路由表 {fn}】")
                lines.append(table)
                lines.append("")

    lines.append("【候选】")
    has_cross_theme = any(str(c.get("role") or "") == "cross_theme" for c in candidates)
    if has_cross_theme:
        lines.append(
            "说明：候选中 role=cross_theme 的条目是本子文档交叉梳理（1+n）后形成的主题化 Skill，"
            "用于跨文档交叉主题能力；与文档蒸馏 Skill / 包成员并列供你挑选。"
        )
        print("[Skill] 挑选提示已加入 cross_theme 说明", flush=True)
    for c in candidates:
        lines.append(
            f"- name={c['name']} | role={c.get('role')} | desc={(c.get('description') or '')[:1000]}"
        )

    selected: List[str] = []
    reason = ""
    try:
        raw = _call_skill_select_model(
            "你只输出合法 JSON，不要其它文字。",
            "\n".join(lines),
        )
        selected, reason = _parse_select(raw, {c["name"] for c in candidates} | {store.NOTEBOOK_HUB_NAME})
    except Exception as e:
        traceback.print_exc()
        print(f"[Skill] select 失败: {e}", flush=True)
        selected = []

    # injection
    counter_ask = False  # caller may override
    injection = build_injection_block(username, selected, counter_ask=counter_ask)
    if disabled_notice:
        injection = f"{disabled_notice}\n\n{injection}".strip() if injection else disabled_notice
    selected_roles = []
    name_to_role = {c["name"]: c.get("role") for c in candidates}
    for n in selected:
        selected_roles.append(f"{n}({name_to_role.get(n) or ('notebook-hub' if n == store.NOTEBOOK_HUB_NAME else '?')})")
    print(
        f"[Skill] 本轮选用: {', '.join(selected_roles) if selected_roles else '(none)'}"
        + (f" | reason={reason}" if reason else ""),
        flush=True,
    )
    return {
        "ok": True,
        "selected_skills": selected,
        "reason": reason,
        "injection_block": injection,
        "candidates": candidates,
        "disabled_notice": bool(disabled_notice),
        "model": PROBE_MODEL_ABBR,
    }


def build_disabled_skills_notice(username: str, file_list: Optional[List[str]]) -> str:
    """勾选了 FileCard 但背后 Skill 被用户禁用时，向回答模型警示（不刷新 hub）。"""
    idx = store.load_index(username)
    disabled: List[str] = []
    for fn in file_list or []:
        low = str(fn).lower()
        names: List[str] = []
        if low.endswith(".zip"):
            pack = (idx.get("packs") or {}).get(fn) or {}
            names = list(pack.get("members") or [])
        elif low.endswith(".pdf") or low.endswith(".txt"):
            n = store.find_skill_by_source_doc(username, fn)
            if n:
                names = [n]
        for name in names:
            meta = (idx.get("skills") or {}).get(name) or {}
            if meta.get("orphaned"):
                continue
            if not store.is_skill_enabled(idx, name):
                title = meta.get("title") or name
                disabled.append(f"`{name}`（{title}，来自 {fn}）")
    if not disabled:
        return ""
    return (
        "[NKCN_DISABLED_SKILLS_NOTICE]\n"
        "警示：以下 Skill 对应本轮已勾选的文档/Skill包，但用户已手动禁用。"
        "本轮不得套用这些 Skill 的方法论；若问题本可依赖它们，请明确告知用户「相关 Skill 已禁用」，"
        "并改用 RAG 证据与通用推理作答：\n"
        + "\n".join(f"- {x}" for x in disabled)
    )


def _call_skill_select_model(system_prompt: str, user_prompt: str) -> str:
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
        timeout=35.0,
    )
    rsp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=512,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return ((rsp.choices[0].message.content or "") if rsp.choices else "").strip()


def _parse_select(raw: str, allowed: set) -> Tuple[List[str], str]:
    text = (raw or "").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return [], ""
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return [], ""
    sel = obj.get("selected") or []
    if not isinstance(sel, list):
        sel = []
    out = []
    for x in sel:
        name = str(x).strip()
        if name in allowed and name not in out:
            out.append(name)
        if len(out) >= 3:
            break
    return out, str(obj.get("reason") or "")[:80]


def _partial_skill_block(sk: Dict[str, Any]) -> str:
    """第 2、3 个：description + 五个小节的开头，不注全文。"""
    chunks = [(sk.get("description") or "")[:800]]
    body = sk.get("body") or ""
    for heading, limit in _PARTIAL_SECTIONS:
        sec = _section_head(body, heading, limit)
        if sec:
            chunks.append(sec)
    return "\n\n".join(c for c in chunks if c).strip()


def build_injection_block(
    username: str,
    selected: List[str],
    *,
    counter_ask: bool = False,
    full_budget: int = 1,
    max_full_chars: int = 5000,
) -> str:
    if not selected:
        return ""
    parts = [f"[NKCN_ACTIVE_SKILLS]\n{SKILL_ROLE_HINT}\n"]
    for i, name in enumerate(selected):
        sk = store.read_skill(username, name)
        if not sk:
            continue
        if counter_ask:
            parts.append(f"### skill: {name}\n{(sk.get('description') or '')[:800]}\n")
        elif i >= full_budget:
            parts.append(f"### skill: {name}\n{_partial_skill_block(sk)}\n")
        else:
            raw = (sk.get("raw") or "")[:max_full_chars]
            parts.append(f"### skill: {name}\n{raw}\n")
    return "\n".join(parts).strip()


def apply_skills_to_system_prompt(system_prompt: str, injection_block: str) -> str:
    if not injection_block:
        return system_prompt or ""
    base = system_prompt or ""
    return f"{base}\n\n{injection_block}".strip()


def pull_skill_injection(
    chat_with_files_params: Any,
    username: str,
    writer: Any = None,
    params_hint: Any = None,
) -> str:
    """取 skill_injection。

    组本并发（作者+协作者同开）：params 挂在个人键 name2lock 上；
    stream 的 username 也是个人键。禁止回退到共享 writer，避免串用他人本轮 Skill。
    """
    try:
        if isinstance(params_hint, dict):
            inj = params_hint.get("skill_injection") or ""
            if not inj and isinstance(params_hint.get("skill_select"), dict):
                inj = (params_hint.get("skill_select") or {}).get("injection_block") or ""
            if inj:
                return inj

        if not isinstance(chat_with_files_params, dict):
            return ""

        keys = []
        if username:
            keys.append(username)
        # 仅非组本（writer 与 username 相同）时再试 writer；组本 writer=共享本子键，不可回退
        if writer and writer != username and writer not in keys:
            pass
        elif writer and writer not in keys:
            keys.append(writer)

        for key in keys:
            params = chat_with_files_params.get(key)
            if not isinstance(params, dict):
                continue
            inj = params.get("skill_injection") or ""
            if not inj and isinstance(params.get("skill_select"), dict):
                inj = (params.get("skill_select") or {}).get("injection_block") or ""
            if inj:
                return inj
        return ""
    except Exception:
        return ""
