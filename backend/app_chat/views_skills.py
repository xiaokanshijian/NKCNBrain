# -*- coding: utf-8 -*-
"""Skill API：list/get/save、zip 导入、启用禁用、冲突预检。"""
from __future__ import annotations

import json
import os
import traceback

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_chat import skills_store as store
from app_chat import skill_generate as gen


def _parse_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


@csrf_exempt
def skill_list(request):
    data = _parse_body(request)
    username = data.get("username") or ""
    if not username:
        return JsonResponse({"error_num": 1, "msg": "缺少 username"})
    try:
        from pathlib import Path
        from django.conf import settings
        from app_chat.ci_access import assert_workspace_path
        assert_workspace_path(username, Path(settings.BASE_DIR) / 'received_dir' / 'user_raw_file' / username)
        idx = store.reconcile_index(username)
        items = []
        for name in store.list_skill_dirs(username):
            sk = store.read_skill(username, name)
            meta = (idx.get("skills") or {}).get(name) or {}
            items.append({
                "name": name,
                "title": meta.get("title") or ((sk or {}).get("metadata") or {}).get("title") or name,
                "description": ((sk or {}).get("description") or "")[:300],
                "source": meta.get("source"),
                "source_doc": meta.get("source_doc"),
                "pack_zip": meta.get("pack_zip"),
                "enabled": store.is_skill_enabled(idx, name),
                "orphaned": bool(meta.get("orphaned")),
                "missing": not bool(sk) or bool(meta.get("missing")),
            })
        return JsonResponse({
            "error_num": 0,
            "msg": "success",
            "skills": items,
            "packs": idx.get("packs") or {},
            "notebook_hub": idx.get("notebook_hub") or store.NOTEBOOK_HUB_NAME,
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error_num": 2, "msg": str(e)[:200]})


@csrf_exempt
def skill_get(request):
    data = _parse_body(request)
    username = data.get("username") or ""
    name = data.get("name") or ""
    if not username or not name:
        return JsonResponse({"error_num": 1, "msg": "缺少 username/name"})
    sk = store.read_skill(username, name)
    if not sk:
        return JsonResponse({"error_num": 1, "msg": "Skill 不存在"})
    return JsonResponse({
        "error_num": 0,
        "msg": "success",
        "name": name,
        "raw": sk.get("raw") or "",
        "frontmatter": sk.get("frontmatter") or {},
        "body": sk.get("body") or "",
    })


@csrf_exempt
def skill_save(request):
    data = _parse_body(request)
    username = data.get("username") or ""
    name = data.get("name") or ""
    raw = data.get("raw")
    if not username or not name:
        return JsonResponse({"error_num": 1, "msg": "缺少 username/name"})
    try:
        if raw is not None:
            fm, body = store.parse_skill_md(raw)
            fm["name"] = name
            # preserve source_doc if missing in edit
            idx = store.load_index(username)
            old_meta = (idx.get("skills") or {}).get(name) or {}
            md = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
            if old_meta.get("source_doc") and not md.get("source_doc"):
                md["source_doc"] = old_meta["source_doc"]
                fm["metadata"] = md
            err = store.validate_frontmatter_minimal(fm)
            if err:
                return JsonResponse({"error_num": 1, "msg": err})
            line_err = store.validate_skill_line_limit(store.dump_skill_md(fm, body))
            if line_err:
                return JsonResponse({"error_num": 1, "msg": line_err})
            store.write_skill(username, name, fm, body, backup=True)
        else:
            body = data.get("body") or ""
            fm = data.get("frontmatter") or {"name": name, "description": data.get("description") or name}
            fm["name"] = name
            store.write_skill(username, name, fm, body, backup=True)
        return JsonResponse({"error_num": 0, "msg": "success"})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error_num": 2, "msg": str(e)[:200]})


@csrf_exempt
def skill_set_enabled(request):
    data = _parse_body(request)
    username = data.get("username") or ""
    names = data.get("names") or []
    if isinstance(names, str):
        names = [names]
    enabled = bool(data.get("enabled", True))
    if not username or not names:
        return JsonResponse({"error_num": 1, "msg": "缺少 username/names"})
    store.set_skill_enabled(username, names, enabled)
    return JsonResponse({"error_num": 0, "msg": "success"})


@csrf_exempt
def skill_for_file(request):
    """按文档或 zip 查背后 Skill 列表（右键菜单用）。"""
    data = _parse_body(request)
    username = data.get("username") or ""
    filename = data.get("filename") or ""
    if not username or not filename:
        return JsonResponse({"error_num": 1, "msg": "缺少参数"})
    idx = store.reconcile_index(username)
    items = []
    low = filename.lower()
    if low.endswith(".zip"):
        pack = (idx.get("packs") or {}).get(filename) or {}
        hub = pack.get("hub")
        for name in pack.get("members") or []:
            sk = store.read_skill(username, name)
            items.append({
                "name": name,
                "title": ((sk or {}).get("metadata") or {}).get("title") or name,
                "description": ((sk or {}).get("description") or "")[:1024],
                "enabled": store.is_skill_enabled(idx, name),
                "is_hub": name == hub,
            })
    else:
        name = store.find_skill_by_source_doc(username, filename)
        if name:
            sk = store.read_skill(username, name)
            items.append({
                "name": name,
                "title": ((sk or {}).get("metadata") or {}).get("title") or filename,
                "description": ((sk or {}).get("description") or "")[:1024],
                "enabled": store.is_skill_enabled(idx, name),
                "is_hub": False,
            })
    return JsonResponse({"error_num": 0, "msg": "success", "skills": items})


@csrf_exempt
def import_skill_zip_api(request):
    data = _parse_body(request)
    username = data.get("username") or ""
    zip_name = data.get("zip_name") or data.get("filename") or ""
    policy = data.get("conflict_policy") or "ask"
    rename_map = data.get("rename_map") or {}
    if not username or not zip_name:
        return JsonResponse({"error_num": 1, "msg": "缺少 username/zip_name"})
    zip_path = os.path.join(store.notebook_root(username), zip_name)
    if not os.path.isfile(zip_path):
        return JsonResponse({"error_num": 1, "msg": "zip 文件不存在，请先上传"})
    if policy == "dry_run" or policy == "ask":
        insp = store.inspect_skill_zip(zip_path)
        if not insp.get("ok"):
            return JsonResponse({"error_num": 1, "msg": insp.get("error") or "校验失败"})
        existing = set(store.list_skill_dirs(username))
        conflicts = [n for n in insp.get("skill_names") or [] if n in existing]
        if conflicts and policy == "ask":
            return JsonResponse({
                "error_num": 0,
                "msg": "need_conflict_resolution",
                "need_conflict_resolution": True,
                "conflicts": conflicts,
                "skill_names": insp.get("skill_names") or [],
            })
        if policy == "dry_run":
            return JsonResponse({"error_num": 0, "msg": "ok", "skill_names": insp.get("skill_names") or [], "conflicts": conflicts})

    result = store.import_skill_zip(
        username, zip_path, zip_name,
        conflict_policy=policy if policy != "ask" else "overwrite",
        rename_map=rename_map,
    )
    if not result.get("ok"):
        if result.get("need_conflict_resolution"):
            return JsonResponse({
                "error_num": 0,
                "msg": "need_conflict_resolution",
                **result,
            })
        return JsonResponse({"error_num": 1, "msg": result.get("error") or "导入失败"})
    # 标记 zip 就绪（重启后靠 card_getAllUserFiles 对 .zip 恒为 split=1；内存态一并补齐）
    try:
        from llm_langchain import global_var as _gv
        _gv.add_split_file(username, zip_name)
    except Exception:
        pass
    # refresh notebook hub
    real = data.get("realName") or (username.split("_")[0] if "_" in username else username)
    try:
        gen.update_notebook_hub(real, username)
    except Exception:
        traceback.print_exc()
    return JsonResponse({"error_num": 0, "msg": "success", **{k: v for k, v in result.items() if k != "ok"}})


@csrf_exempt
def skill_status(request):
    data = _parse_body(request)
    username = data.get("username") or ""
    real = data.get("realName") or ""
    book = data.get("bookName") or ""
    if not real or not book:
        # parse from username
        if username and "_" in username and real:
            book = username[len(real) + 1:]
        elif username and "_" in username:
            parts = username.split("_", 1)
            real, book = parts[0], parts[1]
    try:
        from zym.models import UserNotebook
        nb = UserNotebook.objects.get(username=real, bookName=book)
        raw = getattr(nb, "documentSkillStatus", "") or ""
        status = json.loads(raw) if raw else {}
        return JsonResponse({"error_num": 0, "msg": "success", "documentSkillStatus": status})
    except Exception as e:
        return JsonResponse({"error_num": 0, "msg": "success", "documentSkillStatus": {}, "note": str(e)[:80]})


@csrf_exempt
def skill_regenerate(request):
    """失败重试：重新后台生成文档 Skill。"""
    data = _parse_body(request)
    username = data.get("username") or ""
    filename = data.get("filename") or data.get("docs_name") or ""
    real = data.get("realName") or ""
    if not username or not filename:
        return JsonResponse({"error_num": 1, "msg": "缺少 username/filename"})
    if not (filename.lower().endswith(".pdf") or filename.lower().endswith(".txt")):
        return JsonResponse({"error_num": 1, "msg": "仅支持 PDF/TXT"})
    if not real:
        real = username.split("_")[0] if "_" in username else username
    try:
        gen.spawn_document_skill_async(real, username, filename)
        return JsonResponse({"error_num": 0, "msg": "started"})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error_num": 2, "msg": str(e)[:200]})
