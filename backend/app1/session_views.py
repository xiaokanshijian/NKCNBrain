from django.db import DatabaseError
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from app1.session_auth import clear_user_session, get_session_user

@never_cache
@require_GET
@ensure_csrf_cookie
def csrf_token(request):
    return JsonResponse({"error_num": 0, "csrfToken": get_token(request)})

@never_cache
@require_GET
def current_session(request):
    try:
        user = get_session_user(request)
    except DatabaseError:
        return JsonResponse({"error_num": 1, "msg": "登录状态暂时无法验证"}, status=503)
    if user is None:
        return JsonResponse({"error_num": 1, "msg": "登录已失效，请重新登录"}, status=401)
    return JsonResponse({
        "error_num": 0, "msg": "success", "name": user.username,
        "coacherName": user.coacher, "level": user.level, "choose": user.choose,
    })

@never_cache
@require_POST
@csrf_protect
def logout_session(request):
    clear_user_session(request)
    return JsonResponse({"error_num": 0, "msg": "success"})
