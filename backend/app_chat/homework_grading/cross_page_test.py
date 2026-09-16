import unittest

from app_chat.homework_grading.cross_page import (
    _can_apply_correction,
    _question_needs_resolution,
    group_needs_resolution,
    merge_corrections,
)


class CrossPageResolutionTest(unittest.TestCase):
    def test_uncertain_cross_page_error_triggers_resolution(self):
        page_data = {
            'boundary': {'continues_from_prev': True},
            'questions': [
                {
                    'id': '4-2',
                    'cross_page': False,
                    'verdict': 'uncertain',
                    'error_type': '跨页缺失：依赖前文材料',
                }
            ],
        }
        question = page_data['questions'][0]
        self.assertTrue(_question_needs_resolution(question, page_data))
        self.assertTrue(group_needs_resolution([29], {29: page_data}))

    def test_merge_uncertain_cross_page_without_cross_page_flag(self):
        all_jsons = {
            29: {
                'boundary': {'continues_from_prev': True},
                'questions': [
                    {
                        'id': '4-2',
                        'cross_page': False,
                        'verdict': 'uncertain',
                        'error_type': '跨页缺失',
                        'student_answer': '鼓鼓，三角形',
                    }
                ],
            }
        }
        result = {
            'corrections': [
                {
                    'page': 29,
                    'id': '4-2',
                    'verdict': 'correct',
                    'correct_answer': '鼓鼓的，三角形的',
                    'error_type': '',
                    'cross_page': True,
                    'cross_page_resolved': True,
                }
            ]
        }
        modified = merge_corrections(all_jsons, result)
        self.assertEqual(len(modified), 1)
        question = all_jsons[29]['questions'][0]
        self.assertEqual(question['verdict'], 'correct')
        self.assertTrue(question.get('cross_page_resolved'))

    def test_skip_non_uncertain_non_cross_page(self):
        page_data = {
            'boundary': {'continues_from_prev': True},
            'questions': [{'id': '1-1', 'cross_page': False, 'verdict': 'correct', 'error_type': ''}],
        }
        self.assertFalse(_can_apply_correction(page_data['questions'][0], page_data))


if __name__ == '__main__':
    unittest.main()
