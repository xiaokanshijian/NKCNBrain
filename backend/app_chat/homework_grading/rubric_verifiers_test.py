import json
import os
import tempfile
import unittest

from app_chat.homework_grading.verifiers import verify_pass1_dir


CHINESE_SOURCE_SHA256 = (
    '9c44fc825cff56855eb4710f3370022ad30ea9db74c9bd45c5d59bb1ae2cb9ab'
)


class RubricVerifiersTest(unittest.TestCase):
    def _write_page(self, tmp: str, subject: str, questions, page: int = 1):
        path = os.path.join(tmp, f'{subject}_sample_page{page}.json')
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(
                {'page': page, 'subject': subject, 'questions': questions},
                file,
                ensure_ascii=False,
            )
        return path

    def _verify_one(
        self,
        subject: str,
        question,
        *,
        page: int = 1,
        source_document_sha256: str = '',
    ):
        with tempfile.TemporaryDirectory() as tmp:
            page_path = self._write_page(tmp, subject, [question], page=page)
            report_path = os.path.join(tmp, 'verification.json')
            report = verify_pass1_dir(
                subject,
                tmp,
                report_path,
                apply=True,
                source_document_sha256=source_document_sha256,
            )
            with open(page_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
            return report, data['questions'][0]

    def test_source_lock_turns_no_audio_listening_correct_to_uncertain(self):
        report, question = self._verify_one('english', {
            'id': '1',
            'stem_excerpt': 'Listen and number.',
            'student_answer': '1 2 3',
            'correct_answer': '1 2 3',
            'verdict': 'correct',
            'knowledge_point': 'listening',
        })

        self.assertEqual(report['total_discrepancies'], 1)
        self.assertEqual(question['verdict'], 'uncertain')
        self.assertEqual(question['uncertain_reason'], 'no_audio_source')
        self.assertTrue(question['source_lock']['locked'])
        self.assertEqual(question['source_lock']['reason_code'], 'no_audio_source')
        self.assertEqual(question['rubric_checks'][0]['name'], 'source_lock')

    def test_source_lock_is_idempotent_after_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_page(tmp, 'english', [{
                'id': '1',
                'stem_excerpt': 'Listen and number.',
                'student_answer': '1 2 3',
                'correct_answer': '1 2 3',
                'verdict': 'correct',
                'knowledge_point': 'listening',
            }])
            report_path = os.path.join(tmp, 'verification.json')
            first = verify_pass1_dir('english', tmp, report_path, apply=True)
            second = verify_pass1_dir('english', tmp, report_path, apply=True)

        self.assertEqual(first['total_discrepancies'], 1)
        self.assertEqual(second['total_discrepancies'], 0)

    def test_non_listening_english_table_is_not_source_locked(self):
        report, question = self._verify_one('english', {
            'id': '2',
            'stem_excerpt': 'Read, ask and write. 完成表格。',
            'student_answer': "Qu's father, driver, station",
            'correct_answer': None,
            'verdict': 'correct',
            'knowledge_point': 'communication',
        })

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(question['verdict'], 'correct')
        self.assertNotIn('source_lock', question)

    def test_math_rubric_items_are_prompt_only_not_hard_verifier(self):
        report, question = self._verify_one('math', {
            'id': '3',
            'stem_excerpt': '小明走了6千米，小红也走了6千米，一共走了多少千米？',
            'student_answer': '6+6=12千米',
            'correct_answer': '12千米',
            'verdict': 'correct',
            'knowledge_point': 'word_problem',
        })

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(question['verdict'], 'correct')
        self.assertNotIn('verification_result', question)
        self.assertNotIn('rubric_checks', question)

    def test_math_missing_unit_is_not_downgraded_by_hard_rubric(self):
        report, question = self._verify_one('math', {
            'id': '4',
            'stem_excerpt': '这段路长多少千米？',
            'student_answer': '12',
            'correct_answer': '12千米',
            'verdict': 'correct',
            'knowledge_point': 'length_unit',
        })

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(question['verdict'], 'correct')
        self.assertNotIn('verification_result', question)

    def test_math_final_form_is_not_downgraded_by_hard_rubric(self):
        report, question = self._verify_one('math', {
            'id': '5',
            'stem_excerpt': '把下面分数化简成最简分数。',
            'student_answer': '2/4',
            'correct_answer': '1/2',
            'verdict': 'correct',
            'knowledge_point': 'fraction_simplification',
        })

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(question['verdict'], 'correct')
        self.assertNotIn('verification_result', question)

    def test_uncertain_math_question_is_not_forced_by_rubric(self):
        report, question = self._verify_one('math', {
            'id': '7',
            'stem_excerpt': '这段路长多少千米？',
            'student_answer': '12',
            'correct_answer': '12千米',
            'verdict': 'uncertain',
            'knowledge_point': 'length_unit',
        })

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(question['verdict'], 'uncertain')
        self.assertNotIn('verification_result', question)

    def test_fixed_chinese_page12_question5_2_uses_answer_a(self):
        report, question = self._verify_one(
            'chinese',
            {
                'id': '5-2',
                'stem_excerpt': '“黄黄的”指的是（ ）的颜色。',
                'student_answer': 'A',
                'correct_answer': 'D',
                'verdict': 'wrong',
                'error_type': '理解偏差',
            },
            page=12,
            source_document_sha256=CHINESE_SOURCE_SHA256,
        )

        self.assertEqual(report['total_discrepancies'], 1)
        self.assertEqual(question['correct_answer'], 'A')
        self.assertEqual(question['verdict'], 'correct')
        self.assertEqual(question['error_type'], '')
        self.assertEqual(
            question['verification_result']['rule'],
            'fixed_chinese_page12_question5_2_answer',
        )

    def test_fixed_chinese_page41_personification_rule_marks_known_answer_wrong(self):
        report, question = self._verify_one(
            'chinese',
            {
                'id': '三-2',
                'stem_excerpt': (
                    '从“快乐”一词可以看出作者是把小苍蝇当作人来描写的，'
                    '请用这一写法，改写下面的句子。'
                ),
                'student_answer': '一只蜘蛛伸出腿，慢慢的向树干爬去。',
                'correct_answer': None,
                'verdict': 'correct',
                'error_type': '',
                'knowledge_point': 'sentence_rewrite',
            },
            page=41,
            source_document_sha256=CHINESE_SOURCE_SHA256,
        )

        self.assertEqual(report['total_discrepancies'], 1)
        self.assertEqual(question['verdict'], 'wrong')
        self.assertEqual(
            question['error_type'],
            'missing_required_personification',
        )
        self.assertEqual(
            question['rubric_checks'][0]['name'],
            'required_personification',
        )

    def test_fixed_chinese_rules_do_not_apply_to_other_document_hash(self):
        report, question = self._verify_one(
            'chinese',
            {
                'id': '三-2',
                'stem_excerpt': '请用拟人手法改写下面的句子。',
                'student_answer': '一只蜘蛛伸出腿，慢慢的向树干爬去。',
                'verdict': 'correct',
                'knowledge_point': 'sentence_rewrite',
            },
            page=41,
            source_document_sha256='0' * 64,
        )

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(question['verdict'], 'correct')
        self.assertNotIn('verification_result', question)


if __name__ == '__main__':
    unittest.main()
