# -*- coding: utf-8 -*-
"""本子 Agent Skill 存储：路径、_index.json、zip 安全导入、读写 SKILL.md。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import yaml

SKILLS_DIR_NAME = "skills"
DOC_STRUCTURE_DIR_NAME = "doc_structure"
INDEX_NAME = "_index.json"
NOTEBOOK_HUB_NAME = "notebook-hub"
MAX_ZIP_BYTES = 80 * 1024 * 1024
MAX_SKILL_MD_CHARS = 120000
MAX_SKILL_LINES = 500

_SKIP_ROOT_NAMES = frozenset({
    "cardImage", "pre_summary", "pre_image_summary", "_twin", "cardCondense",
    "pre_tribal_knowledge", "skills", "_socratic_meta", "continuous_image_dmt",
    DOC_STRUCTURE_DIR_NAME,
})

_INDEX_LOCKS: Dict[str, threading.RLock] = {}
_INDEX_LOCKS_GUARD = threading.Lock()


def _index_lock(username: str) -> threading.RLock:
    with _INDEX_LOCKS_GUARD:
        lock = _INDEX_LOCKS.get(username)
        if lock is None:
            lock = threading.RLock()
            _INDEX_LOCKS[username] = lock
        return lock


def notebook_root(username: str) -> str:
    return os.path.normpath(f"./received_dir/user_raw_file/{username}")


def skills_root(username: str) -> str:
    path = os.path.join(notebook_root(username), SKILLS_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def doc_structure_root(username: str) -> str:
    path = os.path.join(notebook_root(username), DOC_STRUCTURE_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def doc_structure_path(username: str, docs_name: str) -> str:
    base = os.path.splitext(docs_name)[0]
    return os.path.join(doc_structure_root(username), f"{base}_DocStructure.md")


def index_path(username: str) -> str:
    return os.path.join(skills_root(username), INDEX_NAME)


def skill_dir(username: str, name: str, *, rel_dir: str = "") -> str:
    """rel_dir 形如 `_cross_reorganize/{slug}` 时写入交叉枝；默认平铺。"""
    rel = (rel_dir or "").strip().replace("\\", "/").strip("/")
    if rel:
        # 允许 rel 已含 name 末段
        if rel.endswith("/" + name) or rel == name:
            return os.path.join(skills_root(username), *rel.split("/"))
        return os.path.join(skills_root(username), *rel.split("/"), name)
    return os.path.join(skills_root(username), name)


def skill_md_path(username: str, name: str, *, rel_dir: str = "") -> str:
    return os.path.join(skill_dir(username, name, rel_dir=rel_dir), "SKILL.md")


def _resolve_skill_rel_dir(username: str, name: str) -> str:
    try:
        idx = _load_index_unlocked(username)
        meta = (idx.get("skills") or {}).get(name) or {}
        return str(meta.get("rel_dir") or "").strip()
    except Exception:
        return ""


def empty_index() -> Dict[str, Any]:
    return {"packs": {}, "skills": {}, "notebook_hub": NOTEBOOK_HUB_NAME}


def load_index(username: str) -> Dict[str, Any]:
    with _index_lock(username):
        return _load_index_unlocked(username)


def _load_index_unlocked(username: str) -> Dict[str, Any]:
    path = index_path(username)
    if not os.path.isfile(path):
        idx = empty_index()
        _save_index_unlocked(username, idx)
        return idx
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return empty_index()
        data.setdefault("packs", {})
        data.setdefault("skills", {})
        data.setdefault("notebook_hub", NOTEBOOK_HUB_NAME)
        return data
    except Exception:
        return empty_index()


def save_index(username: str, index: Dict[str, Any]) -> None:
    with _index_lock(username):
        _save_index_unlocked(username, index)


def _save_index_unlocked(username: str, index: Dict[str, Any]) -> None:
    """原子写 _index.json；Windows 下多线程并发时 os.replace 易 WinError 5，故加锁+重试。"""
    path = index_path(username)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = json.dumps(index, ensure_ascii=False, indent=2)
    last_err: Optional[Exception] = None
    for attempt in range(8):
        tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}.{attempt}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            try:
                os.replace(tmp, path)
            except PermissionError:
                # Windows：目标被短暂占用时，先删再替换 / 直接覆盖写
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                    os.replace(tmp, path)
                except Exception:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(payload)
                    try:
                        if os.path.isfile(tmp):
                            os.remove(tmp)
                    except Exception:
                        pass
            return
        except Exception as e:
            last_err = e
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            time.sleep(0.03 * (attempt + 1))
    if last_err:
        raise last_err


def _slugify_pinyin(text: str) -> str:
    text = (text or "").strip()
    base = os.path.splitext(text)[0] if text else "doc"
    try:
        from pypinyin import lazy_pinyin
        parts = lazy_pinyin(base)
        slug = "-".join(parts)
    except Exception:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", base)
    slug = slug.lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if len(slug) > 40:
        slug = slug[:40].rstrip("-")
    return slug or "doc"


def make_document_slug(docs_name: str) -> str:
    """文档 Skill slug：{拼音}-{hash12}。"""
    h = hashlib.md5((docs_name or "").encode("utf-8")).hexdigest()[:12]
    return f"{_slugify_pinyin(docs_name)}-{h}"


def parse_skill_md(text: str) -> Tuple[Dict[str, Any], str]:
    """返回 (frontmatter_dict, body)。"""
    text = text or ""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.DOTALL)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}
    return fm, m.group(2) or ""


def dump_skill_md(frontmatter: Dict[str, Any], body: str) -> str:
    fm = dict(frontmatter or {})
    yaml_str = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False).strip()
    body = (body or "").lstrip("\n")
    return f"---\n{yaml_str}\n---\n\n{body}"


def validate_frontmatter_minimal(fm: Dict[str, Any]) -> Optional[str]:
    name = str(fm.get("name") or "").strip()
    desc = str(fm.get("description") or "").strip()
    if not name or not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", name):
        return "SKILL.md 缺少合法 name（小写字母/数字/连字符）"
    if not desc:
        return "SKILL.md 缺少 description"
    if len(desc) > 1024:
        return "description 超过 1024 字符"
    return None


def count_skill_lines(content: str) -> int:
    if not content:
        return 0
    return content.count("\n") + (0 if content.endswith("\n") else 1)


def validate_skill_line_limit(content: str, max_lines: int = MAX_SKILL_LINES) -> Optional[str]:
    n = count_skill_lines(content or "")
    if n > max_lines:
        return f"SKILL.md 超过 {max_lines} 行（当前 {n} 行）"
    return None


def trim_skill_to_max_lines(frontmatter: Dict[str, Any], body: str, max_lines: int = MAX_SKILL_LINES) -> Tuple[str, bool]:
    """超长时截断正文行，保证全文 ≤ max_lines。返回 (content, truncated)。"""
    content = dump_skill_md(frontmatter, body)
    if count_skill_lines(content) <= max_lines:
        return content, False
    # 先算 frontmatter 占用行数，再截 body
    fm_only = dump_skill_md(frontmatter, "")
    fm_lines = count_skill_lines(fm_only.rstrip("\n") + "\n")
    remain = max(0, max_lines - fm_lines)
    body_lines = (body or "").splitlines()
    truncated_body = "\n".join(body_lines[:remain]).rstrip() + "\n"
    if remain > 0 and not truncated_body.strip().endswith("（已截断至规格上限）"):
        truncated_body = truncated_body.rstrip() + "\n\n（已截断至规格上限）\n"
    return dump_skill_md(frontmatter, truncated_body), True


def read_skill(username: str, name: str) -> Optional[Dict[str, Any]]:
    with _index_lock(username):
        rel = _resolve_skill_rel_dir(username, name)
    path = skill_md_path(username, name, rel_dir=rel)
    if not os.path.isfile(path):
        # 回退平铺
        path = skill_md_path(username, name)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    fm, body = parse_skill_md(raw)
    return {
        "name": name,
        "path": path,
        "frontmatter": fm,
        "body": body,
        "raw": raw,
        "description": str(fm.get("description") or ""),
        "metadata": fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {},
    }


def write_skill(
    username: str,
    name: str,
    frontmatter: Dict[str, Any],
    body: str,
    *,
    backup: bool = False,
    enforce_line_limit: bool = True,
) -> str:
    d = skill_dir(username, name)
    os.makedirs(d, exist_ok=True)
    path = skill_md_path(username, name)
    if backup and os.path.isfile(path):
        shutil.copy2(path, path + ".bak")
    fm = dict(frontmatter or {})
    fm["name"] = name
    if enforce_line_limit:
        content, truncated = trim_skill_to_max_lines(fm, body)
        if truncated:
            print(f"[Skill] 写入时截断至 ≤{MAX_SKILL_LINES} 行: {name}")
    else:
        content = dump_skill_md(fm, body)
    if len(content) > MAX_SKILL_MD_CHARS:
        content = content[:MAX_SKILL_MD_CHARS]
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def list_skill_dirs(username: str) -> List[str]:
    root = skills_root(username)
    names = []
    if not os.path.isdir(root):
        return []
    for fn in os.listdir(root):
        if fn.startswith("."):
            continue
        full = os.path.join(root, fn)
        if fn.startswith("_"):
            # 交叉梳理枝：_cross_reorganize/{slug}/SKILL.md
            if fn == "_cross_reorganize" and os.path.isdir(full):
                for sub in os.listdir(full):
                    if sub.startswith("_") or sub.startswith("."):
                        continue
                    sub_full = os.path.join(full, sub)
                    if os.path.isdir(sub_full) and os.path.isfile(os.path.join(sub_full, "SKILL.md")):
                        names.append(sub)
            continue
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, "SKILL.md")):
            names.append(fn)
    return sorted(set(names))


def reconcile_index(username: str) -> Dict[str, Any]:
    with _index_lock(username):
        idx = _load_index_unlocked(username)
        on_disk = set(list_skill_dirs(username))
        changed = False
        for name in list(idx.get("skills") or {}):
            if name not in on_disk and name != NOTEBOOK_HUB_NAME:
                meta = idx["skills"].get(name) or {}
                if not meta.get("missing"):
                    meta["missing"] = True
                    idx["skills"][name] = meta
                    changed = True
            elif name in on_disk and (idx["skills"].get(name) or {}).get("missing"):
                idx["skills"][name]["missing"] = False
                changed = True
        for name in on_disk:
            if name not in idx["skills"]:
                sk = read_skill(username, name)
                md = (sk or {}).get("metadata") or {}
                idx["skills"][name] = {
                    "source": md.get("source") or ("document" if md.get("source_doc") else "pack"),
                    "source_doc": md.get("source_doc") or "",
                    "pack_zip": md.get("pack_zip") or "",
                    "enabled": True,
                    "title": md.get("title") or name,
                }
                changed = True
        if changed:
            _save_index_unlocked(username, idx)
        return idx


def find_skill_by_source_doc(username: str, docs_name: str) -> Optional[str]:
    idx = load_index(username)
    for name, meta in (idx.get("skills") or {}).items():
        if (meta or {}).get("source_doc") == docs_name:
            if os.path.isfile(skill_md_path(username, name)):
                return name
    # fallback: deterministic slug
    slug = make_document_slug(docs_name)
    if os.path.isfile(skill_md_path(username, slug)):
        return slug
    return None


def set_skill_enabled(username: str, names: List[str], enabled: bool) -> Dict[str, Any]:
    idx = load_index(username)
    for name in names:
        if name in (idx.get("skills") or {}):
            idx["skills"][name]["enabled"] = bool(enabled)
        for pack in (idx.get("packs") or {}).values():
            members = pack.get("members") or []
            hub = pack.get("hub")
            if name not in members and name != hub:
                continue
            en = pack.get("enabled")
            # 兼容整包 bool；切换单个 skill 时升级为 per-member dict
            if isinstance(en, bool):
                en = {m: bool(en) for m in members}
                if hub:
                    en[hub] = bool(pack.get("enabled"))
                pack["enabled"] = en
            elif not isinstance(en, dict):
                en = {}
                pack["enabled"] = en
            en[name] = bool(enabled)
    save_index(username, idx)
    return idx


def is_skill_enabled(index: Dict[str, Any], name: str) -> bool:
    meta = (index.get("skills") or {}).get(name) or {}
    if meta.get("enabled") is False:
        return False
    for pack in (index.get("packs") or {}).values():
        en = pack.get("enabled")
        members = pack.get("members") or []
        hub = pack.get("hub")
        belongs = name in members or name == hub
        if isinstance(en, bool):
            # 交叉梳理等：整包 enabled 布尔开关
            if belongs and en is False:
                return False
            continue
        if isinstance(en, dict):
            if name in en and en[name] is False:
                return False
    return True


def detect_pack_hub(member_names: List[str], skill_metas: Dict[str, Dict[str, Any]]) -> Optional[str]:
    if "271-education" in member_names:
        return "271-education"
    # 课标套装约定：*-kebiao-2022 为 Hub
    for name in member_names:
        if str(name).endswith("-kebiao-2022"):
            return name
    for name in member_names:
        desc = str((skill_metas.get(name) or {}).get("description") or "")
        title = str((skill_metas.get(name) or {}).get("title") or "")
        blob = desc + " " + title
        if (
            "总入口" in blob
            or "Hub" in blob
            or "按场景路由" in blob
            or "先加载本 skill" in blob
            or "技能总入口" in blob
            or "套装的总入口" in blob
        ):
            return name
    return member_names[0] if member_names else None


def _safe_zip_members(zf: zipfile.ZipFile) -> List[zipfile.ZipInfo]:
    out = []
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
            raise ValueError(f"非法路径: {info.filename}")
        if os.path.isabs(info.filename):
            raise ValueError(f"绝对路径不允许: {info.filename}")
        out.append(info)
    return out


def _norm_zip_name(name: str) -> str:
    return str(name or "").replace("\\", "/").lstrip("/")


def _is_junk_zip_path(name: str) -> bool:
    n = _norm_zip_name(name)
    if not n:
        return True
    parts = [p for p in n.split("/") if p]
    if not parts:
        return True
    if parts[0] in ("__MACOSX", ".DS_Store", "Thumbs.db"):
        return True
    if any(p.startswith("._") for p in parts):
        return True
    return False


def _list_skill_md_zip_paths(zf: zipfile.ZipFile) -> List[str]:
    """zip 内所有 SKILL.md 的规范路径（已排除系统垃圾目录）。"""
    out: List[str] = []
    for info in zf.infolist():
        name = _norm_zip_name(info.filename)
        if _is_junk_zip_path(name):
            continue
        if name.endswith("/SKILL.md") or name == "SKILL.md":
            out.append(name)
    return out


def detect_zip_wrapper_prefix(skill_md_paths: List[str]) -> str:
    """识别「整包外套一层目录」的常见打法。

    - 图2/271：根下直接是各 skill 目录 → 返回 ''
    - 图1/课标：根下只有「语文课标2022-skills分发包/」再才是各 skill → 返回该前缀
    - 单 skill 目录在根下（xxx/SKILL.md）→ 不剥前缀
    """
    parents: List[str] = []
    for md in skill_md_paths or []:
        parts = [p for p in _norm_zip_name(md).split("/") if p]
        if not parts or parts[-1] != "SKILL.md":
            continue
        parents.append("/".join(parts[:-1]))  # '' 表示 SKILL.md 在根
    if not parents:
        return ""
    if any(p == "" for p in parents):
        return ""
    tops = {p.split("/")[0] for p in parents}
    if len(tops) != 1:
        return ""
    top = next(iter(tops))
    # 顶层本身就是 skill（271 单目录 / 根下直接 hub）→ 不剥
    if any(p == top for p in parents):
        return ""
    # 全部 skill 都在 top/xxx/SKILL.md → 剥掉外套
    if all(p.startswith(top + "/") for p in parents):
        return top + "/"
    return ""


def _skill_entry_from_md_path(md_path: str) -> str:
    parts = [p for p in _norm_zip_name(md_path).split("/") if p]
    if parts == ["SKILL.md"]:
        return "."
    if len(parts) >= 2 and parts[-1] == "SKILL.md":
        return "/".join(parts[:-1])
    return ""


def _pack_index_store_path(username: str, pack_zip_name: str) -> str:
    root = os.path.join(skills_root(username), "_pack_indexes")
    os.makedirs(root, exist_ok=True)
    safe = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "_", str(pack_zip_name or "pack"))[:96] or "pack"
    return os.path.join(root, safe + ".md")


def _find_pack_index_bytes(
    zf: zipfile.ZipFile,
    *,
    wrapper_prefix: str,
    hub_entry: str,
    hub_name: str,
) -> Tuple[Optional[bytes], str]:
    """在 zip 中定位包 INDEX.md：优先 Hub 旁，其次外套下浅层，再任意 INDEX。"""
    candidates: List[Tuple[int, str]] = []
    hub_entry = (hub_entry or "").rstrip("/")
    for info in zf.infolist():
        fn = _norm_zip_name(info.filename)
        if _is_junk_zip_path(fn):
            continue
        # 仅认 INDEX.md，避免误匹配 xxx_INDEX.md
        if fn != "INDEX.md" and not fn.endswith("/INDEX.md"):
            continue
        # 优先级：Hub 目录内 > 外套下一层 > 其它
        score = 100
        if hub_entry and fn == f"{hub_entry}/INDEX.md":
            score = 0
        elif hub_name and fn.endswith(f"/{hub_name}/INDEX.md"):
            score = 1
        elif wrapper_prefix and fn.startswith(wrapper_prefix):
            rel = fn[len(wrapper_prefix):]
            score = 2 if rel.count("/") <= 1 else 5
        else:
            score = 3 if fn.count("/") <= 1 else 6
        candidates.append((score, fn))
    if not candidates:
        return None, ""
    candidates.sort(key=lambda x: (x[0], x[1]))
    pick = candidates[0][1]
    return zf.read(pick), pick


def inspect_skill_zip(zip_path: str) -> Dict[str, Any]:
    """预检 zip 是否为 Skill 包；不落盘。兼容根下平铺与外套一层目录。"""
    if not os.path.isfile(zip_path):
        return {"ok": False, "error": "zip 文件不存在"}
    if os.path.getsize(zip_path) > MAX_ZIP_BYTES:
        return {"ok": False, "error": f"zip 过大（上限 {MAX_ZIP_BYTES // (1024 * 1024)}MB）"}
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_zip_members(zf)
            md_paths = _list_skill_md_zip_paths(zf)
            if not md_paths:
                return {
                    "ok": False,
                    "error": "当前仅支持 Skill 包结构的 zip（需包含带 SKILL.md 的技能目录），其它内容的 zip 暂不支持。",
                }
            wrapper = detect_zip_wrapper_prefix(md_paths)
            skill_entries = []
            for md in md_paths:
                entry = _skill_entry_from_md_path(md)
                if entry:
                    skill_entries.append(entry)
            # 去重并保持稳定顺序
            skill_entries = list(dict.fromkeys(skill_entries))
            names = []
            logical_folders = []
            for entry in skill_entries:
                md_name = "SKILL.md" if entry == "." else f"{entry}/SKILL.md"
                raw = zf.read(md_name).decode("utf-8", errors="replace")
                fm, _ = parse_skill_md(raw)
                err = validate_frontmatter_minimal(fm)
                if err:
                    return {"ok": False, "error": f"{md_name}: {err}"}
                nm = str(fm.get("name") or "").strip()
                names.append(nm)
                logical = entry.split("/")[-1] if entry != "." else nm
                if wrapper and entry.startswith(wrapper):
                    logical = entry[len(wrapper):].split("/")[0] or logical
                logical_folders.append(logical)
            return {
                "ok": True,
                "skill_names": names,
                "skill_folders": skill_entries,
                "logical_folders": logical_folders,
                "wrapper_prefix": wrapper,
                "conflicts": [],
            }
    except zipfile.BadZipFile:
        return {"ok": False, "error": "无效的 zip 文件"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def import_skill_zip(
    username: str,
    zip_path: str,
    pack_zip_name: str,
    *,
    conflict_policy: str = "overwrite",
    rename_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    conflict_policy: overwrite | skip | rename
    rename_map: old_name -> new_name when policy=rename
    """
    inspect = inspect_skill_zip(zip_path)
    if not inspect.get("ok"):
        return inspect

    rename_map = rename_map or {}
    idx = load_index(username)
    existing = set(list_skill_dirs(username))
    conflicts = [n for n in inspect["skill_names"] if n in existing]
    if conflicts and conflict_policy == "ask":
        return {"ok": False, "need_conflict_resolution": True, "conflicts": conflicts, "skill_names": inspect["skill_names"]}

    imported = []
    skipped = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        _safe_zip_members(zf)
        # group by top-level skill folder
        folder_to_name = {}
        for entry in inspect["skill_folders"]:
            md_name = "SKILL.md" if entry == "." else f"{entry}/SKILL.md"
            raw = zf.read(md_name).decode("utf-8", errors="replace")
            fm, body = parse_skill_md(raw)
            name = str(fm.get("name") or "").strip()
            folder_to_name[entry] = name

        for entry, name in folder_to_name.items():
            if conflict_policy == "rename":
                target_name = str(rename_map.get(name, name) or name).strip()
                if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", target_name):
                    return {"ok": False, "error": f"非法重命名: {name} -> {target_name}"}
                if name in conflicts and name not in rename_map:
                    return {"ok": False, "error": f"冲突项未提供新名称: {name}"}
                if target_name in existing and target_name != name:
                    return {"ok": False, "error": f"目标名已存在: {target_name}（来自 {name}）"}
                if name in existing and target_name == name:
                    return {"ok": False, "error": f"仍与已有 Skill 冲突: {name}"}
            else:
                target_name = rename_map.get(name, name)

            if target_name in existing and conflict_policy == "skip":
                skipped.append(target_name)
                continue
            if target_name in existing and conflict_policy == "overwrite":
                # backup whole dir
                d = skill_dir(username, target_name)
                bak = d + ".bak"
                if os.path.isdir(bak):
                    shutil.rmtree(bak, ignore_errors=True)
                if os.path.isdir(d):
                    shutil.move(d, bak)
            elif target_name in existing and conflict_policy == "rename":
                return {"ok": False, "error": f"目标名冲突: {target_name}"}

            dest = skill_dir(username, target_name)
            os.makedirs(dest, exist_ok=True)
            prefix = "" if entry == "." else entry.rstrip("/") + "/"
            for info in zf.infolist():
                fn = _norm_zip_name(info.filename)
                if _is_junk_zip_path(fn):
                    continue
                if entry == ".":
                    if "/" in fn.rstrip("/"):
                        continue
                    rel = fn
                else:
                    if not fn.startswith(prefix):
                        continue
                    rel = fn[len(prefix):]
                if not rel or rel.endswith("/"):
                    continue
                out_path = os.path.join(dest, rel.replace("/", os.sep))
                out_path = os.path.normpath(out_path)
                if not out_path.startswith(os.path.normpath(dest)):
                    raise ValueError("zip 路径逃逸")
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with zf.open(info) as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)

            # ensure name in frontmatter matches directory
            sk = read_skill(username, target_name)
            if sk:
                fm = dict(sk["frontmatter"] or {})
                fm["name"] = target_name
                md = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
                # do not force-write metadata into pack skills; only index tracks pack
                write_skill(username, target_name, fm, sk["body"])
            imported.append(target_name)
            existing.add(target_name)
            idx["skills"][target_name] = {
                "source": "pack",
                "source_doc": "",
                "pack_zip": pack_zip_name,
                "enabled": True,
                "title": target_name,
            }

    hub_metas = {}
    for n in imported:
        sk = read_skill(username, n) or {}
        hub_metas[n] = {
            "description": sk.get("description") or "",
            "title": ((sk.get("frontmatter") or {}).get("name") or n),
        }
    hub = detect_pack_hub(imported, hub_metas)
    wrapper_prefix = str(inspect.get("wrapper_prefix") or "")

    # 定位 Hub 在 zip 内的目录（用于找 INDEX.md）
    hub_entry = ""
    if hub:
        for entry, name in folder_to_name.items():
            if name == hub or (entry != "." and entry.split("/")[-1] == hub):
                hub_entry = entry
                break

    index_rel = ""
    index_store = ""
    try:
        index_bytes = None
        # 1) 优先已解压到 Hub 目录旁的 INDEX.md（271 / 课标均适用）
        if hub:
            hub_index_disk = os.path.join(skill_dir(username, hub), "INDEX.md")
            if os.path.isfile(hub_index_disk):
                with open(hub_index_disk, "rb") as f:
                    index_bytes = f.read()
                index_rel = f"{hub}/INDEX.md"
        # 2) 再从 zip 按优先级找（兼容外套一层：语文课标…/yuwen-kebiao-2022/INDEX.md）
        if index_bytes is None:
            with zipfile.ZipFile(zip_path, "r") as zf:
                index_bytes, index_rel = _find_pack_index_bytes(
                    zf,
                    wrapper_prefix=wrapper_prefix,
                    hub_entry=hub_entry,
                    hub_name=hub or "",
                )
        if index_bytes:
            text = index_bytes.decode("utf-8", errors="replace")
            index_store = _pack_index_store_path(username, pack_zip_name)
            with open(index_store, "w", encoding="utf-8") as f:
                f.write(text)
            # 兼容旧逻辑：仍写一份最近导入的全局快照
            with open(os.path.join(skills_root(username), "_pack_index.md"), "w", encoding="utf-8") as f:
                f.write(text)
    except Exception:
        pass

    has_glossary = False
    if hub:
        has_glossary = os.path.isfile(os.path.join(skill_dir(username, hub), "GLOSSARY.md"))

    idx["packs"][pack_zip_name] = {
        "hub": hub,
        "members": imported,
        "enabled": {n: True for n in imported},
        "wrapper_prefix": wrapper_prefix,
        "index_file": index_store,
        "index_zip_path": index_rel,
        "has_glossary": has_glossary,
    }

    save_index(username, idx)
    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "hub": hub,
        "pack_zip": pack_zip_name,
        "wrapper_prefix": wrapper_prefix,
        "index_file": index_store,
        "has_glossary": has_glossary,
    }


def candidates_from_checked_files(username: str, file_list: List[str]) -> List[Dict[str, Any]]:
    """由勾选 FileCard 推导候选 Skill（含 role）。

    若本子已成功做过 1+n 交叉梳理：在原有候选之外，按主题
    related_docs / related_existing_skills 与勾选文档的匹配度，最多再并入 4 个交叉主题 Skill。
    未做过 1+n 的本子：行为与原先完全一致。
    """
    idx = reconcile_index(username)
    out: List[Dict[str, Any]] = []
    seen = set()

    def _add(name: str, role: str, *, extra: Optional[Dict[str, Any]] = None):
        if not name or name in seen:
            return
        meta = (idx.get("skills") or {}).get(name) or {}
        if meta.get("orphaned"):
            return
        if not is_skill_enabled(idx, name):
            return
        sk = read_skill(username, name)
        if not sk:
            return
        seen.add(name)
        md = sk.get("metadata") or {}
        item = {
            "name": name,
            "description": sk.get("description") or "",
            "role": role,
            "semantic_keywords": md.get("semantic_keywords") or [],
            "doc_role": md.get("doc_role") or "",
            "main_four_color": md.get("main_four_color") or "",
            "secondary_four_color": md.get("secondary_four_color") or "",
            "dmt_level": md.get("dmt_level") or "",
            "title": md.get("title") or name,
        }
        if extra:
            item.update(extra)
        out.append(item)

    for fn in file_list or []:
        low = fn.lower()
        if low.endswith(".zip"):
            pack = (idx.get("packs") or {}).get(fn) or {}
            members = pack.get("members") or []
            hub = pack.get("hub")
            for m in members:
                role = "pack_hub" if m == hub else "pack_member"
                _add(m, role)
        elif low.endswith(".pdf") or low.endswith(".txt"):
            name = find_skill_by_source_doc(username, fn)
            if name:
                _add(name, "document")

    base_n = len(out)
    _append_cross_theme_candidates(username, file_list or [], seen, _add)
    cross_n = len(out) - base_n
    if cross_n > 0:
        cross_names = [c["name"] for c in out if c.get("role") == "cross_theme"]
        print(
            f"[Skill] 候选扩展(1+n): base={base_n} +cross={cross_n} → {cross_names}",
            flush=True,
        )
    return out


def _append_cross_theme_candidates(
    username: str,
    file_list: List[str],
    seen: set,
    add_fn,
) -> None:
    """有成功 1+n 时：按 related_* 与勾选文档匹配，最多并入 4 个主题 Skill。"""
    try:
        from app_chat.cross_reorganize_skills import load_index_cross
    except Exception:
        return
    try:
        idx_cross = load_index_cross(username)
    except Exception:
        return
    if not isinstance(idx_cross, dict):
        return
    status = str(idx_cross.get("status") or "")
    # 仅成功做过（全成或部分成）才扩展候选；failed/running/空 = 等同未做过
    if status not in ("ok", "partial"):
        return
    themes = [
        t for t in (idx_cross.get("themes") or [])
        if isinstance(t, dict)
        and str(t.get("status") or "") == "ok"
        and str(t.get("name") or "").strip()
    ]
    if not themes:
        print(f"[Skill] 1+n 索引 status={status} 但无成功主题，不扩展候选", flush=True)
        return

    checked_docs: set = set()
    checked_skill_names: set = set()
    for fn in file_list:
        fn = str(fn or "").strip()
        if not fn:
            continue
        low = fn.lower()
        if not (low.endswith(".pdf") or low.endswith(".txt")):
            continue
        checked_docs.add(fn)
        checked_docs.add(os.path.basename(fn))
        doc_skill = find_skill_by_source_doc(username, fn)
        if doc_skill:
            checked_skill_names.add(doc_skill)

    if not checked_docs and not checked_skill_names:
        return

    def _doc_hit(related_docs: Any) -> int:
        n = 0
        for d in related_docs or []:
            d = str(d or "").strip()
            if not d:
                continue
            if d in checked_docs or os.path.basename(d) in checked_docs:
                n += 1
        return n

    def _skill_hit(related_skills: Any) -> int:
        n = 0
        for s in related_skills or []:
            s = str(s or "").strip()
            if s and s in checked_skill_names:
                n += 1
        return n

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for t in themes:
        slug = str(t.get("name") or "").strip()
        if not slug or slug in seen:
            continue
        score = _doc_hit(t.get("related_docs")) + _skill_hit(t.get("related_existing_skills"))
        if score > 0:
            scored.append((score, t))

    if not scored:
        print(
            f"[Skill] 1+n 有 {len(themes)} 个成功主题，但与勾选文档无 related_* 命中 "
            f"(docs={sorted(checked_docs)[:6]} skills={sorted(checked_skill_names)[:6]})",
            flush=True,
        )
        return
    scored.sort(key=lambda x: (-x[0], str(x[1].get("name") or "")))
    picked = scored[:4]
    print(
        f"[Skill] 1+n related 命中 {len(scored)} 个主题，取前 {len(picked)}: "
        + ", ".join(f"{t.get('name')}(score={s})" for s, t in picked),
        flush=True,
    )
    for score, t in picked:
        slug = str(t.get("name") or "").strip()
        add_fn(
            slug,
            "cross_theme",
            extra={
                "cross_match_score": score,
                "cross_title": t.get("title") or slug,
            },
        )


def get_notebook_hub_meta(username: str) -> Optional[Dict[str, Any]]:
    sk = read_skill(username, NOTEBOOK_HUB_NAME)
    if not sk:
        return None
    return {
        "name": NOTEBOOK_HUB_NAME,
        "description": sk.get("description") or "",
        "role": "notebook_hub",
        "raw": sk.get("raw") or "",
        "body": sk.get("body") or "",
        "frontmatter": sk.get("frontmatter") or {},
    }


def pack_short_route_table(username: str, pack_zip: str, max_chars: int = 600) -> str:
    idx = load_index(username)
    pack = (idx.get("packs") or {}).get(pack_zip) or {}
    hub = pack.get("hub")
    lines = []
    if hub:
        sk = read_skill(username, hub)
        if sk:
            desc = (sk.get("description") or "")[:400]
            lines.append(f"Hub `{hub}`: {desc}")
    # INDEX.md 短摘（Hub 旁或包级落盘），与 271 / 课标包一致可读
    index_path = str(pack.get("index_file") or "").strip()
    if not index_path and hub:
        cand = os.path.join(skill_dir(username, hub), "INDEX.md")
        if os.path.isfile(cand):
            index_path = cand
    if index_path and os.path.isfile(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                idx_txt = f.read(800).strip()
            if idx_txt:
                lines.append("INDEX:\n" + idx_txt[:500])
        except Exception:
            pass
    for m in (pack.get("members") or [])[:12]:
        if m == hub:
            continue
        sk = read_skill(username, m)
        if not sk:
            continue
        d = (sk.get("description") or "")[:120]
        lines.append(f"- `{m}`: {d}")
    text = "\n".join(lines)
    return text[:max_chars]


def mark_orphaned_for_doc(username: str, docs_name: str) -> None:
    idx = load_index(username)
    for name, meta in (idx.get("skills") or {}).items():
        if (meta or {}).get("source_doc") == docs_name:
            meta["orphaned"] = True
            meta["source_doc_missing"] = True
    save_index(username, idx)


def mark_orphaned_for_file(username: str, filename: str) -> None:
    """删除 PDF/TXT/zip FileCard 时标记关联 Skill 为 orphaned（不删磁盘）。"""
    if not username or not filename:
        return
    low = filename.lower()
    idx = load_index(username)
    changed = False
    if low.endswith(".zip"):
        pack = (idx.get("packs") or {}).get(filename) or {}
        for m in pack.get("members") or []:
            meta = (idx.get("skills") or {}).setdefault(m, {})
            meta["orphaned"] = True
            meta["pack_zip_missing"] = True
            changed = True
        for name, meta in list((idx.get("skills") or {}).items()):
            if (meta or {}).get("pack_zip") == filename:
                meta["orphaned"] = True
                meta["pack_zip_missing"] = True
                changed = True
    else:
        for name, meta in (idx.get("skills") or {}).items():
            if (meta or {}).get("source_doc") == filename:
                meta["orphaned"] = True
                meta["source_doc_missing"] = True
                changed = True
    if changed:
        save_index(username, idx)
