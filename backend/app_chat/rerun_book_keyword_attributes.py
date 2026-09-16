#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""仅补做本子语义关键词「四色 / DMT / 三类知识」属性分析（含分批核验）。

不重跑抽词、浓缩、核心问题、补词、连边。

默认本子：marklee_DuJiangYan

在 本地backend 目录下执行：
  python app_chat/rerun_book_keyword_attributes.py
  python app_chat/rerun_book_keyword_attributes.py --username marklee_DuJiangYan
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from typing import Any, Dict, List, Set

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')

import django  # noqa: E402

django.setup()

from app_chat.keyword_utils import split_semantic_keywords_raw  # noqa: E402
from app_chat.models import Card  # noqa: E402
from app_chat.semantic_keyword_service import (  # noqa: E402
    _load_notebook,
    _load_semantic_meta,
    _save_notebook_semantic_state,
)
from app_chat.semantic_reorganize_pipeline import (  # noqa: E402
    card_condense_dir,
    collect_union_keywords,
    load_card_rows_by_cids,
    run_attribute_analysis_concurrent,
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


def _keywords_from_selected(username: str, selected: List[int]) -> List[str]:
    rows = load_card_rows_by_cids(username, selected)
    kws = collect_union_keywords(rows)
    if kws:
        return kws
    # 兜底：直接扫卡
    out: List[str] = []
    seen: Set[str] = set()
    for card in Card.objects.filter(username=username, cid__in=selected).only('keyWords'):
        for kw in split_semantic_keywords_raw(card.keyWords or ''):
            if kw and kw not in seen:
                seen.add(kw)
                out.append(kw)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description='仅补做语义关键词四色/DMT/三类知识分析+核验')
    parser.add_argument('--username', default=DEFAULT_USERNAME)
    parser.add_argument('--scene-name', default='')
    parser.add_argument('--dry-run', action='store_true', help='只分析不写库')
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
        print(f'[rerun_attrs] meta 无选中集，回退 cardCondense cid={len(selected)}', flush=True)
    if not selected:
        print('无法确定 reorganize_selected_cids', flush=True)
        return 2

    keywords = _keywords_from_selected(username, selected)
    if not keywords:
        print('选中卡上无语义关键词', flush=True)
        return 2

    notebook_desc = (notebook.bookdescription or '') if notebook else ''
    print(
        f'[rerun_attrs] username={username} selected={len(selected)} '
        f'keywords={len(keywords)} desc_len={len(notebook_desc)}',
        flush=True,
    )

    try:
        attr_map = run_attribute_analysis_concurrent(
            keywords,
            notebook_desc,
            username=username,
            set_job_fn=None,
            track_fn=None,
            is_running_fn=None,
        )
    except Exception as exc:
        traceback.print_exc()
        print(f'[rerun_attrs] 失败: {exc}', flush=True)
        return 1

    print(f'[rerun_attrs] 完成 attrs={len(attr_map)}/{len(keywords)}', flush=True)
    from app_chat.semantic_reorganize_pipeline import (
        book_kw_attrs_diff_path,
        book_kw_attrs_draft_path,
        book_kw_attrs_verified_path,
    )
    print(
        f'[rerun_attrs] 初判文件: {book_kw_attrs_draft_path(username)}\n'
        f'[rerun_attrs] 核验文件: {book_kw_attrs_verified_path(username)}\n'
        f'[rerun_attrs] 改动对照: {book_kw_attrs_diff_path(username)}',
        flush=True,
    )
    # 抽样打印几条
    for i, kw in enumerate(keywords[:12]):
        a = attr_map.get(kw) or {}
        print(
            f'  {kw}|{a.get("four_color_type") or "?"}|'
            f'{a.get("dmt_level") or "?"}|{a.get("knowledge_type") or "?"}',
            flush=True,
        )
    if len(keywords) > 12:
        print(f'  ... 另有 {len(keywords) - 12} 词', flush=True)

    if args.dry_run:
        print('[rerun_attrs] dry-run：不写库', flush=True)
        return 0

    # 仅保留本轮新语义空间词的属性（与全量 v2 一致，不混旧词）
    final_map: Dict[str, Dict[str, str]] = {}
    for kw in keywords:
        final_map[kw] = dict(attr_map.get(kw) or {})

    new_meta = dict(meta or {})
    new_meta['pipeline'] = new_meta.get('pipeline') or 'v2_condense_hierarchy'
    new_meta['reorganize_selected_cids'] = sorted(set(selected))
    _save_notebook_semantic_state(notebook, final_map, new_meta)
    print(
        f'[rerun_attrs] 已写入 keywordFourColorDMT 词数={len(final_map)}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
