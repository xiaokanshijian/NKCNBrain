"""真实文件写入故障注入，仅使用临时目录。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .utils import safe_json_dump, safe_json_load


class AtomicArtifactsTest(unittest.TestCase):
    def test_serialization_and_nonfinite_failure_preserve_previous_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'中文结果.json'
            safe_json_dump(path, {'原结果': '有效'})
            before = path.read_bytes()
            for invalid in ({'bad': object()}, {'bad': float('nan')}):
                with self.assertRaises((TypeError, ValueError)):
                    safe_json_dump(path, invalid)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(list(Path(tmp).glob('*.tmp')), [])

    def test_partial_write_and_replace_failure_leave_old_result_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'report.json'
            safe_json_dump(path, {'valid': True})

            def fail_mid_write(data, handle, **kwargs):
                handle.write('{"partial":')
                raise OSError('synthetic disk failure')

            for target, failure in [('json.dump', fail_mid_write), ('os.replace', OSError('synthetic replace failure'))]:
                with patch('app_chat.ci.file_io.' + target, side_effect=failure):
                    with self.assertRaises(OSError):
                        safe_json_dump(path, {'replacement': True})
                self.assertEqual(safe_json_load(path), {'valid': True})
                self.assertEqual(list(Path(tmp).glob('*.tmp')), [])
            safe_json_dump(path, {'new': '正常'})
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'new': '正常'})


if __name__ == '__main__':
    unittest.main()
