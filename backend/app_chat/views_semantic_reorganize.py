# encoding=utf-8
"""语义关键词重新/迭代梳理 API。"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_chat.semantic_keyword_service import (
    get_job_status,
    rollback_semantic_reorganize,
    start_semantic_reorganize,
    update_hierarchy_link_strength,
)


@csrf_exempt
def semantic_reorganize_start(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or request.POST.get('username') or '').strip()
    scene_name = (body.get('scene_name') or request.POST.get('scene_name') or '').strip()
    mode = (body.get('mode') or request.POST.get('mode') or 'full').strip().lower()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'username required'})
    incremental = mode in ('incremental', 'iterate', '迭代')
    result = start_semantic_reorganize(username, scene_name or None, incremental=incremental)
    status = get_job_status(username, scene_name or None)
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'mode': result.get('mode'),
        'status': status,
    })


@csrf_exempt
def semantic_reorganize_status(request):
    username = (request.GET.get('username') or '').strip()
    scene_name = (request.GET.get('scene_name') or '').strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'username required'})
    status = get_job_status(username, scene_name or None)
    return JsonResponse({'error_num': 0, 'status': status})


@csrf_exempt
def semantic_reorganize_rollback(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or request.POST.get('username') or '').strip()
    scene_name = (body.get('scene_name') or request.POST.get('scene_name') or '').strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'username required'})
    result = rollback_semantic_reorganize(username, scene_name or None)
    status = get_job_status(username, scene_name or None)
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'cards_restored': result.get('cards_restored', 0),
        'status': status,
    })


@csrf_exempt
def update_hierarchy_link_strength_api(request):
    """手动调整单条层次连边的关联程度（强/强中/普通）并保存。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or '').strip()
    scene_name = (body.get('scene_name') or '').strip()
    parent = (body.get('parent') or body.get('source') or '').strip()
    child = (body.get('child') or body.get('target') or '').strip()
    strength = (body.get('strength') or body.get('link_strength') or '').strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'username required'})
    if not parent or not child:
        return JsonResponse({'error_num': 1, 'msg': 'parent/child required'})
    result = update_hierarchy_link_strength(
        username,
        scene_name or None,
        parent=parent,
        child=child,
        strength=strength,
    )
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'parent': result.get('parent', parent),
        'child': result.get('child', child),
        'strength': result.get('strength', ''),
        'hierarchy_links': result.get('hierarchy_links') or [],
    })
