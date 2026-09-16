"""Math slot-level answer-presence evidence collected during lossless layout.

Only explicitly approved sample pages may use this evidence as a formal Pass1
guard. Other math pages can still collect the same evidence in shadow mode.
"""
from __future__ import annotations

from .feedback_runtime import frozen_environment, stamp_feedback

import copy
import os
import re
from typing import Any, Dict, List, Set, Tuple

from app_chat.homework_grading.grader_pass1 import _call_qwen_json_with_retry
from app_chat.homework_grading.prompts import (
    PASS1_SLOT_PRESENCE_PROMPT_VERSION,
    pass1_slot_presence_system,
    pass1_slot_presence_user_prompt,
)
from app_chat.homework_grading.utils import (
    image_to_data_uri,
    normalize_position,
    safe_json_dump,
    safe_json_load,
)
from app_chat.homework_grading.special_cases import (
    ACTION_MATH_SLOT_PRESENCE_GUARD,
    document_special_case_enabled,
)


SLOT_PRESENCE_ENV = 'HOMEWORK_PASS1_SLOT_PRESENCE'
SLOT_PRESENCE_SCHEMA_VERSION = 'math-slot-presence-v2'
SLOT_PRESENCE_REGRESSION_PATH = os.path.join(
    os.path.dirname(__file__),
    'data',
    'experiments',
    'math_slot_presence_cases_20260724.json',
)
SLOT_TYPES = {
    'fill_blank',
    'work_area',
    'connection_area',
    'choice_mark',
    'drawing_area',
    'other',
}
PRESENCE_VALUES = {'present', 'absent', 'uncertain'}
REASON_CODES = {
    'black_stroke',
    'red_only',
    'residual_only',
    'no_mark',
    'printed_only',
    'ambiguous_overlap',
}
SLOT_KEYS = (
    'slot_id',
    'slot_type',
    'position',
    'presence',
    'ink_source',
    'student_black_visible',
    'teacher_mark_visible',
    'residual_or_negative_trace_visible',
    'reason_code',
    'confidence',
    'outside_formal_bbox',
)


def slot_presence_mode(subject: str, *, feedback_runtime=None) -> str:
    if (subject or '').strip().lower() != 'math':
        return 'off'
    raw = frozen_environment(feedback_runtime, SLOT_PRESENCE_ENV, 'apply').strip().lower()
    return raw if raw in {'off', 'shadow', 'apply'} else 'off'


def slot_presence_shadow_enabled(subject: str, *, feedback_runtime=None) -> bool:
    return slot_presence_mode(subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) == 'shadow'


def slot_presence_layout_enabled(subject: str, *, feedback_runtime=None) -> bool:
    return slot_presence_mode(subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) in {'shadow', 'apply'}


def _load_regression_manifest(*, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None:
        return next((s["content"]["resources"]["slot_presence_regression"] for s in feedback_runtime.dependencies["skills"] if "slot_presence_regression" in s["content"]["resources"]), {})
    if not os.path.isfile(SLOT_PRESENCE_REGRESSION_PATH):
        return {}
    return safe_json_load(SLOT_PRESENCE_REGRESSION_PATH)


def _page_stem(path_or_stem: str) -> str:
    return os.path.splitext(os.path.basename(str(path_or_stem or '').strip()))[0]


def slot_presence_apply_approved(
    path_or_stem: str,
    subject: str,
    *,
    source_document_sha256: str = '',
feedback_runtime=None) -> bool:
    if feedback_runtime is not None and (not source_document_sha256 or not feedback_runtime.has_specialized("math")):
        return False
    if slot_presence_mode(subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) != 'apply':
        return False
    stem = _page_stem(path_or_stem)
    match = re.match(r'^[^_]+_(?P<sample_id>.+)_page(?P<page>\d+)$', stem)
    if source_document_sha256:
        if not match:
            return False
        return document_special_case_enabled(
            subject,
            int(match.group('page')),
            ACTION_MATH_SLOT_PRESENCE_GUARD,
            source_document_sha256=source_document_sha256,
            sample_id=str(match.group('sample_id') or ''),
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    manifest = _load_regression_manifest(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    approved = {
        _page_stem(value)
        for value in manifest.get('apply_approved_page_stems') or []
        if str(value or '').strip()
    }
    return stem in approved


def _confidence(value: Any) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def _strict_bool(value: Any) -> bool:
    return value is True


def _slot_sort_key(slot: Dict[str, Any], fallback_index: int) -> Tuple[int, float, float, int]:
    try:
        model_index = int(slot.get('slot_index'))
    except (TypeError, ValueError):
        model_index = 0
    position = normalize_position(slot.get('position'))
    x1, y1 = (position[0], position[1]) if position else (1000.0, 1000.0)
    return (0 if model_index > 0 else 1, float(model_index or 0), y1 * 1001.0 + x1, fallback_index)


def _ink_source(
    student_black_visible: bool,
    teacher_mark_visible: bool,
    residual_visible: bool,
) -> str:
    if student_black_visible and (teacher_mark_visible or residual_visible):
        return 'mixed'
    if student_black_visible:
        return 'student_black'
    if teacher_mark_visible:
        return 'teacher_red'
    if residual_visible:
        return 'teacher_residual'
    return 'none'


def _normalized_presence(
    raw_presence: Any,
    student_black_visible: bool,
    reason_code: str,
) -> str:
    requested = str(raw_presence or '').strip().lower()
    if not student_black_visible:
        # The model is not allowed to call a slot present without separately
        # affirming visible student-black evidence.
        return 'uncertain' if reason_code == 'ambiguous_overlap' else 'absent'
    if requested == 'uncertain' or reason_code == 'ambiguous_overlap':
        return 'uncertain'
    return 'present'


def _question_presence(slots: List[Dict[str, Any]]) -> str:
    if not slots:
        return 'unknown'
    values = [slot['presence'] for slot in slots]
    if 'uncertain' in values:
        return 'uncertain'
    if all(value == 'absent' for value in values):
        return 'absent'
    if all(value == 'present' for value in values):
        return 'present'
    return 'partial'


def _slot_belongs_to_question(slot_position: Any, question_position: Any) -> bool:
    slot = normalize_position(slot_position)
    question = normalize_position(question_position)
    if not slot or not question:
        return False
    center_x = (slot[0] + slot[2]) / 2.0
    center_y = (slot[1] + slot[3]) / 2.0
    return (
        question[0] <= center_x <= question[2]
        and question[1] <= center_y <= question[3]
    )


def normalize_slot_presence_result(
    result: Dict[str, Any],
    detected: Dict[str, Any],
    subject: str,
    page_num: int,
*, feedback_runtime=None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    model_questions = result.get('questions') if isinstance(result.get('questions'), list) else []
    by_id: Dict[str, Dict[str, Any]] = {}
    returned_ids: Set[str] = set()
    for question in model_questions:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        if not qid or qid in by_id:
            continue
        by_id[qid] = question
        returned_ids.add(qid)

    expected_ids: List[str] = []
    questions: List[Dict[str, Any]] = []
    total_slots = 0
    for detected_question in detected.get('questions') or []:
        if not isinstance(detected_question, dict):
            continue
        qid = str(detected_question.get('id') or '').strip()
        if not qid:
            continue
        expected_ids.append(qid)
        source = by_id.get(qid) or {}
        raw_slots = source.get('slots') if isinstance(source.get('slots'), list) else []
        question_position = detected_question.get('position')
        candidate_slots = [
            (index, slot)
            for index, slot in enumerate(raw_slots)
            if isinstance(slot, dict) and normalize_position(slot.get('position'))
        ]
        ordered_slots = sorted(
            candidate_slots,
            key=lambda item: _slot_sort_key(item[1], item[0]),
        )
        slots: List[Dict[str, Any]] = []
        for slot_number, (_raw_index, raw_slot) in enumerate(ordered_slots, start=1):
            student_black_visible = _strict_bool(raw_slot.get('student_black_visible'))
            teacher_mark_visible = _strict_bool(raw_slot.get('teacher_mark_visible'))
            residual_visible = _strict_bool(
                raw_slot.get('residual_or_negative_trace_visible')
            )
            reason_code = str(raw_slot.get('reason_code') or '').strip().lower()
            if reason_code not in REASON_CODES:
                if student_black_visible:
                    reason_code = 'black_stroke'
                elif teacher_mark_visible:
                    reason_code = 'red_only'
                elif residual_visible:
                    reason_code = 'residual_only'
                else:
                    reason_code = 'no_mark'
            slot_type = str(raw_slot.get('slot_type') or '').strip().lower()
            if slot_type not in SLOT_TYPES:
                slot_type = 'other'
            slot = {
                'slot_id': f'{qid}:s{slot_number}',
                'slot_type': slot_type,
                'position': normalize_position(raw_slot.get('position')),
                'presence': _normalized_presence(
                    raw_slot.get('presence'),
                    student_black_visible,
                    reason_code,
                ),
                'ink_source': _ink_source(
                    student_black_visible,
                    teacher_mark_visible,
                    residual_visible,
                ),
                'student_black_visible': student_black_visible,
                'teacher_mark_visible': teacher_mark_visible,
                'residual_or_negative_trace_visible': residual_visible,
                'reason_code': reason_code,
                'confidence': _confidence(raw_slot.get('confidence')),
                # Formal detect currently stores one rectangle per question.
                # A wrapped/two-column sub-question can legitimately continue
                # outside it, so this is audit evidence rather than a reject
                # condition.
                'outside_formal_bbox': not _slot_belongs_to_question(
                    raw_slot.get('position'),
                    question_position,
                ),
            }
            slots.append({key: slot[key] for key in SLOT_KEYS})
        total_slots += len(slots)
        questions.append({
            'id': qid,
            'answer_presence': _question_presence(slots),
            'slots': slots,
        })

    expected_set = set(expected_ids)
    page_result = {
        'schema_version': SLOT_PRESENCE_SCHEMA_VERSION,
        'prompt_version': PASS1_SLOT_PRESENCE_PROMPT_VERSION,
        'mode': slot_presence_mode(subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
        'page': page_num,
        'subject': subject,
        'questions': questions,
    }
    metadata = {
        'expected_ids': expected_ids,
        'returned_ids': sorted(returned_ids & expected_set),
        'missing_ids': [qid for qid in expected_ids if qid not in returned_ids],
        'extra_ids': sorted(returned_ids - expected_set),
        'slot_count': total_slots,
        'outside_formal_bbox_count': sum(
            1
            for question in questions
            for slot in question.get('slots') or []
            if slot.get('outside_formal_bbox') is True
        ),
    }
    return page_result, metadata


def run_slot_presence_layout_page(
    raw_image_path: str,
    clean_image_path: str,
    subject: str,
    page_num: int,
    detected: Dict[str, Any],
    out_json_path: str,
*, feedback_runtime=None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Collect slot presence from raw and clean page evidence."""
    if feedback_runtime is not None:
        subject = feedback_runtime.context["subject_code"]
        if not feedback_runtime.has_specialized("math"):
            result = stamp_feedback({"status":"not_covered", "questions":[], "page":page_num}, feedback_runtime, "slot_presence")
            safe_json_dump(out_json_path, result)
            return result, {"status":"not_covered"}
    result, _message = _call_qwen_json_with_retry(
        [
            {'role': 'system', 'content': pass1_slot_presence_system()},
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {'url': image_to_data_uri(raw_image_path)},
                    },
                    {
                        'type': 'image_url',
                        'image_url': {'url': image_to_data_uri(clean_image_path)},
                    },
                    {
                        'type': 'text',
                        'text': pass1_slot_presence_user_prompt(page_num, detected),
                    },
                ],
            },
        ],
        {'enable_thinking': False},
        stage_label='Pass 1 无损版面槽位存在性判断',
        require_questions=True,
        error_dump_path=out_json_path.replace('.presence.json', '.presence.error.txt'),
        temperature=0.0,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    normalized, metadata = normalize_slot_presence_result(
        result,
        detected,
        subject,
        page_num,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    safe_json_dump(out_json_path, stamp_feedback(normalized, feedback_runtime, "slot_presence"))
    return normalized, metadata


def evaluate_slot_presence_regression(
    page_result: Dict[str, Any],
    regression_manifest: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare one page result with offline-only labels from a regression manifest."""
    page_num = int(page_result.get('page') or 0)
    actual_by_id = {
        str(question.get('id') or '').strip(): question
        for question in page_result.get('questions') or []
        if isinstance(question, dict) and str(question.get('id') or '').strip()
    }
    cases = [
        case for case in regression_manifest.get('cases') or []
        if isinstance(case, dict) and int(case.get('page') or 0) == page_num
    ]
    details: List[Dict[str, Any]] = []
    passed = 0
    for case in cases:
        qid = str(case.get('question_id') or '').strip()
        expected = case.get('evaluation') if isinstance(case.get('evaluation'), dict) else {}
        actual = actual_by_id.get(qid) or {}
        actual_slots = {
            str(slot.get('slot_id') or '').strip(): slot
            for slot in actual.get('slots') or []
            if isinstance(slot, dict) and str(slot.get('slot_id') or '').strip()
        }
        expected_slots = expected.get('slots') if isinstance(expected.get('slots'), list) else []
        expected_slot_ids = {
            str(slot.get('slot_id') or '').strip()
            for slot in expected_slots
            if isinstance(slot, dict) and str(slot.get('slot_id') or '').strip()
        }
        slot_checks = []
        for expected_slot in expected_slots:
            if not isinstance(expected_slot, dict):
                continue
            slot_id = str(expected_slot.get('slot_id') or '').strip()
            actual_slot = actual_slots.get(slot_id) or {}
            slot_checks.append({
                'slot_id': slot_id,
                'expected_presence': expected_slot.get('presence'),
                'actual_presence': actual_slot.get('presence'),
                'passed': (
                    bool(actual_slot)
                    and actual_slot.get('presence') == expected_slot.get('presence')
                ),
            })
        unexpected_slot_ids = sorted(set(actual_slots) - expected_slot_ids)
        slot_set_passed = (
            set(actual_slots) == expected_slot_ids
            if expected_slot_ids
            else not actual_slots
        )
        question_presence_passed = (
            actual.get('answer_presence') == expected.get('answer_presence')
        )
        case_passed = (
            bool(actual)
            and question_presence_passed
            and bool(slot_checks)
            and all(check['passed'] for check in slot_checks)
            and slot_set_passed
        )
        passed += int(case_passed)
        details.append({
            'case_id': case.get('case_id'),
            'question_id': qid,
            'expected_answer_presence': expected.get('answer_presence'),
            'actual_answer_presence': actual.get('answer_presence'),
            'answer_presence_passed': question_presence_passed,
            'slot_checks': slot_checks,
            'unexpected_slot_ids': unexpected_slot_ids,
            'slot_set_passed': slot_set_passed,
            'passed': case_passed,
        })
    return {
        'page': page_num,
        'case_count': len(details),
        'passed_count': passed,
        'pass_rate': round(passed / len(details), 4) if details else 0.0,
        'details': details,
    }


def _question_by_id(page_result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(question.get('id') or '').strip(): question
        for question in page_result.get('questions') or []
        if isinstance(question, dict) and str(question.get('id') or '').strip()
    }


def _locked_question_fields(
    question: Dict[str, Any],
    presence_question: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    slots = presence_question.get('slots') if isinstance(
        presence_question.get('slots'),
        list,
    ) else []
    answer_presence = str(presence_question.get('answer_presence') or '').strip()
    segments = question.get('visual_answer_segments')
    if not isinstance(segments, list):
        return {}, {'block_reason': 'visual_answer_segments_missing'}
    normalized_segments = [str(segment or '').strip() for segment in segments]

    if answer_presence == 'absent':
        kept_segments: List[str] = []
    elif answer_presence in {'partial', 'present'}:
        if len(normalized_segments) != len(slots):
            return {}, {
                'block_reason': 'slot_segment_count_mismatch',
                'slot_count': len(slots),
                'segment_count': len(normalized_segments),
            }
        kept_segments = [
            segment
            for segment, slot in zip(normalized_segments, slots)
            if slot.get('presence') == 'present'
        ]
    else:
        return {}, {'block_reason': f'unsupported_presence:{answer_presence or "unknown"}'}

    if answer_presence == 'present':
        # All slots were independently confirmed. Preserve the original
        # mathematical verdict and explanation.
        return {
            'visual_answer_segments': normalized_segments,
            'student_answer': str(question.get('student_answer') or '').strip(),
            'understanding': str(question.get('understanding') or '').strip(),
            'verdict': str(question.get('verdict') or 'uncertain').strip(),
            'error_type': str(question.get('error_type') or '').strip(),
        }, {
            'kept_slot_ids': [
                str(slot.get('slot_id') or '').strip() for slot in slots
            ],
            'removed_slot_ids': [],
        }

    if answer_presence == 'absent':
        locked = {
            'visual_answer_segments': [],
            'student_answer': '',
            'understanding': '未检测到学生黑笔作答。',
            'verdict': 'unanswered',
            'error_type': '未作答',
        }
    else:
        locked = {
            'visual_answer_segments': kept_segments,
            'student_answer': ' '.join(segment for segment in kept_segments if segment),
            'understanding': '仅检测到部分作答槽位存在学生黑笔；空槽不按题意补全。',
            'verdict': 'partial',
            'error_type': '未完整作答',
        }
    return locked, {
        'kept_slot_ids': [
            str(slot.get('slot_id') or '').strip()
            for slot in slots
            if slot.get('presence') == 'present'
        ],
        'removed_slot_ids': [
            str(slot.get('slot_id') or '').strip()
            for slot in slots
            if slot.get('presence') == 'absent'
        ],
    }


def apply_slot_presence_guard(
    graded: Dict[str, Any],
    page_result: Dict[str, Any],
    page_stem: str,
    subject: str = 'math',
    *,
    source_document_sha256: str = '',
feedback_runtime=None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Apply an approved, regression-validated presence result to Pass1 grade."""
    guarded = copy.deepcopy(graded)
    audit: Dict[str, Any] = {
        'mode': slot_presence_mode(subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
        'page_stem': _page_stem(page_stem),
        'approved': slot_presence_apply_approved(
            page_stem,
            subject,
            source_document_sha256=source_document_sha256,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})),
        'applied_question_count': 0,
        'blocked_questions': [],
    }
    if not audit['approved']:
        audit['block_reason'] = 'page_not_apply_approved'
        return guarded, audit

    manifest = _load_regression_manifest(**({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    evaluation = evaluate_slot_presence_regression(page_result, manifest)
    audit['regression'] = evaluation
    if (
        evaluation.get('case_count', 0) <= 0
        or evaluation.get('passed_count') != evaluation.get('case_count')
    ):
        audit['block_reason'] = 'fixed_regression_mismatch'
        return guarded, audit

    presence_by_id = _question_by_id(page_result)
    graded_by_id = _question_by_id(guarded)
    target_ids = [
        str(detail.get('question_id') or '').strip()
        for detail in evaluation.get('details') or []
        if str(detail.get('question_id') or '').strip()
    ]
    for qid in target_ids:
        question = graded_by_id.get(qid)
        presence_question = presence_by_id.get(qid)
        if not question or not presence_question:
            audit['blocked_questions'].append({
                'question_id': qid,
                'block_reason': 'question_missing',
            })
            continue
        original = {
            key: copy.deepcopy(question.get(key))
            for key in (
                'visual_answer_segments',
                'student_answer',
                'understanding',
                'verdict',
                'error_type',
            )
        }
        locked, detail = _locked_question_fields(question, presence_question)
        if not locked:
            audit['blocked_questions'].append({
                'question_id': qid,
                **detail,
            })
            continue
        question.update(copy.deepcopy(locked))
        question['slot_presence_guard'] = {
            'mode': 'apply',
            'applied': True,
            'answer_presence': presence_question.get('answer_presence'),
            'original_fields': original,
            'locked_fields': copy.deepcopy(locked),
            **detail,
        }
        audit['applied_question_count'] += 1

    audit['applied'] = audit['applied_question_count'] > 0
    guarded['slot_presence_guard'] = copy.deepcopy(audit)
    return guarded, audit


def reapply_slot_presence_locks(
    page_result: Dict[str, Any],
    guard_source: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], int]:
    """Restore immutable guarded fields after downstream review/verifier stages."""
    restored = copy.deepcopy(page_result)
    source = guard_source if isinstance(guard_source, dict) else page_result
    source_by_id = _question_by_id(source)
    restored_count = 0
    for question in restored.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        source_question = source_by_id.get(qid) or {}
        guard = source_question.get('slot_presence_guard')
        if not isinstance(guard, dict) or guard.get('applied') is not True:
            continue
        locked = guard.get('locked_fields')
        if not isinstance(locked, dict):
            continue
        for key, value in locked.items():
            # Merged business JSON intentionally has no internal visual
            # segments; keep that contract while still restoring grade files.
            if key == 'visual_answer_segments' and 'visual_answer_segments' not in question:
                continue
            question[key] = copy.deepcopy(value)
        question['slot_presence_guard'] = copy.deepcopy(guard)
        restored_count += 1
    source_audit = source.get('slot_presence_guard')
    if isinstance(source_audit, dict):
        restored['slot_presence_guard'] = copy.deepcopy(source_audit)
    return restored, restored_count


def apply_slot_presence_guard_to_files(
    grade_path: str,
    final_path: str,
    presence_path: str,
    page_stem: str,
    subject: str = 'math',
    *,
    source_document_sha256: str = '',
feedback_runtime=None) -> Dict[str, Any]:
    """Apply once to the grade JSON and propagate locks to merged page JSON."""
    graded = safe_json_load(grade_path)
    presence = safe_json_load(presence_path)
    guarded, audit = apply_slot_presence_guard(
        graded,
        presence,
        page_stem,
        subject=subject,
        source_document_sha256=source_document_sha256,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if not audit.get('applied'):
        return audit
    safe_json_dump(grade_path, guarded)
    final = safe_json_load(final_path)
    restored, restored_count = reapply_slot_presence_locks(final, guarded)
    safe_json_dump(final_path, restored)
    audit['restored_final_question_count'] = restored_count
    return audit


def reapply_slot_presence_guard_files(
    grade_path: str,
    final_path: str,
) -> int:
    """Reapply grade-file locks to one downstream-mutated merged page JSON."""
    if not os.path.isfile(grade_path) or not os.path.isfile(final_path):
        return 0
    guarded_grade = safe_json_load(grade_path)
    final = safe_json_load(final_path)
    restored, restored_count = reapply_slot_presence_locks(final, guarded_grade)
    if restored_count:
        safe_json_dump(final_path, restored)
    return restored_count
