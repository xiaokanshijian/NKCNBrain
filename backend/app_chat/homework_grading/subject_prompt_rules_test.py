import unittest

from app_chat.homework_grading.prompts import (
    pass1_detect_system,
    pass1_grade_system,
    pass1_review_system,
    pass1_review_user_prompt,
)


class SubjectPromptRulesTest(unittest.TestCase):
    def test_chinese_prompt_contains_subjective_and_visual_form_rules(self):
        prompt = pass1_grade_system('chinese', grade=4, stage=2)
        self.assertIn('言之有理', prompt)
        self.assertIn('读拼音', prompt)
        self.assertIn('结合语境写字词', prompt)
        self.assertIn('看拼音', prompt)
        self.assertIn('字形错误', prompt)
        self.assertIn('错别字', prompt)
        self.assertIn('斜杠', prompt)
        self.assertIn('田字格', prompt)
        self.assertIn('左上', prompt)
        self.assertIn('部首', prompt)
        self.assertIn('其它语文题', prompt)
        self.assertIn('不需要刻意做汉字部件级字形审查', prompt)
        self.assertNotIn('默写要逐字核查字形部件', prompt)
        self.assertNotIn('选字组词', prompt)

    def test_english_prompt_contains_communicative_tolerance_rules(self):
        prompt = pass1_grade_system('english', grade=4, stage=2)
        self.assertIn('交际意图', prompt)
        self.assertIn('轻微拼写', prompt)
        self.assertIn('不要以「缺少对话原文/来源文本」为由设为 uncertain', prompt)

    def test_math_detect_prompt_contains_double_column_rules(self):
        prompt = pass1_detect_system('math', grade=4, stage=2)
        self.assertIn('双栏', prompt)
        self.assertIn('auto-*', prompt)
        self.assertIn('N-2', prompt)

    def test_review_prompt_supports_error_type_fix(self):
        prompt = pass1_review_system('chinese', grade=4, stage=2)
        self.assertIn('wrong/uncertain', prompt)
        self.assertNotIn('wrong/partial/uncertain', prompt)
        self.assertIn('读拼音', prompt)
        self.assertIn('涂改', prompt)
        self.assertIn('斜杠', prompt)
        self.assertIn('田字格', prompt)
        self.assertIn('左上', prompt)
        self.assertIn('fix.error_type', prompt)
        self.assertIn('字形错误', prompt)
        self.assertIn('不要直接相信 student_answer', prompt)
        self.assertNotIn('翔', prompt)
        self.assertNotIn('赖', prompt)
        self.assertNotIn('藤', prompt)
        self.assertNotIn('蔬', prompt)

    def test_review_user_prompt_lifts_focus_items(self):
        prompt = pass1_review_user_prompt('chinese', 3, {
            'questions': [{
                'id': '3-1',
                'review_focus': 'chinese_pinyin_words',
                'stem_excerpt': '读拼音，写词语。',
                'student_answer': '滑翔',
            }]
        })
        self.assertIn('需重点复核项', prompt)
        self.assertNotIn('高风险项', prompt)
        self.assertIn('3-1', prompt)
        self.assertIn('滑翔', prompt)
        self.assertIn('student_answer 只是上一轮模型转写草稿', prompt)
        self.assertIn('重新辨认', prompt)
        self.assertIn('田字格外', prompt)
        self.assertIn('correct_answer', prompt)
        self.assertIn('visual_answer', prompt)
        self.assertIn('必须写 visual_answer', prompt)


if __name__ == '__main__':
    unittest.main()
