"""以操作系统运行锁核实进程存活；内存任务缺失不代表执行完成。"""
import json
from pathlib import Path

from app_chat.ci.file_io import FileLockBusy, atomic_json
from app_chat.ci.task_store import read_task, update_task, TERMINAL
from .feedback_start_service import RunLease


def recover_abandoned_task(task):
    if not task.get('_ci_persistent') or task.get('status') in TERMINAL:
        return task
    try:
        lease = RunLease(task['_ci_workspace'], task['source_document_sha256']).acquire()
    except FileLockBusy:
        return task
    try:
        latest = read_task(task['task_id'])
        if not latest or latest.get('status') in TERMINAL:
            return latest or task
        from .homework_versions import _container_root, resolve_homework_run_root
        from .feedback_start_transaction import recover_start, JOURNAL
        from app_chat.ci.index_manager import CIIndexManager
        workspace, analysis_id = task['_ci_workspace'], task['analysis_id']
        container = Path(_container_root(workspace, analysis_id))
        journal_path = container / JOURNAL
        if journal_path.is_file():
            journal = json.loads(journal_path.read_text(encoding='utf-8'))
            if journal.get('task_id') == task['task_id']:
                recover_start(container, write_index=lambda record: CIIndexManager.restore_record(workspace, analysis_id, record))
                latest = read_task(task['task_id'])
                if latest and latest.get('status') in TERMINAL:
                    return latest
        # 单独质量重试没有版本切换事务；只记录评分中断，不破坏已完成批改。
        if task.get('task_kind') == 'homework_red_blue_review':
            root = Path(resolve_homework_run_root(workspace, analysis_id, task['run_id']))
            path = root / 'manifest.json'
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['red_blue_review'] = {'status': 'failed', 'error': '评分进程已中断，可重新评分'}
            atomic_json(path, manifest)
        return update_task(task['task_id'], {'status': 'interrupted', 'failure_stage': 'interrupted',
            'current_section': '执行已中断', 'error': '执行进程已中断，已保留原有产物，请重新启动或续跑'})
    finally:
        lease.release()
