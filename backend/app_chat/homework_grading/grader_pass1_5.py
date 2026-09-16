from .feedback_runtime import frozen_environment
"""Pass1.5 cross-page grading repair model call."""

from .feedback_prompts import system_prompt
from .feedback_runtime import stamp_feedback

import json
import os
from typing import Any, Dict, List, Optional

from app_chat.homework_grading.llm_clients import (
    _call_qwen_json,
    _loads_json_with_retry_text,
)
from app_chat.homework_grading.prompts import CROSS_PAGE_SYSTEM, cross_page_user_prompt
from app_chat.homework_grading.utils import image_to_data_uri


def pass1_5_math_thinking_enabled(*, feedback_runtime=None) -> bool:
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_5_MATH_THINKING', '0').strip().lower()
    return raw in ('1', 'true', 'yes', 'y', 'on')


def _cross_page_extra_body(subject: str, *, feedback_runtime=None) -> Dict[str, Any]:
    if subject == 'math' and pass1_5_math_thinking_enabled(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})):
        return {'enable_thinking': True, 'thinking_budget': 4096}
    return {'enable_thinking': False}


def grade_cross_page_group(
    image_paths: List[str],
    subject: str,
    group: List[int],
    boundaries: Dict[int, Dict[str, Any]],
    pending_questions: Optional[List[Dict[str, Any]]] = None,
*, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    context_notes = []
    for page_num in group:
        boundary = boundaries.get(page_num) or {}
        notes = []
        if boundary.get('continues_from_prev') and boundary.get('description_prev'):
            notes.append(f"顶部延续自上页：{boundary['description_prev']}")
        if boundary.get('continues_to_next') and boundary.get('description_next'):
            notes.append(f"底部延续至下页：{boundary['description_next']}")
        context_notes.append('；'.join(notes) if notes else '（无额外跨页说明）')

    content: List[Dict[str, Any]] = [
        {'type': 'image_url', 'image_url': {'url': image_to_data_uri(image_path)}}
        for image_path in image_paths
    ]
    content.append({
        'type': 'text',
        'text': cross_page_user_prompt(group, context_notes, pending_questions=pending_questions),
    })
    extra_body = _cross_page_extra_body(subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    messages = [
        {'role': 'system', 'content': (system_prompt(feedback_runtime, 'cross_page') if feedback_runtime is not None else CROSS_PAGE_SYSTEM)},
        {'role': 'user', 'content': content},
    ]

    last_raw = ''
    for attempt in range(2):
        if attempt == 1:
            retry_content = list(content)
            retry_content[-1] = {
                'type': 'text',
                'text': cross_page_user_prompt(group, context_notes, pending_questions=pending_questions)
                + '\n\n上次返回不是合法 JSON，请严格输出 JSON 对象。',
            }
            messages = [
                {'role': 'system', 'content': (system_prompt(feedback_runtime, 'cross_page') if feedback_runtime is not None else CROSS_PAGE_SYSTEM)},
                {'role': 'user', 'content': retry_content},
            ]
        response = _call_qwen_json(
            messages,
            extra_body,
            temperature=None if subject == 'math' else 0.1,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        last_raw = response.choices[0].message.content or ''
        try:
            result = _loads_json_with_retry_text(last_raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(result.get('corrections'), list):
            result['corrections'] = []
        result['cross_page_group'] = result.get('cross_page_group') or group
        return stamp_feedback(result, feedback_runtime, "cross_page")
    raise ValueError(f'Pass 1.5 跨页修补返回无法解析为 JSON: {last_raw[:200]}')
