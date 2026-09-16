#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量重跑指定本子内卡片的四色/DMT 分析。

默认本子：marklee_DuJiangYan

在 本地backend 目录下执行：
  python app_chat/rerun_notebook_four_color_dmt.py

常用参数：
  --username marklee_DuJiangYan   本子 username（默认即此值）
  --only-empty                                仅处理 four_color_type 与 dmt_level 均为空的卡（默认）
  --all                                       重跑本子内全部卡片（覆盖已有四色/DMT；处理顺序随机打乱）
  --dry-run                                   只分析不写库
  --limit 10                                  最多处理 N 张（调试用）
  --with-keywords                             完成后顺带重跑本子关键词四色/DMT
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
import traceback
from typing import Dict, List, Optional, Tuple

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')

import django  # noqa: E402

django.setup()

from app_chat.card_analyzer import analyze_card_with_new_standard  # noqa: E402
from app_chat.models import Card  # noqa: E402
from app_chat.scene_context_helper import (  # noqa: E402
    get_scene_info_from_username,
    get_scene_summary,
    get_notebook_description,
)

DEFAULT_USERNAME = 'marklee_DuJiangYan'


def _card_needs_rerun(card, only_empty: bool) -> bool:
    if not (card.content or '').strip():
        return False
    if not only_empty:
        return True
    fc = (card.four_color_type or '').strip()
    dmt = (card.dmt_level or '').strip()
    return not fc and not dmt


def _load_cards(username: str, only_empty: bool, limit: Optional[int], shuffle: bool) -> List[Card]:
    qs = Card.objects.filter(username=username).order_by('cid')
    cards = [c for c in qs if _card_needs_rerun(c, only_empty)]
    if shuffle and len(cards) > 1:
        random.shuffle(cards)
    if limit is not None and limit > 0:
        cards = cards[:limit]
    return cards


def _reset_all_cards_color_in_memory(all_cards_data: List[dict]) -> None:
    """全量重跑时清空内存中的四色/DMT，避免按 cid 顺序时「已有色卡」参考失真。"""
    for row in all_cards_data:
        row['four_color_type'] = ''
        row['dmt_level'] = ''


def _build_all_cards_data(username: str) -> Tuple[List[dict], int]:
    all_cards = Card.objects.filter(username=username).values(
        'cid', 'content', 'contentTitle', 'is_neuron', 'is_evolved', 'selection_count', 'postIndex',
        'four_color_type', 'dmt_level'
    )
    all_cards_data = list(all_cards)
    return all_cards_data, len(all_cards_data)


def rerun_notebook_four_color_dmt(
    username: str,
    *,
    only_empty: bool = True,
    dry_run: bool = False,
    limit: Optional[int] = None,
    with_keywords: bool = False,
) -> Dict[str, int]:
    """重跑本子卡片四色/DMT，返回统计计数。"""
    stats = {
        'total_in_notebook': 0,
        'candidates': 0,
        'processed': 0,
        'updated_nonempty': 0,
        'still_empty': 0,
        'errors': 0,
        'skipped_no_content': 0,
    }

    stats['total_in_notebook'] = Card.objects.filter(username=username).count()
    if stats['total_in_notebook'] == 0:
        print(f'[rerun_four_color_dmt] 未找到 username={username!r} 的卡片，请确认本子名拼写。')
        return stats

    cards = _load_cards(username, only_empty, limit, shuffle=not only_empty)
    stats['candidates'] = len(cards)
    all_cards_data, total_cards_count = _build_all_cards_data(username)

    if not only_empty and cards:
        _reset_all_cards_color_in_memory(all_cards_data)
        print('  全量重跑：处理顺序已随机打乱，内存占比统计已清零后逐张累计')

    scene_name, _, scene_summary, notebook_desc = get_scene_info_from_username(username)
    if scene_name:
        scene_summary_info, _ = get_scene_summary(scene_name)
        if not scene_summary:
            scene_summary = scene_summary_info
    if not notebook_desc and scene_name:
        notebook_desc = get_notebook_description(username, scene_name)

    print(f'[rerun_four_color_dmt] username={username}')
    print(f'  本子总卡数: {stats["total_in_notebook"]}')
    print(f'  待处理: {stats["candidates"]} (only_empty={only_empty}, dry_run={dry_run})')
    print(f'  场景: {scene_name or "(未解析)"}')
    if dry_run:
        print('  *** dry-run 模式：结果不会写入数据库 ***')

    t0 = time.time()
    for idx, card in enumerate(cards, start=1):
        cid = card.cid
        content = (card.content or '').strip()
        if not content:
            stats['skipped_no_content'] += 1
            print(f'  [{idx}/{stats["candidates"]}] cid={cid} 内容为空，跳过')
            continue

        _, sub_scene_name, per_card_summary, _ = get_scene_info_from_username(
            username, card.contentTitle or ''
        )
        final_summary = per_card_summary or scene_summary

        card_data = {
            'cid': card.cid,
            'content': card.content or '',
            'contentTitle': card.contentTitle or '',
            'is_neuron': card.is_neuron,
            'is_evolved': card.is_evolved,
            'selection_count': card.selection_count,
            'username': card.username,
        }

        try:
            four_color_type, dmt_level, is_analyzed = analyze_card_with_new_standard(
                card_data,
                scene_name=scene_name or None,
                sub_scene_name=sub_scene_name or None,
                scene_summary=final_summary,
                notebook_description=notebook_desc,
                all_cards_data=all_cards_data,
                total_cards_count=total_cards_count,
            )
            stats['processed'] += 1

            has_attr = bool((four_color_type or '').strip() or (dmt_level or '').strip())
            if has_attr:
                stats['updated_nonempty'] += 1
            else:
                stats['still_empty'] += 1

            print(
                f'  [{idx}/{stats["candidates"]}] cid={cid} '
                f'四色={four_color_type or "-"} DMT={dmt_level or "-"} '
                f'{"✓" if has_attr else "仍空"}'
            )

            if not dry_run:
                Card.objects.filter(cid=cid, username=username).update(
                    four_color_type=four_color_type or '',
                    dmt_level=dmt_level or '',
                    is_analyzed_by_new_standard=is_analyzed,
                )
                for row in all_cards_data:
                    if row.get('cid') == cid:
                        row['four_color_type'] = four_color_type or ''
                        row['dmt_level'] = dmt_level or ''
                        break
        except Exception as e:
            stats['errors'] += 1
            print(f'  [{idx}/{stats["candidates"]}] cid={cid} 失败: {e}')
            traceback.print_exc()

    elapsed = time.time() - t0
    print(f'\n[rerun_four_color_dmt] 完成，耗时 {elapsed:.1f}s')
    print(f'  处理: {stats["processed"]}, 写入非空: {stats["updated_nonempty"]}, '
          f'仍空: {stats["still_empty"]}, 错误: {stats["errors"]}')

    if with_keywords and not dry_run and scene_name:
        print('\n[rerun_four_color_dmt] 开始重跑本子关键词四色/DMT …')
        try:
            from app_chat.keyword_analyzer import analyze_and_update_keywords_for_notebook

            analyze_and_update_keywords_for_notebook(username, scene_name=scene_name)
            print('[rerun_four_color_dmt] 关键词分析完成')
        except Exception as e:
            stats['errors'] += 1
            print(f'[rerun_four_color_dmt] 关键词分析失败: {e}')
            traceback.print_exc()
    elif with_keywords and dry_run:
        print('[rerun_four_color_dmt] dry-run 跳过关键词重跑')

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description='批量重跑本子内卡片四色/DMT 分析')
    parser.add_argument(
        '--username', default=DEFAULT_USERNAME,
        help=f'本子 username，默认 {DEFAULT_USERNAME}',
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        '--only-empty', action='store_true', default=False,
        help='仅处理四色/DMT 均为空的卡片（与 --all 二选一；都不指定时默认 only-empty）',
    )
    scope.add_argument(
        '--all', action='store_true', default=False,
        help='重跑本子内全部有内容的卡片',
    )
    parser.add_argument('--dry-run', action='store_true', help='只分析，不写数据库')
    parser.add_argument('--limit', type=int, default=None, help='最多处理 N 张卡片')
    parser.add_argument(
        '--with-keywords', action='store_true',
        help='卡片完成后顺带重跑本子关键词四色/DMT',
    )
    args = parser.parse_args()

    only_empty = not args.all if (args.all or args.only_empty) else True

    stats = rerun_notebook_four_color_dmt(
        args.username,
        only_empty=only_empty,
        dry_run=args.dry_run,
        limit=args.limit,
        with_keywords=args.with_keywords,
    )
    if stats['candidates'] == 0:
        return 0
    if stats['errors'] > 0:
        return 2
    if stats['processed'] > 0 and stats['updated_nonempty'] == 0:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
