# -*- coding: utf-8 -*-
"""长短记忆：手动 AutoDream、状态查询。"""
import json
import threading

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def notebook_memory_autodream(request):
    """Admin / 测试：手动触发 AutoDream。POST: username, sceneName(optional)"""
    if request.method != "POST":
        return JsonResponse({"error_num": 1, "msg": "POST only"})
    try:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            data = request.POST.dict() if hasattr(request, "POST") else {}
        username = (data.get("username") or data.get("user_name") or "").strip()
        scene = (data.get("sceneName") or data.get("scene_name") or "").strip()
        if not username:
            return JsonResponse({"error_num": 1, "msg": "username required"})

        from app_chat.notebook_memory import run_autodream, log_notebook_memory

        log_notebook_memory(f"API 手动触发 AutoDream scene={scene!r}", book_key=username)
        result_box = {}

        def _run():
            result_box["r"] = run_autodream(username, scene_name=scene, manual=True)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=300)
        if t.is_alive():
            log_notebook_memory("API AutoDream 超时仍后台继续", book_key=username)
            return JsonResponse({"error_num": 0, "msg": "AutoDream 已在后台继续运行", "async": True})
        r = result_box.get("r") or {}
        log_notebook_memory(f"API AutoDream 返回 ok={r.get('ok')} msg={r.get('msg')}", book_key=username)
        return JsonResponse({"error_num": 0 if r.get("ok") else 1, "msg": "ok" if r.get("ok") else r.get("msg", "fail"), "result": r})
    except Exception as e:
        try:
            from app_chat.notebook_memory import log_notebook_memory
            log_notebook_memory(f"API AutoDream 异常: {e}")
        except Exception:
            pass
        return JsonResponse({"error_num": 1, "msg": str(e)})


@csrf_exempt
def notebook_memory_status(request):
    """GET/POST: username → 文件是否存在、dream meta"""
    try:
        if request.method == "POST":
            try:
                data = json.loads(request.body.decode("utf-8") or "{}")
            except Exception:
                data = {}
        else:
            data = request.GET.dict()
        username = (data.get("username") or "").strip()
        if not username:
            return JsonResponse({"error_num": 1, "msg": "username required"})
        import os
        from app_chat.notebook_memory import book_memory_dir, account_user_path, split_account_book, _read_text, log_notebook_memory

        account, _ = split_account_book(username)
        bd = book_memory_dir(username)
        meta_path = os.path.join(bd, ".dream_meta.json")
        meta = {}
        if os.path.isfile(meta_path):
            try:
                meta = json.loads(_read_text(meta_path) or "{}")
            except Exception:
                meta = {}
        log_notebook_memory(f"API status has_memory={os.path.isfile(os.path.join(bd, 'MEMORY.md'))}", book_key=username)
        return JsonResponse({
            "error_num": 0,
            "book_dir": bd,
            "user_md": account_user_path(account),
            "has_memory": os.path.isfile(os.path.join(bd, "MEMORY.md")),
            "has_rules": os.path.isfile(os.path.join(bd, "规矩.md")),
            "dream_meta": meta,
        })
    except Exception as e:
        return JsonResponse({"error_num": 1, "msg": str(e)})
