# -*- coding: utf-8 -*-
"""NK2026 小组 Gxx.md 孪生：HTTP 接口。"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_chat.automation_nk2026 import NK2026_SCENE_NAME, is_nk2026_ladder_scene
from app_chat.group_twin_gxx import (
    get_progress,
    list_twin_files,
    read_twin_file,
    start_job,
)
from app_chat.scene_context_helper import get_scene_info_from_username


@csrf_exempt
def group_twin_gxx_start(request):
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "只支持POST"})
    try:
        data = json.loads(request.body)
        username = data.get("username") or ""
        scene_name = data.get("sceneName") or ""
        if not username:
            return JsonResponse({"error_num": 1, "msg": "缺少 username"})
        if not is_nk2026_ladder_scene(scene_name):
            return JsonResponse(
                {
                    "error_num": 1,
                    "msg": f"仅「{NK2026_SCENE_NAME}」场景可生成小组孪生",
                }
            )
        _, _, _, notebook_description = get_scene_info_from_username(username)
        job_id = start_job(username, scene_name, notebook_description or "")
        if not job_id:
            return JsonResponse({"error_num": 1, "msg": "无法启动任务"})
        return JsonResponse({"error_num": 0, "msg": "success", "job_id": job_id})
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})


def group_twin_gxx_progress(request, task_id):
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "只支持GET"})
    p = get_progress(task_id)
    if not p:
        return JsonResponse({"error_num": 1, "msg": "任务不存在或已过期"})
    return JsonResponse({"error_num": 0, "msg": "success", **p})


def group_twin_gxx_list(request):
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "只支持GET"})
    username = request.GET.get("username") or ""
    if not username:
        return JsonResponse({"error_num": 1, "msg": "缺少 username"})
    files = list_twin_files(username)
    return JsonResponse({"error_num": 0, "msg": "success", "files": files})


def group_twin_gxx_content(request):
    if request.method != "GET":
        return JsonResponse({"error_num": 1, "msg": "只支持GET"})
    username = request.GET.get("username") or ""
    name = request.GET.get("name") or ""
    if not username or not name:
        return JsonResponse({"error_num": 1, "msg": "缺少 username 或 name"})
    content = read_twin_file(username, name)
    if content is None:
        return JsonResponse({"error_num": 1, "msg": "文件不存在或非法文件名"})
    return JsonResponse({"error_num": 0, "msg": "success", "content": content, "name": name})
