import json
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from app_chat.homework_grading import slot_presence, staged_pipeline


class SlotPresenceTest(unittest.TestCase):
    def test_switch_defaults_to_allowlisted_apply_and_remains_math_only(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(slot_presence.slot_presence_mode('math'), 'apply')
            self.assertFalse(slot_presence.slot_presence_shadow_enabled('math'))
            self.assertTrue(slot_presence.slot_presence_layout_enabled('math'))
            self.assertTrue(slot_presence.slot_presence_apply_approved(
                'math_db2d0b12_page12',
                'math',
            ))
            self.assertFalse(slot_presence.slot_presence_apply_approved(
                'math_other_page12',
                'math',
            ))
            self.assertTrue(slot_presence.slot_presence_apply_approved(
                'math_new-runtime-id_page12',
                'math',
                source_document_sha256=(
                    '83a954cb09d9b8ac6dd7c416941445f51c52b87d1db0899b52ddda6e55ddf62b'
                ),
            ))
            self.assertFalse(slot_presence.slot_presence_apply_approved(
                'math_db2d0b12_page12',
                'math',
                source_document_sha256='0' * 64,
            ))
        with mock.patch.dict(
            os.environ,
            {'HOMEWORK_PASS1_SLOT_PRESENCE': 'shadow'},
            clear=True,
        ):
            self.assertTrue(slot_presence.slot_presence_shadow_enabled('math'))
            self.assertFalse(slot_presence.slot_presence_shadow_enabled('chinese'))
            self.assertFalse(slot_presence.slot_presence_shadow_enabled('english'))
        with mock.patch.dict(
            os.environ,
            {'HOMEWORK_PASS1_SLOT_PRESENCE': 'off'},
            clear=True,
        ):
            self.assertEqual(slot_presence.slot_presence_mode('math'), 'off')
            self.assertFalse(slot_presence.slot_presence_layout_enabled('math'))

    def test_presence_call_uses_raw_and_clean_without_answer_transcription(self):
        detected = {
            'page': 15,
            'subject': 'math',
            'questions': [{
                'id': '2-1',
                'stem_excerpt': '25+56=56+[25]',
                'position': [105, 825, 480, 885],
            }],
        }
        model_result = {
            'questions': [{
                'id': '2-1',
                'student_answer': 'must drop',
                'slots': [
                    {
                        'slot_index': 1,
                        'slot_type': 'fill_blank',
                        'position': [250, 830, 290, 850],
                        'student_black_visible': False,
                        'teacher_mark_visible': True,
                        'residual_or_negative_trace_visible': True,
                        'presence': 'present',
                        'reason_code': 'red_only',
                        'confidence': 101,
                        'transcript': '25',
                    },
                    {
                        'slot_index': 2,
                        'slot_type': 'fill_blank',
                        'position': [145, 850, 340, 882],
                        'student_black_visible': True,
                        'teacher_mark_visible': False,
                        'residual_or_negative_trace_visible': False,
                        'presence': 'present',
                        'reason_code': 'black_stroke',
                        'confidence': 92,
                    },
                    {
                        'slot_index': 3,
                        'slot_type': 'fill_blank',
                        'position': [540, 345, 650, 375],
                        'student_black_visible': True,
                        'teacher_mark_visible': False,
                        'residual_or_negative_trace_visible': False,
                        'presence': 'present',
                        'reason_code': 'black_stroke',
                        'confidence': 98,
                    },
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as root:
            raw_path = os.path.join(root, 'raw.png')
            clean_path = os.path.join(root, 'clean.png')
            out_path = os.path.join(root, 'page15.presence.json')
            Image.new('RGB', (40, 40), 'white').save(raw_path)
            Image.new('RGB', (40, 40), 'white').save(clean_path)
            with mock.patch.object(
                slot_presence,
                'image_to_data_uri',
                side_effect=['data:image/png;base64,RAW', 'data:image/png;base64,CLEAN'],
            ), mock.patch.object(
                slot_presence,
                '_call_qwen_json_with_retry',
                return_value=(model_result, mock.Mock()),
            ) as call:
                result, metadata = slot_presence.run_slot_presence_layout_page(
                    raw_path,
                    clean_path,
                    'math',
                    15,
                    detected,
                    out_path,
                )

        messages, extra_body = call.call_args.args
        request_text = json.dumps(messages, ensure_ascii=False)
        self.assertEqual(extra_body, {'enable_thinking': False})
        self.assertEqual(call.call_args.kwargs['temperature'], 0.0)
        self.assertIn('data:image/png;base64,RAW', request_text)
        self.assertIn('data:image/png;base64,CLEAN', request_text)
        self.assertNotIn('25+56=56+[25]', request_text)
        self.assertIn('不得包含任何答案字符', request_text)
        self.assertEqual(metadata['slot_count'], 3)
        self.assertEqual(metadata['outside_formal_bbox_count'], 1)
        question = result['questions'][0]
        self.assertEqual(question['answer_presence'], 'partial')
        self.assertEqual(question['slots'][0]['slot_id'], '2-1:s1')
        self.assertEqual(question['slots'][0]['presence'], 'absent')
        self.assertEqual(question['slots'][0]['ink_source'], 'teacher_red')
        self.assertEqual(question['slots'][0]['confidence'], 100)
        self.assertEqual(question['slots'][1]['slot_id'], '2-1:s2')
        self.assertEqual(question['slots'][1]['presence'], 'present')
        self.assertEqual(question['slots'][1]['ink_source'], 'student_black')
        self.assertEqual(question['slots'][2]['slot_id'], '2-1:s3')
        self.assertTrue(question['slots'][2]['outside_formal_bbox'])
        self.assertNotIn('student_answer', json.dumps(result, ensure_ascii=False))
        self.assertNotIn('transcript', json.dumps(result, ensure_ascii=False))

    def test_no_student_black_forces_absent_even_if_model_claims_present(self):
        detected = {'questions': [{'id': '2-2', 'position': [500, 345, 870, 475]}]}
        model_result = {'questions': [{
            'id': '2-2',
            'slots': [{
                'slot_index': 1,
                'slot_type': 'fill_blank',
                'position': [630, 365, 670, 390],
                'student_black_visible': False,
                'teacher_mark_visible': False,
                'residual_or_negative_trace_visible': False,
                'presence': 'present',
                'reason_code': 'no_mark',
                'confidence': 90,
            }],
        }]}
        result, _metadata = slot_presence.normalize_slot_presence_result(
            model_result,
            detected,
            'math',
            15,
        )
        slot = result['questions'][0]['slots'][0]
        self.assertEqual(slot['presence'], 'absent')
        self.assertEqual(slot['ink_source'], 'none')

    def test_red_connection_area_is_absent(self):
        detected = {'questions': [{'id': '1', 'position': [180, 205, 520, 295]}]}
        model_result = {'questions': [{
            'id': '1',
            'slots': [{
                'slot_index': 1,
                'slot_type': 'connection_area',
                'position': [180, 205, 520, 295],
                'student_black_visible': False,
                'teacher_mark_visible': True,
                'residual_or_negative_trace_visible': True,
                'presence': 'absent',
                'reason_code': 'red_only',
                'confidence': 96,
            }],
        }]}
        result, _metadata = slot_presence.normalize_slot_presence_result(
            model_result,
            detected,
            'math',
            12,
        )
        self.assertEqual(result['questions'][0]['answer_presence'], 'absent')
        self.assertEqual(
            result['questions'][0]['slots'][0]['slot_type'],
            'connection_area',
        )

    def test_layout_shadow_writes_separate_evidence_without_mutating_detect(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, 'homework_grading')
            raw_dir = os.path.join(base, 'raw')
            clean_dir = os.path.join(base, 'clean')
            pass1_dir = os.path.join(base, 'pass1_json')
            os.makedirs(raw_dir)
            os.makedirs(clean_dir)
            os.makedirs(pass1_dir)
            stem = 'math_demo_page15'
            raw_path = os.path.join(raw_dir, stem + '.png')
            clean_path = os.path.join(clean_dir, stem + '.png')
            detect_path = os.path.join(pass1_dir, stem + '.detect.json')
            Image.new('RGB', (20, 20), 'white').save(raw_path)
            Image.new('RGB', (20, 20), 'white').save(clean_path)
            detected = {'page': 15, 'questions': [{'id': '2-1'}]}
            with open(detect_path, 'w', encoding='utf-8') as file:
                json.dump(detected, file)
            paths = {
                'base': base,
                'raw': raw_dir,
                'pass1_json': pass1_dir,
            }
            page = {
                'page': 15,
                'raw_abs_path': raw_path,
                'clean_abs_path': clean_path,
            }

            def fake_run(_raw, _clean, subject, page_num, _detected, out_path):
                body = {
                    'page': page_num,
                    'subject': subject,
                    'questions': [{'id': '2-1', 'answer_presence': 'partial'}],
                }
                with open(out_path, 'w', encoding='utf-8') as file:
                    json.dump(body, file)
                return body, {
                    'expected_ids': ['2-1'],
                    'returned_ids': ['2-1'],
                    'missing_ids': [],
                    'extra_ids': [],
                    'slot_count': 2,
                    'outside_formal_bbox_count': 0,
                }

            with mock.patch.dict(
                os.environ,
                {'HOMEWORK_PASS1_SLOT_PRESENCE': 'shadow'},
                clear=True,
            ), mock.patch.object(
                staged_pipeline,
                'run_slot_presence_layout_page',
                side_effect=fake_run,
            ), mock.patch.object(
                staged_pipeline,
                'homework_qwen_model',
                return_value='qwen-test',
            ):
                summary = staged_pipeline._run_slot_presence_layout_all_pages(
                    [page],
                    paths,
                    'math',
                    1,
                )

            with open(detect_path, 'r', encoding='utf-8') as file:
                self.assertEqual(json.load(file), detected)
            evidence_path = os.path.join(
                base,
                'layout_evidence',
                'slot_presence',
                stem + '.presence.json',
            )
            self.assertTrue(os.path.isfile(evidence_path))
            self.assertEqual(summary['successful_pages'], 1)
            self.assertEqual(summary['slot_count'], 2)
            self.assertEqual(summary['outside_formal_bbox_count'], 0)

    def test_layout_apply_collects_only_approved_page_stems(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, 'homework_grading')
            raw_dir = os.path.join(base, 'raw')
            clean_dir = os.path.join(base, 'clean')
            pass1_dir = os.path.join(base, 'pass1_json')
            os.makedirs(raw_dir)
            os.makedirs(clean_dir)
            os.makedirs(pass1_dir)
            pages = []
            for page_num, stem in (
                (12, 'math_db2d0b12_page12'),
                (13, 'math_db2d0b12_page13'),
            ):
                raw_path = os.path.join(raw_dir, stem + '.png')
                clean_path = os.path.join(clean_dir, stem + '.png')
                detect_path = os.path.join(pass1_dir, stem + '.detect.json')
                Image.new('RGB', (20, 20), 'white').save(raw_path)
                Image.new('RGB', (20, 20), 'white').save(clean_path)
                with open(detect_path, 'w', encoding='utf-8') as file:
                    json.dump({'page': page_num, 'questions': [{'id': '1'}]}, file)
                pages.append({
                    'page': page_num,
                    'raw_abs_path': raw_path,
                    'clean_abs_path': clean_path,
                })
            paths = {'base': base, 'raw': raw_dir, 'pass1_json': pass1_dir}

            def fake_run(_raw, _clean, subject, page_num, _detected, out_path):
                body = {'page': page_num, 'subject': subject, 'questions': []}
                with open(out_path, 'w', encoding='utf-8') as file:
                    json.dump(body, file)
                return body, {
                    'expected_ids': ['1'],
                    'returned_ids': ['1'],
                    'missing_ids': [],
                    'extra_ids': [],
                    'slot_count': 1,
                    'outside_formal_bbox_count': 0,
                }

            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                staged_pipeline,
                'run_slot_presence_layout_page',
                side_effect=fake_run,
            ) as run, mock.patch.object(
                staged_pipeline,
                'homework_qwen_model',
                return_value='qwen-test',
            ):
                summary = staged_pipeline._run_slot_presence_layout_all_pages(
                    pages,
                    paths,
                    'math',
                    2,
                )

            self.assertEqual(summary['mode'], 'apply')
            self.assertEqual(summary['attempted_pages'], 1)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[3], 12)

    def test_grade_job_applies_existing_layout_evidence_to_approved_page(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, 'homework_grading')
            pass1_dir = os.path.join(base, 'pass1_json')
            clean_dir = os.path.join(base, 'clean')
            evidence_dir = os.path.join(base, 'layout_evidence', 'slot_presence')
            os.makedirs(pass1_dir)
            os.makedirs(clean_dir)
            os.makedirs(evidence_dir)
            stem = 'math_db2d0b12_page12'
            clean_path = os.path.join(clean_dir, stem + '.png')
            Image.new('RGB', (20, 20), 'white').save(clean_path)
            presence_path = os.path.join(evidence_dir, stem + '.presence.json')
            with open(presence_path, 'w', encoding='utf-8') as file:
                json.dump({'page': 12, 'questions': []}, file)
            paths = {'base': base, 'pass1_json': pass1_dir}
            page = {'page': 12, 'clean_abs_path': clean_path}

            def fake_grade(_image, _subject, _page, out_json, **_kwargs):
                grade_path = out_json.replace('.json', '.grade.json')
                with open(grade_path, 'w', encoding='utf-8') as file:
                    json.dump({'page': 12, 'questions': []}, file)
                with open(out_json, 'w', encoding='utf-8') as file:
                    json.dump({'page': 12, 'questions': []}, file)

            with mock.patch.object(
                staged_pipeline,
                'pass1_two_stage_enabled',
                return_value=True,
            ), mock.patch.object(
                staged_pipeline,
                'grade_page_from_detect',
                side_effect=fake_grade,
            ), mock.patch.object(
                staged_pipeline,
                'apply_slot_presence_guard_to_files',
                return_value={'applied': True},
            ) as apply_guard:
                staged_pipeline._grade_page_job(
                    page,
                    paths,
                    'math',
                    None,
                    4,
                    2,
                )

            self.assertEqual(apply_guard.call_count, 1)
            self.assertEqual(apply_guard.call_args.args[2], presence_path)
            self.assertEqual(apply_guard.call_args.args[3], stem)

    def test_fixed_regression_manifest_contains_page15_q2_1_both_polarities(self):
        data_path = os.path.join(
            os.path.dirname(__file__),
            'data',
            'experiments',
            'math_slot_presence_cases_20260724.json',
        )
        with open(data_path, 'r', encoding='utf-8') as file:
            payload = json.load(file)
        cases = {case['case_id']: case for case in payload['cases']}
        case = cases['math1_p15_q2_1_mixed_empty_and_written']
        slots = case['evaluation']['slots']
        self.assertEqual(
            [slot['presence'] for slot in slots],
            ['absent', 'present', 'present'],
        )
        self.assertEqual(case['evaluation']['answer_presence'], 'partial')
        self.assertEqual(
            payload['apply_approved_page_stems'],
            ['math_db2d0b12_page12', 'math_db2d0b12_page15'],
        )
        self.assertIn('math1_p12_q1_red_connection_absent', cases)
        self.assertIn('math1_p15_q2_2_two_empty_two_written', cases)

        page_result = {
            'page': 15,
            'questions': [{
                'id': '2-1',
                'answer_presence': 'partial',
                'slots': [
                    {'slot_id': '2-1:s1', 'presence': 'absent'},
                    {'slot_id': '2-1:s2', 'presence': 'present'},
                    {'slot_id': '2-1:s3', 'presence': 'present'},
                ],
            }],
        }
        evaluation = slot_presence.evaluate_slot_presence_regression(
            page_result,
            {
                **payload,
                'cases': [case],
            },
        )
        self.assertEqual(evaluation['passed_count'], 1)
        self.assertEqual(evaluation['pass_rate'], 1.0)

        page_result['questions'][0]['slots'].append({
            'slot_id': '2-1:s4',
            'presence': 'present',
        })
        evaluation_with_extra = slot_presence.evaluate_slot_presence_regression(
            page_result,
            {
                **payload,
                'cases': [case],
            },
        )
        self.assertEqual(evaluation_with_extra['passed_count'], 0)
        self.assertEqual(
            evaluation_with_extra['details'][0]['unexpected_slot_ids'],
            ['2-1:s4'],
        )

    def test_formal_guard_clears_page12_red_only_connection(self):
        graded = {
            'page': 12,
            'subject': 'math',
            'questions': [{
                'id': '1',
                'visual_answer_segments': [
                    'a²-a×a',
                    '9d-9×d',
                    '2a-a+a',
                    'x×y-y²',
                ],
                'student_answer': 'a²-a×a, 9d-9×d, 2a-a+a, x×y-y²',
                'understanding': '模型按题意重建了连线。',
                'verdict': 'partial',
                'error_type': 'matching_error',
            }],
        }
        presence = {
            'page': 12,
            'questions': [{
                'id': '1',
                'answer_presence': 'absent',
                'slots': [{'slot_id': '1:s1', 'presence': 'absent'}],
            }],
        }
        guarded, audit = slot_presence.apply_slot_presence_guard(
            graded,
            presence,
            'math_db2d0b12_page12',
        )
        question = guarded['questions'][0]
        self.assertTrue(audit['applied'])
        self.assertEqual(question['visual_answer_segments'], [])
        self.assertEqual(question['student_answer'], '')
        self.assertEqual(question['verdict'], 'unanswered')
        self.assertEqual(question['error_type'], '未作答')

    def test_formal_guard_file_lock_survives_downstream_mutation(self):
        graded = {
            'page': 12,
            'subject': 'math',
            'questions': [{
                'id': '1',
                'visual_answer_segments': ['a', 'b'],
                'student_answer': 'a b',
                'understanding': '原理解',
                'verdict': 'correct',
                'error_type': '',
            }],
        }
        final = {
            'page': 12,
            'subject': 'math',
            'questions': [{
                'id': '1',
                'student_answer': 'a b',
                'understanding': '原理解',
                'verdict': 'correct',
                'error_type': '',
            }],
        }
        presence = {
            'page': 12,
            'questions': [{
                'id': '1',
                'answer_presence': 'absent',
                'slots': [{'slot_id': '1:s1', 'presence': 'absent'}],
            }],
        }
        with tempfile.TemporaryDirectory() as root:
            grade_path = os.path.join(root, 'page12.grade.json')
            final_path = os.path.join(root, 'page12.json')
            presence_path = os.path.join(root, 'page12.presence.json')
            for path, payload in (
                (grade_path, graded),
                (final_path, final),
                (presence_path, presence),
            ):
                with open(path, 'w', encoding='utf-8') as file:
                    json.dump(payload, file)

            audit = slot_presence.apply_slot_presence_guard_to_files(
                grade_path,
                final_path,
                presence_path,
                'math_db2d0b12_page12',
            )
            self.assertEqual(audit['restored_final_question_count'], 1)
            with open(final_path, 'r', encoding='utf-8') as file:
                guarded_final = json.load(file)
            self.assertEqual(guarded_final['questions'][0]['verdict'], 'unanswered')
            self.assertNotIn(
                'visual_answer_segments',
                guarded_final['questions'][0],
            )

            guarded_final['questions'][0].update({
                'student_answer': '模型再次补写',
                'verdict': 'correct',
            })
            with open(final_path, 'w', encoding='utf-8') as file:
                json.dump(guarded_final, file)
            restored_count = slot_presence.reapply_slot_presence_guard_files(
                grade_path,
                final_path,
            )
            self.assertEqual(restored_count, 1)
            with open(final_path, 'r', encoding='utf-8') as file:
                restored = json.load(file)
            self.assertEqual(restored['questions'][0]['student_answer'], '')
            self.assertEqual(restored['questions'][0]['verdict'], 'unanswered')

    def test_formal_guard_removes_only_empty_page15_slots(self):
        graded = {
            'page': 15,
            'subject': 'math',
            'questions': [
                {
                    'id': '2-1',
                    'visual_answer_segments': ['25', '加法交换', 'a+b=b+a'],
                    'student_answer': '25 加法交换 a+b=b+a',
                    'understanding': '原理解',
                    'verdict': 'correct',
                    'error_type': '',
                },
                {
                    'id': '2-2',
                    'visual_answer_segments': [
                        '137',
                        '63',
                        '加法结合',
                        'a+b+c=a+(b+c)',
                    ],
                    'student_answer': '137 63 加法结合 a+b+c=a+(b+c)',
                    'understanding': '原理解',
                    'verdict': 'correct',
                    'error_type': '',
                },
                {
                    'id': '2-3',
                    'visual_answer_segments': ['1000-961=39', '1000÷39=961'],
                    'student_answer': '1000-961=39 1000÷39=961',
                    'understanding': '原理解',
                    'verdict': 'partial',
                    'error_type': '第二式错误',
                },
            ],
        }
        presence = {
            'page': 15,
            'questions': [
                {
                    'id': '2-1',
                    'answer_presence': 'partial',
                    'slots': [
                        {'slot_id': '2-1:s1', 'presence': 'absent'},
                        {'slot_id': '2-1:s2', 'presence': 'present'},
                        {'slot_id': '2-1:s3', 'presence': 'present'},
                    ],
                },
                {
                    'id': '2-2',
                    'answer_presence': 'partial',
                    'slots': [
                        {'slot_id': '2-2:s1', 'presence': 'absent'},
                        {'slot_id': '2-2:s2', 'presence': 'absent'},
                        {'slot_id': '2-2:s3', 'presence': 'present'},
                        {'slot_id': '2-2:s4', 'presence': 'present'},
                    ],
                },
                {
                    'id': '2-3',
                    'answer_presence': 'present',
                    'slots': [
                        {'slot_id': '2-3:s1', 'presence': 'present'},
                        {'slot_id': '2-3:s2', 'presence': 'present'},
                    ],
                },
            ],
        }
        guarded, audit = slot_presence.apply_slot_presence_guard(
            graded,
            presence,
            'math_db2d0b12_page15',
        )
        questions = {item['id']: item for item in guarded['questions']}
        self.assertEqual(audit['applied_question_count'], 3)
        self.assertEqual(
            questions['2-1']['visual_answer_segments'],
            ['加法交换', 'a+b=b+a'],
        )
        self.assertEqual(
            questions['2-1']['student_answer'],
            '加法交换 a+b=b+a',
        )
        self.assertEqual(questions['2-1']['verdict'], 'partial')
        self.assertEqual(
            questions['2-2']['visual_answer_segments'],
            ['加法结合', 'a+b+c=a+(b+c)'],
        )
        self.assertEqual(
            questions['2-2']['student_answer'],
            '加法结合 a+b+c=a+(b+c)',
        )
        self.assertEqual(questions['2-3']['verdict'], 'partial')
        self.assertEqual(
            questions['2-3']['student_answer'],
            '1000-961=39 1000÷39=961',
        )

        downstream = {
            'page': 15,
            'questions': [{
                'id': '2-1',
                'student_answer': '25 加法交换 a+b=b+a',
                'verdict': 'correct',
                'error_type': '',
            }],
        }
        restored, count = slot_presence.reapply_slot_presence_locks(
            downstream,
            guarded,
        )
        self.assertEqual(count, 1)
        self.assertEqual(
            restored['questions'][0]['student_answer'],
            '加法交换 a+b=b+a',
        )
        self.assertEqual(restored['questions'][0]['verdict'], 'partial')

    def test_formal_guard_fails_closed_on_regression_or_segment_mismatch(self):
        graded = {
            'page': 15,
            'questions': [{
                'id': '2-1',
                'visual_answer_segments': ['25', '加法交换'],
                'student_answer': '25 加法交换',
                'understanding': '原理解',
                'verdict': 'correct',
                'error_type': '',
            }],
        }
        presence = {
            'page': 15,
            'questions': [{
                'id': '2-1',
                'answer_presence': 'partial',
                'slots': [
                    {'slot_id': '2-1:s1', 'presence': 'absent'},
                    {'slot_id': '2-1:s2', 'presence': 'present'},
                    {'slot_id': '2-1:s3', 'presence': 'present'},
                ],
            }],
        }
        manifest = {
            'apply_approved_page_stems': ['math_db2d0b12_page15'],
            'cases': [{
                'case_id': 'q2-1',
                'page': 15,
                'question_id': '2-1',
                'evaluation': {
                    'answer_presence': 'partial',
                    'slots': [
                        {'slot_id': '2-1:s1', 'presence': 'absent'},
                        {'slot_id': '2-1:s2', 'presence': 'present'},
                        {'slot_id': '2-1:s3', 'presence': 'present'},
                    ],
                },
            }],
        }
        with mock.patch.object(
            slot_presence,
            '_load_regression_manifest',
            return_value=manifest,
        ):
            guarded, audit = slot_presence.apply_slot_presence_guard(
                graded,
                presence,
                'math_db2d0b12_page15',
            )
        self.assertFalse(audit['applied'])
        self.assertEqual(
            audit['blocked_questions'][0]['block_reason'],
            'slot_segment_count_mismatch',
        )
        self.assertEqual(guarded, {
            **graded,
            'slot_presence_guard': audit,
        })


if __name__ == '__main__':
    unittest.main()
