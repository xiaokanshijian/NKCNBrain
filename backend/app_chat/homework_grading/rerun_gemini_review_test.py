import json
import os
import unittest

from app_chat.homework_grading.rerun_gemini_review_pipeline import (
    prepare_pre_review_pass1_json,
    restore_page_before_self_review,
)


SAMPLE_PAGE9 = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'homework_a96de3a8ba9d',
    'homework_grading',
    'pass1_json',
    'math_a96de3a8_page9.json',
)


class RestorePreReviewTest(unittest.TestCase):
    def test_restore_page9_self_review(self):
        if not os.path.isfile(SAMPLE_PAGE9):
            self.skipTest('sample page9 missing')
        data = json.load(open(SAMPLE_PAGE9, encoding='utf-8'))
        restored = restore_page_before_self_review(data)
        q91 = next(q for q in restored['questions'] if q['id'] == '9-1')
        self.assertEqual(q91['verdict'], 'wrong')
        self.assertEqual(q91['correct_answer'], 'a-b÷18')
        self.assertNotIn('self_review', q91)


if __name__ == '__main__':
    unittest.main()
