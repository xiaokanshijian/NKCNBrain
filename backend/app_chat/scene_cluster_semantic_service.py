# encoding=utf-8
"""场景 / 任务簇大本体语义梳理：任务调度、状态、回退、结果读取。"""
from __future__ import annotations

import threading
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

from app_chat.scene_cluster_semantic_pipeline import (
    SCOPE_SCENE,
    SCOPE_TASK_CLUSTER,
    backup_scope_result,
    load_scope_backup,
    load_scope_result,
    rename_scope_keyword,
    restore_scope_backup,
    run_full_pipeline,
    update_scope_hierarchy_link_strength,
    update_scope_keyword_attrs,
)

_LOCK = threading.Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}


def _job_key(scope_type: str, scope_id: str, viewer: str) -> str:
    return f'{scope_type}:{scope_id}:{viewer}'


def _set_job(key: str, **kwargs) -> None:
    with _LOCK:
        job = _JOBS.setdefault(key, {})
        job.update(kwargs)
        if 'updated_at' not in kwargs:
            job['updated_at'] = datetime.now().isoformat(timespec='seconds')


def _is_running(key: str) -> bool:
    with _LOCK:
        job = _JOBS.get(key) or {}
        return bool(job.get('running'))


def get_job_status(scope_type: str, scope_id: str, viewer: str) -> Dict[str, Any]:
    key = _job_key(scope_type, scope_id, viewer)
    with _LOCK:
        job = dict(_JOBS.get(key) or {'running': False, 'phase': 'idle'})
    result = load_scope_result(scope_type, scope_id, viewer)
    backup = load_scope_backup(scope_type, scope_id, viewer)
    job['has_result'] = bool(result and result.get('has_result'))
    job['rollback_available'] = bool(backup) and not job.get('running')
    if backup:
        job['backup_created_at'] = backup.get('created_at')
    if result:
        job['keywords_count'] = len(result.get('keywords') or [])
        job['links_count'] = len(result.get('hierarchy_links') or [])
        job['scope_name'] = result.get('scope_name') or ''
        job['last_completed_at'] = result.get('last_completed_at') or result.get('updated_at') or ''
    # phase_label
    phase = job.get('phase') or 'idle'
    msg = job.get('message') or ''
    labels = {
        'idle': '空闲',
        'select_books': '筛选本子…',
        'book_prepare': '处理本子浓缩/取词…',
        'scope_keywords': '生成大本体关键词…',
        'scope_connect_attrs': '层次连边与属性…',
        'completed': '已完成',
        'error': '失败',
    }
    job['phase_label'] = msg or labels.get(phase, phase)
    if 'progress_percent' not in job:
        job['progress_percent'] = 100 if phase == 'completed' else (0 if phase == 'idle' else 5)
    return job


def get_result_payload(scope_type: str, scope_id: str, viewer: str) -> Dict[str, Any]:
    result = load_scope_result(scope_type, scope_id, viewer)
    if not result:
        return {'has_result': False}
    keywords = result.get('keywords') or []
    attrs = result.get('keywordFourColorDMT') or {}
    links = result.get('hierarchy_links') or []
    return {
        'has_result': True,
        'scope_type': scope_type,
        'scope_id': str(scope_id),
        'scope_name': result.get('scope_name') or '',
        'viewer': viewer,
        'keywords': keywords,
        'keywordFourColorDMT': attrs,
        'hierarchy_links': links,
        'key_issues': result.get('key_issues') or '',
        'semantic_reorganize_meta': {
            'hierarchy_links': links,
            'pipeline': result.get('pipeline') or 'scene_cluster_v1',
            'last_completed_at': result.get('last_completed_at') or result.get('updated_at') or '',
            'selected_books': result.get('selected_books') or [],
            'keywordFourColorDMT': attrs,
        },
        'meta': result,
    }


def start_scene_cluster_semantic(
    *,
    scope_type: str,
    scope_id: str,
    viewer: str,
    mode: str = 'full',
) -> Dict[str, Any]:
    scope_type = SCOPE_TASK_CLUSTER if scope_type == SCOPE_TASK_CLUSTER else SCOPE_SCENE
    viewer = (viewer or '').strip()
    scope_id = str(scope_id or '').strip()
    if not viewer or not scope_id:
        return {'ok': False, 'msg': 'viewer / scope_id 必填'}

    mode = (mode or 'full').strip().lower()
    if mode in ('incremental', 'iterate', '迭代'):
        return {'ok': False, 'msg': '迭代梳理语义尚未实现，请稍后再试'}

    key = _job_key(scope_type, scope_id, viewer)
    with _LOCK:
        cur = _JOBS.get(key) or {}
        if cur.get('running'):
            return {'ok': False, 'msg': '该范围梳理任务正在进行中'}

    # 若已有结果则备份（重新梳理可回退）
    existing = load_scope_result(scope_type, scope_id, viewer)
    if existing and existing.get('has_result'):
        backup_scope_result(scope_type, scope_id, viewer)

    _set_job(
        key,
        running=True,
        phase='select_books',
        progress_percent=2,
        message='已提交任务…',
        error='',
        mode='full',
        started_at=datetime.now().isoformat(timespec='seconds'),
    )

    def _job():
        try:
            run_full_pipeline(
                scope_type=scope_type,
                scope_id=scope_id,
                viewer=viewer,
                set_job_fn=_set_job,
                is_running_fn=_is_running,
                job_key=key,
            )
            _set_job(
                key,
                running=False,
                phase='completed',
                progress_percent=100,
                message='完成',
            )
        except Exception as exc:
            traceback.print_exc()
            _set_job(
                key,
                running=False,
                phase='error',
                progress_percent=100,
                message=str(exc),
                error=str(exc),
            )

    threading.Thread(target=_job, daemon=True).start()
    return {'ok': True, 'msg': '已开始梳理', 'mode': 'full'}


def rollback_scene_cluster_semantic(
    *,
    scope_type: str,
    scope_id: str,
    viewer: str,
) -> Dict[str, Any]:
    scope_type = SCOPE_TASK_CLUSTER if scope_type == SCOPE_TASK_CLUSTER else SCOPE_SCENE
    viewer = (viewer or '').strip()
    key = _job_key(scope_type, scope_id, viewer)
    if _is_running(key):
        return {'ok': False, 'msg': '梳理任务进行中，无法回退'}
    result = restore_scope_backup(scope_type, scope_id, viewer)
    if result.get('ok'):
        _set_job(
            key,
            running=False,
            phase='idle',
            message='已回退',
            rollback_applied_at=datetime.now().isoformat(timespec='seconds'),
        )
    return result


def update_scene_cluster_link_strength(
    *,
    scope_type: str,
    scope_id: str,
    viewer: str,
    parent: str,
    child: str,
    strength: str,
) -> Dict[str, Any]:
    scope_type = SCOPE_TASK_CLUSTER if scope_type == SCOPE_TASK_CLUSTER else SCOPE_SCENE
    return update_scope_hierarchy_link_strength(
        scope_type,
        scope_id,
        username=viewer,
        parent=parent,
        child=child,
        strength=strength,
    )


def update_scene_cluster_keyword_attrs(
    *,
    scope_type: str,
    scope_id: str,
    viewer: str,
    keyword: str,
    four_color_type: str = '',
    dmt_level: str = '',
    knowledge_type: str = '',
) -> Dict[str, Any]:
    scope_type = SCOPE_TASK_CLUSTER if scope_type == SCOPE_TASK_CLUSTER else SCOPE_SCENE
    return update_scope_keyword_attrs(
        scope_type,
        scope_id,
        username=viewer,
        keyword=keyword,
        four_color_type=four_color_type,
        dmt_level=dmt_level,
        knowledge_type=knowledge_type,
    )


def rename_scene_cluster_keyword(
    *,
    scope_type: str,
    scope_id: str,
    viewer: str,
    old_keyword: str,
    new_keyword: str,
) -> Dict[str, Any]:
    scope_type = SCOPE_TASK_CLUSTER if scope_type == SCOPE_TASK_CLUSTER else SCOPE_SCENE
    return rename_scope_keyword(
        scope_type,
        scope_id,
        username=viewer,
        old_keyword=old_keyword,
        new_keyword=new_keyword,
    )
