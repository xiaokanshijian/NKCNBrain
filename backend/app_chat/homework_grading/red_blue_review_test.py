import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from app_chat.homework_grading import llm_clients
from app_chat.homework_grading.red_blue_review import (
    EARLY_STAGE_FEEDBACK_ENV,
    build_iteration_context,
    build_review_evidence,
    compile_iteration_guidance,
    evaluate_homework_red_blue,
    normalize_review,
)


class _FakeCompletions:
    def __init__(self, fail_format=False):
        self.calls = []
        self.fail_format = fail_format

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_format and len(self.calls) == 1:
            raise ValueError('unsupported parameter: response_format')
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{}', reasoning_content='thinking'))]
        )


class _FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def _raw_review():
    dimensions = {
        'evidence_fidelity': {'score': 4.0, 'reason': '证据清楚', 'evidence_refs': ['p1:1']},
        'judgment_consistency': {'score': 3.0, 'reason': '边界尚可', 'evidence_refs': ['p1:1']},
        'diagnostic_value': {'score': 4.5, 'reason': '诊断具体', 'evidence_refs': ['p1:1']},
        'actionability': {'score': 4.0, 'reason': '建议可执行', 'evidence_refs': ['p1:1']},
        'closed_loop_fusion': {'score': 3.5, 'reason': '形成闭环', 'evidence_refs': ['p1:1']},
    }
    return {
        'dimensions': dimensions,
        'reason': '证据与教学建议能够对应。',
        'suggestions': [{
            'id': 's1',
            'priority': 'high',
            'target_stage': 'grading',
            'action': '收紧诊断证据引用',
            'why': '部分结论跨度较大',
            'acceptance_criteria': '每条诊断都引用真实题号',
            'evidence_refs': ['p1:1', 'p9:9'],
        }],
    }


class RedBlueReviewTest(unittest.TestCase):
    def _paths(self, root):
        base = os.path.join(root, 'homework_grading')
        report = os.path.join(base, 'pass2_report')
        os.makedirs(report, exist_ok=True)
        return {
            'base': base,
            'pass1_json': os.path.join(base, 'pass1_json'),
            'pass2_report': report,
        }

    def test_kimi_call_uses_fixed_model_and_top_level_high(self):
        completions = _FakeCompletions()
        with mock.patch.object(llm_clients, '_homework_red_blue_client', return_value=_FakeClient(completions)):
            llm_clients._call_homework_red_blue_json([{'role': 'user', 'content': 'test'}])
        call = completions.calls[0]
        self.assertEqual(call['model'], 'kimi-k3')
        self.assertEqual(call['reasoning_effort'], 'high')
        self.assertNotIn('extra_body', call)
        self.assertEqual(call['temperature'], 1.0)
        self.assertNotIn('top_p', call)
        self.assertEqual(call['max_completion_tokens'], 12000)

    def test_response_format_fallback_keeps_kimi_high(self):
        completions = _FakeCompletions(fail_format=True)
        with mock.patch.object(llm_clients, '_homework_red_blue_client', return_value=_FakeClient(completions)):
            llm_clients._call_homework_red_blue_json([{'role': 'user', 'content': 'test'}])
        self.assertEqual(len(completions.calls), 2)
        self.assertIn('response_format', completions.calls[0])
        self.assertNotIn('response_format', completions.calls[1])
        self.assertEqual(completions.calls[1]['model'], 'kimi-k3')
        self.assertEqual(completions.calls[1]['reasoning_effort'], 'high')

    def test_non_json_parameter_error_does_not_trigger_parameter_downgrade(self):
        completions = _FakeCompletions()
        completions.create = mock.Mock(side_effect=ValueError('unsupported parameter: reasoning_effort'))
        with mock.patch.object(
            llm_clients,
            '_homework_red_blue_client',
            return_value=_FakeClient(completions),
        ):
            with self.assertRaises(ValueError):
                llm_clients._call_homework_red_blue_json([{'role': 'user', 'content': 'test'}])
        self.assertEqual(completions.create.call_count, 1)

    def test_key_priority(self):
        captured = {}

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        cfg = {'api_key': 'legacy', 'base_url': 'https://legacy.example/v1'}
        with mock.patch.dict(os.environ, {'MOONSHOT_API_KEY': 'moonshot', 'KIMI_API_KEY': 'kimi'}, clear=True):
            with mock.patch('app_chat.scene_models.resolve_openai_cfg_from_abbr', return_value=cfg):
                with mock.patch.object(llm_clients, 'OpenAI', FakeOpenAI):
                    llm_clients._homework_red_blue_client()
        self.assertEqual(captured['api_key'], 'moonshot')
        self.assertEqual(captured['base_url'], 'https://legacy.example/v1/')
        self.assertEqual(captured['timeout'], 300)
        self.assertEqual(captured['max_retries'], 1)

    def test_kimi_key_and_dedicated_base_override(self):
        captured = {}

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        cfg = {'api_key': 'legacy', 'base_url': 'https://legacy.example/v1'}
        env = {
            'KIMI_API_KEY': 'kimi-only',
            'NKCN_HOMEWORK_RED_BLUE_BASE_URL': 'https://review.example/v1',
            'NKCN_HOMEWORK_RED_BLUE_TIMEOUT': '42',
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch('app_chat.scene_models.resolve_openai_cfg_from_abbr', return_value=cfg):
                with mock.patch.object(llm_clients, 'OpenAI', FakeOpenAI):
                    llm_clients._homework_red_blue_client()
        self.assertEqual(captured['api_key'], 'kimi-only')
        self.assertEqual(captured['base_url'], 'https://review.example/v1/')
        self.assertEqual(captured['timeout'], 42)

    def test_missing_env_key_does_not_fall_back_to_legacy_secret(self):
        cfg = {'api_key': 'legacy-secret', 'base_url': 'https://legacy.example/v1'}
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch('app_chat.scene_models.resolve_openai_cfg_from_abbr', return_value=cfg):
                with self.assertRaises(EnvironmentError):
                    llm_clients._homework_red_blue_client()

    def test_weight_rounding_color_and_ref_validation(self):
        evidence = {'allowed_evidence_refs': ['p1:1']}
        review = normalize_review(_raw_review(), evidence)
        self.assertEqual(review['score'], 3.9)
        self.assertEqual(review['red_score'], 4.3)
        self.assertEqual(review['blue_score'], 3.6)
        self.assertEqual(review['color'], 'red')
        self.assertEqual(review['suggestions'][0]['evidence_refs'], ['p1:1'])

    def test_score_clamp_and_color_boundary(self):
        raw = _raw_review()
        raw['dimensions']['evidence_fidelity']['score'] = 6
        raw['dimensions']['judgment_consistency']['score'] = -1
        raw['dimensions']['diagnostic_value']['score'] = 4.96
        review = normalize_review(raw, {'allowed_evidence_refs': ['p1:1']})
        scores = {item['key']: item['score'] for item in review['dimensions']}
        self.assertEqual(scores['evidence_fidelity'], 5.0)
        self.assertEqual(scores['judgment_consistency'], 0.0)
        self.assertEqual(scores['diagnostic_value'], 5.0)

        boundary = _raw_review()
        boundary['dimensions']['evidence_fidelity']['score'] = 4.5
        boundary['dimensions']['judgment_consistency']['score'] = 4.5
        boundary['dimensions']['diagnostic_value']['score'] = 4.0
        boundary['dimensions']['actionability']['score'] = 4.0
        self.assertEqual(
            normalize_review(boundary, {'allowed_evidence_refs': ['p1:1']})['color'],
            'purple',
        )
        boundary['dimensions']['evidence_fidelity']['score'] = 4.6
        boundary['dimensions']['judgment_consistency']['score'] = 4.6
        self.assertEqual(
            normalize_review(boundary, {'allowed_evidence_refs': ['p1:1']})['color'],
            'blue',
        )

    def test_iteration_guidance_filters_stage_and_page(self):
        ready = normalize_review(_raw_review(), {'allowed_evidence_refs': ['p1:1']})
        context = build_iteration_context(ready, True, 'run-1', 'grading', ['s1'])
        self.assertIn('上轮批改质量卡标', compile_iteration_guidance(context, 'grading', {1}))
        self.assertEqual(compile_iteration_guidance(context, 'layout', {1}), '')
        self.assertEqual(compile_iteration_guidance(context, 'grading', {2}), '')

    def test_global_suggestion_survives_page_filter(self):
        raw = _raw_review()
        raw['suggestions'][0]['scope'] = 'global'
        ready = normalize_review(raw, {'allowed_evidence_refs': ['p1:1']})
        context = build_iteration_context(ready, True, 'run-1', 'grading', ['s2'])
        self.assertIn('上轮批改质量卡标', compile_iteration_guidance(context, 'grading', {2}))

    def test_disabled_iteration_has_no_guidance(self):
        context = build_iteration_context({}, False, 'run-1', 'grading')
        self.assertFalse(context['enabled'])
        self.assertEqual(compile_iteration_guidance(context, 'grading'), '')

    def test_early_stage_feedback_is_disabled_including_all_suggestions(self):
        raw = _raw_review()
        raw['suggestions'] = [
            {
                **raw['suggestions'][0],
                'id': 'layout-only',
                'target_stage': 'layout',
                'action': '调整版面检测',
            },
            {
                **raw['suggestions'][0],
                'id': 'all-stages',
                'target_stage': 'all',
                'action': '调整所有阶段',
            },
        ]
        ready = normalize_review(raw, {'allowed_evidence_refs': ['p1:1']})
        with mock.patch.dict(os.environ, {EARLY_STAGE_FEEDBACK_ENV: '0'}):
            context = build_iteration_context(ready, True, 'run-1', 'all', ['s1'])
        self.assertFalse(context['feedback_policy']['early_stages_enabled'])
        self.assertEqual(compile_iteration_guidance(context, 'layout', {1}), '')
        self.assertEqual(compile_iteration_guidance(context, 'understanding', {1}), '')
        grading = compile_iteration_guidance(context, 'grading', {1})
        self.assertIn('调整所有阶段', grading)
        self.assertNotIn('调整版面检测', grading)

    def test_early_stage_feedback_can_be_enabled_and_is_frozen_in_context(self):
        raw = _raw_review()
        raw['suggestions'][0]['target_stage'] = 'all'
        ready = normalize_review(raw, {'allowed_evidence_refs': ['p1:1']})
        with mock.patch.dict(os.environ, {EARLY_STAGE_FEEDBACK_ENV: '1'}):
            context = build_iteration_context(ready, True, 'run-1', 'all', ['s1'])
        self.assertTrue(context['feedback_policy']['early_stages_enabled'])
        with mock.patch.dict(os.environ, {EARLY_STAGE_FEEDBACK_ENV: '0'}):
            self.assertIn(
                '上轮批改质量卡标',
                compile_iteration_guidance(context, 'layout', {1}),
            )
            self.assertIn(
                '上轮批改质量卡标',
                compile_iteration_guidance(context, 'understanding', {1}),
            )

    def test_format_correction_still_uses_same_kimi_path(self):
        with tempfile.TemporaryDirectory() as root:
            paths = self._paths(root)
            invalid = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='not-json', reasoning_content='first'))]
            )
            valid = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content=json.dumps(_raw_review(), ensure_ascii=False),
                    reasoning_content='second',
                ))]
            )
            with mock.patch(
                'app_chat.homework_grading.red_blue_review.build_review_evidence',
                return_value={'allowed_evidence_refs': ['p1:1']},
            ), mock.patch(
                'app_chat.homework_grading.red_blue_review._call_homework_red_blue_json',
                side_effect=[invalid, valid],
            ) as call:
                review = evaluate_homework_red_blue(paths, {'subject': 'math'})
            self.assertEqual(call.call_count, 2)
            self.assertEqual(review['status'], 'ready')
            self.assertEqual(review['model'], 'kimi-k3')
            self.assertEqual(review['reasoning_effort'], 'high')
            self.assertTrue(os.path.isfile(os.path.join(paths['pass2_report'], 'red_blue_review.thinking.txt')))

    def test_schema_correction_is_attempted_once(self):
        with tempfile.TemporaryDirectory() as root:
            paths = self._paths(root)
            invalid = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"dimensions": {}}'))]
            )
            valid = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content=json.dumps(_raw_review(), ensure_ascii=False),
                ))]
            )
            with mock.patch(
                'app_chat.homework_grading.red_blue_review.build_review_evidence',
                return_value={'allowed_evidence_refs': ['p1:1']},
            ), mock.patch(
                'app_chat.homework_grading.red_blue_review._call_homework_red_blue_json',
                side_effect=[invalid, valid],
            ) as call:
                review = evaluate_homework_red_blue(paths, {'subject': 'math'})
            self.assertEqual(call.call_count, 2)
            self.assertEqual(review['status'], 'ready')

    def test_call_failure_is_persisted_as_soft_failure(self):
        with tempfile.TemporaryDirectory() as root:
            paths = self._paths(root)
            with mock.patch(
                'app_chat.homework_grading.red_blue_review.build_review_evidence',
                return_value={'allowed_evidence_refs': ['p1:1']},
            ), mock.patch(
                'app_chat.homework_grading.red_blue_review._call_homework_red_blue_json',
                side_effect=RuntimeError('quota denied'),
            ):
                review = evaluate_homework_red_blue(paths, {'subject': 'math'})
            self.assertEqual(review['status'], 'failed')
            self.assertEqual(review['model'], 'kimi-k3')
            with open(
                os.path.join(paths['pass2_report'], 'red_blue_review.json'),
                'r',
                encoding='utf-8',
            ) as file:
                persisted = json.load(file)
            self.assertEqual(persisted['status'], 'failed')

    def test_evidence_pack_prioritizes_uncertain_and_keeps_real_qids(self):
        with tempfile.TemporaryDirectory() as root:
            paths = self._paths(root)
            os.makedirs(paths['pass1_json'], exist_ok=True)
            with open(os.path.join(paths['pass1_json'], 'page_1.json'), 'w', encoding='utf-8') as file:
                json.dump({
                    'page': 1,
                    'questions': [
                        {'id': '1', 'verdict': 'correct', 'grading_confidence': 99},
                        {'id': '2', 'verdict': 'uncertain', 'grading_confidence': 45},
                    ],
                }, file)
            with open(
                os.path.join(paths['pass2_report'], 'math_abcdef12_report.json'),
                'w',
                encoding='utf-8',
            ) as file:
                json.dump({
                    'diagnosis': {'summary': '诊断'},
                    'zone_classification': {},
                    'per_question_feedback': [{'qid_global': 'p1:2', 'comment': '待复核'}],
                }, file)
            evidence = build_review_evidence(
                paths,
                {'group_id': 'homework_abcdef123456', 'subject': 'math'},
            )
            self.assertEqual(evidence['representative_questions'][0]['qid_global'], 'p1:2')
            self.assertEqual(evidence['allowed_evidence_refs'], ['p1:1', 'p1:2'])
            self.assertEqual(evidence['quality_metrics']['uncertain_count'], 1)


if __name__ == '__main__':
    unittest.main()
