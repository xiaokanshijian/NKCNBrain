"""质量单独重试沿用原运行快照，并与同PDF启动/重跑互斥。"""
import json
from pathlib import Path
import threading
import uuid

from app_chat.ci.task_store import create_task, update_task
from .feedback_start_service import RunLease
from .feedback_runtime_service import restore_feedback_runtime
from .feedback_snapshot_reader import is_sha256
from .completion import saved_report_ready, available_actions, summarize_completion, finish_delivery


def start_quality_retry(workspace, analysis_id, *, sid=None):
    from llm_langchain import global_var
    from .homework_versions import resolve_homework_run_root
    from .service import prepare_homework_workspace, run_homework_red_blue_review
    from app_chat.ci.index_manager import CIIndexManager
    from .utils import safe_json_dump
    root = Path(resolve_homework_run_root(workspace, analysis_id))
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    requested_run = manifest.get('run_id') or 'current'
    digest = manifest.get('source_document_sha256')
    if not is_sha256(digest):
        raise ValueError('原版本缺少完整源文件标识，不能单独重试质量评分')
    lease = RunLease(workspace, digest).acquire()
    handed_off = False
    task_id = None
    try:
        root = Path(resolve_homework_run_root(workspace, analysis_id))
        runtime = restore_feedback_runtime(root)
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('run_id') or 'current') != requested_run:
            raise ValueError('等待评分期间当前版本已变化，请重新打开结果')
        if manifest.get('source_document_sha256') != digest:
            raise ValueError('当前版本源文件已变化，请重新打开结果')
        paths = prepare_homework_workspace(workspace, analysis_id, create=False)
        actions = available_actions(manifest, summarize_completion(manifest), snapshot_ok=True,
                                    artifacts_ok=saved_report_ready(paths, manifest))
        if not actions['retry_quality']['enabled']:
            raise ValueError(actions['retry_quality']['reason'])
        task_id = 'ci_task_' + uuid.uuid4().hex
        record = create_task({'task_id': task_id, '_ci_principal': workspace, '_ci_workspace': workspace,
            'analysis_id': analysis_id, 'run_id': manifest.get('run_id') or 'current',
            'source_document_sha256': digest, 'config_fingerprint': runtime.fingerprint,
            'files': manifest.get('selected_files', []), 'task_kind': 'homework_red_blue_review',
            'analysis_type': 'homework_grading', 'current_item': 0, 'total_items': 1,
            'current_section': '准备重新评分', 'error': ''})
        global_var.tasks[task_id] = record
        manifest['task_id'] = task_id
        manifest['red_blue_review'] = {'status': 'pending', 'score': None, 'color': '', 'error': ''}
        finish_delivery(manifest)
        safe_json_dump(root / 'manifest.json', manifest)
        previous_index = CIIndexManager.find_by_id(workspace, analysis_id) or {}
        CIIndexManager.add_or_update(workspace, {**previous_index,
            'analysis_id': analysis_id, 'task_id': task_id, 'analysis_type': 'homework_grading',
            'mode': 'single', 'files': manifest.get('selected_files', []),
            'source_document_sha256': digest, 'run_id': record['run_id'], 'status': manifest['status']})

        def worker():
            try:
                update_task(task_id, {'status': 'running'})
                run_homework_red_blue_review(task_id, workspace, analysis_id,
                    feedback_runtime=runtime, run_id=record['run_id'])
            except Exception as exc:
                failed = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
                failed['red_blue_review'] = {'status': 'failed', 'score': None, 'color': '', 'error': str(exc)}
                completion = finish_delivery(failed)
                safe_json_dump(root / 'manifest.json', failed)
                CIIndexManager.update_status(workspace, analysis_id, failed['status'])
                update_task(task_id, {'status': 'failed', 'error': str(exc), 'failure_stage': 'quality',
                                     'completion': completion})
            finally:
                lease.release()

        threading.Thread(target=worker, name='ci-quality-' + task_id, daemon=True).start()
        handed_off = True
        return {'error_num': 0, 'msg': 'success', 'task_id': task_id, 'analysis_id': analysis_id,
                'analysis_type': 'homework_grading', 'run_id': record['run_id'],
                'config_fingerprint': runtime.fingerprint, 'feedback_context': runtime.context}
    except Exception as exc:
        if task_id:
            manifest['red_blue_review'] = {'status': 'failed', 'score': None, 'color': '', 'error': str(exc)}
            finish_delivery(manifest)
            safe_json_dump(root / 'manifest.json', manifest)
            CIIndexManager.update_status(workspace, analysis_id, manifest['status'])
            update_task(task_id, {'status': 'failed', 'error': str(exc), 'failure_stage': 'startup'})
        raise
    finally:
        if not handed_off:
            lease.release()
