"""验证独立运行目录下超过 Windows MAX_PATH 的报告写入与消费者读取。"""
import os
import tempfile
import unittest
from pathlib import Path

from .utils import safe_json_dump, safe_json_load, windows_io_path
from .service import _safe_load_or_default
from .red_blue_review import _load_optional


class LongReportPathTest(unittest.TestCase):
    def test_report_round_trip_and_consumers(self):
        root = tempfile.mkdtemp(prefix='p03-long-report-')
        directory = Path(root) / ('run_' + 'a' * 90) / ('reports_' + 'b' * 90)
        report = str(directory / 'math_fixture_answer_statement_verification.json')
        self.assertGreater(len(os.path.abspath(report)), 260)
        value = {'total_discrepancies': 0, 'checks': [], 'public_checks': 'executed'}
        try:
            safe_json_dump(report, value)
            self.assertEqual(safe_json_load(report), value)
            self.assertEqual(_safe_load_or_default(report, {}), value)
            self.assertEqual(_load_optional(report), value)
            self.assertEqual(_load_optional(report + '.missing'), {})
        finally:
            if os.path.isfile(windows_io_path(report)):
                os.remove(windows_io_path(report))
            for folder in (directory, directory.parent, Path(root)):
                if os.path.isdir(windows_io_path(folder)):
                    os.rmdir(windows_io_path(folder))
