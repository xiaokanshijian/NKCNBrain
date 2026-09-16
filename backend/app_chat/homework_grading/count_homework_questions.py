#!/usr/bin/env python
"""Count sub-questions (小题) per subject for homework grading runs.

Usage (from 本地backend):
  python -m app_chat.homework_grading.count_homework_questions

  python -m app_chat.homework_grading.count_homework_questions \\
      --base-dir "F:\\NKCNBrain\\djangoProject\\received_dir\\user_raw_file\\marklee_pigai\\continuous_image_dmt" \\
      --homework homework_7965e9e9cd0a homework_a96de3a8ba9d homework_644dcfb516b3
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app_chat.homework_grading.utils import (  # noqa: E402
    SUBJECT_LABELS,
    is_final_pass1_page_json,
    safe_json_load,
    sorted_json_pages,
)

DEFAULT_BASE_DIR = (
    r'F:\NKCNBrain\djangoProject\received_dir\user_raw_file\marklee_pigai'
    r'\continuous_image_dmt'
)
DEFAULT_HOMEWORK_IDS = (
    'homework_7965e9e9cd0a',
    'homework_a96de3a8ba9d',
    'homework_644dcfb516b3',
)


def _subject_from_filename(name: str) -> str:
    match = re.match(r'^(chinese|math|english|unknown)_', name)
    return match.group(1) if match else 'unknown'


def _load_manifest_subject(homework_root: str) -> str:
    manifest_path = os.path.join(homework_root, 'manifest.json')
    if not os.path.isfile(manifest_path):
        return ''
    try:
        manifest = safe_json_load(manifest_path)
    except (OSError, json.JSONDecodeError):
        return ''
    return str(manifest.get('subject') or manifest.get('homework_attributes', {}).get('homework_subject') or '').strip()


def count_homework_questions(homework_root: str) -> Dict[str, Any]:
    pass1_dir = os.path.join(homework_root, 'homework_grading', 'pass1_json')
    if not os.path.isdir(pass1_dir):
        raise FileNotFoundError(f'pass1_json not found: {pass1_dir}')

    manifest_subject = _load_manifest_subject(homework_root)
    by_subject: Dict[str, Dict[str, int]] = {}
    pages_by_subject: Dict[str, int] = {}
    total = 0
    page_files = sorted_json_pages(pass1_dir)

    for json_path in page_files:
        data = safe_json_load(json_path)
        filename = os.path.basename(json_path)
        subject = str(data.get('subject') or _subject_from_filename(filename) or manifest_subject or 'unknown').strip()
        questions = [q for q in data.get('questions') or [] if isinstance(q, dict)]
        count = len(questions)
        total += count
        bucket = by_subject.setdefault(subject, {'questions': 0, 'pages': 0})
        bucket['questions'] += count
        bucket['pages'] += 1
        pages_by_subject[subject] = pages_by_subject.get(subject, 0) + 1

    return {
        'homework_root': os.path.abspath(homework_root),
        'homework_id': os.path.basename(os.path.abspath(homework_root)),
        'manifest_subject': manifest_subject,
        'page_json_files': len(page_files),
        'total_questions': total,
        'by_subject': by_subject,
    }


def _print_report(results: List[Dict[str, Any]]) -> None:
    grand_by_subject: Dict[str, int] = {}
    print('=' * 72)
    print('Homework sub-question counts (pass1_json final page JSON)')
    print('=' * 72)

    for result in results:
        hid = result['homework_id']
        manifest_subject = result.get('manifest_subject') or '-'
        manifest_label = SUBJECT_LABELS.get(manifest_subject, manifest_subject)
        print(f"\n[{hid}]  manifest学科: {manifest_label} ({manifest_subject or '-'})")
        print(f"  路径: {result['homework_root']}")
        print(f"  页 JSON 文件: {result['page_json_files']}  小题总数: {result['total_questions']}")
        for subject, stats in sorted(result['by_subject'].items()):
            label = SUBJECT_LABELS.get(subject, subject)
            print(f"    - {label} ({subject}): {stats['questions']} 小题 / {stats['pages']} 页")
            grand_by_subject[subject] = grand_by_subject.get(subject, 0) + stats['questions']

    print('\n' + '-' * 72)
    print('三份作业合计（按学科）:')
    for subject in ('chinese', 'math', 'english', 'unknown'):
        if subject not in grand_by_subject:
            continue
        label = SUBJECT_LABELS.get(subject, subject)
        print(f"  {label}: {grand_by_subject[subject]} 小题")
    print(f"  全部合计: {sum(grand_by_subject.values())} 小题")
    print('=' * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description='Count homework sub-questions by subject.')
    parser.add_argument('--base-dir', default=DEFAULT_BASE_DIR, help='Parent directory containing homework_* folders')
    parser.add_argument(
        '--homework',
        nargs='+',
        default=list(DEFAULT_HOMEWORK_IDS),
        help='Homework folder names or absolute paths',
    )
    parser.add_argument('--json-out', default='', help='Optional path to write JSON summary')
    args = parser.parse_args()

    results: List[Dict[str, Any]] = []
    errors: List[str] = []
    for item in args.homework:
        homework_root = item if os.path.isabs(item) else os.path.join(args.base_dir, item)
        if not os.path.isdir(homework_root):
            errors.append(f'not found: {homework_root}')
            continue
        try:
            results.append(count_homework_questions(homework_root))
        except Exception as exc:
            errors.append(f'{homework_root}: {exc}')

    if not results:
        for msg in errors:
            print(f'ERROR: {msg}', file=sys.stderr)
        return 1

    _print_report(results)

    if errors:
        print('\nWarnings:', file=sys.stderr)
        for msg in errors:
            print(f'  - {msg}', file=sys.stderr)

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, 'w', encoding='utf-8') as file:
            json.dump({'results': results, 'errors': errors}, file, ensure_ascii=False, indent=2)
        print(f'\nJSON written: {args.json_out}')

    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
