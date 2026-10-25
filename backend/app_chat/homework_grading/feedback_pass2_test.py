"""合成批语输出与证据完整性测试。"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from . import grader_pass2 as p, prompts
from . import feedback_model
from .feedback_skills_test import runtime_fixture
from .feedback_runtime import stamp_feedback


class Pass2RuntimeTest(unittest.TestCase):
    def test_report_preserves_actual_context(self):
        r=runtime_fixture()
        memory=stamp_feedback({'error_questions':[{'qid_global':'p1:1','page':1,'id':'1'}]},r)
        ontology=stamp_feedback({'zones':{'blind_spot':[],'friction_zone':[],'zpd':[]}},r)
        feedback={'per_question_feedback':[{'qid_global':'p1:1','page':1,'id':'1','zone':'','comment':'合成反馈'}]}
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'_call_pass2_feedback_llm',return_value=feedback) as call:
            result=p.analyze_pass2(memory,'math','synthetic',str(Path(tmp)/'report.json'),str(Path(tmp)/'thinking.txt'),ontology=ontology,feedback_runtime=r)
        self.assertEqual(result['subject'],'physics')
        self.assertIs(call.call_args.kwargs['feedback_runtime'],r)
        self.assertEqual(result['feedback_execution']['config_fingerprint'],r.fingerprint)

    def test_empty_or_fake_evidence_rejected(self):
        memory={'error_questions':[{'qid_global':'p1:1','page':1,'id':'1'}]}
        for feedback in ([],[{'qid_global':'p99:1','page':1,'id':'1','comment':'synthetic'}]):
            with self.assertRaises(ValueError):p._validate_runtime_feedback({'per_question_feedback':feedback},memory)

    def test_both_prompt_paths_use_runtime(self):
        r=runtime_fixture()
        with patch.object(prompts,'load_curriculum_entries',side_effect=AssertionError('global curriculum')):
            for fn in (prompts.pass2_system,prompts.pass2_feedback_system):
                self.assertIn('physics',fn('math',feedback_runtime=r))

    def test_open_material_overview_contract_and_report_compatibility(self):
        runtime = runtime_fixture('初中·初一·语文·作文.pdf')
        valid = {
            'subject_and_layout': '初一作文稿纸，共三页，内容跨页连续。',
            'content_review': '文章围绕一次阅读经历展开。',
            'next_steps': ['第2页转折处补充人物反应。'],
        }
        self.assertEqual(
            p._validate_open_material_overview({'open_material_overview': valid}),
            valid,
        )
        for invalid in (
            {},
            {'open_material_overview': {'subject_and_layout': '', 'content_review': 'x', 'next_steps': ['x']}},
            {'open_material_overview': {'subject_and_layout': 'x', 'content_review': 'y', 'next_steps': []}},
            {'open_material_overview': {'subject_and_layout': 'x', 'content_review': 'y', 'next_steps': ['1', '2', '3']}},
        ):
            with self.assertRaises(ValueError):
                p._validate_open_material_overview(invalid)
        system = prompts.pass2_feedback_system('chinese', feedback_runtime=runtime)
        self.assertIn('open_material_overview', system)
        self.assertIn('不得输出百分制分数', system)
        self.assertIn('open_material_overview', prompts.pass2_system(
            'chinese', feedback_runtime=runtime,
        ))
        self.assertNotIn('open_material_overview', prompts.pass2_feedback_system(
            'physics', feedback_runtime=runtime_fixture(),
        ))
        memory = stamp_feedback({'error_questions': [{
            'qid_global': 'p1:paragraph-1', 'page': 1, 'id': 'paragraph-1',
        }]}, runtime)
        ontology = stamp_feedback({
            'zones': {'blind_spot': [], 'friction_zone': [], 'zpd': []},
        }, runtime)
        generated = {
            'open_material_overview': valid,
            'per_question_feedback': [{
                'qid_global': 'p1:paragraph-1', 'page': 1, 'id': 'paragraph-1',
                'zone': '', 'comment': '第1段主题明确，可补充场景细节。',
            }],
        }
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            p, '_call_pass2_feedback_llm', return_value=generated,
        ):
            result = p.analyze_pass2(
                memory, 'chinese', 'synthetic', str(Path(tmp) / 'report.json'),
                str(Path(tmp) / 'thinking.txt'), ontology=ontology,
                feedback_runtime=runtime,
            )
        self.assertEqual(result['open_material_overview'], valid)

    def test_invalid_open_overview_retries_once(self):
        runtime = runtime_fixture('初中·初一·语文·作文.pdf')
        payloads = [
            {'per_question_feedback': []},
            {
                'open_material_overview': {
                    'subject_and_layout': '三页连续作文。',
                    'content_review': '主题清楚。',
                    'next_steps': ['第2页补充转折细节。'],
                },
                'per_question_feedback': [{'qid_global': 'p1:1', 'page': 1, 'id': '1',
                                          'zone': '', 'comment': '主题清楚，可补充具体细节。'}],
            },
        ]

        class SequencedClient:
            def __init__(self):
                self.chat = SimpleNamespace(completions=self)
                self.calls = 0

            def create(self, **_kwargs):
                payload = payloads[self.calls]
                self.calls += 1
                message = SimpleNamespace(
                    content=json.dumps(payload, ensure_ascii=False),
                    reasoning_content='',
                )
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        client = SequencedClient()
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(p, '_deepseek_client', return_value=client), \
                patch.object(feedback_model, 'runtime_client', side_effect=lambda value, *_args: value):
            result = p._call_pass2_feedback_llm(
                {'error_questions': [{'qid_global': 'p1:1', 'page': 1, 'id': '1'}]},
                'chinese', 'synthetic', {}, str(Path(tmp) / 'thinking.txt'),
                feedback_runtime=runtime,
            )
        self.assertEqual(client.calls, 2)
        self.assertEqual(result['open_material_overview']['next_steps'], ['第2页补充转折细节。'])
