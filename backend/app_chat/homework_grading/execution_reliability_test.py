"""第三批离线验证：预算、传输分类、跨任务并发、分批及检查点依赖失效。"""
import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from . import execution_control as control, grader_pass2, llm_clients
from .execution_checkpoints import checkpoint_key, receipt_matches, record_stage_receipt
from .feedback_skills_test import runtime_fixture
from .feedback_runtime import freeze_feedback_runtime
from .model_output import request_json_object, ModelOutputError
from .utils import safe_json_dump, safe_json_load


def response(payload, finish='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish,
        message=SimpleNamespace(content=json.dumps(payload), reasoning_content=''))])


def client(call):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=call)))


class HTTPError(RuntimeError):
    def __init__(self, code):
        super().__init__('synthetic HTTP error')
        self.status_code = code


class ExecutionControlTest(unittest.TestCase):
    def test_transient_retries_are_bounded_and_permanent_failures_are_not_retried(self):
        with patch.object(control.time, 'sleep'):
            for errors in ([HTTPError(429), HTTPError(503)], [TimeoutError(), ConnectionError()]):
                call = Mock(side_effect=[*errors, 'ok'])
                self.assertEqual(control.bounded_create(client(call), 'qwen'), 'ok')
                self.assertEqual(call.call_count, 3)
            call = Mock(side_effect=HTTPError(503))
            with self.assertRaises(control.TransportExhausted):
                control.bounded_create(client(call), 'qwen')
            self.assertEqual(call.call_count, 3)
            for error in (HTTPError(400), HTTPError(401), HTTPError(403), ValueError('bug'), OSError('disk')):
                call = Mock(side_effect=error)
                with self.assertRaises(type(error)):
                    control.bounded_create(client(call), 'qwen')
                self.assertEqual(call.call_count, 1)

    def test_format_fallback_does_not_repeat_network_or_auth_errors(self):
        for status in (401, 429):
            error = HTTPError(status)
            error.args = ('response_format error',)
            self.assertFalse(llm_clients._is_response_format_error(error))
        call = Mock(side_effect=HTTPError(401))
        with patch.object(llm_clients, '_qwen_client', return_value=client(call)), self.assertRaises(HTTPError):
            llm_clients._call_qwen_json([], {'enable_thinking': False})
        self.assertEqual(call.call_count, 1)

    def test_task_and_stage_deadlines_cannot_be_reset_by_retry(self):
        execution = control.Execution()
        execution.deadline = time.monotonic() - 1
        call = Mock()
        with control.execution_scope(execution), self.assertRaises(control.BudgetExceeded):
            control.bounded_create(client(call), 'qwen')
        call.assert_not_called()
        with self.assertRaises(control.BudgetExceeded):
            execution.mark('another-stage')
        execution = control.Execution()
        execution.stage_deadline = time.monotonic() - 1
        with self.assertRaises(control.BudgetExceeded):
            execution.remaining()

    def test_sdk_timeout_and_retries_are_explicit(self):
        import httpx
        from openai import OpenAI
        observed = []
        def handle(request):
            observed.append(request.extensions['timeout'])
            return httpx.Response(200, json={'id': 'synthetic', 'object': 'chat.completion',
                'created': 0, 'model': 'synthetic', 'choices': [{'index': 0, 'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': '{}'}}]})
        execution = control.Execution()
        execution.request_seconds = 2
        with OpenAI(api_key='synthetic', base_url='http://example.invalid/v1',
                    http_client=httpx.Client(transport=httpx.MockTransport(handle))) as sdk:
            with control.execution_scope(execution):
                control.bounded_create(sdk, 'qwen', model='synthetic', messages=[])
        self.assertEqual(len(observed), 1)
        self.assertLessEqual(observed[0]['read'], 2)

    def test_hard_deadline_discards_late_result_and_keeps_slot_until_transport_exits(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        execution = control.Execution();execution.request_seconds = 0.04
        def blocked(**kwargs):
            entered.set()
            release.wait(2)
            finished.set()
            return 'late-result'
        with tempfile.TemporaryDirectory() as tmp, patch.object(control.tempfile, 'gettempdir', return_value=tmp), \
                patch.dict('os.environ', {'HOMEWORK_MODEL_CONCURRENCY': '1'}):
            try:
                started=time.monotonic()
                with control.execution_scope(execution), self.assertRaises(control.BudgetExceeded):
                    control.bounded_create(client(blocked),'qwen')
                self.assertLess(time.monotonic()-started,0.5)
                self.assertTrue(entered.is_set())
                self.assertFalse(finished.is_set())
                other=Mock(return_value='should not start')
                with control.execution_scope(execution), self.assertRaises(control.BudgetExceeded):
                    control.bounded_create(client(other),'qwen')
                other.assert_not_called()
            finally:
                release.set();finished.wait(1)
                # 等待运输线程释放锁和已取消的队列等待者退出，临时目录再清理。
                time.sleep(0.15)

    def test_multiple_tasks_share_slots_and_worker_context_stays_separate(self):
        active, peak = 0, 0
        lock = threading.Lock()
        executions = [control.Execution(), control.Execution()]
        def call(**kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(active, peak)
            time.sleep(0.025)
            with lock:
                active -= 1
            return control.current_execution()
        with tempfile.TemporaryDirectory() as tmp, patch.object(control.tempfile, 'gettempdir', return_value=tmp), \
                patch.dict('os.environ', {'HOMEWORK_MODEL_CONCURRENCY': '2'}):
            with control.ThreadPoolExecutor(max_workers=8) as pool:
                futures = []
                for number in range(8):
                    execution = executions[number % 2]
                    with control.execution_scope(execution):
                        futures.append((execution, pool.submit(control.bounded_create, client(call), 'qwen')))
                for expected, future in futures:
                    self.assertIs(future.result(), expected)
        self.assertLessEqual(peak, 2)
        self.assertEqual(active, 0)
        self.assertIsNone(control.current_execution())

    def test_exhausted_transport_is_not_retried_by_output_or_page_wrappers(self):
        from .staged_pipeline import _run_pass1_page_with_retry
        call = Mock(side_effect=control.TransportExhausted('synthetic'))
        with self.assertRaises(control.TransportExhausted):
            _run_pass1_page_with_retry(1, 'synthetic', lambda: request_json_object(call, [],
                parser=json.loads, validate=lambda x: x, audit_path=None, stage='test', retry_call_errors=True))
        self.assertEqual(call.call_count, 1)

    def test_fatal_page_failure_stops_sibling_wait_and_queued_work(self):
        execution=control.Execution();entered=threading.Event();release=threading.Event()
        def slow(**kwargs):
            entered.set();release.wait(2);return 'late'
        try:
            started=time.monotonic()
            with control.execution_scope(execution), self.assertRaises(ValueError):
                with control.ThreadPoolExecutor(max_workers=2) as pool:
                    waiting=pool.submit(control.bounded_create,client(slow),'qwen')
                    self.assertTrue(entered.wait(1))
                    raise ValueError('fatal page failure')
            self.assertLess(time.monotonic()-started,0.6)
            self.assertIsInstance(waiting.exception(),control.BudgetExceeded)
        finally:
            release.set();time.sleep(0.05)


class CheckpointTest(unittest.TestCase):
    def test_failed_whole_run_can_resume_without_a_session_plan(self):
        from .feedback_rerun_plan import prepare_rerun_workspace
        from .homework_versions import _copy_homework_version_workspace
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp)/'old';destination = Path(tmp)/'new'
            safe_json_dump(original/'manifest.json', {'status':'failed'})
            safe_json_dump(original/'homework_grading/checkpoints/accepted.json', {'synthetic':True})
            _copy_homework_version_workspace(str(original/'homework_grading'), str(destination/'homework_grading'))
            plan={'stage':'all','resume':True,'clone':True}
            result=prepare_rerun_workspace(destination, original,'synthetic','homework_synthetic',
                                           runtime_fixture(),plan,{'resume':True})
            self.assertTrue(result['checkpoint_resume'])
            self.assertIsNone(result['scope_page_nums'])
            self.assertFalse(result['force_preprocess_scope'])
            self.assertEqual(safe_json_load(destination/'homework_grading/checkpoints/accepted.json'),{'synthetic':True})

    def test_reuse_validates_input_configuration_code_and_saved_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = runtime_fixture()
            execution = control.Execution(runtime, tmp, reuse=True)
            call = Mock(return_value=response({'accepted': True}))
            def run(messages):
                return request_json_object(call, messages, parser=json.loads, validate=lambda x: x,
                    audit_path=str(Path(tmp)/'responses.json'), stage='test')
            with control.execution_scope(execution):
                run([{'role': 'user', 'content': 'image-or-text-A'}])
                run([{'role': 'user', 'content': 'image-or-text-A'}])
                self.assertEqual(call.call_count, 1)
                run([{'role': 'user', 'content': 'image-or-text-B'}])
                self.assertEqual(call.call_count, 2)
                execution.identity['actual_code_fingerprint'] = 'changed-code'
                run([{'role': 'user', 'content': 'image-or-text-B'}])
                self.assertEqual(call.call_count, 3)
                key = checkpoint_key([{'role': 'user', 'content': 'image-or-text-B'}], 'test')
                path = Path(tmp)/'checkpoints'/(key + '.json')
                value = safe_json_load(path);value['result'] = {'tampered': True};safe_json_dump(path, value)
                run([{'role': 'user', 'content': 'image-or-text-B'}])
                self.assertEqual(call.call_count, 4)
                deps = runtime.dependencies;deps['references']['reference_text'] = 'changed reference'
                execution.runtime = freeze_feedback_runtime(runtime.context, **deps)
                run([{'role': 'user', 'content': 'image-or-text-B'}])
                self.assertEqual(call.call_count, 5)

    def test_rejected_or_partial_responses_never_become_reusable_success(self):
        with tempfile.TemporaryDirectory() as tmp, control.execution_scope(control.Execution(runtime_fixture(), tmp, True)):
            with self.assertRaises(ModelOutputError):
                request_json_object(lambda _: response([]), [], parser=json.loads, validate=lambda x: x,
                                    audit_path=None, stage='test')
            self.assertFalse((Path(tmp)/'checkpoints').exists())

    def test_stage_receipt_rejects_changed_images_or_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'clean').mkdir();(base/'clean/p1.png').write_bytes(b'synthetic')
            paths={'base':tmp};manifest={'config_fingerprint':'configuration'}
            record_stage_receipt(paths, manifest, 'layout')
            self.assertTrue(receipt_matches(paths, manifest, 'layout'))
            self.assertFalse(receipt_matches(paths, manifest, 'layout', {'actual_code_fingerprint':'changed'}))
            (base/'clean/p1.png').write_bytes(b'changed')
            self.assertFalse(receipt_matches(paths, manifest, 'layout'))


class Pass2BatchTest(unittest.TestCase):
    def test_interrupted_batch_reuses_only_completed_requests(self):
        runtime=runtime_fixture()
        memory={'error_questions':[{'qid_global':f'p1:{n}','id':str(n),'page':1} for n in range(13)]}
        fail=True; calls=[]
        def create(**kwargs):
            selected=json.loads(kwargs['messages'][1]['content'])['error_questions']
            calls.append([q['qid_global'] for q in selected])
            if fail and len(selected)==1:
                raise HTTPError(401)
            return response({'per_question_feedback':[dict(q,comment='synthetic') for q in selected]})
        with tempfile.TemporaryDirectory() as tmp, control.execution_scope(control.Execution(runtime,tmp,True)), \
                patch.object(grader_pass2,'_deepseek_client',return_value=client(create)), \
                patch.object(grader_pass2,'pass2_feedback_user',side_effect=lambda m,*a,**kw:json.dumps(m)):
            def run():
                return grader_pass2._call_pass2_feedback_llm(memory,'physics','x',{},str(Path(tmp)/'thinking.txt'),feedback_runtime=runtime)
            with self.assertRaises(HTTPError):run()
            fail=False
            result=run()
        self.assertEqual([len(x) for x in calls],[12,1,1])
        self.assertEqual(len(result['per_question_feedback']),13)

    def test_batches_use_same_diagnosis_and_join_exact_coverage(self):
        runtime=runtime_fixture('初中·初一·历史·笔记.pdf')
        memory={'error_questions':[{'qid_global':f'p1:{n}', 'id':str(n), 'page':1,
                 'student_answer':'合成观察', 'note_role':'note', 'verdict':'correct'} for n in range(1, 28)]}
        ontology={'zones':{'blind_spot':[], 'friction_zone':[], 'zpd':[]}}
        seen=[]
        def create(**kwargs):
            selected=json.loads(kwargs['messages'][1]['content'])['error_questions']
            seen.append([q['qid_global'] for q in selected])
            payload={'per_question_feedback':[{'qid_global':q['qid_global'],'id':q['id'],
                     'page':q['page'],'zone':'','comment':'可见文字。'} for q in selected],
                     'open_material_overview':{'subject_and_layout':'整份笔记。','content_review':'有可定位观察。',
                                               'next_steps':['核对所记内容。']}}
            return response(payload)
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(grader_pass2, '_deepseek_client', return_value=client(create)), \
                patch.object(grader_pass2, 'pass2_feedback_user', side_effect=lambda m,*a,**kw:json.dumps(m)):
            result=grader_pass2._call_pass2_feedback_llm(memory,'history','synthetic',ontology,
                str(Path(tmp)/'thinking.txt'),feedback_runtime=runtime)
            self.assertEqual(len(list(Path(tmp).glob('*.responses.json'))),3)
        self.assertEqual([len(x) for x in seen],[12,12,3])
        self.assertEqual([x['qid_global'] for x in result['per_question_feedback']],
                         [x['qid_global'] for x in memory['error_questions']])
        self.assertEqual(result['open_material_overview']['subject_and_layout'],'整份笔记。')

    def test_truncated_batch_splits_and_single_item_truncation_stops(self):
        from .model_output import OutputTruncatedError
        runtime=runtime_fixture()
        memory={'error_questions':[{'qid_global':f'p1:{n}','id':str(n),'page':1} for n in range(3)]}
        calls=[]
        def batch(m, *args, **kwargs):
            items=m['error_questions'];calls.append(len(items))
            if len(items)>1:
                raise OutputTruncatedError('synthetic length')
            return {'per_question_feedback':[dict(items[0],comment='synthetic')]}
        with patch.object(grader_pass2,'_call_pass2_feedback_batch',side_effect=batch):
            result=grader_pass2._call_pass2_feedback_llm(memory,'physics','x',{},'x',feedback_runtime=runtime)
        self.assertEqual(len(result['per_question_feedback']),3)
        self.assertEqual(calls,[3,1,2,1,1])
        with patch.object(grader_pass2,'_call_pass2_feedback_batch',side_effect=OutputTruncatedError('length')) as call:
            with self.assertRaises(OutputTruncatedError):
                grader_pass2._call_pass2_feedback_llm({'error_questions':memory['error_questions'][:1]},
                    'physics','x',{},'x',feedback_runtime=runtime)
            self.assertEqual(call.call_count,1)


if __name__ == '__main__':
    unittest.main()
