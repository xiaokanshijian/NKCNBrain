from .feedback_runtime import frozen_environment
"""Pass1 single-page homework grading with Qwen vision.

Default flow (two-stage):
  A. detect_page_layout  — question ids + answer-area bboxes + cross-page flags
  B. grade_page_questions — transcription + verdict on the fixed question list

Set env HOMEWORK_PASS1_TWO_STAGE=0 to restore legacy one-shot Pass1.
Set env HOMEWORK_PASS1_MAX_ATTEMPTS=3 to control LLM call retries per stage.
"""

import copy
from .feedback_runtime import runtime_attributes, stamp_feedback

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app_chat.homework_grading.fixed_english_choice_slots import (
    ROI_TRANSCRIPTION_SYSTEM,
    apply_fixed_english_choice_guard,
    attach_fixed_english_choice_slots,
    normalize_fixed_english_choice_transcription,
    prepare_fixed_english_choice_rois,
    record_fixed_english_choice_transcription,
)
from app_chat.homework_grading.fixed_english_page15_guard import (
    apply_fixed_english_page15_guard,
)
from app_chat.homework_grading.llm_clients import (
    _call_qwen_json,
    _loads_json_with_retry_text,
    _write_text,
)
from app_chat.homework_grading.prompts import (
    pass1_detect_supplement_user_prompt,
    pass1_detect_system,
    pass1_detect_user_prompt,
    pass1_grade_supplement_user_prompt,
    pass1_grade_system,
    pass1_grade_user_prompt,
    pass1_system,
    pass1_user_prompt,
)
from app_chat.homework_grading.question_type import (
    is_chinese_pronunciation_selection_question,
    normalize_application_major_problem,
    normalize_final_unit_requirement,
)
from app_chat.homework_grading.utils import (
    image_to_data_uri,
    normalize_position,
    safe_json_dump,
    safe_json_load,
    source_document_sha256_from_artifact_path,
)


logger = logging.getLogger(__name__)

_MAX_PRONUNCIATION_ANSWER_SLOTS = 32
_WRAPPED_PRONUNCIATION_RE = re.compile(
    r'([\u3400-\u9fff]+)\s*[（(]\s*([^()（）]+?)\s*[）)]\s*[√✓]?'
)
_PASS1_PAGE_ARTIFACT_RE = re.compile(
    r'^[^_]+_(?P<sample_id>.+)_page\d+(?:\.(?:detect|grade))?\.json$',
    re.IGNORECASE,
)


def _sample_id_from_page_artifact_path(path: str) -> str:
    match = _PASS1_PAGE_ARTIFACT_RE.match(os.path.basename(str(path or '')))
    return str(match.group('sample_id') or '').strip() if match else ''


def pass1_two_stage_enabled(*, feedback_runtime=None) -> bool:
    return _pass1_two_stage_enabled(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))


def _pass1_two_stage_enabled(*, feedback_runtime=None) -> bool:
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_TWO_STAGE', '1').strip().lower()
    return raw not in ('0', 'false', 'no', 'off')


def _default_boundary() -> Dict[str, Any]:
    return {
        'continues_from_prev': False,
        'description_prev': None,
        'continues_to_next': False,
        'description_next': None,
    }


def _normalize_boundary(boundary: Any) -> Dict[str, Any]:
    if not isinstance(boundary, dict):
        return _default_boundary()
    return {
        'continues_from_prev': bool(boundary.get('continues_from_prev')),
        'description_prev': boundary.get('description_prev') or None,
        'continues_to_next': bool(boundary.get('continues_to_next')),
        'description_next': boundary.get('description_next') or None,
    }


def _clamp_confidence(value: Any) -> Optional[int]:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, number))


def _box_contains(outer: List[float], inner: List[float], tolerance: float = 12.0) -> bool:
    if not outer or not inner:
        return False
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] >= outer[1] - tolerance
        and inner[2] <= outer[2] + tolerance
        and inner[3] <= outer[3] + tolerance
    )


def _normalize_pronunciation_answer_slots(value: Any, qid: str) -> List[Dict[str, Any]]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > _MAX_PRONUNCIATION_ANSWER_SLOTS
    ):
        return []
    slots: List[Dict[str, Any]] = []
    seen_targets = set()
    for raw_slot in value:
        if not isinstance(raw_slot, dict):
            return []
        target = str(raw_slot.get('target') or '').strip()
        slot_position = normalize_position(raw_slot.get('slot_position'))
        mark_position = normalize_position(raw_slot.get('mark_position'))
        if (
            not target
            or target in seen_targets
            or not slot_position
            or not mark_position
            or not _box_contains(slot_position, mark_position)
        ):
            return []
        raw_candidates = raw_slot.get('candidate_regions')
        if not isinstance(raw_candidates, list) or len(raw_candidates) != 2:
            return []
        candidates: List[Dict[str, Any]] = []
        for raw_candidate in raw_candidates:
            if not isinstance(raw_candidate, dict):
                return []
            label = str(raw_candidate.get('label') or '').strip()
            position = normalize_position(
                raw_candidate.get('position') or raw_candidate.get('region')
            )
            if (
                not label
                or not position
                or not _box_contains(slot_position, position)
            ):
                return []
            candidates.append({'label': label, 'position': position})
        confidence = _clamp_confidence(raw_slot.get('layout_confidence'))
        slot = {
            'slot_id': f'{qid}:{target}',
            'target': target,
            'slot_position': slot_position,
            'candidate_regions': candidates,
            'mark_position': mark_position,
        }
        if confidence is not None:
            slot['layout_confidence'] = confidence
        slots.append(slot)
        seen_targets.add(target)
    return slots


def _normalize_pronunciation_student_answer(
    student_answer: Any,
    detected_question: Dict[str, Any],
    subject: str,
) -> str:
    text = str(student_answer or '').strip()
    if not text or subject != 'chinese':
        return text
    slots = detected_question.get('answer_slots')
    if not isinstance(slots, list) or not slots:
        return text
    matches = _WRAPPED_PRONUNCIATION_RE.findall(text)
    if len(matches) != len(slots):
        return text
    selected: List[str] = []
    for (written_target, raw_label), slot in zip(matches, slots):
        target = str(slot.get('target') or '').strip()
        label = str(raw_label or '').strip().rstrip('√✓').strip()
        if written_target.strip() != target or not label:
            return text
        selected.append(label)
    return ', '.join(selected)


def _normalize_pronunciation_grade_answers(
    result: Dict[str, Any],
    detected: Dict[str, Any],
    subject: str,
) -> None:
    if subject != 'chinese':
        return
    detected_by_id = {
        str(question.get('id') or '').strip(): question
        for question in detected.get('questions') or []
        if isinstance(question, dict) and str(question.get('id') or '').strip()
    }
    for question in result.get('questions') or []:
        if not isinstance(question, dict):
            continue
        detected_question = detected_by_id.get(str(question.get('id') or '').strip())
        if not detected_question:
            continue
        question['student_answer'] = _normalize_pronunciation_student_answer(
            question.get('student_answer'),
            detected_question,
            subject,
        )


def _normalize_detect_result(result: Dict[str, Any], subject: str, page_num: int) -> Dict[str, Any]:
    result['page'] = result.get('page') or page_num
    result['subject'] = result.get('subject') or subject
    result['page_header'] = str(result.get('page_header') or '').strip()
    result['boundary'] = _normalize_boundary(result.get('boundary'))
    questions = result.get('questions') if isinstance(result.get('questions'), list) else []
    normalized_questions: List[Dict[str, Any]] = []
    dropped_layout_artifacts: List[Dict[str, Any]] = []
    for idx, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or f'auto-{idx}').strip() or f'auto-{idx}'
        item = {
            'id': qid,
            'parent_group_id': str(question.get('parent_group_id') or '').strip(),
            'parent_stem_excerpt': str(question.get('parent_stem_excerpt') or '').strip(),
            'stem_excerpt': str(question.get('stem_excerpt') or '').strip(),
            'position': normalize_position(question.get('position')),
            'cross_page': bool(question.get('cross_page')),
            'cross_page_note': question.get('cross_page_note') or None,
            'is_application_major_problem': normalize_application_major_problem(question, subject),
            'final_unit_requirement': question.get('final_unit_requirement'),
        }
        item['final_unit_requirement'] = normalize_final_unit_requirement(item, subject)
        layout_confidence = _clamp_confidence(question.get('layout_confidence'))
        if layout_confidence is not None:
            item['layout_confidence'] = layout_confidence
        if question.get('cross_page_context_ready'):
            item['cross_page_context_ready'] = True
        if is_chinese_pronunciation_selection_question(question, subject):
            answer_slots = _normalize_pronunciation_answer_slots(
                question.get('answer_slots'),
                qid,
            )
            if answer_slots:
                item['answer_slots'] = answer_slots
        if _is_empty_auto_layout_artifact(item):
            dropped_layout_artifacts.append({
                'id': qid,
                'reason': 'empty_auto_question',
            })
            continue
        normalized_questions.append(item)
    result['questions'] = normalized_questions
    if dropped_layout_artifacts:
        result['layout_artifacts'] = dropped_layout_artifacts
    return result


def _is_empty_auto_layout_artifact(question: Any) -> bool:
    """Identify a model-emitted auto item that contains no grading evidence."""
    if not isinstance(question, dict):
        return False
    qid = str(question.get('id') or '').strip().lower()
    if not qid.startswith('auto-'):
        return False
    if any(
        str(question.get(field) or '').strip()
        for field in (
            'parent_group_id',
            'parent_stem_excerpt',
            'stem_excerpt',
            'student_answer',
            'understanding',
            'cross_page_note',
        )
    ):
        return False
    if normalize_position(question.get('position')):
        return False
    if question.get('cross_page') or question.get('answer_slots'):
        return False
    correct_answer = question.get('correct_answer')
    return correct_answer is None or not str(correct_answer).strip()


def _normalize_pass1_result(result: Dict[str, Any], subject: str, page_num: int) -> Dict[str, Any]:
    result['page'] = result.get('page') or page_num
    result['subject'] = result.get('subject') or subject
    result['page_header'] = str(result.get('page_header') or '').strip()
    result['boundary'] = _normalize_boundary(result.get('boundary'))
    normalized_questions: List[Dict[str, Any]] = []
    existing_layout_artifacts = result.get('layout_artifacts')
    dropped_layout_artifacts = (
        [
            dict(artifact)
            for artifact in existing_layout_artifacts
            if isinstance(artifact, dict)
        ]
        if isinstance(existing_layout_artifacts, list)
        else []
    )
    for question in result.get('questions') or []:
        question['position'] = normalize_position(question.get('position'))
        if _is_empty_auto_layout_artifact(question):
            dropped_layout_artifacts.append({
                'id': str(question.get('id') or '').strip(),
                'reason': 'empty_auto_question',
            })
            continue
        if 'cross_page' not in question:
            question['cross_page'] = False
        if 'cross_page_note' not in question:
            question['cross_page_note'] = None
        if 'recurrence_hint' not in question:
            question['recurrence_hint'] = 'na'
        question['is_application_major_problem'] = normalize_application_major_problem(question, subject)
        question['final_unit_requirement'] = normalize_final_unit_requirement(question, subject)
        normalized_questions.append(question)
    result['questions'] = normalized_questions
    if dropped_layout_artifacts:
        deduped_artifacts: List[Dict[str, Any]] = []
        seen_artifacts = set()
        for artifact in dropped_layout_artifacts:
            key = (
                str(artifact.get('id') or '').strip(),
                str(artifact.get('reason') or '').strip(),
            )
            if key in seen_artifacts:
                continue
            seen_artifacts.add(key)
            deduped_artifacts.append(artifact)
        result['layout_artifacts'] = deduped_artifacts
    return result


def _grade_extra_body(subject: str, thinking_budget: int = 4096) -> Dict[str, Any]:
    if subject == 'math':
        return {'enable_thinking': True, 'thinking_budget': thinking_budget}
    return {'enable_thinking': False}


def _pass1_max_attempts(*, feedback_runtime=None) -> int:
    try:
        return max(1, min(int(frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_MAX_ATTEMPTS') or 3), 5))
    except (TypeError, ValueError):
        return 3


def _pass1_retry_hint(last_error: Optional[Exception], require_questions: bool) -> str:
    message = str(last_error or '')
    if require_questions and 'questions' in message:
        return (
            '上次返回缺少 questions 数组。'
            '必须输出 JSON 对象，且顶层含 questions 数组；'
            '数组内每项须含 id、student_answer、verdict 等字段。'
            '不要输出 Markdown 围栏或其他说明文字。'
        )
    if isinstance(last_error, json.JSONDecodeError):
        return '上次返回不是合法 JSON。请只输出 JSON 对象，不要包含任何其他文字。'
    return '上次返回格式不符合要求。请严格按 schema 只输出 JSON 对象。'


def _fallback_grade_from_detect(
    detected: Dict[str, Any],
    page_num: int,
    subject: str,
    reason: str,
) -> Dict[str, Any]:
    """When grade LLM keeps failing, emit uncertain placeholders instead of aborting the whole job."""
    questions: List[Dict[str, Any]] = []
    for question in detected.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        if not qid:
            continue
        questions.append({
            'id': qid,
            'parent_group_id': str(question.get('parent_group_id') or '').strip(),
            'parent_stem_excerpt': str(question.get('parent_stem_excerpt') or '').strip(),
            'stem_excerpt': str(question.get('stem_excerpt') or '').strip(),
            'student_answer': '',
            'understanding': '',
            'correct_answer': None,
            'verdict': 'uncertain',
            'error_type': '',
            'knowledge_point': '',
            'recurrence_hint': 'na',
            'is_application_major_problem': bool(question.get('is_application_major_problem')),
            'final_unit_requirement': normalize_final_unit_requirement(question, subject),
            'uncertain_reason': 'model_retry_exhausted',
            'fallback_reason': reason,
        })
    return {
        'page': page_num,
        'subject': subject,
        'questions': questions,
        '_fallback': True,
        '_fallback_reason': reason,
    }


def _call_qwen_json_with_retry(
    messages: List[Dict[str, Any]],
    extra_body: Dict[str, Any],
    *,
    stage_label: str = 'Pass 1',
    require_questions: bool = True,
    error_dump_path: Optional[str] = None,
    temperature: Optional[float] = 0.1,
feedback_runtime=None) -> Tuple[Dict[str, Any], Any]:
    last_raw = ''
    last_error: Optional[Exception] = None
    max_attempts = _pass1_max_attempts(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))

    for attempt in range(max_attempts):
        call_messages = messages
        if attempt > 0:
            call_messages = messages + [
                {'role': 'assistant', 'content': last_raw or '{}'},
                {
                    'role': 'user',
                    'content': _pass1_retry_hint(last_error, require_questions),
                },
            ]
        try:
            response = _call_qwen_json(call_messages, extra_body, temperature=temperature, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        except Exception as exc:
            last_error = exc
            logger.warning('%s API 调用失败 attempt=%s/%s: %s', stage_label, attempt + 1, max_attempts, exc)
            continue

        message = response.choices[0].message
        last_raw = message.content or ''
        try:
            result = _loads_json_with_retry_text(last_raw)
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning('%s JSON 解析失败 attempt=%s/%s', stage_label, attempt + 1, max_attempts)
            continue

        if not isinstance(result, dict):
            last_error = ValueError(f'{stage_label} 返回不是 JSON 对象')
            logger.warning('%s 返回非对象 attempt=%s/%s', stage_label, attempt + 1, max_attempts)
            continue

        if require_questions and not isinstance(result.get('questions'), list):
            last_error = ValueError(f'{stage_label} 返回缺少 questions 数组')
            logger.warning('%s 缺少 questions attempt=%s/%s', stage_label, attempt + 1, max_attempts)
            continue

        return result, message

    if error_dump_path and last_raw:
        _write_text(error_dump_path, last_raw)
    detail = f'{last_error}; raw={last_raw[:200]!r}' if last_raw else str(last_error)
    raise ValueError(f'{stage_label} 在 {max_attempts} 次尝试后仍失败: {detail}')


def _cross_page_needs_uncertain(question: Dict[str, Any], *, material_type: str = '') -> bool:
    # 作文/笔记：跨页连续书写是常态，禁止按题目卷规则强制 uncertain（作业/试卷仍走原逻辑）
    from .feedback_material_kinds import is_open_material
    if is_open_material(material_type):
        return False
    if not question.get('cross_page'):
        return False
    if question.get('cross_page_context_ready'):
        return False
    qid = str(question.get('id') or '').strip()
    if qid.startswith('auto-'):
        return True
    parent = str(question.get('parent_group_id') or '').strip()
    parent_stem = str(question.get('parent_stem_excerpt') or '').strip()
    stem = str(question.get('stem_excerpt') or '').strip()
    parsed = re.match(r'^(\d+)-(\d+)$', qid)
    if parsed and parent and parent_stem and stem:
        return False
    return True


def _merge_detect_and_grade(
    detect: Dict[str, Any],
    grade: Dict[str, Any],
    subject: str,
    page_num: int,
    *,
    feedback_runtime=None,
) -> Dict[str, Any]:
    from .feedback_material_kinds import is_open_material
    material_type = ''
    if feedback_runtime is not None:
        material_type = str((feedback_runtime.context or {}).get('material_type') or '')
    open_material = is_open_material(material_type)
    detect = _normalize_detect_result(detect, subject, page_num)
    grade_items = grade.get('questions') if isinstance(grade.get('questions'), list) else []
    grade_by_id = {
        str(item.get('id')).strip(): item
        for item in grade_items
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }

    merged_questions: List[Dict[str, Any]] = []
    for question in detect.get('questions') or []:
        qid = question['id']
        graded = grade_by_id.get(qid, {})
        merged = dict(question)
        student_answer = _normalize_pronunciation_student_answer(
            graded.get('student_answer'),
            question,
            subject,
        )
        force_uncertain = _cross_page_needs_uncertain(question, material_type=material_type)
        merged.update({
            'student_answer': student_answer,
            'understanding': str(graded.get('understanding') or '').strip(),
            'correct_answer': graded.get('correct_answer'),
            'verdict': (
                'uncertain'
                if force_uncertain
                else (graded.get('verdict') or 'uncertain')
            ),
            'error_type': str(graded.get('error_type') or '').strip(),
            'knowledge_point': str(graded.get('knowledge_point') or '').strip(),
            'recurrence_hint': graded.get('recurrence_hint') or 'na',
        })
        if isinstance(graded.get('choice_slot_guard'), dict):
            merged['choice_slot_guard'] = dict(graded['choice_slot_guard'])
        if isinstance(graded.get('fixed_english_page15_guard'), dict):
            merged['fixed_english_page15_guard'] = copy.deepcopy(
                graded['fixed_english_page15_guard']
            )
        if str(graded.get('error_detail') or '').strip():
            merged['error_detail'] = str(graded['error_detail']).strip()
        merged['final_unit_requirement'] = normalize_final_unit_requirement(merged, subject)
        for field in ('recognition_confidence', 'understanding_confidence', 'grading_confidence'):
            confidence = _clamp_confidence(graded.get(field))
            if confidence is not None:
                merged[field] = confidence
        if force_uncertain and merged.get('verdict') not in ('uncertain', 'unanswered'):
            merged['verdict'] = 'uncertain'
            if not merged.get('cross_page_note'):
                merged['cross_page_note'] = '跨页题目，单页上下文不足'
        # 作文/笔记已给出形成性结论时，跨页仅表示书写延续，视为上下文已可评价
        if (
            open_material
            and merged.get('cross_page')
            and merged.get('verdict') not in ('uncertain', 'unanswered', '', None)
        ):
            merged['cross_page_resolved'] = True
        merged_questions.append(merged)

    for qid, graded in grade_by_id.items():
        if any(q['id'] == qid for q in merged_questions):
            continue
        merged_questions.append({
            'id': qid,
            'parent_group_id': str(graded.get('parent_group_id') or '').strip(),
            'parent_stem_excerpt': str(graded.get('parent_stem_excerpt') or '').strip(),
            'stem_excerpt': str(graded.get('stem_excerpt') or '').strip(),
            'position': normalize_position(graded.get('position')),
            'cross_page': bool(graded.get('cross_page')),
            'cross_page_note': graded.get('cross_page_note'),
            'student_answer': str(graded.get('student_answer') or '').strip(),
            'understanding': str(graded.get('understanding') or '').strip(),
            'correct_answer': graded.get('correct_answer'),
            'verdict': graded.get('verdict') or 'uncertain',
            'error_type': str(graded.get('error_type') or '').strip(),
            'knowledge_point': str(graded.get('knowledge_point') or '').strip(),
            'recurrence_hint': graded.get('recurrence_hint') or 'na',
        })
        merged_questions[-1]['final_unit_requirement'] = normalize_final_unit_requirement(
            merged_questions[-1], subject,
        )
        for field in ('recognition_confidence', 'understanding_confidence', 'grading_confidence'):
            confidence = _clamp_confidence(graded.get(field))
            if confidence is not None:
                merged_questions[-1][field] = confidence
        if isinstance(graded.get('fixed_english_page15_guard'), dict):
            merged_questions[-1]['fixed_english_page15_guard'] = copy.deepcopy(
                graded['fixed_english_page15_guard']
            )
        if str(graded.get('error_detail') or '').strip():
            merged_questions[-1]['error_detail'] = str(
                graded['error_detail']
            ).strip()

    result = {
        'page': detect.get('page') or page_num,
        'subject': detect.get('subject') or subject,
        'page_header': detect.get('page_header') or '',
        'boundary': detect.get('boundary') or _default_boundary(),
        'questions': merged_questions,
        'pass1_mode': 'two_stage',
    }
    return _normalize_pass1_result(result, subject, page_num)


def detect_page_layout(
    image_path: str,
    subject: str,
    page_num: int,
    out_detect_json_path: str,
    grade: int = 4,
    stage: int = 2,
    iteration_guidance: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
    messages = [
        {'role': 'system', 'content': pass1_detect_system(subject, grade=grade, stage=stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
        {
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': image_to_data_uri(image_path)}},
                {
                    'type': 'text',
                    'text': pass1_detect_user_prompt(subject, page_num, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) + (iteration_guidance or ''),
                },
            ],
        },
    ]
    result, _message = _call_qwen_json_with_retry(
        messages,
        {'enable_thinking': False},
        stage_label='Pass 1 检测阶段',
        require_questions=True,
        error_dump_path=out_detect_json_path.replace('.json', '.detect.error.txt'),
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    result = _normalize_detect_result(result, subject, page_num)
    sample_id = _sample_id_from_page_artifact_path(out_detect_json_path)
    source_document_sha256 = source_document_sha256_from_artifact_path(
        out_detect_json_path
    )
    (attach_fixed_english_choice_slots(
        result,
        subject,
        sample_id,
        page_num,
        image_path=image_path,
        source_document_sha256=source_document_sha256,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) if feedback_runtime is None or (feedback_runtime.has_specialized('english') and source_document_sha256_from_artifact_path(out_detect_json_path)) else {})
    safe_json_dump(out_detect_json_path, stamp_feedback(result, feedback_runtime, 'detect_page_layout'))
    return result


def grade_page_questions(
    image_path: str,
    subject: str,
    page_num: int,
    detected: Dict[str, Any],
    out_grade_json_path: str,
    thinking_budget: int = 4096,
    prior_context: Optional[str] = None,
    grade: int = 4,
    stage: int = 2,
    iteration_guidance: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
    extra_body = _grade_extra_body(subject, thinking_budget=thinking_budget)
    sample_id = _sample_id_from_page_artifact_path(out_grade_json_path)
    source_document_sha256 = source_document_sha256_from_artifact_path(
        out_grade_json_path
    )
    slot_audit = (attach_fixed_english_choice_slots(
        detected,
        subject,
        sample_id,
        page_num,
        image_path=image_path,
        source_document_sha256=source_document_sha256,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) if feedback_runtime is None or (feedback_runtime.has_specialized('english') and source_document_sha256_from_artifact_path(out_grade_json_path)) else {})
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(out_grade_json_path)))
    roi_dir = os.path.join(
        base_dir,
        'layout_evidence',
        'fixed_english_choice_slots',
    )
    if slot_audit.get('applied'):
        roi_items, _roi_audit = prepare_fixed_english_choice_rois(
            image_path,
            roi_dir,
            subject,
            sample_id,
            page_num,
            source_document_sha256=source_document_sha256,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    else:
        roi_items = []
    if roi_items:
        roi_transcription_content: List[Dict[str, Any]] = []
        for roi_item in roi_items:
            roi_transcription_content.extend([
                {
                    'type': 'text',
                    'text': f"槽位 {roi_item['question_id']}：",
                },
                {
                    'type': 'image_url',
                    'image_url': {'url': image_to_data_uri(roi_item['path'])},
                },
            ])
        roi_transcription_content.append({
            'type': 'text',
            'text': (
                '按上述顺序逐图抄写括号内黑笔字母，只输出 JSON。'
                + (iteration_guidance or '')
            ),
        })
        transcription_raw: Dict[str, Any] = {}
        try:
            transcription_raw, _transcription_message = _call_qwen_json_with_retry(
                [
                    {'role': 'system', 'content': ROI_TRANSCRIPTION_SYSTEM},
                    {'role': 'user', 'content': roi_transcription_content},
                ],
                {'enable_thinking': False},
                stage_label='英语固定括号 ROI 视觉转写',
                require_questions=True,
                error_dump_path=os.path.join(
                    roi_dir,
                    'transcription.error.txt',
                ),
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
            transcription, transcription_audit = (
                normalize_fixed_english_choice_transcription(
                    transcription_raw,
                    subject,
                    sample_id,
                    page_num,
                    source_document_sha256=source_document_sha256,
                **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
            )
            transcription_audit['recorded_slot_count'] = (
                record_fixed_english_choice_transcription(
                    detected,
                    transcription,
                    transcription_audit,
                )
            )
        except Exception as exc:
            logger.exception('英语固定括号 ROI 视觉转写失败')
            transcription_audit = {
                'accepted': False,
                'reason': 'roi_transcription_call_failed',
                'error': str(exc) or 'roi_transcription_call_failed',
            }
        safe_json_dump(
            os.path.join(roi_dir, 'transcription.json'),
            {
                'raw_result': transcription_raw,
                'audit': transcription_audit,
            },
        )
    user_content: List[Dict[str, Any]] = [
        {'type': 'image_url', 'image_url': {'url': image_to_data_uri(image_path)}},
    ]
    if roi_items:
        user_content.append({
            'type': 'text',
            'text': (
                '以下局部图按题号逐张给出，只用于读取对应 answer_slots 的括号内黑笔字母；'
                '每张图均直接裁自前面的同一张 clean 图并等比放大，不含答案标签或人工描画。'
            ),
        })
        for roi_item in roi_items:
            user_content.extend([
                {
                    'type': 'text',
                    'text': f"题目 {roi_item['question_id']} 的括号作答槽位 ROI：",
                },
                {
                    'type': 'image_url',
                    'image_url': {'url': image_to_data_uri(roi_item['path'])},
                },
            ])
    user_content.append({
        'type': 'text',
        'text': pass1_grade_user_prompt(
            subject,
            page_num,
            detected,
            prior_context=prior_context,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}), source_document_sha256=source_document_sha256) + (iteration_guidance or ''),
    })
    messages = [
        {
            'role': 'system',
            'content': pass1_grade_system(
                subject,
                grade=grade,
                stage=stage,
                sample_id=sample_id,
                page_num=page_num,
                source_document_sha256=source_document_sha256,
            **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
        },
        {
            'role': 'user',
            'content': user_content,
        },
    ]
    error_dump_path = out_grade_json_path.replace('.json', '.grade.error.txt')
    try:
        result, message = _call_qwen_json_with_retry(
            messages,
            extra_body,
            stage_label='Pass 1 批改阶段',
            require_questions=True,
            error_dump_path=error_dump_path,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    except ValueError as exc:
        if detected.get('questions'):
            logger.warning('Pass 1 批改阶段降级为 uncertain：page=%s reason=%s', page_num, exc)
            result = _fallback_grade_from_detect(detected, page_num, subject, str(exc))
            message = None
        else:
            raise
    if message is not None and subject == 'math':
        reasoning = getattr(message, 'reasoning_content', None) or ''
        if reasoning:
            with open(out_grade_json_path.replace('.json', '.thinking.txt'), 'w', encoding='utf-8') as file:
                file.write(reasoning)
    _normalize_pronunciation_grade_answers(result, detected, subject)
    (apply_fixed_english_page15_guard(
        result,
        page_num=page_num,
        source_document_sha256=source_document_sha256,
        sample_id=sample_id,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) if feedback_runtime is None or (feedback_runtime.has_specialized('english') and source_document_sha256_from_artifact_path(out_grade_json_path)) else {})
    (apply_fixed_english_choice_guard(result, detected) if feedback_runtime is None or (feedback_runtime.has_specialized('english') and source_document_sha256_from_artifact_path(out_grade_json_path)) else {})
    safe_json_dump(out_grade_json_path, stamp_feedback(result, feedback_runtime, 'grade_page_questions'))
    return result


def _patch_detect_layout_confidence(
    detected: Dict[str, Any],
    patch: Dict[str, Any],
    *,
    force: bool = False,
) -> Dict[str, Any]:
    patch_by_id = {
        str(item.get('id')).strip(): item
        for item in (patch.get('questions') or [])
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    for question in detected.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        item = patch_by_id.get(qid)
        if not item:
            continue
        if not force and 'layout_confidence' in question:
            continue
        confidence = _clamp_confidence(item.get('layout_confidence'))
        if confidence is not None:
            question['layout_confidence'] = confidence
    return detected


def _patch_grade_supplement_fields(
    graded: Dict[str, Any],
    patch: Dict[str, Any],
    *,
    force: bool = False,
) -> Dict[str, Any]:
    patch_by_id = {
        str(item.get('id')).strip(): item
        for item in (patch.get('questions') or [])
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    }
    locked_fields = (
        'student_answer', 'correct_answer', 'verdict',
        'error_type', 'knowledge_point', 'recurrence_hint',
    )
    for question in graded.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        item = patch_by_id.get(qid)
        if not item:
            continue
        if force or not str(question.get('understanding') or '').strip():
            understanding = str(item.get('understanding') or '').strip()
            if understanding:
                question['understanding'] = understanding
        for field in ('recognition_confidence', 'understanding_confidence', 'grading_confidence'):
            if not force and field in question:
                continue
            confidence = _clamp_confidence(item.get(field))
            if confidence is not None:
                question[field] = confidence
        for field in locked_fields:
            if field in item and item.get(field) not in (None, '') and question.get(field) not in (None, ''):
                if str(item.get(field)) != str(question.get(field)):
                    logger.warning(
                        'grade supplement attempted to change locked field %s for %s; kept existing',
                        field, qid,
                    )
    return graded


def supplement_detect_layout_confidence(
    image_path: str,
    subject: str,
    page_num: int,
    detected: Dict[str, Any],
    out_detect_json_path: str,
    grade: int = 4,
    stage: int = 2,
    force: bool = False,
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    """补全 Stage A 缺失的 layout_confidence，复用正常 detect system prompt。"""
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
    detected = _normalize_detect_result(dict(detected), subject, page_num)
    if not force and not any(
        isinstance(q, dict) and 'layout_confidence' not in q
        for q in (detected.get('questions') or [])
    ):
        safe_json_dump(out_detect_json_path, stamp_feedback(detected, feedback_runtime, 'supplement_detect_layout_confidence'))
        return detected

    messages = [
        {'role': 'system', 'content': pass1_detect_system(subject, grade=grade, stage=stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
        {
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': image_to_data_uri(image_path)}},
                {
                    'type': 'text',
                    'text': pass1_detect_supplement_user_prompt(subject, page_num, detected, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
                },
            ],
        },
    ]
    patch, _message = _call_qwen_json_with_retry(
        messages,
        {'enable_thinking': False},
        stage_label='Pass 1 版面置信度补全',
        require_questions=True,
        error_dump_path=out_detect_json_path.replace('.json', '.detect.supplement.error.txt'),
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    result = _patch_detect_layout_confidence(detected, patch, force=force)
    safe_json_dump(out_detect_json_path, stamp_feedback(result, feedback_runtime, 'supplement_detect_layout_confidence'))
    return result


def supplement_grade_understanding_fields(
    image_path: str,
    subject: str,
    page_num: int,
    detected: Dict[str, Any],
    graded: Dict[str, Any],
    out_grade_json_path: str,
    prior_context: Optional[str] = None,
    grade: int = 4,
    stage: int = 2,
    force: bool = False,
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    """补全 Stage B 缺失的 understanding/置信度，复用正常 grade system prompt。"""
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
    detected = _normalize_detect_result(dict(detected), subject, page_num)
    graded_questions = graded.get('questions') if isinstance(graded.get('questions'), list) else []
    graded = {'questions': list(graded_questions)}

    needs = force
    if not needs:
        for question in graded.get('questions') or []:
            if not isinstance(question, dict):
                continue
            if not str(question.get('understanding') or '').strip():
                needs = True
                break
            for field in ('recognition_confidence', 'understanding_confidence', 'grading_confidence'):
                if field not in question:
                    needs = True
                    break
            if needs:
                break
    if not needs:
        safe_json_dump(out_grade_json_path, stamp_feedback(graded, feedback_runtime, 'supplement_grade_understanding_fields'))
        return graded

    extra_body = _grade_extra_body(subject, thinking_budget=4096)
    messages = [
        {'role': 'system', 'content': pass1_grade_system(subject, grade=grade, stage=stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
        {
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': image_to_data_uri(image_path)}},
                {
                    'type': 'text',
                    'text': pass1_grade_supplement_user_prompt(
                        subject, page_num, detected, graded, prior_context=prior_context,
                    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
                },
            ],
        },
    ]
    patch, message = _call_qwen_json_with_retry(
        messages,
        extra_body,
        stage_label='Pass 1 理解置信度补全',
        require_questions=True,
        error_dump_path=out_grade_json_path.replace('.json', '.grade.supplement.error.txt'),
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    result = _patch_grade_supplement_fields(graded, patch, force=force)
    if message is not None and subject == 'math':
        reasoning = getattr(message, 'reasoning_content', None) or ''
        if reasoning:
            thinking_path = out_grade_json_path.replace('.json', '.grade.supplement.thinking.txt')
            with open(thinking_path, 'w', encoding='utf-8') as file:
                file.write(reasoning)
    safe_json_dump(out_grade_json_path, stamp_feedback(result, feedback_runtime, 'supplement_grade_understanding_fields'))
    return result


def _grade_page_two_stage(
    image_path: str,
    subject: str,
    page_num: int,
    out_json_path: str,
    thinking_budget: int = 4096,
    prior_context: Optional[str] = None,
    grade: int = 4,
    stage: int = 2,
    iteration_guidance: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
    detect_path = out_json_path.replace('.json', '.detect.json')
    grade_path = out_json_path.replace('.json', '.grade.json')
    detected = detect_page_layout(
        image_path,
        subject,
        page_num,
        detect_path,
        grade=grade,
        stage=stage,
        iteration_guidance=iteration_guidance,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    graded = grade_page_questions(
        image_path,
        subject,
        page_num,
        detected,
        grade_path,
        thinking_budget=thinking_budget,
        prior_context=prior_context,
        grade=grade,
        stage=stage,
        iteration_guidance=iteration_guidance,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    safe_json_dump(detect_path, stamp_feedback(detected, feedback_runtime, '_grade_page_two_stage'))
    result = _merge_detect_and_grade(
        detected, graded, subject, page_num, feedback_runtime=feedback_runtime,
    )
    source_document_sha256 = source_document_sha256_from_artifact_path(
        out_json_path
    )
    (attach_fixed_english_choice_slots(
        result,
        subject,
        _sample_id_from_page_artifact_path(out_json_path),
        page_num,
        image_path=image_path,
        source_document_sha256=source_document_sha256,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) if feedback_runtime is None or (feedback_runtime.has_specialized('english') and source_document_sha256_from_artifact_path(out_json_path)) else {})
    safe_json_dump(out_json_path, stamp_feedback(result, feedback_runtime, '_grade_page_two_stage'))
    return result


def _grade_page_one_shot(
    image_path: str,
    subject: str,
    page_num: int,
    out_json_path: str,
    thinking_budget: int = 4096,
    prior_context: Optional[str] = None,
    grade: int = 4,
    stage: int = 2,
    iteration_guidance: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
    extra_body = _grade_extra_body(subject, thinking_budget=thinking_budget)
    messages = [
        {'role': 'system', 'content': pass1_system(subject, grade=grade, stage=stage, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
        {
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': image_to_data_uri(image_path)}},
                {
                    'type': 'text',
                    'text': (
                        pass1_user_prompt(subject, page_num, prior_context=prior_context, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
                        + (iteration_guidance or '')
                    ),
                },
            ],
        },
    ]
    result, message = _call_qwen_json_with_retry(
        messages,
        extra_body,
        stage_label='Pass 1',
        require_questions=True,
        error_dump_path=out_json_path.replace('.json', '.error.txt'),
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if subject == 'math':
        reasoning = getattr(message, 'reasoning_content', None) or ''
        if reasoning:
            with open(out_json_path.replace('.json', '.thinking.txt'), 'w', encoding='utf-8') as file:
                file.write(reasoning)
    result = _normalize_pass1_result(result, subject, page_num)
    (apply_fixed_english_page15_guard(
        result,
        page_num=page_num,
        source_document_sha256=source_document_sha256_from_artifact_path(
            out_json_path
        ),
        sample_id=_sample_id_from_page_artifact_path(out_json_path),
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) if feedback_runtime is None or (feedback_runtime.has_specialized('english') and source_document_sha256_from_artifact_path(out_json_path)) else {})
    result['pass1_mode'] = 'one_shot'
    safe_json_dump(out_json_path, stamp_feedback(result, feedback_runtime, '_grade_page_one_shot'))
    return result


def detect_page_only(
    image_path: str,
    subject: str,
    page_num: int,
    out_json_path: str,
    grade: int = 4,
    stage: int = 2,
    iteration_guidance: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
    detect_path = out_json_path.replace('.json', '.detect.json')
    return detect_page_layout(
        image_path,
        subject,
        page_num,
        detect_path,
        grade=grade,
        stage=stage,
        iteration_guidance=iteration_guidance,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))


def grade_page_from_detect(
    image_path: str,
    subject: str,
    page_num: int,
    out_json_path: str,
    thinking_budget: int = 4096,
    prior_context: Optional[str] = None,
    grade: int = 4,
    stage: int = 2,
    iteration_guidance: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
    detect_path = out_json_path.replace('.json', '.detect.json')
    if not os.path.exists(detect_path):
        raise FileNotFoundError(f'缺少版面检测结果: {detect_path}')
    detected = _normalize_detect_result(safe_json_load(detect_path), subject, page_num)
    grade_path = out_json_path.replace('.json', '.grade.json')
    graded = grade_page_questions(
        image_path,
        subject,
        page_num,
        detected,
        grade_path,
        thinking_budget=thinking_budget,
        prior_context=prior_context,
        grade=grade,
        stage=stage,
        iteration_guidance=iteration_guidance,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    safe_json_dump(detect_path, stamp_feedback(detected, feedback_runtime, 'grade_page_from_detect'))
    result = _merge_detect_and_grade(
        detected, graded, subject, page_num, feedback_runtime=feedback_runtime,
    )
    source_document_sha256 = source_document_sha256_from_artifact_path(
        out_json_path
    )
    (attach_fixed_english_choice_slots(
        result,
        subject,
        _sample_id_from_page_artifact_path(out_json_path),
        page_num,
        image_path=image_path,
        source_document_sha256=source_document_sha256,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) if feedback_runtime is None or (feedback_runtime.has_specialized('english') and source_document_sha256_from_artifact_path(out_json_path)) else {})
    safe_json_dump(out_json_path, stamp_feedback(result, feedback_runtime, 'grade_page_from_detect'))
    return result


def grade_page(
    image_path: str,
    subject: str,
    page_num: int,
    out_json_path: str,
    thinking_budget: int = 4096,
    prior_context: Optional[str] = None,
    grade: int = 4,
    stage: int = 2,
    iteration_guidance: str = '',
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
    if _pass1_two_stage_enabled(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})):
        return _grade_page_two_stage(
            image_path,
            subject,
            page_num,
            out_json_path,
            thinking_budget=thinking_budget,
            prior_context=prior_context,
            grade=grade,
            stage=stage,
            iteration_guidance=iteration_guidance,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    return _grade_page_one_shot(
        image_path,
        subject,
        page_num,
        out_json_path,
        thinking_budget=thinking_budget,
        prior_context=prior_context,
        grade=grade,
        stage=stage,
        iteration_guidance=iteration_guidance,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
