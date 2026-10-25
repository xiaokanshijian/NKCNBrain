"""P01-06b合成索引故障注入，绝不访问真实历史工作区。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_chat.homework_grading import homework_versions as versions


class AtomicIndexTest(unittest.TestCase):
    def test_failures_preserve_original_bytes(self):
        for point in ('serialization', 'write', 'replace', 'validate'):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as root, mock.patch.object(versions, '_analysis_root', return_value=root):
                parent = Path(root) / '_archives'
                parent.mkdir()
                path = parent / 'index.json'
                original = b'{"versions": [{"run_id": "keep"}]}'
                path.write_bytes(original)
                value = {'versions': [{'run_id': 'new'}]}
                if point == 'serialization':
                    value['bad'] = object()
                    patch = mock.patch.object(versions.os, 'replace', side_effect=AssertionError('must not publish'))
                elif point == 'write':
                    patch = mock.patch.object(versions.json, 'dump', side_effect=OSError('synthetic write failed'))
                elif point == 'replace':
                    patch = mock.patch.object(versions.os, 'replace', side_effect=OSError('synthetic replace failed'))
                else:
                    patch = mock.patch.object(versions, 'safe_json_load', return_value={'versions': []})
                with patch, self.assertRaises((TypeError, OSError, ValueError)):
                    versions._save_archives_index('fixture', 'fixture', value)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(json.loads(path.read_bytes())['versions'][0]['run_id'], 'keep')
                self.assertEqual(sorted(p.name for p in parent.iterdir()), ['index.json'])

    def test_success_and_invalid_index_type(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(versions, '_analysis_root', return_value=root):
            value = {'versions': [{'run_id': 'synthetic', 'label': '合成版本'}]}
            versions._save_archives_index('fixture', 'fixture', value)
            self.assertEqual(versions._load_archives_index('fixture', 'fixture'), value)
            with self.assertRaises(ValueError):
                versions._save_archives_index('fixture', 'fixture', {'versions': 'wrong'})
            self.assertEqual(versions._load_archives_index('fixture', 'fixture'), value)


if __name__ == '__main__':
    unittest.main()
