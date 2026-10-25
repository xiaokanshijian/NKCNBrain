"""Issue vendor-specific short-lived URLs without exposing the signing secret."""
import base64
import hashlib
import hmac
from email.utils import formatdate
from urllib.parse import urlencode
from django.http import JsonResponse
from django.db import DatabaseError
from app1.session_auth import get_session_user
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from nkcn_public_config import secret

SERVICES = {
    "iat": ("iat-api.xfyun.cn", "/v2/iat"),
    "tts": ("tts-api.xfyun.cn", "/v2/tts"),
}

@never_cache
@require_GET
def voice_session(request):
    # Never trust a username from query parameters as authentication.
    try:
        account = get_session_user(request)
    except DatabaseError:
        return JsonResponse({"error_num": 1, "msg": "登录状态暂时无法验证"}, status=503)
    if account is None and not getattr(getattr(request, "user", None), "is_authenticated", False):
        return JsonResponse({"error_num": 1, "msg": "语音服务需要登录认证"}, status=401)
    service = request.GET.get("service", "")
    if service not in SERVICES:
        return JsonResponse({"error_num": 1, "msg": "不支持的语音服务"}, status=400)
    app_id = secret("XFYUN_APP_ID")
    api_key = secret("XFYUN_API_KEY")
    api_secret = secret("XFYUN_API_SECRET")
    if not all((app_id, api_key, api_secret)):
        return JsonResponse({"error_num": 1, "msg": "服务端尚未配置语音凭据"}, status=503)
    host, path = SERVICES[service]
    date = formatdate(usegmt=True)
    canonical = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature = base64.b64encode(hmac.new(api_secret.encode(), canonical.encode(),
                                        hashlib.sha256).digest()).decode()
    authorization = (f'api_key="{api_key}", algorithm="hmac-sha256", '
                     f'headers="host date request-line", signature="{signature}"')
    params = urlencode({"authorization": base64.b64encode(authorization.encode()).decode(),
                        "date": date, "host": host})
    return JsonResponse({"error_num": 0, "url": f"wss://{host}{path}?{params}", "app_id": app_id})
