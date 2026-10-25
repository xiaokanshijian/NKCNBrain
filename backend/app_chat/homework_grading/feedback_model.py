"""冻结模型身份和采样参数；连接凭据仍由既有客户端提供，不进入快照。"""
import copy
from types import SimpleNamespace


def model_spec(runtime, role):
    spec = runtime.dependencies['model_config'].get('roles', {}).get(role)
    if not isinstance(spec, dict) or not isinstance(spec.get('model'), str) or not spec['model']:
        raise ValueError('冻结模型配置缺少角色：' + role)
    allowed = {'model', 'temperature', 'max_tokens', 'max_completion_tokens', 'extra_body', 'reasoning_effort'}
    if set(spec) - allowed:
        raise ValueError('冻结模型配置含未支持参数：' + role)
    if role == 'qwen' and not isinstance(spec.get('extra_body', {}).get('enable_thinking'), bool):
        raise ValueError('Qwen 必须显式冻结 enable_thinking')
    return copy.deepcopy(spec)


def runtime_client(client, runtime, role):
    from .execution_control import controlled_client
    client = controlled_client(client, role, runtime)
    if runtime is None:
        return client
    spec = model_spec(runtime, role)

    def create(**kwargs):
        from .feedback_prompts import context_block, reference_block
        kwargs = copy.deepcopy(kwargs)
        effective_spec = copy.deepcopy(spec)
        policy = runtime.dependencies['model_config'].get('qwen_call_policy') if role == 'qwen' else None
        if policy is not None:
            body = kwargs.get('extra_body')
            if policy.get('version') != 1 or body not in policy.get('allowed_extra_bodies', []):
                raise ValueError('Qwen调用参数不在本轮冻结策略中')
            if kwargs.get('temperature') not in policy.get('allowed_temperatures', []):
                raise ValueError('Qwen采样参数不在本轮冻结策略中')
            effective_spec.pop('extra_body', None)
        kwargs.update(effective_spec)
        messages = kwargs.setdefault('messages', [])
        if not any(context_block(runtime) in str(m.get('content', '')) for m in messages):
            messages.insert(0, {'role': 'system', 'content': context_block(runtime) + reference_block(runtime)})
        if role == 'qwen' and kwargs['extra_body']['enable_thinking']:
            kwargs.pop('response_format', None)
        return client.chat.completions.create(**kwargs)

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
