"""
文档TODO清单的API视图
"""

import json
import threading
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from app_chat.models import AutomationRecord
from app_chat.document_todo import (
    detect_todo_card,
    parse_todo_items,
    DocumentTodoEngine,
    TODO_TASKS
)


@csrf_exempt
def check_todo_card(request):
    """
    检查是否存在TODO清单卡片
    
    请求参数：
        username: 用户名（notebook_id）
        filename: 文件名
    
    返回：
        has_todo: 是否有TODO卡片
        card_id: 卡片ID
        todo_items: TODO项列表
        total_items: TODO项总数
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        filename = data.get('filename')
        
        if not username or not filename:
            return JsonResponse({
                'error_num': 1,
                'msg': '缺少必要参数'
            })
        
        # 检测TODO卡片
        todo_card = detect_todo_card(username, filename)
        
        if not todo_card:
            return JsonResponse({
                'error_num': 0,
                'has_todo': False,
                'msg': '未找到TODO清单卡片'
            })
        
        # 解析TODO项
        todo_items = parse_todo_items(todo_card.content)
        
        if not todo_items:
            return JsonResponse({
                'error_num': 0,
                'has_todo': False,
                'msg': 'TODO清单卡片存在但未能解析出清单项'
            })
        
        return JsonResponse({
            'error_num': 0,
            'has_todo': True,
            'card_id': todo_card.cid,
            'todo_items': todo_items,
            'total_items': len(todo_items),
            'msg': f'找到 {len(todo_items)} 个TODO项'
        })
        
    except Exception as e:
        return JsonResponse({
            'error_num': 1,
            'msg': f'检查TODO卡片失败: {str(e)}'
        })


@csrf_exempt
def start_document_todo(request):
    """
    启动文档TODO自动化
    
    请求参数：
        notebook_id: 本子ID
        filename: 文件名
        todo_items: TODO项列表（可选，如果不提供则自动检测）
    
    返回：
        task_id: 任务ID
        total_items: 总TODO项数
    """
    try:
        data = json.loads(request.body)
        notebook_id = data.get('notebook_id')
        filename = data.get('filename')
        todo_items = data.get('todo_items')
        current_user = data.get('current_user', notebook_id.split('_')[0])  # 🔥 获取当前登录用户
        
        if not notebook_id or not filename:
            return JsonResponse({
                'error_num': 1,
                'msg': '缺少必要参数'
            })
        
        # 如果没有提供TODO项，自动检测
        if not todo_items:
            todo_card = detect_todo_card(notebook_id, filename)
            if not todo_card:
                return JsonResponse({
                    'error_num': 1,
                    'msg': '未找到TODO清单卡片'
                })
            
            todo_items = parse_todo_items(todo_card.content)
            if not todo_items:
                return JsonResponse({
                    'error_num': 1,
                    'msg': '无法解析TODO清单'
                })
        
        # 检查是否有示范操作记录
        has_demo = AutomationRecord.objects.filter(
            notebook_id=notebook_id,
            target_file=filename
        ).exists()
        
        if not has_demo:
            return JsonResponse({
                'error_num': 1,
                'msg': '请先完成第一项的操作示范'
            })
        
        # 创建TODO引擎
        engine = DocumentTodoEngine(notebook_id, filename, todo_items, current_user=current_user)
        
        # 生成任务ID
        task_id = f"todo_{notebook_id}_{filename}_{len(TODO_TASKS)}"
        TODO_TASKS[task_id] = engine
        
        # 在后台线程中执行
        thread = threading.Thread(
            target=engine.run_for_remaining_items,
            daemon=True
        )
        thread.start()
        
        return JsonResponse({
            'error_num': 0,
            'task_id': task_id,
            'total_items': len(todo_items),
            'msg': f'已启动TODO自动化，共 {len(todo_items)} 项'
        })
        
    except Exception as e:
        import traceback
        return JsonResponse({
            'error_num': 1,
            'msg': f'启动失败: {str(e)}',
            'traceback': traceback.format_exc()
        })


@csrf_exempt
def get_todo_progress(request):
    """
    查询TODO自动化进度
    
    请求参数：
        task_id: 任务ID
    
    返回：
        current_item: 当前项索引
        total_items: 总项数
        status: 状态
    """
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        
        if not task_id or task_id not in TODO_TASKS:
            return JsonResponse({
                'error_num': 1,
                'msg': '任务不存在'
            })
        
        engine = TODO_TASKS[task_id]
        
        return JsonResponse({
            'error_num': 0,
            'current_item': engine.current_item_index,
            'total_items': len(engine.todo_items),
            'status': 'running' if not engine.stop_flag else 'stopped',
            'msg': '查询成功'
        })
        
    except Exception as e:
        return JsonResponse({
            'error_num': 1,
            'msg': f'查询失败: {str(e)}'
        })


@csrf_exempt
def stop_document_todo(request):
    """
    停止文档TODO自动化
    
    请求参数：
        task_id: 任务ID
    """
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        
        if not task_id or task_id not in TODO_TASKS:
            return JsonResponse({
                'error_num': 1,
                'msg': '任务不存在'
            })
        
        engine = TODO_TASKS[task_id]
        engine.stop_flag = True
        
        return JsonResponse({
            'error_num': 0,
            'msg': 'TODO自动化已停止'
        })
        
    except Exception as e:
        return JsonResponse({
            'error_num': 1,
            'msg': f'停止失败: {str(e)}'
        })

