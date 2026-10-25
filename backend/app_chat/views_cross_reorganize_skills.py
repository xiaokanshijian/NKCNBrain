# -*- coding: utf-8 -*-
"""交叉梳理 1+n Skill HTTP 接口。"""
from __future__ import annotations

import json
import traceback

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_chat import cross_reorganize_skills as xr
from app_chat import skills_store as store


def _parse(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


@csrf_exempt
def cross_reorganize_skills_start(request):
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "只支持POST"})
    try:
        data = _parse(request)
        username = data.get("username") or ""
        scene_name = data.get("sceneName") or data.get("scene_name") or ""
        if not username:
            return JsonResponse({"error_num": 1, "msg": "缺少 username"})
        job_id = xr.start_cross_reorganize_job(username, scene_name=scene_name)
        print(f"[CrossReorg] API start username={username} scene={scene_name} job_id={job_id}", flush=True)
        return JsonResponse({"error_num": 0, "msg": "success", "job_id": job_id})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error_num": 1, "msg": str(e)[:300]})


@csrf_exempt
def cross_reorganize_skills_status(request):
    if request.method == "GET":
        job_id = request.GET.get("job_id") or ""
        username = request.GET.get("username") or ""
    else:
        data = _parse(request)
        job_id = data.get("job_id") or ""
        username = data.get("username") or ""
    if job_id:
        job = xr.get_job(job_id)
        if not job:
            return JsonResponse({"error_num": 1, "msg": "任务不存在或已过期"})
        idx = xr.load_index_cross(job.get("username") or username) or {}
        return JsonResponse({
            "error_num": 0,
            "msg": "success",
            "job": job,
            "index_cross": idx,
        })
    if username:
        idx = xr.load_index_cross(username) or {}
        return JsonResponse({"error_num": 0, "msg": "success", "index_cross": idx})
    return JsonResponse({"error_num": 1, "msg": "缺少 job_id 或 username"})


@csrf_exempt
def cross_reorganize_index(request):
    """卡片 UI 快读 _index_cross.json。"""
    data = _parse(request) if request.method == "POST" else {}
    username = data.get("username") or request.GET.get("username") or ""
    if not username:
        return JsonResponse({"error_num": 1, "msg": "缺少 username"})
    idx = xr.load_index_cross(username)
    if not idx:
        return JsonResponse({
            "error_num": 0,
            "msg": "success",
            "index_cross": None,
            "exists": False,
        })
    return JsonResponse({
        "error_num": 0,
        "msg": "success",
        "index_cross": idx,
        "exists": True,
    })


@csrf_exempt
def cross_reorganize_skill_get(request):
    """读取交叉枝或 notebook-hub 的 SKILL.md。"""
    data = _parse(request) if request.method == "POST" else {}
    username = data.get("username") or request.GET.get("username") or ""
    name = data.get("name") or request.GET.get("name") or ""
    if not username or not name:
        return JsonResponse({"error_num": 1, "msg": "缺少 username/name"})
    if name == store.NOTEBOOK_HUB_NAME:
        sk = store.read_skill(username, name)
    else:
        sk = xr.read_cross_skill(username, name)
    if not sk:
        return JsonResponse({"error_num": 1, "msg": "Skill 不存在"})
    return JsonResponse({
        "error_num": 0,
        "msg": "success",
        "name": name,
        "raw": sk.get("raw") or "",
        "description": sk.get("description") or "",
        "metadata": sk.get("metadata") or {},
        "frontmatter": sk.get("frontmatter") or {},
    })
