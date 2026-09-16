#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""仅补做本子语义关键词「层次连边」一步（bookKWConnect / hierarchy_links）。

不重跑抽词、浓缩、核心问题、补词、属性分析。

默认本子：marklee_DuJiangYan

在 本地backend 目录下执行：
  python app_chat/rerun_book_kw_connect.py
  python app_chat/rerun_book_kw_connect.py --username marklee_DuJiangYan

说明：
  - 读取 meta.reorganize_selected_cids（无则回退 cardCondense 下的 cid.txt）
  - 读取 bookKeyIssue.txt + 各卡 keyWords/浓缩
  - 调用 run_hierarchy_connections（边数=0 按失败重试 Claude×2 → deepseek；顺带强度）
  - 写回 bookKWConnect.txt（父|子|强/强中/普通），并更新本子 meta.hierarchy_links
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
    book_key_issue_path,
    book_kw_connect_path,
    card_condense_dir,
    load_card_rows_by_cids,
    run_hierarchy_connections,
)

DEFAULT_USERNAME = 'marklee_DuJiangYan'


def _selected_cids_from_meta(meta: Dict[str, Any]) -> List[int]:
    selected = [int(x) for x in (meta.get('reorganize_selected_cids') or [])]
    if selected:
        return selected
    # 兼容旧 v2：抽样时 processed 即选中集
    if meta.get('pipeline') == 'v2_condense_hierarchy' and meta.get('sampled'):
        return [int(x) for x in (meta.get('processed_cids') or [])]
    return [int(x) for x in (meta.get('processed_cids') or [])]


def _selected_cids_from_condense_dir(username: str) -> List[int]:
    d = card_condense_dir(username)
    if not os.path.isdir(d):
        return []
    cids: List[int] = []
    for name in os.listdir(d):
        if not name.endswith('.txt'):
            continue
        stem = name[:-4]
        if stem.isdigit():
            cids.append(int(stem))
    return sorted(cids)


def _load_book_key_issues(username: str) -> str:
    path = book_key_issue_path(username)
    if not os.path.isfile(path):
        return ''
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def main() -> int:
    parser = argparse.ArgumentParser(description='仅补做语义关键词层次连边分析')
    parser.add_argument('--username', default=DEFAULT_USERNAME, help='本子 username（用户名_本子名）')
    parser.add_argument('--scene-name', default='', help='可选 scene_name')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只调用分析并打印边数，不写 meta（仍会写 bookKWConnect.txt，因流水线函数内落盘）',
    )
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
        print(
            f'[rerun_book_kw_connect] meta 无选中集，回退 cardCondense 目录 cid 数={len(selected)}',
            flush=True,
        )
    if not selected:
        print('无法确定 reorganize_selected_cids，退出', flush=True)
        return 2

    issues = _load_book_key_issues(username)
    notebook_desc = (notebook.bookdescription or '') if notebook else ''
    card_rows = load_card_rows_by_cids(username, selected)
    if not card_rows:
        print(f'未加载到卡片 rows，selected={len(selected)}', flush=True)
        return 2

    kw_count = len({kw for r in card_rows for kw in (r.get('keywords') or [])})
    print(
        f'[rerun_book_kw_connect] username={username} '
        f'selected={len(selected)} rows={len(card_rows)} keywords≈{kw_count} '
        f'bookKeyIssue_len={len(issues)} desc_len={len(notebook_desc)}',
        flush=True,
    )
    print(f'[rerun_book_kw_connect] 将写入 {book_kw_connect_path(username)}', flush=True)

    try:
        links = run_hierarchy_connections(
            username=username,
            notebook_description=notebook_desc,
            book_key_issues=issues,
            card_rows=card_rows,
            track_fn=None,
            is_running_fn=None,
        )
    except Exception as exc:
        traceback.print_exc()
        print(f'[rerun_book_kw_connect] 失败: {exc}', flush=True)
        return 1

    hierarchy_links = [[a, b, s] for a, b, s in links]
    print(f'[rerun_book_kw_connect] 成功 links={len(hierarchy_links)}', flush=True)
    for i, (a, b, s) in enumerate(links[:15]):
        print(f'  {a} | {b} | {s}', flush=True)
    if len(links) > 15:
        print(f'  ... 另有 {len(links) - 15} 条', flush=True)

    if args.dry_run:
        print('[rerun_book_kw_connect] dry-run：不更新 notebook meta', flush=True)
        return 0

    # 更新 meta.hierarchy_links，保留其它字段
    new_meta = dict(meta or {})
    new_meta['hierarchy_links'] = hierarchy_links
    new_meta['pipeline'] = new_meta.get('pipeline') or 'v2_condense_hierarchy'
    new_meta['reorganize_selected_cids'] = sorted(set(selected))
    new_meta['book_kw_connect_path'] = book_kw_connect_path(username)
    new_meta['book_key_issue_path'] = book_key_issue_path(username)

    kw_map: Dict[str, Any] = {}
    if notebook.keywordFourColorDMT:
        try:
            kw_map = json.loads(notebook.keywordFourColorDMT)
        except Exception:
            kw_map = {}

    _save_notebook_semantic_state(notebook, kw_map, new_meta)
    print(
        f'[rerun_book_kw_connect] 已更新 meta.hierarchy_links={len(hierarchy_links)} '
        f'选中卡={len(new_meta["reorganize_selected_cids"])}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
