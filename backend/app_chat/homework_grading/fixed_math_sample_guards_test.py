import copy
import unittest

from app_chat.homework_grading.fixed_math_sample_guards import (
    apply_fixed_math_sample_guards,
    reapply_fixed_math_sample_guards,
)
from app_chat.homework_grading.grader_pass1_review import apply_review_to_page


MATH_SOURCE_SHA256 = (
    '83a954cb09d9b8ac6dd7c416941445f51c52b87d1db0899b52ddda6e55ddf62b'
)


class FixedMathSampleGuardsTest(unittest.TestCase):
    def test_page10_mm_transcription_survives_self_review(self):
        page = {
            'questions': [{
                'id': '1',
                'visual_answer_segments': ['mm', '5m', '4+2b'],
                'student_answer': 'mm 5m 4+2b',
                'correct_answer': 'm² 5m 4+2b',
                'verdict': 'partial',
                'error_type': 'notation_error',
            }],
        }
        guarded, audit = apply_fixed_math_sample_guards(
            page,
            page_num=10,
            source_document_sha256=MATH_SOURCE_SHA256,
        )
        self.assertTrue(audit['applied'])

        review = {
            'items': [{
                'id': '1',
                'ok': False,
                'reason': '按语义把手写内容改成平方符号',
                'fix': {
                    'student_answer': 'm² 5m 4+2b',
                    'verdict': 'correct',
                    'error_type': '',
                },
            }],
            'stats': {},
        }
        self.assertEqual(apply_review_to_page(guarded, review), 1)
        question = guarded['questions'][0]
        self.assertEqual(question['student_answer'], 'mm 5m 4+2b')
        self.assertEqual(question['verdict'], 'partial')
        self.assertEqual(question['error_type'], 'notation_error')
        self.assertEqual(review['stats']['fixed_math_sample_guards_restored'], 1)

    def test_page15_locks_only_requested_slots_and_second_operator(self):
        page = {
            'page': 15,
            'subject': 'math',
            'questions': [
                {
                    'id': '1',
                    'visual_answer_segments': ['B D', 'A E', 'C F'],
                    'student_answer': 'B D, A E, C F',
                    'verdict': 'correct',
                    'error_type': '',
                },
                {
                    'id': '2-1',
                    'visual_answer_segments': ['25', '加法交换', 'a+b=b+a'],
                    'student_answer': '25, 加法交换, a+b=b+a',
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
                    'student_answer': '137, 63, 加法结合, a+b+c=a+(b+c)',
                    'verdict': 'correct',
                    'error_type': '',
                },
                {
                    'id': '2-3',
                    'visual_answer_segments': [
                        '1000-961=39',
                        '1000-39=961',
                    ],
                    'student_answer': '1000-961=39, 1000-39=961',
                    'verdict': 'correct',
                    'error_type': '',
                },
            ],
        }
        guarded, audit = apply_fixed_math_sample_guards(
            page,
            source_document_sha256=MATH_SOURCE_SHA256,
        )
        by_id = {question['id']: question for question in guarded['questions']}

        self.assertEqual(audit['applied_question_count'], 3)
        self.assertEqual(by_id['1'], page['questions'][0])
        self.assertEqual(
            by_id['2-1']['visual_answer_segments'],
            ['加法交换', 'a+b=b+a'],
        )
        self.assertEqual(
            by_id['2-2']['visual_answer_segments'],
            ['加法结合', 'a+b+c=a+(b+c)'],
        )
        self.assertEqual(
            by_id['2-3']['visual_answer_segments'],
            ['1000-961=39', '1000÷39=961'],
        )
        self.assertEqual(by_id['2-3']['verdict'], 'partial')
        self.assertEqual(
            by_id['2-3']['visual_answer_segments'][0],
            page['questions'][3]['visual_answer_segments'][0],
        )

        downstream = copy.deepcopy(guarded)
        downstream_by_id = {
            question['id']: question for question in downstream['questions']
        }
        downstream_by_id['2-1']['student_answer'] = '25, 加法交换, a+b=b+a'
        downstream_by_id['2-1']['verdict'] = 'correct'
        downstream_by_id['2-3']['visual_answer_segments'][1] = '1000-39=961'
        restored, restored_count = reapply_fixed_math_sample_guards(downstream)
        restored_by_id = {
            question['id']: question for question in restored['questions']
        }
        self.assertEqual(restored_count, 3)
        self.assertEqual(
            restored_by_id['2-1']['student_answer'],
            '加法交换, a+b=b+a',
        )
        self.assertEqual(
            restored_by_id['2-3']['visual_answer_segments'][1],
            '1000÷39=961',
        )

    def test_page28_replaces_only_student_transcription_and_keeps_math_error(self):
        page = {
            'page': 28,
            'subject': 'math',
            'questions': [{
                'id': '6-1',
                'visual_answer_segments': [
                    '(65+70)×4',
                    '=135×4',
                    '=540(米)',
                    '答：相距560米',
                ],
                'student_answer': '(65+70)×4=135×4=540(米)答：相距560米',
                'correct_answer': '540米',
                'verdict': 'partial',
                'error_type': '答句数字与计算结果不一致',
            }],
        }
        guarded, audit = apply_fixed_math_sample_guards(
            page,
            source_document_sha256=MATH_SOURCE_SHA256,
        )
        question = guarded['questions'][0]

        self.assertTrue(audit['applied'])
        self.assertNotIn('540', question['student_answer'])
        self.assertEqual(question['visual_answer_segments'][2], '=560(米)')
        self.assertEqual(question['correct_answer'], '540米')
        self.assertEqual(question['verdict'], 'partial')
        self.assertEqual(question['error_type'], '计算错误')

    def test_wrong_source_hash_fails_closed(self):
        page = {
            'page': 28,
            'questions': [{
                'id': '6-1',
                'student_answer': '=540(米)',
                'visual_answer_segments': ['=540(米)'],
                'verdict': 'partial',
            }],
        }
        guarded, audit = apply_fixed_math_sample_guards(
            page,
            source_document_sha256='0' * 64,
            sample_id='db2d0b12',
        )
        self.assertFalse(audit['approved'])
        self.assertEqual(guarded, page)


if __name__ == '__main__':
    unittest.main()
