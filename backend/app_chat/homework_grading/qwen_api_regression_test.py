import json
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_chat import scene_models
from app_chat.homework_grading import grader_pass1_5, llm_clients


class _FakeCompletions:
    def __init__(
        self,
        content='{"page": 1, "subject": "math", "questions": []}',
        fail_first=False,
    ):
        self.content = content
        self.fail_first = fail_first
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError('json mode unsupported')
        message = SimpleNamespace(content=self.content, reasoning_content='')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


class _FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def _fake_qwen_client(completions):
    fake_client = _FakeClient(completions)
    return mock.patch.object(llm_clients, '_qwen_client', return_value=fake_client)


class QwenApiRegressionTest(unittest.TestCase):
    def test_homework_qwen_defaults_to_qwen36_plus(self):
        homework_scene = scene_models.SCENE_SLOTS['homework_qwen']
        self.assertEqual(homework_scene['default'], 'qwen3.6-plus')
        self.assertEqual(homework_scene['options'][0], 'qwen3.6-plus')
        self.assertIn('qwen3.7-plus', homework_scene['options'])
        self.assertIn('qwen3.5-plus', homework_scene['options'])
        self.assertIn('qwen3.5-flash', homework_scene['options'])

        config_path = Path(__file__).resolve().parents[1] / 'scene_models_config.json'
        config = json.loads(config_path.read_text(encoding='utf-8'))
        self.assertEqual(config['values']['homework_qwen'], 'qwen3.6-plus')
        self.assertEqual(llm_clients.homework_qwen_model(), 'qwen3.6-plus')

    def test_qwen_thinking_call_omits_response_format(self):
        completions = _FakeCompletions()
        with _fake_qwen_client(completions):
            llm_clients._call_qwen_json([], {'enable_thinking': True, 'thinking_budget': 4096})

        self.assertNotIn('response_format', completions.calls[0])

    def test_non_thinking_call_keeps_response_format(self):
        completions = _FakeCompletions()
        with _fake_qwen_client(completions):
            llm_clients._call_qwen_json([], {'enable_thinking': False})

        self.assertEqual(completions.calls[0]['response_format'], {'type': 'json_object'})

    def test_response_format_fallback_is_only_for_non_thinking(self):
        completions = _FakeCompletions(fail_first=True)
        with _fake_qwen_client(completions):
            llm_clients._call_qwen_json([], {'enable_thinking': False})

        self.assertEqual(completions.calls[0]['response_format'], {'type': 'json_object'})
        self.assertNotIn('response_format', completions.calls[1])

    def test_thinking_call_failure_does_not_retry_json_mode_fallback(self):
        completions = _FakeCompletions(fail_first=True)
        with _fake_qwen_client(completions):
            with self.assertRaises(RuntimeError):
                llm_clients._call_qwen_json([], {'enable_thinking': True})

        self.assertEqual(len(completions.calls), 1)
        self.assertNotIn('response_format', completions.calls[0])

    def test_loads_json_accepts_fence_and_surrounding_text(self):
        fenced = '```json\n{"page": 1, "subject": "math", "questions": []}\n```'
        surrounded = '说明文字\n{"page": 2, "subject": "math", "questions": []}\n尾注'
        with_brace_in_string = '前缀 {"page": 3, "note": "学生写了 } 符号", "questions": []} 后缀 {"x": 1}'

        self.assertEqual(llm_clients._loads_json_with_retry_text(fenced)['page'], 1)
        self.assertEqual(llm_clients._loads_json_with_retry_text(surrounded)['page'], 2)
        self.assertEqual(llm_clients._loads_json_with_retry_text(with_brace_in_string)['page'], 3)

    def test_cross_page_math_thinking_omits_response_format_and_temperature(self):
        completions = _FakeCompletions('{"cross_page_group": [1], "corrections": []}')
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / 'math_01_page1.png'
            image_path.write_bytes(b'png')
            with _fake_qwen_client(completions):
                result = grader_pass1_5.grade_cross_page_group([str(image_path)], 'math', [1], boundaries={})

        self.assertEqual(result['cross_page_group'], [1])
        self.assertNotIn('response_format', completions.calls[0])
        self.assertNotIn('temperature', completions.calls[0])


if __name__ == '__main__':
    unittest.main()
