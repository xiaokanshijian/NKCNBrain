import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_chat.homework_grading.complex_glyph_description_experiment import (
    C_DESCRIPTION_SYSTEM_PROMPT,
    EXPERIMENT_MODE,
    build_c_description_messages,
    evaluate,
    normalize_c_description_response,
    request_audit,
    _run_one,
)


class ComplexGlyphDescriptionExperimentTest(unittest.TestCase):
    def test_request_is_visual_only_and_does_not_accept_business_object(self):
        messages = build_c_description_messages('data:image/png;base64,AAAA')
        payload = json.dumps(messages, ensure_ascii=False)
        for forbidden in ('student_answer', 'correct_answer', 'verdict', 'target_slot', 'target_char'):
            self.assertNotIn(forbidden, payload)
        self.assertIn('不要判断对错', C_DESCRIPTION_SYSTEM_PROMPT)
        audit = request_audit(messages, 'sha')
        self.assertTrue(audit['business_text_leakage_free'])
        self.assertEqual(audit['image_count'], 1)

    def test_schema_requires_description_only_for_nonstandard_glyph(self):
        normalized = normalize_c_description_response(json.dumps({
            'slots': [
                {'index': 1, 'status': 'nonstandard', 'recognized_char': '', 'visual_description': '右下有独立的鸟形结构'},
                {'index': 2, 'status': 'recognized', 'recognized_char': '萝', 'visual_description': ''},
            ],
        }, ensure_ascii=False))
        self.assertEqual(normalized['slots'][0]['status'], 'nonstandard')
        for invalid in (
            {'slots': [{'index': 1, 'status': 'nonstandard', 'recognized_char': '藤', 'visual_description': '右下有结构'}]},
            {'slots': [{'index': 1, 'status': 'recognized', 'recognized_char': '藤', 'visual_description': '描述'}]},
            {'slots': [{'index': 2, 'status': 'blank', 'recognized_char': '', 'visual_description': ''}]},
            'not json',
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    raw = invalid if isinstance(invalid, str) else json.dumps(invalid, ensure_ascii=False)
                    normalize_c_description_response(raw)

    def test_only_format_errors_retry_and_raw_response_is_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crop = root / 'crop.png'
            crop.write_bytes(b'not-a-real-image')
            prepared = {'crop_path': str(crop), 'crop_sha256': 'sha'}
            calls = []

            def fake_call(_messages):
                calls.append(1)
                return 'not json' if len(calls) == 1 else json.dumps({
                    'slots': [
                        {'index': 1, 'status': 'nonstandard', 'recognized_char': '', 'visual_description': '右下有独立形状'},
                    ],
                }, ensure_ascii=False)

            with mock.patch(
                'app_chat.homework_grading.complex_glyph_description_experiment.image_to_data_uri_for_gemini_review',
                return_value='data:image/png;base64,AAAA',
            ):
                result = _run_one(prepared, root / 'out', 1, {'used': 0}, fake_call)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(len(calls), 2)
            self.assertEqual(result['attempts'][0]['raw_response'], 'not json')

    def test_evaluation_uses_label_only_after_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'case.json'
            path.write_text(json.dumps({
                'experiment_mode': EXPERIMENT_MODE,
                'case': {'evaluation': {'target_index': 1, 'target_expected_char': '藤'}},
            }, ensure_ascii=False), encoding='utf-8')
            results = [
                {
                    'status': 'completed',
                    'normalized_response': {'slots': [
                        {'index': 1, 'status': 'nonstandard', 'recognized_char': '', 'visual_description': '右下有鸟形结构'},
                    ]},
                    'request_audit': {'business_text_leakage_free': True},
                }
                for _ in range(3)
            ]
            evaluation = evaluate(path, results)
        self.assertTrue(evaluation['passed'])
        self.assertEqual(evaluation['nonstandard_description_runs'], 3)


if __name__ == '__main__':
    unittest.main()
