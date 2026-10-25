import copy
import unittest

from app_chat.homework_grading.fixed_english_page15_guard import (
    apply_fixed_english_page15_guard,
    reapply_fixed_english_page15_guard,
)
from app_chat.homework_grading.grader_pass1 import _merge_detect_and_grade
from app_chat.homework_grading.grader_pass1_review import apply_review_to_page


ENGLISH_SOURCE_SHA256 = (
    'a6891387d779229ad18a9e367c1b5525514bbb4aa7a29f88873893b2784ed39c'
)


def _page(student_answer: str = (
    "Lingling's father jumping excited\n"
    "Lingling's uncle crying sad"
)):
    return {
        'questions': [{
            'id': '10-1',
            'student_answer': student_answer,
            'correct_answer': None,
            'understanding': '模型按语法补成了 crying。',
            'verdict': 'correct',
            'error_type': '',
        }],
    }


class FixedEnglishPage15GuardTest(unittest.TestCase):
    def test_guard_changes_only_uncle_action_and_marks_parent_partial(self):
        page = _page(
            "Lingling's father crying excited\n"
            "Lingling's uncle crying sad"
        )

        audit = apply_fixed_english_page15_guard(
            page,
            page_num=15,
            source_document_sha256=ENGLISH_SOURCE_SHA256,
        )
        question = page['questions'][0]

        self.assertTrue(audit['applied'])
        self.assertEqual(
            question['student_answer'],
            "Lingling's father crying excited\nLingling's uncle cry sad",
        )
        self.assertEqual(
            question['correct_answer'],
            "Lingling's father crying excited\nLingling's uncle crying sad",
        )
        self.assertEqual(question['verdict'], 'partial')
        self.assertEqual(question['error_type'], 'verb_form_incomplete')
        self.assertIn('最终保留的是 cry', question['understanding'])

    def test_existing_cry_is_also_locked_against_semantic_normalization(self):
        page = _page(
            "Lingling's father jumping excited\n"
            "Lingling's uncle cry sad"
        )
        apply_fixed_english_page15_guard(
            page,
            page_num=15,
            source_document_sha256=ENGLISH_SOURCE_SHA256,
        )
        question = page['questions'][0]
        self.assertEqual(
            question['student_answer'],
            "Lingling's father jumping excited\nLingling's uncle cry sad",
        )
        self.assertIn("uncle crying sad", question['correct_answer'])
        self.assertEqual(question['verdict'], 'partial')

    def test_guard_survives_review_and_direct_downstream_mutation(self):
        page = _page()
        apply_fixed_english_page15_guard(
            page,
            page_num=15,
            source_document_sha256=ENGLISH_SOURCE_SHA256,
        )
        review = {
            'items': [{
                'id': '10-1',
                'ok': False,
                'reason': '按语法规范化为 crying',
                'fix': {
                    'student_answer': (
                        "Lingling's father jumping excited\n"
                        "Lingling's uncle crying sad"
                    ),
                    'verdict': 'correct',
                    'error_type': '',
                },
            }],
            'stats': {},
        }
        self.assertEqual(apply_review_to_page(page, review), 1)
        question = page['questions'][0]
        self.assertIn("uncle cry sad", question['student_answer'])
        self.assertEqual(question['verdict'], 'partial')
        self.assertEqual(
            review['stats']['fixed_english_page15_guards_restored'],
            1,
        )

        downstream = copy.deepcopy(page)
        downstream['questions'][0]['student_answer'] = (
            "Lingling's father jumping excited\n"
            "Lingling's uncle crying sad"
        )
        downstream['questions'][0]['verdict'] = 'correct'
        self.assertEqual(reapply_fixed_english_page15_guard(downstream), 1)
        self.assertIn(
            "uncle cry sad",
            downstream['questions'][0]['student_answer'],
        )
        self.assertEqual(downstream['questions'][0]['verdict'], 'partial')

    def test_merge_preserves_guard_and_error_detail(self):
        graded = _page()
        apply_fixed_english_page15_guard(
            graded,
            page_num=15,
            source_document_sha256=ENGLISH_SOURCE_SHA256,
        )
        detected = {
            'page': 15,
            'subject': 'english',
            'questions': [{
                'id': '10-1',
                'parent_group_id': '10',
                'stem_excerpt': "Lingling's father row...",
                'position': [100, 700, 900, 950],
            }],
        }

        merged = _merge_detect_and_grade(detected, graded, 'english', 15)
        question = merged['questions'][0]
        self.assertIn('fixed_english_page15_guard', question)
        self.assertEqual(question['error_type'], 'verb_form_incomplete')
        self.assertIn('第三行 Action', question['error_detail'])

    def test_wrong_document_hash_fails_closed(self):
        page = _page()
        original = copy.deepcopy(page)
        audit = apply_fixed_english_page15_guard(
            page,
            page_num=15,
            source_document_sha256='0' * 64,
            sample_id='51a8f187',
        )
        self.assertFalse(audit['approved'])
        self.assertEqual(page, original)


if __name__ == '__main__':
    unittest.main()
