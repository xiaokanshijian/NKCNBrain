"""用户批准的P01历史保留策略；全部为临时合成工作区。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_chat.homework_grading import homework_versions as versions


class HistoryRetentionTest(unittest.TestCase):
    def make_history(self, root):
        root = Path(root)
        items = []
        for index in range(6):
            run = f'synthetic_{index}'
            target = root / '_archives' / run
            target.mkdir(parents=True)
            (target / 'manifest.json').write_text(json.dumps({'source': index}), encoding='utf-8')
            items.append({'run_id': run, 'is_key_version': index < 3})
        items.append({'run_id': 'missing_synthetic'})
        index_path = root / '_archives' / 'index.json'
        index_path.write_text(json.dumps({'versions': items}), encoding='utf-8')
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def assert_history_unchanged(self, root, before, include_index=True):
        for name, payload in before.items():
            if include_index or name != str(Path('_archives') / 'index.json'):
                self.assertEqual((Path(root) / name).read_bytes(), payload)

    def test_list_is_read_only_above_four(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(versions, '_analysis_root', return_value=root), \
                mock.patch.object(versions, '_container_root', return_value=root):
            before = self.make_history(root)
            with mock.patch.object(versions, '_save_archives_index', side_effect=AssertionError('list wrote index')):
                result = versions.list_homework_versions('synthetic', 'synthetic')
            self.assertEqual(len(result), 6)
            self.assert_history_unchanged(root, before)

    def test_archive_retains_all_history(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(versions, '_analysis_root', return_value=root), \
                mock.patch.object(versions, '_container_root', return_value=root):
            before = self.make_history(root)
            (Path(root) / 'homework_grading').mkdir()
            (Path(root) / 'manifest.json').write_text('{}', encoding='utf-8')
            run = versions.archive_homework_run_if_exists('synthetic', 'synthetic')
            self.assertTrue((Path(root) / '_archives' / run).is_dir())
            self.assert_history_unchanged(root, before, include_index=False)
            index = json.loads((Path(root) / '_archives' / 'index.json').read_text())
            self.assertEqual(len(index['versions']), 8)

    def test_key_limit_remains_but_never_prunes(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(versions, '_analysis_root', return_value=root), \
                mock.patch.object(versions, '_container_root', return_value=root):
            before = self.make_history(root)
            with self.assertRaisesRegex(ValueError, '最多只能设置 3'):
                versions.set_homework_version_key('synthetic', 'synthetic', 'synthetic_3', True)
            self.assert_history_unchanged(root, before)
            versions.set_homework_version_key('synthetic', 'synthetic', 'synthetic_0', False)
            versions.set_homework_version_key('synthetic', 'synthetic', 'synthetic_3', True)
            self.assert_history_unchanged(root, before, include_index=False)


if __name__ == '__main__':
    unittest.main()
