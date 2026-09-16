# -*- coding: utf-8 -*-
"""任务簇型视图 API。"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_chat.task_cluster_service import (
    adjust_notebook_cluster,
    create_empty_cluster,
    delete_cluster,
    get_task_cluster_progress,
    get_task_cluster_status,
    load_task_cluster_result,
    start_task_cluster_analyze_async,
    update_cluster_meta,
)


@csrf_exempt
def task_cluster_get(request):
    if request.method not in ('GET', 'POST'):
        return JsonResponse({'error_num': 1, 'msg': 'GET/POST only'})
    try:
        if request.method == 'POST':
            body = json.loads(request.body.decode('utf-8') or '{}')
        else:
            body = {}
    except json.JSONDecodeError:
        body = {}
    username = (
        body.get('username')
        or request.GET.get('username')
        or request.POST.get('username')
        or ''
    ).strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': '缺少 username'})
    result = load_task_cluster_result(username)
    if result:
        result = dict(result)
        result['error_num'] = 0
        result['processed'] = True
        return JsonResponse(result)
    status = get_task_cluster_status(username)
    status['processed'] = False
    status['clusters'] = []
    status['unclustered'] = []
    return JsonResponse(status)


@csrf_exempt
def task_cluster_analyze(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or request.POST.get('username') or '').strip()
    force = str(body.get('force', 'false')).lower() in ('true', '1', 'yes')
    mode = (body.get('mode') or 'full').strip().lower()
    if mode not in ('full', 'incremental'):
        mode = 'full'
    if not username:
        return JsonResponse({'error_num': 1, 'msg': '缺少 username'})
    result = start_task_cluster_analyze_async(username, force=force, mode=mode)
    return JsonResponse(result)


@csrf_exempt
def task_cluster_progress(request):
    if request.method not in ('GET', 'POST'):
        return JsonResponse({'error_num': 1, 'msg': 'GET/POST only'})
    try:
        if request.method == 'POST':
            body = json.loads(request.body.decode('utf-8') or '{}')
        else:
            body = {}
    except json.JSONDecodeError:
        body = {}
    username = (
        body.get('username')
        or request.GET.get('username')
        or request.POST.get('username')
        or ''
    ).strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': '缺少 username'})
    progress = get_task_cluster_progress(username)
    progress['error_num'] = int(progress.get('error_num') or 0)
    return JsonResponse(progress)


@csrf_exempt
def task_cluster_update_meta(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or request.POST.get('username') or '').strip()
    cluster_id = (body.get('cluster_id') or '').strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': '缺少 username'})
    if not cluster_id:
        return JsonResponse({'error_num': 1, 'msg': '缺少 cluster_id'})
    cluster_name = body.get('cluster_name')
    summary = body.get('summary')
    if cluster_name is None and summary is None:
        return JsonResponse({'error_num': 1, 'msg': '缺少 cluster_name 或 summary'})
    result = update_cluster_meta(
        username,
        cluster_id,
        cluster_name=cluster_name,
        summary=summary,
    )
    return JsonResponse(result)


@csrf_exempt
def task_cluster_adjust_notebook(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or request.POST.get('username') or '').strip()
    notebook_key = (body.get('notebook_key') or '').strip()
    action = (body.get('action') or '').strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': '缺少 username'})
    if not notebook_key:
        return JsonResponse({'error_num': 1, 'msg': '缺少 notebook_key'})
    if not action:
        return JsonResponse({'error_num': 1, 'msg': '缺少 action'})
    result = adjust_notebook_cluster(
        username,
        notebook_key,
        action,
        target_cluster_id=body.get('target_cluster_id'),
        new_cluster_name=body.get('new_cluster_name'),
        new_cluster_summary=body.get('new_cluster_summary'),
    )
    return JsonResponse(result)


@csrf_exempt
def task_cluster_create(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or request.POST.get('username') or '').strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': '缺少 username'})
    result = create_empty_cluster(
        username,
        cluster_name=body.get('cluster_name') or '',
        summary=body.get('summary') or '',
    )
    return JsonResponse(result)


@csrf_exempt
def task_cluster_delete(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or request.POST.get('username') or '').strip()
    cluster_id = (body.get('cluster_id') or '').strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': '缺少 username'})
    if not cluster_id:
        return JsonResponse({'error_num': 1, 'msg': '缺少 cluster_id'})
    result = delete_cluster(username, cluster_id)
    return JsonResponse(result)
