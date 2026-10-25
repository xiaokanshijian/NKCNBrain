"""P01版本摘要临时fixture验证。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_chat.homework_grading import homework_versions as versions
from app_chat.homework_grading.feedback_snapshot_reader_test import write_snapshot_fixture


class VersionSummaryTest(unittest.TestCase):
    def test_each_version_uses_own_context_and_keeps_legacy_fields(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(versions, '_analysis_root', return_value=root):
            current = write_snapshot_fixture(root)
            current['updated_at'] = '2026-09-09T12:00:00'
            (Path(root) / 'manifest.json').write_text(json.dumps(current), encoding='utf-8')
            archive = Path(root) / '_archives' / 'synthetic_old'
            write_snapshot_fixture(archive, '大学·大一·高等数学·笔记.pdf')
            legacy = Path(root) / '_archives' / 'legacy'
            legacy.mkdir()
            (legacy / 'manifest.json').write_text('{"grade":4}', encoding='utf-8')
            (Path(root) / '_archives' / 'index.json').write_text(json.dumps({'versions': [
                {'run_id': 'synthetic_old', 'is_key_version': True, 'archived_at': 'synthetic-time'},
                {'run_id': 'legacy', 'is_key_version': False}]}), encoding='utf-8')
            result = {item['run_id']: item for item in versions.list_homework_versions('fixture', 'fixture')}
            self.assertEqual(result['current']['feedback_context']['education_level'], 'junior')
            self.assertEqual(result['synthetic_old']['feedback_context']['education_level'], 'university')
            self.assertEqual(result['current']['created_at'], current['updated_at'])
            self.assertTrue(result['synthetic_old']['is_key_version'])
            self.assertEqual(result['synthetic_old']['created_at'], 'synthetic-time')
            self.assertIn('red_blue_status', result['current'])
            self.assertNotIn('declared_metadata', result['current']['feedback_context'])
            self.assertNotIn('reference_text', json.dumps(result))
            self.assertEqual(result['legacy']['snapshot_status'], 'legacy_missing')
            self.assertIsNone(result['legacy']['feedback_context'])
            (archive / 'curriculum_snapshot.json').unlink()
            result = {item['run_id']: item for item in versions.list_homework_versions('fixture', 'fixture')}
            self.assertEqual(result['synthetic_old']['snapshot_status'], 'missing')
            self.assertEqual(result['current']['snapshot_status'], 'complete')


if __name__ == '__main__':
    unittest.main()
