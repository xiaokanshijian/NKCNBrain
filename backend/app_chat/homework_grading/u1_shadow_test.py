import json
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from app_chat.homework_grading import staged_pipeline, u1_shadow
from app_chat.homework_grading.grader_pass1 import _grade_extra_body


class U1ShadowTest(unittest.TestCase):
    def test_switch_is_default_off_and_math_only(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(u1_shadow.u1_shadow_enabled('math'))
        with mock.patch.dict(os.environ, {'HOMEWORK_PASS1_U1_SHADOW': '1'}, clear=True):
            self.assertTrue(u1_shadow.u1_shadow_enabled('math'))
            self.assertFalse(u1_shadow.u1_shadow_enabled('chinese'))
            self.assertFalse(u1_shadow.u1_shadow_enabled('english'))

    def test_transcription_is_nonthinking_and_strictly_whitelisted(self):
        detected = {'page': 8, 'subject': 'math', 'questions': [{'id': '4-2'}, {'id': '4-3'}]}
        model_result = {
            'questions': [
                {
                    'id': '4-2',
                    'student_answer': ' 1288 ',
                    'recognition_confidence': 120,
                    'understanding': 'must drop',
                    'verdict': 'correct',
                    'alternatives': ['x'],
                },
                {'id': 'extra', 'student_answer': 'ignored'},
            ],
        }
        with tempfile.TemporaryDirectory() as root:
            out_path = os.path.join(root, 'page8.u1.json')
            with mock.patch.object(u1_shadow, 'image_to_data_uri', return_value='data:image/png;base64,CLEAN'), \
                 mock.patch.object(
                     u1_shadow, '_call_qwen_json_with_retry', return_value=(model_result, mock.Mock()),
                 ) as call:
                result, metadata = u1_shadow.run_u1_shadow_page(
                    'clean_page8.png', 'math', 8, detected, out_path,
                )

        messages, extra_body = call.call_args.args
        self.assertEqual(extra_body, {'enable_thinking': False})
        self.assertEqual(call.call_args.kwargs['temperature'], 0.0)
        request_text = json.dumps(messages, ensure_ascii=False)
        self.assertIn('data:image/png;base64,CLEAN', request_text)
        self.assertIn('不要输出 understanding', request_text)
        self.assertNotIn('正式判分结果', request_text)
        self.assertEqual(set(result), {'page', 'subject', 'questions'})
        self.assertEqual(set(result['questions'][0]), set(u1_shadow.U1_QUESTION_KEYS))
        self.assertEqual(result['questions'][0]['student_answer'], '1288')
        self.assertEqual(result['questions'][0]['recognition_confidence'], 100)
        self.assertEqual(result['questions'][1], {
            'id': '4-3', 'student_answer': '', 'recognition_confidence': 0,
        })
        self.assertEqual(metadata['missing_ids'], ['4-3'])
        self.assertEqual(metadata['extra_ids'], ['extra'])

    def test_layout_classification_and_crop_split_are_nonthinking(self):
        detected = {
            'page': 10,
            'subject': 'math',
            'questions': [
                {'id': '1', 'stem_excerpt': '用简便方法写出下列各式', 'position': [100, 100, 900, 500], 'layout_confidence': 90},
                {'id': '2', 'stem_excerpt': '单题', 'position': [100, 550, 900, 900], 'layout_confidence': 90},
            ],
        }
        candidate = {'questions': [{'id': '1', 'multi_item': True, 'student_answer': 'drop'}]}
        split = {'questions': [
            {'id': '1-1', 'stem_excerpt': 'm×m=', 'position': [0, 0, 500, 500], 'layout_confidence': 91, 'verdict': 'drop'},
            {'id': '1-2', 'stem_excerpt': 'x+x=', 'position': [500, 0, 1000, 500], 'layout_confidence': 92},
        ]}
        with tempfile.TemporaryDirectory() as root:
            image_path = os.path.join(root, 'clean_page10.png')
            Image.new('RGB', (100, 100), 'white').save(image_path)
            out_path = os.path.join(root, 'page10.layout.json')
            calls = []

            def fake_call(messages, extra_body, **kwargs):
                calls.append((messages, extra_body, kwargs))
                return (candidate if len(calls) == 1 else split), mock.Mock()

            with mock.patch.object(u1_shadow, '_call_qwen_json_with_retry', side_effect=fake_call):
                layout, metadata = u1_shadow.run_u1_shadow_layout_page(
                    image_path, 'math', 10, detected, out_path,
                )

        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call[1] == {'enable_thinking': False} for call in calls))
        self.assertTrue(all(call[2]['temperature'] == 0.0 for call in calls))
        request_text = json.dumps(calls, ensure_ascii=False, default=str)
        self.assertNotIn('参考答案内容', request_text)
        self.assertEqual([item['id'] for item in layout['questions']], ['1-1', '1-2', '2'])
        self.assertEqual(metadata['split_parent_ids'], ['1'])
        self.assertEqual(metadata['child_count'], 2)
        for item in layout['questions']:
            self.assertEqual(set(item), set(u1_shadow.LAYOUT_QUESTION_KEYS))
            self.assertNotIn('verdict', item)
            self.assertNotIn('student_answer', item)
        self.assertEqual(layout['questions'][0]['position'], [100.0, 100.0, 500.0, 300.0])

    def test_invalid_split_falls_back_to_parent_and_writes_error(self):
        detected = {
            'questions': [{'id': '1', 'position': [0, 0, 1000, 1000], 'layout_confidence': 90}],
        }
        candidate = {'questions': [{'id': '1', 'multi_item': True}]}
        non_contiguous = {'questions': [
            {'id': '1-1', 'position': [0, 0, 500, 500]},
            {'id': '1-3', 'position': [500, 0, 1000, 500]},
        ]}
        with tempfile.TemporaryDirectory() as root:
            image_path = os.path.join(root, 'clean.png')
            Image.new('RGB', (50, 50), 'white').save(image_path)
            out_path = os.path.join(root, 'page10.layout.json')
            with mock.patch.object(
                u1_shadow, '_call_qwen_json_with_retry',
                side_effect=[(candidate, mock.Mock()), (non_contiguous, mock.Mock())],
            ):
                layout, metadata = u1_shadow.run_u1_shadow_layout_page(
                    image_path, 'math', 10, detected, out_path,
                )
            self.assertEqual([item['id'] for item in layout['questions']], ['1'])
            self.assertEqual(metadata['fallback_parent_ids'], ['1'])
            self.assertTrue(os.path.isfile(out_path.replace('.layout.json', '.layout.error.txt')))

    def test_split_rejects_out_of_crop_bbox(self):
        parent = {'id': '1', 'position': [0, 0, 1000, 1000]}
        result = {'questions': [
            {'id': '1-1', 'position': [-1, 0, 500, 500]},
            {'id': '1-2', 'position': [500, 0, 1000, 500]},
        ]}
        with self.assertRaisesRegex(ValueError, '连续'):
            u1_shadow._normalize_split_children(parent, result)

    def test_official_math_grading_still_thinks_with_4096_budget(self):
        self.assertEqual(_grade_extra_body('math'), {'enable_thinking': True, 'thinking_budget': 4096})

    def test_comparison_normalization_is_width_and_whitespace_only(self):
        self.assertEqual(u1_shadow.comparison_text(' １２８８ '), '1288')
        self.assertNotEqual(u1_shadow.comparison_text('m²'), u1_shadow.comparison_text('m2'))

    def _summary_fixture(self, root):
        base = os.path.join(root, 'homework_grading')
        clean_dir = os.path.join(base, 'clean')
        pass1_dir = os.path.join(base, 'pass1_json')
        layout_dir = os.path.join(base, 'pass1_u1_shadow', 'layout')
        os.makedirs(clean_dir)
        os.makedirs(pass1_dir)
        os.makedirs(layout_dir)
        stem = 'math_demo_page10'
        clean_path = os.path.join(clean_dir, stem + '.png')
        with open(clean_path, 'wb') as file:
            file.write(b'clean')
        formal_detect = {'page': 10, 'questions': [
            {'id': '1'}, {'id': '2'},
        ]}
        layout = {'page': 10, 'questions': [
            {'id': '1-1'}, {'id': '1-2'}, {'id': '2'},
        ]}
        official = {'page': 10, 'questions': [
            {'id': '1', 'student_answer': 'm²;2x'}, {'id': '2', 'student_answer': '１２８８'},
        ]}
        for path, body in (
            (os.path.join(pass1_dir, stem + '.detect.json'), formal_detect),
            (os.path.join(pass1_dir, stem + '.json'), official),
            (os.path.join(layout_dir, stem + '.layout.json'), layout),
        ):
            with open(path, 'w', encoding='utf-8') as file:
                json.dump(body, file, ensure_ascii=False)
        return base, pass1_dir, clean_path, official

    def test_summary_does_not_compare_shadow_children_as_formal_parent(self):
        with tempfile.TemporaryDirectory() as root:
            base, pass1_dir, clean_path, official = self._summary_fixture(root)

            def fake_run(_image, subject, page, _detected, out_path):
                shadow = {'page': page, 'subject': subject, 'questions': [
                    {'id': '1-1', 'student_answer': 'mm', 'recognition_confidence': 95},
                    {'id': '1-2', 'student_answer': '2x', 'recognition_confidence': 95},
                    {'id': '2', 'student_answer': '1288', 'recognition_confidence': 95},
                ]}
                with open(out_path, 'w', encoding='utf-8') as file:
                    json.dump(shadow, file, ensure_ascii=False)
                ids = ['1-1', '1-2', '2']
                return shadow, {'expected_ids': ids, 'returned_ids': ids, 'missing_ids': [], 'extra_ids': []}

            paths = {'base': base, 'pass1_json': pass1_dir}
            page = {'page': 10, 'clean_abs_path': clean_path}
            with mock.patch.object(staged_pipeline, 'run_u1_shadow_page', side_effect=fake_run), \
                 mock.patch.object(staged_pipeline, 'homework_qwen_model', return_value='qwen-test'):
                summary = staged_pipeline._run_u1_shadow_all_pages([page], paths, 'math', 1)

            with open(os.path.join(pass1_dir, 'math_demo_page10.json'), 'r', encoding='utf-8') as file:
                self.assertEqual(json.load(file), official)
            self.assertEqual(summary['split_parent_count'], 1)
            self.assertEqual(summary['split_child_count'], 2)
            self.assertEqual(summary['comparable_ids'], 1)
            self.assertEqual(summary['exact_matches'], 0)
            self.assertEqual(summary['normalized_matches'], 1)
            self.assertEqual(summary['unmatched_formal_ids'], [{'page': 10, 'id': '1'}])

    def test_transcription_failure_only_writes_nested_shadow_error(self):
        with tempfile.TemporaryDirectory() as root:
            base, pass1_dir, clean_path, official = self._summary_fixture(root)
            paths = {'base': base, 'pass1_json': pass1_dir}
            page = {'page': 10, 'clean_abs_path': clean_path}
            with mock.patch.object(staged_pipeline, 'run_u1_shadow_page', side_effect=ValueError('bad json')), \
                 mock.patch.object(staged_pipeline, 'homework_qwen_model', return_value='qwen-test'):
                summary = staged_pipeline._run_u1_shadow_all_pages([page], paths, 'math', 1)

            with open(os.path.join(pass1_dir, 'math_demo_page10.json'), 'r', encoding='utf-8') as file:
                self.assertEqual(json.load(file), official)
            error_path = os.path.join(
                base, 'pass1_u1_shadow', 'transcription', 'math_demo_page10.u1.error.txt',
            )
            self.assertTrue(os.path.isfile(error_path))
            self.assertEqual(summary['transcription_failed_pages'], 1)


if __name__ == '__main__':
    unittest.main()
