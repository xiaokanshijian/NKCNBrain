"""模型配置、重试、冻结边界；仅模拟外部客户端。"""
import copy
import unittest
from unittest.mock import patch
from . import llm_clients, grader_pass1
from .feedback_model import model_spec
from .feedback_pipeline_test import SyntheticClient
from .feedback_skills_test import runtime_fixture
from .feedback_runtime import freeze_feedback_runtime
from .feedback_skill_matching import compose_skills
from .feedback_metadata import resolve_feedback_metadata
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_reader import read_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
import tempfile
from pathlib import Path


class FrozenModelTest(unittest.TestCase):
    def test_parameters_and_format_retry_use_frozen_model(self):
        for thinking in (False, True):
            original = runtime_fixture()
            deps = original.dependencies
            deps['model_config']['roles']['qwen'].update(extra_body={'enable_thinking':thinking}, temperature=0.25)
            runtime = freeze_feedback_runtime(original.context, **deps)
            client = SyntheticClient()
            actual = client.create
            def create(**kwargs):
                if not client.calls:
                    client.calls.append(copy.deepcopy(kwargs))
                    raise TimeoutError('synthetic retry')
                return actual(**kwargs)
            client.create = create
            with patch.object(llm_clients, '_qwen_client', return_value=client), patch.object(
                    llm_clients, 'homework_qwen_model', return_value='changed-after-freeze'):
                result, _ = grader_pass1._call_qwen_json_with_retry([], {}, require_questions=False, feedback_runtime=runtime)
            self.assertEqual(result, {})
            self.assertEqual(len(client.calls), 2)
            for call in client.calls:
                self.assertEqual(call['model'], 'synthetic-qwen')
                self.assertEqual(call['temperature'], 0.25)
                if thinking: self.assertNotIn('response_format', call)
            deps['model_config']['roles']['qwen']['model'] = 'mutated-copy'
            self.assertEqual(model_spec(runtime, 'qwen')['model'], 'synthetic-qwen')

    def test_missing_role_fails(self):
        runtime = runtime_fixture()
        with self.assertRaises(ValueError): model_spec(runtime, 'missing')

    def test_manual_binding_cannot_bypass_scope(self):
        selected, _ = compose_skills(resolve_feedback_metadata('小学·四年级·数学·作业.pdf'))
        with self.assertRaisesRegex(ValueError, '专项范围'):
            runtime_fixture('大学·大二·数学·作业.pdf', skills=selected)

    def test_frozen_switch_and_p01_snapshot(self):
        runtime = runtime_fixture()
        with patch.dict('os.environ', {'HOMEWORK_PASS1_TWO_STAGE':'0'}):
            self.assertTrue(grader_pass1._pass1_two_stage_enabled(feedback_runtime=runtime))
            self.assertFalse(grader_pass1._pass1_two_stage_enabled())
        with tempfile.TemporaryDirectory() as tmp:
            args = snapshot_arguments(tmp)
            args.update(context=runtime.context, **runtime.dependencies)
            target = Path(tmp)/'snapshot'
            manifest = prepare_feedback_snapshot(target, **args)
            self.assertEqual(manifest['config_fingerprint'], runtime.fingerprint)
            self.assertEqual(read_feedback_snapshot(target)['snapshot_status'], 'complete')

    def test_fixed_document_manifest_is_frozen(self):
        from . import special_cases
        selected, _ = compose_skills(resolve_feedback_metadata('小学·四年级·英语·作业.pdf'))
        runtime = runtime_fixture('小学·四年级·英语·作业.pdf', skills=selected)
        case = selected[1]['content']['resources']['fixed_documents']['cases'][0]
        with patch.object(special_cases, 'load_document_special_case_manifest', side_effect=AssertionError('latest resource')):
            for sha, page, expected in [(case['source_document_sha256'],15,True), ('0'*64,15,False),
                                        (case['source_document_sha256'],14,False), ('',15,False)]:
                actual = special_cases.document_special_case_enabled('english',page,'english_visual_transcription_lock',
                    source_document_sha256=sha, feedback_runtime=runtime)
                self.assertEqual(actual, expected)
