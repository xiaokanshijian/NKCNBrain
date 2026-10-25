"""合成页面与模型响应：真实阶段写入、进程中断和恢复调度，不使用学生材料。"""
import copy
from contextlib import ExitStack
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from . import grader_pass1 as grader, staged_pipeline as pipeline
from .execution_checkpoints import record_stage_receipt, receipt_matches
from .execution_reliability_test import response
from .feedback_pass1_test import PAGE
from .feedback_skills_test import runtime_fixture
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .utils import safe_json_dump, safe_json_load


class StageReceiptLifecycleTest(unittest.TestCase):
    def test_understanding_preserves_layout_bytes_even_when_normalizing_input(self):
        frozen = runtime_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'pass1_json').mkdir()
            output = str(base / 'pass1_json/physics_fixture_page1.json')
            detect = Path(output.replace('.json', '.detect.json'))
            with patch.object(grader, 'image_to_data_uri', return_value='synthetic'), \
                    patch.object(grader, '_call_qwen_json_with_retry',
                                 side_effect=lambda *a, **kw: (copy.deepcopy(PAGE), None)):
                grader.detect_page_only('synthetic', 'physics', 1, output, feedback_runtime=frozen)
                # 模拟版面后处理留下的额外来源字段；理解规范化不得抹掉它。
                data = safe_json_load(detect)
                data['questions'][0]['layout_source_note'] = 'synthetic source evidence'
                safe_json_dump(detect, data)
                before = detect.read_bytes()
                manifest = {'config_fingerprint': frozen.fingerprint}
                paths = {'base': str(base)}
                record_stage_receipt(paths, manifest, 'layout')
                result = grader.grade_page_from_detect('synthetic', 'physics', 1, output,
                                                      feedback_runtime=frozen)
            self.assertEqual(detect.read_bytes(), before)
            self.assertTrue(receipt_matches(paths, manifest, 'layout'))
            self.assertEqual(result['questions'][0]['student_answer'], 'x')
            self.assertEqual(result['feedback_execution']['consumer'], 'grade_page_from_detect')
            self.assertTrue(Path(output.replace('.json', '.grade.json')).is_file())
            # 真正的依据、程序或文件变化仍必须拒绝复用。
            self.assertFalse(receipt_matches(paths, {**manifest, 'config_fingerprint': 'changed'}, 'layout'))
            self.assertFalse(receipt_matches(paths, manifest, 'layout', {'actual_code_fingerprint': 'changed'}))
            data['questions'][0]['stem_excerpt'] = 'changed source evidence'
            safe_json_dump(detect, data)
            self.assertFalse(receipt_matches(paths, manifest, 'layout'))

    def _resume_pipeline(self, interrupt_during_understanding):
        frozen = runtime_fixture()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            args = snapshot_arguments(tmp)
            args.update(context=frozen.context, **frozen.dependencies)
            root = Path(tmp) / 'run'
            prepare_feedback_snapshot(root, **args)

            def workspace(directory):
                base = directory / 'homework_grading'
                paths = {'base': str(base), 'root': str(directory), 'manifest': str(directory / 'manifest.json')}
                for name in ('raw', 'clean', 'pass1_json', 'pass2_report', 'annotated',
                             'annotated_layout', 'annotated_understanding'):
                    (base / name).mkdir(parents=True, exist_ok=True)
                    paths[name] = str(base / name)
                return paths

            paths = workspace(root)
            image_name = 'physics_fixture_page1.png'
            for name in ('raw', 'clean'):
                Image.new('RGB', (64, 64), 'white').save(Path(paths[name]) / image_name)
            stack.enter_context(patch.object(pipeline, '_resolve_user_file_path', return_value=args['source_path']))
            stack.enter_context(patch.object(pipeline, '_update_task'))
            stack.enter_context(patch.object(pipeline.CIIndexManager, 'update_status'))
            stack.enter_context(patch.object(grader, 'image_to_data_uri', return_value='synthetic'))
            # 保留真实解析、落盘及模型检查点逻辑，只替换最底层模型调用。
            model = stack.enter_context(patch.object(grader, '_call_qwen_json',
                side_effect=lambda *a, **kw: response(copy.deepcopy(PAGE))))
            detect = stack.enter_context(patch.object(pipeline, '_run_detect_all_pages',
                                                       wraps=pipeline._run_detect_all_pages))
            understand = stack.enter_context(patch.object(pipeline, '_run_pass1_grade_all_pages',
                                                           wraps=pipeline._run_pass1_grade_all_pages))
            interrupted = False

            def render(current_paths, pages, modes, **kwargs):
                nonlocal interrupted
                if modes == ('understanding',) and interrupt_during_understanding and not interrupted:
                    interrupted = True
                    raise KeyboardInterrupt('synthetic exit after grade files, before stage receipt')
                for mode in modes:
                    folder = 'annotated_' + mode
                    for page in pages:
                        shutil.copyfile(page['clean_abs_path'], Path(current_paths[folder]) / Path(page['clean_abs_path']).name)

            stack.enter_context(patch.object(pipeline, '_render_pages', side_effect=render))
            # 达到批改阶段即停止；不得调用跨页或后续真实模型。
            cross_page = stack.enter_context(patch.object(pipeline, 'resolve_cross_pages',
                side_effect=KeyboardInterrupt('synthetic exit at grading boundary')))

            def execute(current_paths):
                pipeline.execute_staged_homework_grading('synthetic-task', 'synthetic-user',
                    'synthetic-source.pdf', args['analysis_id'], current_paths, {}, 'grading',
                    lambda *a: [], feedback_runtime=frozen)

            with self.assertRaises(KeyboardInterrupt):
                execute(paths)
            self.assertEqual(model.call_count, 2)  # 检测与理解各一次合成响应
            manifest = safe_json_load(paths['manifest'])
            self.assertTrue(receipt_matches(paths, manifest, 'layout'))
            self.assertEqual(receipt_matches(paths, manifest, 'understanding'), not interrupt_during_understanding)
            before = (Path(paths['pass1_json']) / image_name.replace('.png', '.detect.json')).read_bytes()
            # 模拟恢复入口把原运行复制到新版本；重新进入真实阶段编排。
            resumed = Path(tmp) / 'resumed'
            shutil.copytree(root, resumed)
            resumed_paths = workspace(resumed)
            manifest.update(status='interrupted', checkpoint_resume=True)
            safe_json_dump(resumed_paths['manifest'], manifest)
            for mocked in (detect, understand, model, cross_page):
                mocked.reset_mock()
            with self.assertRaises(KeyboardInterrupt):
                execute(resumed_paths)
            detect.assert_not_called()
            self.assertEqual(understand.call_count, int(interrupt_during_understanding))
            model.assert_not_called()  # 未收尾的理解阶段也应命中模型检查点
            if interrupt_during_understanding:
                audit = safe_json_load(next(Path(resumed_paths['pass1_json']).glob('*.grade.error.txt.responses.json')))
                self.assertEqual(audit['attempts'][-1]['status'], 'checkpoint_reused')
            cross_page.assert_called_once()
            current = safe_json_load(resumed_paths['manifest'])
            self.assertTrue(receipt_matches(resumed_paths, current, 'layout'))
            self.assertTrue(receipt_matches(resumed_paths, current, 'understanding'))
            self.assertEqual((Path(paths['pass1_json']) / image_name.replace('.png', '.detect.json')).read_bytes(), before)

    def test_exit_during_understanding_reuses_layout_in_new_run(self):
        self._resume_pipeline(interrupt_during_understanding=True)

    def test_exit_after_understanding_reuses_both_stages_in_new_run(self):
        self._resume_pipeline(interrupt_during_understanding=False)
