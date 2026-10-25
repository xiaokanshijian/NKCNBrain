"""接收模型JSON：响应包和结构错误可有限重试，每次返回先落审计再消费。"""
import json
import os
import uuid
import copy

from .utils import safe_json_dump, safe_json_load, windows_io_path


class ModelOutputError(ValueError):
    """模型输出协议错误，不用于捕获网络、磁盘或业务代码异常。"""


class OutputTruncatedError(ModelOutputError):
    pass


def object_list(value, field):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ModelOutputError(f'{field}必须为对象数组')
    return value


def string_list(value, field):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ModelOutputError(f'{field}必须为文字数组')
    return value


def optional_text_fields(value, fields):
    for field in fields:
        if value.get(field) is not None and not isinstance(value[field], str):
            raise ModelOutputError(f'{field}必须为文字或空值')


def validate_zones(zones, field='zones'):
    if not isinstance(zones, dict):
        raise ModelOutputError(f'{field}必须为对象')
    for bucket, entries in zones.items():
        for item in object_list(entries, f'{field}.{bucket}'):
            optional_text_fields(item, ('knowledge_point', 'curriculum_id', 'rationale', 'suggested_next_step',
                                        'evidence_basis', 'trend', 'stability', 'fallback', 'comment'))
            for key in ('evidence', 'evidence_question_ids', 'content_context_evidence', 'evidence_curriculum_ids'):
                if key in item:
                    if item[key] is None:
                        item[key] = []
                    string_list(item[key], key)
            for cluster in object_list(item.get('error_clusters') or [], 'error_clusters'):
                optional_text_fields(cluster, ('cause',))
                if 'evidence' in cluster:
                    if cluster['evidence'] is None:
                        cluster['evidence'] = []
                    string_list(cluster['evidence'], 'error_clusters.evidence')


def _get(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _response_content(response, record, *, allow_reasoning_json=False):
    choices = _get(response, 'choices')
    if not isinstance(choices, (list, tuple)) or not choices:
        raise ModelOutputError('模型响应缺少choices')
    choice = choices[0]
    message = _get(choice, 'message')
    if message is None:
        raise ModelOutputError('模型响应缺少message')
    raw = _get(message, 'content')
    # 只保存返回正文，不保存请求、客户端对象、连接参数或HTTP头。
    try:
        json.dumps(raw, allow_nan=False)
        record['raw_response'] = raw
    except (TypeError, ValueError):
        record['raw_response'] = None
    record['content_type'] = type(raw).__name__
    finish = _get(choice, 'finish_reason')
    record['finish_reason'] = finish if isinstance(finish, str) else None
    reasoning = _get(message, 'reasoning_content')
    record['reasoning_content'] = reasoning if isinstance(reasoning, str) else ''
    record['content_source'] = 'content'
    if (allow_reasoning_json and (raw is None or isinstance(raw, str) and not raw.strip())
            and record['finish_reason'] == 'stop' and not _get(message, 'refusal')
            and isinstance(reasoning, str)):
        # 部分服务把最终JSON放在reasoning_content。只接收整段纯JSON对象，
        # 不从推理散文中抽取片段；原始正文不改写，随后仍走原结构/证据校验。
        try:
            candidate = json.loads(reasoning)
        except (ValueError, TypeError):
            candidate = None
        if isinstance(candidate, dict):
            record['content_source'] = 'reasoning_json'
            raw = reasoning
    if not isinstance(raw, str) or not raw.strip():
        raise ModelOutputError('模型正文必须为非空文字')
    if record['finish_reason'] in ('length', 'content_filter'):
        raise ModelOutputError('模型返回未完整结束：' + record['finish_reason'])
    return raw


def request_json_object(call, messages, *, parser, validate, audit_path, stage,
                        attempts=2, retry_prompt=None, thinking_path=None, error_path=None,
                        retry_call_errors=False, repair_plan=None, on_exhausted=None,
                        split_on_truncation=False, allow_reasoning_json=False):
    """纠正输出/校验错误；受控传输耗尽与写入失败不进入上层重复调用。"""
    history = []
    if audit_path and os.path.isfile(windows_io_path(audit_path)):
        previous = safe_json_load(audit_path)
        if isinstance(previous, dict) and isinstance(previous.get('attempts'), list):
            history = previous['attempts']
    invocation = uuid.uuid4().hex
    from .notebook_skills import audit_messages
    from .execution_checkpoints import checkpoint_key, load_checkpoint, save_checkpoint
    cache_key = checkpoint_key(messages, stage)
    cached = load_checkpoint(cache_key, validate)
    if cached is not None:
        if audit_path:
            history.append({'invocation_id': invocation, 'status': 'checkpoint_reused', 'checkpoint': cache_key,
                            'notebook_skills': audit_messages(messages)})
            safe_json_dump(audit_path, {'stage': stage, 'attempts': history})
        return cached
    last_raw, last_error, last_data, last_data_error = '', None, None, None
    for number in range(1, attempts + 1):
        current = list(messages)
        plan = repair_plan(last_data, last_data_error) if number > 1 and repair_plan else None
        if number > 1:
            safe_error = type(last_error).__name__ if history[-1]['status'] == 'call_failed' else last_error
            hint = retry_prompt(safe_error) if retry_prompt else (
                f'上次输出未通过结构、字段或证据校验：{safe_error}。请修正后输出完整JSON对象，保留其他有效内容。')
            previous_content = json.dumps(last_data, ensure_ascii=False) if plan else last_raw or '{}'
            current += [{'role': 'assistant', 'content': previous_content},
                        {'role': 'user', 'content': hint + ('\n' + plan['prompt'] if plan else '')}]
        record = {'attempt': len(history) + 1, 'call_attempt': number,
                  'invocation_id': invocation, 'raw_response': None, 'status': 'received',
                  'notebook_skills': audit_messages(current)}
        history.append(record)
        if plan:
            record['repair_paths'] = plan['paths']

        def persist():
            if audit_path:
                safe_json_dump(audit_path, {'stage': stage, 'attempts': history})

        try:
            record['request_attempted'] = True
            record['request_sent'] = None  # 排队/本地失败不能伪称已发送。
            persist()
            response = call(current)
            record['request_sent'] = True
        except Exception as exc:
            record.update(status='call_failed', error_kind=type(exc).__name__)
            from .execution_control import budget_diagnostics
            budget = budget_diagnostics(exc)
            if budget:
                record['budget'] = budget
                record['request_sent'] = budget.get('scope') == 'request'
            elif isinstance(getattr(exc, 'status_code', None), int):
                record['request_sent'] = True
            persist()
            from .execution_control import BudgetExceeded, TransportExhausted, retryable_transport
            if (not retry_call_errors or isinstance(exc, (BudgetExceeded, TransportExhausted))
                    or getattr(exc, 'status_code', None) in (400, 401, 403, 404, 422)):
                raise
            last_error = exc
            last_raw = ''
            if not retryable_transport(exc):
                break
            continue
        try:
            raw = _response_content(response, record, allow_reasoning_json=allow_reasoning_json)
        except ModelOutputError as exc:
            raw = None
            last_error = exc
        # 先保存返回，即使后续解析器或业务校验出现未预期异常，也可复现。
        persist()
        if split_on_truncation and record.get('finish_reason') == 'length':
            record.update(status='rejected', error_kind='truncated')
            persist()
            raise OutputTruncatedError('逐项反馈输出截断，需缩小本批范围')
        if raw is not None:
            last_raw = raw
            if thinking_path and record.get('reasoning_content'):
                _write_text(thinking_path, record['reasoning_content'])
            try:
                result = parser(raw)
                if not isinstance(result, dict):
                    raise ModelOutputError('模型JSON顶层必须为对象')
                json.dumps(result, allow_nan=False)
                if plan:
                    result = plan['merge'](result)
                last_data = copy.deepcopy(result)
                last_data_error = None
                try:
                    result = validate(result)
                    json.dumps(result, allow_nan=False)
                except (ValueError, TypeError) as exc:
                    last_data_error = exc
                    raise
            except (ValueError, TypeError) as exc:
                last_error = exc
            except Exception as exc:
                record.update(status='validation_failed', error_kind=type(exc).__name__)
                persist()
                raise
            else:
                record['status'] = 'accepted'
                persist()
                save_checkpoint(cache_key, result)
                return result
        # 响应包本身不合规时，也保留其可读取正文供下一次纠正。
        elif isinstance(record.get('raw_response'), str):
            last_raw = record['raw_response']
        record.update(status='rejected', error_kind='json' if isinstance(last_error, json.JSONDecodeError)
                      else 'evidence', error=str(last_error),
                      validation_kind='schema' if isinstance(last_error, ModelOutputError) else 'content')
        persist()
    if on_exhausted is not None and last_data is not None:
        # 响应包/解析/补丁错误不能抹掉上一份有效候选及其单元校验结果。
        candidate = on_exhausted(copy.deepcopy(last_data), last_data_error)
        if candidate is not None:
            result = validate(candidate)
            result['content_validation'] = candidate['content_validation']
            record['status'] = 'needs_review'
            record['unresolved_issues'] = candidate['content_validation'].get('issues', [])
            persist()
            return result
    if error_path:
        _write_text(error_path, last_raw)
    detail = type(last_error).__name__ if history[-1]['status'] == 'call_failed' else str(last_error)
    raise ModelOutputError(f'{stage}在{attempts}次尝试后仍未通过输出校验：{detail}'
                           + (f'；原始返回已保存到 {audit_path}' if audit_path else '')) from last_error


def _write_text(path, text):
    path = windows_io_path(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
