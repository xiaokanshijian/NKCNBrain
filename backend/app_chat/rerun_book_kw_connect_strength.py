#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""仅补做本子语义关键词层次连边的「连接强度」（强 / 强中 / 普通）。

不重算连边拓扑：读取已有 bookKWConnect.txt 的父子对，调用模型只打强度。
漏标的边默认「普通」，并 print 漏标数量与样例。

默认本子：marklee_DuJiangYan

在 本地backend 目录下执行：
  python app_chat/rerun_book_kw_connect_strength.py
  python app_chat/rerun_book_kw_connect_strength.py --username marklee_DuJiangYan
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from typing import Any, Dict, List

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
from app_chat.semantic_reorganize_pipeline import (  # noqa: E402
    LINK_STRENGTH_MID,
    LINK_STRENGTH_NORMAL,
    LINK_STRENGTH_STRONG,
    book_key_issue_path,
    book_kw_connect_path,
    card_condense_dir,
    load_card_rows_by_cids,
    load_hierarchy_link_pairs_from_file,
    run_hierarchy_link_strength_fill,
)

DEFAULT_USERNAME = 'marklee_DuJiangYan'


def _selected_cids_from_meta(meta: Dict[str, Any]) -> List[int]:
    selected = [int(x) for x in (meta.get('reorganize_selected_cids') or [])]
    if selected:
        return selected
    if meta.get('pipeline') == 'v2_condense_hierarchy' and meta.get('sampled'):
        return [int(x) for x in (meta.get('processed_cids') or [])]
    return [int(x) for x in (meta.get('processed_cids') or [])]


def _selected_cids_from_condense_dir(username: str) -> List[int]:
    d = card_condense_dir(username)
    if not os.path.isdir(d):
        return []
    cids: List[int] = []
    for name in os.listdir(d):
        if name.endswith('.txt') and name[:-4].isdigit():
            cids.append(int(name[:-4]))
    return sorted(cids)


def _load_book_key_issues(username: str) -> str:
    path = book_key_issue_path(username)
    if not os.path.isfile(path):
        return ''
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return ''


def main() -> int:
    parser = argparse.ArgumentParser(description='仅补做层次连边连接强度（强/强中/普通）')
    parser.add_argument('--username', default=DEFAULT_USERNAME)
    parser.add_argument('--scene-name', default='')
    parser.add_argument('--dry-run', action='store_true', help='只分析不写 notebook meta（仍会写 bookKWConnect.txt）')
    args = parser.parse_args()
    username = (args.username or '').strip()
    if not username:
        print('username 不能为空', flush=True)
        return 2

    notebook = _load_notebook(username, args.scene_name or None)
    if not notebook:
        print(f'未找到本子 username={username}', flush=True)
        return 2

    meta = _load_semantic_meta(notebook)
    selected = _selected_cids_from_meta(meta)
    if not selected:
        selected = _selected_cids_from_condense_dir(username)
    if not selected:
        print('无选中卡片（reorganize_selected_cids / cardCondense），无法补强度', flush=True)
        return 2

    connect_path = book_kw_connect_path(username)
    if not os.path.isfile(connect_path):
        print(f'找不到已有连边文件: {connect_path}', flush=True)
        return 2

    existing = load_hierarchy_link_pairs_from_file(username)
    if not existing:
        print(f'连边文件为空或无法解析: {connect_path}', flush=True)
        return 2

    notebook_desc = (notebook.bookdescription or '') if notebook else ''
    issues = _load_book_key_issues(username)
    card_rows = load_card_rows_by_cids(username, selected)
    if not card_rows:
        print(f'未加载到卡片 rows，selected={len(selected)}', flush=True)
        return 2

    print(
        f'[rerun_connect_strength] username={username} selected_cards={len(selected)} '
        f'existing_links={len(existing)} rows={len(card_rows)} desc_len={len(notebook_desc)}',
        flush=True,
    )
    print(f'[rerun_connect_strength] 将写回 {connect_path}', flush=True)

    try:
        links, missing = run_hierarchy_link_strength_fill(
            username=username,
            notebook_description=notebook_desc,
            book_key_issues=issues,
            card_rows=card_rows,
            existing_links=existing,
            track_fn=None,
            is_running_fn=None,
        )
    except Exception as exc:
        traceback.print_exc()
        print(f'[rerun_connect_strength] 失败: {exc}', flush=True)
        return 1

    strong = sum(1 for _a, _b, s in links if s == LINK_STRENGTH_STRONG)
    mid = sum(1 for _a, _b, s in links if s == LINK_STRENGTH_MID)
    normal = sum(1 for _a, _b, s in links if s == LINK_STRENGTH_NORMAL)
    n = len(links) or 1
    print(
        f'[rerun_connect_strength] 完成 links={len(links)} '
        f'强={strong}({100 * strong / n:.1f}%) '
        f'强中={mid}({100 * mid / n:.1f}%) '
        f'普通={normal}({100 * normal / n:.1f}%)',
        flush=True,
    )
    print(
        f'[rerun_connect_strength] 模型漏标（已默认普通）: {len(missing)}/{len(links)}',
        flush=True,
    )
    for a, b in missing[:30]:
        print(f'  漏标默认普通: {a}|{b}', flush=True)
    if len(missing) > 30:
        print(f'  ... 另有 {len(missing) - 30} 条漏标', flush=True)

    for i, (a, b, s) in enumerate(links[:15]):
        print(f'  {a}|{b}|{s}', flush=True)
    if len(links) > 15:
        print(f'  ... 另有 {len(links) - 15} 条', flush=True)

    hierarchy_links = [[a, b, s] for a, b, s in links]
    if args.dry_run:
        print('[rerun_connect_strength] dry-run：不更新 notebook meta', flush=True)
        return 0

    new_meta = dict(meta or {})
    new_meta['hierarchy_links'] = hierarchy_links
    new_meta['pipeline'] = new_meta.get('pipeline') or 'v2_condense_hierarchy'
    new_meta['reorganize_selected_cids'] = sorted(set(selected))
    new_meta['book_kw_connect_path'] = connect_path
    new_meta['book_key_issue_path'] = book_key_issue_path(username)

    kw_map: Dict[str, Any] = {}
    if notebook.keywordFourColorDMT:
        try:
            kw_map = json.loads(notebook.keywordFourColorDMT)
        except Exception:
            kw_map = {}

    _save_notebook_semantic_state(notebook, kw_map, new_meta)
    print(
        f'[rerun_connect_strength] 已更新 meta.hierarchy_links={len(hierarchy_links)}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
