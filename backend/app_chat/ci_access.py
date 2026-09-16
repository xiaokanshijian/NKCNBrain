"""CI 请求上下文与路径校验；沿用客户端声明的工作区，不执行身份授权。"""
import json
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse


class CIRequestError(ValueError):
    """CI 请求参数或工作区路径无效。"""


def _tasks():
    from llm_langchain import global_var
    return global_var.tasks


def request_error_response(exc):
    return JsonResponse({'error_num': 1, 'msg': str(exc)})


def is_relative_to(path: Path, other: Path) -> bool:
    """Python 3.8 兼容：Path.is_relative_to 仅 3.9+ 提供。"""
    try:
        Path(path).relative_to(Path(other))
        return True
    except ValueError:
        return False


def assert_workspace_path(workspace, path):
    if (not isinstance(workspace, str) or not workspace or workspace != workspace.strip()
            or any(char in workspace for char in ('/', '\\', '\x00', ':'))
            or workspace in ('.', '..')):
        raise CIRequestError('工作区标识无效')
    root = (Path(settings.BASE_DIR) / 'received_dir' / 'user_raw_file' / workspace).resolve()
    resolved = Path(path).resolve()
    if not is_relative_to(resolved, root):
        raise CIRequestError('文件不在当前本子工作区内')
    return str(resolved)


def ci_request_context(view):
    """从请求或任务记录取得工作区，并保留原 CI 参数与路径校验。"""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            data = json.loads(request.body) if request.method == 'POST' and request.body else request.GET
            if not hasattr(data, 'get'):
                raise CIRequestError('请求参数必须为对象')
            task_id = kwargs.get('task_id')
            task = None
            if task_id:
                if task_id.startswith('ci_task_'):
                    from app_chat.ci.task_store import read_task
                    try:
                        task = read_task(task_id)
                    except (ValueError, OSError) as exc:
                        raise CIRequestError('持久化任务记录无法读取，请保留现场检查') from exc
                task = task or _tasks().get(task_id)
                workspace = (task or {}).get('_ci_workspace') or (task or {}).get('username')
                request.ci_task = task
            else:
                workspace = data.get('username')
            if workspace is not None:
                assert_workspace_path(workspace,
                    Path(settings.BASE_DIR) / 'received_dir' / 'user_raw_file' / workspace)
            request.ci_workspace = workspace
            # 兼容现有调用签名和 ci-task-v1；该值不再表示可信身份。
            request.ci_principal = workspace
            files = data.get('files', [])
            if not isinstance(files, list) or any(not isinstance(name, str) or not name for name in files):
                raise CIRequestError('files必须为文件名数组')
            if files and not workspace:
                raise CIRequestError('缺少username')
            for name in files:
                path = Path(settings.BASE_DIR) / 'received_dir' / 'user_raw_file' / workspace / name
                assert_workspace_path(workspace, path)
            for name in ('analysis_id', 'analysis_id_a', 'analysis_id_b', 'run_id', 'runId'):
                value = data.get(name)
                if value and (not isinstance(value, str)
                              or any(char in value for char in ('/', '\\', '\x00', ':'))
                              or value in ('.', '..')):
                    raise CIRequestError('分析或版本标识无效')
            response = view(request, *args, **kwargs)
            if (workspace and not getattr(response, 'streaming', False)
                    and response.get('Content-Type', '').startswith('application/json')):
                payload = json.loads(response.content)
                created = payload.get('task_id') if isinstance(payload, dict) else None
                if created and created in _tasks():
                    _tasks()[created]['_ci_workspace'] = workspace
                    _tasks()[created]['_ci_principal'] = workspace
            return response
        except CIRequestError as exc:
            return request_error_response(exc)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return request_error_response(CIRequestError('请求JSON无效'))
    return wrapped


# 保留既有装饰器名称，避免改变所有 CI 视图的公共接线。
ci_access = ci_request_context
