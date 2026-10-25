import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .feedback_observation import collect_observation, observe_records, update_runtime_observation
from .feedback_preprocess_test import runtime


class ObservationTest(unittest.TestCase):
    def test_detect_suffix_and_invalid_pages_do_not_inflate_coverage(self):
        context = runtime().context
        records = [{'page': n, 'text': '九年级'} for n in (0, 1, 2, 3, 4, 5, 6, 7, 8)]
        result = observe_records(records, context, expected_pages=7)
        self.assertEqual(result['coverage']['pages'], list(range(1, 8)))
        self.assertTrue(result['coverage']['complete'])
        self.assertIsNone(result['evidence'][0]['page'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'math_fixture_page5.detect.json'
            path.write_text(json.dumps({'page_header': '九年级'}), encoding='utf-8')
            with patch('app_chat.homework_grading.sessions._find_ocr_markdown', return_value=''):
                result = collect_observation('', context, pass1_dir=tmp, expected_pages=7)
            self.assertEqual(result['coverage']['pages'], [5])

    def test_missing_grade_is_not_conflict_and_explicit_conflict_has_evidence(self):
        context = runtime().context
        before = copy.deepcopy(context)
        missing = observe_records([{'text': '第一题 说明中断响应过程', 'page': 1}], context, expected_pages=6)
        self.assertEqual(missing['status'], 'inconclusive')
        result = observe_records([{'text': '学段：大学 年级：大三 课程：嵌入式系统',
                                  'page': 2, 'source': 'page_header', 'source_sha256': 'a'*64}], context, expected_pages=6)
        self.assertEqual(result['status'], 'conflict')
        self.assertIn('grade', result['conflict_fields'])
        self.assertEqual(result['coverage']['pages'], [2])
        self.assertFalse(result['coverage']['complete'])
        self.assertTrue(result['evidence'])
        self.assertEqual(context, before)

    def test_timeout_and_bad_json_are_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'fixture.pdf'
            source.write_bytes(b'synthetic')
            (Path(tmp) / 'fixture_ocr.md').write_text('学段：大学 年级：大二', encoding='utf-8')
            result = collect_observation(source, runtime().context, budget_seconds=0)
            self.assertEqual(result['status'], 'inconclusive')
            self.assertTrue(result['warnings'])
            (Path(tmp) / 'page_001.detect.json').write_text('{')
            result = collect_observation(source, runtime().context, pass1_dir=tmp)
            self.assertEqual(result['status'], 'inconclusive')
            self.assertTrue(result['warnings'])

    def test_storing_observation_never_changes_snapshots_or_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {'manifest': str(Path(tmp)/'manifest.json'), 'pass1_json': tmp}
            frozen = runtime()
            manifest = {'config_fingerprint': frozen.fingerprint, 'feedback_context': frozen.context}
            with patch('app_chat.ci._utils._update_task') as update:
                update_runtime_observation('synthetic', paths, manifest, '', frozen, 6)
            saved = json.loads(Path(paths['manifest']).read_text(encoding='utf-8'))
            self.assertEqual(saved['feedback_context'], frozen.context)
            self.assertEqual(saved['config_fingerprint'], frozen.fingerprint)
            self.assertEqual(saved['content_validation']['status'], 'inconclusive')
            self.assertEqual(update.call_args.kwargs['content_validation'], saved['content_validation'])
