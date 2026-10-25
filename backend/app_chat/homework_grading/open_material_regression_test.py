"""开放材料跨页回归；仅使用合成数据，不调用真实模型。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import cross_page, grader_pass1_review, grader_pass2
from .feedback_runtime import freeze_feedback_runtime, stamp_feedback
from .feedback_skills_test import runtime_fixture
from .memory import build_memory
from .utils import safe_json_dump, safe_json_load


class OpenMaterialCrossPageRegressionTest(unittest.TestCase):
    def test_review_clears_stale_boundary_error_when_adjacent_page_exists(self):
        runtime = runtime_fixture('初中·初一·语文·作文.pdf')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page1_path = root / 'composition_page1.json'
            page2_path = root / 'composition_page2.json'
            review_path = root / 'composition_page1.review.json'
            page1 = {
                'page': 1,
                'boundary': {
                    'continues_from_prev': False,
                    'continues_to_next': True,
                    'description_next': '段落延续到下一页',
                },
                'questions': [{
                    'id': 'auto-1',
                    'student_answer': '第一页可见作文内容',
                    'understanding': '内容将在第二页继续',
                    'verdict': 'partial',
                    'error_type': '跨页截断，无法评估全文结构与字数达标情况',
                    'cross_page': True,
                    'cross_page_note': '段落延续至下一页',
                    'self_review': {
                        'ok': False,
                        'previous': {'verdict': 'uncertain'},
                        'applied': True,
                    },
                }],
            }
            page2 = {
                'page': 2,
                'boundary': {'continues_from_prev': True, 'continues_to_next': False},
                'questions': [],
            }
            review = {
                'page': 1,
                'items': [{
                    'id': 'auto-1', 'ok': False,
                    'reason': '不能仅因跨页判 uncertain',
                    'fix': {'verdict': 'partial'},
                }],
                'stats': {'applied': 1},
            }
            safe_json_dump(page1_path, stamp_feedback(page1, runtime, 'review'))
            safe_json_dump(page2_path, stamp_feedback(page2, runtime, 'review'))
            safe_json_dump(review_path, stamp_feedback(review, runtime, 'review'))

            reconciled = grader_pass1_review._reconcile_open_material_boundary_errors(
                [str(page1_path), str(page2_path)], feedback_runtime=runtime,
            )
            final_page = safe_json_load(page1_path)
            final_review = safe_json_load(review_path)
            memory = build_memory(
                str(root), 'chinese', 'synthetic', feedback_runtime=runtime,
            )

        self.assertEqual(reconciled, 1)
        question = final_page['questions'][0]
        self.assertEqual(question['verdict'], 'uncertain')
        self.assertEqual(question['error_type'], '')
        self.assertTrue(question['material_check']['blocks_assessment'])
        self.assertTrue(question['cross_page'])
        self.assertEqual(question['cross_page_note'], '段落延续至下一页')
        self.assertTrue(final_page['boundary']['continues_to_next'])
        self.assertEqual(final_review['items'][0]['fix']['verdict'], 'uncertain')
        self.assertEqual(final_review['items'][0]['fix']['error_type'], '')
        self.assertEqual(memory['error_questions'][0]['verdict'], 'uncertain')
        self.assertEqual(memory['error_questions'][0]['error_type'], '')
        self.assertEqual(memory['error_type_distribution'], {})

    def test_question_material_keeps_existing_cross_page_error_policy(self):
        runtime = runtime_fixture('初中·初一·语文·作业.pdf')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / 'homework_page1.json', root / 'homework_page2.json']
            safe_json_dump(paths[0], stamp_feedback({
                'page': 1,
                'boundary': {'continues_to_next': True},
                'questions': [{
                    'id': '1', 'student_answer': '局部作答', 'verdict': 'partial',
                    'error_type': '跨页截断，题干不完整', 'cross_page': True,
                }],
            }, runtime, 'review'))
            safe_json_dump(paths[1], stamp_feedback({
                'page': 2, 'boundary': {'continues_from_prev': True}, 'questions': [],
            }, runtime, 'review'))
            reconciled = grader_pass1_review._reconcile_open_material_boundary_errors(
                [str(path) for path in paths], feedback_runtime=runtime,
            )
            final_page = safe_json_load(paths[0])
        self.assertEqual(reconciled, 0)
        self.assertEqual(final_page['questions'][0]['verdict'], 'partial')
        self.assertEqual(final_page['questions'][0]['error_type'], '跨页截断，题干不完整')

    def test_disabled_cross_page_pass_still_produces_three_feedback_units(self):
        original = runtime_fixture('初中·初一·语文·作文.pdf')
        dependencies = original.dependencies
        dependencies['preprocessing']['environment'] = {'HOMEWORK_PASS1_5_ENABLED': '0'}
        runtime = freeze_feedback_runtime(original.context, **dependencies)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pass1 = root / 'pass1_json'
            clean = root / 'clean'
            pass1.mkdir()
            clean.mkdir()
            for page in range(1, 4):
                payload = {
                    'page': page,
                    'subject': 'chinese',
                    'boundary': {
                        'continues_from_prev': page > 1,
                        'continues_to_next': page < 3,
                    },
                    'questions': [{
                        'id': 'auto-1',
                        'position': [20, 30, 950, 980],
                        'stem_excerpt': f'作文第{page}页',
                        'student_answer': f'第{page}页可见作文内容',
                        'understanding': f'第{page}页承接全文内容',
                        'verdict': 'uncertain',
                        'error_type': '',
                        'knowledge_point': '',
                        'cross_page': True,
                    }],
                }
                safe_json_dump(
                    pass1 / f'composition_page{page}.json',
                    stamp_feedback(payload, runtime, 'grade'),
                )

            with patch.object(cross_page, 'pass1_5_enabled', return_value=False):
                self.assertEqual(cross_page.resolve_cross_pages(
                    str(pass1), str(clean), 'chinese', 'synthetic',
                    feedback_runtime=runtime,
                ), [])

            memory = build_memory(
                str(pass1), 'chinese', 'synthetic', feedback_runtime=runtime,
            )
            self.assertEqual(memory['question_count'], 3)
            self.assertEqual(len(memory['error_questions']), 3)
            self.assertEqual(memory['cross_page_uncertain_count'], 3)
            self.assertEqual(
                {item.get('uncertain_reason') for item in memory['error_questions']},
                {'cross_page_unresolved'},
            )

            ontology = stamp_feedback({
                'zones': {'blind_spot': [], 'friction_zone': [], 'zpd': []},
                'evolution_narrative': '三页属于同一篇作文。',
            }, runtime, 'ontology')
            generated = {
                'open_material_overview': {
                    'subject_and_layout': '初一学生的三页连续作文。',
                    'content_review': '三页围绕同一主题展开。',
                    'next_steps': ['第2页转折处补充具体反应。'],
                },
                'per_question_feedback': [{
                    'page': page,
                    'id': 'auto-1',
                    'qid_global': f'p{page}:auto-1',
                    'zone': '',
                    'comment': f'第{page}页形成性反馈',
                } for page in range(1, 4)],
            }
            with patch.object(
                grader_pass2, '_call_pass2_feedback_llm', return_value=generated,
            ):
                report = grader_pass2.analyze_pass2(
                    memory, 'chinese', 'synthetic',
                    str(root / 'report.json'), str(root / 'thinking.txt'),
                    ontology=ontology, feedback_runtime=runtime,
                )

        self.assertTrue(report['open_material_overview']['subject_and_layout'])
        self.assertEqual(len(report['per_question_feedback']), 3)


if __name__ == '__main__':
    unittest.main()
