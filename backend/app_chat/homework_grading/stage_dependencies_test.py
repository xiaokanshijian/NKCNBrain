"""阶段失效矩阵、真实恢复编排和派生产物补做；全部为合成输入。"""
import copy
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from . import execution_control as control, staged_pipeline as pipeline
from .stage_dependencies import SCHEMA, ORDER, basis, code_basis, configuration, assert_registry_complete
from .feedback_runtime import freeze_feedback_runtime
from .feedback_skills_test import runtime_fixture
from .execution_checkpoints import record_stage_receipt, receipt_matches, checkpoint_key
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .utils import safe_json_dump, safe_json_load


def scoped_runtime():
    original = runtime_fixture()
    deps = original.dependencies
    deps['model_config']['dependency_schema'] = SCHEMA
    return freeze_feedback_runtime(original.context, **deps)


class StageDependenciesTest(unittest.TestCase):
    def test_reused_artifact_keeps_original_identity_and_checks_stage_basis(self):
        from .feedback_runtime import stamp_feedback
        from .stage_dependencies import artifact_compatible, reusable_upstream
        original = scoped_runtime()
        execution = control.Execution(original)
        execution.stage = 'grading'
        with control.execution_scope(execution):
            value = stamp_feedback({'synthetic': True}, original, 'report')
        before = copy.deepcopy(value)
        deps = original.dependencies
        deps['model_config']['roles']['quality']['model'] = 'changed-quality'
        candidate = freeze_feedback_runtime(original.context, **deps)
        self.assertTrue(reusable_upstream(original, candidate))
        self.assertTrue(artifact_compatible(value, candidate))
        self.assertEqual(value, before)
        deps['model_config']['roles']['review']['model'] = 'changed-review'
        self.assertFalse(artifact_compatible(value, freeze_feedback_runtime(original.context, **deps)))

    def test_registry_covers_every_production_module(self):
        assert_registry_complete()

    def test_code_change_matrix_and_unknown_modules(self):
        original = {'preprocess.py': 'a', 'fixed_math_sample_guards.py': 'a', 'grader_pass2.py': 'a',
                    'render.py': 'a', 'red_blue_review.py': 'a', 'feedback_result_basis.py': 'a'}
        for file, first in [('preprocess.py', 0), ('fixed_math_sample_guards.py', 1), ('grader_pass2.py', 2),
                            ('render.py', 3), ('red_blue_review.py', 4), ('feedback_result_basis.py', 5)]:
            changed = dict(original, **{file: 'b'})
            self.assertEqual([code_basis(original, stage) != code_basis(changed, stage) for stage in ORDER],
                             [i >= first for i in range(5)])
        self.assertNotEqual(code_basis(original, 'layout'), code_basis(dict(original, unknown='new'), 'layout'))

    def test_model_config_and_audit_code_have_separate_effects(self):
        runtime = scoped_runtime()
        for role, first in [('qwen', 0), ('review', 2), ('deepseek', 2), ('quality', 4)]:
            deps = runtime.dependencies
            deps['model_config']['roles'][role]['model'] = 'synthetic-change'
            changed = freeze_feedback_runtime(runtime.context, **deps)
            self.assertEqual([configuration(runtime, stage) != configuration(changed, stage) for stage in ORDER],
                             [i >= first for i in range(5)])
        deps = runtime.dependencies
        deps['model_config']['consumer_code_hashes'] = {'display.py': 'changed'}
        self.assertEqual(runtime.fingerprint, freeze_feedback_runtime(runtime.context, **deps).fingerprint)

    def test_checkpoints_use_execution_stage_not_display_or_global_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            execution = control.Execution(scoped_runtime(), tmp, True)
            execution.stage = 'understanding'
            with control.execution_scope(execution):
                before = checkpoint_key([{'role': 'user', 'content': 'synthetic'}], '模型输出')
                execution.identity['actual_code_hashes']['feedback_result_basis.py'] = 'changed'
                execution.identity['actual_code_hashes']['red_blue_review.py'] = 'changed'
                self.assertEqual(checkpoint_key([{'role': 'user', 'content': 'synthetic'}], '模型输出'), before)
                execution.identity['actual_code_hashes']['grader_pass1.py'] = 'changed'
                self.assertNotEqual(checkpoint_key([{'role': 'user', 'content': 'synthetic'}], '模型输出'), before)

    def test_receipts_reject_changed_bytes_and_pin_saved_code_for_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {'base': tmp}
            folder = Path(tmp) / 'pass1_json'
            folder.mkdir()
            target = folder / 'fixture.detect.json'
            safe_json_dump(target, {'synthetic': 1})
            runtime = scoped_runtime()
            manifest = {'config_fingerprint': runtime.fingerprint}
            execution = control.Execution(runtime, tmp, True)
            with control.execution_scope(execution):
                record_stage_receipt(paths, manifest, 'layout')
                self.assertEqual(manifest['stage_receipts']['layout']['schema'], 3)
                execution.identity['actual_code_hashes']['feedback_result_basis.py'] = 'changed'
                self.assertTrue(receipt_matches(paths, manifest, 'layout'))
                execution.identity['actual_code_hashes']['preprocess.py'] = 'changed'
                self.assertFalse(receipt_matches(paths, manifest, 'layout'))
                code = {'actual_code_fingerprint': manifest['stage_receipts']['layout']['code']}
                self.assertTrue(receipt_matches(paths, manifest, 'layout', code))
                safe_json_dump(target, {'synthetic': 2})
                self.assertFalse(receipt_matches(paths, manifest, 'layout', code))

    def test_grading_change_resumes_real_pipeline_without_layout_or_understanding_calls(self):
        from .stage_receipt_lifecycle_test import StageReceiptLifecycleTest
        import shutil
        original_identity = control.code_identity
        original_copy = shutil.copytree
        changed = [False]
        def identity():
            result = original_identity()
            if changed[0]:
                result['actual_code_hashes']['grader_pass2.py'] = 'synthetic-code-change'
                result['actual_code_fingerprint'] = 'synthetic-new-audit'
            return result
        def clone(*a, **kw):
            result = original_copy(*a, **kw)
            changed[0] = True
            return result
        with patch('app_chat.homework_grading.stage_receipt_lifecycle_test.runtime_fixture', side_effect=scoped_runtime), \
                patch.object(control, 'code_identity', side_effect=identity), patch.object(shutil, 'copytree', side_effect=clone):
            StageReceiptLifecycleTest()._resume_pipeline(interrupt_during_understanding=False)

    def run_derived(self, changed_module, expected_render):
        from .red_blue_pipeline_test import RedBluePipelineTest
        helper = RedBluePipelineTest()
        frozen = scoped_runtime()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            args = snapshot_arguments(tmp)
            args.update(context=frozen.context, **frozen.dependencies)
            manifest = prepare_feedback_snapshot(Path(tmp) / 'run', **args)
            paths = helper._workspace(str(Path(tmp) / 'run'))
            manifest.update(subject='physics', group_id='homework_fixture', target_stage='grading', status='completed',
                stages={'layout': 'done', 'understanding': 'done', 'grading': 'done'},
                pass1_review={'enabled': True, 'errors': 0, 'coverage': {}}, hallucination={'status': 'ready'},
                red_blue_review={'status': 'ready'}, output_validation={'status': 'passed', 'target_stage': 'grading'})
            safe_json_dump(Path(paths['pass1_json']) / 'physics_fixture_page1.detect.json', {'page': 1})
            report = Path(paths['pass2_report']) / 'physics_fixture_report.json'
            safe_json_dump(report, {'diagnosis': 'synthetic immutable report'})
            execution = control.Execution(frozen, paths['base'], True)
            with control.execution_scope(execution):
                for stage in ORDER:
                    record_stage_receipt(paths, manifest, stage)
            saved_grading = copy.deepcopy(manifest['stage_receipts']['grading'])
            manifest['execution_provenance'] = execution.audit()
            safe_json_dump(paths['manifest'], manifest)
            actual = copy.deepcopy(execution.identity)
            actual['actual_code_hashes'][changed_module] = 'synthetic-code-change'
            actual['actual_code_fingerprint'] = 'synthetic-new-audit'
            stack.enter_context(patch.object(control, 'code_identity', return_value=actual))
            helper._base_patches(stack, [{'page': 1, 'clean_abs_path': str(Path(paths['clean']) / 'physics_fixture_page1.png')}])
            stack.enter_context(patch.object(pipeline, '_stages_needed_for_target', return_value=[]))
            stack.enter_context(patch.object(pipeline, 'resolve_cross_pages', side_effect=AssertionError('no grading')))
            stack.enter_context(patch.object(pipeline, '_run_detect_all_pages', side_effect=AssertionError('no layout')))
            stack.enter_context(patch.object(pipeline, '_run_pass1_grade_all_pages', side_effect=AssertionError('no understanding')))
            stack.enter_context(patch('app_chat.homework_grading.feedback_artifacts.validate_artifacts', return_value=[]))
            renderer = stack.enter_context(patch.object(pipeline, '_render_pages'))
            scorer = stack.enter_context(patch.object(pipeline, 'evaluate_homework_red_blue', return_value={'status': 'ready'}))
            pipeline.execute_staged_homework_grading('synthetic', 'user', 'fixture.pdf', 'homework_fixture', paths, {},
                                                    'grading', lambda *a: [], feedback_runtime=frozen)
            self.assertEqual(renderer.call_count, expected_render)
            scorer.assert_called_once()
            self.assertEqual(safe_json_load(paths['manifest'])['stage_receipts']['grading'], saved_grading)
            self.assertEqual(safe_json_load(report)['diagnosis'], 'synthetic immutable report')

    def test_quality_change_only_scores(self):
        self.run_derived('red_blue_review.py', 0)

    def test_render_change_only_renders_and_scores(self):
        self.run_derived('render.py', 1)
