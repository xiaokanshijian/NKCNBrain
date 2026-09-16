"""Model clients and shared LLM response parsing helpers."""

import json
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI


# 与 llm_langchain/parse_input.py、chat_qwq_model.py 及 ci/_llm.py 保持一致
_HOMEWORK_QWEN_API_KEY_DEFAULT = os.environ.get("DASHSCOPE_API_KEY", "")
_HOMEWORK_QWEN_BASE_URL_DEFAULT = 'https://dashscope.aliyuncs.com/compatible-mode/v1'


def _resolve_qwen_api_key() -> str:
    """作业 Pass1 Qwen key：从环境变量读取，不再使用仓库内硬编码密钥。"""
    api_key = (
        os.environ.get('DASHSCOPE_API_KEY')
        or os.environ.get('DEEPSEEK_API_KEY_ALI')
        or os.environ.get('NKCN_SNIPPET_QWEN_API_KEY')
    )
    if api_key:
        return api_key
    try:
        from llm_langchain.chat_qwq_model import DEEPSEEK_API_KEY_ALI as _ali_key
        if _ali_key:
            return _ali_key
    except Exception:
        pass
    try:
        from llm_langchain.parse_input import DASHSCOPE_API_KEY as _dash_key
        if _dash_key:
            return _dash_key
    except Exception:
        pass
    return _HOMEWORK_QWEN_API_KEY_DEFAULT


def _qwen_client() -> OpenAI:
    return OpenAI(api_key=_resolve_qwen_api_key(), base_url=_HOMEWORK_QWEN_BASE_URL_DEFAULT)


def _deepseek_client() -> OpenAI:
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        raise EnvironmentError('缺少 DEEPSEEK_API_KEY，无法执行作业综合诊断')
    return OpenAI(api_key=api_key, base_url='https://api.deepseek.com')


def homework_qwen_model() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('homework_qwen', 'qwen3.6-plus')


def homework_deepseek_model() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('homework_deepseek', 'deepseek-v4-flash')


def homework_review_gemini_model() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('homework_review_gemini', 'gemini-3.1-pro-preview')


def _is_moonshot_fixed_sampling_model(name: str) -> bool:
    n = (name or '').strip().lower()
    if not n:
        return False
    if n == 'kimi-k3' or n.startswith('kimi-k3'):
        return True
    if n == 'kimi-k2.7-code' or n.startswith('kimi-k2'):
        return True
    return False


_HOMEWORK_GEMINI_BASE_URL_DEFAULT = 'https://www.dmxapi.cn/v1'
_HOMEWORK_GEMINI_API_KEY_DEFAULT = os.environ.get("DMX_API_KEY", "")
_HOMEWORK_MOONSHOT_BASE_URL_DEFAULT = 'https://api.moonshot.cn/v1'


def _homework_gemini_client() -> OpenAI:
    api_key = (
        os.environ.get('NKCN_HOMEWORK_GEMINI_API_KEY')
        or os.environ.get('NKCN_DMT_GEMINI_API_KEY')
        or os.environ.get('GEMINI_API_KEY')
        or _HOMEWORK_GEMINI_API_KEY_DEFAULT
    )
    base_url = (
        os.environ.get('NKCN_HOMEWORK_GEMINI_BASE_URL')
        or os.environ.get('NKCN_DMT_GEMINI_BASE_URL')
        or _HOMEWORK_GEMINI_BASE_URL_DEFAULT
    ).rstrip('/') + '/'
    try:
        timeout = int(os.environ.get('NKCN_HOMEWORK_GEMINI_TIMEOUT') or 240)
    except (TypeError, ValueError):
        timeout = 240
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)


def _homework_review_client_and_model(model=None):
    """自检模型：Gemini 走 dmxapi；kimi-k3 走 Moonshot 配置。"""
    model = model or homework_review_gemini_model()
    if _is_moonshot_fixed_sampling_model(model):
        from app_chat.scene_models import resolve_openai_cfg_from_abbr

        # 兼容仓库既有 ``Kimi`` 配置：它负责按统一规则加载 .env，
        # 这里只复用 Moonshot 连接信息，实际请求模型仍由场景值决定。
        legacy_cfg = resolve_openai_cfg_from_abbr(
            'Kimi',
            default_model=model,
            default_base=_HOMEWORK_MOONSHOT_BASE_URL_DEFAULT,
        )
        moonshot_api_key = (
            os.environ.get('MOONSHOT_API_KEY')
            or os.environ.get('KIMI_API_KEY')
            or legacy_cfg.get('api_key')
            or ''
        )
        cfg = resolve_openai_cfg_from_abbr(
            model,
            default_model=model,
            default_base=(
                legacy_cfg.get('base_url')
                or _HOMEWORK_MOONSHOT_BASE_URL_DEFAULT
            ),
            default_key=moonshot_api_key,
        )
        if not cfg.get('api_key'):
            raise EnvironmentError(
                '缺少 MOONSHOT_API_KEY 或 KIMI_API_KEY，无法执行 Kimi 作业自检'
            )
        headers = {}
        try:
            from app_chat.config.config_manager import config_manager
            mc = config_manager.get_model_config(model)
            if mc:
                cur = mc.get_config() or {}
                if cur.get('default_headers'):
                    headers = cur.get('default_headers')
        except Exception:
            pass
        try:
            timeout = int(os.environ.get('NKCN_HOMEWORK_GEMINI_TIMEOUT') or 240)
        except (TypeError, ValueError):
            timeout = 240
        client = OpenAI(
            api_key=cfg.get('api_key'),
            base_url=(cfg.get('base_url') or '').rstrip('/') + '/',
            default_headers=headers,
            timeout=timeout,
        )
        return client, str(cfg.get('model') or model), True
    return _homework_gemini_client(), model, False


def _call_homework_gemini_json(
    messages: List[Dict[str, Any]],
    temperature: Optional[float] = 0.1,
    max_tokens: int = 8000,
*, feedback_runtime=None) -> Any:
    from .feedback_model import runtime_client, model_spec
    if feedback_runtime is None:
        client, model_name, fixed_sampling = _homework_review_client_and_model()
    else:
        client, model_name, fixed_sampling = _homework_review_client_and_model(model_spec(feedback_runtime, "review")["model"])
    client = runtime_client(client, feedback_runtime, "review")
    create_kwargs: Dict[str, Any] = {
        'model': model_name,
        'messages': messages,
        'max_tokens': max_tokens,
        'response_format': {'type': 'json_object'},
    }
    if fixed_sampling:
        # kimi-k3：仅 temperature=1，省略 top_p / penalty / n，避免 400
        create_kwargs['temperature'] = 1.0
        print(
            f'[homework_review] {model_name} 固定采样：temperature=1.0（已省略 top_p/penalty）',
            flush=True,
        )
    elif temperature is not None:
        create_kwargs['temperature'] = temperature
    try:
        return client.chat.completions.create(**create_kwargs)
    except Exception:
        create_kwargs.pop('response_format', None)
        return client.chat.completions.create(**create_kwargs)


HOMEWORK_RED_BLUE_MODEL = 'kimi-k3'
HOMEWORK_RED_BLUE_REASONING_EFFORT = 'high'


def _homework_red_blue_client() -> OpenAI:
    """红蓝卡标专用 Kimi 客户端，不复用可切换的作业自检模型。"""
    from app_chat.scene_models import resolve_openai_cfg_from_abbr

    legacy_cfg = resolve_openai_cfg_from_abbr(
        'Kimi',
        default_model=HOMEWORK_RED_BLUE_MODEL,
        default_base=_HOMEWORK_MOONSHOT_BASE_URL_DEFAULT,
    ) or {}
    api_key = (
        os.environ.get('MOONSHOT_API_KEY')
        or os.environ.get('KIMI_API_KEY')
        or ''
    )
    if not api_key:
        raise EnvironmentError(
            '缺少 MOONSHOT_API_KEY 或 KIMI_API_KEY，无法生成批改质量红蓝卡标'
        )
    base_url = (
        os.environ.get('NKCN_HOMEWORK_RED_BLUE_BASE_URL')
        or legacy_cfg.get('base_url')
        or _HOMEWORK_MOONSHOT_BASE_URL_DEFAULT
    )
    try:
        timeout = int(os.environ.get('NKCN_HOMEWORK_RED_BLUE_TIMEOUT') or 300)
    except (TypeError, ValueError):
        timeout = 300
    return OpenAI(
        api_key=api_key,
        base_url=str(base_url).rstrip('/') + '/',
        timeout=max(30, min(timeout, 900)),
        max_retries=1,
    )


def _is_response_format_error(exc: Exception) -> bool:
    text = str(exc or '').lower()
    return any(token in text for token in (
        'response_format',
        'json_object',
        'json mode',
    ))


def _call_homework_red_blue_json(
    messages: List[Dict[str, Any]],
    max_completion_tokens: int = 12000,
*, feedback_runtime=None) -> Any:
    """固定使用 kimi-k3/high；JSON Mode 不兼容时仅移除该参数重试。"""
    from .feedback_model import runtime_client, model_spec
    if feedback_runtime is not None and model_spec(feedback_runtime, "quality")["model"] != HOMEWORK_RED_BLUE_MODEL:
        raise ValueError("质量检查须保持既有固定模型")
    client = runtime_client(_homework_red_blue_client(), feedback_runtime, "quality")
    create_kwargs: Dict[str, Any] = {
        'model': HOMEWORK_RED_BLUE_MODEL,
        'messages': messages,
        'reasoning_effort': HOMEWORK_RED_BLUE_REASONING_EFFORT,
        'temperature': 1.0,
        'max_completion_tokens': max(1000, min(int(max_completion_tokens), 32000)),
        'response_format': {'type': 'json_object'},
    }
    try:
        return client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        if not _is_response_format_error(exc):
            raise
        create_kwargs.pop('response_format', None)
        return client.chat.completions.create(**create_kwargs)


def _strip_json_text(raw: str) -> str:
    clean = (raw or '').strip()
    if not clean.startswith('```'):
        return clean
    lines = clean.splitlines()
    if lines and lines[0].strip().startswith('```'):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith('```'):
        lines = lines[:-1]
    return '\n'.join(lines).strip()


def _extract_first_json_object(raw: str) -> Optional[str]:
    text = _strip_json_text(raw)
    start = text.find('{')
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def _loads_json_with_retry_text(raw: str) -> Dict[str, Any]:
    text = (raw or '').strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as original_error:
        clean = _strip_json_text(raw)
        if clean != text:
            try:
                return json.loads(clean)
            except json.JSONDecodeError:
                pass

        json_object = _extract_first_json_object(raw)
        if json_object:
            return json.loads(json_object)
        raise original_error


def _write_text(path: str, content: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        file.write(content)


def _qwen_thinking_enabled(extra_body: Dict[str, Any]) -> bool:
    """DashScope Qwen thinking mode is mutually exclusive with JSON Mode."""
    return bool((extra_body or {}).get('enable_thinking'))


def _call_qwen_json(
    messages: List[Dict[str, Any]],
    extra_body: Dict[str, Any],
    temperature: Optional[float] = 0.1,
*, feedback_runtime=None) -> Any:
    from .feedback_model import runtime_client, model_spec
    client = runtime_client(_qwen_client(), feedback_runtime, "qwen")
    if feedback_runtime is not None and not feedback_runtime.dependencies['model_config'].get('qwen_call_policy'):
        extra_body = model_spec(feedback_runtime, "qwen")["extra_body"]
    use_response_format = not _qwen_thinking_enabled(extra_body)
    create_kwargs: Dict[str, Any] = {
        'model': homework_qwen_model(),
        'messages': messages,
        'extra_body': extra_body,
    }
    if temperature is not None:
        create_kwargs['temperature'] = temperature
    if use_response_format:
        create_kwargs['response_format'] = {'type': 'json_object'}

    try:
        return client.chat.completions.create(**create_kwargs)
    except Exception:
        if not use_response_format:
            raise
        create_kwargs.pop('response_format', None)
        return client.chat.completions.create(**create_kwargs)
