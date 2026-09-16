"""Default-off math shadow layout splitting and U1 faithful transcription."""
from __future__ import annotations

import os
import re
import tempfile
from typing import Any, Dict, List, Set, Tuple

from app_chat.homework_grading.grader_pass1 import _call_qwen_json_with_retry
from app_chat.homework_grading.prompts import (
    PASS1_U1_LAYOUT_SPLIT_SYSTEM,
    pass1_u1_layout_candidate_system,
    pass1_u1_layout_candidate_user_prompt,
    pass1_u1_layout_split_user_prompt,
    pass1_u1_shadow_system,
    pass1_u1_shadow_user_prompt,
)
from app_chat.homework_grading.utils import (
    image_to_data_uri,
    normalize_position,
    safe_json_dump,
)


U1_QUESTION_KEYS = ('id', 'student_answer', 'recognition_confidence')
LAYOUT_QUESTION_KEYS = (
    'id', 'parent_group_id', 'parent_stem_excerpt', 'stem_excerpt', 'position',
    'cross_page', 'cross_page_note', 'is_application_major_problem', 'layout_confidence',
)


def u1_shadow_enabled(subject: str, *, feedback_runtime=None) -> bool:
    from .feedback_runtime import frozen_environment
    if feedback_runtime is not None and not feedback_runtime.has_specialized('math'):
        return False
    raw = frozen_environment(feedback_runtime, 'HOMEWORK_PASS1_U1_SHADOW', '0').strip().lower()
    return subject == 'math' and raw in ('1', 'true', 'yes', 'on')


def _confidence(value: Any) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def comparison_text(value: Any) -> str:
    """Conservative audit-only normalization: Unicode width plus whitespace."""
    chars = []
    for char in str(value or ''):
        codepoint = ord(char)
        if codepoint == 0x3000:
            chars.append(' ')
        elif 0xFF01 <= codepoint <= 0xFF5E:
            chars.append(chr(codepoint - 0xFEE0))
        else:
            chars.append(char)
    return ''.join(''.join(chars).split())


def _layout_question(question: Dict[str, Any]) -> Dict[str, Any]:
    item = {
        'id': str(question.get('id') or '').strip(),
        'parent_group_id': str(question.get('parent_group_id') or '').strip(),
        'parent_stem_excerpt': str(question.get('parent_stem_excerpt') or '').strip(),
        'stem_excerpt': str(question.get('stem_excerpt') or '').strip(),
        'position': normalize_position(question.get('position')),
        'cross_page': bool(question.get('cross_page')),
        'cross_page_note': question.get('cross_page_note') or None,
        'is_application_major_problem': bool(question.get('is_application_major_problem')),
        'layout_confidence': _confidence(question.get('layout_confidence')),
    }
    return {key: item[key] for key in LAYOUT_QUESTION_KEYS}


def _crop_parent(image_path: str, position: Any) -> str:
    normalized = normalize_position(position)
    if not normalized:
        raise ValueError('父题 bbox 无效')
    from PIL import Image  # noqa: PLC0415

    image = Image.open(image_path)
    try:
        width, height = image.size
        x1, y1, x2, y2 = normalized
        box = (
            max(0, int(x1 / 1000.0 * width)),
            max(0, int(y1 / 1000.0 * height)),
            min(width, int(x2 / 1000.0 * width + 0.999)),
            min(height, int(y2 / 1000.0 * height + 0.999)),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError('父题 crop 尺寸无效')
        crop = image.crop(box)
    finally:
        image.close()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    tmp_path = tmp.name
    tmp.close()
    try:
        crop.save(tmp_path)
    finally:
        crop.close()
    return tmp_path


def _strict_crop_position(position: Any) -> List[float]:
    if not isinstance(position, list) or len(position) != 4:
        return []
    try:
        values = [float(value) for value in position]
    except (TypeError, ValueError):
        return []
    if any(value < 0 or value > 1000 for value in values):
        return []
    x1, y1, x2, y2 = values
    return values if x2 > x1 and y2 > y1 else []


def _normalize_split_children(parent: Dict[str, Any], result: Dict[str, Any]) -> List[Dict[str, Any]]:
    parent_id = str(parent.get('id') or '').strip()
    parent_position = normalize_position(parent.get('position'))
    if not parent_id or not parent_position:
        raise ValueError('父题 id 或 bbox 无效')

    parsed: List[Tuple[int, Dict[str, Any], List[float]]] = []
    for raw_child in result.get('questions') or []:
        if not isinstance(raw_child, dict):
            continue
        child_id = str(raw_child.get('id') or '').strip()
        match = re.fullmatch(rf'{re.escape(parent_id)}-(\d+)', child_id)
        crop_position = _strict_crop_position(raw_child.get('position'))
        if not match or not crop_position:
            continue
        parsed.append((int(match.group(1)), raw_child, crop_position))
    parsed.sort(key=lambda item: item[0])
    if len(parsed) < 2 or [item[0] for item in parsed] != list(range(1, len(parsed) + 1)):
        raise ValueError('子题 id 必须从 1 开始连续且至少包含两个子题')

    px1, py1, px2, py2 = parent_position
    parent_width, parent_height = px2 - px1, py2 - py1
    children: List[Dict[str, Any]] = []
    for _index, raw_child, crop_position in parsed:
        cx1, cy1, cx2, cy2 = crop_position
        child = _layout_question({
            'id': raw_child.get('id'),
            'parent_group_id': parent_id,
            'parent_stem_excerpt': (
                raw_child.get('parent_stem_excerpt')
                or parent.get('parent_stem_excerpt')
                or parent.get('stem_excerpt')
                or ''
            ),
            'stem_excerpt': raw_child.get('stem_excerpt') or '',
            'position': [
                px1 + cx1 * parent_width / 1000.0,
                py1 + cy1 * parent_height / 1000.0,
                px1 + cx2 * parent_width / 1000.0,
                py1 + cy2 * parent_height / 1000.0,
            ],
            'cross_page': parent.get('cross_page'),
            'cross_page_note': parent.get('cross_page_note'),
            'is_application_major_problem': parent.get('is_application_major_problem'),
            'layout_confidence': raw_child.get('layout_confidence'),
        })
        if not child['position']:
            raise ValueError(f'子题 {child["id"]} bbox 越界或无效')
        children.append(child)
    return children


def run_u1_shadow_layout_page(
    image_path: str,
    subject: str,
    page_num: int,
    detected: Dict[str, Any],
    out_json_path: str,
    *, feedback_runtime=None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Classify and split multi-item parents without changing formal detect."""
    from .feedback_runtime import stamp_feedback
    if feedback_runtime is not None and not feedback_runtime.has_specialized('math'):
        return stamp_feedback({'page': page_num, 'questions': [], 'status': 'not_covered'}, feedback_runtime), {'status': 'not_covered'}
    error_path = out_json_path.replace('.layout.json', '.layout.error.txt')
    errors: List[str] = []
    formal_questions = [
        _layout_question(item) for item in detected.get('questions') or []
        if isinstance(item, dict) and str(item.get('id') or '').strip()
    ]
    candidate_ids: Set[str] = set()
    try:
        candidate_result, _message = _call_qwen_json_with_retry(
            [
                {'role': 'system', 'content': pass1_u1_layout_candidate_system()},
                {
                    'role': 'user',
                    'content': [
                        {'type': 'image_url', 'image_url': {'url': image_to_data_uri(image_path)}},
                        {'type': 'text', 'text': pass1_u1_layout_candidate_user_prompt(page_num, detected)},
                    ],
                },
            ],
            {'enable_thinking': False},
            stage_label='Pass 1 U1影子多小题候选识别',
            require_questions=True,
            error_dump_path=error_path,
            temperature=0.0,
            feedback_runtime=feedback_runtime,
        )
        formal_ids = {item['id'] for item in formal_questions}
        candidate_ids = {
            str(item.get('id') or '').strip()
            for item in candidate_result.get('questions') or []
            if isinstance(item, dict)
            and item.get('multi_item') is True
            and str(item.get('id') or '').strip() in formal_ids
            and not re.search(r'-\d+$', str(item.get('id') or '').strip())
        }
    except Exception as exc:
        errors.append(f'候选识别失败: {exc}')

    output: List[Dict[str, Any]] = []
    split_parents: List[str] = []
    fallback_parents: List[str] = []
    for parent in formal_questions:
        parent_id = parent['id']
        if parent_id not in candidate_ids:
            output.append(parent)
            continue
        crop_path = ''
        try:
            crop_path = _crop_parent(image_path, parent['position'])
            split_result, _message = _call_qwen_json_with_retry(
                [
                    {'role': 'system', 'content': PASS1_U1_LAYOUT_SPLIT_SYSTEM},
                    {
                        'role': 'user',
                        'content': [
                            {'type': 'image_url', 'image_url': {'url': image_to_data_uri(crop_path)}},
                            {'type': 'text', 'text': pass1_u1_layout_split_user_prompt(page_num, parent)},
                        ],
                    },
                ],
                {'enable_thinking': False},
                stage_label='Pass 1 U1影子多小题拆分',
                require_questions=True,
                error_dump_path=error_path,
                temperature=0.0,
                feedback_runtime=feedback_runtime,
            )
            children = _normalize_split_children(parent, split_result)
            output.extend(children)
            split_parents.append(parent_id)
        except Exception as exc:
            output.append(parent)
            fallback_parents.append(parent_id)
            errors.append(f'{parent_id} 拆分失败: {exc}')
        finally:
            if crop_path and os.path.isfile(crop_path):
                os.remove(crop_path)

    layout = {'page': page_num, 'subject': subject, 'questions': output}
    safe_json_dump(out_json_path, stamp_feedback(layout, feedback_runtime, 'u1_layout'))
    if errors:
        with open(error_path, 'w', encoding='utf-8') as file:
            file.write('\n'.join(errors))
    elif os.path.isfile(error_path):
        os.remove(error_path)
    metadata = {
        'candidate_ids': sorted(candidate_ids),
        'split_parent_ids': split_parents,
        'fallback_parent_ids': fallback_parents,
        'child_count': sum(1 for item in output if item.get('parent_group_id') in split_parents),
        'errors': errors,
    }
    return layout, metadata


def normalize_u1_result(
    result: Dict[str, Any],
    detected: Dict[str, Any],
    subject: str,
    page_num: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
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
    for detected_question in detected.get('questions') or []:
        if not isinstance(detected_question, dict):
            continue
        qid = str(detected_question.get('id') or '').strip()
        if not qid:
            continue
        expected_ids.append(qid)
        source = by_id.get(qid) or {}
        questions.append({
            'id': qid,
            'student_answer': str(source.get('student_answer') or '').strip(),
            'recognition_confidence': _confidence(source.get('recognition_confidence')),
        })

    expected_set = set(expected_ids)
    page_result = {'page': page_num, 'subject': subject, 'questions': questions}
    metadata = {
        'expected_ids': expected_ids,
        'returned_ids': sorted(returned_ids & expected_set),
        'missing_ids': [qid for qid in expected_ids if qid not in returned_ids],
        'extra_ids': sorted(returned_ids - expected_set),
    }
    return page_result, metadata


def run_u1_shadow_page(
    image_path: str,
    subject: str,
    page_num: int,
    detected: Dict[str, Any],
    out_json_path: str,
    *, feedback_runtime=None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    from .feedback_runtime import stamp_feedback
    if feedback_runtime is not None and not feedback_runtime.has_specialized('math'):
        return stamp_feedback({'page': page_num, 'questions': [], 'status': 'not_covered'}, feedback_runtime), {'status': 'not_covered'}
    result, _message = _call_qwen_json_with_retry(
        [
            {'role': 'system', 'content': pass1_u1_shadow_system()},
            {
                'role': 'user',
                'content': [
                    {'type': 'image_url', 'image_url': {'url': image_to_data_uri(image_path)}},
                    {'type': 'text', 'text': pass1_u1_shadow_user_prompt(page_num, detected)},
                ],
            },
        ],
        {'enable_thinking': False},
        stage_label='Pass 1 U1纯转写',
        require_questions=True,
        error_dump_path=out_json_path.replace('.u1.json', '.u1.error.txt'),
        temperature=0.0,
        feedback_runtime=feedback_runtime,
    )
    normalized, metadata = normalize_u1_result(result, detected, subject, page_num)
    safe_json_dump(out_json_path, stamp_feedback(normalized, feedback_runtime, 'u1_transcription'))
    return normalized, metadata
