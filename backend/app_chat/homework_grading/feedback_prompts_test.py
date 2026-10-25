"""合成请求构造验证，不调用模型。"""
import unittest
from unittest.mock import patch
from .feedback_skills_test import runtime_fixture
from .feedback_metadata import resolve_feedback_metadata
from .feedback_skill_matching import compose_skills
from . import prompts


class FeedbackPromptsTest(unittest.TestCase):
    def test_new_scope_never_loads_global_curriculum(self):
        for name in ('初中·初二·物理·试卷.pdf','高中·高二·数学·作业.pdf','大学·大二·嵌入式系统·作业.pdf','小学··英语·作业.pdf'):
            r=runtime_fixture(name)
            with patch.object(prompts,'load_curriculum_labels',side_effect=AssertionError('mutable curriculum')),patch.object(prompts,'get_seed_labels',side_effect=AssertionError('legacy grade')):
                for fn in (prompts.pass1_system,prompts.pass1_detect_system,prompts.pass1_grade_system,prompts.pass1_review_system):
                    text=fn('math',feedback_runtime=r)
                    self.assertNotIn('当前批改对象为4年级',text)
                    self.assertNotIn('<math|chinese|english>',text)
                    self.assertIn(r.context['subject_name'],text)
                    self.assertNotIn('【数学评分细则】',text)

    def test_conditional_rule_and_shared_protocol(self):
        name='小学·四年级·数学·作业.pdf'
        selected,_=compose_skills(resolve_feedback_metadata(name))
        r=runtime_fixture(name,skills=selected)
        text=prompts.pass1_grade_system('math',feedback_runtime=r)
        self.assertEqual(text.count('【数学评分细则】'),1)
        payload={'questions':[{'id':'1','stem_excerpt':'运用了什么运算律','student_answer':'结合律'}]}
        with patch.object(prompts,'_has_math_operation_law_name_question',return_value=True):
            text=prompts.pass1_grade_user_prompt('math',1,payload,feedback_runtime=r)
        self.assertIn('operation_law_name_incomplete',text)

    def test_missing_source_not_fixed_rule(self):
        from .feedback_prompts import condition_matches
        r=runtime_fixture()
        self.assertFalse(condition_matches('fixed_english_transcription',r,page_num=15))
