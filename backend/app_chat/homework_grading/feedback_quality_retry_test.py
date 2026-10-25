import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from app_chat import ci_test_support  # noqa: F401
from django.test import override_settings

from . import feedback_quality_retry as retry
from .feedback_preprocess_test import runtime
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .feedback_start_service_test import InlineThread
from .completion_test import complete_manifest
from app_chat.ci.task_store import read_task, update_task
from app_chat.ci.file_io import FileLockBusy


class QualityRetryTest(unittest.TestCase):
    def test_scoring_preserves_material_index_identity(self):
        from app_chat.ci.index_manager import CIIndexManager
        from app_chat.ci.orchestrator import query_ci_analyses
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, _, manifest = self.fixture(tmp, stack)
            source = Path(tmp) / 'received_dir/user_raw_file/synthetic_book/试卷.pdf'
            source.parent.mkdir(parents=True)
            # snapshot_arguments creates the original synthetic PDF at this location.
            original = Path(snapshot_arguments(tmp)['source_path'])
            source.write_bytes(original.read_bytes())
            CIIndexManager.add_or_update('synthetic_book', {'analysis_id': 'homework_fixture',
                'analysis_type': 'homework_grading', 'mode': 'single', 'files': ['试卷.pdf'],
                'source_document_sha256': manifest['source_document_sha256'], 'created_at': 'synthetic-original'})
            stack.enter_context(patch.object(retry.threading, 'Thread', InlineThread))
            stack.enter_context(patch('app_chat.homework_grading.service.run_homework_red_blue_review',
                side_effect=lambda task_id, *a, **kw: update_task(task_id, {'completed': True})))
            retry.start_quality_retry('synthetic_book', 'homework_fixture')
            saved = CIIndexManager.find_by_id('synthetic_book', 'homework_fixture')
            self.assertEqual(saved['created_at'], 'synthetic-original')
            self.assertEqual(saved['source_document_sha256'], manifest['source_document_sha256'])
            self.assertEqual(query_ci_analyses('synthetic_book', ['试卷.pdf'])['singles'][0]['analysis_id'], 'homework_fixture')

    def test_version_switch_before_lease_recheck_never_scores_new_version(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, _, manifest = self.fixture(tmp, stack)
            acquire = retry.RunLease.acquire
            def switch(lease):
                held = acquire(lease)
                changed = dict(manifest, run_id='p03_' + 'b' * 32)
                (root / 'manifest.json').write_text(json.dumps(changed), encoding='utf-8')
                return held
            stack.enter_context(patch.object(retry.RunLease, 'acquire', switch))
            runner = stack.enter_context(patch('app_chat.homework_grading.service.run_homework_red_blue_review'))
            with self.assertRaisesRegex(ValueError, '当前版本已变化'):
                retry.start_quality_retry('synthetic_book', 'homework_fixture')
            runner.assert_not_called()

    def fixture(self, tmp, stack):
        stack.enter_context(override_settings(BASE_DIR=tmp))
        frozen = runtime()
        root = Path(tmp) / 'run'
        args = snapshot_arguments(tmp)
        args.update(context=frozen.context, **frozen.dependencies)
        prepare_feedback_snapshot(root, **args)
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        manifest.update(complete_manifest())
        manifest.update(run_id='p03_' + 'a' * 32, selected_files=['试卷.pdf'], red_blue_review={'status': 'failed'})
        (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        stack.enter_context(patch('app_chat.homework_grading.homework_versions.resolve_homework_run_root', return_value=str(root)))
        stack.enter_context(patch.object(retry, 'saved_report_ready', return_value=True))
        return root, frozen, manifest

    def test_original_basis_and_shared_run_lock(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, frozen, manifest = self.fixture(tmp, stack)
            stack.enter_context(patch.object(retry.threading, 'Thread', InlineThread))
            def run(task_id, *args, **kwargs):
                record = read_task(task_id)
                self.assertEqual(record['_ci_principal'], 'synthetic_book')
                self.assertEqual(kwargs['feedback_runtime'].fingerprint, frozen.fingerprint)
                self.assertEqual(kwargs['run_id'], manifest['run_id'])
                with self.assertRaises(FileLockBusy):
                    retry.RunLease('synthetic_book', manifest['source_document_sha256']).acquire()
                update_task(task_id, {'completed': True})
            runner = stack.enter_context(patch('app_chat.homework_grading.service.run_homework_red_blue_review', side_effect=run))
            with patch('app_chat.homework_grading.feedback_runtime_service.execution_configuration', side_effect=AssertionError('不得重新读取配置')):
                result = retry.start_quality_retry('synthetic_book', 'homework_fixture')
            self.assertEqual(read_task(result['task_id'])['status'], 'completed')
            runner.assert_called_once()
            retry.RunLease('synthetic_book', manifest['source_document_sha256']).acquire().release()
            (root / 'skill_snapshot.json').write_text('{}')
            with self.assertRaises(ValueError):
                retry.start_quality_retry('synthetic_book', 'homework_fixture')
            self.assertEqual(runner.call_count, 1)

    def test_thread_start_failure_persists_terminal_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            _, _, manifest = self.fixture(tmp, stack)
            thread = stack.enter_context(patch.object(retry.threading, 'Thread'))
            thread.return_value.start.side_effect = RuntimeError('synthetic thread failure')
            with self.assertRaises(RuntimeError):
                retry.start_quality_retry('synthetic_book', 'homework_fixture')
            records = list((Path(tmp) / 'received_dir/.ci_runtime/tasks').glob('*.json'))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text(encoding='utf-8'))
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['failure_stage'], 'startup')
            retry.RunLease('synthetic_book', manifest['source_document_sha256']).acquire().release()

    def test_worker_entry_failure_does_not_leave_pending_quality(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, _, _ = self.fixture(tmp, stack)
            stack.enter_context(patch.object(retry.threading, 'Thread', InlineThread))
            stack.enter_context(patch('app_chat.homework_grading.service.run_homework_red_blue_review',
                                      side_effect=RuntimeError('synthetic worker entry failure')))
            response = retry.start_quality_retry('synthetic_book', 'homework_fixture')
            record = read_task(response['task_id'])
            saved = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(saved['red_blue_review']['status'], 'failed')
            self.assertEqual(saved['status'], 'partial')
            self.assertTrue(saved['completion']['report_usable'])
