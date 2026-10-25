"""以操作系统运行锁核实进程存活；内存任务缺失不代表执行完成。"""
import json
from pathlib import Path

from app_chat.ci.file_io import FileLockBusy, atomic_json
from app_chat.ci.task_store import read_task, update_task, TERMINAL
from .feedback_start_service import RunLease
from .completion import summarize_completion, finish_delivery


def task_reference(workspace, analysis_id, manifest, root, *, recover=False):
    """只返回与当前运行完全匹配的任务；历史结果读取不执行恢复写入。"""
    task_id = manifest.get('task_id')
    try:
        if not task_id:
            from .feedback_start_transaction import JOURNAL
            container = Path(root).parent.parent if Path(root).parent.name == '_runs' else Path(root)
            journal = container / JOURNAL
            if journal.is_file():
                record = json.loads(journal.read_text(encoding='utf-8'))
                if record.get('run_id') == manifest.get('run_id'):
                    task_id = record.get('task_id')
        if not task_id:
            return None, '无法核实当前任务记录，请重新连接后检查。' if manifest.get('status') in ('running', 'prepared') else ''
        task = read_task(task_id)
        if not task or any((task.get('_ci_workspace') != workspace,
                            task.get('analysis_id') != analysis_id,
                            task.get('run_id') != (manifest.get('run_id') or 'current'),
                            task.get('source_document_sha256') != manifest.get('source_document_sha256'))):
            return None, '任务记录与当前材料版本不一致，未恢复订阅。'
        if recover:
            task = recover_abandoned_task(task)
        return {key: task.get(key) for key in ('task_id', 'run_id', 'analysis_id', 'task_kind', 'status',
                                              'completed', 'error', 'failure_stage', 'current_section')}, ''
    except (OSError, ValueError, KeyError):
        return None, '任务记录暂不可读，请重新连接。'


def completion_for_task(task):
    from .homework_versions import resolve_homework_run_root
    root = Path(resolve_homework_run_root(task['_ci_workspace'], task['analysis_id'], task['run_id']))
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('run_id', 'current') != task['run_id'] or manifest.get('source_document_sha256') != task['source_document_sha256']:
        raise ValueError('任务与批改版本不一致')
    return summarize_completion(manifest)


def enrich_query_records(workspace, records):
    """补充批改状态；某条记录不可读只影响该条，不阻断其他文件查询。"""
    from .homework_versions import resolve_homework_run_root
    for record in records:
        if record.get('analysis_type') != 'homework_grading':
            continue
        try:
            root = Path(resolve_homework_run_root(workspace, record['analysis_id']))
            manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
            task, error = task_reference(workspace, record['analysis_id'], manifest, root, recover=True)
            # 恢复可能刚将清单改为interrupted，重读后再汇总。
            manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
            record.update(status=manifest.get('status', record.get('status')), task=task,
                          completion=summarize_completion(manifest), task_lookup_error=error)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            record['task_lookup_error'] = '本版本状态暂不可读，请重新连接。'
    return records


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
            manifest['red_blue_review'] = {'status': 'failed', 'score': None, 'color': '', 'error': '评分进程已中断，可重新评分'}
            finish_delivery(manifest)
            atomic_json(path, manifest)
            CIIndexManager.update_status(workspace, analysis_id, manifest['status'])
        return update_task(task['task_id'], {'status': 'interrupted', 'failure_stage': 'interrupted',
            'current_section': '执行已中断', 'error': '执行进程已中断，已保留原有产物，请重新启动或续跑'})
    finally:
        lease.release()
