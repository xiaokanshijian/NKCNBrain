# -*- coding: utf-8 -*-
"""交叉梳理 1+n Skill：规划 → 写 n 份 → hub 微调 → 索引 / 历史。"""
from __future__ import annotations
import nkcn_public_config as _public_config

import json
import os
import re
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from app_chat import skills_store as store
from app_chat.doc_structure import presummary_max_content_chars, truncate_like_presummary
from app_chat.skill_generate import QUALITY_PROMPT, _extract_skill_md

CROSS_DIR = "_cross_reorganize"
PLAN_NAME = "_plan.json"
INDEX_CROSS_NAME = "_index_cross.json"
HISTORY_DIR = "_history"
HUB_BAK_NAME = "notebook-hub.SKILL.md.bak"

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


def cross_root(username: str) -> str:
    path = os.path.join(store.skills_root(username), CROSS_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def plan_path(username: str) -> str:
    return os.path.join(cross_root(username), PLAN_NAME)


def index_cross_path(username: str) -> str:
    return os.path.join(cross_root(username), INDEX_CROSS_NAME)


def theme_skill_dir(username: str, slug: str) -> str:
    return os.path.join(cross_root(username), slug)


def theme_skill_md(username: str, slug: str) -> str:
    return os.path.join(theme_skill_dir(username, slug), "SKILL.md")


def load_index_cross(username: str) -> Optional[Dict[str, Any]]:
    path = index_cross_path(username)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_index_cross(username: str, data: Dict[str, Any]) -> None:
    path = index_cross_path(username)
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


def start_cross_reorganize_job(username: str, scene_name: str = "") -> str:
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
            ok, err = run_cross_reorganize_skills(username, scene_name=scene_name, job_id=job_id)
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


def _snapshot_history(username: str) -> Optional[str]:
    root = cross_root(username)
    has_plan = os.path.isfile(plan_path(username))
    has_index = os.path.isfile(index_cross_path(username))
    theme_dirs = [
        d for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d)) and not d.startswith("_")
    ]
    if not (has_plan or has_index or theme_dirs):
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(root, HISTORY_DIR, ts)
    os.makedirs(dest, exist_ok=True)
    if has_plan:
        shutil.copy2(plan_path(username), os.path.join(dest, PLAN_NAME))
    if has_index:
        shutil.copy2(index_cross_path(username), os.path.join(dest, INDEX_CROSS_NAME))
    for d in theme_dirs:
        src = os.path.join(root, d)
        dst = os.path.join(dest, d)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
    hub_path = store.skill_md_path(username, store.NOTEBOOK_HUB_NAME)
    if os.path.isfile(hub_path):
        shutil.copy2(hub_path, os.path.join(dest, HUB_BAK_NAME))
    print(
        f"[CrossReorg] 已快照入 _history/{ts} themes={len(theme_dirs)} "
        f"plan={has_plan} index={has_index}",
        flush=True,
    )
    return ts


def _restore_from_history(username: str, ts: str) -> bool:
    """
    从 _history/{ts} 恢复线上交叉枝（主题目录 + plan + index_cross + hub bak）。
    用于：已清空旧主题后本轮新主题全部写失败，或清空后流水线异常。
    """
    if not ts:
        return False
    src_root = os.path.join(cross_root(username), HISTORY_DIR, ts)
    if not os.path.isdir(src_root):
        print(f"[CrossReorg] 回滚失败：历史目录不存在 {src_root}", flush=True)
        return False
    try:
        _clear_current_themes(username)
        for name in os.listdir(src_root):
            if name.startswith(".") or name in (PLAN_NAME, INDEX_CROSS_NAME, HUB_BAK_NAME):
                continue
            src = os.path.join(src_root, name)
            if os.path.isdir(src):
                dst = os.path.join(cross_root(username), name)
                if os.path.isdir(dst):
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
        plan_src = os.path.join(src_root, PLAN_NAME)
        if os.path.isfile(plan_src):
            shutil.copy2(plan_src, plan_path(username))
        idx_src = os.path.join(src_root, INDEX_CROSS_NAME)
        if os.path.isfile(idx_src):
            shutil.copy2(idx_src, index_cross_path(username))
        hub_bak = os.path.join(src_root, HUB_BAK_NAME)
        if os.path.isfile(hub_bak):
            hub_path = store.skill_md_path(username, store.NOTEBOOK_HUB_NAME)
            os.makedirs(os.path.dirname(hub_path), exist_ok=True)
            shutil.copy2(hub_bak, hub_path)
        # 按恢复后的主题目录重挂 _index.json
        root = cross_root(username)
        theme_dirs = [
            d for d in os.listdir(root)
            if os.path.isdir(os.path.join(root, d)) and not d.startswith("_")
        ]
        restored_entries = []
        for slug in theme_dirs:
            sk = read_cross_skill(username, slug)
            md = (sk or {}).get("metadata") or {}
            restored_entries.append({
                "name": slug,
                "title": md.get("title") or slug,
                "description": ((sk or {}).get("description") or "")[:400],
                "how_to_use": "",
                "reuse_goal": "",
                "semantic_keywords": md.get("semantic_keywords") or [],
                "related_docs": [],
                "related_existing_skills": [],
                "status": "ok",
                "error": "",
                "path": f"{CROSS_DIR}/{slug}/SKILL.md",
            })
        # 若历史 index 更完整，优先用历史 index，并标注 rolled_back
        idx = load_index_cross(username) or {}
        if isinstance(idx, dict) and idx.get("themes"):
            idx = dict(idx)
            idx["rolled_back_from"] = ts
            idx["rollback_reason"] = "本轮新主题全部失败或中途异常，已自动恢复上一版"
            save_index_cross(username, idx)
            reg = []
            for e in idx.get("themes") or []:
                if not isinstance(e, dict) or not e.get("name"):
                    continue
                ee = dict(e)
                ee["status"] = "ok"
                reg.append(ee)
            _register_cross_skills(username, reg or restored_entries)
        else:
            hub_sk = store.read_skill(username, store.NOTEBOOK_HUB_NAME)
            save_index_cross(username, {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "status": "ok" if restored_entries else "failed",
                "notebook_aim_one_liner": "",
                "hub": {
                    "name": store.NOTEBOOK_HUB_NAME,
                    "description": ((hub_sk or {}).get("description") or "")[:400],
                },
                "n": len(restored_entries),
                "themes": restored_entries,
                "rolled_back_from": ts,
                "rollback_reason": "本轮新主题全部失败或中途异常，已自动恢复上一版",
            })
            _register_cross_skills(username, restored_entries)
        print(f"[CrossReorg] 已从 _history/{ts} 自动回滚", flush=True)
        return True
    except Exception as e:
        traceback.print_exc()
        print(f"[CrossReorg] 自动回滚失败: {e}", flush=True)
        return False


def _clear_current_themes(username: str) -> None:
    root = cross_root(username)
    for d in list(os.listdir(root)):
        if d.startswith("_"):
            continue
        full = os.path.join(root, d)
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)


def _is_retryable_llm_error(exc: BaseException) -> bool:
    """网关超时 / 短暂 5xx / 限流等可退避重试或降级。"""
    try:
        from openai import APIConnectionError, APITimeoutError, APIStatusError
    except ImportError:
        APIConnectionError = APITimeoutError = APIStatusError = ()  # type: ignore
    if isinstance(exc, (TimeoutError, ConnectionError, APIConnectionError, APITimeoutError)):
        return True
    status = getattr(exc, "status_code", None)
    if status is None and isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
    if status in (408, 429, 500, 502, 503, 504, 524):
        return True
    text = str(exc).lower()
    return any(token in text for token in ("524", "timeout", "timed out", "overloaded", "retryable"))


def _is_deepseek_v4_abbr(abbr: str, model_name: str = "") -> bool:
    for name in (abbr or "", model_name or ""):
        n = str(name).strip().lower()
        if n.startswith("deepseek-v4-flash") or n.startswith("deepseek-v4-pro"):
            return True
    return False


def _should_stream_llm(abbr: str, model_name: str = "") -> bool:
    """Claude / GPT 走流式，减轻网关等整包超时；deepseek 等仍非流。"""
    for name in (abbr or "", model_name or ""):
        n = str(name).strip().lower()
        if "claude" in n or n.startswith("gpt") or "gpt-" in n:
            return True
    return False


def _collect_stream_text(stream) -> str:
    parts: List[str] = []
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        content = getattr(delta, "content", None) if delta is not None else None
        if content:
            parts.append(content)
    return "".join(parts).strip()


def _client_for_abbr(abbr: str):
    """按 abbr 解析 OpenAI 兼容客户端；deepseek-v4 关闭 thinking。"""
    from app_chat.scene_models import resolve_openai_cfg_from_abbr

    abbr = str(abbr or "").strip()
    if abbr.startswith("deepseek"):
        cfg = resolve_openai_cfg_from_abbr(
            abbr,
            default_model=abbr if abbr.startswith("deepseek-") else "deepseek-chat",
            default_base="https://api.deepseek.com",
            default_key=os.environ.get("DEEPSEEK_API_KEY") or "",
        )
    else:
        cfg = resolve_openai_cfg_from_abbr(
            abbr,
            default_model=abbr or "claude-opus-4.8",
            default_base=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
            default_key=_public_config.secret('OPENAI_API_KEY'),
        )

    model_name = str(cfg.get("model") or abbr or "deepseek-chat")
    api_key = str(cfg.get("api_key") or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    base_url = str(cfg.get("base_url") or "https://api.deepseek.com").rstrip("/")
    create_extra: Dict[str, Any] = {}

    if _is_deepseek_v4_abbr(abbr, model_name):
        api_key = (os.environ.get("DEEPSEEK_API_KEY") or api_key or _public_config.secret('DEEPSEEK_API_KEY')).strip()
        base_url = "https://api.deepseek.com"
        if not model_name.startswith("deepseek-v4"):
            model_name = abbr
        create_extra["extra_body"] = {"thinking": {"type": "disabled"}}

    if not api_key:
        api_key = _public_config.secret('DEEPSEEK_API_KEY')

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=300.0,
        max_retries=0,
    )
    return client, model_name, create_extra


def _call_slot_chat(slot_key: str, system: str, user: str, *, max_tokens: int = 8192, default: str = "") -> str:
    """
    调用场景槽位模型；不改动输入输出内容。
    降级链：admin 配置模型 → 同模型再试 1 次 → deepseek-v4-pro → deepseek-chat。
    Claude/GPT 用流式拼全文；其余非流。
    """
    from app_chat.scene_models import get_scene_value

    primary = str(get_scene_value(slot_key, default) or default or "").strip() or str(default or "claude-opus-4.8")
    chain: List[str] = [primary, primary, "deepseek-v4-pro", "deepseek-chat"]
    last_exc: Optional[BaseException] = None
    for attempt, abbr in enumerate(chain):
        try:
            client, model_name, create_extra = _client_for_abbr(abbr)
            use_stream = _should_stream_llm(abbr, model_name)
            print(
                f"[cross_reorganize] LLM call slot={slot_key} step={attempt + 1}/{len(chain)} "
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
                "temperature": 0.3,
            }
            kwargs.update(create_extra)
            if use_stream:
                kwargs["stream"] = True
                return _collect_stream_text(client.chat.completions.create(**kwargs))
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            last_exc = exc
            if attempt >= len(chain) - 1 or not _is_retryable_llm_error(exc):
                raise
            delay = 8.0 if attempt == 0 else 12.0
            nxt = chain[attempt + 1]
            print(
                f"[cross_reorganize] LLM 失败 step={attempt + 1}/{len(chain)} "
                f"abbr={abbr} → next={nxt} wait={delay:.0f}s: {exc}",
                flush=True,
            )
            time.sleep(delay)
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
        raise ValueError("规划结果不是合法 JSON 对象")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("规划 JSON 根须为对象")
    return data


def _collect_skill_inventory(username: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回 (文档/包等底座 Skill 清单, 上轮交叉主题 Skill 清单含正文要点)。"""
    idx = store.reconcile_index(username)
    base_items: List[Dict[str, Any]] = []
    cross_items: List[Dict[str, Any]] = []
    for name, meta in (idx.get("skills") or {}).items():
        if name == store.NOTEBOOK_HUB_NAME:
            continue
        source = meta.get("source")
        if source == "cross_reorganize":
            sk = read_cross_skill(username, name) or store.read_skill(username, name)
            md = (sk or {}).get("metadata") or {}
            body = ((sk or {}).get("body") or "")[:2500]
            cross_items.append({
                "name": name,
                "title": meta.get("title") or md.get("title") or name,
                "description": ((sk or {}).get("description") or "")[:800],
                "semantic_keywords": md.get("semantic_keywords"),
                "source": "cross_reorganize",
                "body_excerpt": body,
            })
            continue
        sk = store.read_skill(username, name)
        md = (sk or {}).get("metadata") or {}
        base_items.append({
            "name": name,
            "description": ((sk or {}).get("description") or "")[:500],
            "semantic_keywords": md.get("semantic_keywords"),
            "source": source,
            "source_doc": meta.get("source_doc") or md.get("source_doc") or "",
            "pack": bool(meta.get("pack_zip")),
            "title": meta.get("title") or md.get("title") or name,
        })
    return base_items, cross_items


def _collect_doc_list(username: str, scene_name: str) -> Tuple[List[Dict[str, Any]], bool]:
    from app_chat.cross_document_suggestion import check_if_base_document
    from zym.models import UserNotebook

    root = store.notebook_root(username)
    skip = store._SKIP_ROOT_NAMES
    docs = []
    four = {}
    try:
        real = username.split("_")[0] if "_" in username else username
        book = username[len(real) + 1:] if "_" in username else ""
        nb = None
        if book:
            nb = UserNotebook.objects.filter(username=real, bookName=book).first()
        if not nb:
            nb = UserNotebook.objects.filter(username=real).first()
        if nb and getattr(nb, "documentFourColorDMT", None):
            four = json.loads(nb.documentFourColorDMT) if isinstance(nb.documentFourColorDMT, str) else (nb.documentFourColorDMT or {})
    except Exception:
        four = {}

    has_base = False
    if os.path.isdir(root):
        for fn in sorted(os.listdir(root)):
            if fn.startswith(".") or fn in skip:
                continue
            full = os.path.join(root, fn)
            if not os.path.isfile(full):
                continue
            is_base = bool(scene_name and check_if_base_document(scene_name, fn))
            if is_base:
                has_base = True
            info = four.get(fn) or four.get(os.path.splitext(fn)[0]) or {}
            docs.append({
                "filename": fn,
                "main_four_color": info.get("main_four_color") or info.get("four_color") or "",
                "secondary_four_color": info.get("secondary_four_color") or "",
                "is_scene_base": is_base,
            })
    return docs, has_base


def _plan_system() -> str:
    return """你是 NKCN 本子交叉梳理规划助手。根据已有文档 Skill、文档清单，以及（若有）上轮交叉梳理 1+n 主题 Skill，规划本子目标下的 n 个可复用交叉主题 Skill。
只输出唯一 JSON 对象，不要 Markdown 围栏，不要前言后语。

硬约束：
- n 建议在 3～8；按可复用能力/本子目标分支分主题，不要按文件名各写一份摘要。
- 每主题 semantic_keywords 建议 5～15 个；既有整体又有具体细节，具象化、不可发虚，尽可能全面完整涵盖相关文档内容，实体概念覆盖尽量齐全；有依据、不堆砌空词。
- description 必须含 Use when / NOT for。
- 不要用「骨架/延展」对立来限制抽词。
- hub_touch_hints 为对 notebook-hub 的条目级微调建议（只写「补哪几句/加哪一小节」），禁止推倒重写、禁止要求改写全文。

【文档覆盖（重要·验收硬点）】
- 输入【文档清单】里的每一份文档，都应在至少一个主题的 related_docs 中出现。
- 覆盖要尽量全面、完整：主线材料可出现在多个主题；辅材至少挂到最相关的 1～2 个主题，并在该主题的 keywords / description / how_to_use 中能体现其内容贡献（不是空挂文件名）。
- related_existing_skills 同理：与主题交叉相关的已有文档 Skill、包成员 Skill 尽量点名，避免只列少数几个。
- 若某文档确与本子目标几乎无关，可在 notebook_aim_one_liner 或该主题 description 的 NOT for 中简短说明，但仍优先尝试合理挂载而非默默漏掉。

【稳定迭代（重要）】
- 若输入中带有「上轮交叉 1+n 主题 / Skill」，须以其为底座做合理增改：可保留成熟主题并深化、合并重叠主题、拆分过粗主题、新增必要主题、按新文档/新目标微调关键词与 how_to_use（注意：这些都不是必须的，都是要视情况而定）；避免无谓另起炉灶导致主题结构来回振荡。
- 视情况灵活变通：上轮明显过时、重复或与本子目标冲突时，可果断改写或替换个别主题，但整体宜迭代更新而非推倒重来。
- 主题 name（slug）在可延续时尽量保持稳定，便于历史对照；确需更名时在 title/description 中体现承接关系。

JSON schema:
{
  "notebook_aim_one_liner": "...",
  "n": 4,
  "themes": [{
    "name": "theme-slug-英文小写连字符",
    "title": "中文短标题",
    "description": "… Use when … NOT for …",
    "semantic_keywords": [{"term":"…","gloss":"…","coverage":"整体|细节|二者"}],
    "how_to_use": "…",
    "reuse_goal": "…",
    "related_existing_skills": ["…"],
    "related_docs": ["…"]
  }],
  "hub_touch_hints": ["…"]
}
"""


def _run_plan(username: str, scene_name: str, job_id: str = "") -> Dict[str, Any]:
    from app_chat.scene_context_helper import get_scene_info_from_username, get_scene_summary

    if job_id:
        _set_job(job_id, phase="plan", msg="规划交叉主题中…")
    _, _, _, notebook_desc = get_scene_info_from_username(username)
    scene_summary = ""
    try:
        scene_summary = get_scene_summary(scene_name) if scene_name else ""
    except Exception:
        scene_summary = ""

    inventory, prev_cross = _collect_skill_inventory(username)
    docs, has_base = _collect_doc_list(username, scene_name)
    color_legend = (
        "四色简要：红=行业专业知识；蓝=可照做的步骤与清单；紫=思维模型与判断原则；绿=大白话、通俗易懂的解释。"
    )
    doc_lines = []
    for d in docs:
        role = ""
        if has_base:
            role = "角色=场景基础文档" if d["is_scene_base"] else "角色=本子增量"
        doc_lines.append(
            f"- {d['filename']} 主色={d['main_four_color'] or '无'} 辅色={d['secondary_four_color'] or '无'} {role}"
        )

    prev_plan = None
    prev_index = load_index_cross(username)
    try:
        if os.path.isfile(plan_path(username)):
            with open(plan_path(username), "r", encoding="utf-8") as f:
                prev_plan = json.load(f)
    except Exception:
        prev_plan = None

    user = (
        f"【本子描述】\n{notebook_desc or '（无）'}\n\n"
        f"【场景要点】\n{scene_summary or scene_name or '（无）'}\n\n"
        f"【{color_legend}】\n\n"
        f"【文档清单】共 {len(docs)} 份——规划时须尽量全面、完整覆盖；"
        f"每一份都应出现在至少一个主题的 related_docs（主线可多主题，辅材至少挂 1～2 个最相关主题，禁止只覆盖主线）。\n"
        + ("\n".join(doc_lines) if doc_lines else "（无文档）") + "\n\n"
        f"【已有文档/包 Skill 清单（底座）】\n{json.dumps(inventory, ensure_ascii=False)}\n\n"
        f"【上轮交叉 1+n 主题 Skill（若有；请在此底座上稳定迭代，勿无谓推倒重来）】\n"
        + (json.dumps(prev_cross, ensure_ascii=False) if prev_cross else "（无上轮交叉主题）")
        + "\n\n"
        f"【上轮 _plan / _index_cross 摘要（若有）】\n"
        + json.dumps(
            {
                "prev_plan_aim": (prev_plan or {}).get("notebook_aim_one_liner"),
                "prev_plan_themes": [
                    {
                        "name": t.get("name"),
                        "title": t.get("title"),
                        "description": (t.get("description") or "")[:200],
                    }
                    for t in ((prev_plan or {}).get("themes") or [])
                    if isinstance(t, dict)
                ],
                "prev_index_status": (prev_index or {}).get("status"),
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    raw = _call_slot_chat(
        "cross_reorganize_plan",
        _plan_system(),
        user,
        max_tokens=8192,
        default="claude-opus-4.8",
    )
    try:
        plan = _extract_json_obj(raw)
    except Exception:
        raw2 = _call_slot_chat(
            "cross_reorganize_plan",
            _plan_system() + "\n上次输出无法解析，请严格只输出 JSON 对象。",
            user,
            max_tokens=8192,
            default="claude-opus-4.8",
        )
        plan = _extract_json_obj(raw2)

    themes = plan.get("themes") if isinstance(plan.get("themes"), list) else []
    themes = [t for t in themes if isinstance(t, dict) and str(t.get("name") or "").strip()]
    if not themes:
        raise ValueError("规划结果 themes 为空")
    # 规范 slug，并避开与文档/包/notebook 等同名冲突（交叉枝可用 cross_reorganize 覆盖）
    idx_skills = (store.load_index(username).get("skills") or {})
    used: set = set()
    for t in themes:
        slug = str(t.get("name") or "").strip().lower()
        slug = re.sub(r"[^a-z0-9-]+", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-") or "theme"
        slug = slug[:64]
        base = slug
        n = 0
        while True:
            cand = base if n == 0 else f"{base[: max(1, 64 - len(f'-xr{n}'))]}-xr{n}"[:64]
            meta = idx_skills.get(cand) or {}
            src = str(meta.get("source") or "")
            conflict = bool(meta) and src not in ("", "cross_reorganize")
            if cand not in used and not conflict:
                if cand != base:
                    print(
                        f"[CrossReorg] 规划 slug 冲突改名 {base} → {cand} "
                        f"(已有 source={src or '?'})",
                        flush=True,
                    )
                slug = cand
                break
            n += 1
            if n > 30:
                slug = f"xr-theme-{len(used)+1}"[:64]
                print(f"[CrossReorg] 规划 slug 穷尽，使用 {slug}", flush=True)
                break
        t["name"] = slug
        used.add(slug)
    plan["themes"] = themes
    plan["n"] = len(themes)
    print(
        f"[CrossReorg] 规划规范化完成 n={plan['n']} slugs={[t['name'] for t in themes]}",
        flush=True,
    )
    return plan


CROSS_THEME_SYSTEM = f"""你是 NKCN 交叉主题 Skill 撰写助手。根据规划主题与相关已有材料，写出一份可路由、可复用的主题 SKILL.md。
{QUALITY_PROMPT}

不要再摘要一遍文档原文；要做交叉梳理后的主题能力。
语义关键词须全面完整（整体+细节，具象不发虚，实体概念覆盖齐全），与文档→Skill 口径一致。

必须严格按以下结构输出（先 YAML，再正文）：
---
name: <slug原样保留>
description: >-
  <做什么。Use when …。NOT for …。>
metadata:
  title: "<中文标题>"
  source: cross_reorganize
  cross_plan_name: "<slug>"
  semantic_keywords: []
  standards: ["Agent Skills Spec", "NKCN"]
  version: "1.0"
---

# <短标题>

## 核心主张
...

## 何时用 / 何时不用
...

## 怎么做（工作流）
...

## 关键锚点
...

## 约束与输出期望
...

## 自检（用前过一遍）
...
"""


def _load_related_materials(username: str, theme: Dict[str, Any]) -> str:
    chunks: List[str] = []
    chunks.append("【本主题规划】\n" + json.dumps(theme, ensure_ascii=False, indent=2))

    for name in theme.get("related_existing_skills") or []:
        name = str(name or "").strip()
        if not name:
            continue
        sk = store.read_skill(username, name)
        if sk and sk.get("raw"):
            chunks.append(f"【已有 Skill: {name}】\n{sk['raw']}")

    for doc in theme.get("related_docs") or []:
        doc = str(doc or "").strip()
        if not doc:
            continue
        base, ext = os.path.splitext(doc)
        ext = (ext or "").lstrip(".").lower() or "pdf"
        # PreSummary
        pre = os.path.join(store.notebook_root(username), "pre_summary", f"{base}_Presummary_{ext}.md")
        if os.path.isfile(pre):
            with open(pre, "r", encoding="utf-8", errors="ignore") as f:
                chunks.append(f"【PreSummary: {doc}】\n{f.read()}")
        # DocStructure
        ds = store.doc_structure_path(username, doc)
        if os.path.isfile(ds):
            with open(ds, "r", encoding="utf-8", errors="ignore") as f:
                chunks.append(f"【DocStructure: {doc}】\n{f.read()}")
        # 文档 Skill
        idx = store.load_index(username)
        for sname, meta in (idx.get("skills") or {}).items():
            if meta.get("source_doc") == doc or meta.get("title") == doc:
                sk = store.read_skill(username, sname)
                if sk and sk.get("raw"):
                    chunks.append(f"【文档 Skill: {sname} ← {doc}】\n{sk['raw']}")
                break

    joined = "\n\n".join(chunks)
    return truncate_like_presummary(joined)


def _compose_theme_entry(theme: Dict[str, Any], slug: str, fm: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    # 优先保留规划侧 term+gloss；写 Skill 常会压成纯字符串
    kws = theme.get("semantic_keywords") or meta.get("semantic_keywords") or []
    return {
        "name": slug,
        "title": meta.get("title") or theme.get("title") or slug,
        "description": fm.get("description") or theme.get("description") or "",
        "how_to_use": theme.get("how_to_use") or "",
        "reuse_goal": theme.get("reuse_goal") or "",
        "semantic_keywords": kws,
        "related_docs": theme.get("related_docs") or [],
        "related_existing_skills": theme.get("related_existing_skills") or [],
        "status": "ok",
        "error": "",
        "path": f"{CROSS_DIR}/{slug}/SKILL.md",
    }


def _generate_theme_md(username: str, theme: Dict[str, Any], user_material: str) -> Tuple[Dict[str, Any], str]:
    """调用写 Skill 模型并解析 frontmatter；失败抛异常供外层重试。"""
    slug = str(theme.get("name") or "").strip()
    raw = _call_slot_chat(
        "cross_reorganize_write",
        CROSS_THEME_SYSTEM,
        user_material,
        max_tokens=4096,
        default="deepseek-chat",
    )
    md = _extract_skill_md(raw)
    fm, body = store.parse_skill_md(md)
    if not fm:
        raise ValueError("未能解析 SKILL.md frontmatter")
    fm["name"] = slug
    meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    meta["source"] = "cross_reorganize"
    meta["cross_plan_name"] = slug
    meta["title"] = theme.get("title") or meta.get("title") or slug
    if not meta.get("semantic_keywords"):
        kws = theme.get("semantic_keywords") or []
        if kws and isinstance(kws[0], dict):
            meta["semantic_keywords"] = [
                {"term": k.get("term"), "gloss": k.get("gloss"), "coverage": k.get("coverage")}
                for k in kws if k.get("term")
            ]
        else:
            meta["semantic_keywords"] = kws
    else:
        # 模型若写成纯字符串列表，用规划侧 term+gloss 覆盖，保证索引/卡片可读内涵
        plan_kws = theme.get("semantic_keywords") or []
        if plan_kws and isinstance(plan_kws[0], dict):
            written = meta.get("semantic_keywords")
            if isinstance(written, list) and written and not isinstance(written[0], dict):
                meta["semantic_keywords"] = [
                    {"term": k.get("term"), "gloss": k.get("gloss"), "coverage": k.get("coverage")}
                    for k in plan_kws if k.get("term")
                ]
    if not fm.get("description"):
        fm["description"] = theme.get("description") or f"{theme.get('title')}. Use when 相关主题。NOT for 无关闲聊。"
    fm["metadata"] = meta
    err = store.validate_frontmatter_minimal(fm)
    if err:
        fm["description"] = (fm.get("description") or "交叉主题 Skill。")[:1024]
    return fm, body or ("# " + str(theme.get("title") or slug))


def _write_one_theme(username: str, theme: Dict[str, Any]) -> Tuple[str, bool, str, Dict[str, Any]]:
    slug = str(theme.get("name") or "").strip()
    try:
        user = _load_related_materials(username, theme)
        last_err: Optional[Exception] = None
        fm = None
        body = ""
        # 方案：单路失败按上策重试 1 次（含 API 失败与解析失败）
        for attempt in range(2):
            try:
                material = user
                if attempt == 1:
                    material = truncate_like_presummary(
                        user[: max(8000, presummary_max_content_chars() // 2)]
                    )
                fm, body = _generate_theme_md(username, theme, material)
                last_err = None
                break
            except Exception as e:
                last_err = e
                print(f"[CrossReorg] 写主题 {slug} 第{attempt + 1}次失败: {e}", flush=True)
        if last_err or not fm:
            raise last_err or ValueError("写主题失败")

        meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
        os.makedirs(theme_skill_dir(username, slug), exist_ok=True)
        content = store.dump_skill_md(fm, body)
        path = theme_skill_md(username, slug)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        entry = _compose_theme_entry(theme, slug, fm, meta)
        print(f"[CrossReorg] 写主题成功 slug={slug}", flush=True)
        return slug, True, "", entry
    except Exception as e:
        traceback.print_exc()
        err = str(e)[:240]
        entry = {
            "name": slug,
            "title": theme.get("title") or slug,
            "description": theme.get("description") or "",
            "how_to_use": theme.get("how_to_use") or "",
            "reuse_goal": theme.get("reuse_goal") or "",
            "semantic_keywords": theme.get("semantic_keywords") or [],
            "related_docs": theme.get("related_docs") or [],
            "related_existing_skills": theme.get("related_existing_skills") or [],
            "status": "failed",
            "error": err,
            "path": f"{CROSS_DIR}/{slug}/SKILL.md",
        }
        print(f"[CrossReorg] 写主题最终失败 slug={slug}: {err}", flush=True)
        return slug, False, err, entry


def _read_cross_skill_raw(username: str, slug: str) -> Optional[str]:
    path = theme_skill_md(username, slug)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_cross_skill(username: str, slug: str) -> Optional[Dict[str, Any]]:
    raw = _read_cross_skill_raw(username, slug)
    if raw is None:
        # 兼容：若误写到平铺 skills/{slug}
        return store.read_skill(username, slug)
    fm, body = store.parse_skill_md(raw)
    return {
        "name": slug,
        "path": theme_skill_md(username, slug),
        "frontmatter": fm,
        "body": body,
        "raw": raw,
        "description": str(fm.get("description") or ""),
        "metadata": fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {},
    }


HUB_TOUCH_SYSTEM = f"""你是 notebook-hub「微调」助手——不是重写助手。任务是保留原有总入口定位与已有路由信息的前提下，在旧文上做最小必要增补。
{QUALITY_PROMPT}

核心原则（必须遵守）：
- **微调 = 保留旧文主体不动**，只在指定位置增补少量句子/一段小节；输出长度应与旧文接近（相对变化宜远小于一半）。
- 禁止整篇重写、禁止换结构大纲、禁止用新文覆盖旧文再「看起来像改过」。
- 禁止删除或改写原有文档 Skill / 包 / 路由条目信息；旧有列表、链接、说明须原样保留。
- description：可以最多追加 1～3 句「交叉主题怎么选」；勿重写整段 description，勿空洞口号，总长 ≤1024 字符。
- 正文：最多小幅度增补一小节「交叉主题 Skill」索引（条目级列出新主题 name/title）；其它章节保持原文。
- 若旧 hub 已有交叉主题索引，只更新该小节内容，不要另起炉灶重排全文。
- 输出完整 SKILL.md（YAML+正文），name 必须为 notebook-hub；YAML 其它字段能保留则保留。
"""


def _refine_hub(username: str, plan: Dict[str, Any], theme_entries: List[Dict[str, Any]], job_id: str = "") -> None:
    if job_id:
        _set_job(job_id, phase="hub", msg="微调 notebook-hub…")
    old = store.read_skill(username, store.NOTEBOOK_HUB_NAME)
    old_raw = (old or {}).get("raw") or ""
    old_len = len(old_raw)
    hints = plan.get("hub_touch_hints") or []
    ok_themes = [t for t in theme_entries if t.get("status") == "ok"]
    user = (
        "【任务】对下方旧 notebook-hub 做「微调精修」，不是重写。\n"
        "要求：\n"
        "1) 保留旧文绝大部分段落与路由列表；\n"
        "2) 仅按 hub_touch_hints 做条目级小改；\n"
        "3) 可在正文末尾或合适位置**增补一小节**「交叉主题 Skill」索引（列出新主题）；\n"
        "4) description 只允许少量追加，禁止整段重写；\n"
        "5) 输出全文长度应与旧文接近；若你发现自己在重写，请停下来只做补丁式修改。\n\n"
        "【旧 notebook-hub 全文】\n"
        + (old_raw or "（尚无 hub，请写一个简洁总入口并纳入交叉主题）")
        + "\n\n【微调要点 hub_touch_hints（条目级，勿据此推倒全文）】\n"
        + json.dumps(hints, ensure_ascii=False)
        + "\n\n【新交叉主题清单（供索引小节引用）】\n"
        + json.dumps(
            [{"name": t["name"], "title": t["title"], "description": (t.get("description") or "")[:200]} for t in ok_themes],
            ensure_ascii=False,
        )
        + "\n\n请在旧文基础上微调精修后输出完整 SKILL.md。"
    )
    raw = _call_slot_chat(
        "cross_reorganize_write",
        HUB_TOUCH_SYSTEM,
        user,
        max_tokens=3072,
        default="deepseek-chat",
    )
    md = _extract_skill_md(raw)
    fm, body = store.parse_skill_md(md)
    if not fm:
        print("[CrossReorg] hub 解析失败，保留旧版", flush=True)
        return
    fm["name"] = store.NOTEBOOK_HUB_NAME
    new_content = store.dump_skill_md(fm, body)
    # 护栏：增删过大则保留旧版
    if old_len > 200:
        ratio = abs(len(new_content) - old_len) / float(old_len)
        if ratio > 0.55:
            print(f"[CrossReorg] hub 变化过大({ratio:.0%})，保留旧版", flush=True)
            return
        # 简单检查：旧文若干关键片段应仍在
        keep_hits = 0
        for line in old_raw.splitlines():
            s = line.strip()
            if len(s) > 20 and s.startswith("-"):
                if s[:40] in new_content:
                    keep_hits += 1
                if keep_hits >= 3:
                    break
        if keep_hits == 0 and old_raw.count("name=") + old_raw.count("##") > 6:
            # 旧 hub 有实质内容却几乎无保留
            print("[CrossReorg] hub 疑似推倒重写，保留旧版", flush=True)
            return
    store.write_skill(username, store.NOTEBOOK_HUB_NAME, fm, body)
    idx = store.load_index(username)
    idx["skills"][store.NOTEBOOK_HUB_NAME] = {
        "source": "notebook",
        "source_doc": "",
        "pack_zip": "",
        "enabled": True,
        "title": "本子 Skill 总入口",
    }
    idx["notebook_hub"] = store.NOTEBOOK_HUB_NAME
    store.save_index(username, idx)


def _register_cross_skills(username: str, theme_entries: List[Dict[str, Any]]) -> List[str]:
    """注册成功主题到 _index.json；返回实际注册的 slug 列表。冲突则跳过。"""
    idx = store.load_index(username)
    members: List[str] = []
    # 清掉旧 cross_reorganize 索引项
    for name in list((idx.get("skills") or {}).keys()):
        meta = idx["skills"].get(name) or {}
        if meta.get("source") == "cross_reorganize":
            del idx["skills"][name]
    for t in theme_entries:
        if t.get("status") != "ok":
            continue
        slug = t["name"]
        existing = (idx.get("skills") or {}).get(slug) or {}
        existing_source = str(existing.get("source") or "")
        # 禁止覆盖文档/包/notebook 等同名 Skill
        if existing_source and existing_source not in ("cross_reorganize",):
            print(
                f"[CrossReorg] 跳过注册主题 slug={slug}：与已有 Skill source={existing_source} 同名冲突",
                flush=True,
            )
            continue
        members.append(slug)
        idx["skills"][slug] = {
            "source": "cross_reorganize",
            "source_doc": "",
            "pack_zip": "",
            "enabled": True,
            "title": t.get("title") or slug,
            "rel_dir": f"{CROSS_DIR}/{slug}",
        }
    packs = idx.setdefault("packs", {})
    packs[CROSS_DIR] = {
        "hub": store.NOTEBOOK_HUB_NAME,
        "members": members,
        "enabled": {m: True for m in members},
        "kind": "cross_reorganize",
    }
    store.save_index(username, idx)
    print(f"[CrossReorg] 已注册交叉主题 {len(members)} 个: {members}", flush=True)
    return members


def run_cross_reorganize_skills(
    username: str,
    *,
    scene_name: str = "",
    job_id: str = "",
) -> Tuple[bool, Optional[str]]:
    if not username:
        return False, "缺少 username"
    with _user_lock(username):
        history_ts: Optional[str] = None
        cleared = False
        try:
            history_ts = _snapshot_history(username)
            print(
                f"[CrossReorg] 开始 username={username} history_ts={history_ts or '(首次无快照)'}",
                flush=True,
            )
            plan = _run_plan(username, scene_name, job_id=job_id)
            print(
                f"[CrossReorg] 规划完成 n={plan.get('n')} aim={(plan.get('notebook_aim_one_liner') or '')[:80]}",
                flush=True,
            )
            with open(plan_path(username), "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)

            # 写进行中索引，供前端显示「生成中」
            hub_sk = store.read_skill(username, store.NOTEBOOK_HUB_NAME)
            running_index = {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "status": "running",
                "notebook_aim_one_liner": plan.get("notebook_aim_one_liner") or "",
                "hub": {
                    "name": store.NOTEBOOK_HUB_NAME,
                    "description": ((hub_sk or {}).get("description") or "")[:300],
                },
                "n": plan.get("n") or len(plan.get("themes") or []),
                "themes": [
                    {
                        "name": t.get("name"),
                        "title": t.get("title"),
                        "description": t.get("description"),
                        "status": "running",
                        "path": f"{CROSS_DIR}/{t.get('name')}/SKILL.md",
                    }
                    for t in plan.get("themes") or []
                ],
            }
            save_index_cross(username, running_index)
            print(
                f"[CrossReorg] 已写 running 索引，开始清空旧主题并撰写 n={len(plan.get('themes') or [])}",
                flush=True,
            )

            _clear_current_themes(username)
            cleared = True
            if job_id:
                _set_job(job_id, phase="write", msg="并发撰写主题 Skill…")

            themes = plan.get("themes") or []
            entries: List[Dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=min(4, max(1, len(themes)))) as ex:
                futs = {ex.submit(_write_one_theme, username, t): t for t in themes}
                for fut in as_completed(futs):
                    _slug, _ok, _err, entry = fut.result()
                    entries.append(entry)
            # 按规划顺序排序
            order = {str(t.get("name")): i for i, t in enumerate(themes)}
            entries.sort(key=lambda e: order.get(e.get("name"), 999))

            ok_n = sum(1 for e in entries if e.get("status") == "ok")
            fail_n = len(entries) - ok_n
            print(
                f"[CrossReorg] 撰写结束 ok={ok_n} fail={fail_n} cleared={cleared}",
                flush=True,
            )

            # 仅当「已清空且本轮 0 个成功」才自动回滚；partial 保留新结果
            if ok_n == 0 and history_ts:
                restored = _restore_from_history(username, history_ts)
                msg = (
                    "全部主题生成失败，已自动恢复上一版交叉 Skill"
                    if restored
                    else "全部主题生成失败，且自动回滚失败（请从 _history 手工恢复）"
                )
                if job_id:
                    _set_job(job_id, phase="done", msg=msg, status="failed")
                print(f"[CrossReorg] ❌ {msg} username={username}", flush=True)
                return False, msg

            registered = set(_register_cross_skills(username, entries))
            # 注册被跳过的「写成功」主题：改标 failed，避免索引/问答不一致
            for e in entries:
                if e.get("status") == "ok" and e.get("name") not in registered:
                    e["status"] = "failed"
                    e["error"] = "与已有 Skill 同名冲突，未注册到索引"
                    print(
                        f"[CrossReorg] 主题 {e.get('name')} 写盘成功但未注册 → failed",
                        flush=True,
                    )
            ok_n = sum(1 for e in entries if e.get("status") == "ok")
            fail_n = len(entries) - ok_n
            if ok_n == 0 and history_ts:
                restored = _restore_from_history(username, history_ts)
                msg = (
                    "全部主题因冲突未能注册，已自动恢复上一版交叉 Skill"
                    if restored
                    else "全部主题未能注册，且自动回滚失败（请从 _history 手工恢复）"
                )
                if job_id:
                    _set_job(job_id, phase="done", msg=msg, status="failed")
                print(f"[CrossReorg] ❌ {msg} username={username}", flush=True)
                return False, msg

            try:
                _refine_hub(username, plan, entries, job_id=job_id)
            except Exception:
                traceback.print_exc()
                print("[CrossReorg] hub 微调失败（不影响 n 份与交叉卡）", flush=True)

            hub_sk = store.read_skill(username, store.NOTEBOOK_HUB_NAME)
            status = "ok" if fail_n == 0 and ok_n else ("partial" if ok_n else "failed")
            index_cross = {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "status": status,
                "notebook_aim_one_liner": plan.get("notebook_aim_one_liner") or "",
                "hub": {
                    "name": store.NOTEBOOK_HUB_NAME,
                    "description": ((hub_sk or {}).get("description") or "")[:400],
                },
                "n": len(entries),
                "themes": entries,
            }
            save_index_cross(username, index_cross)
            done_msg = (
                "完成"
                if status == "ok"
                else (f"部分完成（成功 {ok_n}/{len(entries)}）" if status == "partial" else "失败")
            )
            if job_id:
                _set_job(job_id, phase="done", msg=done_msg, status=status if status != "partial" else "ok")
            print(
                f"[CrossReorg] ✅ 完成 username={username} status={status} ok={ok_n} fail={fail_n}",
                flush=True,
            )
            return status != "failed", None if status != "failed" else "全部主题生成失败"
        except Exception as e:
            traceback.print_exc()
            # 已清空旧主题后异常：有历史则自动回滚，避免线上空枝
            rolled = False
            if cleared and history_ts:
                try:
                    rolled = _restore_from_history(username, history_ts)
                except Exception:
                    traceback.print_exc()
            try:
                err_payload = {
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "status": "failed",
                    "notebook_aim_one_liner": "",
                    "hub": {"name": store.NOTEBOOK_HUB_NAME, "description": ""},
                    "n": 0,
                    "themes": [],
                    "error": str(e)[:300],
                }
                if rolled:
                    idx = load_index_cross(username) or {}
                    if isinstance(idx, dict):
                        idx["last_run_error"] = str(e)[:300]
                        idx["rolled_back_from"] = history_ts
                        idx["rollback_reason"] = "本轮中途异常，已自动恢复上一版"
                        save_index_cross(username, idx)
                    else:
                        save_index_cross(username, err_payload)
                elif not cleared:
                    # 尚未清空主题（如规划失败）：绝不能用空 failed 覆盖已有成功 1+n 索引
                    idx = load_index_cross(username) or {}
                    st = str((idx or {}).get("status") or "")
                    if st == "running" and history_ts:
                        # 已写入 running 索引但未清主题 → 从 history 恢复索引
                        rolled = _restore_from_history(username, history_ts)
                        idx2 = load_index_cross(username) or {}
                        if isinstance(idx2, dict):
                            idx2["last_run_error"] = str(e)[:300]
                            idx2["rollback_reason"] = "本轮失败（未清空主题），已恢复上一版索引"
                            save_index_cross(username, idx2)
                        print(
                            f"[CrossReorg] 未清空阶段失败，已恢复上一版索引 rolled={rolled}",
                            flush=True,
                        )
                    elif idx.get("themes") and st in ("ok", "partial"):
                        idx = dict(idx)
                        idx["last_run_error"] = str(e)[:300]
                        save_index_cross(username, idx)
                        print(
                            f"[CrossReorg] 规划/早失败，保留已有 1+n 索引 status={st}",
                            flush=True,
                        )
                    else:
                        # 本子原先无成功 1+n
                        save_index_cross(username, err_payload)
                else:
                    # 已清空但回滚未成功 / 无历史
                    save_index_cross(username, err_payload)
            except Exception:
                pass
            msg = str(e)[:300]
            if rolled:
                msg = f"{msg}（已自动恢复上一版交叉 Skill）"
            print(
                f"[CrossReorg] ❌ 异常 username={username} cleared={cleared} "
                f"rolled={rolled} err={msg}",
                flush=True,
            )
            return False, msg
