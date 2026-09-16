# app_chat/ci/_utils.py
# Phase 1.1 产物：从 continuous_image_service.py 抽取的通用基础工具函数
# 来源映射：continuous_image_service.py L102-281
# 规则：函数体与原始定义完全一致，不做任何行为修改

import datetime
import json
import os
import re
from typing import Any, Dict, Optional

from llm_langchain import global_var


# ─── JSON 序列化 / 反序列化 ──────────────────────────────────────────────────
# from continuous_image_service.py L102-109

def _safe_json_dump(path: str, data: Dict[str, Any]) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _safe_json_load(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ─── 文件读取 ─────────────────────────────────────────────────────────────────
# from continuous_image_service.py L112-119

def _read_text_if_exists(path: str, default: str = '') -> str:
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return default


# ─── 任务状态更新 ─────────────────────────────────────────────────────────────
# from continuous_image_service.py L122-138

def _update_task(task_id: str, *, current_item: Optional[int] = None, total_items: Optional[int] = None,
                 current_section: Optional[str] = None, completed: Optional[bool] = None,
                 error: Optional[str] = None, failure_stage: Optional[str] = None,
                 content_validation: Optional[dict] = None, warnings: Optional[list] = None) -> None:
    if task_id not in global_var.tasks:
        global_var.tasks[task_id] = {}
    task = global_var.tasks[task_id]

    if current_item is not None:
        task['current_item'] = current_item
    if total_items is not None:
        task['total_items'] = total_items
    if current_section is not None:
        task['current_section'] = current_section
    if completed is not None:
        task['completed'] = completed
    if error is not None:
        task['error'] = error
    for key, value in {'failure_stage': failure_stage, 'content_validation': content_validation,
                       'warnings': warnings}.items():
        if value is not None:
            task[key] = value
    if task.get('_ci_persistent'):
        from app_chat.ci.task_store import update_task
        changes = {key: value for key, value in {
            'current_item': current_item, 'total_items': total_items,
            'current_section': current_section, 'completed': completed,
            'error': error, 'failure_stage': failure_stage,
            'content_validation': content_validation, 'warnings': warnings}.items() if value is not None}
        task.update(update_task(task_id, changes))


# ─── 时间工具 ─────────────────────────────────────────────────────────────────
# from continuous_image_service.py L182-183

def _now_iso() -> str:
    return datetime.datetime.now().isoformat()


# ─── 文本工具 ─────────────────────────────────────────────────────────────────
# from continuous_image_service.py L186-201

def _truncate_text(value: Any, max_len: int) -> str:
    return str(value or '').strip()[:max_len]


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ('true', '1', 'yes', 'y', 'on'):
            return True
        if s in ('false', '0', 'no', 'n', 'off'):
            return False
    return bool(value)


# ─── 文件名提取 ───────────────────────────────────────────────────────────────
# from continuous_image_service.py L228-236

def _extract_filename(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ('filename', 'file_name', 'name', 'docs_name', 'value'):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ''


# ─── 路径安全校验与解析 ───────────────────────────────────────────────────────
# from continuous_image_service.py L239-261

def _is_safe_user_relative_path(path: str) -> bool:
    if not path or '..' in path:
        return False
    if path.startswith('/') or path.startswith('\\'):
        return False
    if re.match(r'^[A-Za-z]:', path):
        return False
    return True


def _normalize_rel(path: str) -> str:
    return path.replace('\\', '/').lstrip('./')


def _resolve_user_file_path(username: str, file_name: str) -> str:
    rel = _normalize_rel(file_name)
    if not _is_safe_user_relative_path(rel):
        return ''
    base_dir = os.path.abspath(os.path.join('.', 'received_dir', 'user_raw_file', username))
    abs_path = os.path.abspath(os.path.join(base_dir, rel))
    if not abs_path.startswith(base_dir):
        return ''
    return abs_path


# ─── CI 目录路径工具 ──────────────────────────────────────────────────────────
# from continuous_image_service.py L271-280

def _ci_dmt_root(username: str) -> str:
    return os.path.join('.', 'received_dir', 'user_raw_file', username, 'continuous_image_dmt')


def _ci_d_cache_root(username: str) -> str:
    return os.path.join(_ci_dmt_root(username), 'd_cache')


def _ci_index_path(username: str) -> str:
    return os.path.join(_ci_dmt_root(username), 'index.json')
