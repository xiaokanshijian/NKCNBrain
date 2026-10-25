import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_chat.homework_grading.blind_pinyin_review_experiment import (
    BLIND_TRANSCRIPTION_SYSTEM_PROMPT,
    EXPERIMENT_MODE,
    build_arg_parser,
    build_blind_messages,
    evaluate_results,
    normalize_blind_response,
    prepare_cases,
    request_audit,
    run_blind_calls,
)


class BlindPinyinReviewExperimentTest(unittest.TestCase):
    def test_blind_request_has_no_business_text_or_mode_switch(self):
        sentinels = ('__student_answer_sentinel__', '__correct_answer_sentinel__', '__verdict_sentinel__')
        messages = build_blind_messages('data:image/png;base64,AAAA')
        payload = json.dumps(messages, ensure_ascii=False)
        for sentinel in sentinels:
            self.assertNotIn(sentinel, payload)
        self.assertNotIn('correct_answer', payload)
        self.assertNotIn('student_answer', payload)
        self.assertNotIn('target_slot', payload)
        self.assertIn('不要判断对错', BLIND_TRANSCRIPTION_SYSTEM_PROMPT)

        parser = build_arg_parser()
        option_names = {option.dest for option in parser._actions}
        self.assertNotIn('mode', option_names)
        self.assertNotIn('legacy', payload.lower())
        self.assertNotIn('confirmation', payload.lower())

        audit = request_audit(messages, 'abc')
        self.assertTrue(audit['business_text_leakage_free'])
        self.assertEqual(audit['image_count'], 1)

    def test_normalize_response_requires_ordered_unicode_slots(self):
        result = normalize_blind_response(json.dumps({
            'slots': [
                {'index': 1, 'status': 'recognized', 'recognized_char': '藤'},
                {'index': 2, 'status': 'nonstandard', 'recognized_char': ''},
            ],
        }, ensure_ascii=False))
        self.assertEqual(result['slots'][0]['recognized_char'], '藤')

        for raw in (
            {'slots': [{'index': 2, 'status': 'recognized', 'recognized_char': '藤'}]},
            {'slots': [{'index': 1, 'status': 'recognized', 'recognized_char': '藤萝'}]},
            {'slots': [{'index': 1, 'status': 'unclear', 'recognized_char': '藤'}]},
            {'slots': []},
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    normalize_blind_response(json.dumps(raw, ensure_ascii=False))

    def test_prepare_cases_exports_scaled_roi_and_contact_sheet(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest('Pillow unavailable')

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'homework_x' / 'homework_grading' / 'clean'
            source.mkdir(parents=True)
            Image.new('RGB', (100, 100), 'white').save(source / 'page.png')
            cases_path = root / 'cases.json'
            cases_path.write_text(json.dumps({
                'experiment_mode': EXPERIMENT_MODE,
                'cases': [
                    {
                        'case_id': f'case_{index}',
                        'homework_id': 'homework_x',
                        'image_relpath': 'homework_grading/clean/page.png',
                        'question_roi': [100, 100, 900, 900],
                        'evaluation': {'kind': 'correct', 'expected_text': '甲'},
                    }
                    for index in range(10)
                ],
            }, ensure_ascii=False), encoding='utf-8')
            prepared = prepare_cases(cases_path, root, root / 'out')
            self.assertEqual(prepared['case_count'], 10)
            self.assertTrue(Path(prepared['contact_sheet']).is_file())
            self.assertEqual(prepared['cases'][0]['crop_size'], [160, 160])
            self.assertTrue(Path(prepared['cases'][0]['crop_path']).is_file())

    def test_run_retries_only_bad_b_mode_format_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crop_path = root / 'crop.png'
            crop_path.write_bytes(b'not-a-real-png')
            prepared = {
                'cases': [{
                    'case_id': 'case', 'crop_path': str(crop_path), 'crop_sha256': 'sha',
                }],
            }
            calls = []

            def fake_call(_messages):
                calls.append(1)
                if len(calls) == 1:
                    return '{}'
                return '{"slots":[{"index":1,"status":"recognized","recognized_char":"甲"}]}'

            with mock.patch(
                'app_chat.homework_grading.blind_pinyin_review_experiment.image_to_data_uri_for_gemini_review',
                return_value='data:image/png;base64,AAAA',
            ):
                results = run_blind_calls(prepared, root / 'out', workers=1, call_func=fake_call)
                self.assertEqual(len(results), 3)
                self.assertEqual(sum(item['status'] == 'completed' for item in results), 3)
                self.assertEqual(len(calls), 4)
                self.assertEqual(results[0]['attempts'][0]['raw_response'], '{}')
                results_again = run_blind_calls(prepared, root / 'out', workers=1, call_func=fake_call)
            self.assertEqual(len(results_again), 3)
            self.assertEqual(len(calls), 4)

    def test_evaluator_uses_labels_only_after_completed_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases_path = root / 'cases.json'
            cases = []
            for index in range(2):
                cases.append({
                    'case_id': f'wrong_{index}',
                    'evaluation': {'kind': 'standard_wrong', 'actual_text': '纸灰'},
                })
            for index in range(7):
                cases.append({
                    'case_id': f'correct_{index}',
                    'evaluation': {'kind': 'correct', 'expected_text': '藤萝'},
                })
            cases.append({
                'case_id': 'nonstandard',
                'evaluation': {'kind': 'nonstandard', 'target_index': 1, 'target_expected_char': '藤'},
            })
            cases_path.write_text(json.dumps({'experiment_mode': EXPERIMENT_MODE, 'cases': cases}, ensure_ascii=False), encoding='utf-8')
            results = []
            for case in cases:
                label = case['evaluation']
                for repeat in range(1, 4):
                    if label['kind'] == 'standard_wrong':
                        chars = '纸灰'
                        slots = [
                            {'index': idx, 'status': 'recognized', 'recognized_char': char}
                            for idx, char in enumerate(chars, start=1)
                        ]
                    elif label['kind'] == 'correct':
                        slots = [
                            {'index': idx, 'status': 'recognized', 'recognized_char': char}
                            for idx, char in enumerate('藤萝', start=1)
                        ]
                    else:
                        slots = [
                            {'index': 1, 'status': 'nonstandard', 'recognized_char': ''},
                            {'index': 2, 'status': 'recognized', 'recognized_char': '萝'},
                        ]
                    results.append({
                        'case_id': case['case_id'],
                        'repeat': repeat,
                        'status': 'completed',
                        'normalized_response': {'slots': slots},
                        'request_audit': {'business_text_leakage_free': True},
                    })
            evaluation = evaluate_results(cases_path, results)
            self.assertTrue(evaluation['passed'])
            self.assertEqual(evaluation['valid_json_count'], 30)


if __name__ == '__main__':
    unittest.main()
