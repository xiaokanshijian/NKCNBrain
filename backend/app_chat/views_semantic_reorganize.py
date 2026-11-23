# encoding=utf-8
"""语义关键词重新/迭代梳理 API。"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_chat.semantic_keyword_service import (
    apply_top_alternative_replace,
    confirm_semantic_pending,
    get_job_status,
    rollback_semantic_reorganize,
    save_semantic_intent_preference,
    start_semantic_reorganize,
    suggest_semantic_panel_options,
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
    force_v2 = bool(body.get('force_v2') or body.get('confirm_force_v2'))
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'username required'})
    incremental = mode in ('incremental', 'iterate', '迭代')
    result = start_semantic_reorganize(
        username,
        scene_name or None,
        incremental=incremental,
        force_v2=force_v2,
    )
    status = get_job_status(username, scene_name or None)
    payload = {
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'mode': result.get('mode'),
        'pipeline': result.get('pipeline') or '',
        'status': status,
    }
    if result.get('source_incomplete') or result.get('need_force_v2'):
        payload['source_incomplete'] = True
        # 兼容旧字段名；前端已不再据此改走 v2
        payload['need_force_v2'] = False
        payload['readiness'] = result.get('readiness') or {}
    if result.get('readiness') is not None and 'readiness' not in payload:
        payload['readiness'] = result.get('readiness')
    return JsonResponse(payload)


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


@csrf_exempt
def semantic_intent_preference_api(request):
    """保存用户改选（Top/核心问题/刻度等），写入意图记忆，下次跟随。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or '').strip()
    scene_name = (body.get('scene_name') or '').strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'username required'})
    patch = body.get('patch') if isinstance(body.get('patch'), dict) else {
        k: body[k]
        for k in (
            'preferred_top',
            'preferred_core_issue',
            'preferred_sub_issues',
            'preferred_scale_definitions',
            'locked_attr_words',
            'confirmations',
            'notes',
            'custom_options',
        )
        if k in body
    }
    result = save_semantic_intent_preference(username, scene_name or None, patch=patch)
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'intent': result.get('intent') or {},
    })


@csrf_exempt
def semantic_panel_suggest_api(request):
    """为子问题增改、刻度说明修改生成可点选说法。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only', 'options': []})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or '').strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'username required', 'options': []})
    result = suggest_semantic_panel_options(
        username,
        (body.get('scene_name') or '').strip() or None,
        kind=str(body.get('kind') or ''),
        current=str(body.get('current') or ''),
        scale_key=str(body.get('scale_key') or ''),
        item_key=str(body.get('item_key') or ''),
        item_name=str(body.get('item_name') or ''),
    )
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'options': result.get('options') or [],
    })


@csrf_exempt
def semantic_top_alternative_replace_api(request):
    """Top1/3/5/10 备选：近义替换该档中的一个词，并同步属性/层次等。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or '').strip()
    scene_name = (body.get('scene_name') or '').strip()
    tier = (body.get('tier') or body.get('key') or '').strip()
    alt_word = (body.get('alt_word') or body.get('word') or body.get('alternative') or '').strip()
    replace_word = (
        body.get('replace_word')
        or body.get('old_word')
        or body.get('target_word')
        or ''
    )
    replace_word = str(replace_word).strip()
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'username required'})
    result = apply_top_alternative_replace(
        username,
        scene_name or None,
        tier=tier,
        alt_word=alt_word,
        replace_word=replace_word,
    )
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'tier': result.get('tier') or tier,
        'old': result.get('old') or '',
        'new': result.get('new') or alt_word,
        'top_list': result.get('top_list') or [],
        'book_top_keywords': result.get('book_top_keywords') or {},
        'keyword_map': result.get('keyword_map') or {},
        'hierarchy_links': result.get('hierarchy_links') or [],
        'keyword_levels': result.get('keyword_levels') or {},
        'quadrants': result.get('quadrants') or {},
        'book_keywords': result.get('book_keywords') or [],
    })


@csrf_exempt
def semantic_confirm_pending_api(request):
    """确认存疑/冲突节点选项（含自由输入第五选项），写入记忆与属性/象限。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': 'POST only'})
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        body = {}
    username = (body.get('username') or '').strip()
    scene_name = (body.get('scene_name') or '').strip()
    word = (body.get('word') or body.get('keyword') or '').strip()
    choice = (body.get('choice') or body.get('option') or '').strip()
    custom_text = (body.get('custom_text') or body.get('custom') or '').strip()
    preview = body.get('preview_applied') if isinstance(body.get('preview_applied'), dict) else None
    if not username:
        return JsonResponse({'error_num': 1, 'msg': 'username required'})
    if not word:
        return JsonResponse({'error_num': 1, 'msg': 'word required'})
    result = confirm_semantic_pending(
        username,
        scene_name or None,
        word=word,
        choice=choice,
        custom_text=custom_text,
        preview_applied=preview,
    )
    return JsonResponse({
        'error_num': 0 if result.get('ok') else 1,
        'msg': result.get('msg', ''),
        'applied': result.get('applied') or {},
        'quadrant': result.get('quadrant') or {},
        'keyword': result.get('keyword') or {},
    })
