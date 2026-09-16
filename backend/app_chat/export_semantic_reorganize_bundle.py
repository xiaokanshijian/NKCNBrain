#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""导出本子「最新语义梳理」结果为可迁移 bundle（txt / JSON）。

包含：选中卡片的 contentTitle/正文/语义关键词/浓缩、bookKeyIssue、
hierarchy_links（连边+强度）、keywordFourColorDMT（四色/DMT/三类知识）、meta 摘要。

默认本子：marklee_DuJiangYan

在 本地backend 目录下执行：
  python app_chat/export_semantic_reorganize_bundle.py
  python app_chat/export_semantic_reorganize_bundle.py --username marklee_DuJiangYan
  python app_chat/export_semantic_reorganize_bundle.py -o marklee_DuJiangYan_semantic_bundle.txt

将生成的 txt 拷到服务器 /home/ubuntu/Backend 后，用 import_semantic_reorganize_bundle.py 导入。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')

import django  # noqa: E402

django.setup()

from app_chat.models import Card  # noqa: E402
from app_chat.semantic_keyword_service import (  # noqa: E402
    _load_notebook,
    _load_semantic_meta,
)
from app_chat.semantic_reorganize_pipeline import (  # noqa: E402
    book_key_issue_path,
    book_kw_connect_path,
    card_condense_dir,
    card_condense_path,
    load_hierarchy_links_from_file,
)

BUNDLE_FORMAT = 'nkcn_semantic_reorganize_bundle_v1'
DEFAULT_USERNAME = 'marklee_DuJiangYan'


def _selected_cids(meta: Dict[str, Any], username: str) -> List[int]:
    selected: List[int] = []
    for x in (meta.get('reorganize_selected_cids') or []):
        try:
            if isinstance(x, bool):
                continue
            if isinstance(x, int):
                selected.append(int(x))
                continue
            s = str(x).strip()
            if s.isdigit():
                selected.append(int(s))
        except Exception:
            continue
    if selected:
        return sorted(set(selected))
    # 兼容：cardCondense 下的 cid.txt
    d = card_condense_dir(username)
    if not os.path.isdir(d):
        return []
    cids: List[int] = []
    for name in os.listdir(d):
        if name.endswith('.txt') and name[:-4].isdigit():
            cids.append(int(name[:-4]))
    return sorted(cids)


def _load_text(path: str) -> str:
    if not os.path.isfile(path):
        return ''
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _load_keyword_map(notebook) -> Dict[str, Any]:
    raw = (notebook.keywordFourColorDMT or '').strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_bundle(username: str, scene_name: Optional[str] = None) -> Dict[str, Any]:
    notebook = _load_notebook(username, scene_name)
    if not notebook:
        raise RuntimeError(f'未找到本子 username={username}')

    meta = _load_semantic_meta(notebook)
    selected = _selected_cids(meta, username)
    if not selected:
        raise RuntimeError(
            '无法确定语义梳理选中卡片（meta.reorganize_selected_cids / cardCondense 均为空）'
        )

    cards_qs = Card.objects.filter(username=username, cid__in=selected)
    by_cid = {int(c.cid): c for c in cards_qs}
    missing = [cid for cid in selected if cid not in by_cid]
    if missing:
        print(f'[export] 警告：选中 cid 在库中缺失 {len(missing)} 个，示例={missing[:10]}', flush=True)

    cards_out: List[Dict[str, Any]] = []
    for cid in selected:
        card = by_cid.get(cid)
        if not card:
            continue
        condense = _load_text(card_condense_path(username, cid))
        cards_out.append({
            # source_cid 仅供排查，导入禁止用 cid 匹配
            'source_cid': cid,
            'contentTitle': card.contentTitle or '',
            'content': card.content or '',
            'keyWords': card.keyWords or '',
            'condense': condense,
        })

    hierarchy = list(meta.get('hierarchy_links') or [])
    if not hierarchy:
        hierarchy = load_hierarchy_links_from_file(username)

    book_key_issues = _load_text(book_key_issue_path(username))
    book_kw_connect = _load_text(book_kw_connect_path(username))
    keyword_map = _load_keyword_map(notebook)

    # meta 中与 cid 强绑定的字段导入时会重写，这里仍带上便于对照
    meta_export = {
        'pipeline': meta.get('pipeline') or 'v2_condense_hierarchy',
        'last_mode': meta.get('last_mode') or '',
        'sampled': bool(meta.get('sampled')),
        'card_selection': meta.get('card_selection') or {},
        'source_reorganize_selected_cids': selected,
        'source_hierarchy_link_count': len(hierarchy),
    }

    return {
        'format': BUNDLE_FORMAT,
        'exported_at': datetime.now().isoformat(timespec='seconds'),
        'source_username': username,
        'bookdescription': (notebook.bookdescription or '') if notebook else '',
        'book_key_issues': book_key_issues,
        'book_kw_connect_text': book_kw_connect,
        'hierarchy_links': hierarchy,
        'keywordFourColorDMT': keyword_map,
        'semantic_meta': meta_export,
        'cards': cards_out,
        'stats': {
            'selected_cids': len(selected),
            'exported_cards': len(cards_out),
            'hierarchy_links': len(hierarchy),
            'keyword_attrs': len(keyword_map),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='导出语义梳理结果 bundle（txt）')
    parser.add_argument('--username', default=DEFAULT_USERNAME, help='本子 username')
    parser.add_argument('--scene-name', default='', help='可选 scene_name')
    parser.add_argument(
        '-o', '--output',
        default='',
        help='输出路径（默认：当前目录/<username>_semantic_bundle.txt）',
    )
    args = parser.parse_args()
    username = (args.username or '').strip()
    if not username:
        print('username 不能为空', flush=True)
        return 2

    out = (args.output or '').strip() or os.path.join(
        _BACKEND_ROOT, f'{username}_semantic_bundle.txt'
    )

    try:
        bundle = build_bundle(username, args.scene_name or None)
    except Exception as exc:
        print(f'[export] 失败: {exc}', flush=True)
        return 1

    out_abs = os.path.abspath(out)
    out_dir = os.path.dirname(out_abs)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_abs, 'w', encoding='utf-8') as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
        f.write('\n')

    st = bundle.get('stats') or {}
    print(
        f'[export] 成功 → {out_abs}\n'
        f'  cards={st.get("exported_cards")} links={st.get("hierarchy_links")} '
        f'attrs={st.get("keyword_attrs")}',
        flush=True,
    )
    print('请将此文件拷到服务器 /home/ubuntu/Backend 后执行 import 脚本。', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
