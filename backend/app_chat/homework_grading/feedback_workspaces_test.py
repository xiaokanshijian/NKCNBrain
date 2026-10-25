import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_chat.ci.file_io import atomic_json
from .feedback_workspaces import current_directory, publish_pointer, restore_pointer, run_directory


class WorkspacePointerTest(unittest.TestCase):
    def test_publish_failure_and_restore_keep_original_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / 'manifest.json'
            atomic_json(old, {'status': 'completed', 'legacy': True})
            run_id = 'p03_' + 'a'*32
            target = run_directory(tmp, run_id)
            atomic_json(target / 'manifest.json', {'status': 'prepared'})
            with patch('app_chat.ci.file_io.os.replace', side_effect=OSError('synthetic failure')):
                with self.assertRaises(OSError):
                    publish_pointer(tmp, run_id)
            self.assertEqual(current_directory(tmp), Path(tmp))
            publish_pointer(tmp, run_id)
            self.assertEqual(current_directory(tmp), target)
            restore_pointer(tmp, None)
            self.assertEqual(current_directory(tmp), Path(tmp))
            self.assertTrue(old.is_file())
            self.assertTrue((target / 'manifest.json').is_file())

    def test_missing_run_and_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                publish_pointer(tmp, 'p03_' + 'b'*32)
            with self.assertRaises(ValueError):
                run_directory(tmp, '../old')

    def test_switched_runs_share_history_container_and_keep_more_than_four(self):
        from . import homework_versions as versions
        with tempfile.TemporaryDirectory() as tmp, patch.object(versions, '_container_root', return_value=tmp):
            for n in range(6):
                if n:
                    self.assertIsNotNone(versions.archive_homework_run_if_exists('synthetic', 'synthetic'))
                run_id = 'p03_' + format(n, '032x')
                directory = run_directory(tmp, run_id)
                atomic_json(directory / 'manifest.json', {'status': 'completed', 'subject': 'unknown'})
                (directory / 'homework_grading').mkdir()
                publish_pointer(tmp, run_id)
            listed = versions.list_homework_versions('synthetic', 'synthetic')
            self.assertEqual(len(listed), 6)
            for item in listed:
                resolved = Path(versions.resolve_homework_run_root('synthetic', 'synthetic', item['run_id']))
                self.assertTrue((resolved / 'manifest.json').is_file())
                if not item['is_current']:
                    self.assertEqual(resolved.parent, Path(tmp) / '_archives')
