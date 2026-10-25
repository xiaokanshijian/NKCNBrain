import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .feedback_metadata import resolve_feedback_metadata
from .feedback_runtime_service import build_request_runtime, restore_feedback_runtime
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .feedback_pipeline_test import SyntheticClient
from . import llm_clients


class RuntimeServiceTests(unittest.TestCase):
    def runtime(self, filename='大学·大二·嵌入式系统·试卷.pdf', data=None):
        data = dict(data or {})
        preprocess_mode = data.pop('preprocess_mode', None)
        with patch.object(llm_clients, 'homework_qwen_model', return_value='synthetic-qwen'), \
             patch.object(llm_clients, 'homework_deepseek_model', return_value='synthetic-deepseek'), \
             patch.object(llm_clients, 'homework_review_gemini_model', return_value='synthetic-review'):
            return build_request_runtime(
                resolve_feedback_metadata(filename), data,
                preprocess_mode=preprocess_mode,
            )

    def test_second_year_and_explicit_null_curriculum(self):
        runtime = self.runtime()
        self.assertEqual(runtime.context['grade_in_level'], 2)
        self.assertIsNone(runtime.context['grade_global'])
        self.assertIsNone(runtime.dependencies['curriculum'])
        self.assertEqual(len(runtime.dependencies['skills']), 1)
        self.assertIsNotNone(self.runtime('小学·二年级·数学·作业.pdf').dependencies['curriculum'])
        self.assertIsNone(self.runtime('小学·二年级·数学·作业.pdf', {'curriculum_selection': None}).dependencies['curriculum'])
        with self.assertRaises(ValueError):
            self.runtime(data={'curriculum_selection': {'resource_id': 'unsupported'}})

    def test_snapshot_restores_original_resources_and_models(self):
        runtime = self.runtime(data={'reference_text': '合成资料正文'})
        with tempfile.TemporaryDirectory() as tmp:
            args = snapshot_arguments(tmp)
            args.update(context=runtime.context, **runtime.dependencies)
            target = Path(tmp) / 'run'
            prepare_feedback_snapshot(target, **args)
            with patch.object(llm_clients, 'homework_qwen_model', side_effect=AssertionError('不能读取最新配置')):
                restored = restore_feedback_runtime(target)
            self.assertEqual(restored.fingerprint, runtime.fingerprint)
            self.assertEqual(restored.dependencies, runtime.dependencies)
            (target / 'skill_snapshot.json').write_text('{}')
            with self.assertRaises(ValueError):
                restore_feedback_runtime(target)

    def test_frozen_environment_and_reference_status(self):
        with patch.dict('os.environ', {'HOMEWORK_PASS1_TWO_STAGE': '0', 'DASHSCOPE_API_KEY': 'synthetic-secret'}):
            runtime = self.runtime(data={'context_docs': ['not-read.pdf']})
        self.assertEqual(runtime.dependencies['preprocessing']['environment']['HOMEWORK_PASS1_TWO_STAGE'], '0')
        self.assertNotIn('synthetic-secret', runtime._json)
        self.assertEqual(runtime.dependencies['references']['status'], 'provided_text_documents_not_read')
        self.assertEqual(runtime.dependencies['references']['documents'], [])

    def test_open_material_defaults_to_original_color(self):
        self.assertEqual(
            self.runtime('初中·初一·语文·作文.pdf').dependencies['preprocessing']['mode'],
            'off',
        )
        self.assertEqual(
            self.runtime('初中·初一·数学·笔记.pdf').dependencies['preprocessing']['mode'],
            'off',
        )
        self.assertEqual(
            self.runtime('初中·初一·数学·作业.pdf').dependencies['preprocessing']['mode'],
            'auto',
        )
        self.assertEqual(
            self.runtime('初中·初一·数学·笔记.pdf', {'preprocess_mode': 'scan'})
            .dependencies['preprocessing']['mode'],
            'scan',
        )

    def test_each_qwen_call_retains_its_frozen_policy(self):
        runtime = self.runtime('小学·四年级·数学·作业.pdf')
        client = SyntheticClient()
        with patch.object(llm_clients, '_qwen_client', return_value=client):
            llm_clients._call_qwen_json([], {'enable_thinking': False}, feedback_runtime=runtime)
            llm_clients._call_qwen_json([], {'enable_thinking': True, 'thinking_budget': 4096}, feedback_runtime=runtime)
            llm_clients._call_qwen_json([], {'enable_thinking': False}, temperature=0.0, feedback_runtime=runtime)
            with self.assertRaises(ValueError):
                llm_clients._call_qwen_json([], {'enable_thinking': True, 'thinking_budget': 9999}, feedback_runtime=runtime)
        self.assertEqual(client.calls[0]['model'], 'synthetic-qwen')
        self.assertIn('response_format', client.calls[0])
        self.assertNotIn('response_format', client.calls[1])
        self.assertTrue(client.calls[1]['extra_body']['enable_thinking'])

    def test_auxiliary_actions_reject_wrong_scope_and_source(self):
        from . import fixed_sample_crossout, u1_shadow
        with patch.object(u1_shadow, '_call_qwen_json_with_retry', side_effect=AssertionError('不应调用模型')):
            output, _ = u1_shadow.run_u1_shadow_page('unused', 'math', 1, {}, 'unused',
                                                     feedback_runtime=self.runtime())
            self.assertEqual(output['status'], 'not_covered')
        frozen = self.runtime('小学·四年级·数学·作业.pdf')
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'synthetic.png'
            source.write_bytes(b'synthetic image identity')
            with patch.object(fixed_sample_crossout, 'load_fixed_sample_crossout_manifest',
                              side_effect=AssertionError('不能读取最新清单')):
                _, audit = fixed_sample_crossout.repair_fixed_sample_image(
                    str(source), tmp, 'math', 15, feedback_runtime=frozen,
                    source_document_sha256='0' * 64)
            self.assertFalse(audit['applied'])
            self.assertEqual(audit['reason'], 'source_document_not_approved')


if __name__ == '__main__':
    unittest.main()
