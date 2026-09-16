"""
响应中断相关的API视图
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
from .interrupt_manager import interrupt_manager


@csrf_exempt
@require_POST
def interrupt_response(request):
    """中断指定的流式响应"""
    try:
        data = json.loads(request.body)
        username = data.get("username")
        model_id = data.get("model_id")
        session_id = data.get("session_id")
        force = data.get("force", True)  # 默认使用强制中断
        interrupt_all = data.get("interrupt_all", False)  # 是否中断所有窗口
        
        if not username:
            return JsonResponse({
                "error_num": 1,
                "msg": "缺少必要参数: username"
            }, status=400)
        
        # 如果要求中断所有窗口
        if interrupt_all:
            count = interrupt_manager.interrupt_all_user_sessions(username, force=force)
            return JsonResponse({
                "error_num": 0,
                "msg": f"成功中断用户所有响应会话 ({count} 个)",
                "interrupted_count": count
            })
        
        # 如果没有提供具体的session_id，尝试中断该用户该模型的所有活跃会话
        if not session_id:
            if not model_id:
                return JsonResponse({
                    "error_num": 1,
                    "msg": "缺少必要参数: model_id 或 session_id"
                }, status=400)
            
            active_sessions = interrupt_manager.get_active_sessions()
            interrupted_count = 0
            for active_session in active_sessions:
                if active_session.startswith(f"{username}_{model_id}"):
                    if interrupt_manager.interrupt_session(active_session, force=force):
                        interrupted_count += 1
            
            return JsonResponse({
                "error_num": 0,
                "msg": f"成功中断 {interrupted_count} 个响应会话",
                "interrupted_count": interrupted_count
            })
        else:
            # 中断指定的会话
            success = interrupt_manager.interrupt_session(session_id, force=force)
            if success:
                return JsonResponse({
                    "error_num": 0,
                    "msg": f"成功中断响应会话: {session_id}",
                    "force": force
                })
            else:
                return JsonResponse({
                    "error_num": 1,
                    "msg": f"未找到会话或会话已结束: {session_id}"
                })
                
    except json.JSONDecodeError:
        return JsonResponse({
            "error_num": 1,
            "msg": "无效的JSON数据"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "error_num": 1,
            "msg": f"中断响应时发生错误: {str(e)}"
        }, status=500)


@csrf_exempt
def get_active_sessions(request):
    """获取当前活跃的响应会话列表"""
    try:
        active_sessions = interrupt_manager.get_active_sessions()
        
        # 按用户分组整理会话信息
        sessions_by_user = {}
        for session_id in active_sessions:
            parts = session_id.split('_')
            if len(parts) >= 2:
                username = parts[0]
                model_id = parts[1]
                if username not in sessions_by_user:
                    sessions_by_user[username] = []
                sessions_by_user[username].append({
                    "session_id": session_id,
                    "model_id": model_id
                })
        
        return JsonResponse({
            "error_num": 0,
            "msg": "获取活跃会话成功",
            "active_sessions": sessions_by_user,
            "total_count": len(active_sessions)
        })
        
    except Exception as e:
        return JsonResponse({
            "error_num": 1,
            "msg": f"获取活跃会话时发生错误: {str(e)}"
        }, status=500)


@csrf_exempt
@require_POST  
def force_cleanup_sessions(request):
    """强制清理所有会话（管理员功能）"""
    try:
        data = json.loads(request.body)
        username = data.get("username")
        
        # 这里可以添加管理员权限检查
        # if not is_admin(username):
        #     return JsonResponse({"error_num": 1, "msg": "权限不足"}, status=403)
        
        # 清理所有会话
        active_sessions = list(interrupt_manager.get_active_sessions())
        for session_id in active_sessions:
            interrupt_manager.cleanup_session(session_id)
        
        return JsonResponse({
            "error_num": 0,
            "msg": f"已清理 {len(active_sessions)} 个会话"
        })
        
    except Exception as e:
        return JsonResponse({
            "error_num": 1,
            "msg": f"清理会话时发生错误: {str(e)}"
        }, status=500)


@csrf_exempt
@require_POST
def interrupt_all_on_new_message(request):
    """用户发送新消息时，中断所有窗口的响应
    
    这个接口应该在用户点击发送新消息时被调用，
    会强制中断该用户所有正在进行的响应，确保不会有刹车失效的情况
    """
    try:
        data = json.loads(request.body)
        username = data.get("username")
        
        if not username:
            return JsonResponse({
                "error_num": 1,
                "msg": "缺少必要参数: username"
            }, status=400)
        
        # 强制中断用户的所有活跃会话
        count = interrupt_manager.interrupt_all_user_sessions(username, force=True)
        
        print(f"[新消息中断] 用户 {username} 发送新消息，已中断 {count} 个窗口的响应")
        
        return JsonResponse({
            "error_num": 0,
            "msg": f"新消息已触发全局中断，成功中断 {count} 个窗口",
            "interrupted_count": count
        })
        
    except Exception as e:
        return JsonResponse({
            "error_num": 1,
            "msg": f"全局中断失败: {str(e)}"
        }, status=500)
        active_sessions = interrupt_manager.get_active_sessions()
        cleaned_count = 0
        
        for session_id in list(active_sessions):
            interrupt_manager.cleanup_session(session_id)
            cleaned_count += 1
        
        return JsonResponse({
            "error_num": 0,
            "msg": f"成功清理 {cleaned_count} 个会话",
            "cleaned_count": cleaned_count
        })
        
    except Exception as e:
        return JsonResponse({
            "error_num": 1,
            "msg": f"清理会话时发生错误: {str(e)}"
        }, status=500)