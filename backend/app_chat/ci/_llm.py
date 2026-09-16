# app_chat/ci/_llm.py
# Phase 1.3 产物：从 continuous_image_service.py 抽取的 LLM 调用封装函数
# 来源映射：continuous_image_service.py L2808-2813, L2815-3078, L3392-3457
# 规则：函数体与原始定义完全一致，不做任何行为修改

import json
import os
import re
from typing import Any, List, Optional

from openai import OpenAI


# ─── API 配置常量 ─────────────────────────────────────────────────────────────
# from continuous_image_service.py L2809-2812

_DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
_DASHSCOPE_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
_DMXAPI_API_KEY = os.environ.get("DMX_API_KEY", "")
_DMXAPI_BASE_URL = 'https://www.dmxapi.cn/v1/'

# DashScope 等对单条 data-uri 有体积上限；原图直接 base64 易超限。超过此阈值走 llm_langchain.util.encode_image 压到目标以内。
_CI_LLM_DEFAULTS = {
    'ci_llm_qwen35_plus': 'qwen3.5-plus',
    'ci_llm_qwen35_flash': 'qwen3.5-flash',
    'ci_llm_claude_sonnet': 'claude-4-sonnet',
    'ci_t_layer_gemini': 'gemini-3-pro-preview',
}


def _ci_llm_model(key: str) -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value(key, _CI_LLM_DEFAULTS.get(key, ''))

_CI_IMAGE_INLINE_MAX_MB = 3.0
_CI_IMAGE_INLINE_TARGET_MB = 3.0


# ─── 图片 base64 编码 ─────────────────────────────────────────────────────────
# from continuous_image_service.py L2815-2830

def _image_path_to_base64_url(img_path: str) -> Optional[str]:
    """将本地图片文件转为 data:image/{mime};base64,... 格式（用于 image_url 消息内容）。

    超过约 3MB 时复用 llm_langchain.util.encode_image 压缩到 3MB 以内（多为 JPEG），避免 DashScope data-uri 超限。
    """
    if not img_path or not os.path.exists(img_path):
        return None
    try:
        from llm_langchain.util import encode_image  # noqa: PLC0415

        ext = os.path.splitext(img_path)[1].lower().lstrip('.')
        mime = {
            'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png',
            'webp': 'webp', 'bmp': 'bmp',
        }.get(ext, 'jpeg')

        file_size_mb = os.path.getsize(img_path) / (1024 * 1024)
        b64 = encode_image(
            img_path,
            max_size_mb=_CI_IMAGE_INLINE_MAX_MB,
            target_size_mb=_CI_IMAGE_INLINE_TARGET_MB,
        )
        if file_size_mb > _CI_IMAGE_INLINE_MAX_MB:
            mime = 'jpeg'
        return f'data:image/{mime};base64,{b64}'
    except Exception as e:
        print(f'[ci] _image_path_to_base64_url failed ({img_path}): {e}')
        return None


# ─── LLM 响应文本归一化 ───────────────────────────────────────────────────────
# from continuous_image_service.py L2833-2867

def _normalize_llm_response_text(raw: Any) -> str:
    """将不同 LLM 网关返回的 content 统一归一为纯文本。"""
    if raw is None:
        return ''
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: List[str] = []
        for item in raw:
            if isinstance(item, str):
                if item.strip():
                    parts.append(item)
                continue
            if isinstance(item, dict):
                for key in ('text', 'content'):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value)
                        break
                continue
            maybe_text = getattr(item, 'text', None)
            if isinstance(maybe_text, str) and maybe_text.strip():
                parts.append(maybe_text)
        return '\n'.join(parts)
    if isinstance(raw, dict):
        for key in ('text', 'content', 'output_text'):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list):
                return _normalize_llm_response_text(value)
    maybe_text = getattr(raw, 'text', None)
    if isinstance(maybe_text, str):
        return maybe_text
    return str(raw)


# ─── JSON 提取与修复 ──────────────────────────────────────────────────────────
# from continuous_image_service.py L2870-2993

def _extract_balanced_json_object(raw_text: str) -> Optional[str]:
    """提取文本中首个平衡的 JSON 对象，忽略字符串字面量内部的大括号。"""
    start = raw_text.find('{')
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(raw_text)):
            char = raw_text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return raw_text[start:index + 1]
        start = raw_text.find('{', start + 1)
    return None


def _parse_llm_json(raw: Any, fallback: dict) -> dict:
    """从LLM响应中提取JSON，失败时返回 fallback。"""
    raw_text = _normalize_llm_response_text(raw).strip()
    if not raw_text:
        return fallback
    # 1. 尝试从 ```json ... ``` 中提取
    m = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', raw_text, re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 1.1 尝试从普通代码块中提取
    m = re.search(r'```\s*(\{[\s\S]*?\})\s*```', raw_text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 2. 尝试直接解析整个响应（有时模型直接输出 JSON）
    if raw_text.startswith('{'):
        try:
            return json.loads(raw_text)
        except Exception:
            pass
    # 3. 尝试提取首个平衡 JSON 对象
    balanced_json = _extract_balanced_json_object(raw_text)
    if balanced_json:
        try:
            return json.loads(balanced_json)
        except Exception:
            pass
    return fallback


def _repair_json_locally(raw_text: str) -> Optional[str]:
    """本地修复常见的 LLM JSON 脏格式，不额外调用模型。"""
    normalized = _normalize_llm_response_text(raw_text).strip()
    if not normalized:
        return None

    fenced_match = re.search(r'```json\s*([\s\S]*?)\s*```', normalized, re.IGNORECASE)
    if fenced_match:
        normalized = fenced_match.group(1).strip()
    else:
        fenced_match = re.search(r'```\s*([\s\S]*?)\s*```', normalized)
        if fenced_match:
            normalized = fenced_match.group(1).strip()

    candidate = _extract_balanced_json_object(normalized) or normalized
    if not candidate:
        return None

    candidate = re.sub(r',\s*([}\]])', r'\1', candidate)

    repaired_chars: List[str] = []
    in_string = False
    escaped = False
    for index, char in enumerate(candidate):
        if not in_string:
            repaired_chars.append(char)
            if char == '"':
                in_string = True
                escaped = False
            continue

        if escaped:
            repaired_chars.append(char)
            escaped = False
            continue

        if char == '\\':
            repaired_chars.append(char)
            escaped = True
            continue

        if char == '"':
            next_char = ''
            for lookahead in range(index + 1, len(candidate)):
                probe = candidate[lookahead]
                if probe.strip():
                    next_char = probe
                    break
            if next_char in (',', '}', ']', ':') or not next_char:
                repaired_chars.append(char)
                in_string = False
            else:
                repaired_chars.append('\\"')
            continue

        repaired_chars.append(char)

    repaired = ''.join(repaired_chars)
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
    return repaired


# ─── M 层 LLM 调用 ────────────────────────────────────────────────────────────
# from continuous_image_service.py L2996-3078

def _call_qwen35_plus_m_layer_llm(system_prompt: str, user_content: list, timeout: int, attempts: int) -> Optional[str]:
    for attempt in range(max(attempts, 0)):
        try:
            client = OpenAI(api_key=_DASHSCOPE_API_KEY, base_url=_DASHSCOPE_BASE_URL)
            resp = client.chat.completions.create(
                model=_ci_llm_model('ci_llm_qwen35_plus'),
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_content},
                ],
                max_tokens=4096,
                temperature=0.3,
                timeout=timeout,
                extra_body={'enable_thinking': False},
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f'[ci_m_layer] qwen3.5-plus 第{attempt + 1}次失败: {e}')
    return None


def _call_qwen35_m_layer_llm(system_prompt: str, user_content: list, timeout: int, attempts: int) -> Optional[str]:
    for attempt in range(max(attempts, 0)):
        try:
            client = OpenAI(api_key=_DASHSCOPE_API_KEY, base_url=_DASHSCOPE_BASE_URL)
            resp = client.chat.completions.create(
                model=_ci_llm_model('ci_llm_qwen35_flash'),
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_content},
                ],
                max_tokens=4096,
                temperature=0.3,
                timeout=timeout,
                extra_body={'enable_thinking': False},
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f'[ci_m_layer] qwen3.5-flash 第{attempt + 1}次失败: {e}')
    return None


def _call_claude4_sonnet_text_llm(system_prompt: str, user_content: list, timeout: int, attempts: int) -> Optional[str]:
    for attempt in range(max(attempts, 0)):
        try:
            from app_chat.config.config_manager import config_manager

            model_config = config_manager.get_model_config(_ci_llm_model('ci_llm_claude_sonnet'))
            cur_config = model_config.get_config()
            headers = cur_config.get('default_headers') or {'x-foo': 'true'}
            client = OpenAI(
                api_key=cur_config.get('openai_api_key'),
                base_url=cur_config.get('openai_api_base'),
                default_headers=headers,
            )
            resp = client.chat.completions.create(
                model=model_config.get_full_name(),
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_content},
                ],
                max_tokens=4096,
                temperature=0.2,
                timeout=timeout,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f'[ci_layout_iter] claude-4-sonnet 第{attempt + 1}次失败: {e}')
    return None


def _call_claude4_sonnet_vision_llm(system_prompt: str, user_content: list, timeout: int, attempts: int) -> Optional[str]:
    for attempt in range(max(attempts, 0)):
        try:
            from app_chat.config.config_manager import config_manager

            model_config = config_manager.get_model_config(_ci_llm_model('ci_llm_claude_sonnet'))
            cur_config = model_config.get_config()
            headers = cur_config.get('default_headers') or {'x-foo': 'true'}
            client = OpenAI(
                api_key=cur_config.get('openai_api_key'),
                base_url=cur_config.get('openai_api_base'),
                default_headers=headers,
            )
            resp = client.chat.completions.create(
                model=model_config.get_full_name(),
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_content},
                ],
                max_tokens=2048,
                temperature=0,
                timeout=timeout,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f'[ci_auto_iter] claude-4-sonnet 视觉第{attempt + 1}次失败: {e}')
    return None


def _call_qwen_vl_flash_fast(system_prompt: str, user_content: list, timeout: int) -> Optional[str]:
    try:
        client = OpenAI(api_key=_DASHSCOPE_API_KEY, base_url=_DASHSCOPE_BASE_URL)
        resp = client.chat.completions.create(
            model='qwen3-vl-flash',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content},
            ],
            max_tokens=4096,
            temperature=0.3,
            timeout=timeout,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f'[ci_m_layer] qwen3-vl-flash 快速调用失败: {e}')
    return None


def _call_m_layer_llm(system_prompt: str, user_content: list, timeout: int = 60,
                      primary_attempts: int = 2, fallback_attempts: int = 2,
                      prefer_qwen35_plus: bool = False, qwen35_plus_attempts: int = 2) -> Optional[str]:
    """
    M层LLM调用：
    - 默认：qwen3.5-flash -> qwen3-vl-flash
    - 条件命中时：qwen3.5-plus -> qwen3.5-flash -> qwen3-vl-flash
    """
    if prefer_qwen35_plus:
        resp = _call_qwen35_plus_m_layer_llm(system_prompt, user_content, timeout, qwen35_plus_attempts)
        if resp:
            return resp

    resp = _call_qwen35_m_layer_llm(system_prompt, user_content, timeout, primary_attempts)
    if resp:
        return resp

    for _ in range(max(fallback_attempts, 0)):
        resp = _call_qwen_vl_flash_fast(system_prompt, user_content, timeout)
        if resp:
            return resp
    return None


# ─── T 层 LLM 调用 ────────────────────────────────────────────────────────────
# from continuous_image_service.py L3392-3457

def _call_t_layer_llm(system_prompt: str, user_content: list, timeout: int = 120) -> Optional[str]:
    """
    T层LLM调用，三级降级：claude-4-sonnet → gemini-3-pro-preview → qwen3.5-plus
    """
    # --- 级别1：claude-4-sonnet（每级最多重试2次）---
    for attempt in range(2):
        try:
            from app_chat.config.config_manager import config_manager
            model_config = config_manager.get_model_config(_ci_llm_model('ci_llm_claude_sonnet'))
            cur_config = model_config.get_config()
            client = OpenAI(
                api_key=cur_config.get('openai_api_key'),
                base_url=cur_config.get('openai_api_base'),
                default_headers={'x-foo': 'true'},
            )
            resp = client.chat.completions.create(
                model=model_config.get_full_name(),
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_content},
                ],
                max_tokens=8192,
                temperature=0.5,
                timeout=timeout,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f'[ci_t_layer] claude-4-sonnet 第{attempt + 1}次失败: {e}')

    # --- 级别2：gemini-3-pro-preview（每级最多重试2次）---
    for attempt in range(2):
        try:
            client = OpenAI(api_key=_DMXAPI_API_KEY, base_url=_DMXAPI_BASE_URL)
            resp = client.chat.completions.create(
                model=_ci_llm_model('ci_t_layer_gemini'),
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_content},
                ],
                max_tokens=8192,
                temperature=0.5,
                timeout=timeout,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f'[ci_t_layer] gemini-3-pro-preview 第{attempt + 1}次失败: {e}')

    # --- 级别3：qwen3.5-plus（每级最多重试2次）---
    for attempt in range(2):
        try:
            client = OpenAI(api_key=_DASHSCOPE_API_KEY, base_url=_DASHSCOPE_BASE_URL)
            resp = client.chat.completions.create(
                model=_ci_llm_model('ci_llm_qwen35_plus'),
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_content},
                ],
                max_tokens=8192,
                temperature=0.5,
                timeout=timeout,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f'[ci_t_layer] qwen3.5-plus 第{attempt + 1}次失败: {e}')

    return None
