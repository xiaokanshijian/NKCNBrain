import tempfile
import unittest
import ast
import json
import uuid
from types import SimpleNamespace
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import fitz
from app_chat import ci_test_support  # noqa: F401
from django.test import override_settings

from . import feedback_start_service as service
from .feedback_preprocess_test import runtime
from .feedback_runtime import freeze_feedback_runtime
from .feedback_workspaces import current_directory
from app_chat.ci.task_store import update_task, read_task
from app_chat.feedback_material_settings import settings_path


class InlineThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


class StartServiceTest(unittest.TestCase):
    def test_new_run_rejects_corrupt_saved_settings_before_task_start(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=tmp):
            path = settings_path('synthetic_book', '笔记.pdf')
            path.parent.mkdir(parents=True)
            path.write_text('{bad json', encoding='utf-8')
            with patch.object(service, 'RunLease', side_effect=AssertionError('不应创建任务锁')):
                with self.assertRaisesRegex(ValueError, '已保存材料设置无法读取'):
                    service.start_grading_request(
                        'synthetic_book', '笔记.pdf', {},
                        resolution={'route': 'homework_grading', 'feedback_context': {}, 'warnings': []},
                    )

    def test_ordinary_rerun_does_not_read_current_saved_settings(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=tmp), \
                patch('app_chat.feedback_material_settings.merge_saved_material_settings',
                      side_effect=AssertionError('普通迭代必须沿用原快照')):
            with self.assertRaisesRegex(ValueError, '材料PDF不存在'):
                service.start_grading_request(
                    'synthetic_book', '试卷.pdf',
                    {'analysis_id': 'homework_synthetic', 'rerun_stage': 'all'},
                    rerun=True,
                )

    def test_actual_start_route_respects_explicit_intent_and_metadata(self):
        from django.http import JsonResponse
        from django.test import RequestFactory
        from .feedback_request import resolve_feedback_request
        source = Path(__file__).parents[1] / 'views_continuous_image.py'
        node = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'ci_start')
        node.decorator_list = []
        namespace = {'json': json, 'JsonResponse': JsonResponse, 'uuid': uuid,
            'resolve_feedback_request': resolve_feedback_request,
            'merge_saved_material_settings': lambda workspace, filename, data: (dict(data), False),
            'is_pdf_filename': lambda name: name.lower().endswith('.pdf'),
            'load_document_attrs': Mock(return_value={'is_homework_pdf': False}),
            'build_analysis_id': Mock(return_value='continuous-synthetic'),
            'CIIndexManager': SimpleNamespace(find_by_id=Mock(return_value={'status': 'completed'})),
            'global_var': SimpleNamespace(tasks={})}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        body = {'username': 'synthetic_book', 'files': ['试卷.pdf'], 'requested_action': 'grading',
                'feedback_overrides': {'education_level': '大学', 'grade': '大二',
                                       'subject': '嵌入式系统', 'material_type': '试卷'}}

        def call():
            request = RequestFactory().post('/', body, content_type='application/json')
            return json.loads(namespace['ci_start'](request).content)

        with patch.object(service, 'start_grading_request', return_value={'error_num': 0}) as start:
            self.assertEqual(call()['error_num'], 0)
            context = start.call_args.kwargs['resolution']['feedback_context']
            self.assertEqual(context['grade_in_level'], 2)
            self.assertIsNone(context['grade_global'])
            start.reset_mock()
            body['requested_action'] = 'understanding'
            namespace['load_document_attrs'].return_value = {'is_homework_pdf': True}
            self.assertEqual(call()['analysis_id'], 'continuous-synthetic')
            start.assert_not_called()
            body.update(requested_action='grading', files=['one.pdf', 'two.pdf'])
            self.assertEqual(call()['error_num'], 1)
            start.assert_not_called()

    def test_start_reuse_and_changed_configuration_new_run(self):
        frozen = runtime()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(override_settings(BASE_DIR=tmp))
            source = Path(tmp) / 'received_dir/user_raw_file/synthetic_book/试卷.pdf'
            source.parent.mkdir(parents=True)
            document = fitz.open()
            document.new_page().insert_text((72, 72), 'Synthetic fixture only')
            document.save(source)
            document.close()
            container = Path(tmp) / 'document'
            stack.enter_context(patch('app_chat.homework_grading.homework_versions._container_root', return_value=str(container)))
            stack.enter_context(patch.object(service, 'build_request_runtime', return_value=frozen))
            stack.enter_context(patch.object(service.threading, 'Thread', InlineThread))
            stack.enter_context(patch.object(service.CIIndexManager, 'find_by_id', return_value=None))
            stack.enter_context(patch.object(service.CIIndexManager, 'restore_record'))
            ready = stack.enter_context(patch('app_chat.homework_grading.service.check_homework_stage_ready', return_value=False))

            def run(task_id, *args, **kwargs):
                self.assertEqual(read_task(task_id)['config_fingerprint'], kwargs['feedback_runtime'].fingerprint)
                update_task(task_id, {'completed': True})

            runner = stack.enter_context(patch('app_chat.homework_grading.service.run_homework_grading', side_effect=run))
            resolution = {'route': 'homework_grading', 'feedback_context': frozen.context, 'warnings': []}
            first = service.start_grading_request('synthetic_book', '试卷.pdf', {}, resolution=resolution)
            self.assertEqual(first['msg'], 'success')
            self.assertEqual(first['feedback_context']['grade_in_level'], 2)
            ready.return_value = True
            second = service.start_grading_request('synthetic_book', '试卷.pdf', {}, resolution=resolution)
            self.assertEqual(second['msg'], 'existing_result')
            self.assertEqual(second['run_id'], first['run_id'])
            self.assertEqual(runner.call_count, 1)
            old_directory = current_directory(container)
            deps = frozen.dependencies
            deps['references']['reference_text'] = '合成配置变化'
            changed = freeze_feedback_runtime(frozen.context, **deps)
            with patch.object(service, 'build_request_runtime', return_value=changed):
                third = service.start_grading_request('synthetic_book', '试卷.pdf', {}, resolution=resolution)
            self.assertNotEqual(third['run_id'], first['run_id'])
            self.assertNotEqual(third['config_fingerprint'], first['config_fingerprint'])
            self.assertTrue((old_directory / 'manifest.json').is_file())
            self.assertEqual(runner.call_count, 2)
            rerun_data = {'analysis_id': third['analysis_id'], 'rerun_stage': 'all'}
            fourth = service.start_grading_request('synthetic_book', '试卷.pdf', rerun_data, rerun=True)
            self.assertEqual(fourth['config_fingerprint'], third['config_fingerprint'])
            self.assertNotEqual(fourth['run_id'], third['run_id'])
            self.assertEqual(runner.call_count, 3)
            stable = current_directory(container)
            with self.assertRaises(ValueError):
                service.start_grading_request('synthetic_book', '试卷.pdf',
                    dict(rerun_data, reference_text='不能与续跑混用的新资料', resume=True), rerun=True)
            self.assertEqual(current_directory(container), stable)
            (stable / 'feedback_context.json').write_text('{}')
            with self.assertRaises(ValueError):
                service.start_grading_request('synthetic_book', '试卷.pdf', rerun_data, rerun=True)
            fifth = service.start_grading_request('synthetic_book', '试卷.pdf',
                dict(rerun_data, full_recompute=True, feedback_overrides={
                    'education_level': '大学', 'grade': '大二', 'subject': '嵌入式系统', 'material_type': '试卷'}), rerun=True)
            self.assertTrue(fifth['warnings'])
            self.assertEqual((stable / 'feedback_context.json').read_text(), '{}')
            self.assertEqual(fifth['archived_run_id'], stable.name)
            self.assertTrue((container / '_runs' / fifth['archived_run_id'] / 'feedback_context.json').is_file())
            self.assertFalse((container / '_archives' / fifth['archived_run_id']).exists())

    def test_lease_serializes_same_document_in_workspace(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(service, 'runtime_root', return_value=Path(tmp)):
            first = service.RunLease('book1', 'a'*64).acquire()
            try:
                from app_chat.ci.file_io import FileLockBusy
                with self.assertRaises(FileLockBusy):
                    service.RunLease('book1', 'a'*64).acquire()
                service.RunLease('book2', 'a'*64).acquire().release()
            finally:
                first.release()
            service.RunLease('book1', 'a'*64).acquire().release()
