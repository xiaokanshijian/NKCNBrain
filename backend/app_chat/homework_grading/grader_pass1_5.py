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
*, feedback_runtime=None, audit_path=None) -> Dict[str, Any]:
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
    from .note_evidence import is_notes
    user_text = (
        '核对候选笔记页是否同源同题；不能由候选页码推定作答连续。'
        '逐一返回requires_material_check=true单元的核对状态；本页独立题标not_required，'
        '依赖材料却无法对应时标unresolved，不能用空数组代替核对结果。'
        '材料来源可在本页或非相邻页；本页来源使用not_required并给出材料证据。'
        '每项材料证据须包含qid_global、material_label、逐字quote和relation；明确材料数量，不能伪造引文。\n'
        + json.dumps({'image_pdf_pages': group, 'visible_units': pending_questions or []}, ensure_ascii=False)
        if is_notes(feedback_runtime) or any(q.get('requires_material_check') for q in pending_questions or []) else
        cross_page_user_prompt(group, context_notes, pending_questions=pending_questions)
    )
    content.append({
        'type': 'text',
        'text': user_text,
    })
    extra_body = _cross_page_extra_body(subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    messages = [
        {'role': 'system', 'content': (system_prompt(feedback_runtime, 'cross_page') if feedback_runtime is not None else CROSS_PAGE_SYSTEM)},
        {'role': 'user', 'content': content},
    ]

    from .model_output import request_json_object, object_list

    def validate(result):
        object_list(result.get('corrections'), 'corrections')
        result['cross_page_group'] = result.get('cross_page_group') or group
        return stamp_feedback(result, feedback_runtime, 'cross_page')

    return request_json_object(
        lambda current: _call_qwen_json(current, extra_body,
            temperature=None if subject == 'math' else 0.1,
            **({'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {})),
        messages, parser=_loads_json_with_retry_text, validate=validate,
        audit_path=audit_path, stage='跨页核对')
