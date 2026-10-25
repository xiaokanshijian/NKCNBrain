# -*- coding: utf-8 -*-
"""知识冲突挖掘 HTTP 接口。"""
from __future__ import annotations

import json
import traceback

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_chat import knowledge_conflict_mine as kc


def _parse(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


@csrf_exempt
def knowledge_conflict_start(request):
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "只支持POST"})
    try:
        data = _parse(request)
        username = data.get("username") or ""
        scene_name = data.get("sceneName") or data.get("scene_name") or ""
        if not username:
            return JsonResponse({"error_num": 1, "msg": "缺少 username"})
        job_id = kc.start_knowledge_conflict_job(username, scene_name=scene_name)
        print(f"[KnowledgeConflict] API start username={username} scene={scene_name} job_id={job_id}", flush=True)
        return JsonResponse({"error_num": 0, "msg": "success", "job_id": job_id})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error_num": 1, "msg": str(e)[:300]})


@csrf_exempt
def knowledge_conflict_status(request):
    data = _parse(request) if request.method == "POST" else {}
    job_id = data.get("job_id") or request.GET.get("job_id") or ""
    username = data.get("username") or request.GET.get("username") or ""
    if job_id:
        job = kc.get_job(job_id)
        if not job:
            return JsonResponse({"error_num": 1, "msg": "任务不存在或已过期"})
        result = kc.load_conflicts(job.get("username") or username)
        return JsonResponse({
            "error_num": 0,
            "msg": "success",
            "job": job,
            "conflicts": result,
        })
    if username:
        result = kc.load_conflicts(username)
        return JsonResponse({
            "error_num": 0,
            "msg": "success",
            "conflicts": result,
            "exists": bool(result),
        })
    return JsonResponse({"error_num": 1, "msg": "缺少 job_id 或 username"})


@csrf_exempt
def knowledge_conflict_get(request):
    data = _parse(request) if request.method == "POST" else {}
    username = data.get("username") or request.GET.get("username") or ""
    if not username:
        return JsonResponse({"error_num": 1, "msg": "缺少 username"})
    result = kc.load_conflicts(username)
    return JsonResponse({
        "error_num": 0,
        "msg": "success",
        "conflicts": result,
        "exists": bool(result),
        "path_hint": f"skills/{kc.CONFLICT_DIR}/{kc.RESULT_NAME}",
    })


@csrf_exempt
def knowledge_conflict_feedback(request):
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "只支持POST"})
    try:
        data = _parse(request)
        username = data.get("username") or ""
        item_id = data.get("id") or data.get("item_id") or ""
        if not username or not item_id:
            return JsonResponse({"error_num": 1, "msg": "缺少 username/id"})
        user_status = data.get("user_status") or data.get("status") or ""
        note = data.get("user_note")
        if "user_note" not in data and "note" in data:
            note = data.get("note")
        item = kc.update_item_feedback(
            username,
            item_id,
            user_status=str(user_status or ""),
            user_note=None if note is None else str(note),
        )
        return JsonResponse({"error_num": 0, "msg": "success", "item": item})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error_num": 1, "msg": str(e)[:300]})
