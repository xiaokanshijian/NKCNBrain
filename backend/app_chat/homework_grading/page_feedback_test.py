"""前言的全页覆盖、证据失效和历史读取离线回归。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import page_feedback as p, grader_pass2
from .memory import aggregate_pages
from .feedback_skills_test import runtime_fixture


class PageFeedbackTest(unittest.TestCase):
    def setUp(self):
        self.page = p.page_evidence({'questions': [{'id': '1', 'verdict': 'correct',
            'stem_excerpt': '第一单元 有理数', 'student_answer': '0既不是正数也不是负数',
            'understanding': '记录了0与正负数的关系。'}]}, 1)
        self.item = {'page': 1, 'unit_kind': 'unit', 'unit_title': '第一单元 有理数',
                     'unit_evidence_quote': '第一单元 有理数', 'understanding_summary': '本页记录有理数知识。',
                     'evidence_qids': ['p1:1']}

    def test_all_correct_and_blank_pages_in_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for num, questions in [(1, [{'id': '1', 'verdict': 'correct', 'understanding': '正确理解'}]), (2, [])]:
                path = Path(tmp) / f'page_{num:03}.json'
                path.write_text(json.dumps({'page': num, 'questions': questions}), encoding='utf-8')
                paths.append(str(path))
            memory = aggregate_pages(paths)
        self.assertEqual(memory['error_questions'], [])
        self.assertEqual([x['page'] for x in memory['page_understanding']], [1, 2])
        self.assertEqual(memory['page_understanding'][0]['units'][0]['understanding'], '正确理解')

    def test_valid_context_and_grounded_unit(self):
        result = p.normalize_page_contexts([self.item], [self.page])[0]
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['unit_title'], self.item['unit_title'])

    def test_unknown_unit_does_not_guess(self):
        self.item.update(unit_title='第二单元', unit_evidence_quote='第二单元')
        result = p.normalize_page_contexts([self.item], [self.page])[0]
        self.assertEqual(result['unit_kind'], 'unconfirmed')
        self.assertEqual(result['unit_title'], '')

    def test_invalid_duplicate_or_other_page_evidence_falls_back(self):
        for items in ([], [self.item, self.item], [{**self.item, 'evidence_qids': ['p2:1']}],
                      [{**self.item, 'evidence_qids': []}]):
            result = p.normalize_page_contexts(items, [self.page])[0]
            self.assertEqual(result['status'], 'fallback')
            self.assertIn('0与正负数', result['understanding_summary'])

    def test_review_changed_evidence_invalidates_only_affected_page(self):
        second = p.page_evidence({'questions': [{'id': 'a', 'understanding': '地图旁批'}]}, 2)
        items = p.normalize_page_contexts([self.item,
            {**self.item, 'page': 2, 'evidence_qids': ['p2:a']}], [self.page, second])
        changed = copy.deepcopy(self.page)
        changed['units'][0]['understanding'] = '复核后仍有局部字迹待确认'
        result = p.normalize_page_contexts(items, [changed, second])
        self.assertEqual(result[0]['status'], 'fallback')
        self.assertIn('复核', result[0]['warning'])
        self.assertEqual(result[1], items[1])

    def test_background_comes_from_frozen_context_all_material_kinds(self):
        for kind in ('笔记', '作文', '作业', '试卷', '听写'):
            runtime = runtime_fixture(f'初中·七年级·语文·{kind}.pdf')
            result = p.display_context(1, {}, runtime.context)
            self.assertEqual(result['education_level_label'], '初中')
            self.assertNotEqual(result['grade_label'], '年级未确认')
            self.assertEqual(result['understanding_summary'], '本版本未生成逐页理解摘要')

    def test_unknown_background_and_empty_page(self):
        context = p.display_context(1, {}, {'grade_status': 'conflict', 'grade_label': '四年级'})
        self.assertEqual(context['grade_label'], '年级未确认')
        self.assertEqual(context['unit_label'], '教学单元未确认')
        empty = p.normalize_page_contexts([], [{'page': 2, 'units': []}])[0]
        self.assertEqual(empty['evidence_qids'], [])
        self.assertIn('未提取', empty['understanding_summary'])

    def test_all_correct_page_still_uses_existing_feedback_call(self):
        data = {'per_question_feedback': [], 'page_feedback_contexts': [self.item]}
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data)))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
        with tempfile.TemporaryDirectory() as tmp, patch.object(grader_pass2, '_deepseek_client', return_value=client):
            result = grader_pass2._call_pass2_feedback_llm(
                {'error_questions': [], 'page_understanding': [self.page]}, 'math', 'fixture', {},
                str(Path(tmp) / 'unused.txt'))
        self.assertEqual(result['per_question_feedback'], [])
        self.assertEqual(result['page_feedback_contexts'][0]['status'], 'ready')

    def test_result_reader_exposes_page_context_from_selected_snapshot(self):
        from . import service
        from .feedback_preprocess_test import runtime
        from .feedback_snapshot import prepare_feedback_snapshot
        from .feedback_snapshot_test import snapshot_arguments
        frozen = runtime()
        report = {'page_feedback_contexts': p.normalize_page_contexts([self.item], [self.page])}
        with tempfile.TemporaryDirectory() as tmp:
            args = snapshot_arguments(tmp)
            args.update(context=frozen.context, **frozen.dependencies)
            root = Path(tmp) / 'run'
            prepare_feedback_snapshot(root, **args)
            with patch.object(service, 'resolve_homework_run_root', return_value=str(root)), \
                 patch.object(service, '_build_page_units', return_value=[{'page': 1}]), \
                 patch.object(service, '_load_report', return_value=report):
                result = service.get_homework_grading_result('fixture', 'homework_fixture', 'synthetic')
        context = result['pages'][0]['feedback_context']
        self.assertEqual(result['snapshot_status'], 'complete')
        self.assertEqual(context['education_level_label'], frozen.context['education_level_name'])
        self.assertEqual(context['grade_label'], frozen.context['grade_label'])
        self.assertEqual(context['understanding_summary'], self.item['understanding_summary'])

    def test_summary_stays_within_two_sentences(self):
        item = {**self.item, 'understanding_summary': '第一句。第二句。第三句。'}
        result = p.normalize_page_contexts([item], [self.page])[0]
        self.assertEqual(result['understanding_summary'], '第一句。第二句。')


if __name__ == '__main__':
    unittest.main()
