"""显式配置开关的离线参数回归，不读取真实图像或调用模型。"""
import unittest
from unittest.mock import patch
from . import grader_pass1_5, llm_clients
from .qwen_api_regression_test import _FakeCompletions, _fake_qwen_client


class ExplicitQwenTest(unittest.TestCase):
    def test_cross_page_thinking_both_modes(self):
        for flag in ('0','1'):
            completions=_FakeCompletions('{"corrections": []}')
            with patch.dict('os.environ',{'HOMEWORK_PASS1_5_MATH_THINKING':flag}),patch.object(grader_pass1_5,'image_to_data_uri',return_value='synthetic'),_fake_qwen_client(completions):
                grader_pass1_5.grade_cross_page_group(['synthetic.png'],'math',[1],{})
            request=completions.calls[0]
            self.assertEqual(request['extra_body']['enable_thinking'],flag=='1')
            self.assertEqual('response_format' in request,flag=='0')
            self.assertNotIn('temperature',request)

    def test_non_thinking_retry(self):
        completions=_FakeCompletions(fail_first=True)
        with _fake_qwen_client(completions):
            llm_clients._call_qwen_json([],{'enable_thinking':False})
        self.assertEqual(len(completions.calls),2)
        self.assertIn('response_format',completions.calls[0])
        self.assertNotIn('response_format',completions.calls[1])
