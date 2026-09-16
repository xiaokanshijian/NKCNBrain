"""Cross-page post-processing on Pass1 detect JSON (after all pages finish stage A).

Aligns adjacent page boundaries, infers question ids for page-top continuations,
and backfills essential prior-page context (parent_group_id, parent_stem_excerpt)
from the previous page's *.detect.json so stage B can grade cross-page items
without missing stem context.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from app_chat.homework_grading.parent_stem_backfill import _iter_detect_json_files
from app_chat.homework_grading.utils import safe_json_dump


_AUTO_ID_RE = re.compile(r'^auto-\d+$', re.I)
_SUB_QID_RE = re.compile(r'^(\d+)-(\d+)$')
_BIG_QID_RE = re.compile(r'^(\d+)$')
_SECTION_QID_RE = re.compile(r'^[^\d].*')
_SUB_IN_TEXT_RE = [
    re.compile(r'第(\d+)小题'),
    re.compile(r'小题[\(（](\d+)[\)）]'),
    re.compile(r'[\(（](\d+)[\)）]'),
]


def _is_auto_id(qid: str) -> bool:
    return bool(_AUTO_ID_RE.match(str(qid or '').strip()))


def _plain_numeric_id(qid: str) -> bool:
    return bool(_BIG_QID_RE.match(str(qid or '').strip()))


def _prev_page_continues_with_sub_anchor(prev_data: Dict[str, Any]) -> bool:
    boundary = prev_data.get('boundary') or {}
    if not boundary.get('continues_to_next'):
        return False
    anchor = _prev_page_anchor(prev_data)
    if not anchor:
        return False
    parsed = _parse_question_id(str(anchor.get('id') or ''))
    return parsed is not None and parsed[1] is not None


def _is_new_section_question(question: Dict[str, Any], continuation_group_id: str) -> bool:
    qid = str(question.get('id') or '').strip()
    parent_gid = str(question.get('parent_group_id') or '').strip()
    if parent_gid and continuation_group_id and parent_gid != continuation_group_id:
        return True
    if _SECTION_QID_RE.match(qid):
        return True
    stem = str(question.get('stem_excerpt') or '').strip()
    if re.match(r'^[一二三四五六七八九十百千]+、', stem):
        return True
    return False


def _is_continuation_question(
    question: Dict[str, Any],
    *,
    plain_numeric_mode: bool,
) -> bool:
    qid = str(question.get('id') or '').strip()
    if question.get('cross_page') or _is_auto_id(qid):
        return True
    parsed = _parse_question_id(qid)
    if parsed and parsed[1] is not None:
        return True
    if plain_numeric_mode and _plain_numeric_id(qid):
        return True
    return False


def _parse_question_id(qid: str) -> Optional[Tuple[str, Optional[int]]]:
    text = str(qid or '').strip()
    match = _SUB_QID_RE.match(text)
    if match:
        return match.group(1), int(match.group(2))
    match = _BIG_QID_RE.match(text)
    if match:
        return match.group(1), None
    return None


def _parse_sub_index(text: str) -> Optional[int]:
    for pattern in _SUB_IN_TEXT_RE:
        match = pattern.search(str(text or ''))
        if match:
            return int(match.group(1))
    return None


def _big_question_header(parent_stem: str, group_id: str) -> str:
    stem = str(parent_stem or '').strip()
    if not stem:
        return f'{group_id}.' if group_id else ''
    match = re.match(r'^(\d+\.\s*[^(\(]+(?:[。\.]|$))', stem)
    if match:
        return match.group(1).strip()
    for sep in (' (1)', '（1）', '(1)', ' (2)', '（2）', '(2)'):
        if sep in stem:
            return stem.split(sep)[0].strip()
    return stem


def _default_boundary() -> Dict[str, Any]:
    return {
        'continues_from_prev': False,
        'description_prev': None,
        'continues_to_next': False,
        'description_next': None,
    }


def _align_boundaries(items: List[Tuple[int, str, Dict[str, Any]]]) -> int:
    by_page = {page: data for page, _path, data in items}
    patched = 0
    for page_num in sorted(by_page):
        if page_num <= 1:
            continue
        curr = by_page[page_num]
        prev = by_page.get(page_num - 1)
        if not prev:
            continue
        cb = curr.setdefault('boundary', _default_boundary())
        pb = prev.setdefault('boundary', _default_boundary())

        if cb.get('continues_from_prev') and not pb.get('continues_to_next'):
            pb['continues_to_next'] = True
            if cb.get('description_prev') and not pb.get('description_next'):
                pb['description_next'] = f'下页延续：{cb["description_prev"]}'
            patched += 1

        if pb.get('continues_to_next') and not cb.get('continues_from_prev'):
            cb['continues_from_prev'] = True
            if pb.get('description_next') and not cb.get('description_prev'):
                cb['description_prev'] = f'上页延续：{pb["description_next"]}'
            patched += 1
    return patched


def _prev_page_anchor(prev_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    questions = prev_data.get('questions') or []
    for question in reversed(questions):
        if isinstance(question, dict):
            return question
    return None


def _max_sub_in_group(prev_data: Dict[str, Any], group_id: str) -> int:
    max_sub = 0
    for question in prev_data.get('questions') or []:
        if not isinstance(question, dict):
            continue
        if str(question.get('parent_group_id') or '').strip() != group_id:
            continue
        parsed = _parse_question_id(str(question.get('id') or ''))
        if parsed and parsed[1] is not None:
            max_sub = max(max_sub, parsed[1])
    return max_sub


def _group_parent_stem(prev_data: Dict[str, Any], group_id: str) -> str:
    for question in prev_data.get('questions') or []:
        if not isinstance(question, dict):
            continue
        q_group = str(question.get('parent_group_id') or '').strip()
        if q_group == group_id:
            stem = _big_question_header(str(question.get('parent_stem_excerpt') or ''), group_id)
            if stem:
                return stem
        parsed = _parse_question_id(str(question.get('id') or ''))
        if parsed and parsed[0] == group_id:
            parent_stem = str(question.get('parent_stem_excerpt') or '').strip()
            if parent_stem:
                return _big_question_header(parent_stem, group_id)
            stem_excerpt = str(question.get('stem_excerpt') or '').strip()
            if stem_excerpt and re.match(r'^\d+\.', stem_excerpt):
                return _big_question_header(stem_excerpt, group_id)
    return f'{group_id}.' if group_id else ''


def _infer_group_id(prev_data: Dict[str, Any], anchor: Optional[Dict[str, Any]]) -> str:
    if not anchor:
        return ''
    group_id = str(anchor.get('parent_group_id') or '').strip()
    if group_id:
        return group_id
    parsed = _parse_question_id(str(anchor.get('id') or ''))
    if parsed:
        return parsed[0]
    return ''


def _iter_leading_continuation_questions(
    questions: List[Any],
    boundary: Dict[str, Any],
    prev_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if not boundary.get('continues_from_prev'):
        return [
            q for q in questions
            if isinstance(q, dict) and (q.get('cross_page') or _is_auto_id(str(q.get('id') or '')))
        ]

    continuation_group_id = ''
    plain_numeric_mode = True
    if prev_data and _prev_page_continues_with_sub_anchor(prev_data):
        anchor = _prev_page_anchor(prev_data)
        continuation_group_id = _infer_group_id(prev_data, anchor)

    leading: List[Dict[str, Any]] = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        if leading and _is_new_section_question(question, continuation_group_id):
            break
        if not _is_continuation_question(question, plain_numeric_mode=plain_numeric_mode):
            break
        leading.append(question)
    return leading


def _mark_cross_page_leading(prev_data: Dict[str, Any], data: Dict[str, Any]) -> int:
    boundary = data.setdefault('boundary', _default_boundary())
    if not boundary.get('continues_from_prev'):
        return 0
    leading = _iter_leading_continuation_questions(
        data.get('questions') or [],
        boundary,
        prev_data,
    )
    patched = 0
    for question in leading:
        if not question.get('cross_page'):
            question['cross_page'] = True
            patched += 1
    return patched


def _ensure_sub_prefix(stem_excerpt: str, sub_index: int) -> str:
    stem = str(stem_excerpt or '').strip()
    if not stem:
        return stem
    if re.match(r'^[\(（]\d+[\)）]', stem):
        return stem
    return f'({sub_index}) {stem}'


def _fill_parent_context(
    prev_data: Dict[str, Any],
    question: Dict[str, Any],
    group_id: str,
    sub_index: Optional[int] = None,
) -> bool:
    changed = False
    if group_id and not str(question.get('parent_group_id') or '').strip():
        question['parent_group_id'] = group_id
        changed = True
    if group_id and not str(question.get('parent_stem_excerpt') or '').strip():
        donor = _group_parent_stem(prev_data, group_id)
        if donor:
            question['parent_stem_excerpt'] = donor
            changed = True
    if sub_index is not None and question.get('cross_page'):
        new_stem = _ensure_sub_prefix(str(question.get('stem_excerpt') or ''), sub_index)
        if new_stem != str(question.get('stem_excerpt') or ''):
            question['stem_excerpt'] = new_stem
            changed = True
    return changed


def _mark_context_ready(question: Dict[str, Any]) -> bool:
    qid = str(question.get('id') or '')
    if _is_auto_id(qid):
        return False
    stem = str(question.get('stem_excerpt') or '').strip()
    if not stem:
        return False
    parsed = _parse_question_id(qid)
    if parsed and parsed[1] is not None:
        parent = str(question.get('parent_group_id') or '').strip()
        parent_stem = str(question.get('parent_stem_excerpt') or '').strip()
        if not parent or not parent_stem:
            return False
    question['cross_page_context_ready'] = True
    note = str(question.get('cross_page_note') or '')
    if note in ('跨页题目，单页上下文不足', '跨页题目，单页上下文不足。'):
        question['cross_page_note'] = None
    return True


def _backfill_page_from_prev(
    prev_data: Dict[str, Any],
    data: Dict[str, Any],
) -> Tuple[int, int]:
    boundary = data.setdefault('boundary', _default_boundary())
    questions = data.get('questions') or []
    leading = _iter_leading_continuation_questions(questions, boundary, prev_data)
    if not leading:
        return 0, 0

    anchor = _prev_page_anchor(prev_data)
    group_id = _infer_group_id(prev_data, anchor)
    description = str(boundary.get('description_prev') or '')
    start_sub = _parse_sub_index(description)
    if start_sub is None and anchor:
        parsed = _parse_question_id(str(anchor.get('id') or ''))
        if parsed and parsed[1] is not None:
            start_sub = parsed[1] + 1
        elif group_id:
            max_sub = _max_sub_in_group(prev_data, group_id)
            start_sub = max_sub + 1 if max_sub else 1

    id_patched = 0
    context_patched = 0
    next_sub = start_sub

    for question in leading:
        qid = str(question.get('id') or '')
        parsed = _parse_question_id(qid)
        sub_index = parsed[1] if parsed else next_sub

        if _is_auto_id(qid) and group_id and next_sub is not None:
            question['id'] = f'{group_id}-{next_sub}'
            sub_index = next_sub
            next_sub += 1
            id_patched += 1
        elif parsed and parsed[1] is not None:
            sub_index = parsed[1]
            if start_sub is not None:
                next_sub = max(next_sub or 0, parsed[1] + 1)
        elif (
            group_id
            and next_sub is not None
            and parsed
            and parsed[1] is None
            and _plain_numeric_id(qid)
        ):
            question['id'] = f'{group_id}-{next_sub}'
            sub_index = next_sub
            next_sub += 1
            id_patched += 1
        elif group_id and next_sub is not None and not parsed:
            question['id'] = f'{group_id}-{next_sub}'
            sub_index = next_sub
            next_sub += 1
            id_patched += 1

        effective_group = group_id or (parsed[0] if parsed else '')
        if _fill_parent_context(prev_data, question, effective_group, sub_index):
            context_patched += 1
        if _mark_context_ready(question):
            context_patched += 1

    return id_patched, context_patched


def backfill_cross_page_detect_dir(pass1_dir: str) -> Dict[str, int]:
    """Run cross-page detect backfill. Returns counters for logging."""
    items = _iter_detect_json_files(pass1_dir)
    stats = {
        'boundary_patched': 0,
        'cross_page_patched': 0,
        'id_patched': 0,
        'context_patched': 0,
        'pages_written': 0,
    }
    if not items:
        return stats

    stats['boundary_patched'] = _align_boundaries(items)

    by_page = {page: (path, data) for page, path, data in items}
    dirty_paths: set = set()

    for page_num in sorted(by_page):
        if page_num <= 1:
            continue
        prev_entry = by_page.get(page_num - 1)
        if not prev_entry:
            continue
        path, data = by_page[page_num]
        prev_data = prev_entry[1]
        cross_page_patched = _mark_cross_page_leading(prev_data, data)
        if cross_page_patched:
            stats['cross_page_patched'] += cross_page_patched
            dirty_paths.add(path)
        id_patched, context_patched = _backfill_page_from_prev(prev_data, data)
        if id_patched or context_patched:
            stats['id_patched'] += id_patched
            stats['context_patched'] += context_patched
            dirty_paths.add(path)

    if stats['boundary_patched']:
        dirty_paths.update(path for path, _data in by_page.values())

    stats['pages_written'] = 0
    for path in dirty_paths:
        for _page, item_path, data in items:
            if item_path == path:
                safe_json_dump(path, data)
                stats['pages_written'] += 1
                break

    return stats
