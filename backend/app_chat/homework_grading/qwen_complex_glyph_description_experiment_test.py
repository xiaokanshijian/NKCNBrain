import unittest
from types import SimpleNamespace
from unittest import mock

from app_chat.homework_grading import qwen_complex_glyph_description_experiment as qwen_c


class QwenComplexGlyphDescriptionExperimentTest(unittest.TestCase):
    def test_qwen_adapter_uses_non_thinking_json_mode_and_returns_content(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"slots":[]}'))])
        with mock.patch.object(qwen_c, '_call_qwen_json', return_value=response) as call:
            result = qwen_c.call_qwen_c_description_model([])
        self.assertEqual(result, '{"slots":[]}')
        call.assert_called_once_with([], {'enable_thinking': False}, temperature=0.1)

    def test_qwen_runner_has_its_own_output_directory(self):
        self.assertIn('qwen_complex_glyph_description_', str(qwen_c.DEFAULT_OUTPUT_DIR))
        self.assertEqual(qwen_c.BACKEND, 'qwen')


if __name__ == '__main__':
    unittest.main()
