"""质量单独重试沿用原运行快照，并与同PDF启动/重跑互斥。"""
import json
from pathlib import Path
import threading
import uuid

from app_chat.ci.task_store import create_task, update_task
from .feedback_start_service import RunLease
from .feedback_runtime_service import restore_feedback_runtime
from .feedback_snapshot_reader import is_sha256


def start_quality_retry(workspace, analysis_id, *, sid=None):
    from llm_langchain import global_var
    from .homework_versions import resolve_homework_run_root
    from .service import check_homework_stage_ready, run_homework_red_blue_review
    root = Path(resolve_homework_run_root(workspace, analysis_id))
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
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
        if manifest.get('source_document_sha256') != digest:
            raise ValueError('当前版本源文件已变化，请重新打开结果')
        if not check_homework_stage_ready(workspace, analysis_id, 'grading'):
            raise ValueError('完整批改尚未完成，暂不能重新评分')
        task_id = 'ci_task_' + uuid.uuid4().hex
        record = create_task({'task_id': task_id, '_ci_principal': workspace, '_ci_workspace': workspace,
            'analysis_id': analysis_id, 'run_id': manifest.get('run_id') or 'current',
            'source_document_sha256': digest, 'config_fingerprint': runtime.fingerprint,
            'files': manifest.get('selected_files', []), 'task_kind': 'homework_red_blue_review',
            'analysis_type': 'homework_grading', 'current_item': 0, 'total_items': 1,
            'current_section': '准备重新评分', 'error': ''})
        global_var.tasks[task_id] = record

        def worker():
            try:
                update_task(task_id, {'status': 'running'})
                run_homework_red_blue_review(task_id, workspace, analysis_id,
                    feedback_runtime=runtime, run_id=record['run_id'])
            except Exception as exc:
                update_task(task_id, {'status': 'failed', 'error': str(exc), 'failure_stage': 'quality'})
            finally:
                lease.release()

        threading.Thread(target=worker, name='ci-quality-' + task_id, daemon=True).start()
        handed_off = True
        return {'error_num': 0, 'msg': 'success', 'task_id': task_id, 'analysis_id': analysis_id,
                'analysis_type': 'homework_grading', 'run_id': record['run_id'],
                'config_fingerprint': runtime.fingerprint, 'feedback_context': runtime.context}
    except Exception as exc:
        if task_id:
            update_task(task_id, {'status': 'failed', 'error': str(exc), 'failure_stage': 'startup'})
        raise
    finally:
        if not handed_off:
            lease.release()
