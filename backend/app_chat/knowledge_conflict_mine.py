# -*- coding: utf-8 -*-
"""本子知识冲突挖掘：基于文档 Skill / 导入包 Skill 节选，DeepSeek 分类分点产出。"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app_chat import skills_store as store

CONFLICT_DIR = "_knowledge_conflicts"
RESULT_NAME = "conflicts.json"
SCHEMA = 1
# 仅作安全阀；真正上限与文档 PreSummary 输入字符上限一致（见 _input_char_limit）
MAX_DOC_SKILLS = 240
MAX_PACK_SKILLS = 240


def _input_char_limit() -> int:
    """与 llm_langchain.parse_input 文档 PreSummary 输入截断上限一致。"""
    # CONTEXT 131072 - COMPLETION 4096 - RESERVED 6500；chars/token≈1.50；safety 0.90
    return int(max(0, 131072 - 4096 - 6500) * 1.50 * 0.90)  # → 162642
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_USER_LOCKS: Dict[str, threading.Lock] = {}
_USER_LOCKS_GUARD = threading.Lock()


def _user_lock(username: str) -> threading.Lock:
    with _USER_LOCKS_GUARD:
        lk = _USER_LOCKS.get(username)
        if not lk:
            lk = threading.Lock()
            _USER_LOCKS[username] = lk
        return lk


def conflict_root(username: str) -> str:
    path = os.path.join(store.skills_root(username), CONFLICT_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def result_path(username: str) -> str:
    return os.path.join(conflict_root(username), RESULT_NAME)


def load_conflicts(username: str) -> Optional[Dict[str, Any]]:
    path = result_path(username)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_conflicts(username: str, data: Dict[str, Any]) -> None:
    path = result_path(username)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
        return dict(j) if j else None


def _set_job(job_id: str, **kwargs) -> None:
    with _JOBS_LOCK:
        cur = _JOBS.get(job_id) or {}
        cur.update(kwargs)
        _JOBS[job_id] = cur


def start_knowledge_conflict_job(username: str, scene_name: str = "") -> str:
    job_id = uuid.uuid4().hex[:16]
    _set_job(
        job_id,
        status="running",
        phase="queued",
        username=username,
        scene_name=scene_name or "",
        msg="排队中",
        error="",
        started_at=time.time(),
    )

    def _run():
        try:
            ok, err = run_knowledge_conflict_mine(username, scene_name=scene_name, job_id=job_id)
            if ok:
                _set_job(job_id, status="ok", phase="done", msg="完成", finished_at=time.time())
            else:
                _set_job(
                    job_id,
                    status="failed",
                    phase="done",
                    msg=err or "失败",
                    error=err or "",
                    finished_at=time.time(),
                )
        except Exception as e:
            traceback.print_exc()
            _set_job(
                job_id,
                status="failed",
                phase="done",
                msg=str(e)[:300],
                error=str(e)[:300],
                finished_at=time.time(),
            )

    threading.Thread(target=_run, daemon=True).start()
    return job_id


def _split_sections(body: str) -> List[Tuple[str, str]]:
    text = body or ""
    matches = list(re.finditer(r"^#{1,3}\s+.+$", text, re.M))
    if not matches:
        return [("正文", text.strip())] if text.strip() else []
    out: List[Tuple[str, str]] = []
    # preamble before first heading
    if matches[0].start() > 0:
        pre = text[: matches[0].start()].strip()
        if pre:
            out.append(("开头", pre))
    for i, m in enumerate(matches):
        title = m.group(0).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((title, text[start:end].strip()))
    return out


def _section_by_keywords(sections: List[Tuple[str, str]], *keywords: str) -> str:
    for title, content in sections:
        t = title.lstrip("#").strip()
        if any(k in t for k in keywords):
            return content
    return ""


def _opening_for_doc(body: str) -> str:
    """文档 Skill 开头：H1（及 H1 前前言）到「核心主张」之前。"""
    sections = _split_sections(body)
    if not sections:
        return (body or "")[:1200]
    parts: List[str] = []
    for title, content in sections:
        t = title.lstrip("#").strip()
        if any(k in t for k in ("核心主张", "关键锚点")):
            break
        parts.append(content)
        if title.startswith("# ") and not title.startswith("##"):
            # 取完 H1 后若下一段不是主张，可再带一小段
            continue
        if title == "开头":
            continue
        # 已有 H1 后停止，避免把何时用等整段塞进开头
        if any(p.startswith("# ") for p in parts):
            break
    text = "\n\n".join(p for p in parts if p).strip()
    return text or (sections[0][1][:1200] if sections else "")


def _opening_for_pack(body: str) -> str:
    """导入包 Skill 开头：H1 + 性质/务必先读（若有）+ 核心主张，止于 R/I/A/E 详段。"""
    sections = _split_sections(body)
    if not sections:
        return (body or "")[:2000]
    parts: List[str] = []
    for title, content in sections:
        t = title.lstrip("#").strip()
        if re.match(r"^[RIAE]\b", t) or t.startswith("R —") or t.startswith("R -") or "原文依据" in t:
            if "核心主张" not in t:
                break
        if re.match(r"^[IAE]\b", t) or "方法论重述" in t or "执行步骤" in t or "书中案例" in t:
            break
        if "相关 skill" in t.lower() or "相关 Skill" in t:
            break
        parts.append(content)
        # 已拿到核心主张后可收
        if "核心主张" in t and len("\n\n".join(parts)) > 400:
            break
    text = "\n\n".join(p for p in parts if p).strip()
    return text[:4500] if text else (sections[0][1][:2000] if sections else "")


def _excerpt_doc_skill(body: str, description: str = "") -> str:
    opening = _opening_for_doc(body)
    sections = _split_sections(body)
    claim = _section_by_keywords(sections, "核心主张")
    anchors = _section_by_keywords(sections, "关键锚点")
    chunks = []
    if description:
        chunks.append(f"（description）{description.strip()[:600]}")
    if opening:
        chunks.append("【开头部分】\n" + opening)
    if claim:
        chunks.append("【核心主张】\n" + claim)
    if anchors:
        chunks.append("【关键锚点】\n" + anchors)
    if not chunks:
        chunks.append((body or "")[:2500])
    return "\n\n".join(chunks)


def _excerpt_pack_skill(body: str, description: str = "") -> str:
    opening = _opening_for_pack(body)
    chunks = []
    if description:
        chunks.append(f"（description）{description.strip()[:700]}")
    if opening:
        chunks.append("【开头部分】\n" + opening)
    if not chunks:
        chunks.append((body or "")[:2000])
    return "\n\n".join(chunks)


def _collect_skill_excerpts(username: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    idx = store.reconcile_index(username)
    docs: List[Dict[str, Any]] = []
    packs: List[Dict[str, Any]] = []
    for name, meta in (idx.get("skills") or {}).items():
        if name == store.NOTEBOOK_HUB_NAME:
            continue
        if not store.is_skill_enabled(idx, name):
            continue
        if meta.get("orphaned") or meta.get("missing"):
            continue
        source = meta.get("source")
        if source == "cross_reorganize":
            continue
        sk = store.read_skill(username, name)
        if not sk:
            continue
        body = sk.get("body") or ""
        desc = sk.get("description") or ""
        title = meta.get("title") or (sk.get("metadata") or {}).get("title") or name
        pack_zip = meta.get("pack_zip") or ""
        item = {
            "name": name,
            "title": title,
            "source_doc": meta.get("source_doc") or "",
            "pack_zip": pack_zip,
        }
        if pack_zip:
            item["kind"] = "pack"
            item["excerpt"] = _excerpt_pack_skill(body, desc)
            packs.append(item)
        else:
            item["kind"] = "doc"
            item["excerpt"] = _excerpt_doc_skill(body, desc)
            docs.append(item)
    docs = docs[:MAX_DOC_SKILLS]
    packs = packs[:MAX_PACK_SKILLS]
    return docs, packs


def _chunk_for_item(it: Dict[str, Any]) -> str:
    if it.get("kind") == "pack" or it.get("pack_zip"):
        return (
            f"### {it.get('title') or it['name']}（name={it['name']}｜pack={it.get('pack_zip') or '—'}）\n"
            f"{it.get('excerpt') or ''}"
        )
    return (
        f"### {it.get('title') or it['name']}（name={it['name']}｜doc={it.get('source_doc') or '—'}）\n"
        f"{it.get('excerpt') or ''}"
    )


def _budget_excerpts(docs: List[Dict[str, Any]], packs: List[Dict[str, Any]]) -> str:
    """轮询拼入文档/包成员，总长 ≤ PreSummary 输入上限，避免总是砍掉后面的包。"""
    limit = _input_char_limit()
    doc_chunks = [_chunk_for_item(it) for it in docs]
    pack_chunks = [_chunk_for_item(it) for it in packs]
    chosen_docs: List[str] = []
    chosen_packs: List[str] = []
    used = 0
    i = j = 0

    def _take_one(chunks: List[str], idx: int, chosen: List[str]) -> Tuple[int, bool]:
        """尝试纳入或跳过一条；返回 (新 idx, 是否因满额截断而结束)。"""
        nonlocal used
        if idx >= len(chunks) or used >= limit:
            return idx, False
        c = chunks[idx]
        need = len(c) + 2
        if used + need <= limit:
            chosen.append(c)
            used += need
            return idx + 1, False
        if not chosen_docs and not chosen_packs and (limit - used) > 500:
            chosen.append(c[: max(0, limit - used - 20)] + "\n…(截断)")
            used = limit
            return idx + 1, True
        # 装不下则跳过，留给后面更短的条目 / 另一侧轮询
        return idx + 1, False

    while i < len(doc_chunks) or j < len(pack_chunks):
        if used >= limit:
            break
        before = (i, j, len(chosen_docs), len(chosen_packs), used)
        i, stop = _take_one(doc_chunks, i, chosen_docs)
        if stop:
            break
        j, stop = _take_one(pack_chunks, j, chosen_packs)
        if stop:
            break
        # 两侧都无法再推进（通常只剩装不下的超长条且预算已紧）
        if (i, j, len(chosen_docs), len(chosen_packs), used) == before:
            break

    parts = ["## 本子文档 Skill（开头 + 核心主张 + 关键锚点）"]
    parts.extend(chosen_docs or ["（本轮未纳入文档 Skill 节选）"])
    parts.append("\n## 导入 Skill 包成员（仅开头部分）")
    parts.extend(chosen_packs or ["（本轮未纳入包成员节选）"])
    left_docs = max(0, len(doc_chunks) - len(chosen_docs))
    left_packs = max(0, len(pack_chunks) - len(chosen_packs))
    if left_docs or left_packs or used >= limit:
        parts.append(
            f"\n…(已达 PreSummary 同级输入上限 {limit} 字；"
            f"文档未纳入约 {left_docs}，包成员未纳入约 {left_packs})"
        )
    text = "\n\n".join(parts)
    if len(text) > limit:
        text = text[:limit]
    return text


def _call_deepseek(system: str, user: str, *, max_tokens: int = 4500) -> Tuple[str, str]:
    """固定 DeepSeek 链：v4-flash → v4-pro → deepseek-chat。"""
    from app_chat.cross_reorganize_skills import (
        _client_for_abbr,
        _collect_stream_text,
        _is_retryable_llm_error,
        _should_stream_llm,
    )

    chain = ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat"]
    last_exc: Optional[BaseException] = None
    used = chain[0]
    for attempt, abbr in enumerate(chain):
        try:
            client, model_name, create_extra = _client_for_abbr(abbr)
            use_stream = _should_stream_llm(abbr, model_name)
            print(
                f"[KnowledgeConflict] LLM step={attempt + 1}/{len(chain)} "
                f"abbr={abbr} model={model_name} stream={use_stream}",
                flush=True,
            )
            kwargs: Dict[str, Any] = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.25,
            }
            kwargs.update(create_extra)
            if use_stream:
                kwargs["stream"] = True
                text = _collect_stream_text(client.chat.completions.create(**kwargs))
            else:
                resp = client.chat.completions.create(**kwargs)
                text = (resp.choices[0].message.content or "").strip()
            return text, model_name or abbr
        except Exception as exc:
            last_exc = exc
            used = abbr
            if attempt >= len(chain) - 1 or not _is_retryable_llm_error(exc):
                raise
            time.sleep(8.0 if attempt == 0 else 12.0)
    raise last_exc  # pragma: no cover


def _extract_json_obj(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("冲突挖掘结果不是合法 JSON")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("冲突挖掘 JSON 根须为对象")
    return data


def _stable_feedback_key(item: Dict[str, Any]) -> str:
    """跨重挖稳定键：类别 + 标题 + 参与方 name（重编号 id 时仍可找回确认状态）。"""
    parties = item.get("parties") if isinstance(item.get("parties"), list) else []
    names = sorted({
        str(p.get("name") or p.get("title") or "").strip().lower()
        for p in parties if isinstance(p, dict)
    } - {""})
    title = re.sub(r"\s+", "", str(item.get("title") or "").lower())
    cat = re.sub(r"\s+", "", str(item.get("category") or "").lower())
    return f"{cat}::{title}::{'|'.join(names)}"


def _feedback_blob(src: Dict[str, Any]) -> Dict[str, Any]:
    status = str(src.get("user_status") or "pending")
    if status not in ("pending", "confirm", "unsure", "deny"):
        status = "pending"
    return {
        "user_status": status,
        "user_note": str(src.get("user_note") or "")[:2000],
        "user_updated_at": str(src.get("user_updated_at") or ""),
    }


def _build_feedback_ledger(prev: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    ledger: Dict[str, Dict[str, Any]] = {}
    if not prev:
        return ledger
    raw = prev.get("feedback_ledger")
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict) and str(k).strip():
                ledger[str(k)] = _feedback_blob(v)
    for it in prev.get("items") or []:
        if not isinstance(it, dict):
            continue
        key = _stable_feedback_key(it)
        if not key or key.count("::") < 2:
            continue
        blob = _feedback_blob(it)
        # 已有有效反馈优先保留
        if blob["user_status"] != "pending" or blob["user_note"]:
            ledger[key] = blob
        else:
            ledger.setdefault(key, blob)
    return ledger


def _lookup_feedback(
    cid: str,
    draft: Dict[str, Any],
    prev_by_id: Dict[str, Dict[str, Any]],
    ledger: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    if cid in prev_by_id:
        return _feedback_blob(prev_by_id[cid])
    key = _stable_feedback_key(draft)
    if key in ledger:
        return dict(ledger[key])
    # 标题兜底：类别空时仍尽量对齐
    title = re.sub(r"\s+", "", str(draft.get("title") or "").lower())
    if title:
        for lk, fb in ledger.items():
            parts = lk.split("::")
            if len(parts) >= 2 and parts[1] == title:
                return dict(fb)
    return {"user_status": "pending", "user_note": "", "user_updated_at": ""}


def _normalize_items(
    raw_items: Any,
    prev: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    prev_by_id: Dict[str, Dict[str, Any]] = {}
    if prev and isinstance(prev.get("items"), list):
        for it in prev["items"]:
            if isinstance(it, dict) and it.get("id"):
                prev_by_id[str(it["id"])] = it
    ledger = _build_feedback_ledger(prev)
    out: List[Dict[str, Any]] = []
    if not isinstance(raw_items, list):
        return out, ledger
    for i, it in enumerate(raw_items):
        if not isinstance(it, dict):
            continue
        cid = str(it.get("id") or f"kc_{i + 1:03d}").strip()[:64]
        draft = {
            "id": cid,
            "category": str(it.get("category") or "其他张力")[:40],
            "title": str(it.get("title") or "未命名冲突点")[:120],
            "parties": it.get("parties") if isinstance(it.get("parties"), list) else [],
        }
        fb = _lookup_feedback(cid, draft, prev_by_id, ledger)
        row = {
            "id": cid,
            "category": draft["category"],
            "title": draft["title"],
            "summary": str(it.get("summary") or it.get("insight") or "")[:220],
            "insight": str(it.get("insight") or it.get("summary") or "")[:360],
            "tension": str(it.get("tension") or "")[:280],
            "why_not_forced": str(it.get("why_not_forced") or it.get("caveat") or "")[:220],
            "parties": draft["parties"],
            "user_status": fb["user_status"],
            "user_note": fb["user_note"],
            "user_updated_at": fb["user_updated_at"],
        }
        out.append(row)
        key = _stable_feedback_key(row)
        if key:
            ledger[key] = _feedback_blob(row)
    return out, ledger


def _save_failed(
    username: str,
    prev: Optional[Dict[str, Any]],
    *,
    scene_name: str,
    err: str,
) -> None:
    save_conflicts(username, {
        "schema_version": SCHEMA,
        "status": "failed",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "model": (prev or {}).get("model") or "",
        "scene_name": scene_name or "",
        "stats": (prev or {}).get("stats") or {},
        "items": (prev or {}).get("items") or [],
        "feedback_ledger": (prev or {}).get("feedback_ledger") or {},
        "note": f"挖掘失败：{err}"[:500],
        "error": err[:300],
    })


def run_knowledge_conflict_mine(
    username: str,
    *,
    scene_name: str = "",
    job_id: str = "",
) -> Tuple[bool, str]:
    with _user_lock(username):
        prev = load_conflicts(username)
        try:
            if job_id:
                _set_job(job_id, phase="collect", msg="收集 Skill 节选")
            # 先落 running，便于 UI 轮询
            save_conflicts(username, {
                "schema_version": SCHEMA,
                "status": "running",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "model": "",
                "scene_name": scene_name or "",
                "stats": (prev or {}).get("stats") or {},
                "items": (prev or {}).get("items") or [],
                "feedback_ledger": (prev or {}).get("feedback_ledger") or {},
                "note": "挖掘进行中…",
            })
            docs, packs = _collect_skill_excerpts(username)
            if not docs and not packs:
                empty = {
                    "schema_version": SCHEMA,
                    "status": "ok",
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "model": "",
                    "scene_name": scene_name or "",
                    "stats": {"doc_skills": 0, "pack_skills": 0, "item_count": 0},
                    "items": [],
                    "feedback_ledger": (prev or {}).get("feedback_ledger") or {},
                    "note": "本子暂无可用文档/包 Skill，未做冲突挖掘",
                }
                save_conflicts(username, empty)
                return True, ""

            corpus = _budget_excerpts(docs, packs)
            system = (
                "你是严谨的教研知识审计员。根据多份 Skill 节选，挖掘彼此间「可能存在、且不牵强」的知识冲突或张力。"
                "只输出唯一 JSON 对象，不要 Markdown 围栏。"
                "要求：分类分点、点到为止；宁可少报，也不要把表述差异、互补关系硬说成冲突；"
                "文案务必短：读者一眼能扫完，禁止长篇铺陈。"
            )
            user = "\n".join([
                "请输出 JSON：",
                '{"items":[{"id":"kc_001","category":"概念定义|方法路径|目标优先级|适用范围|评价标准|其他张力",'
                '"title":"短标题(≤22字)","summary":"一句概述(≤40字)",'
                '"tension":"张力一句话(≤50字)","insight":"洞察一句话(≤60字)",'
                '"why_not_forced":"为何不牵强(≤40字)",'
                '"parties":[{"name":"skill-name","title":"标题","kind":"doc|pack"}]}]}',
                "条数建议 4～10；字段严格控长，不要多句段落；几乎无冲突可 items=[] 并加 note。",
                f"场景：{scene_name or '未指定'}",
                f"文档 Skill 数：{len(docs)}；包成员 Skill 数：{len(packs)}",
                f"输入字符上限（与文档 PreSummary 一致）：{_input_char_limit()}",
                "",
                "【Skill 节选】",
                corpus,
            ])
            if job_id:
                _set_job(job_id, phase="llm", msg="DeepSeek 挖掘中")
            raw, model_tag = _call_deepseek(system, user)
            obj = _extract_json_obj(raw)
            items, ledger = _normalize_items(obj.get("items"), prev)
            result = {
                "schema_version": SCHEMA,
                "status": "ok",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "model": model_tag,
                "scene_name": scene_name or "",
                "stats": {
                    "doc_skills": len(docs),
                    "pack_skills": len(packs),
                    "item_count": len(items),
                    "input_char_limit": _input_char_limit(),
                    "input_chars": len(corpus),
                },
                "items": items,
                "feedback_ledger": ledger,
                "note": str(obj.get("note") or "")[:500],
            }
            save_conflicts(username, result)
            print(
                f"[KnowledgeConflict] ok user={username} docs={len(docs)} packs={len(packs)} "
                f"items={len(items)} input={len(corpus)}/{_input_char_limit()}",
                flush=True,
            )
            return True, ""
        except Exception as e:
            traceback.print_exc()
            err = str(e)[:300]
            try:
                _save_failed(username, prev, scene_name=scene_name, err=err)
            except Exception:
                traceback.print_exc()
            print(f"[KnowledgeConflict] failed user={username}: {err}", flush=True)
            return False, err


def update_item_feedback(
    username: str,
    item_id: str,
    *,
    user_status: str = "",
    user_note: Optional[str] = None,
) -> Dict[str, Any]:
    data = load_conflicts(username)
    if not data:
        raise ValueError("尚无冲突挖掘结果")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("结果格式无效")
    found = None
    for it in items:
        if isinstance(it, dict) and str(it.get("id")) == str(item_id):
            found = it
            break
    if not found:
        raise ValueError("条目不存在")
    if user_status:
        if user_status not in ("pending", "confirm", "unsure", "deny"):
            raise ValueError("无效状态")
        found["user_status"] = user_status
    if user_note is not None:
        found["user_note"] = str(user_note)[:2000]
    found["user_updated_at"] = datetime.now().isoformat(timespec="seconds")
    data["updated_at"] = found["user_updated_at"]
    ledger = data.get("feedback_ledger")
    if not isinstance(ledger, dict):
        ledger = {}
    key = _stable_feedback_key(found)
    if key:
        ledger[key] = _feedback_blob(found)
    data["feedback_ledger"] = ledger
    save_conflicts(username, data)
    return found
