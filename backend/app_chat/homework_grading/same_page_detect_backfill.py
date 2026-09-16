"""Same-page layout backfill for Pass1 detect JSON.

Handles double-column pages where a later sub-question appears far from its
parent stem on the same page, e.g. left-column ``11-1`` followed by right-column
``(2)`` detected as ``auto-*``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app_chat.homework_grading.parent_stem_backfill import _iter_detect_json_files
from app_chat.homework_grading.utils import safe_json_dump


_AUTO_ID_RE = re.compile(r'^auto-\d+$', re.I)
_SUB_QID_RE = re.compile(r'^(\d+)-(\d+)$')
_SUB_STEM_RE = re.compile(r'^[\s　]*[\(（]\s*(\d+)\s*[\)）]')


def _parse_qid(qid: Any) -> Optional[Tuple[str, int]]:
    match = _SUB_QID_RE.match(str(qid or '').strip())
    if not match:
        return None
    return match.group(1), int(match.group(2))


def _parse_stem_sub_index(stem: Any) -> Optional[int]:
    match = _SUB_STEM_RE.search(str(stem or '').strip())
    if not match:
        return None
    return int(match.group(1))


def _is_auto_id(qid: Any) -> bool:
    return bool(_AUTO_ID_RE.match(str(qid or '').strip()))


def _find_previous_anchor(
    previous_questions: List[Dict[str, Any]],
    sub_index: int,
) -> Optional[Dict[str, Any]]:
    expected_prev = sub_index - 1
    if expected_prev < 1:
        return None
    for question in reversed(previous_questions):
        parsed = _parse_qid(question.get('id'))
        if not parsed:
            continue
        group_id, prev_sub = parsed
        if prev_sub != expected_prev:
            continue
        parent_stem = str(question.get('parent_stem_excerpt') or '').strip()
        if parent_stem or str(question.get('parent_group_id') or '').strip() == group_id:
            return question
    return None


def _position(question: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    raw = question.get('position')
    if not isinstance(raw, list) or len(raw) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except (TypeError, ValueError):
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _reading_precedes(
    anchor: Dict[str, Any],
    question: Dict[str, Any],
) -> Optional[Tuple[int, float]]:
    """Return a sortable reading-order key when anchor appears before question."""
    anchor_pos = _position(anchor)
    question_pos = _position(question)
    if not anchor_pos or not question_pos:
        return None
    ax1, ay1, ax2, _ay2 = anchor_pos
    qx1, qy1, qx2, _qy2 = question_pos
    anchor_mid_x = (ax1 + ax2) / 2
    question_mid_x = (qx1 + qx2) / 2

    # In two-column pages, the lower end of the left column is read before the
    # top of the right column. This handles models that list right-column items
    # before the left-column parent stem.
    if ax2 <= qx1 - 20 or anchor_mid_x + 80 < question_mid_x:
        return 0, ay1

    # Same-column or overlapping boxes: normal top-to-bottom reading order.
    horizontally_overlaps = not (ax2 < qx1 - 20 or qx2 < ax1 - 20)
    if horizontally_overlaps and ay1 <= qy1:
        return 1, ay1

    return None


def _find_best_anchor(
    questions: List[Dict[str, Any]],
    current_index: int,
    sub_index: int,
) -> Optional[Dict[str, Any]]:
    expected_prev = sub_index - 1
    if expected_prev < 1:
        return None
    question = questions[current_index]
    candidates: List[Tuple[Tuple[int, float], Dict[str, Any]]] = []
    for index, anchor in enumerate(questions):
        if index == current_index or not isinstance(anchor, dict):
            continue
        parsed = _parse_qid(anchor.get('id'))
        if not parsed:
            continue
        group_id, prev_sub = parsed
        if prev_sub != expected_prev:
            continue
        parent_stem = str(anchor.get('parent_stem_excerpt') or '').strip()
        if not parent_stem and str(anchor.get('parent_group_id') or '').strip() != group_id:
            continue
        order_key = _reading_precedes(anchor, question)
        if order_key is not None:
            candidates.append((order_key, anchor))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]

    return _find_previous_anchor(questions[:current_index], sub_index)


def _candidate_needs_same_page_context(question: Dict[str, Any]) -> bool:
    qid = str(question.get('id') or '').strip()
    if _is_auto_id(qid):
        return True
    parsed = _parse_qid(qid)
    if not parsed:
        return False
    return not (
        str(question.get('parent_group_id') or '').strip()
        and str(question.get('parent_stem_excerpt') or '').strip()
    )


def _patch_question_from_anchor(
    question: Dict[str, Any],
    anchor: Dict[str, Any],
    sub_index: int,
    existing_ids: set,
) -> Tuple[int, int]:
    parsed = _parse_qid(anchor.get('id'))
    if not parsed:
        return 0, 0
    group_id = parsed[0]
    target_id = f'{group_id}-{sub_index}'
    id_patched = 0
    context_patched = 0

    if _is_auto_id(question.get('id')) or not _parse_qid(question.get('id')):
        current_id = str(question.get('id') or '').strip()
        if target_id not in existing_ids or target_id == current_id:
            if current_id:
                existing_ids.discard(current_id)
            question['id'] = target_id
            existing_ids.add(target_id)
            id_patched += 1

    if not str(question.get('parent_group_id') or '').strip():
        question['parent_group_id'] = group_id
        context_patched += 1

    if not str(question.get('parent_stem_excerpt') or '').strip():
        parent_stem = str(anchor.get('parent_stem_excerpt') or '').strip()
        if parent_stem:
            question['parent_stem_excerpt'] = parent_stem
            context_patched += 1

    return id_patched, context_patched


def backfill_same_page_detect_dir(pass1_dir: str) -> Dict[str, int]:
    """Patch same-page sub-question ids and parent context in detect JSON files."""
    items = _iter_detect_json_files(pass1_dir)
    stats = {
        'id_patched': 0,
        'context_patched': 0,
        'pages_written': 0,
    }
    if not items:
        return stats

    for _page_num, path, data in items:
        questions = data.get('questions') if isinstance(data.get('questions'), list) else []
        existing_ids = {
            str(question.get('id') or '').strip()
            for question in questions
            if isinstance(question, dict) and str(question.get('id') or '').strip()
        }
        changed = False
        for index, question in enumerate(questions):
            if not isinstance(question, dict):
                continue
            sub_index = _parse_stem_sub_index(question.get('stem_excerpt'))
            if sub_index is None:
                continue
            if not _candidate_needs_same_page_context(question):
                continue
            anchor = _find_best_anchor(questions, index, sub_index)
            if not anchor:
                continue
            id_count, context_count = _patch_question_from_anchor(question, anchor, sub_index, existing_ids)
            if id_count or context_count:
                stats['id_patched'] += id_count
                stats['context_patched'] += context_count
                changed = True
        if changed:
            safe_json_dump(path, data)
            stats['pages_written'] += 1
    return stats
