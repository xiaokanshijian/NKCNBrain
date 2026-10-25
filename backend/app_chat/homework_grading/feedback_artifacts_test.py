import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from .feedback_artifacts import validate_artifacts, record_failure


class ArtifactTest(unittest.TestCase):
    def fixture(self, tmp):
        paths = {'manifest': str(Path(tmp) / 'manifest.json')}
        for name in ('pass1_json', 'raw', 'clean', 'annotated', 'annotated_layout', 'annotated_understanding', 'pass2_report'):
            path = Path(tmp) / name
            path.mkdir()
            paths[name] = str(path)
        for number in (1, 2):
            stem = f'synthetic_page{number}'
            for name in ('raw', 'clean', 'annotated', 'annotated_layout', 'annotated_understanding'):
                Image.new('RGB', (30, 30), 'white').save(Path(paths[name]) / (stem + '.png'))
            (Path(paths['pass1_json']) / (stem + '.json')).write_text(json.dumps({'questions': [{'id': '1'}] if number == 1 else []}))
        manifest = {'group_id': 'homework_synthetic', 'subject': 'unknown', 'processing_stage': 'report', 'config_fingerprint': 'a'*64}
        Path(paths['manifest']).write_text(json.dumps(manifest))
        report = Path(paths['pass2_report']) / 'unknown_syntheti_report.json'
        report.write_text('{"diagnosis":{"synthetic":true}}')
        pages = [{'page': n, 'clean_abs_path': str(Path(paths['clean']) / f'synthetic_page{n}.png')} for n in (1, 2)]
        return paths, pages, manifest, report

    def test_blank_page_is_reported_without_inventing_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths, pages, manifest, _ = self.fixture(tmp)
            warnings = validate_artifacts(paths, pages, manifest, 'grading', expected_pages=2)
            self.assertEqual(len(warnings), 1)
            self.assertIn('第2页', warnings[0])

    def test_missing_page_bad_json_missing_image_and_empty_report_fail(self):
        for defect in ('missing_page', 'bad_json', 'missing_image', 'empty_report', 'all_empty'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                paths, pages, manifest, report = self.fixture(tmp)
                if defect == 'missing_page':
                    pages.pop()
                elif defect == 'bad_json':
                    (Path(paths['pass1_json']) / 'synthetic_page1.json').write_text('{')
                elif defect == 'missing_image':
                    (Path(paths['annotated']) / 'synthetic_page1.png').unlink()
                elif defect == 'empty_report':
                    report.write_text('{}')
                else:
                    (Path(paths['pass1_json']) / 'synthetic_page1.json').write_text('{"questions":[]}')
                with self.assertRaises(ValueError):
                    validate_artifacts(paths, pages, manifest, 'grading', expected_pages=2)

    def test_failure_keeps_fingerprint_and_records_actual_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths, _, manifest, _ = self.fixture(tmp)
            self.assertEqual(record_failure(paths, ValueError('synthetic model failure')), 'report')
            saved = json.loads(Path(paths['manifest']).read_text())
            self.assertEqual(saved['config_fingerprint'], manifest['config_fingerprint'])
            self.assertEqual(saved['status'], 'failed')
            self.assertEqual(saved['failure_stage'], 'report')
