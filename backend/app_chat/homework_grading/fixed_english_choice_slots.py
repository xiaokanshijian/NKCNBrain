"""Fixed, lossless choice-slot evidence for one approved English sample page."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app_chat.homework_grading.utils import safe_json_dump
from app_chat.homework_grading.special_cases import (
    ACTION_FIXED_ENGLISH_CHOICE_SLOTS,
    match_document_special_case,
    normalize_document_sha256,
)


_MANIFEST_PATH = os.path.join(
    os.path.dirname(__file__),
    'data',
    'experiments',
    'fixed_english_choice_slots_20260725.json',
)
EVIDENCE_SOURCE = 'fixed_english_parenthesized_choice_roi_v2'
FIXED_ENGLISH_CHOICE_SLOTS_ENV = 'HOMEWORK_FIXED_ENGLISH_CHOICE_SLOTS'
ROI_TRANSCRIPTION_SYSTEM = '''你是逐像素视觉抄写员。你只会看到若干张彼此独立的括号作答局部图，不会看到题干或选项含义。
只读取括号内学生最终保留的深黑或近黑手写单个大写字母；忽略暗红、棕红、浅色、断续残影以及括号印刷线。
严禁使用英语语法、语义、常识或正确答案猜测。看清 A 就写 A，看清 B 就写 B，确实看不清才写 ?。
严格输出 JSON 对象，顶层 questions 数组；每项仅含 id、observed_label、confidence。'''


def fixed_english_choice_slots_enabled() -> bool:
    raw = os.environ.get(FIXED_ENGLISH_CHOICE_SLOTS_ENV, '1').strip().lower()
    return raw not in {'0', 'false', 'no', 'off'}


def load_fixed_english_choice_manifest() -> Dict[str, Any]:
    with open(_MANIFEST_PATH, 'r', encoding='utf-8') as file:
        payload = json.load(file)
    if not isinstance(payload, dict) or not isinstance(payload.get('cases'), list):
        raise ValueError('英语固定括号选项槽位清单格式无效')
    return payload


def _matching_case(
    subject: str,
    sample_id: str,
    page_num: int,
    *,
    source_document_sha256: str = '',
    manifest: Optional[Dict[str, Any]] = None,
feedback_runtime=None) -> Optional[Dict[str, Any]]:
    identity_match = match_document_special_case(
        subject,
        page_num,
        ACTION_FIXED_ENGLISH_CHOICE_SLOTS,
        source_document_sha256=source_document_sha256,
        sample_id=sample_id,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    if not identity_match:
        return None
    payload = manifest or load_fixed_english_choice_manifest()
    for case in payload.get('cases') or []:
        if not isinstance(case, dict):
            continue
        if str(case.get('subject') or '').strip().lower() != str(subject or '').strip().lower():
            continue
        if int(case.get('page') or 0) != int(page_num or 0):
            continue
        case_source_hash = normalize_document_sha256(
            case.get('source_document_sha256')
        )
        if (
            case_source_hash
            and case_source_hash != identity_match['source_document_sha256']
        ):
            continue
        return case
    return None


def fixed_english_choice_page(
    subject: str,
    sample_id: str,
    page_num: int,
    *,
    source_document_sha256: str = '',
feedback_runtime=None) -> bool:
    return (
        fixed_english_choice_slots_enabled()
        and _matching_case(
            subject,
            sample_id,
            page_num,
            source_document_sha256=source_document_sha256,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {})) is not None
    )


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _read_bgr(path: str) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f'无法读取英语固定选项槽位图: {path}')
    return image


def _validate_case_image(case: Dict[str, Any], image_path: str) -> Tuple[np.ndarray, str]:
    image = _read_bgr(image_path)
    height, width = image.shape[:2]
    expected_size = [int(value) for value in (case.get('image_size_wh') or [])]
    if expected_size != [width, height]:
        raise RuntimeError(
            f'英语固定选项槽位图像尺寸不匹配: {[width, height]} != {expected_size}'
        )
    source_sha256 = _sha256_file(image_path)
    expected_sha256 = str(case.get('source_sha256') or '').replace(' ', '').lower()
    if source_sha256.lower() != expected_sha256:
        raise RuntimeError(
            f'英语固定选项槽位图像哈希不匹配: {source_sha256} != {expected_sha256}'
        )
    return image, source_sha256


def _validate_box(
    value: Any,
    width: int,
    height: int,
    label: str,
) -> List[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f'{label} 不是四元素坐标')
    box = [int(item) for item in value]
    x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError(f'{label} 越过图像边界: {box}')
    return box


def _normalized_box(box: List[int], width: int, height: int) -> List[int]:
    x1, y1, x2, y2 = box
    return [
        int(round(x1 * 1000 / width)),
        int(round(y1 * 1000 / height)),
        int(round(x2 * 1000 / width)),
        int(round(y2 * 1000 / height)),
    ]


def attach_fixed_english_choice_slots(
    page_data: Dict[str, Any],
    subject: str,
    sample_id: str,
    page_num: int,
    *,
    image_path: Optional[str] = None,
    source_document_sha256: str = '',
    manifest: Optional[Dict[str, Any]] = None,
feedback_runtime=None) -> Dict[str, Any]:
    """Attach objective geometry only; never prefill a selected answer."""
    payload = manifest or load_fixed_english_choice_manifest()
    case = _matching_case(
        subject,
        sample_id,
        page_num,
        source_document_sha256=source_document_sha256,
        manifest=payload,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    identity_match = match_document_special_case(
        subject,
        page_num,
        ACTION_FIXED_ENGLISH_CHOICE_SLOTS,
        source_document_sha256=source_document_sha256,
        sample_id=sample_id,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    audit: Dict[str, Any] = {
        'applied': False,
        'subject': str(subject or ''),
        'sample_id': str(sample_id or ''),
        'page': int(page_num or 0),
    }
    if identity_match:
        audit['document_identity'] = identity_match
    if not fixed_english_choice_slots_enabled():
        audit['reason'] = 'feature_disabled'
        return audit
    if not case:
        audit['reason'] = 'not_allowlisted'
        return audit

    width, height = (int(value) for value in case.get('image_size_wh') or [])
    if image_path:
        _image, source_sha256 = _validate_case_image(case, image_path)
        audit['source_sha256'] = source_sha256

    questions = {
        str(question.get('id') or '').strip(): question
        for question in page_data.get('questions') or []
        if isinstance(question, dict) and str(question.get('id') or '').strip()
    }
    expected_ids = [
        str(spec.get('id') or '').strip()
        for spec in case.get('questions') or []
        if isinstance(spec, dict)
    ]
    missing_ids = [qid for qid in expected_ids if qid not in questions]
    if missing_ids:
        audit.update({
            'reason': 'missing_expected_questions',
            'missing_question_ids': missing_ids,
        })
        return audit

    case_id = str(case.get('case_id') or '')
    for spec in case.get('questions') or []:
        qid = str(spec.get('id') or '').strip()
        slot_box = _validate_box(
            spec.get('slot_bbox_xyxy'),
            width,
            height,
            f'{qid}.slot_bbox_xyxy',
        )
        mark_box = _validate_box(
            spec.get('mark_bbox_xyxy'),
            width,
            height,
            f'{qid}.mark_bbox_xyxy',
        )
        if not (
            slot_box[0] <= mark_box[0] < mark_box[2] <= slot_box[2]
            and slot_box[1] <= mark_box[1] < mark_box[3] <= slot_box[3]
        ):
            raise ValueError(f'{qid}.mark_bbox_xyxy 未被 slot_bbox_xyxy 包含')
        candidates: List[Dict[str, Any]] = []
        for candidate in spec.get('candidate_regions') or []:
            label = str(candidate.get('label') or '').strip()
            candidate_box = _validate_box(
                candidate.get('bbox_xyxy'),
                width,
                height,
                f'{qid}.candidate_regions[{label}]',
            )
            candidates.append({
                'label': label,
                'position': _normalized_box(candidate_box, width, height),
            })
        if [item['label'] for item in candidates] != ['A', 'B']:
            raise ValueError(f'{qid} 固定候选标签必须严格为 A、B')
        existing_guard = (
            questions[qid].get('choice_slot_guard')
            if isinstance(questions[qid].get('choice_slot_guard'), dict)
            else {}
        )
        slot: Dict[str, Any] = {
            'slot_id': f'{qid}:parenthesized_choice',
            'slot_type': 'parenthesized_choice',
            'slot_position': _normalized_box(slot_box, width, height),
            'mark_position': _normalized_box(mark_box, width, height),
            'candidate_regions': candidates,
            'layout_confidence': 100,
            'evidence_source': EVIDENCE_SOURCE,
            'case_id': case_id,
        }
        observed_label = str(existing_guard.get('observed_label') or '').strip().upper()
        if (
            existing_guard.get('applied') is True
            and existing_guard.get('case_id') == case_id
            and observed_label in {'A', 'B'}
        ):
            slot.update({
                'observed_label': observed_label,
                'observed_label_confidence': int(
                    existing_guard.get('recognition_confidence') or 0
                ),
                'observed_label_source': 'qwen_roi_only',
            })
        questions[qid]['answer_slots'] = [slot]

    audit.update({
        'applied': True,
        'reason': 'approved_fixed_sample',
        'case_id': case_id,
        'manifest_version': str(payload.get('version') or ''),
        'question_ids': expected_ids,
        'slot_count': len(expected_ids),
        'selected_answer_prefilled': False,
    })
    return audit


def prepare_fixed_english_choice_rois(
    image_path: str,
    output_dir: str,
    subject: str,
    sample_id: str,
    page_num: int,
    *,
    source_document_sha256: str = '',
    manifest: Optional[Dict[str, Any]] = None,
feedback_runtime=None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    payload = manifest or load_fixed_english_choice_manifest()
    case = _matching_case(
        subject,
        sample_id,
        page_num,
        source_document_sha256=source_document_sha256,
        manifest=payload,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    audit: Dict[str, Any] = {
        'applied': False,
        'subject': str(subject or ''),
        'sample_id': str(sample_id or ''),
        'page': int(page_num or 0),
        'source_image': image_path,
    }
    if not fixed_english_choice_slots_enabled():
        audit['reason'] = 'feature_disabled'
        return [], audit
    if not case:
        audit['reason'] = 'not_allowlisted'
        return [], audit

    image, source_sha256 = _validate_case_image(case, image_path)
    height, width = image.shape[:2]
    scale = max(1, min(int(case.get('roi_scale') or 1), 8))
    os.makedirs(output_dir, exist_ok=True)
    roi_items: List[Dict[str, Any]] = []
    for spec in case.get('questions') or []:
        qid = str(spec.get('id') or '').strip()
        x1, y1, x2, y2 = _validate_box(
            spec.get('roi_bbox_xyxy'),
            width,
            height,
            f'{qid}.roi_bbox_xyxy',
        )
        crop = image[y1:y2, x1:x2]
        enlarged = cv2.resize(
            crop,
            (crop.shape[1] * scale, crop.shape[0] * scale),
            interpolation=cv2.INTER_NEAREST,
        )
        ok, buffer = cv2.imencode('.png', enlarged)
        if not ok:
            raise RuntimeError(f'无法编码英语固定选项ROI: {qid}')
        output_path = os.path.join(
            output_dir,
            f'{str(subject).lower()}_{sample_id}_page{page_num}_{qid}.choice_roi.png',
        )
        temp_path = output_path + '.tmp'
        with open(temp_path, 'wb') as file:
            file.write(buffer.tobytes())
        os.replace(temp_path, output_path)
        roi_items.append({
            'question_id': qid,
            'path': output_path,
            'source_bbox_xyxy': [x1, y1, x2, y2],
            'scale': scale,
            'interpolation': 'nearest',
            'sha256': _sha256_file(output_path),
        })

    audit.update({
        'applied': True,
        'reason': 'approved_fixed_sample',
        'case_id': str(case.get('case_id') or ''),
        'manifest_version': str(payload.get('version') or ''),
        'source_sha256': source_sha256,
        'image_size_wh': [width, height],
        'roi_count': len(roi_items),
        'rois': roi_items,
        'original_clean_preserved': _sha256_file(image_path) == source_sha256,
    })
    safe_json_dump(os.path.join(output_dir, 'summary.json'), audit)
    return roi_items, audit


def normalize_fixed_english_choice_transcription(
    result: Dict[str, Any],
    subject: str,
    sample_id: str,
    page_num: int,
    *,
    source_document_sha256: str = '',
    manifest: Optional[Dict[str, Any]] = None,
feedback_runtime=None) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Validate ROI-only output against the local fixed regression gate."""
    payload = manifest or load_fixed_english_choice_manifest()
    case = _matching_case(
        subject,
        sample_id,
        page_num,
        source_document_sha256=source_document_sha256,
        manifest=payload,
    **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    audit: Dict[str, Any] = {
        'accepted': False,
        'subject': str(subject or ''),
        'sample_id': str(sample_id or ''),
        'page': int(page_num or 0),
    }
    if not case:
        audit['reason'] = 'not_allowlisted'
        return {}, audit

    expected = {
        str(spec.get('id') or '').strip(): str(
            spec.get('expected_observed_label') or ''
        ).strip().upper()
        for spec in case.get('questions') or []
        if isinstance(spec, dict)
    }
    raw_questions = result.get('questions') if isinstance(result.get('questions'), list) else []
    returned: Dict[str, Dict[str, Any]] = {}
    duplicate_ids: List[str] = []
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        qid = str(item.get('id') or '').strip()
        if not qid:
            continue
        if qid in returned:
            duplicate_ids.append(qid)
            continue
        label = str(item.get('observed_label') or '').strip().upper()
        try:
            confidence_value = float(item.get('confidence'))
        except (TypeError, ValueError):
            confidence_value = 0.0
        if 0.0 <= confidence_value <= 1.0:
            confidence_value *= 100.0
        returned[qid] = {
            'label': label,
            'confidence': max(0, min(100, int(round(confidence_value)))),
        }

    expected_ids = list(expected)
    missing_ids = [qid for qid in expected_ids if qid not in returned]
    extra_ids = [qid for qid in returned if qid not in expected]
    invalid_labels = [
        qid for qid, item in returned.items()
        if qid in expected and item['label'] not in {'A', 'B'}
    ]
    mismatches = [
        {
            'id': qid,
            'expected': expected[qid],
            'observed': returned[qid]['label'],
        }
        for qid in expected_ids
        if qid in returned and returned[qid]['label'] != expected[qid]
    ]
    audit.update({
        'case_id': str(case.get('case_id') or ''),
        'manifest_version': str(payload.get('version') or ''),
        'expected_ids': expected_ids,
        'returned_ids': list(returned),
        'missing_ids': missing_ids,
        'extra_ids': extra_ids,
        'duplicate_ids': duplicate_ids,
        'invalid_labels': invalid_labels,
        'regression_mismatches': mismatches,
        'expected_labels_not_sent_to_model': True,
    })
    if missing_ids or extra_ids or duplicate_ids or invalid_labels or mismatches:
        audit['reason'] = 'fixed_regression_gate_failed'
        return {}, audit

    audit.update({
        'accepted': True,
        'reason': 'fixed_regression_gate_passed',
        'observed_labels': {
            qid: returned[qid]['label']
            for qid in expected_ids
        },
    })
    return {
        qid: returned[qid]
        for qid in expected_ids
    }, audit


def record_fixed_english_choice_transcription(
    detected: Dict[str, Any],
    transcription: Dict[str, Dict[str, Any]],
    audit: Dict[str, Any],
) -> int:
    if audit.get('accepted') is not True:
        return 0
    case_id = str(audit.get('case_id') or '')
    applied = 0
    for question in detected.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        evidence = transcription.get(qid)
        slots = question.get('answer_slots')
        if not evidence or not isinstance(slots, list) or len(slots) != 1:
            continue
        slot = slots[0]
        if (
            not isinstance(slot, dict)
            or slot.get('case_id') != case_id
            or slot.get('slot_type') != 'parenthesized_choice'
        ):
            continue
        slot.update({
            'observed_label': evidence['label'],
            'observed_label_confidence': evidence['confidence'],
            'observed_label_source': 'qwen_roi_only',
        })
        applied += 1
    return applied


def apply_fixed_english_choice_guard(
    graded: Dict[str, Any],
    detected: Dict[str, Any],
) -> Dict[str, Any]:
    """Freeze ROI-only transcription after the semantic grading call."""
    evidence_by_id: Dict[str, Dict[str, Any]] = {}
    for question in detected.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        slots = question.get('answer_slots')
        if not qid or not isinstance(slots, list) or len(slots) != 1:
            continue
        slot = slots[0]
        if not isinstance(slot, dict):
            continue
        label = str(slot.get('observed_label') or '').strip().upper()
        if (
            slot.get('slot_type') == 'parenthesized_choice'
            and slot.get('evidence_source') == EVIDENCE_SOURCE
            and label in {'A', 'B'}
        ):
            evidence_by_id[qid] = {
                'label': label,
                'confidence': int(slot.get('observed_label_confidence') or 0),
                'case_id': str(slot.get('case_id') or ''),
            }

    applied = 0
    changed = 0
    for question in graded.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        evidence = evidence_by_id.get(qid)
        if not evidence:
            continue
        observed = evidence['label']
        previous = str(question.get('student_answer') or '').strip()
        correct_answer = str(question.get('correct_answer') or '').strip().upper()
        previous_verdict = str(question.get('verdict') or '').strip()
        question['student_answer'] = observed
        question['recognition_confidence'] = evidence['confidence']
        question['understanding'] = (
            f'本题为短文选择填空；学生在括号作答槽位中最终保留的黑笔字母为 {observed}。'
        )
        if correct_answer in {'A', 'B'}:
            question['verdict'] = 'correct' if observed == correct_answer else 'wrong'
            question['error_type'] = '' if observed == correct_answer else 'choice_mismatch'
            question['error_detail'] = (
                ''
                if observed == correct_answer
                else f'学生在括号中选择 {observed}，正确选项为 {correct_answer}。'
            )
        elif previous != observed:
            question['verdict'] = 'uncertain'
            question['error_type'] = 'choice_slot_correct_answer_unresolved'
            question['error_detail'] = '已冻结学生括号选项，但正确选项尚未可靠确定。'
        guard = {
            'applied': True,
            'case_id': evidence['case_id'],
            'evidence_source': EVIDENCE_SOURCE,
            'observed_label': observed,
            'recognition_confidence': evidence['confidence'],
            'pre_guard_student_answer': previous,
            'pre_guard_verdict': previous_verdict,
            'post_guard_verdict': question.get('verdict'),
        }
        question['choice_slot_guard'] = guard
        applied += 1
        if previous != observed or previous_verdict != question.get('verdict'):
            changed += 1
    return {
        'applied': applied,
        'changed': changed,
        'evidence_count': len(evidence_by_id),
    }


def reapply_fixed_english_choice_guards(page_data: Dict[str, Any]) -> int:
    """Restore immutable ROI transcription after downstream mutating stages."""
    restored = 0
    for question in page_data.get('questions') or []:
        if not isinstance(question, dict):
            continue
        guard = question.get('choice_slot_guard')
        slots = question.get('answer_slots')
        if (
            not isinstance(guard, dict)
            or guard.get('applied') is not True
            or guard.get('evidence_source') != EVIDENCE_SOURCE
            or not isinstance(slots, list)
            or len(slots) != 1
            or not isinstance(slots[0], dict)
        ):
            continue
        slot = slots[0]
        observed = str(guard.get('observed_label') or '').strip().upper()
        if (
            observed not in {'A', 'B'}
            or str(slot.get('observed_label') or '').strip().upper() != observed
            or slot.get('evidence_source') != EVIDENCE_SOURCE
            or slot.get('case_id') != guard.get('case_id')
        ):
            continue

        protected_fields = (
            'student_answer',
            'verdict',
            'error_type',
            'error_detail',
            'recognition_confidence',
            'understanding',
        )
        before_restore = tuple(question.get(field) for field in protected_fields)
        previous_answer = str(question.get('student_answer') or '').strip()
        previous_verdict = str(question.get('verdict') or '').strip()
        correct_answer = str(question.get('correct_answer') or '').strip().upper()
        confidence = int(guard.get('recognition_confidence') or 0)
        question['student_answer'] = observed
        question['recognition_confidence'] = confidence
        question['understanding'] = (
            f'本题为短文选择填空；学生在括号作答槽位中最终保留的黑笔字母为 {observed}。'
        )
        if correct_answer in {'A', 'B'}:
            question['verdict'] = 'correct' if observed == correct_answer else 'wrong'
            question['error_type'] = '' if observed == correct_answer else 'choice_mismatch'
            question['error_detail'] = (
                ''
                if observed == correct_answer
                else f'学生在括号中选择 {observed}，正确选项为 {correct_answer}。'
            )
        else:
            question['verdict'] = 'uncertain'
            question['error_type'] = 'choice_slot_correct_answer_unresolved'
            question['error_detail'] = '已冻结学生括号选项，但正确选项尚未可靠确定。'

        after_restore = tuple(question.get(field) for field in protected_fields)
        if before_restore != after_restore:
            restored += 1
        guard['last_pre_restore_student_answer'] = previous_answer
        guard['last_pre_restore_verdict'] = previous_verdict
        guard['post_guard_verdict'] = question.get('verdict')
    return restored
