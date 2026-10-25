import json
import os
import tempfile
import unittest

from app_chat.homework_grading.answer_statement_verifier import (
    has_answer_statement_unit,
    has_final_unit,
    has_final_answer_statement,
    has_solution_final_unit,
    split_solution_and_answer_statement,
    verify_answer_statements,
)
from app_chat.homework_grading.grader_pass1 import (
    _is_empty_auto_layout_artifact,
    _merge_detect_and_grade,
    _normalize_detect_result,
)
from app_chat.homework_grading.question_type import (
    is_math_fill_blank_style_question,
    normalize_final_unit_requirement,
)


class AnswerStatementVerifierTest(unittest.TestCase):
    def _write_page(self, tmp: str, questions):
        path = os.path.join(tmp, 'math_sample_page1.json')
        with open(path, 'w', encoding='utf-8') as file:
            json.dump({'page': 1, 'subject': 'math', 'questions': questions}, file, ensure_ascii=False)
        return path

    def test_answer_statement_detector_is_conservative(self):
        self.assertFalse(has_final_answer_statement('36×365=13140(千克)'))
        self.assertFalse(has_final_answer_statement('a+b'))
        self.assertTrue(has_final_answer_statement('答：会浪费13140千克水。'))
        self.assertTrue(has_final_answer_statement('一共是12千米。'))
        self.assertTrue(has_final_answer_statement('12个苹果'))

    def test_final_unit_detector_covers_sample_units(self):
        for answer in ('1530(元)', '91根', '120面', '7小时', '78m²'):
            with self.subTest(answer=answer):
                self.assertTrue(has_final_unit(answer))
        self.assertFalse(has_final_unit('答：还剩120。'))
        self.assertFalse(has_final_unit('答：先分类再计算。'))

    def test_solution_and_answer_statement_units_are_separated(self):
        answer = 'm÷12=3600÷12=300\n答：平均每月生产300个'
        solution, statement = split_solution_and_answer_statement(answer)

        self.assertEqual(solution, 'm÷12=3600÷12=300')
        self.assertEqual(statement, '平均每月生产300个')
        self.assertFalse(has_solution_final_unit(answer))
        self.assertTrue(has_answer_statement_unit(answer))

    def test_inline_answer_marker_after_number_separates_units(self):
        samples = (
            (
                'm÷12=3600÷12=300答每月生产300个',
                'm÷12=3600÷12=300',
                '每月生产300个',
            ),
            (
                'a-(b÷18)=20-216÷18=8答比二楼多8排座位',
                'a-(b÷18)=20-216÷18=8',
                '比二楼多8排座位',
            ),
        )
        for answer, expected_solution, expected_statement in samples:
            with self.subTest(answer=answer):
                solution, statement = split_solution_and_answer_statement(answer)
                self.assertEqual(solution, expected_solution)
                self.assertEqual(statement, expected_statement)
                self.assertFalse(has_solution_final_unit(answer))
                self.assertTrue(has_answer_statement_unit(answer))

    def test_only_last_solution_value_controls_process_unit_rule(self):
        answer = '600-50×5=350(千米)\n350÷50=7\n答：需要行驶7小时。'
        self.assertFalse(has_solution_final_unit(answer))

        answer_with_final_unit = answer.replace('350÷50=7', '350÷50=7(小时)')
        self.assertTrue(has_solution_final_unit(answer_with_final_unit))

    def test_application_problem_correct_without_answer_statement_becomes_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            page_path = self._write_page(tmp, [{
                'id': '4-2',
                'stem_excerpt': '平均每天浪费多少千克水？',
                'student_answer': '36×365=13140(千克)',
                'correct_answer': '13140千克',
                'verdict': 'correct',
                'error_type': '',
                'is_application_major_problem': True,
            }])
            report_path = os.path.join(tmp, 'answer_statement.json')

            report = verify_answer_statements('math', tmp, report_path, apply=True)
            with open(page_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

        question = data['questions'][0]
        self.assertEqual(report['total_discrepancies'], 1)
        self.assertEqual(report['corrections_applied'], 1)
        self.assertEqual(question['verdict'], 'partial')
        self.assertEqual(question['error_type'], '缺少最终答话')
        self.assertEqual(question['post_review_guard']['previous']['verdict'], 'correct')
        self.assertEqual(question['rubric_checks'][0]['name'], 'missing_answer_statement')

    def test_non_application_or_existing_answer_statement_is_not_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            page_path = self._write_page(tmp, [
                {
                    'id': '1',
                    'stem_excerpt': '计算。',
                    'student_answer': '36×365=13140',
                    'verdict': 'correct',
                    'is_application_major_problem': False,
                },
                {
                    'id': '2',
                    'stem_excerpt': '平均每天浪费多少千克水？',
                    'student_answer': '答：会浪费13140千克水。',
                    'verdict': 'correct',
                    'is_application_major_problem': True,
                },
                {
                    'id': '3',
                    'stem_excerpt': '一共有多少个苹果？',
                    'student_answer': '12个苹果',
                    'verdict': 'correct',
                    'is_application_major_problem': True,
                },
            ])
            report_path = os.path.join(tmp, 'answer_statement.json')

            report = verify_answer_statements('math', tmp, report_path, apply=True)
            with open(page_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual([q['verdict'] for q in data['questions']], ['correct', 'correct', 'correct'])

    def test_letter_substitution_answers_with_units_become_partial(self):
        sample_questions = [
            ('4-2', '(2)当x=15,y=12时，一共花了多少钱？', '=1530(元)\n答：一共花了1530元。'),
            ('5-2', '(2)当n=30时，需要多少根小棒？', '=91(根)\n答：需要91根小棒。'),
            ('10-2', '(2)当x=6时，还剩多少面小彩旗没做？', '480-360=120(面)\n答：还剩120面小彩旗没做。'),
            ('11-2', '(2)当a=5时，剩下的路程需要行驶几小时？', '350÷50=7(小时)\n答：需要行驶7小时。'),
            ('12-2', '(2)当a=3时，总面积是多少平方米？', '=78(m²)\n答：总面积是78平方米。'),
        ]
        questions = [
            {
                'id': qid,
                'parent_group_id': qid.split('-')[0],
                'stem_excerpt': stem,
                'student_answer': answer,
                'correct_answer': answer,
                'verdict': 'correct',
                'error_type': '',
                'is_application_major_problem': True,
            }
            for qid, stem, answer in sample_questions
        ]
        with tempfile.TemporaryDirectory() as tmp:
            page_path = self._write_page(tmp, questions)
            report_path = os.path.join(tmp, 'answer_statement.json')

            report = verify_answer_statements('math', tmp, report_path, apply=True)
            with open(page_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

        self.assertEqual(report['total_discrepancies'], 5)
        self.assertEqual(report['corrections_applied'], 5)
        for question in data['questions']:
            self.assertEqual(question['verdict'], 'partial')
            self.assertEqual(question['error_type'], '代入求值的计算过程末值不应加单位')
            self.assertEqual(question['post_review_guard']['rule'], 'math_substitution_process_final_unit')
            self.assertEqual(question['rubric_checks'][0]['name'], 'substitution_process_final_unit')

    def test_substitution_process_without_unit_and_answer_with_unit_remains_correct(self):
        question = {
            'id': '5-2',
            'parent_group_id': '5',
            'stem_excerpt': '(2)当n=30时，需要多少根小棒？',
            'student_answer': 'n×3+1=30×3+1=91\n答：需要91根小棒。',
            'verdict': 'correct',
            'is_application_major_problem': True,
        }
        self.assertEqual(normalize_final_unit_requirement(question, 'math'), 'forbidden')
        with tempfile.TemporaryDirectory() as tmp:
            page_path = self._write_page(tmp, [question])
            report_path = os.path.join(tmp, 'answer_statement.json')
            report = verify_answer_statements('math', tmp, report_path, apply=True)
            with open(page_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(data['questions'][0]['verdict'], 'correct')

    def test_substitution_answer_statement_without_unit_becomes_partial(self):
        question = {
            'id': '5-2',
            'parent_group_id': '5',
            'stem_excerpt': '(2)当n=30时，需要多少根小棒？',
            'student_answer': 'n×3+1=30×3+1=91\n答：需要91。',
            'verdict': 'correct',
            'is_application_major_problem': True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            page_path = self._write_page(tmp, [question])
            report_path = os.path.join(tmp, 'answer_statement.json')
            report = verify_answer_statements('math', tmp, report_path, apply=True)
            with open(page_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

        self.assertEqual(report['total_discrepancies'], 1)
        self.assertEqual(data['questions'][0]['verdict'], 'partial')
        self.assertEqual(data['questions'][0]['error_type'], '代入求值的答话缺少单位')

    def test_regression_samples_keep_answer_units_without_process_units(self):
        questions = [
            {
                'id': '8-2',
                'parent_group_id': '8',
                'stem_excerpt': '(2)当m=3600时，平均每月生产多少个零件？',
                'student_answer': 'm÷12=3600÷12=300\n答：平均每月生产300个',
                'verdict': 'correct',
                'is_application_major_problem': True,
            },
            {
                'id': '7-2',
                'parent_group_id': '7',
                'stem_excerpt': '(2)当n=5时，这棵树高多少米？',
                'student_answer': 'n×3+2=5×3+2=17\n答：这棵树高17米。',
                'verdict': 'correct',
                'is_application_major_problem': True,
            },
            {
                'id': '9-2',
                'parent_group_id': '9',
                'stem_excerpt': '(2)当a=20，b=216时，比二楼多多少排座位？',
                'student_answer': 'a-(b÷18)=20-216÷18=8答比二楼多8排座位',
                'verdict': 'correct',
                'is_application_major_problem': True,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            page_path = self._write_page(tmp, questions)
            report_path = os.path.join(tmp, 'answer_statement.json')
            report = verify_answer_statements('math', tmp, report_path, apply=True)
            with open(page_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(
            [q['verdict'] for q in data['questions']],
            ['correct', 'correct', 'correct'],
        )

    def test_non_substitution_ratio_answer_is_not_treated_as_process_unit(self):
        question = {
            'id': '4-1',
            'parent_group_id': '4',
            'stem_excerpt': '(1)北京故宫的占地面积是该博物馆的多少倍？',
            'student_answer': '720000÷40000=18\n答：是博物馆的18倍。',
            'verdict': 'correct',
            'is_application_major_problem': True,
            'final_unit_requirement': 'forbidden',
        }
        with tempfile.TemporaryDirectory() as tmp:
            page_path = self._write_page(tmp, [question])
            report_path = os.path.join(tmp, 'answer_statement.json')
            report = verify_answer_statements('math', tmp, report_path, apply=True)
            with open(page_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(data['questions'][0]['verdict'], 'correct')

    def test_fill_blank_style_problem_is_not_changed_even_if_flagged_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            page_path = self._write_page(tmp, [{
                'id': '4-1',
                'parent_stem_excerpt': '看图填空：裙子现价是60元，减价x元。',
                'stem_excerpt': '(1)这条裙子原价是( )元。',
                'student_answer': '60+x',
                'verdict': 'correct',
                'is_application_major_problem': True,
            }])
            report_path = os.path.join(tmp, 'answer_statement.json')

            report = verify_answer_statements('math', tmp, report_path, apply=True)
            with open(page_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

        self.assertEqual(report['total_discrepancies'], 0)
        self.assertEqual(data['questions'][0]['verdict'], 'correct')
        self.assertNotIn('post_review_guard', data['questions'][0])

    def test_non_math_subject_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = os.path.join(tmp, 'answer_statement.json')
            report = verify_answer_statements('chinese', tmp, report_path, apply=True)

        self.assertTrue(report['skipped'])
        self.assertEqual(report['total_discrepancies'], 0)

    def test_detect_normalization_preserves_application_flag_for_math_only(self):
        data = {
            'questions': [{
                'id': '1',
                'is_application_major_problem': '是',
            }]
        }

        math = _normalize_detect_result(dict(data), 'math', 1)
        chinese = _normalize_detect_result(dict(data), 'chinese', 1)

        self.assertTrue(math['questions'][0]['is_application_major_problem'])
        self.assertFalse(chinese['questions'][0]['is_application_major_problem'])

    def test_detect_normalization_drops_empty_auto_layout_artifact(self):
        normalized = _normalize_detect_result({
            'questions': [
                {
                    'id': '1',
                    'stem_excerpt': '给加点字选择正确的读音。',
                    'position': [100, 100, 500, 200],
                },
                {
                    'id': 'auto-2',
                    'stem_excerpt': '',
                    'position': [],
                    'cross_page': False,
                },
            ],
        }, 'chinese', 28)

        self.assertEqual(
            [question['id'] for question in normalized['questions']],
            ['1'],
        )
        self.assertEqual(normalized['layout_artifacts'], [{
            'id': 'auto-2',
            'reason': 'empty_auto_question',
        }])
        self.assertTrue(_is_empty_auto_layout_artifact({
            'id': 'auto-2',
            'verdict': 'uncertain',
        }))
        self.assertFalse(_is_empty_auto_layout_artifact({
            'id': 'auto-2',
            'stem_excerpt': '二、连线。',
            'verdict': 'uncertain',
        }))

    def test_detect_normalization_excludes_fill_blank_application_style_questions(self):
        data = {
            'questions': [
                {
                    'id': '4-1',
                    'parent_stem_excerpt': '看图填空：裙子现价是60元，减价x元。',
                    'stem_excerpt': '(1)这条裙子原价是( )元。',
                    'is_application_major_problem': True,
                },
                {
                    'id': '5-1',
                    'parent_stem_excerpt': '植树节来临，学校开展“我与小树共成长”活动，四年级6个班共植树m棵。',
                    'stem_excerpt': '(1)若平均每个班植树a棵，则m=( )。',
                    'is_application_major_problem': True,
                },
                {
                    'id': '7-1',
                    'parent_stem_excerpt': '中华红叶杨生长迅速，每年大约增长3米。',
                    'stem_excerpt': '(1)如果栽种时树高2米，n年后，这棵树高多少米？',
                    'is_application_major_problem': True,
                },
            ]
        }

        normalized = _normalize_detect_result(data, 'math', 8)

        self.assertTrue(is_math_fill_blank_style_question(normalized['questions'][0]))
        self.assertFalse(normalized['questions'][0]['is_application_major_problem'])
        self.assertFalse(normalized['questions'][1]['is_application_major_problem'])
        self.assertTrue(normalized['questions'][2]['is_application_major_problem'])

    def test_merge_keeps_layout_application_flag_when_grade_omits_it(self):
        merged = _merge_detect_and_grade(
            {
                'page': 1,
                'subject': 'math',
                'questions': [{
                    'id': '1',
                    'is_application_major_problem': True,
                }],
            },
            {
                'questions': [{
                    'id': '1',
                    'student_answer': '6+6=12',
                    'verdict': 'correct',
                }]
            },
            'math',
            1,
        )

        self.assertTrue(merged['questions'][0]['is_application_major_problem'])

    def test_detect_normalization_preserves_valid_chinese_pronunciation_slots(self):
        normalized = _normalize_detect_result({
            'questions': [{
                'id': '1',
                'stem_excerpt': '给加点字选择正确的读音，画“√”。',
                'answer_slots': [{
                    'slot_id': 'model-noncanonical-id',
                    'target': '珀',
                    'slot_position': [600, 200, 760, 250],
                    'candidate_regions': [
                        {'label': 'bó', 'region': [620, 205, 670, 245]},
                        {'label': 'pò', 'position': [690, 205, 740, 245]},
                    ],
                    'mark_position': [700, 210, 735, 245],
                    'layout_confidence': 95,
                }],
            }],
        }, 'chinese', 41)

        question = normalized['questions'][0]
        self.assertEqual(question['answer_slots'][0]['slot_id'], '1:珀')
        self.assertEqual(
            [item['label'] for item in question['answer_slots'][0]['candidate_regions']],
            ['bó', 'pò'],
        )
        self.assertEqual(question['answer_slots'][0]['layout_confidence'], 95)

    def test_detect_normalization_drops_incomplete_or_nonmatching_pronunciation_slots(self):
        incomplete = _normalize_detect_result({
            'questions': [{
                'id': '1',
                'stem_excerpt': '给加点字选择正确的读音，画“√”。',
                'answer_slots': [{
                    'target': '珀',
                    'slot_position': [600, 200, 760, 250],
                    'candidate_regions': [
                        {'label': 'pò', 'position': [690, 205, 740, 245]},
                    ],
                    'mark_position': [700, 210, 735, 245],
                }],
            }],
        }, 'chinese', 41)
        unrelated = _normalize_detect_result({
            'questions': [{
                'id': '1',
                'stem_excerpt': '读拼音，写词语。',
                'answer_slots': [{
                    'target': '珀',
                    'slot_position': [600, 200, 760, 250],
                    'candidate_regions': [
                        {'label': 'bó', 'position': [620, 205, 670, 245]},
                        {'label': 'pò', 'position': [690, 205, 740, 245]},
                    ],
                    'mark_position': [700, 210, 735, 245],
                }],
            }],
        }, 'chinese', 41)

        self.assertNotIn('answer_slots', incomplete['questions'][0])
        self.assertNotIn('answer_slots', unrelated['questions'][0])

    def test_merge_normalizes_wrapped_pronunciation_answer_and_keeps_slots(self):
        merged = _merge_detect_and_grade(
            {
                'page': 41,
                'subject': 'chinese',
                'questions': [{
                    'id': '1',
                    'stem_excerpt': '给加点字选择正确的读音，画“√”。',
                    'answer_slots': [
                        {
                            'target': '嗡',
                            'slot_position': [200, 200, 400, 240],
                            'candidate_regions': [
                                {'label': 'wēng', 'position': [250, 205, 315, 235]},
                                {'label': 'wěng', 'position': [325, 205, 390, 235]},
                            ],
                            'mark_position': [265, 210, 310, 235],
                        },
                        {
                            'target': '珀',
                            'slot_position': [600, 200, 760, 250],
                            'candidate_regions': [
                                {'label': 'bó', 'position': [620, 205, 670, 245]},
                                {'label': 'pò', 'position': [690, 205, 740, 245]},
                            ],
                            'mark_position': [700, 210, 735, 245],
                        },
                    ],
                }],
            },
            {
                'questions': [{
                    'id': '1',
                    'student_answer': '嗡(wēng)√, 珀(pò)√',
                    'verdict': 'correct',
                }],
            },
            'chinese',
            41,
        )

        question = merged['questions'][0]
        self.assertEqual(question['student_answer'], 'wēng, pò')
        self.assertEqual(len(question['answer_slots']), 2)

    def test_detect_and_merge_infer_forbidden_unit_policy_for_letter_substitution(self):
        detected = _normalize_detect_result({
            'questions': [{
                'id': '12-2',
                'parent_group_id': '12',
                'stem_excerpt': '(2)当 a=3 时，总面积是多少平方米？',
                'is_application_major_problem': True,
                'final_unit_requirement': 'required',
            }]
        }, 'math', 14)
        self.assertEqual(detected['questions'][0]['final_unit_requirement'], 'forbidden')

        merged = _merge_detect_and_grade(
            detected,
            {'questions': [{'id': '12-2', 'student_answer': '答：78平方米。', 'verdict': 'correct'}]},
            'math',
            14,
        )
        self.assertEqual(merged['questions'][0]['final_unit_requirement'], 'forbidden')


if __name__ == '__main__':
    unittest.main()
