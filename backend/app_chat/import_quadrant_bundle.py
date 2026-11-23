#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 export_quadrant_bundle.py 导出的四象限结果写入目标本子。

只改：
  context_data.semantic_reorganize.quadrants
  context_data.semantic_reorganize.quadrant_meaning
  keywordFourColorDMT 里每个词的 quadrant / status / pending_faded
  cardCondense/bookKeywordQuadrants.json
  cardCondense/bookQuadrantMeaning.json

不改卡片、连边、四色、DMT、知识类型、温度计，也不重跑模型。
按 username 找本子，不按本地笔记本编号。

在 Backend 根目录执行：
  python app_chat/import_quadrant_bundle.py --username demo_notebook --bundle ./quadrants.txt --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import traceback
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
    _save_notebook_semantic_state,
)
from app_chat.semantic_source_v3_pipeline import (  # noqa: E402
    book_quadrant_meaning_path,
    book_quadrant_path,
)

BUNDLE_FORMAT = 'nkcn_quadrant_bundle_v1'
QUADRANTS = ('Q1', 'Q2', 'Q3', 'Q4')
PATCH_KEYS = ('quadrant', 'status', 'pending_faded')


def _resolve_bundle(path: str) -> str:
    if os.path.isfile(path):
        return os.path.abspath(path)
    for alt in (
        os.path.join(_BACKEND_ROOT, os.path.basename(path)),
        os.path.join(_BACKEND_ROOT, path),
    ):
        if os.path.isfile(alt):
            return os.path.abspath(alt)
    return ''


def _counts(quadrants: Dict[str, Any]) -> Dict[str, int]:
    counts = {q: 0 for q in QUADRANTS}
    other = 0
    for record in (quadrants or {}).values():
        if not isinstance(record, dict):
            other += 1
            continue
        q = str(record.get('quadrant') or '').strip().upper()
        if q in counts:
            counts[q] += 1
        else:
            other += 1
    counts['other'] = other
    counts['words'] = sum(counts[q] for q in QUADRANTS)
    return counts


def _load_bundle(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError('bundle 根节点必须是对象')
    if data.get('format') != BUNDLE_FORMAT:
        raise RuntimeError(f'format={data.get("format")!r}，期望 {BUNDLE_FORMAT}')
    meaning = data.get('quadrant_meaning')
    quadrants = data.get('quadrants')
    patch = data.get('keyword_patch')
    if not isinstance(meaning, dict) or not isinstance(quadrants, dict) or not isinstance(patch, dict):
        raise RuntimeError('bundle 缺少 quadrant_meaning / quadrants / keyword_patch')
    definitions = meaning.get('definitions') if isinstance(meaning.get('definitions'), dict) else {}
    missing = [q for q in QUADRANTS if not str(definitions.get(q) or '').strip()]
    if missing:
        raise RuntimeError(f'象限内涵缺段: {missing}')
    if not patch:
        raise RuntimeError('keyword_patch 为空')
    return data


def _apply_patch(server_map: Dict[str, Any], patch: Dict[str, Any]) -> int:
    changed = 0
    for word, item in patch.items():
        label = str(word or '').strip()
        if not label or not isinstance(item, dict):
            continue
        q = str(item.get('quadrant') or '').strip().upper()
        if q not in QUADRANTS:
            continue
        entry = dict(server_map.get(label) or {})
        before = {k: entry.get(k) for k in PATCH_KEYS}
        entry['quadrant'] = q
        status = str(item.get('status') or '').strip()
        if status in ('pending', 'confirmed', 'soft_pending'):
            entry['status'] = status
        if 'pending_faded' in item:
            entry['pending_faded'] = bool(item.get('pending_faded'))
        after = {k: entry.get(k) for k in PATCH_KEYS}
        if before != after or label not in server_map:
            changed += 1
        server_map[label] = entry
    return changed


def _write_json(path: str, data: Dict[str, Any]) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def _backup_file(path: str) -> None:
    if not os.path.isfile(path):
        return
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    bak = f'{path}.bak_before_quadrant_import_{stamp}'
    shutil.copy2(path, bak)
    print(f'[import-quadrant] 已备份 {bak}', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='导入已算好的四象限结果')
    parser.add_argument('--username', required=True)
    parser.add_argument('--scene-name', default='')
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    username = (args.username or '').strip()
    bundle_path = _resolve_bundle((args.bundle or '').strip())
    if not username:
        print('username 不能为空', flush=True)
        return 2
    if not bundle_path:
        print(f'找不到 bundle: {args.bundle}', flush=True)
        return 2

    try:
        bundle = _load_bundle(bundle_path)
    except Exception as exc:
        print(f'[import-quadrant] 读取失败: {exc}', flush=True)
        return 1

    notebook = _load_notebook(username, args.scene_name or None)
    if not notebook:
        print(f'未找到目标本子 username={username}', flush=True)
        return 2

    old_meta = _load_semantic_meta(notebook)
    old_counts = _counts(old_meta.get('quadrants') if isinstance(old_meta.get('quadrants'), dict) else {})
    new_counts = _counts(bundle['quadrants'])
    print(
        f'[import-quadrant] bundle={bundle_path}\n'
        f'  目标本子 id={notebook.id} username={username} bookName={notebook.bookName}\n'
        f'  服务器现有 Q1={old_counts["Q1"]} Q2={old_counts["Q2"]} '
        f'Q3={old_counts["Q3"]} Q4={old_counts["Q4"]}\n'
        f'  将写入   Q1={new_counts["Q1"]} Q2={new_counts["Q2"]} '
        f'Q3={new_counts["Q3"]} Q4={new_counts["Q4"]} words={new_counts["words"]}',
        flush=True,
    )
    fish = (bundle.get('keyword_patch') or {}).get('鱼嘴')
    print(f'  鱼嘴={fish}', flush=True)

    if args.dry_run:
        print('[import-quadrant] dry-run：不写库、不写文件', flush=True)
        return 0

    try:
        server_map: Dict[str, Any] = {}
        if notebook.keywordFourColorDMT:
            loaded = json.loads(notebook.keywordFourColorDMT)
            if isinstance(loaded, dict):
                server_map = loaded
        changed = _apply_patch(server_map, bundle['keyword_patch'])
        new_meta = dict(old_meta or {})
        new_meta['quadrants'] = bundle['quadrants']
        new_meta['quadrant_meaning'] = bundle['quadrant_meaning']
        _save_notebook_semantic_state(notebook, server_map, new_meta)

        q_path = book_quadrant_path(username)
        m_path = book_quadrant_meaning_path(username)
        _backup_file(q_path)
        _backup_file(m_path)
        _write_json(q_path, bundle['quadrants'])
        _write_json(m_path, bundle['quadrant_meaning'])
        print(
            f'[import-quadrant] 完成：词条象限字段写入 {changed} 个，'
            f'quadrants={new_counts["words"]}，内涵四段已写入。\n'
            f'  {q_path}\n  {m_path}',
            flush=True,
        )
        return 0
    except Exception as exc:
        traceback.print_exc()
        print(f'[import-quadrant] 写入失败: {exc}', flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
