import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app_chat.ci.file_io import atomic_json
from app_chat.ci.task_store import read_task
from . import feedback_start_transaction as transaction
from .feedback_preprocess_test import runtime
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .feedback_workspaces import current_directory, run_directory


class StartTransactionTest(unittest.TestCase):
    def prepare(self, tmp):
        container = Path(tmp) / 'document'
        atomic_json(container / 'manifest.json', {'status': 'completed', 'legacy': True})
        frozen = runtime()
        args = snapshot_arguments(tmp)
        args.update(context=frozen.context, **frozen.dependencies)
        run_id = 'p03_' + 'a'*32
        prepare_feedback_snapshot(run_directory(container, run_id), **args)
        task = {'task_id': 'ci_task_synthetic', '_ci_principal': 'synthetic',
                '_ci_workspace': 'synthetic_book', 'analysis_id': args['analysis_id'],
                'run_id': run_id, 'source_document_sha256': args['expected_source_sha256'],
                'config_fingerprint': frozen.fingerprint, 'files': ['synthetic-source.pdf']}
        return container, run_id, task

    def test_failure_at_each_publish_stage_keeps_old_current(self):
        for stage in ('archive', 'register', 'pointer', 'index', 'thread'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                container, run_id, task = self.prepare(tmp)
                old = {'analysis_id': task['analysis_id'], 'status': 'completed'}
                current_index = [old]

                def write_index(value):
                    if stage == 'index' and value.get('status') == 'running':
                        raise OSError('synthetic index publish failure')
                    current_index[0] = value

                failure = Mock(side_effect=OSError('synthetic ' + stage))
                patcher = (patch.object(transaction, 'create_task', failure) if stage == 'register' else
                           patch.object(transaction, 'publish_pointer', failure) if stage == 'pointer' else
                           patch.object(transaction, 'JOURNAL', transaction.JOURNAL))
                with patcher, self.assertRaises(OSError):
                    transaction.publish_start(container, run_id, task, previous_index=old,
                        archive=failure if stage == 'archive' else lambda: 'synthetic-archive',
                        write_index=write_index, new_index=dict(old, status='running'),
                        launch=failure if stage == 'thread' else Mock(), task_root=tmp)
                self.assertEqual(current_directory(container), container)
                self.assertEqual(current_index[0], old)
                self.assertTrue((run_directory(container, run_id) / 'manifest.json').is_file())

    def test_dispatch_after_registration_and_recover_interrupted_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            container, run_id, task = self.prepare(tmp)
            index = []

            def launch(record):
                self.assertEqual(read_task(record['task_id'], root=tmp), record)
                self.assertEqual(current_directory(container), run_directory(container, run_id))
                self.assertEqual(index[-1]['status'], 'running')
                raise KeyboardInterrupt('synthetic process interruption')

            with self.assertRaises(KeyboardInterrupt):
                transaction.publish_start(container, run_id, task, previous_index=None,
                    archive=lambda: None, write_index=index.append,
                    new_index={'analysis_id': task['analysis_id'], 'status': 'running'},
                    launch=launch, task_root=tmp)
            result = transaction.recover_start(container, write_index=index.append, task_root=tmp)
            self.assertEqual(result['phase'], 'interrupted')
            self.assertEqual(read_task(task['task_id'], root=tmp)['status'], 'interrupted')
            self.assertEqual(current_directory(container), run_directory(container, run_id))
            self.assertTrue((container / 'manifest.json').is_file())
