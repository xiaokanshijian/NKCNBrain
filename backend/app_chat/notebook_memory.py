# -*- coding: utf-8 -*-
"""
NKCN 本子/场景/账户长短记忆：写 → 用 → 压 → 升 → AutoDream。
路径均在 received_dir/memory_system/ 下；条目化存储便于索引/更新/剪枝。
"""
from __future__ import annotations
import nkcn_public_config as _public_config

import json
import os
import re
import threading
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# ---------- 预算（注入截断；磁盘保留全文）----------
BUDGET_USER = 1500
BUDGET_SCENE_RULE = 2000
BUDGET_SCENE_MEMORY = 2000
BUDGET_BOOK_RULE = 2000
BUDGET_BOOK_MEMORY = 2000
BUDGET_DAILY = 2500  # 今+昨合计
BUDGET_SNAPSHOT = 2000

WRITE_MODEL_DEFAULT = "deepseek-v4-flash"
DREAM_MODEL_DEFAULT = "claude-sonnet-5"
COMPACT_CHARS_SOFT = 12000
COMPACT_KEEP_ROUNDS = 3
DREAM_MIN_HOURS = 24
DREAM_MIN_WRITES = 5
HISTORY_ROOT = os.path.normpath("./received_dir/memory_system/_history")
HISTORY_KEEP_PER_FILE = 40  # 每个源文件最多保留的历史版本数
_MEMORY_SYSTEM_ROOT = os.path.normpath("./received_dir/memory_system")

_ENTRY_RE = re.compile(
    r"<!--NKCN_MEM_ENTRY\s*\n(.*?)\nNKCN_MEM_ENTRY-->",
    re.S,
)
_LOCK = threading.RLock()
_write_counters: Dict[str, int] = {}  # book_key -> writes since last dream


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _yesterday() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def log_notebook_memory(msg: str, account: str = "", book_key: str = "") -> None:
    """长短记忆统一日志：控制台 print + 写入 memory_system/_logs/日期.txt（便于测试排查）。"""
    msg = str(msg or "").rstrip()
    line = f"[notebook_memory] {msg}"
    print(line, flush=True)
    try:
        log_dir = os.path.normpath("./received_dir/memory_system/_logs")
        os.makedirs(log_dir, exist_ok=True)
        day = _today()
        path = os.path.join(log_dir, f"{day}.txt")
        # 同时追加一份固定文件名，方便总是打开同一个文件看最新
        latest = os.path.join(log_dir, "latest.txt")
        stamp = _now_str()
        acc = (account or "").strip()
        bk = (book_key or "").strip()
        body = f"{stamp}\t{acc}\t{bk}\t{msg}\n"
        with _LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(body)
            with open(latest, "a", encoding="utf-8") as f:
                f.write(body)
    except Exception:
        pass


# 模块内统一别名
_log = log_notebook_memory


def _is_memory_md_path(path: str) -> bool:
    """是否为需要版本留存的记忆 md（排除 _history/_logs 自身）。"""
    if not path or not str(path).lower().endswith(".md"):
        return False
    norm = os.path.normpath(path)
    root = _MEMORY_SYSTEM_ROOT
    try:
        rel = os.path.relpath(norm, root)
    except Exception:
        return False
    if rel.startswith(".."):
        return False
    parts = rel.replace("\\", "/").split("/")
    if not parts or parts[0] in ("_history", "_logs"):
        return False
    return True


def _history_snapshot_before_write(path: str) -> Optional[str]:
    """更新前把现有内容拷到 memory_system/_history/ 镜像路径，返回快照路径。"""
    if not _is_memory_md_path(path) or not os.path.isfile(path):
        return None
    try:
        old = ""
        with open(path, "r", encoding="utf-8") as f:
            old = f.read()
        if not old.strip():
            return None
        rel = os.path.relpath(os.path.normpath(path), _MEMORY_SYSTEM_ROOT)
        # _history/<相对目录>/<文件名>/<时间戳>.md
        base = os.path.basename(rel)
        parent = os.path.dirname(rel)
        hist_dir = os.path.join(HISTORY_ROOT, parent, base)
        os.makedirs(hist_dir, exist_ok=True)
        snap = os.path.join(hist_dir, f"{_now_stamp()}.md")
        with open(snap, "w", encoding="utf-8") as f:
            f.write(old)
        # 裁剪过多历史
        try:
            files = sorted(
                [os.path.join(hist_dir, x) for x in os.listdir(hist_dir) if x.endswith(".md")],
                key=lambda p: os.path.getmtime(p),
            )
            while len(files) > HISTORY_KEEP_PER_FILE:
                victim = files.pop(0)
                try:
                    os.remove(victim)
                except Exception:
                    break
        except Exception:
            pass
        _log(f"历史版本已留存 → {snap}")
        return snap
    except Exception as e:
        _log(f"历史版本留存失败 {path}: {e}")
        return None


def _write_text(path: str, content: str, *, skip_history: bool = False) -> None:
    """写文件；记忆相关 md 更新前先快照到 _history。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not skip_history:
        # 内容未变则不写、不留历史
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    if f.read() == (content or ""):
                        return
            except Exception:
                pass
        _history_snapshot_before_write(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content or "")


def split_account_book(username: str) -> Tuple[str, str]:
    """username = 账户_本子名（本子名可含下划线）。"""
    u = (username or "").strip()
    if "_" not in u:
        return u, ""
    account, book = u.split("_", 1)
    return account, book


def account_user_path(account: str) -> str:
    d = os.path.normpath("./received_dir/memory_system/user_memory")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{account}_USER.md")


def scene_dir(scene_name: str) -> str:
    safe = (scene_name or "未命名场景").strip().replace("\\", "_").replace("/", "_")
    d = os.path.normpath(f"./received_dir/memory_system/scene_memory/{safe}")
    os.makedirs(d, exist_ok=True)
    return d


def book_memory_dir(username: str) -> str:
    d = os.path.normpath(f"./received_dir/memory_system/book_memory/{username}")
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, "memory"), exist_ok=True)
    return d


def twin_dir(username: str) -> str:
    return os.path.normpath(f"./received_dir/user_raw_file/{username}/_twin")


def _read_text(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        _log(f"读失败 {path}: {e}")
        return ""


def ensure_book_templates(username: str) -> None:
    root = book_memory_dir(username)
    for name, title in (
        ("规矩.md", "# 本子规矩（白·边界/踩坑）\n\n"),
        ("MEMORY.md", "# 本子 MEMORY（白·精华）\n\n"),
    ):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            _write_text(p, title, skip_history=True)


def ensure_scene_templates(scene_name: str) -> None:
    root = scene_dir(scene_name)
    for name, title in (
        ("规矩.md", "# 场景规矩（白·边界/质量线）\n\n"),
        ("MEMORY.md", "# 场景 MEMORY（白·共性精华）\n\n"),
        ("相关场景关联.md", "# 相关场景关联（按需注入）\n\n"),
    ):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            _write_text(p, title, skip_history=True)


def ensure_user_template(account: str) -> None:
    p = account_user_path(account)
    if not os.path.isfile(p):
        _write_text(
            p,
            f"# USER · {account}\n\n"
            f"> 更新时间: {_now_str()}\n\n"
            "## 【性格画像】\n（待积累）\n\n"
            "## 【认知状态】\n（待积累）\n\n"
            "## 【交互偏好】\n（待积累）\n\n"
            "## 【专业基线】\n（待积累）\n\n"
            "## 【认知模式】\n（待积累）\n\n"
            "## 【社交与沟通方式】\n（待积累）\n\n"
            "## 【长期动机】\n（待积累）\n\n"
            "## 【近期活动条目】\n\n",
            skip_history=True,
        )


# ---------- 条目解析 / 序列化 ----------

def parse_entries(content: str) -> List[Dict[str, str]]:
    entries = []
    for m in _ENTRY_RE.finditer(content or ""):
        body = m.group(1)
        fields: Dict[str, str] = {}
        text_lines: List[str] = []
        in_text = False
        for line in body.splitlines():
            if in_text:
                text_lines.append(line)
                continue
            if line.startswith("text:"):
                in_text = True
                rest = line[5:].lstrip()
                if rest:
                    text_lines.append(rest)
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k.strip()] = v.strip()
        fields["text"] = "\n".join(text_lines).strip()
        if fields.get("id"):
            entries.append(fields)
    return entries


def serialize_entry(e: Dict[str, Any]) -> str:
    eid = str(e.get("id") or "001").strip()
    lines = [
        "<!--NKCN_MEM_ENTRY",
        f"id: {eid}",
        f"time: {e.get('time') or _now_str()}",
        f"type: {e.get('type') or 'fact'}",
        f"summary: {(e.get('summary') or '').replace(chr(10), ' ').strip()}",
        f"source: {(e.get('source') or '').replace(chr(10), ' ').strip()}",
        "text:",
        str(e.get("text") or "").rstrip(),
        "NKCN_MEM_ENTRY-->",
        "",
    ]
    return "\n".join(lines)


def entries_to_markdown(header: str, entries: List[Dict[str, str]]) -> str:
    parts = [header.rstrip() + "\n\n"]
    for e in entries:
        parts.append(serialize_entry(e))
    return "".join(parts)


def next_entry_id(entries: List[Dict[str, str]]) -> str:
    mx = 0
    for e in entries:
        try:
            mx = max(mx, int(re.sub(r"\D", "", str(e.get("id") or "0")) or 0))
        except Exception:
            pass
    return f"{mx + 1:03d}"


def load_entries_file(path: str) -> Tuple[str, List[Dict[str, str]]]:
    raw = _read_text(path)
    header = _ENTRY_RE.split(raw)[0] if raw else ""
    if not header.strip():
        header = f"# {os.path.basename(path)}\n\n"
    return header, parse_entries(raw)


def append_entries(path: str, new_entries: List[Dict[str, Any]], header_if_new: str = "") -> List[str]:
    with _LOCK:
        if not os.path.isfile(path):
            _write_text(path, header_if_new or f"# {os.path.basename(path)}\n\n", skip_history=True)
        header, entries = load_entries_file(path)
        added_ids = []
        for ne in new_entries:
            eid = str(ne.get("id") or "").strip() or next_entry_id(entries)
            ne = dict(ne)
            ne["id"] = eid
            ne.setdefault("time", _now_str())
            entries.append({k: str(v) if v is not None else "" for k, v in ne.items()})
            added_ids.append(eid)
        _write_text(path, entries_to_markdown(header, entries))
        return added_ids


def _norm_entry(x: Any, idx: int) -> Dict[str, str]:
    if not isinstance(x, dict):
        return {"id": f"{idx:03d}", "time": _now_str(), "type": "fact", "summary": "", "text": str(x), "source": "dream"}
    eid = str(x.get("id") or "").strip() or f"{idx:03d}"
    return {
        "id": eid,
        "time": str(x.get("time") or _now_str()),
        "type": str(x.get("type") or "fact"),
        "summary": str(x.get("summary") or "")[:200],
        "text": str(x.get("text") or ""),
        "source": str(x.get("source") or "dream"),
    }


def replace_entries(path: str, entries: List[Dict[str, str]], header: str = "") -> None:
    with _LOCK:
        if not header:
            header, _ = load_entries_file(path) if os.path.isfile(path) else (f"# {os.path.basename(path)}\n\n", [])
        _write_text(path, entries_to_markdown(header, entries))


def merge_entries_by_id(
    old_entries: List[Dict[str, str]],
    proposed: List[Any],
    delete_ids: Optional[List[Any]] = None,
) -> Tuple[List[Dict[str, str]], Dict[str, List[str]]]:
    """按 id 安全合并：未提及的旧条一律保留；仅显式 delete_ids 可删；同 id 覆盖更新；无 id/新 id 追加。

    返回 (merged_entries, stats)。
    """
    delete_set = {str(x).strip() for x in (delete_ids or []) if str(x).strip()}
    by_id: Dict[str, Dict[str, str]] = {}
    order: List[str] = []
    for e in old_entries or []:
        eid = str(e.get("id") or "").strip()
        if not eid:
            continue
        if eid in delete_set:
            continue
        by_id[eid] = dict(e)
        order.append(eid)

    updated, added = [], []
    for i, raw in enumerate(proposed or [], 1):
        ne = _norm_entry(raw, i)
        eid = str(ne.get("id") or "").strip()
        if eid and eid in delete_set:
            # 既在 delete 又在 proposed：以 delete 为准
            continue
        if eid and eid in by_id:
            # 保留旧 time 若新条未给有意义更新；一律用新字段覆盖
            old = by_id[eid]
            merged = dict(old)
            for k in ("type", "summary", "text", "source", "time"):
                if ne.get(k):
                    merged[k] = ne[k]
            by_id[eid] = merged
            updated.append(eid)
        else:
            if not eid or eid in by_id:
                eid = next_entry_id(list(by_id.values()))
                ne["id"] = eid
            by_id[eid] = ne
            order.append(eid)
            added.append(eid)

    deleted = sorted(delete_set)
    # 保持相对顺序：先旧序（已删跳过），再新增
    seen = set()
    result: List[Dict[str, str]] = []
    for eid in order:
        if eid in seen or eid not in by_id:
            continue
        seen.add(eid)
        result.append(by_id[eid])
    for eid, e in by_id.items():
        if eid not in seen:
            result.append(e)
    stats = {"updated": updated, "added": added, "deleted": deleted}
    return result, stats


def apply_merged_entries_to_file(
    path: str,
    proposed: List[Any],
    delete_ids: Optional[List[Any]] = None,
    *,
    header_if_new: str = "",
) -> Dict[str, List[str]]:
    """读盘 → merge → 写回；无有效变更则不写。"""
    with _LOCK:
        if not os.path.isfile(path):
            _write_text(path, header_if_new or f"# {os.path.basename(path)}\n\n", skip_history=True)
        header, old = load_entries_file(path)
        merged, stats = merge_entries_by_id(old, proposed, delete_ids)
        # 无任何 ops 时（proposed 空且 delete 空）保持原样
        if not (proposed or delete_ids):
            return {"updated": [], "added": [], "deleted": []}
        new_body = entries_to_markdown(header, merged)
        old_body = entries_to_markdown(header, old)
        if new_body == old_body:
            return stats
        _write_text(path, new_body)
        return stats


def format_entries_for_prompt(entries: List[Dict[str, str]], budget: int, prefer_summary_first: bool = True) -> str:
    if not entries:
        return "（暂无）"
    # 最近优先
    ordered = list(reversed(entries))
    chunks = []
    used = 0
    for e in ordered:
        summary = (e.get("summary") or "").strip()
        text = (e.get("text") or "").strip()
        head = f"- [{e.get('id')}|{e.get('type')}|{e.get('time')}] "
        if prefer_summary_first and summary:
            body = head + summary
            if text and text != summary:
                body += f"\n  详情: {text[:400]}"
        else:
            body = head + (text or summary)
        if used + len(body) > budget and chunks:
            break
        if used + len(body) > budget:
            body = body[: max(0, budget - used - 20)] + "…"
        chunks.append(body)
        used += len(body) + 1
    return "\n".join(chunks) if chunks else "（暂无）"


def _truncate(s: str, n: int) -> str:
    s = s or ""
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)] + "…"


# ---------- LLM ----------

def _call_llm(abbr: str, system: str, user: str, *, max_tokens: int = 4096, temperature: float = 0.3) -> str:
    from app_chat.scene_models import get_scene_value, resolve_openai_cfg_from_abbr

    slot_write = get_scene_value("notebook_memory_write", WRITE_MODEL_DEFAULT)
    slot_dream = get_scene_value("notebook_memory_dream", DREAM_MODEL_DEFAULT)
    if abbr == "write":
        model_abbr = slot_write or WRITE_MODEL_DEFAULT
    elif abbr == "dream":
        model_abbr = slot_dream or DREAM_MODEL_DEFAULT
    else:
        model_abbr = abbr

    cfg = resolve_openai_cfg_from_abbr(
        model_abbr,
        default_model=model_abbr,
        default_base=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
        default_key=_public_config.secret('OPENAI_API_KEY'),
    )
    # deepseek 官方优先
    if "deepseek" in model_abbr.lower():
        try:
            from app_chat.scene_models import resolve_openai_cfg_from_abbr as _r
            cfg2 = _r(model_abbr)
            if cfg2.get("api_key"):
                cfg = cfg2
        except Exception:
            pass
        if not cfg.get("base_url") or "cloudapi" in (cfg.get("base_url") or ""):
            # 尝试常见 deepseek 配置名
            for cand in (model_abbr, "deepseek-v4-flash", "deepseek-chat"):
                cfg = resolve_openai_cfg_from_abbr(cand)
                if cfg.get("api_key") and cfg.get("base_url"):
                    break

    client = OpenAI(
        api_key=cfg.get("api_key") or "EMPTY",
        base_url=(cfg.get("base_url") or _public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1')).rstrip("/"),
        timeout=120,
    )
    model = cfg.get("model") or model_abbr
    _log(f"LLM调用开始 kind={abbr} model={model} base={cfg.get('base_url')}")
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # deepseek-v4 可能支持 thinking；写记忆关闭
    if "deepseek" in model.lower():
        try:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        except Exception:
            pass
    resp = client.chat.completions.create(**kwargs)
    content = (resp.choices[0].message.content or "").strip()
    _log(f"LLM调用结束 kind={abbr} model={model} out_chars={len(content)}")
    return content


def _call_llm_retry(kind: str, system: str, user: str, retries: int = 2) -> str:
    last = ""
    for i in range(retries + 1):
        try:
            return _call_llm(kind, system, user)
        except Exception as e:
            last = str(e)
            _log(f"LLM({kind}) 失败 try={i + 1}: {e}")
    return ""


def _parse_json_array(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    t = text.strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
        if m:
            t = m.group(1).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict) and isinstance(obj.get("entries"), list):
            return [x for x in obj["entries"] if isinstance(x, dict)]
    except Exception:
        pass
    m = re.search(r"\[[\s\S]*\]", t)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
        except Exception:
            pass
    return []


# ---------- 本子快照 ----------

def build_book_snapshot(username: str, scene_name: str = "", sub_scene: str = "", budget: int = BUDGET_SNAPSHOT) -> str:
    account, book = split_account_book(username)
    parts = []
    book_desc = ""
    try:
        def _fetch_desc():
            from app_chat.scene_context_helper import get_notebook_description
            return get_notebook_description(username, scene_name) or ""

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            book_desc = pool.submit(_fetch_desc).result(timeout=8) or ""
    except Exception:
        book_desc = ""
    if not book_desc:
        book_desc = book
    parts.append(f"本子: {book_desc} | 场景: {scene_name or '-'} | 子场景: {sub_scene or '-'}")

    # 文档名
    docs = []
    raw_dir = os.path.normpath(f"./received_dir/user_raw_file/{username}")
    if os.path.isdir(raw_dir):
        for f in sorted(os.listdir(raw_dir)):
            if f.startswith(".") or f in ("cardImage", "pre_summary", "pre_image_summary", "_twin", "cardCondense", "pre_tribal_knowledge", "skills", "_socratic_meta"):
                continue
            fp = os.path.join(raw_dir, f)
            if os.path.isfile(fp):
                if f.lower().endswith(".zip"):
                    continue
                docs.append(f)
            elif os.path.isdir(fp) and not f.endswith("_ocr"):
                # 跳过内部目录
                pass
    if docs:
        parts.append("文档名列表: " + "、".join(docs[:40]) + ("…" if len(docs) > 40 else ""))

    # 近期卡片（问答在 async 流里注入，ORM 必须放到线程里跑）
    try:
        def _fetch_cards():
            from app_chat.models import Card
            return list(
                Card.objects.filter(username=username).order_by("-cid").values("cid", "contentTitle")[:15]
            )

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            cards = pool.submit(_fetch_cards).result(timeout=8)
        if cards:
            parts.append(
                "近期卡片: "
                + "；".join(f"{c.get('cid')}:{(c.get('contentTitle') or '')[:30]}" for c in cards)
            )
    except Exception as e:
        _log(f"读卡片失败: {e}")

    # 语义关键词 / bookKeyIssue
    cond = os.path.join(raw_dir, "cardCondense")
    for fn in ("bookKeyIssue.txt", "bookKWConnect.txt"):
        p = os.path.join(cond, fn)
        body = _read_text(p).strip()
        if body:
            parts.append(f"{fn}:\n{_truncate(body, 600)}")

    # 最近问题链：扫近 5 日日记里的提问原话
    q_lines = []
    for i in range(0, 5):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        _, ents = load_entries_file(os.path.join(book_memory_dir(username), "memory", f"{day}.md"))
        for e in reversed(ents):
            if e.get("type") in ("context", "question") or (e.get("source") or "").startswith("qa"):
                s = (e.get("summary") or e.get("text") or "")[:80]
                if s:
                    q_lines.append(f"{e.get('time')}: {s}")
            if len(q_lines) >= 5:
                break
        if len(q_lines) >= 5:
            break
    if q_lines:
        parts.append("最近问题链:\n" + "\n".join(q_lines[:5]))

    return _truncate("\n".join(parts), budget)


# ---------- 注入 ----------

def build_memory_injection_block(
    username: str,
    *,
    scene_name: str = "",
    sub_scene: str = "",
    question: str = "",
    enabled: bool = True,
) -> str:
    if not enabled:
        return ""
    account, _book = split_account_book(username)
    if not account:
        return ""

    ensure_user_template(account)
    ensure_book_templates(username)
    if scene_name:
        ensure_scene_templates(scene_name)

    blocks = ["【本子记忆与现状】（条目化长短记忆；灰区日记可能未完全校验）"]

    # USER
    user_raw = _read_text(account_user_path(account))
    blocks.append("## 账户 USER.md 节选\n" + _truncate(user_raw, BUDGET_USER))

    # 场景
    if scene_name:
        sd = scene_dir(scene_name)
        _, rules = load_entries_file(os.path.join(sd, "规矩.md"))
        _, mems = load_entries_file(os.path.join(sd, "MEMORY.md"))
        # 若尚无条目，仍给文件头说明
        rule_txt = format_entries_for_prompt(rules, BUDGET_SCENE_RULE) if rules else _truncate(_read_text(os.path.join(sd, "规矩.md")), BUDGET_SCENE_RULE)
        mem_txt = format_entries_for_prompt(mems, BUDGET_SCENE_MEMORY) if mems else _truncate(_read_text(os.path.join(sd, "MEMORY.md")), BUDGET_SCENE_MEMORY)
        blocks.append("## 场景规矩\n" + rule_txt)
        blocks.append("## 场景 MEMORY\n" + mem_txt)

        # 显式他场景
        q = question or ""
        if re.search(r"(对比|对照|承接|另一个场景|其他场景|跨场景)", q):
            rel = _read_text(os.path.join(sd, "相关场景关联.md"))
            if rel.strip():
                blocks.append("## 相关场景关联（用户显式提及）\n" + _truncate(rel, 1500))

    bd = book_memory_dir(username)
    _, br = load_entries_file(os.path.join(bd, "规矩.md"))
    _, bm = load_entries_file(os.path.join(bd, "MEMORY.md"))
    book_rule_txt = (
        format_entries_for_prompt(br, BUDGET_BOOK_RULE)
        if br
        else _truncate(_read_text(os.path.join(bd, "规矩.md")), BUDGET_BOOK_RULE)
    )
    book_mem_txt = (
        format_entries_for_prompt(bm, BUDGET_BOOK_MEMORY)
        if bm
        else _truncate(_read_text(os.path.join(bd, "MEMORY.md")), BUDGET_BOOK_MEMORY)
    )
    blocks.append("## 本子规矩\n" + book_rule_txt)
    blocks.append("## 本子 MEMORY\n" + book_mem_txt)

    daily_ents: List[Dict[str, str]] = []
    for day in (_today(), _yesterday()):
        p = os.path.join(bd, "memory", f"{day}.md")
        _, ents = load_entries_file(p)
        daily_ents.extend(ents)
    blocks.append(
        "## 近日日记（今/昨，灰区）\n"
        + format_entries_for_prompt(daily_ents, BUDGET_DAILY)
    )

    blocks.append("## 本子现状快照\n" + build_book_snapshot(username, scene_name, sub_scene))

    # twin 按需
    if re.search(r"(G\d{1,2}|第?\d{1,2}组|组号)", question or "", re.I):
        try:
            from app_chat.group_twin_gxx import read_twin_file
            m = re.search(r"G\s*(\d{1,2})", question or "", re.I) or re.search(r"(\d{1,2})\s*组", question or "")
            if m:
                gid = int(m.group(1))
                twin_name = f"G{gid:02d}"
                body = read_twin_file(username, twin_name) or ""
                if body.strip():
                    blocks.append(f"## _twin/{twin_name}.md 节选\n" + _truncate(body, 3000))
        except Exception as e:
            _log(f"twin 读取失败: {e}")

    out = "\n\n".join(blocks)
    _log(f"注入块 chars={len(out)} scene={scene_name!r}", account=account, book_key=username)
    return out


# ---------- 写 / 升 ----------

_EXTRACT_SYS = """你是记忆萃取助手。根据本轮用户提问与助手回答，抽出若干条「一条一事」的记忆候选。
相对时间尽量改成绝对日期（今天按给定基准日理解）。
只输出 JSON 数组，每项字段：
type: fact|rule|feedback|goal|context|scene 之一
tier: gray|memory|rule|scene_memory|scene_rule
summary: 一两句摘要
text: 完整一条内容
source: 简短来源说明
规则：
- 默认可标 tier=gray（进当日日记）
- 用户明确记住/纠正/认可/以后都按这个 → tier=memory
- 明确别再/禁止类 → tier=rule
- 明显整个场景通用 → scene_memory 或 scene_rule
- 不要编造；没有值得记的就输出 []
"""


def extract_memory_candidates(user_q: str, assistant_a: str, base_date: str = "") -> List[Dict[str, Any]]:
    base_date = base_date or _today()
    user = (
        f"基准日: {base_date}\n\n【用户问】\n{_truncate(user_q, 4000)}\n\n"
        f"【助手答】\n{_truncate(assistant_a, 6000)}\n\n请输出 JSON 数组。"
    )
    raw = _call_llm_retry("write", _EXTRACT_SYS, user, retries=1)
    items = _parse_json_array(raw)
    cleaned = []
    for it in items:
        text = str(it.get("text") or "").strip()
        if not text:
            continue
        cleaned.append({
            "type": str(it.get("type") or "fact").strip() or "fact",
            "tier": str(it.get("tier") or "gray").strip() or "gray",
            "summary": str(it.get("summary") or text[:60]).strip(),
            "text": text,
            "source": str(it.get("source") or "qa").strip(),
            "time": _now_str(),
        })
    return cleaned


def write_after_qa(
    username: str,
    user_q: str,
    assistant_a: str,
    *,
    scene_name: str = "",
    sub_scene: str = "",
) -> Dict[str, Any]:
    account, _ = split_account_book(username)
    ensure_book_templates(username)
    if scene_name:
        ensure_scene_templates(scene_name)
    ensure_user_template(account)

    result = {"gray": [], "memory": [], "rule": [], "scene": []}
    bd = book_memory_dir(username)
    daily_path = os.path.join(bd, "memory", f"{_today()}.md")

    # 先落盘问题链 + 活动流水，不堵在 LLM 萃取后面（避免萃取慢/挂导致「只有空骨架」）
    if user_q and user_q.strip():
        try:
            result["gray"] = append_entries(
                daily_path,
                [{
                    "type": "context",
                    "summary": _truncate(user_q.strip().replace("\n", " "), 80),
                    "text": _truncate(user_q.strip(), 500),
                    "source": "qa-question",
                    "time": _now_str(),
                }],
                header_if_new=f"# 日记 {_today()}\n\n",
            )
            _update_user_activity(account, username, scene_name, user_q)
            _bump_write_counter(username)
            _log(
                f"写记忆·先落问题链 gray={result['gray']}",
                account=account,
                book_key=username,
            )
        except Exception as e:
            _log(f"写记忆·先落问题链失败: {e}\n{traceback.format_exc()}", account=account, book_key=username)

    try:
        cands = extract_memory_candidates(user_q, assistant_a)
    except Exception as e:
        _log(f"萃取异常: {e}\n{traceback.format_exc()}", account=account, book_key=username)
        cands = []

    gray_batch, mem_batch, rule_batch = [], [], []
    scene_mem_batch, scene_rule_batch = [], []

    for c in cands:
        tier = (c.get("tier") or "gray").lower()
        entry = {
            "time": c.get("time") or _now_str(),
            "type": c.get("type") or "fact",
            "summary": c.get("summary") or "",
            "text": c.get("text") or "",
            "source": c.get("source") or "qa",
        }
        if tier in ("memory", "white_memory"):
            mem_batch.append(entry)
        elif tier in ("rule", "white_rule"):
            rule_batch.append(entry)
        elif tier == "scene_memory":
            scene_mem_batch.append(entry)
        elif tier == "scene_rule":
            scene_rule_batch.append(entry)
        else:
            # 问题链已先落盘，萃取里的 context 仍可追加
            gray_batch.append(entry)

    if gray_batch:
        result["gray"] = result.get("gray") or []
        result["gray"] = list(result["gray"]) + append_entries(
            daily_path, gray_batch, header_if_new=f"# 日记 {_today()}\n\n"
        )
    if mem_batch:
        result["memory"] = append_entries(os.path.join(bd, "MEMORY.md"), mem_batch)
    if rule_batch:
        result["rule"] = append_entries(os.path.join(bd, "规矩.md"), rule_batch)
    if scene_name and scene_mem_batch:
        result["scene"] += append_entries(os.path.join(scene_dir(scene_name), "MEMORY.md"), scene_mem_batch)
    if scene_name and scene_rule_batch:
        result["scene"] += append_entries(os.path.join(scene_dir(scene_name), "规矩.md"), scene_rule_batch)

    _log(
        f"写记忆·萃取完成 gray+={len(gray_batch)} memory={result['memory']} rule={result['rule']} scene={result['scene']}",
        account=account,
        book_key=username,
    )
    return result


def _bump_write_counter(username: str) -> None:
    with _LOCK:
        _write_counters[username] = _write_counters.get(username, 0) + 1
        meta_path = os.path.join(book_memory_dir(username), ".dream_meta.json")
        meta = {}
        if os.path.isfile(meta_path):
            try:
                meta = json.loads(_read_text(meta_path) or "{}")
            except Exception:
                meta = {}
        meta["writes_since_dream"] = int(meta.get("writes_since_dream") or 0) + 1
        _write_text(meta_path, json.dumps(meta, ensure_ascii=False, indent=2))


def _update_user_activity(account: str, username: str, scene_name: str, question: str) -> None:
    """轻量更新 USER 近期活动条目；画像大段留给 Dream。"""
    ensure_user_template(account)
    path = account_user_path(account)
    raw = _read_text(path)
    # 追加活动条目到文件末尾「近期活动」区
    _, book = split_account_book(username)
    _, existing = load_entries_file(path) if "<!--NKCN_MEM_ENTRY" in raw else ("", [])
    entry = {
        "id": next_entry_id(existing) if existing else datetime.now().strftime("%Y%m%d%H%M%S"),
        "time": _now_str(),
        "type": "context",
        "summary": f"场景={scene_name or '-'} 本子={book} 问={_truncate(question, 60)}",
        "text": f"scene={scene_name}\nbook={username}\nquestion={_truncate(question, 300)}",
        "source": "activity",
    }
    # 若已有 entries 区则 append；否则追加区块
    if "<!--NKCN_MEM_ENTRY" in raw:
        append_entries(path, [entry])
    else:
        with _LOCK:
            raw2 = _read_text(path)
            stamp = f"\n\n> 最近活动更新: {_now_str()}\n"
            raw2 = re.sub(r"> 最近活动更新:.*", "", raw2)
            if "## 【近期活动条目】" not in raw2:
                raw2 += "\n## 【近期活动条目】\n\n"
            raw2 = raw2.rstrip() + stamp + "\n" + serialize_entry(entry)
            # 保留最近约 40 条活动
            ents = parse_entries(raw2)
            if len(ents) > 40:
                # 重建：保留非 entry 头 + 最近 40
                header = _ENTRY_RE.split(raw2)[0]
                raw2 = entries_to_markdown(header, ents[-40:])
            _write_text(path, raw2)


def maybe_autodream_after_write(username: str, scene_name: str = "") -> Optional[Dict[str, Any]]:
    meta_path = os.path.join(book_memory_dir(username), ".dream_meta.json")
    meta = {}
    if os.path.isfile(meta_path):
        try:
            meta = json.loads(_read_text(meta_path) or "{}")
        except Exception:
            meta = {}
    writes = int(meta.get("writes_since_dream") or 0)
    last = meta.get("last_dream_at") or ""
    due = writes >= DREAM_MIN_WRITES
    if last:
        try:
            lt = datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")
            if datetime.now() - lt < timedelta(hours=DREAM_MIN_HOURS):
                due = False
        except Exception:
            pass
    else:
        # 从未 dream：达到写入次数即可
        pass
    if not due:
        return None
    return run_autodream(username, scene_name=scene_name, manual=False)


# ---------- 压 ----------

def flush_old_turns_to_daily(username: str, turns: List[Dict[str, str]]) -> List[str]:
    """turns: [{q,a}, ...] 较早轮 → 灰区日记。"""
    if not turns:
        return []
    batch = []
    for t in turns:
        q = (t.get("q") or t.get("message") or "").strip()
        a = (t.get("a") or t.get("AImessage") or "").strip()
        if not q and not a:
            continue
        batch.append({
            "time": _now_str(),
            "type": "context",
            "summary": _truncate(q or a, 80),
            "text": f"Q: {_truncate(q, 400)}\nA: {_truncate(a, 600)}",
            "source": "flush",
        })
    path = os.path.join(book_memory_dir(username), "memory", f"{_today()}.md")
    return append_entries(path, batch, header_if_new=f"# 日记 {_today()}\n\n")


def compact_history_text(old_turns: List[Dict[str, str]]) -> str:
    if not old_turns:
        return ""
    blob = []
    for t in old_turns:
        blob.append(f"Q: {_truncate(t.get('q') or t.get('message') or '', 300)}")
        blob.append(f"A: {_truncate(t.get('a') or t.get('AImessage') or '', 500)}")
    user = "请将下列较早对话压缩为不超过800字的要点纪要，保留用户原话关键纠正与结论：\n\n" + "\n".join(blob)
    return _call_llm_retry("write", "你是对话压缩助手，只输出压缩后的中文纪要。", user, retries=1)


def maybe_compact_chat_history(username: str, chat_history_list: List[dict], rounds: int) -> List[dict]:
    """若历史过长：先 flush 再压缩较早轮，保留最近 N 轮。"""
    if not chat_history_list:
        return chat_history_list

    total = sum(
        len(str(x.get("message") or "")) + len(str(x.get("AImessage") or ""))
        for x in chat_history_list
    )
    # 轮数未超且字数未超：不压
    if len(chat_history_list) <= max(1, rounds) and total < COMPACT_CHARS_SOFT:
        return chat_history_list

    keep_n = min(COMPACT_KEEP_ROUNDS, max(1, rounds))
    # 至少保留 keep_n；若只剩 keep_n 条但字数仍爆，再压缩到 keep_n-1（最少 1）
    if len(chat_history_list) <= keep_n:
        if total < COMPACT_CHARS_SOFT or keep_n <= 1:
            return chat_history_list
        keep_n = max(1, keep_n - 1)

    if len(chat_history_list) <= keep_n:
        return chat_history_list

    old = chat_history_list[:-keep_n]
    recent = chat_history_list[-keep_n:]
    flush_old_turns_to_daily(username, [{"q": x.get("message"), "a": x.get("AImessage")} for x in old])
    summary = compact_history_text([{"q": x.get("message"), "a": x.get("AImessage")} for x in old])
    if summary:
        compacted = [{
            "filelist": [],
            "message": "【系统】较早对话已压缩（详见本子 memory 日记）",
            "AImessage": summary,
        }]
        _log(f"压缩历史 old_turns={len(old)} keep={keep_n}", book_key=username)
        return compacted + recent
    return chat_history_list


# ---------- AutoDream ----------

_DREAM_SYS = """你是记忆整理助手（AutoDream）。对给定记忆条目做：合并同义、修正矛盾、相对时间改绝对、删除黑区废话。

【极重要】系统按「补丁合并」落盘，不是整文件覆盖：
- 你在 book_memory / book_rules / daily_keep 里给出的条目 = 要更新或新增的条目（同 id 覆盖更新；无 id 或新 id 追加）。
- 未出现在列表里的旧条目会自动保留，切勿为了「输出全量」而漏条。
- 要删除某条，必须把其 id 放进对应的 *_delete_ids（日记用 daily_delete_ids）。
- 同义合并：保留一条（update 其 text/summary），并把被吃掉的 id 放进 delete_ids。

只输出合法 JSON（可包在 ```json 代码块中）：
{
  "book_memory": [条目...],           // 仅变更/新增；无改动则 [] 或不写
  "book_memory_delete_ids": ["003"], // 显式删除
  "book_rules": [条目...],
  "book_rules_delete_ids": [],
  "daily_keep": { "YYYY-MM-DD": [条目...] },
  "daily_delete_ids": { "YYYY-MM-DD": ["id"...] },
  "scene_memory_add": [条目...],     // 仅追加上浮到场景
  "scene_rules_add": [条目...],
  "user_portrait": "可选：更新后的 USER 画像 Markdown（含各【】小节，勿丢标题）",
  "log": ["改了什么 id 的说明", ...]
}
每条条目字段：id,time,type,summary,text,source
矛盾以较新且具体的为准并修正旧义；不要编造。
字符串内若需引号，请用「」或转义为 \\"，禁止在 JSON 字符串里直接写未转义的英文双引号 "。
"""


def _escape_bare_quotes_inside_json_strings(s: str) -> str:
    """
    扫描类 JSON 文本：已在字符串值内、且不是键/值结束符的裸 " 转成 \\"。
    用于修复模型把「反问"xxx"」直接写进 JSON 字符串的情况。
    """
    out: List[str] = []
    i = 0
    n = len(s)
    in_string = False
    while i < n:
        c = s[i]
        if not in_string:
            out.append(c)
            if c == '"':
                in_string = True
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(c)
            out.append(s[i + 1])
            i += 2
            continue
        if c == '"':
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            # 结构结束：" 后跟 , } ] : 或文件结束 → 真正的字符串收尾
            if j >= n or s[j] in ",}]:":
                out.append(c)
                in_string = False
                i += 1
                continue
            out.append('\\"')
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _repair_dream_json_text(t: str) -> str:
    """尽量修复模型常见非法 JSON：弯引号 + 字符串内未转义直双引号。"""
    s = (t or "").strip()
    if not s:
        return s
    s = (
        s.replace("\u201c", "「")
        .replace("\u201d", "」")
        .replace("\u2018", "『")
        .replace("\u2019", "』")
    )
    # 汉字"短词"汉字 / 汉字"短词"破折号标点
    s = re.sub(
        r'(?<=[\u4e00-\u9fff])"([^"\n]{1,80}?)"(?=[\u4e00-\u9fff\u2014\u2013，。！？：；、）》」』])',
        r"「\1」",
        s,
    )
    s = _escape_bare_quotes_inside_json_strings(s)
    return s


def _parse_dream_json(raw: str) -> Dict[str, Any]:
    """从 Dream 原始输出解析 JSON 对象；失败返回 {}。"""
    t = (raw or "").strip()
    if not t:
        return {}
    if "```" in t:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
        if m:
            t = m.group(1).strip()
    candidates = [t]
    m2 = re.search(r"\{[\s\S]*\}", t)
    if m2 and m2.group(0) not in candidates:
        candidates.append(m2.group(0))
    for cand in candidates:
        for variant in (cand, _repair_dream_json_text(cand)):
            try:
                obj = json.loads(variant)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
    return {}


def run_autodream(username: str, scene_name: str = "", manual: bool = False) -> Dict[str, Any]:
    account, _ = split_account_book(username)
    lock_path = os.path.join(book_memory_dir(username), ".dream.lock")
    if os.path.isfile(lock_path):
        try:
            # 过期锁 1h
            if time_module_age(lock_path) < 3600:
                return {"ok": False, "msg": "dream busy"}
        except Exception:
            pass
    _write_text(lock_path, _now_str(), skip_history=True)
    out: Dict[str, Any] = {"ok": False, "manual": manual}
    try:
        ensure_book_templates(username)
        if scene_name:
            ensure_scene_templates(scene_name)
        ensure_user_template(account)

        bd = book_memory_dir(username)
        _, book_mem = load_entries_file(os.path.join(bd, "MEMORY.md"))
        _, book_rules = load_entries_file(os.path.join(bd, "规矩.md"))
        daily = {}
        for i in range(0, 5):
            day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            p = os.path.join(bd, "memory", f"{day}.md")
            if os.path.isfile(p):
                _, ents = load_entries_file(p)
                if ents:
                    daily[day] = ents

        scene_mem, scene_rules = [], []
        if scene_name:
            sd = scene_dir(scene_name)
            _, scene_mem = load_entries_file(os.path.join(sd, "MEMORY.md"))
            _, scene_rules = load_entries_file(os.path.join(sd, "规矩.md"))

        user_raw = _read_text(account_user_path(account))
        payload = {
            "book_memory": book_mem,
            "book_rules": book_rules,
            "daily": daily,
            "scene_memory": scene_mem,
            "scene_rules": scene_rules,
            "user_md_excerpt": _truncate(user_raw, 3000),
            "now": _now_str(),
            "book": username,
            "scene": scene_name,
            "merge_policy": "patch_by_id_keep_unmentioned_delete_only_via_delete_ids",
        }
        user = "请按补丁合并策略整理下列记忆 JSON：\n" + json.dumps(payload, ensure_ascii=False)[:50000]
        raw = _call_llm_retry("dream", _DREAM_SYS, user, retries=2)
        if not raw:
            # 降级 flash
            _log("Dream 主模型失败，降级 write 模型", account=account, book_key=username)
            raw = _call_llm_retry("write", _DREAM_SYS, user, retries=1)

        data = _parse_dream_json(raw or "")

        if not isinstance(data, dict) or not data:
            out = {"ok": False, "msg": "Dream 无有效 JSON 输出", "manual": manual}
            text = raw if isinstance(raw, str) else str(raw or "")
            try:
                dump_dir = os.path.normpath("./received_dir/memory_system/_logs")
                os.makedirs(dump_dir, exist_ok=True)
                dump_path = os.path.join(
                    dump_dir,
                    f"dream_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                )
                with open(dump_path, "w", encoding="utf-8") as df:
                    df.write(text)
                _log(
                    f"AutoDream 解析失败 raw_len={len(text)} → {dump_path}",
                    account=account,
                    book_key=username,
                )
            except Exception as e:
                _log(
                    f"AutoDream 解析失败 raw_len={len(text)} 另存失败: {e}",
                    account=account,
                    book_key=username,
                )
            return out

        merge_log: Dict[str, Any] = {}
        changed = False

        mem_prop = data.get("book_memory") if isinstance(data.get("book_memory"), list) else []
        mem_del = data.get("book_memory_delete_ids") if isinstance(data.get("book_memory_delete_ids"), list) else []
        if mem_prop or mem_del:
            st = apply_merged_entries_to_file(os.path.join(bd, "MEMORY.md"), mem_prop, mem_del)
            merge_log["book_memory"] = st
            if st.get("updated") or st.get("added") or st.get("deleted"):
                changed = True

        rule_prop = data.get("book_rules") if isinstance(data.get("book_rules"), list) else []
        rule_del = data.get("book_rules_delete_ids") if isinstance(data.get("book_rules_delete_ids"), list) else []
        if rule_prop or rule_del:
            st = apply_merged_entries_to_file(os.path.join(bd, "规矩.md"), rule_prop, rule_del)
            merge_log["book_rules"] = st
            if st.get("updated") or st.get("added") or st.get("deleted"):
                changed = True

        daily_keep = data.get("daily_keep") if isinstance(data.get("daily_keep"), dict) else {}
        daily_del = data.get("daily_delete_ids") if isinstance(data.get("daily_delete_ids"), dict) else {}
        days = set(list(daily_keep.keys()) + list(daily_del.keys()))
        for day in days:
            prop = daily_keep.get(day) if isinstance(daily_keep.get(day), list) else []
            dels = daily_del.get(day) if isinstance(daily_del.get(day), list) else []
            if not prop and not dels:
                continue
            p = os.path.join(bd, "memory", f"{day}.md")
            st = apply_merged_entries_to_file(p, prop, dels, header_if_new=f"# 日记 {day}\n\n")
            merge_log[f"daily:{day}"] = st
            if st.get("updated") or st.get("added") or st.get("deleted"):
                changed = True

        if scene_name and isinstance(data.get("scene_memory_add"), list):
            add = [_norm_entry(x, i) for i, x in enumerate(data["scene_memory_add"], 1)]
            if add:
                for a in add:
                    a["source"] = (a.get("source") or "") + f"|from:{username}"
                append_entries(os.path.join(scene_dir(scene_name), "MEMORY.md"), add)
                changed = True
                merge_log["scene_memory_add"] = [a.get("id") for a in add]
        if scene_name and isinstance(data.get("scene_rules_add"), list):
            add = [_norm_entry(x, i) for i, x in enumerate(data["scene_rules_add"], 1)]
            if add:
                append_entries(os.path.join(scene_dir(scene_name), "规矩.md"), add)
                changed = True
                merge_log["scene_rules_add"] = [a.get("id") for a in add]

        portrait = data.get("user_portrait")
        if isinstance(portrait, str) and portrait.strip() and len(portrait.strip()) > 80:
            # 保留活动条目
            old_ents = parse_entries(_read_text(account_user_path(account)))
            activity = [e for e in old_ents if e.get("source") == "activity"]
            new_body = portrait.strip()
            if activity:
                new_body = new_body.rstrip() + "\n\n## 【近期活动条目】\n\n" + "".join(serialize_entry(e) for e in activity[-30:])
            _write_text(account_user_path(account), new_body)
            changed = True
            merge_log["user_portrait"] = True

        # 仅在解析成功时重置计数（即使模型认为无需改动，也算完成一次 Dream）
        meta_path = os.path.join(bd, ".dream_meta.json")
        meta = {
            "last_dream_at": _now_str(),
            "writes_since_dream": 0,
            "log": data.get("log") or [],
            "merge": merge_log,
            "changed": changed,
        }
        _write_text(meta_path, json.dumps(meta, ensure_ascii=False, indent=2), skip_history=True)
        out = {"ok": True, "log": meta["log"], "manual": manual, "changed": changed, "merge": merge_log}
        _log(f"AutoDream 完成 changed={changed} merge={merge_log} log={meta['log']}", account=account, book_key=username)
    except Exception as e:
        out = {"ok": False, "msg": str(e), "manual": manual}
        _log(f"AutoDream 异常: {e}\n{traceback.format_exc()}", account=account, book_key=username)
    finally:
        try:
            if os.path.isfile(lock_path):
                os.remove(lock_path)
        except Exception:
            pass
    return out


def time_module_age(path: str) -> float:
    return max(0.0, datetime.now().timestamp() - os.path.getmtime(path))


def start_write_after_qa_background(
    username: str,
    user_q: str,
    assistant_a: str,
    scene_name: str = "",
    sub_scene: str = "",
) -> None:
    def _run():
        try:
            try:
                from django.db import close_old_connections
                close_old_connections()
            except Exception:
                pass
            _log(f"后台写记忆开始", book_key=username)
            write_after_qa(username, user_q, assistant_a, scene_name=scene_name, sub_scene=sub_scene)
            maybe_autodream_after_write(username, scene_name=scene_name)
            _log(f"后台写记忆结束", book_key=username)
        except Exception as e:
            _log(f"后台写记忆失败: {e}\n{traceback.format_exc()}", book_key=username)
        finally:
            try:
                from django.db import close_old_connections
                close_old_connections()
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()
