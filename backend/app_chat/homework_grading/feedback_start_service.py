"""正常入口的冻结、复用、发布及后台生命周期。"""
import datetime
import hashlib
import json
from pathlib import Path
import threading
import uuid

import fitz

from app_chat.ci.file_io import FileLock, atomic_json
from app_chat.ci.index_manager import CIIndexManager
from app_chat.ci.task_store import runtime_root, create_task, read_task, update_task
from app_chat.ci_access import assert_workspace_path
from .feedback_request import resolve_feedback_request
from .feedback_runtime_service import build_request_runtime, restore_feedback_runtime
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_reader import read_feedback_snapshot
from .feedback_start_transaction import publish_start, recover_start
from .feedback_workspaces import current_directory, run_directory
from .utils import sha256_file
from .completion import RECOVERABLE, summarize_completion


class RunLease:
    def __init__(self, workspace, digest):
        root = runtime_root() / 'locks'
        identities = (('user', workspace), ('workspace', workspace))
        self.locks = [FileLock(root / (hashlib.sha256(
            (kind + '\0' + identity + '\0' + (digest if kind == 'user' else digest[:24])).encode()).hexdigest() + '.lock'))
            for kind, identity in identities]
        self.held = []

    def acquire(self):
        try:
            for lock in self.locks:
                lock.acquire()
                self.held.append(lock)
            return self
        except Exception:
            self.release()
            raise

    def release(self):
        while self.held:
            self.held.pop().release()


def _response(task, runtime, target_stage, message):
    return {'error_num': 0, 'msg': message, 'task_id': task['task_id'],
            'analysis_id': task['analysis_id'], 'analysis_type': 'homework_grading',
            'run_id': task['run_id'], 'config_fingerprint': runtime.fingerprint,
            'feedback_context': runtime.context, 'snapshot_status': 'complete',
            'warnings': task.get('warnings', []),
            'homework_target_stage': target_stage,
            'preprocess_mode': runtime.dependencies['preprocessing']['mode']}


def start_grading_request(workspace, filename, data, *, resolution=None, rerun=False):
    from django.conf import settings
    from llm_langchain import global_var
    from .service import run_homework_grading, check_homework_stage_ready
    from .staged_pipeline import normalize_homework_target_stage
    from .homework_versions import (_container_root, archive_homework_run_if_exists,
                                    _copy_homework_version_workspace)

    if data.get('homework_target_stage') not in (None, '', 'layout', 'understanding', 'grading'):
        raise ValueError('批改目标阶段无效')
    if not isinstance(filename, str) or not filename.lower().endswith('.pdf'):
        raise ValueError('批改当前仅支持单份PDF')
    refresh_saved_settings = (
        not rerun
        or data.get('refresh_configuration') is True
        or str(data.get('refresh_configuration') or '').strip().lower() in ('1', 'true')
        or ('notebook_skill_selection' not in data and (
            data.get('full_recompute') is True
            or str(data.get('full_recompute') or '').strip().lower() in ('1', 'true')))
    )
    settings_source_digest = None
    if refresh_saved_settings:
        from app_chat.feedback_material_identity import source_digest
        settings_source_digest = source_digest(workspace, filename)
        from app_chat.feedback_material_settings import merge_saved_material_settings
        data, _ = merge_saved_material_settings(workspace, filename, data)
    source = Path(assert_workspace_path(workspace,
        Path(settings.BASE_DIR) / 'received_dir' / 'user_raw_file' / workspace / filename))
    if not source.is_file():
        raise ValueError('材料PDF不存在')
    with fitz.open(source) as document:
        if document.needs_pass or not document.page_count:
            raise ValueError('材料PDF为空或已加密，请提供可读取文件')
        source_page_count = document.page_count
    resolution = ({'route': 'homework_grading', 'warnings': []} if rerun else resolution) or resolve_feedback_request(filename, data.get('feedback_overrides'),
                                                       data.get('requested_action', 'auto'))
    if resolution['route'] != 'homework_grading':
        raise ValueError('当前请求不是可执行的题目批改')
    digest = sha256_file(str(source))
    if refresh_saved_settings and settings_source_digest != digest:
        raise ValueError('读取材料设置期间源文件发生变化，请重新打开材料')
    analysis_id = 'homework_' + digest[:24]
    if rerun and data.get('analysis_id') != analysis_id:
        raise ValueError('源PDF已变化，不能对原运行发起续跑；请从材料入口完整新跑')
    lease = RunLease(workspace, digest).acquire()
    handed_off = False
    try:
        container = Path(_container_root(workspace, analysis_id))
        write_index = lambda record: CIIndexManager.restore_record(workspace, analysis_id, record)
        recover_start(container, write_index=write_index)
        current = current_directory(container)
        manifest_path = current / 'manifest.json'
        old = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
        if old.get('source_document_sha256') and old['source_document_sha256'] != digest:
            raise ValueError('文档标识前缀冲突，已保留原运行，不能复用或覆盖')
        target = normalize_homework_target_stage(data.get('homework_target_stage'))
        rerun_plan = None
        if rerun:
            from .feedback_rerun_plan import choose_rerun_runtime
            runtime, rerun_plan = choose_rerun_runtime(current, filename, data, workspace=workspace)
            target = 'grading' if rerun_plan['stage'] == 'all' else rerun_plan['stage']
            resolution['warnings'].extend(rerun_plan['warnings'])
        else:
            runtime = build_request_runtime(resolution['feedback_context'], data,
                                            preprocess_mode=data.get('preprocess_mode'), workspace=workspace)
        state = read_feedback_snapshot(current, old)
        same = state['snapshot_status'] == 'complete' and state['config_fingerprint'] == runtime.fingerprint
        if same:
            runtime = restore_feedback_runtime(current)
        task_id = 'ci_task_' + uuid.uuid4().hex
        run_id = 'p03_' + uuid.uuid4().hex
        task = {'task_id': task_id, '_ci_principal': workspace, '_ci_workspace': workspace,
                'analysis_id': analysis_id, 'run_id': run_id, 'source_document_sha256': digest,
                'config_fingerprint': runtime.fingerprint, 'files': [filename],
                'task_kind': 'homework_grading', 'analysis_type': 'homework_grading',
                'current_item': 0, 'total_items': 0, 'current_section': '准备批改', 'error': '',
                'warnings': resolution['warnings'], 'content_validation': {'status': 'inconclusive'}}
        dependency_ready = True
        from .stage_dependencies import enabled as scoped_dependencies
        if same and scoped_dependencies(runtime):
            from .service import prepare_homework_workspace
            from .execution_checkpoints import receipt_matches
            previous_paths = prepare_homework_workspace(workspace, analysis_id, create=False)
            required = ['layout'] + (['understanding'] if target != 'layout' else []) + (['grading', 'render', 'quality'] if target == 'grading' else [])
            dependency_ready = all(receipt_matches(previous_paths, old, name) for name in required)
        if not rerun and same and dependency_ready and check_homework_stage_ready(workspace, analysis_id, target):
            completion = summarize_completion(old)
            task.update(run_id=old.get('run_id') or 'current', current_item=1, total_items=1,
                        completion=completion, current_section=completion['message'], completed=True, status='completed')
            global_var.tasks[task_id] = create_task(task)
            return {**_response(task, runtime, target, 'existing_result'), 'completion': completion}

        destination = run_directory(container, run_id)
        snapshot = prepare_feedback_snapshot(destination, source_path=str(source),
            analysis_id=analysis_id, expected_source_sha256=digest,
            context=runtime.context, **runtime.dependencies)
        configuration_clone = False
        if not same and state['snapshot_status'] == 'complete' and not rerun:
            from .stage_dependencies import reusable_upstream
            configuration_clone = reusable_upstream(restore_feedback_runtime(current), runtime)
        clone = rerun_plan['clone'] if rerun_plan is not None else same or configuration_clone
        if clone and (current / 'homework_grading').is_dir():
            _copy_homework_version_workspace(str(current / 'homework_grading'),
                                             str(destination / 'homework_grading'))
            from .artifact_transaction import recover_transaction
            recover_transaction(destination / 'homework_grading')
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        manifest = {**(old if clone else {}), **snapshot, 'run_id': run_id,
                    'source_page_count': source_page_count,
                    'username': workspace, 'selected_files': [filename], 'mode': 'single',
                    'scene_name': str(data.get('scene_name') or data.get('sceneName') or '').strip(),
                    'sub_scene_name': str(data.get('sub_scene_name') or data.get('subSceneName') or '').strip(),
                    'analysis_id': analysis_id,
                    'subject': runtime.context['subject_code'],
                    'subject_label': runtime.context['subject_name'],
                    'feedback_context': runtime.context, 'status': 'prepared',
                    'checkpoint_resume': bool(clone and (old.get('status') in RECOVERABLE
                                                or (rerun_plan or {}).get('resume'))),
                    'failure_stage': '', 'error': '', 'processing_stage': 'startup',
                    'created_at': now, 'updated_at': now, 'task_id': task_id, 'target_stage': target,
                    'completion': {'status': 'running', 'target_stage': target, 'report_usable': False,
                                   'issues': [], 'message': '批改任务正在执行。'}}
        atomic_json(destination / 'manifest.json', manifest)
        rerun_meta = {}
        if rerun_plan is not None:
            from .feedback_rerun_plan import prepare_rerun_workspace
            rerun_meta = prepare_rerun_workspace(destination, current, workspace, analysis_id,
                                                 runtime, rerun_plan, data)
        previous_index = CIIndexManager.find_by_id(workspace, analysis_id)
        new_index = {'analysis_id': analysis_id, 'mode': 'single', 'analysis_type': 'homework_grading',
                     'files': [filename], 'source_document_sha256': digest,
                     'status': 'running', 'run_id': run_id, 'task_id': task_id,
                     'homework_subject': runtime.context['subject_code'], 'created_at': now, 'updated_at': now}

        def worker():
            try:
                global_var.tasks[task_id].update(update_task(task_id, {'status': 'running'}))
                run_homework_grading(task_id, workspace, filename, analysis_id,
                    target_stage=target, preprocess_mode=runtime.dependencies['preprocessing']['mode'],
                    scope_page_nums=rerun_meta.get('scope_page_nums'),
                    force_preprocess_scope=rerun_meta.get('force_preprocess_scope', False),
                    feedback_runtime=runtime)
            except Exception as exc:
                update_task(task_id, {'status': 'failed', 'error': str(exc), 'failure_stage': 'execution'})
                CIIndexManager.update_status(workspace, analysis_id, 'failed')
            finally:
                try:
                    persisted = read_task(task_id)
                    if persisted and not persisted.get('completed'):
                        update_task(task_id, {'status': 'failed', 'error': '执行退出但未登记终态',
                                             'failure_stage': 'execution'})
                finally:
                    lease.release()

        def launch(record):
            global_var.tasks[task_id] = record
            threading.Thread(target=worker, name='ci-' + run_id, daemon=True).start()

        _, journal = publish_start(container, run_id, task, previous_index=previous_index,
            archive=lambda: archive_homework_run_if_exists(workspace, analysis_id, preserve_unrestorable=not clone),
            write_index=write_index, new_index=new_index, launch=launch)
        handed_off = True
        response = _response(task, runtime, target, 'success')
        if rerun_plan is not None:
            response.update(archived_run_id=journal.get('archived_run_id', ''),
                rerun_stage=rerun_plan['stage'], target_stage=target, resumed=rerun_plan['resume'],
                effective_session_ids=rerun_meta.get('effective_session_ids', []),
                remaining_session_ids=rerun_meta.get('remaining_session_ids', []),
                resume_available=bool(rerun_meta.get('resume_available')),
                red_blue_feedback_used=rerun_meta.get('red_blue_feedback_used', False))
        return response
    finally:
        if not handed_off:
            lease.release()
