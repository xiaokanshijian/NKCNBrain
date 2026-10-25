import unittest
from .feedback_request import resolve_feedback_request as resolve


class FeedbackRequestTests(unittest.TestCase):
    def test_unregistered_university_second_year(self):
        result = resolve('试卷.pdf', {'education_level': '大学', 'grade': '大二',
                                     'subject': '嵌入式系统', 'material_type': '试卷'}, 'grading')
        context = result['feedback_context']
        self.assertEqual(result['route'], 'homework_grading')
        self.assertEqual(context['education_level'], 'university')
        self.assertEqual(context['grade_in_level'], 2)
        self.assertIsNone(context['grade_global'])
        self.assertEqual(context['subject_name'], '嵌入式系统')
        self.assertFalse(result['is_k12_homework'])

    def test_explicit_action_beats_cached_classification(self):
        self.assertEqual(resolve('普通名.pdf', requested_action='grading', legacy_attrs={'is_homework_pdf': False})['route'], 'homework_grading')
        self.assertEqual(resolve('小学·二年级·数学·作业.pdf', requested_action='understanding')['route'], 'continuous_image')

    def test_auto_respects_current_declaration_then_existing_observation(self):
        self.assertEqual(resolve('初中·九年级·数学·作业.pdf', legacy_attrs={'is_homework_pdf': False})['route'], 'homework_grading')
        self.assertEqual(resolve('普通名.pdf')['route'], 'continuous_image')
        legacy = resolve('普通名.pdf', legacy_attrs={'is_homework_pdf': True, 'homework_grade': 4})
        self.assertEqual(legacy['route'], 'homework_grading')
        self.assertIsNone(legacy['feedback_context']['grade_global'])

    def test_locked_unknown_and_conflicting_grade(self):
        result = resolve('小学·四年级·数学·作业.pdf', {'grade': None}, reliable_observations={'grade': '四年级'})
        self.assertIsNone(result['feedback_context']['grade_global'])
        conflict = resolve('初中·高二·物理·试卷.pdf', requested_action='grading')
        self.assertEqual(conflict['route'], 'homework_grading')
        self.assertEqual(conflict['feedback_context']['grade_status'], 'conflict')

    def test_nonquestion_and_nonpdf_not_promised(self):
        for filename in ('大学·大二·嵌入式系统·笔记.pdf', '小学·二年级·数学·作业.png'):
            result = resolve(filename, requested_action='grading')
            self.assertFalse(result['feedback_eligible'])
            self.assertEqual(result['route'], 'unsupported')

    def test_invalid_action_and_override_type(self):
        with self.assertRaises(ValueError):
            resolve('试卷.pdf', requested_action='experiment')
        with self.assertRaises(ValueError):
            resolve('试卷.pdf', overrides=[])


if __name__ == '__main__':
    unittest.main()
