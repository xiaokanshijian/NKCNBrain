"""复核超时的隔离回归：虚拟计时与HTTP假传输，不调用真实模型。"""
import contextlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from openai import OpenAI, APITimeoutError

from . import execution_control as control, grader_pass1_review as review
from .completion import review_failure_message
from .execution_reliability_test import client
from .feedback_runtime import freeze_feedback_runtime
from .feedback_skills_test import runtime_fixture
from .model_output import request_json_object
from .utils import safe_json_load


class Clock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def completion_response():
    return httpx.Response(200, json={'id': 'synthetic', 'object': 'chat.completion',
        'created': 0, 'model': 'synthetic', 'choices': [{'index': 0, 'finish_reason': 'stop',
        'message': {'role': 'assistant', 'content': '{}'}}]})


class ReviewTimeoutTest(unittest.TestCase):
    def test_frozen_review_limit_is_independent_of_general_and_live_environment(self):
        runtime = runtime_fixture()
        deps = runtime.dependencies
        deps['preprocessing']['environment'] = {'NKCN_HOMEWORK_GEMINI_TIMEOUT': '420', 'HOMEWORK_REQUEST_TIMEOUT': '180'}
        frozen = freeze_feedback_runtime(runtime.context, **deps)
        with patch.dict('os.environ', {'NKCN_HOMEWORK_GEMINI_TIMEOUT': '900'}):
            execution = control.Execution(frozen)
            self.assertEqual(execution.review_request_seconds, 420)
            self.assertEqual(execution.request_seconds, 180)
            self.assertEqual(control.Execution(runtime).review_request_seconds, 240)
            self.assertEqual(execution.audit()['review_request_timeout_seconds'], 420)

    def run_sdk(self, role, queue_seconds=0, elapsed=0, stage_budget=1800, task_budget=7200):
        clock = Clock()
        observed = []
        @contextlib.contextmanager
        def slot(execution, role):
            clock.advance(queue_seconds)
            yield
        def handle(request):
            observed.append(request.extensions['timeout']['read'])
            clock.advance(elapsed)
            return completion_response()
        with patch.object(control, 'time', clock), patch.object(control, 'model_slot', slot):
            execution = control.Execution(runtime_fixture())
            execution.stage = 'review'
            execution.stage_deadline = stage_budget
            execution.deadline = task_budget
            with OpenAI(api_key='synthetic', base_url='http://example.invalid/v1',
                        http_client=httpx.Client(transport=httpx.MockTransport(handle))) as sdk:
                with control.execution_scope(execution):
                    result = control.bounded_create(sdk, role, model='synthetic', messages=[])
        return observed, result

    def test_review_sdk_gets_240_seconds_and_accepts_response_after_180(self):
        observed, result = self.run_sdk('review', elapsed=200)
        self.assertEqual(observed, [240])
        self.assertEqual(result.choices[0].message.content, '{}')

    def test_queue_wait_does_not_consume_review_or_quality_response_budget(self):
        self.assertEqual(self.run_sdk('review', queue_seconds=100)[0], [240])
        self.assertEqual(self.run_sdk('quality', queue_seconds=100)[0], [300])
        # 普通识别保留原有180秒总请求约束。
        self.assertEqual(self.run_sdk('qwen', queue_seconds=100)[0], [80])

    def test_stage_and_task_caps_still_limit_review_sdk(self):
        self.assertEqual(self.run_sdk('review', queue_seconds=100, stage_budget=150)[0], [50])
        self.assertEqual(self.run_sdk('review', queue_seconds=100, task_budget=130)[0], [30])

    def test_stage_and_task_expiry_have_distinct_scopes(self):
        for stage, task, expected in ((20, 100, 'stage'), (100, 20, 'task')):
            with self.assertRaises(control.BudgetExceeded) as caught:
                self.run_sdk('review', elapsed=30, stage_budget=stage, task_budget=task)
            self.assertEqual(caught.exception.budget_context['scope'], expected)

    def test_sdk_timeout_is_a_single_request_failure_with_safe_diagnostics(self):
        calls = []
        def handle(request):
            calls.append(request)
            raise httpx.ReadTimeout('synthetic private URL must not be persisted', request=request)
        with OpenAI(api_key='synthetic', base_url='http://example.invalid/v1',
                    http_client=httpx.Client(transport=httpx.MockTransport(handle))) as sdk:
            with self.assertRaises(control.BudgetExceeded) as caught:
                control.bounded_create(sdk, 'review', model='synthetic', messages=[])
        self.assertEqual(len(calls), 1)
        diagnostics = control.budget_diagnostics(caught.exception)
        self.assertEqual(diagnostics['scope'], 'request')
        self.assertEqual(diagnostics['timeout_origin'], 'sdk')
        self.assertEqual(diagnostics['request_timeout_seconds'], 240)
        self.assertNotIn('private', str(caught.exception))

    def test_other_roles_keep_existing_sdk_timeout_retry_policy(self):
        error = APITimeoutError(request=httpx.Request('POST', 'http://example.invalid'))
        call = Mock(side_effect=error)
        with patch.object(control.time, 'sleep'), self.assertRaises(control.TransportExhausted):
            control.bounded_create(client(call), 'qwen')
        self.assertEqual(call.call_count, 3)

    def test_real_queue_timeout_sends_no_request(self):
        execution = control.Execution()
        execution.request_seconds = 0.04
        execution.review_request_seconds = 0.3
        call = Mock()
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(control, 'tempfile', SimpleNamespace(gettempdir=lambda: tmp)), \
                patch.dict('os.environ', {'HOMEWORK_MODEL_CONCURRENCY': '1'}):
            root = Path(tmp) / 'nkcn-homework-model-slots'
            root.mkdir()
            lock = control.FileLock(str(root / 'call-0.lock'))
            with lock:
                with control.execution_scope(execution), self.assertRaises(control.BudgetExceeded) as caught:
                    control.bounded_create(client(call), 'review')
            time.sleep(0.15)  # 等待已取消的排队线程退出，再回收临时目录。
        call.assert_not_called()
        self.assertEqual(caught.exception.budget_context['scope'], 'queue')

    def test_request_deadline_discards_late_review_without_retries(self):
        entered, release, exited = threading.Event(), threading.Event(), threading.Event()
        execution = control.Execution()
        execution.review_request_seconds = 0.04
        def slow(**kwargs):
            entered.set()
            release.wait(1)
            exited.set()
            return 'late'
        call = Mock(side_effect=slow)
        try:
            with control.execution_scope(execution), self.assertRaises(control.BudgetExceeded) as caught:
                control.bounded_create(client(call), 'review')
            self.assertTrue(entered.is_set())
            self.assertFalse(exited.is_set())
            self.assertEqual(caught.exception.budget_context['scope'], 'request')
            self.assertEqual(call.call_count, 1)
        finally:
            release.set()
            exited.wait(1)
            time.sleep(0.05)

    def test_failed_page_and_model_audit_keep_scope_and_ui_reason(self):
        failure = control.BudgetExceeded('合成复核响应超时', scope='request', role='review',
                                          request_timeout_seconds=240, queue_wait_seconds=12)
        with tempfile.TemporaryDirectory() as tmp:
            audit = Path(tmp) / 'model.json'
            with self.assertRaises(control.BudgetExceeded):
                request_json_object(Mock(side_effect=failure), [], parser=json.loads, validate=lambda x: x,
                                    audit_path=audit, stage='复核')
            self.assertEqual(safe_json_load(audit)['attempts'][0]['budget']['scope'], 'request')
            page = Path(tmp) / 'math_synthetic_page1.json'
            with patch.object(review, '_review_one_page', side_effect=failure):
                result = review._run_review_candidate(str(page), 'synthetic.png', 'math', 4, 2)
            self.assertEqual(safe_json_load(review._review_json_path(str(page)))['budget']['scope'], 'request')
            message = review_failure_message({'failures': [result]})
            self.assertIn('第1页等待模型响应超时', message)
            self.assertIn('240秒', message)
            self.assertNotIn('BudgetExceeded', message)

    def test_directory_review_keeps_failed_required_unit_and_specific_reason(self):
        from .feedback_runtime import stamp_feedback
        from .utils import safe_json_dump
        from .completion import summarize_completion
        from .completion_test import complete_manifest
        frozen = runtime_fixture('初中·初一·数学·笔记.pdf')
        failure = control.BudgetExceeded('合成复核响应超时', scope='request', role='review',
                                        request_timeout_seconds=240)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            page = base / 'math_synthetic_page1.json'
            safe_json_dump(page, stamp_feedback({'page': 1, 'questions': [
                {'id': '1', 'verdict': 'partial', 'student_answer': 'synthetic', 'error_type': '待核对'}]}, frozen))
            image = base / 'synthetic.png'
            image.write_bytes(b'synthetic image; model stage is replaced')
            with patch.object(review, '_review_one_page', side_effect=failure):
                result = review.review_pass1_dir(str(base), [{'page': 1, 'clean_abs_path': str(image)}],
                                                'math', workers=1, feedback_runtime=frozen)
            self.assertEqual(result['errors'], 1)
            self.assertEqual(result['required_units'][0]['status'], 'failed')
            self.assertEqual(result['failures'][0]['budget']['scope'], 'request')
            manifest = complete_manifest()
            manifest['pass1_review'] = result
            completion = summarize_completion(manifest)
            self.assertFalse(completion['report_usable'])
            message = next(i['message'] for i in completion['issues'] if i['code'] == 'review_incomplete')
            self.assertIn('第1页等待模型响应超时', message)
