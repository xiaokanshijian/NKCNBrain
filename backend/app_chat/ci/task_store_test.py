import tempfile
import unittest
from unittest.mock import patch

from app_chat import ci_test_support  # noqa: F401
from .task_store import create_task, read_task, update_task


class TaskStoreTest(unittest.TestCase):
    def test_progress_bridge_persists_observation_and_failure_stage(self):
        from ._utils import _update_task, global_var
        with tempfile.TemporaryDirectory() as tmp, patch('app_chat.ci.task_store.runtime_root', return_value=tmp), \
                patch.dict(global_var.tasks, {}, clear=True):
            record = create_task(self.record())
            global_var.tasks[record['task_id']] = record
            _update_task(record['task_id'], content_validation={'status': 'inconclusive'},
                         warnings=['合成观察告警'], failure_stage='quality', completed=True, error='合成失败')
            saved = read_task(record['task_id'])
            self.assertEqual(saved['content_validation']['status'], 'inconclusive')
            self.assertEqual(saved['failure_stage'], 'quality')
            self.assertEqual(saved['status'], 'failed')
            self.assertEqual(saved['config_fingerprint'], record['config_fingerprint'])

    def record(self):
        return {'task_id': 'ci_task_synthetic', '_ci_principal': 'synthetic-owner',
                '_ci_workspace': 'synthetic-owner_notebook', 'analysis_id': 'homework_' + 'a'*24,
                'run_id': 'synthetic-run', 'source_document_sha256': 'a'*64,
                'config_fingerprint': 'b'*64}

    def test_roundtrip_terminal_and_immutable_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = create_task(self.record(), root=tmp)
            self.assertEqual(read_task(original['task_id'], root=tmp), original)
            with self.assertRaises(ValueError):
                update_task(original['task_id'], {'_ci_principal': 'other'}, root=tmp)
            update_task(original['task_id'], {'status': 'interrupted', 'error': '进程已中断'}, root=tmp)
            final = update_task(original['task_id'], {'status': 'running', 'completed': False}, root=tmp)
            self.assertEqual(final['status'], 'interrupted')
            self.assertTrue(final['completed'])
            self.assertEqual(final['config_fingerprint'], 'b'*64)
            with self.assertRaises(FileExistsError):
                create_task(self.record(), root=tmp)

    def test_invalid_id_cannot_escape_and_missing_is_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_task('ci_task_missing', root=tmp))
            with self.assertRaises(ValueError):
                read_task('../task', root=tmp)

    def test_progress_uses_durable_workspace_without_memory_cache(self):
        from django.test import RequestFactory
        from django.http import JsonResponse
        from app_chat import ci_access
        with tempfile.TemporaryDirectory() as tmp:
            original = create_task(self.record(), root=tmp)
            with patch('app_chat.ci.task_store.runtime_root', return_value=tmp), \
                 patch.object(ci_access, '_tasks', return_value={}):
                seen = {}

                def view(request, **kwargs):
                    seen['workspace'] = request.ci_workspace
                    seen['task'] = request.ci_task
                    return JsonResponse({'error_num': 0})

                wrapped = ci_access.ci_access(view)
                response = wrapped(RequestFactory().get('/api/ci/progress/', {'username': 'other'}),
                                   task_id=original['task_id'])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(seen['workspace'], 'synthetic-owner_notebook')
                self.assertEqual(seen['task']['_ci_principal'], 'synthetic-owner')
