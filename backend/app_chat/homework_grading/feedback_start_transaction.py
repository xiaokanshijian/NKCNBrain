"""新版本发布事务；调用者持有文档运行锁，后台仅在登记完成后启动。"""
import json
from pathlib import Path

from app_chat.ci.file_io import atomic_json
from app_chat.ci.task_store import create_task, read_task, update_task
from .feedback_workspaces import read_pointer, publish_pointer, restore_pointer, run_directory

JOURNAL = 'start_transaction.json'


def _save(container, journal):
    atomic_json(Path(container) / JOURNAL, journal)


def _rollback(container, journal, write_index, task_root=None):
    restore_pointer(container, journal['previous_pointer'])
    if journal.get('index_attempted'):
        write_index(journal['previous_index'])
    task = read_task(journal['task_id'], root=task_root)
    if task and task.get('run_id') == journal['run_id']:
        update_task(journal['task_id'], {'completed': True, 'status': 'failed',
            'error': '启动事务未完成，原版本已恢复', 'failure_stage': 'startup'}, root=task_root)
    journal['phase'] = 'rolled_back'
    _save(container, journal)


def publish_start(container, run_id, task, *, previous_index, archive, write_index,
                  new_index, launch, task_root=None):
    """archive/write_index/launch为服务端函数，不能从请求参数构造。

    独立快照已准备好；回滚只恢复指针和单文档索引，不删除新旧目录。
    launch须在成功启动后台后立即返回，后台完成情况由持久化任务记录。
    """
    directory = run_directory(container, run_id)
    from .feedback_snapshot_reader import read_feedback_snapshot
    state = read_feedback_snapshot(directory)
    if (state['snapshot_status'] != 'complete' or task.get('run_id') != run_id
            or state['config_fingerprint'] != task.get('config_fingerprint')):
        raise ValueError('新运行快照与任务依据不一致')
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('source_document_sha256') != task.get('source_document_sha256')
            or manifest.get('group_id') != task.get('analysis_id')):
        raise ValueError('新运行源文件与任务身份不一致')
    journal = {'schema_version': 'ci-start-v1', 'phase': 'prepared',
               'run_id': run_id, 'task_id': task['task_id'],
               'previous_pointer': read_pointer(container), 'previous_index': previous_index,
               'index_attempted': False}
    _save(container, journal)
    try:
        journal['archived_run_id'] = archive() or ''
        journal['phase'] = 'archived'
        _save(container, journal)
        registered = create_task(task, root=task_root)
        journal['phase'] = 'registered'
        _save(container, journal)
        publish_pointer(container, run_id)
        journal['phase'] = 'published'
        journal['index_attempted'] = True
        _save(container, journal)
        write_index(new_index)
        # 先持久化派发意图；进程即使在Thread.start前退出，也不会被当作完成。
        journal['phase'] = 'dispatched'
        _save(container, journal)
        launch(registered)
        return registered, journal
    except Exception as exc:
        try:
            _rollback(container, journal, write_index, task_root)
        except Exception as rollback_error:
            journal.update(phase='rollback_required', error=str(exc), rollback_error=str(rollback_error))
            _save(container, journal)
            raise RuntimeError('启动失败且版本恢复尚未完成，请保留目录并重试恢复') from exc
        raise


def recover_start(container, *, write_index, task_root=None):
    """仅在调用者已经获取原文档运行锁后执行，避免误判仍在途任务。"""
    path = Path(container) / JOURNAL
    if not path.is_file():
        return None
    journal = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(journal, dict) or journal.get('schema_version') != 'ci-start-v1':
        raise ValueError('启动事务记录损坏，不能覆盖当前版本')
    if journal.get('phase') in ('rolled_back', 'finished', 'interrupted'):
        return journal
    task = read_task(journal['task_id'], root=task_root)
    if journal.get('phase') == 'dispatched':
        if task and task.get('completed'):
            journal['phase'] = 'finished'
        else:
            if task:
                update_task(journal['task_id'], {'status': 'interrupted',
                    'error': '批改进程已中断，请检查已有产物并重新启动',
                    'failure_stage': 'interrupted'}, root=task_root)
            directory = run_directory(container, journal['run_id'])
            manifest_path = directory / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest.update(status='interrupted', failure_stage='interrupted')
            atomic_json(manifest_path, manifest)
            # 用现有任务身份更新单文档记录，不覆盖其他文档索引。
            if task:
                write_index({'analysis_id': task['analysis_id'], 'mode': 'single',
                             'analysis_type': 'homework_grading', 'files': task.get('files', []),
                             'status': 'interrupted', 'run_id': task['run_id']})
            journal['phase'] = 'interrupted'
        _save(container, journal)
    else:
        _rollback(container, journal, write_index, task_root)
    return journal
