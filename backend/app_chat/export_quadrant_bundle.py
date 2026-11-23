#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""导出本子已经算好的四象限结果，不重新跑模型。

只含：
  quadrant_meaning  四段内涵
  quadrants         每个词的象限记录（含虚线待定）
  keyword_patch     每个词只带 quadrant / status / pending_faded

在 Backend 根目录执行：
  python app_chat/export_quadrant_bundle.py --username demo_notebook --output ./quadrants.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')

import django  # noqa: E402

django.setup()

from app_chat.semantic_keyword_service import (  # noqa: E402
    _load_notebook,
    _load_semantic_meta,
)
from app_chat.semantic_source_v3_pipeline import (  # noqa: E402
    book_quadrant_meaning_path,
    book_quadrant_path,
)

BUNDLE_FORMAT = 'nkcn_quadrant_bundle_v1'
QUADRANTS = ('Q1', 'Q2', 'Q3', 'Q4')
PATCH_STATUSES = ('pending', 'confirmed', 'soft_pending')


def _read_json(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _keyword_map(notebook) -> Dict[str, Any]:
    raw = (notebook.keywordFourColorDMT or '').strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _status_of(entry: Dict[str, Any], record: Dict[str, Any]) -> str:
    status = str(entry.get('status') or '').strip()
    if status in PATCH_STATUSES:
        return status
    if record.get('pending_faded'):
        return 'soft_pending'
    if record.get('pending'):
        return 'pending'
    return 'confirmed'


def build_bundle(username: str, scene_name: str = '') -> Dict[str, Any]:
    notebook = _load_notebook(username, scene_name or None)
    if not notebook:
        raise RuntimeError(f'未找到本子 username={username}')

    meta = _load_semantic_meta(notebook)
    quadrants = meta.get('quadrants') if isinstance(meta.get('quadrants'), dict) else {}
    if not quadrants:
        quadrants = _read_json(book_quadrant_path(username))
    meaning = meta.get('quadrant_meaning') if isinstance(meta.get('quadrant_meaning'), dict) else {}
    if not meaning:
        meaning = _read_json(book_quadrant_meaning_path(username))
    if not quadrants:
        raise RuntimeError('本子里没有 quadrants')
    if not meaning:
        raise RuntimeError('本子里没有 quadrant_meaning')

    kw_map = _keyword_map(notebook)
    keyword_patch: Dict[str, Dict[str, Any]] = {}
    counts = {q: 0 for q in QUADRANTS}
    bad = []
    for word, record in quadrants.items():
        label = str(word or '').strip()
        if not label or not isinstance(record, dict):
            continue
        q = str(record.get('quadrant') or '').strip().upper()
        entry = kw_map.get(label) if isinstance(kw_map.get(label), dict) else {}
        if q not in QUADRANTS:
            stored = str(entry.get('quadrant') or '').strip().upper()
            q = stored if stored in QUADRANTS else ''
        if q not in QUADRANTS:
            bad.append(label)
            continue
        counts[q] += 1
        faded = bool(entry.get('pending_faded')) if 'pending_faded' in entry else bool(record.get('pending_faded'))
        keyword_patch[label] = {
            'quadrant': q,
            'status': _status_of(entry, record),
            'pending_faded': faded,
        }

    definitions = meaning.get('definitions') if isinstance(meaning.get('definitions'), dict) else {}
    missing_def = [q for q in QUADRANTS if not str(definitions.get(q) or '').strip()]
    if missing_def:
        raise RuntimeError(f'象限内涵缺段: {missing_def}')
    if bad:
        raise RuntimeError(f'有词没有合法象限，示例={bad[:8]}')
    if not keyword_patch:
        raise RuntimeError('没有可导出的词')

    total = sum(counts.values())
    return {
        'format': BUNDLE_FORMAT,
        'exported_at': datetime.now().isoformat(timespec='seconds'),
        'source_username': username,
        'notebook_id': notebook.id,
        'quadrant_meaning': meaning,
        'quadrants': quadrants,
        'keyword_patch': keyword_patch,
        'stats': {
            'words': total,
            'Q1': counts['Q1'],
            'Q2': counts['Q2'],
            'Q3': counts['Q3'],
            'Q4': counts['Q4'],
            'pending_faded': sum(1 for item in keyword_patch.values() if item.get('pending_faded')),
            'fish_mouth': keyword_patch.get('鱼嘴'),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='导出已算好的四象限结果')
    parser.add_argument('--username', required=True)
    parser.add_argument('--scene-name', default='')
    parser.add_argument('-o', '--output', default='')
    args = parser.parse_args()
    username = (args.username or '').strip()
    if not username:
        print('username 不能为空', flush=True)
        return 2

    out = (args.output or '').strip() or os.path.join(
        _BACKEND_ROOT, f'{username}_quadrant_bundle.txt'
    )
    try:
        bundle = build_bundle(username, args.scene_name or '')
    except Exception as exc:
        print(f'[export-quadrant] 失败: {exc}', flush=True)
        return 1

    out_abs = os.path.abspath(out)
    out_dir = os.path.dirname(out_abs)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_abs, 'w', encoding='utf-8') as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
        f.write('\n')

    st = bundle['stats']
    print(
        f'[export-quadrant] 成功 → {out_abs}\n'
        f'  words={st["words"]} Q1={st["Q1"]} Q2={st["Q2"]} Q3={st["Q3"]} Q4={st["Q4"]} '
        f'pending_faded={st["pending_faded"]} 鱼嘴={st["fish_mouth"]}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
