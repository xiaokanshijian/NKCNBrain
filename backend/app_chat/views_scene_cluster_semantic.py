# encoding=utf-8
"""场景 / 任务簇大本体语义梳理 API。"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_chat.scene_cluster_semantic_service import (
    get_job_status,
    get_result_payload,
    rename_scene_cluster_keyword,
    rollback_scene_cluster_semantic,
    start_scene_cluster_semantic,
    update_scene_cluster_keyword_attrs,
    update_scene_cluster_link_strength,
)


def _body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return {}


def _viewer_from_request(request, body=None):
    body = body or {}
    if request.method == 'GET':
        return (request.GET.get('viewer') or request.GET.get('username') or '').strip()
    return (body.get('viewer') or body.get('username') or '').strip()


@csrf_exempt
def scene_cluster_semantic_start(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    body = _body(request)
    scope_type = (body.get('scope_type') or body.get('scope') or 'scene').strip()
    scope_id = str(body.get('scope_id') or body.get('sid') or body.get('cluster_id') or '').strip()
    viewer = _viewer_from_request(request, body)
    if not scope_id or not viewer:
        return JsonResponse({'error_num': 1, 'msg': 'scope_id / viewer required'})
    mode = (body.get('mode') or 'full').strip()
    result = start_scene_cluster_semantic(
        scope_type=scope_type,
        scope_id=scope_id,
        viewer=viewer,
        mode=mode,
    )
    status = get_job_status(scope_type, scope_id, viewer) if result.get('ok') else {}
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'mode': result.get('mode'),
        'status': status,
    })


@csrf_exempt
def scene_cluster_semantic_status(request):
    scope_type = (request.GET.get('scope_type') or request.GET.get('scope') or 'scene').strip()
    scope_id = str(request.GET.get('scope_id') or request.GET.get('sid') or request.GET.get('cluster_id') or '').strip()
    viewer = _viewer_from_request(request)
    if not scope_id or not viewer:
        return JsonResponse({'error_num': 1, 'msg': 'scope_id / viewer required'})
    status = get_job_status(scope_type, scope_id, viewer)
    return JsonResponse({'error_num': 0, 'status': status})


@csrf_exempt
def scene_cluster_semantic_rollback(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    body = _body(request)
    scope_type = (body.get('scope_type') or body.get('scope') or 'scene').strip()
    scope_id = str(body.get('scope_id') or body.get('sid') or body.get('cluster_id') or '').strip()
    viewer = _viewer_from_request(request, body)
    if not scope_id or not viewer:
        return JsonResponse({'error_num': 1, 'msg': 'scope_id / viewer required'})
    result = rollback_scene_cluster_semantic(
        scope_type=scope_type,
        scope_id=scope_id,
        viewer=viewer,
    )
    status = get_job_status(scope_type, scope_id, viewer)
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'status': status,
    })


@csrf_exempt
def scene_cluster_semantic_result(request):
    scope_type = (request.GET.get('scope_type') or request.GET.get('scope') or 'scene').strip()
    scope_id = str(request.GET.get('scope_id') or request.GET.get('sid') or request.GET.get('cluster_id') or '').strip()
    viewer = _viewer_from_request(request)
    if not scope_id or not viewer:
        return JsonResponse({'error_num': 1, 'msg': 'scope_id / viewer required'})
    payload = get_result_payload(scope_type, scope_id, viewer)
    return JsonResponse({'error_num': 0, **payload})


@csrf_exempt
def scene_cluster_update_link_strength(request):
    """大本体层次连边强度手动调整（场景 / 任务簇）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    body = _body(request)
    scope_type = (body.get('scope_type') or body.get('scope') or 'scene').strip()
    scope_id = str(body.get('scope_id') or body.get('sid') or body.get('cluster_id') or '').strip()
    viewer = _viewer_from_request(request, body)
    parent = (body.get('parent') or body.get('source') or '').strip()
    child = (body.get('child') or body.get('target') or '').strip()
    strength = (body.get('strength') or body.get('link_strength') or '').strip()
    if not scope_id or not viewer:
        return JsonResponse({'error_num': 1, 'msg': 'scope_id / viewer required'})
    if not parent or not child:
        return JsonResponse({'error_num': 1, 'msg': 'parent/child required'})
    result = update_scene_cluster_link_strength(
        scope_type=scope_type,
        scope_id=scope_id,
        viewer=viewer,
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


@csrf_exempt
def scene_cluster_update_keyword_attrs(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    body = _body(request)
    scope_type = (body.get('scope_type') or body.get('scope') or 'scene').strip()
    scope_id = str(body.get('scope_id') or body.get('sid') or body.get('cluster_id') or '').strip()
    viewer = _viewer_from_request(request, body)
    keyword = str(body.get('keyword') or '').strip()
    if not scope_id or not viewer or not keyword:
        return JsonResponse({'error_num': 1, 'msg': 'scope_id / viewer / keyword required'})
    result = update_scene_cluster_keyword_attrs(
        scope_type=scope_type,
        scope_id=scope_id,
        viewer=viewer,
        keyword=keyword,
        four_color_type=str(body.get('four_color_type') or '').strip(),
        dmt_level=str(body.get('dmt_level') or '').strip(),
        knowledge_type=str(body.get('knowledge_type') or '').strip(),
    )
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'keyword': result.get('keyword', keyword),
        'four_color_type': result.get('four_color_type', ''),
        'dmt_level': result.get('dmt_level', ''),
        'knowledge_type': result.get('knowledge_type', ''),
        'keywordFourColorDMT': result.get('keywordFourColorDMT') or {},
    })


@csrf_exempt
def scene_cluster_rename_keyword(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    body = _body(request)
    scope_type = (body.get('scope_type') or body.get('scope') or 'scene').strip()
    scope_id = str(body.get('scope_id') or body.get('sid') or body.get('cluster_id') or '').strip()
    viewer = _viewer_from_request(request, body)
    old_keyword = str(body.get('old_keyword') or '').strip()
    new_keyword = str(body.get('new_keyword') or '').strip()
    if not scope_id or not viewer or not old_keyword or not new_keyword:
        return JsonResponse({'error_num': 1, 'msg': 'scope_id / viewer / old_keyword / new_keyword required'})
    result = rename_scene_cluster_keyword(
        scope_type=scope_type,
        scope_id=scope_id,
        viewer=viewer,
        old_keyword=old_keyword,
        new_keyword=new_keyword,
    )
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'need_reanalyze': bool(result.get('need_reanalyze')),
        'keywords': result.get('keywords') or [],
        'keywordFourColorDMT': result.get('keywordFourColorDMT') or {},
        'hierarchy_links': result.get('hierarchy_links') or [],
    })
