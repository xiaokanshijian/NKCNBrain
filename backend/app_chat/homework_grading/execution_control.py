"""任务/阶段预算及同主机模型并发槽；SDK重试关闭，传输重试集中管理。"""
import contextvars
import functools
import hashlib
import inspect
import json
import os
from pathlib import Path
import random
import queue
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor as BaseExecutor
from contextlib import contextmanager
from types import SimpleNamespace

from filelock import FileLock, Timeout

_current = contextvars.ContextVar('homework_execution', default=None)


class BudgetExceeded(TimeoutError):
    def __init__(self, message, *, scope='execution', **details):
        super().__init__(message)
        self.budget_context = {'scope': scope, **details}


def budget_diagnostics(error):
    """只保存受控计时字段；不记录客户端、URL、HTTP头或异常响应正文。"""
    details = getattr(error, 'budget_context', None)
    if not isinstance(details, dict):
        return {}
    allowed = ('scope', 'role', 'phase', 'queue_wait_seconds', 'request_elapsed_seconds',
               'request_timeout_seconds', 'effective_request_timeout_seconds', 'queue_timeout_seconds',
               'stage_timeout_seconds', 'task_timeout_seconds', 'timeout_origin')
    return {key: details[key] for key in allowed if key in details and
            isinstance(details[key], (str, int, float))}


class TransportExhausted(RuntimeError):
    pass


def setting(runtime, key, default, minimum=1, maximum=86400):
    from .feedback_runtime import frozen_environment
    try:
        value = int(frozen_environment(runtime, key, str(default)))
    except (ValueError, TypeError):
        value = default
    return max(minimum, min(value, maximum))


def code_identity():
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(Path(__file__).parent.glob('*.py'))
               if not p.name.endswith('_test.py') and not p.name.startswith('test_')}
    from .stage_dependencies import SHARED_FILES
    for name in SHARED_FILES:
        sources[name] = hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    return {'actual_code_hashes': sources, 'actual_code_fingerprint': digest}


class Execution:
    def __init__(self, runtime=None, base=None, reuse=False):
        self.runtime, self.base, self.reuse = runtime, Path(base) if base else None, reuse
        self.request_seconds = setting(runtime, 'HOMEWORK_REQUEST_TIMEOUT', 180, maximum=900)
        self.review_request_seconds = setting(runtime, 'NKCN_HOMEWORK_GEMINI_TIMEOUT', 240, maximum=900)
        self.quality_request_seconds = setting(runtime, 'NKCN_HOMEWORK_RED_BLUE_TIMEOUT', 300, minimum=30, maximum=900)
        self.stage_seconds = setting(runtime, 'HOMEWORK_STAGE_TIMEOUT', 1800)
        self.task_seconds = setting(runtime, 'HOMEWORK_TASK_TIMEOUT', 7200)
        self.started = time.monotonic()
        self.deadline = self.started + self.task_seconds
        self.stage_deadline = min(self.deadline, self.started + self.stage_seconds)
        self.stage = 'startup'
        self.aborted = threading.Event()
        self.identity = code_identity()

    def remaining(self):
        if self.aborted.is_set():
            raise BudgetExceeded('同阶段执行已失败，已停止后续模型请求并保留检查点', scope='cancelled')
        now = time.monotonic()
        seconds = min(self.deadline, self.stage_deadline) - now
        if seconds <= 0:
            scope = 'task' if now >= self.deadline else 'stage'
            label = '整份任务' if scope == 'task' else '当前阶段'
            raise BudgetExceeded(label + '执行时间预算已用尽；已验证的检查点保留，可继续运行',
                                 scope=scope, phase=self.stage, stage_timeout_seconds=self.stage_seconds,
                                 task_timeout_seconds=self.task_seconds)
        return seconds

    def mark(self, stage):
        self.remaining()
        if stage != self.stage:
            self.stage, self.stage_deadline = stage, min(self.deadline, time.monotonic() + self.stage_seconds)

    def audit(self):
        return {**self.identity, 'basis_code_hashes': (self.runtime.dependencies['model_config']
                    .get('consumer_code_hashes', {}) if self.runtime else {}),
                'request_timeout_seconds': self.request_seconds,
                'review_request_timeout_seconds': self.review_request_seconds,
                'quality_request_timeout_seconds': self.quality_request_seconds,
                'stage_timeout_seconds': self.stage_seconds,
                'task_timeout_seconds': self.task_seconds, 'checkpoint_reuse_enabled': self.reuse}


def current_execution():
    return _current.get()


@contextmanager
def execution_scope(execution):
    token = _current.set(execution)
    try:
        yield execution
    finally:
        _current.reset(token)


def managed_execution(fn):
    @functools.wraps(fn)
    def run(*args, **kwargs):
        from .utils import safe_json_load, safe_json_dump
        bound = inspect.signature(fn).bind(*args, **kwargs)
        paths = bound.arguments['paths']
        path = Path(paths['manifest'])
        manifest = safe_json_load(path) if path.is_file() else {}
        execution = Execution(bound.arguments.get('feedback_runtime'), paths['base'],
                              bool(manifest.get('checkpoint_resume')))
        previous = manifest.get('execution_provenance', {}).get('actual_code_fingerprint')
        basis = execution.runtime.dependencies['model_config'].get('consumer_code_hashes') if execution.runtime else None
        changed = ((previous is not None and previous != execution.identity['actual_code_fingerprint'])
                   or (previous is None and bool(basis) and basis != execution.identity['actual_code_hashes']))
        from .stage_dependencies import enabled, basis as stage_basis, ORDER
        receipts = manifest.get('stage_receipts') or {}
        if enabled(execution.runtime) and any(r.get('schema') == 3 for r in receipts.values()):
            affected = [name for name in ORDER if name in receipts and receipts[name].get('schema') == 3
                        and receipts[name].get('basis') != stage_basis(execution.runtime, execution.identity['actual_code_hashes'], name)]
            manifest['dependency_restart'] = affected[0] if affected else ''
            changed = False
            if affected and affected[0] in ('layout', 'understanding', 'grading'):
                bound.arguments['scope_page_nums'] = None
                bound.arguments['force_preprocess_scope'] = False
        else:
            manifest.pop('dependency_restart', None)
        if changed:
            # 旧格式没有阶段依赖证据，继续执行原有严格保护。
            manifest['stage_receipts'] = {}
            manifest['warnings'] = list(dict.fromkeys(manifest.get('warnings', []) + [
                '批改程序已更新，本轮重新核验整份材料；原版本与原规则依据保留。']))
            bound.arguments['scope_page_nums'] = None
            bound.arguments['force_preprocess_scope'] = False
        manifest['execution_provenance'] = execution.audit()
        safe_json_dump(path, manifest)
        with execution_scope(execution):
            return fn(*bound.args, **bound.kwargs)
    return run


class ThreadPoolExecutor(BaseExecutor):
    """每次提交复制上下文；线程共享同一任务预算，不跨任务串用。"""
    def submit(self, fn, /, *args, **kwargs):
        return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            execution = current_execution()
            if execution is not None:
                execution.aborted.set()
        # cancel_futures 仅 Python 3.9+；3.8 环境（如当前 venv）需降级
        try:
            self.shutdown(wait=True, cancel_futures=exc_type is not None)
        except TypeError:
            self.shutdown(wait=True)
        return False


def retryable_transport(error):
    if isinstance(error, (BudgetExceeded, TransportExhausted)):
        return False
    status = getattr(error, 'status_code', None)
    if getattr(error, 'code', None) in ('insufficient_quota', 'billing_hard_limit_reached', 'invalid_api_key'):
        return False
    if status is not None:
        return status in (408, 409, 429) or 500 <= status <= 599
    from openai import APIConnectionError, APITimeoutError
    return isinstance(error, (TimeoutError, ConnectionError, APIConnectionError, APITimeoutError))


@contextmanager
def model_slot(execution, role):
    # 主机内所有Django进程共用OS文件锁；退出/崩溃后自动释放，不存放业务内容。
    root = Path(tempfile.gettempdir()) / 'nkcn-homework-model-slots'
    root.mkdir(exist_ok=True)
    try:
        count = max(1, min(32, int(os.environ.get('HOMEWORK_MODEL_CONCURRENCY', '4'))))
    except ValueError:
        count = 4
    deadline = time.monotonic() + min(execution.remaining(), execution.request_seconds)
    while True:
        execution.remaining()
        for number in range(count):
            lock = FileLock(str(root / f'call-{number}.lock'))
            try:
                lock.acquire(timeout=0)
            except Timeout:
                continue
            try:
                yield
            finally:
                lock.release()
            return
        if time.monotonic() >= deadline:
            raise BudgetExceeded('模型并发队列等待超时；请稍后继续运行', scope='queue', role=role,
                                 queue_timeout_seconds=execution.request_seconds)
        time.sleep(min(0.1, execution.remaining()))


def _request_once(client, role, execution, kwargs):
    from openai import OpenAI
    # 复核/评分使用各自冻结时限；排队限时独立，阶段和任务总预算始终约束两者。
    seconds = (execution.review_request_seconds if role == 'review' else
               execution.quality_request_seconds if role == 'quality' else execution.request_seconds)
    started = time.monotonic()
    timing = {'deadline': started + min(execution.request_seconds, execution.remaining()),
              'phase': 'queue', 'request_started': None, 'effective_request_timeout_seconds': 0}
    timing_lock = threading.Lock()
    cancelled = threading.Event()
    result_queue = queue.Queue(maxsize=1)

    def annotate(error, origin=None):
        if not isinstance(error, BudgetExceeded):
            return error
        now = time.monotonic()
        request_started = timing['request_started']
        error.budget_context.update(role=role, phase=execution.stage,
            queue_wait_seconds=round((request_started if request_started is not None else now) - started, 3),
            request_elapsed_seconds=round(max(0, now - request_started), 3) if request_started is not None else 0,
            request_timeout_seconds=seconds, queue_timeout_seconds=execution.request_seconds,
            effective_request_timeout_seconds=timing['effective_request_timeout_seconds'])
        if origin:
            error.budget_context['timeout_origin'] = origin
        return error

    def invoke():
        try:
            with model_slot(execution, role):
                with timing_lock:
                    if cancelled.is_set():
                        raise BudgetExceeded('本次模型排队已超时，未再发送请求', scope='queue')
                    timing['phase'] = 'request'
                    timing['request_started'] = time.monotonic()
                    if role in ('review', 'quality'):
                        timing['deadline'] = time.monotonic() + min(seconds, execution.remaining())
                    timeout = min(timing['deadline'] - time.monotonic(), execution.remaining())
                    timing['effective_request_timeout_seconds'] = round(max(0, timeout), 3)
                    if timeout <= 0:
                        raise BudgetExceeded('本次模型请求已超时', scope='request')
                actual = client.with_options(timeout=timeout, max_retries=0) if isinstance(client, OpenAI) else client
                result = actual.chat.completions.create(**kwargs)
                execution.remaining()
                result_queue.put((True, result))
        except BaseException as exc:
            # 复核SDK读超时归入本次请求预算，其他角色保留既有传输重试策略。
            from openai import APITimeoutError
            if role == 'review' and isinstance(exc, APITimeoutError):
                exc = annotate(BudgetExceeded('模型响应超时；已保存其他有效结果', scope='request'), 'sdk')
            result_queue.put((False, annotate(exc)))

    context = contextvars.copy_context()
    threading.Thread(target=context.run, args=(invoke,), name='homework-model-request', daemon=True).start()
    while True:
        try:
            execution.remaining()
            with timing_lock:
                left = timing['deadline'] - time.monotonic()
                if left <= 0:
                    cancelled.set()
                    scope = timing['phase']
                    message = ('模型并发队列等待超时，未取得调用槽位' if scope == 'queue' else
                               '模型响应超时；已验证结果保留，可稍后继续')
                    raise annotate(BudgetExceeded(message, scope=scope), 'controller')
            ok, result = result_queue.get(timeout=min(0.1, left))
            break
        except queue.Empty:
            continue
        except BaseException as exc:
            cancelled.set()
            # 迟到线程只接收HTTP响应，不落盘；槽位由它持有至真正退出，避免突破并发上限。
            raise annotate(exc)
    if not ok:
        raise result
    return result


def bounded_create(client, role, *, runtime=None, **kwargs):
    execution = current_execution() or Execution(runtime)
    for attempt in range(3):
        execution.remaining()
        try:
            return _request_once(client, role, execution, kwargs)
        except Exception as exc:
            if not retryable_transport(exc):
                raise
            if attempt == 2:
                raise TransportExhausted('模型连接暂时不可用，有限重试已耗尽') from exc
            delay = min(2 ** attempt + random.uniform(0, 0.25), execution.remaining())
            time.sleep(delay)
    raise AssertionError('unreachable')


def controlled_client(client, role, runtime=None):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: bounded_create(client, role, runtime=runtime, **kwargs))))
