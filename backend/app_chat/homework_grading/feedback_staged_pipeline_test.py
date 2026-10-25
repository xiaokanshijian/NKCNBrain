"""真实主编排，外部阶段用合成结果替代；不代表真实材料验收。"""
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from . import staged_pipeline as pipeline
from .feedback_preprocess_test import runtime
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .feedback_runtime_service import restore_feedback_runtime
from .utils import safe_json_load, safe_json_dump


class FrozenStagedPipelineTest(unittest.TestCase):
    def _execute(self, failing_stage=None, scenario=None):
        frozen = runtime()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            args = snapshot_arguments(tmp)
            args.update(context=frozen.context, **frozen.dependencies)
            root = Path(tmp) / 'run'
            prepare_feedback_snapshot(root, **args)
            base = root / 'homework_grading'
            base.mkdir()
            paths = {'base': str(base), 'root': str(root), 'manifest': str(root / 'manifest.json')}
            for name in ('raw', 'clean', 'pass1_json', 'pass2_report', 'annotated',
                         'annotated_layout', 'annotated_understanding'):
                directory = base / name
                directory.mkdir()
                paths[name] = str(directory)
            pages = [{'page': 1, 'clean_abs_path': str(base / 'clean' / 'synthetic_page1.png')}]
            replacements = {
                '_resolve_user_file_path': args['source_path'],
                'resolve_source_document_sha256': args['expected_source_sha256'],
                'load_homework_clean_pages': [], 'preprocess_pdf': pages,
                'build_pre_pass1_session_map': None, '_update_task': None,
                '_run_detect_all_pages': None, '_merge_all_pages_from_detect': None,
                '_run_pass1_grade_all_pages': 2, '_render_pages': None,
                'infer_homework_stage_status': {'understanding': 'done'},
                '_stages_needed_for_target': ['layout', 'understanding', 'grading'],
                'resolve_cross_pages': [], 'review_pass1_dir': {'enabled': True, 'errors': 0,
                                                               'details': [{'page': 1}]},
                'verify_pass1_dir': {}, 'verify_answer_statements': {},
                'build_memory': {}, 'save_memory': None, 'build_all_session_memories': [],
                'build_student_profile': {}, 'build_ontology': {}, 'analyze_pass2': None,
                'run_hallucination_filter': {}, 'evaluate_homework_red_blue': {'status': 'ready'},
            }
            mocks = {name: stack.enter_context(patch.object(pipeline, name, return_value=value))
                     for name, value in replacements.items()}
            # 前言最终校验需要读取Pass2正式产物；模型仍完全隔离。
            def write_report(*args, **kwargs):
                report = {'diagnosis': {}, 'zone_classification': {}, 'per_question_feedback': []}
                if scenario == 'partial':
                    report['content_validation'] = {'status': 'needs_review', 'issues': [{'message': 'synthetic'}]}
                safe_json_dump(args[3], report)
            mocks['analyze_pass2'].side_effect = write_report
            if scenario == 'candidate_corruption':
                def corrupt(*args, **kwargs):
                    report = safe_json_load(args[2])
                    report['per_question_feedback'] = [{'qid_global': 'p99:1', 'page': 99,
                                                       'id': '1', 'comment': '无据结论'}]
                    safe_json_dump(args[2], report)
                    return {}
                mocks['run_hallucination_filter'].side_effect = corrupt
            if failing_stage:
                mocks[failing_stage].side_effect = RuntimeError('synthetic stage failure')
            if failing_stage == 'build_student_profile':
                mocks['build_all_session_memories'].return_value = [{'synthetic': 'preserved'}]
            stack.enter_context(patch.object(pipeline.CIIndexManager, 'update_status'))
            # 此测试隔离全部模型与渲染阶段；产物完整性使用feedback_artifacts_test真文件验证。
            stack.enter_context(patch('app_chat.homework_grading.feedback_artifacts.validate_artifacts', return_value=[]))
            try:
                pipeline.execute_staged_homework_grading('synthetic-task', 'synthetic-user',
                    'synthetic-source.pdf', args['analysis_id'], paths,
                    {'homework_subject': 'math', 'homework_grade': 4}, 'grading',
                    Mock(return_value=[]), feedback_runtime=frozen)
            except RuntimeError:
                if failing_stage != 'build_all_session_memories':
                    raise
                manifest = safe_json_load(paths['manifest'])
                self.assertEqual(manifest['session_memory']['status'], 'failed')
                self.assertEqual(manifest['processing_stage'], 'memory')
                mocks['build_ontology'].assert_not_called()
                return
            if failing_stage == 'build_all_session_memories':
                self.fail('必要记忆失败必须停止后续诊断')
            if failing_stage == 'run_hallucination_filter' or scenario == 'candidate_corruption':
                manifest = safe_json_load(paths['manifest'])
                audit = safe_json_load(next((base/'pass2_report').glob('*_hallucination.json')))
                self.assertEqual(audit['status'], 'failed')
                self.assertIsNone(audit['total_issues'])
                self.assertEqual(manifest['hallucination']['status'], 'failed')
                self.assertEqual(manifest['content_validation']['status'], 'inconclusive')
                self.assertTrue(any('复核未完成' in w for w in manifest['warnings']))
                from .red_blue_review import _slim_audit
                self.assertEqual(_slim_audit(audit)['status'], 'failed')
                self.assertIsNone(_slim_audit(audit)['total_issues'])
                self.assertEqual(safe_json_load(next((base/'pass2_report').glob('*_report.json')))
                                 ['per_question_feedback'], [])
            if failing_stage == 'build_student_profile':
                manifest = safe_json_load(paths['manifest'])
                self.assertEqual(manifest['rule_profile']['status'], 'failed')
                self.assertEqual(mocks['build_ontology'].call_args.kwargs['session_memories'], [{'synthetic': 'preserved'}])
            for name in ('preprocess_pdf', 'build_pre_pass1_session_map', '_run_detect_all_pages',
                         '_run_pass1_grade_all_pages', 'resolve_cross_pages', 'review_pass1_dir',
                         'verify_pass1_dir', 'verify_answer_statements', 'build_memory',
                         'build_all_session_memories', 'build_student_profile', 'build_ontology',
                         'analyze_pass2', 'run_hallucination_filter', 'evaluate_homework_red_blue'):
                if name == 'evaluate_homework_red_blue' and (failing_stage == 'run_hallucination_filter' or scenario == 'candidate_corruption'):
                    mocks[name].assert_not_called()
                    continue
                self.assertTrue(mocks[name].called, name)
                self.assertTrue(all(call.kwargs.get('feedback_runtime') is frozen
                                    for call in mocks[name].call_args_list), name)
            self.assertEqual(restore_feedback_runtime(root).fingerprint, frozen.fingerprint)
            manifest = safe_json_load(paths['manifest'])
            incomplete = scenario in ('partial', 'candidate_corruption') or failing_stage == 'run_hallucination_filter'
            self.assertEqual(manifest['status'], 'partial' if incomplete else 'completed')
            self.assertEqual(manifest['completion']['status'], 'incomplete' if incomplete else 'complete')
            self.assertEqual(manifest['completion']['report_usable'], not incomplete)
            pipeline.CIIndexManager.update_status.assert_called_with('synthetic-user', args['analysis_id'], manifest['status'])
            self.assertIsNone(manifest['homework_attributes']['homework_grade'])
            self.assertEqual(manifest['feedback_context']['grade_in_level'], 2)

    def test_all_stages_keep_snapshots_and_consumer_runtime(self):
        self._execute()

    def test_filter_exception_is_visible_and_never_recorded_as_zero_issues(self):
        self._execute('run_hallucination_filter')

    def test_required_memory_failure_does_not_become_insufficient_evidence(self):
        self._execute('build_all_session_memories')

    def test_profile_failure_preserves_valid_session_memories(self):
        self._execute('build_student_profile')

    def test_filter_invalid_rewrite_never_replaces_original_report(self):
        self._execute(scenario='candidate_corruption')

    def test_partial_result_is_not_completed(self):
        self._execute(scenario='partial')


if __name__ == '__main__':
    unittest.main()
