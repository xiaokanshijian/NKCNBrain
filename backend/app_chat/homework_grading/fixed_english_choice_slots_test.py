import copy
import os
import tempfile
import unittest
from unittest import mock

from app_chat.homework_grading import grader_pass1
from app_chat.homework_grading.fixed_english_choice_slots import (
    EVIDENCE_SOURCE,
    FIXED_ENGLISH_CHOICE_SLOTS_ENV,
    apply_fixed_english_choice_guard,
    attach_fixed_english_choice_slots,
    fixed_english_choice_page,
    load_fixed_english_choice_manifest,
    normalize_fixed_english_choice_transcription,
    reapply_fixed_english_choice_guards,
    record_fixed_english_choice_transcription,
)


def _detected_page20():
    return {
        'page': 20,
        'subject': 'english',
        'questions': [
            {
                'id': f'10-{index}',
                'parent_group_id': '10',
                'position': [165, 700 + index * 35, 230, 730 + index * 35],
            }
            for index in range(1, 6)
        ],
    }


class FixedEnglishChoiceSlotsTest(unittest.TestCase):
    def test_manifest_is_limited_to_one_approved_page(self):
        payload = load_fixed_english_choice_manifest()
        self.assertEqual(payload['version'], 'fixed-english-choice-slots-20260725-v3')
        self.assertEqual(len(payload['cases']), 1)
        case = payload['cases'][0]
        self.assertEqual(
            (case['subject'], case['sample_id'], case['page']),
            ('english', '51a8f187', 20),
        )
        self.assertEqual(len(case['source_sha256']), 64)
        self.assertEqual(
            [item['id'] for item in case['questions']],
            ['10-1', '10-2', '10-3', '10-4', '10-5'],
        )
        self.assertEqual(
            [item['expected_observed_label'] for item in case['questions']],
            ['A', 'B', 'A', 'B', 'B'],
        )

    def test_attach_adds_geometry_without_prefilling_selected_answer(self):
        detected = _detected_page20()
        with mock.patch.dict(os.environ, {FIXED_ENGLISH_CHOICE_SLOTS_ENV: '1'}):
            audit = attach_fixed_english_choice_slots(
                detected,
                'english',
                '51a8f187',
                20,
            )

        self.assertTrue(audit['applied'])
        self.assertEqual(audit['slot_count'], 5)
        self.assertFalse(audit['selected_answer_prefilled'])
        question = detected['questions'][3]
        self.assertEqual(question['id'], '10-4')
        self.assertEqual(len(question['answer_slots']), 1)
        slot = question['answer_slots'][0]
        self.assertEqual(slot['slot_type'], 'parenthesized_choice')
        self.assertEqual(slot['evidence_source'], EVIDENCE_SOURCE)
        self.assertEqual(
            [candidate['label'] for candidate in slot['candidate_regions']],
            ['A', 'B'],
        )
        self.assertNotIn('selected_answer', slot)
        self.assertNotIn('student_answer', slot)
        sx1, sy1, sx2, sy2 = slot['slot_position']
        mx1, my1, mx2, my2 = slot['mark_position']
        self.assertTrue(sx1 <= mx1 < mx2 <= sx2)
        self.assertTrue(sy1 <= my1 < my2 <= sy2)

    def test_attach_matches_source_document_hash_across_runtime_sample_ids(self):
        source_sha256 = (
            'a6891387d779229ad18a9e367c1b5525514bbb4aa7a29f88873893b2784ed39c'
        )
        detected = _detected_page20()
        audit = attach_fixed_english_choice_slots(
            detected,
            'english',
            'renamed-upload',
            20,
            source_document_sha256=source_sha256,
        )
        self.assertTrue(audit['applied'])
        self.assertEqual(
            audit['document_identity']['matched_by'],
            'source_document_sha256',
        )

        mismatched = attach_fixed_english_choice_slots(
            _detected_page20(),
            'english',
            '51a8f187',
            20,
            source_document_sha256='0' * 64,
        )
        self.assertFalse(mismatched['applied'])

        drifted_manifest = copy.deepcopy(load_fixed_english_choice_manifest())
        drifted_manifest['cases'][0]['source_document_sha256'] = '0' * 64
        drifted = attach_fixed_english_choice_slots(
            _detected_page20(),
            'english',
            'renamed-upload',
            20,
            source_document_sha256=source_sha256,
            manifest=drifted_manifest,
        )
        self.assertFalse(drifted['applied'])

    def test_non_target_page_sample_and_disabled_mode_are_noops(self):
        for sample_id, page_num in (
            ('51a8f187', 19),
            ('other-sample', 20),
        ):
            detected = _detected_page20()
            with self.subTest(sample_id=sample_id, page_num=page_num):
                audit = attach_fixed_english_choice_slots(
                    detected,
                    'english',
                    sample_id,
                    page_num,
                )
                self.assertFalse(audit['applied'])
                self.assertTrue(all(
                    'answer_slots' not in question
                    for question in detected['questions']
                ))

        detected = _detected_page20()
        with mock.patch.dict(os.environ, {FIXED_ENGLISH_CHOICE_SLOTS_ENV: '0'}):
            self.assertFalse(fixed_english_choice_page('english', '51a8f187', 20))
            audit = attach_fixed_english_choice_slots(
                detected,
                'english',
                '51a8f187',
                20,
            )
        self.assertEqual(audit['reason'], 'feature_disabled')
        self.assertTrue(all(
            'answer_slots' not in question
            for question in detected['questions']
        ))

    def test_roi_only_transcription_gate_and_guard_correct_semantic_brainfill(self):
        detected = _detected_page20()
        attach_audit = attach_fixed_english_choice_slots(
            detected,
            'english',
            '51a8f187',
            20,
        )
        self.assertTrue(attach_audit['applied'])
        raw = {
            'questions': [
                {'id': qid, 'observed_label': label, 'confidence': 1.0}
                for qid, label in (
                    ('10-1', 'A'),
                    ('10-2', 'B'),
                    ('10-3', 'A'),
                    ('10-4', 'B'),
                    ('10-5', 'B'),
                )
            ],
        }
        transcription, audit = normalize_fixed_english_choice_transcription(
            raw,
            'english',
            '51a8f187',
            20,
        )
        self.assertTrue(audit['accepted'])
        self.assertTrue(audit['expected_labels_not_sent_to_model'])
        self.assertEqual(
            record_fixed_english_choice_transcription(
                detected,
                transcription,
                audit,
            ),
            5,
        )

        graded = {
            'questions': [
                {
                    'id': f'10-{index}',
                    'student_answer': 'A',
                    'correct_answer': 'A' if index in (1, 3, 4) else 'B',
                    'verdict': 'correct',
                    'error_type': '',
                    'understanding': '按短文语义反推。',
                }
                for index in range(1, 6)
            ],
        }
        guard_audit = apply_fixed_english_choice_guard(graded, detected)
        self.assertEqual(guard_audit['applied'], 5)
        target = graded['questions'][3]
        self.assertEqual(target['id'], '10-4')
        self.assertEqual(target['student_answer'], 'B')
        self.assertEqual(target['correct_answer'], 'A')
        self.assertEqual(target['verdict'], 'wrong')
        self.assertEqual(target['error_type'], 'choice_mismatch')
        self.assertEqual(
            target['error_detail'],
            '学生在括号中选择 B，正确选项为 A。',
        )
        self.assertIn('最终保留的黑笔字母为 B', target['understanding'])
        self.assertEqual(target['choice_slot_guard']['pre_guard_student_answer'], 'A')

        target['student_answer'] = 'A'
        target['verdict'] = 'correct'
        target['error_type'] = ''
        target['error_detail'] = ''
        target['answer_slots'] = copy.deepcopy(
            detected['questions'][3]['answer_slots']
        )
        self.assertEqual(reapply_fixed_english_choice_guards(graded), 1)
        self.assertEqual(target['student_answer'], 'B')
        self.assertEqual(target['verdict'], 'wrong')
        self.assertEqual(target['error_type'], 'choice_mismatch')
        self.assertEqual(
            target['choice_slot_guard']['last_pre_restore_student_answer'],
            'A',
        )
        target['error_type'] = 'semantic_brainfill'
        self.assertEqual(reapply_fixed_english_choice_guards(graded), 1)
        self.assertEqual(target['error_type'], 'choice_mismatch')
        self.assertEqual(reapply_fixed_english_choice_guards(graded), 0)

        rejected_raw = copy.deepcopy(raw)
        rejected_raw['questions'][3]['observed_label'] = 'A'
        rejected, rejected_audit = normalize_fixed_english_choice_transcription(
            rejected_raw,
            'english',
            '51a8f187',
            20,
        )
        self.assertFalse(rejected_audit['accepted'])
        self.assertEqual(rejected, {})
        self.assertEqual(
            rejected_audit['regression_mismatches'],
            [{'id': '10-4', 'expected': 'B', 'observed': 'A'}],
        )

    def test_grade_message_adds_five_labeled_rois_only_for_target_page(self):
        detected = _detected_page20()
        captured = {}

        def attach_without_file(page_data, subject, sample_id, page_num, **_kwargs):
            return attach_fixed_english_choice_slots(
                page_data,
                subject,
                sample_id,
                page_num,
            )

        def fake_call(messages, _extra_body, **kwargs):
            captured.setdefault('stages', []).append(kwargs.get('stage_label'))
            captured['messages'] = messages
            if kwargs.get('stage_label') == '英语固定括号 ROI 视觉转写':
                return {
                    'questions': [
                        {'id': qid, 'observed_label': label, 'confidence': 1.0}
                        for qid, label in (
                            ('10-1', 'A'),
                            ('10-2', 'B'),
                            ('10-3', 'A'),
                            ('10-4', 'B'),
                            ('10-5', 'B'),
                        )
                    ],
                }, None
            return {'questions': []}, None

        roi_items = [
            {'question_id': f'10-{index}', 'path': f'roi-{index}.png'}
            for index in range(1, 6)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, 'pass1_json')
            os.makedirs(out_dir)
            out_path = os.path.join(
                out_dir,
                'english_51a8f187_page20.grade.json',
            )
            with mock.patch.object(
                grader_pass1,
                'attach_fixed_english_choice_slots',
                side_effect=attach_without_file,
            ), mock.patch.object(
                grader_pass1,
                'prepare_fixed_english_choice_rois',
                return_value=(roi_items, {'applied': True}),
            ) as prepare_rois, mock.patch.object(
                grader_pass1,
                'image_to_data_uri',
                side_effect=lambda path: f'data:{os.path.basename(path)}',
            ), mock.patch.object(
                grader_pass1,
                '_call_qwen_json_with_retry',
                side_effect=fake_call,
            ):
                grader_pass1.grade_page_questions(
                    'english_51a8f187_page20.png',
                    'english',
                    20,
                    detected,
                    out_path,
                )

        prepare_rois.assert_called_once()
        self.assertEqual(
            captured['stages'],
            ['英语固定括号 ROI 视觉转写', 'Pass 1 批改阶段'],
        )
        messages = captured['messages']
        self.assertNotIn(
            '英语 student_answer 视觉转写锁（最高优先级）',
            messages[0]['content'],
        )
        content = messages[1]['content']
        self.assertEqual(
            sum(item.get('type') == 'image_url' for item in content),
            6,
        )
        for index in range(1, 6):
            self.assertTrue(any(
                item.get('type') == 'text'
                and f'题目 10-{index} 的括号作答槽位 ROI' in item.get('text', '')
                for item in content
            ))
        final_prompt = content[-1]['text']
        self.assertIn('英语括号选择槽位（最高优先级）', final_prompt)
        self.assertIn('不得把 candidate_regions 中的印刷 A/B 当成学生笔迹', final_prompt)
        self.assertIn('绝不允许把正确选项反写为 student_answer', final_prompt)
        self.assertIn('parenthesized_choice', final_prompt)

    def test_grade_message_does_not_prepare_rois_for_other_page(self):
        detected = copy.deepcopy(_detected_page20())
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, 'pass1_json')
            os.makedirs(out_dir)
            out_path = os.path.join(
                out_dir,
                'english_51a8f187_page19.grade.json',
            )
            with mock.patch.object(
                grader_pass1,
                'prepare_fixed_english_choice_rois',
            ) as prepare_rois, mock.patch.object(
                grader_pass1,
                'image_to_data_uri',
                return_value='data:image',
            ), mock.patch.object(
                grader_pass1,
                '_call_qwen_json_with_retry',
                return_value=({'questions': []}, None),
            ):
                grader_pass1.grade_page_questions(
                    'english_51a8f187_page19.png',
                    'english',
                    19,
                    detected,
                    out_path,
                )
        prepare_rois.assert_not_called()
