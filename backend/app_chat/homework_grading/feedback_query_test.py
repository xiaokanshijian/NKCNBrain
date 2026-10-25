"""执行实际query函数体，隔离庞大视图模块的外部初始化；请求包装另有测试。"""
import ast
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from app_chat import ci_test_support  # noqa: F401
from django.http import JsonResponse
from django.test import RequestFactory, override_settings
from app_chat.feedback_material_settings import merge_saved_material_settings, settings_path
from .utils import safe_json_dump
from .feedback_request import resolve_feedback_request


class FeedbackQueryTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).parents[1] / 'views_continuous_image.py'
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'ci_query')
        function.decorator_list = []
        self.cache = Mock(side_effect=lambda *args: {'singles': [], 'groups': [], 'superset_match': None})
        self.attrs = Mock(return_value={'is_homework_pdf': False})
        namespace = {'json': json, 'JsonResponse': JsonResponse, 'query_ci_analyses': self.cache,
                     'load_document_attrs': self.attrs, 'resolve_feedback_request': resolve_feedback_request,
                     'merge_saved_material_settings': merge_saved_material_settings,
                     'is_pdf_filename': lambda name: name.lower().endswith('.pdf')}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        self.query = namespace['ci_query']
        self.factory = RequestFactory()

    def call(self, **extra):
        body = {'username': 'alice_book', 'files': ['试卷.pdf'], **extra}
        return json.loads(self.query(self.factory.post('/', body, content_type='application/json')).content)

    def test_existing_nonhomework_cache_does_not_block_grading(self):
        result = self.call(requested_action='grading', feedback_overrides={
            'education_level': '大学', 'grade': '大二', 'subject': '嵌入式系统', 'material_type': '试卷'})
        self.assertEqual(result['error_num'], 0)
        self.assertTrue(result['feedback_eligible'])
        self.assertEqual(result['homework_status']['analysis_type'], 'homework_grading')
        self.assertEqual(result['feedback_context']['grade_in_level'], 2)
        self.assertIsNone(result['feedback_context']['grade_global'])
        self.assertIn('singles', result)
        self.assertIn('groups', result)

    def test_query_uses_saved_material_metadata(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            path = settings_path('alice_book', '试卷.pdf')
            safe_json_dump(path, {'feedback_overrides': {
                'education_level': '初中', 'grade': '初一',
                'subject': '历史', 'material_type': '笔记',
            }})
            result = self.call(requested_action='grading')
        self.assertEqual(result['error_num'], 0, result.get('msg'))
        self.assertEqual(result['feedback_context']['grade_in_level'], 1)
        self.assertEqual(result['feedback_context']['subject_code'], 'history')
        self.assertEqual(result['feedback_context']['material_type'], 'notes')

    def test_parse_precedes_index_query_and_invalid_does_not_query(self):
        result = self.call(requested_action='invalid')
        self.assertEqual(result['error_num'], 1)
        self.cache.assert_not_called()

    @patch('app_chat.homework_grading.feedback_observation.collect_observation')
    def test_material_query_resolves_source_without_injected_helper(self, observe):
        observe.return_value = {'status': 'inconclusive'}
        for filename in ('小学二年级数学作业.pdf', '数学九年级作业（6页）.pdf'):
            with self.subTest(filename=filename):
                result = self.call(files=[filename], requested_action='grading')
                self.assertEqual(result['error_num'], 0, result.get('msg'))
                source, context = observe.call_args.args
                self.assertEqual(Path(source), Path('received_dir/user_raw_file/alice_book', filename).resolve())
                self.assertEqual(context, result['feedback_context'])
                self.assertEqual(result['homework_status']['content_validation']['status'], 'inconclusive')

    def test_current_filename_is_used_every_time(self):
        result = self.call(files=['小学·二年级·数学·作业.pdf'])
        self.assertEqual(result['feedback_context']['grade_global'], 2)
        result = self.call(files=['初中·九年级·数学·作业.pdf'])
        self.assertEqual(result['feedback_context']['grade_global'], 9)

    def test_explicit_understanding_and_group_compatibility(self):
        result = self.call(files=['小学·二年级·数学·作业.pdf'], requested_action='understanding')
        self.assertEqual(result['homework_status']['analysis_type'], 'continuous_image')
        result = self.call(files=['a.png', 'b.png'])
        self.assertNotIn('homework_status', result)
        self.assertEqual(result['error_num'], 0)


if __name__ == '__main__':
    unittest.main()
