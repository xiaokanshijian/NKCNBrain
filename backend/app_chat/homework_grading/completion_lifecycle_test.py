"""从真实API函数到持久任务/快照/检查点的离线闭环，不启动真实模型。"""
import ast
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz
from app_chat import ci_test_support  # noqa: F401
from app_chat.ci_access import ci_access
from app_chat.ci.index_manager import CIIndexManager
from app_chat.ci.task_store import read_task, update_task
from django.http import JsonResponse
from django.test import RequestFactory, override_settings
from llm_langchain import global_var

from . import feedback_start_service as start
from . import service
from .completion_test import complete_manifest
from .execution_control import Execution, execution_scope
from .execution_checkpoints import checkpoint_key, save_checkpoint, load_checkpoint, stage_receipt
from .feedback_preprocess_test import runtime
from .feedback_start_service_test import InlineThread
from .feedback_workspaces import current_directory
from .utils import safe_json_load, safe_json_dump


def view(name):
    path = Path(__file__).parents[1] / 'views_continuous_image.py'
    node = next(n for n in ast.parse(path.read_text(encoding='utf-8')).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    namespace = {'json': json, 'os': os, 'JsonResponse': JsonResponse, 'global_var': global_var,
                 'is_homework_analysis_id': service.is_homework_analysis_id, '_safe_json_load': safe_json_load}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return ci_access(namespace[name])


class CompletionLifecycleTest(unittest.TestCase):
    def test_progress_detects_exit_and_public_resume_reuses_checkpoint_at_original_target(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(override_settings(BASE_DIR=tmp))
            stack.enter_context(patch.dict(global_var.tasks, {}, clear=True))
            frozen = runtime()
            source = Path(tmp) / 'received_dir/user_raw_file/synthetic_book/试卷.pdf'
            source.parent.mkdir(parents=True)
            with fitz.open() as pdf:
                pdf.new_page()
                pdf.save(source)
            container = Path(tmp) / 'document'
            stack.enter_context(patch('app_chat.homework_grading.homework_versions._container_root', return_value=str(container)))
            stack.enter_context(patch.object(start, 'build_request_runtime', return_value=frozen))
            leases = []
            lease_class = start.RunLease

            def acquire_reference(*args):
                lease = lease_class(*args)
                leases.append(lease)
                return lease

            stack.enter_context(patch.object(start, 'RunLease', side_effect=acquire_reference))
            thread = stack.enter_context(patch.object(start.threading, 'Thread'))
            # 模拟派发后进程消失：不执行worker；显式释放OS锁模拟进程退出。
            first = start.start_grading_request('synthetic_book', '试卷.pdf', {'homework_target_stage': 'understanding'},
                resolution={'route': 'homework_grading', 'feedback_context': frozen.context, 'warnings': []})
            original = current_directory(container)
            base = original / 'homework_grading'
            base.mkdir()
            messages = [{'role': 'user', 'content': 'synthetic checkpoint'}]
            with execution_scope(Execution(frozen, base)):
                key = checkpoint_key(messages, 'synthetic')
                save_checkpoint(key, {'confirmed': True})
            leases[0].release()
            global_var.tasks.clear()
            factory = RequestFactory()
            progress = json.loads(view('ci_progress')(factory.get('/'), task_id=first['task_id']).content)
            self.assertEqual(progress['status'], 'interrupted')
            self.assertTrue(progress['completed'])
            self.assertEqual(progress['completion']['status'], 'incomplete')
            self.assertEqual(safe_json_load(original / 'manifest.json')['status'], 'interrupted')

            def resume(task_id, workspace, filename, analysis_id, **kwargs):
                new = current_directory(container)
                manifest = safe_json_load(new / 'manifest.json')
                self.assertTrue(manifest['checkpoint_resume'])
                self.assertEqual(kwargs['target_stage'], 'understanding')
                self.assertEqual(kwargs['feedback_runtime'].fingerprint, frozen.fingerprint)
                with execution_scope(Execution(kwargs['feedback_runtime'], new / 'homework_grading', reuse=True)):
                    self.assertEqual(load_checkpoint(checkpoint_key(messages, 'synthetic'), lambda x: x), {'confirmed': True})
                update_task(task_id, {'completed': True})

            thread.side_effect = InlineThread
            stack.enter_context(patch.object(service, 'run_homework_grading', side_effect=resume))
            body = {'username': 'synthetic_book', 'analysis_id': first['analysis_id'],
                    'rerun_stage': 'understanding', 'resume': True}
            response = json.loads(view('ci_homework_rerun')(factory.post('/', body, content_type='application/json')).content)
            self.assertEqual(response['error_num'], 0, response.get('msg'))
            self.assertNotEqual(response['run_id'], first['run_id'])
            self.assertTrue((original / 'manifest.json').is_file())
            self.assertEqual(read_task(response['task_id'])['status'], 'completed')

    def test_task_reference_binds_workspace_analysis_run_and_source(self):
        from app_chat.ci.task_store import create_task
        from .feedback_task_recovery import task_reference
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=tmp):
            task = create_task({'task_id': 'ci_task_fixture', '_ci_workspace': 'book', '_ci_principal': 'book',
                'analysis_id': 'homework_fixture', 'run_id': 'p03_' + 'a' * 32,
                'source_document_sha256': 'b' * 64, 'config_fingerprint': 'c' * 64})
            manifest = {'task_id': task['task_id'], 'run_id': task['run_id'],
                        'source_document_sha256': task['source_document_sha256']}
            public, error = task_reference('book', task['analysis_id'], manifest, tmp)
            self.assertFalse(error)
            self.assertEqual(public['task_id'], task['task_id'])
            self.assertNotIn('_ci_principal', public)
            for workspace, analysis, candidate in [('other', task['analysis_id'], manifest),
                ('book', 'homework_other', manifest), ('book', task['analysis_id'], {**manifest, 'run_id': 'p03_' + 'd' * 32}),
                ('book', task['analysis_id'], {**manifest, 'source_document_sha256': 'd' * 64})]:
                public, error = task_reference(workspace, analysis, candidate, tmp)
                self.assertIsNone(public)
                self.assertTrue(error)

    def test_quality_api_success_and_failure_update_manifest_index_and_progress_without_grading(self):
        from . import feedback_quality_retry as retry
        from .feedback_quality_retry_test import QualityRetryTest
        from .feedback_artifacts_test import ArtifactTest
        for fails in (False, True):
            with self.subTest(fails=fails), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                root, frozen, manifest = QualityRetryTest().fixture(tmp, stack)
                stack.enter_context(patch.object(service, 'resolve_homework_run_root', return_value=str(root)))
                base = root / 'homework_grading'
                base.mkdir()
                paths, pages, _, _ = ArtifactTest().fixture(base)
                paths.update(base=str(base), root=str(root), manifest=str(root / 'manifest.json'))
                manifest.update(group_id='homework_synthetic', subject='unknown', source_page_count=2)
                manifest['stage_receipts'] = {'grading': stage_receipt(paths, 'grading', manifest['config_fingerprint'])}
                safe_json_dump(root / 'manifest.json', manifest)
                stack.enter_context(patch.object(retry.threading, 'Thread', InlineThread))
                stack.enter_context(patch.object(service, 'execute_staged_homework_grading', side_effect=AssertionError('不得重新批改')))
                scorer = stack.enter_context(patch.object(service, 'evaluate_homework_red_blue',
                    side_effect=TimeoutError('synthetic scoring timeout') if fails else None,
                    return_value={'status': 'ready', 'score': 4, 'color': 'purple'}))
                body = {'username': 'synthetic_book', 'analysis_id': 'homework_synthetic'}
                factory = RequestFactory()
                response = json.loads(view('ci_homework_red_blue_retry')(factory.post('/', body, content_type='application/json')).content)
                self.assertEqual(response['error_num'], 0, response.get('msg'))
                self.assertEqual(scorer.call_count, 1, read_task(response['task_id']).get('error'))
                saved = safe_json_load(root / 'manifest.json')
                self.assertEqual(saved['status'], 'partial' if fails else 'completed')
                self.assertEqual(saved['completion']['report_usable'], True)
                self.assertEqual(CIIndexManager.find_by_id('synthetic_book', 'homework_synthetic')['status'], saved['status'])
                self.assertEqual(saved['task_id'], response['task_id'])
                progress = json.loads(view('ci_progress')(factory.get('/'), task_id=response['task_id']).content)
                self.assertEqual(progress['error_num'], 0)
                self.assertTrue(progress['completed'])
                self.assertEqual(progress['completion'], saved['completion'])
                if fails:
                    scorer.side_effect = None
                    retried = json.loads(view('ci_homework_red_blue_retry')(factory.post('/', body, content_type='application/json')).content)
                    self.assertEqual(retried['error_num'], 0, retried.get('msg'))
                    self.assertNotEqual(retried['task_id'], response['task_id'])
                    self.assertEqual(safe_json_load(root / 'manifest.json')['completion']['status'], 'complete')
                    self.assertEqual(read_task(response['task_id'])['status'], 'failed', '旧失败任务仍保持终态')

    def test_historical_score_request_is_rejected_before_start(self):
        from . import feedback_quality_retry
        with patch.object(feedback_quality_retry, 'start_quality_retry') as launch:
            body = {'username': 'synthetic_book', 'analysis_id': 'homework_synthetic', 'run_id': 'archived'}
            response = view('ci_homework_red_blue_retry')(RequestFactory().post('/', body, content_type='application/json'))
            self.assertEqual(json.loads(response.content)['error_num'], 1)
            launch.assert_not_called()

    def test_history_completion_summary_is_read_only_and_uses_each_version(self):
        from . import homework_versions as versions
        from .feedback_snapshot_reader_test import write_snapshot_fixture
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=tmp), \
                patch.object(versions, '_analysis_root', return_value=tmp), \
                patch.object(versions, '_container_root', return_value=tmp):
            root = Path(tmp)
            current = write_snapshot_fixture(root)
            current.update(complete_manifest())
            safe_json_dump(root / 'manifest.json', current)
            archive = root / '_archives/synthetic_old'
            old = write_snapshot_fixture(archive)
            old.update(complete_manifest())
            old['red_blue_review'] = {'status': 'failed'}
            old['status'] = 'partial'
            safe_json_dump(archive / 'manifest.json', old)
            safe_json_dump(root / '_archives/index.json', {'versions': [{'run_id': 'synthetic_old'}]})
            before = {p: p.read_bytes() for p in root.rglob('*.json')}
            items = {x['run_id']: x for x in versions.list_homework_versions('synthetic', 'homework_fixture')}
            self.assertEqual(items['current']['completion']['status'], 'complete')
            self.assertEqual(items['synthetic_old']['completion']['status'], 'incomplete')
            self.assertEqual(items['synthetic_old']['red_blue_status'], 'failed')
            self.assertEqual({p: p.read_bytes() for p in before}, before)


if __name__ == '__main__':
    unittest.main()
