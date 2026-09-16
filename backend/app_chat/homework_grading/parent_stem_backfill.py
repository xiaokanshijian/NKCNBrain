"""Cross-page backfill of parent_stem_excerpt on Pass1 detect JSON files."""

import os
from typing import Any, Dict, List, Tuple

from app_chat.homework_grading.utils import parse_page_num, safe_json_dump, safe_json_load


def _iter_detect_json_files(pass1_dir: str) -> List[Tuple[int, str, Dict[str, Any]]]:
    if not os.path.isdir(pass1_dir):
        return []
    items: List[Tuple[int, str, Dict[str, Any]]] = []
    for name in os.listdir(pass1_dir):
        if not name.endswith('.detect.json'):
            continue
        path = os.path.join(pass1_dir, name)
        try:
            data = safe_json_load(path)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        page_num = int(data.get('page') or parse_page_num(name.replace('.detect.json', '.json')) or 0)
        if page_num <= 0:
            continue
        items.append((page_num, path, data))
    return sorted(items, key=lambda item: (item[0], item[1]))


def _collect_parent_stems(items: List[Tuple[int, str, Dict[str, Any]]]) -> Dict[str, str]:
    """Use the earliest page's non-empty parent_stem_excerpt for each parent_group_id."""
    stems: Dict[str, str] = {}
    for _page_num, _path, data in items:
        for question in data.get('questions') or []:
            if not isinstance(question, dict):
                continue
            group_id = str(question.get('parent_group_id') or '').strip()
            stem = str(question.get('parent_stem_excerpt') or '').strip()
            if group_id and stem and group_id not in stems:
                stems[group_id] = stem
    return stems


def backfill_parent_stems_in_detect_dir(pass1_dir: str) -> int:
    """Fill missing parent_stem_excerpt on later pages from earlier pages. Returns patch count."""
    items = _iter_detect_json_files(pass1_dir)
    if not items:
        return 0

    stems = _collect_parent_stems(items)
    if not stems:
        return 0

    patched = 0
    for _page_num, path, data in items:
        changed = False
        for question in data.get('questions') or []:
            if not isinstance(question, dict):
                continue
            group_id = str(question.get('parent_group_id') or '').strip()
            if not group_id or str(question.get('parent_stem_excerpt') or '').strip():
                continue
            donor = stems.get(group_id)
            if not donor:
                continue
            question['parent_stem_excerpt'] = donor
            patched += 1
            changed = True
        if changed:
            safe_json_dump(path, data)
    return patched
