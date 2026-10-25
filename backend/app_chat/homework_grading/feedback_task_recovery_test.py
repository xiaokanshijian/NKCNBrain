import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_chat import ci_test_support  # noqa: F401
from django.test import override_settings
from app_chat.ci.task_store import create_task, read_task
from app_chat.ci.task_store_test import TaskStoreTest
from .feedback_task_recovery import recover_abandoned_task
from .feedback_start_service import RunLease


class RecoveryTest(unittest.TestCase):
    def test_running_lock_prevents_false_interruption_after_memory_loss(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=tmp), \
                patch('app_chat.homework_grading.homework_versions._container_root', return_value=tmp):
            task = create_task(TaskStoreTest().record())
            lease = RunLease(task['_ci_workspace'], task['source_document_sha256']).acquire()
            try:
                self.assertFalse(recover_abandoned_task(task)['completed'])
            finally:
                lease.release()
            recovered = recover_abandoned_task(task)
            self.assertEqual(recovered['status'], 'interrupted')
            self.assertTrue(recovered['completed'])
            self.assertTrue(recovered['error'])
            self.assertEqual(read_task(task['task_id']), recovered)

    def test_quality_interruption_keeps_report_but_marks_delivery_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=tmp), \
                patch('app_chat.homework_grading.homework_versions._container_root', return_value=tmp), \
                patch('app_chat.homework_grading.homework_versions.resolve_homework_run_root', return_value=tmp):
            task = create_task(dict(TaskStoreTest().record(), task_kind='homework_red_blue_review'))
            path = Path(tmp) / 'manifest.json'
            original = {'status': 'completed', 'config_fingerprint': task['config_fingerprint'], 'feedback_context': {'synthetic': True}}
            path.write_text(json.dumps(original), encoding='utf-8')
            self.assertEqual(recover_abandoned_task(task)['status'], 'interrupted')
            saved = json.loads(path.read_text(encoding='utf-8'))
            for key, value in original.items():
                if key != 'status':
                    self.assertEqual(saved[key], value)
            self.assertEqual(saved['status'], 'partial')
            self.assertEqual(saved['completion']['status'], 'incomplete')
            self.assertEqual(saved['red_blue_review']['status'], 'failed')
