#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""将 export_semantic_reorganize_bundle.py 导出的 txt 导入到目标本子。

卡片匹配：不用 cid；对 contentTitle+正文综合字符串，按「相同文字数量（字符频次交集）/
较长串长度」≥95% 视为同一张卡（一模一样或只改几个字都能过）。
匹配时优先标题精确命中 + 长度剪枝，避免长文两两全量比对卡死。
服务器上多出的卡（与 bundle 中任一张都 <95%）跳过，不改其关键词。

默认：
  bundle = ./marklee_DuJiangYan_semantic_bundle.txt
  目标本子 = marklee_DuJiangYan

在 Backend 根目录执行：
  python app_chat/import_semantic_reorganize_bundle.py
  python app_chat/import_semantic_reorganize_bundle.py --bundle marklee_DuJiangYan_semantic_bundle.txt
  python app_chat/import_semantic_reorganize_bundle.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple

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
    _save_notebook_semantic_state,
)
from app_chat.semantic_reorganize_pipeline import (  # noqa: E402
    book_key_issue_path,
    book_kw_connect_path,
    card_condense_path,
    _finalize_link_strengths,
    _write_book_kw_connect,
)

BUNDLE_FORMAT = 'nkcn_semantic_reorganize_bundle_v1'
DEFAULT_USERNAME = 'marklee_DuJiangYan'
DEFAULT_BUNDLE = 'marklee_DuJiangYan_semantic_bundle.txt'
MATCH_THRESHOLD = 0.95
# 标题+正文归一化后过短则不参与匹配，避免空卡互相误配
MIN_MATCH_BLOB_LEN = 8


def _norm_text(s: str) -> str:
    t = (s or '').replace('\r\n', '\n').replace('\r', '\n')
    lines = [ln.strip() for ln in t.split('\n')]
    return '\n'.join(ln for ln in lines if ln).strip()


def card_match_blob(title: str, content: str) -> str:
    """contentTitle + 正文 的综合匹配串。"""
    return _norm_text(f'{title or ""}\n{content or ""}')


def _length_can_reach(a: str, b: str, threshold: float) -> bool:
    """长度差过大时，相同字数不可能达到 threshold。"""
    la, lb = len(a), len(b)
    denom = max(la, lb)
    if denom <= 0:
        return True
    return (min(la, lb) / denom) >= threshold


def same_char_ratio(a: str, b: str, *, threshold: float = MATCH_THRESHOLD) -> float:
    """
    相同文字数量占比 = 两边共有字符数（按出现次数取交集） / max(len(a), len(b))。

    例：全文 1000 字、只改约 20 字 → 相同约 980 → 98%。
    用 Counter 交集 O(n)，避免长正文 SequenceMatcher 卡死。
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if not _length_can_reach(a, b, threshold):
        return 0.0
    matched = sum((Counter(a) & Counter(b)).values())
    denom = max(len(a), len(b))
    return (matched / denom) if denom else 1.0


def load_bundle(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError('bundle 根节点必须是 JSON object')
    fmt = data.get('format') or ''
    if fmt and fmt != BUNDLE_FORMAT:
        print(f'[import] 警告：format={fmt!r}，期望 {BUNDLE_FORMAT}，继续尝试导入', flush=True)
    if not isinstance(data.get('cards'), list):
        raise RuntimeError('bundle 缺少 cards 数组')
    return data


def match_cards(
    bundle_cards: List[Dict[str, Any]],
    server_cards: List[Any],
    *,
    threshold: float = MATCH_THRESHOLD,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Any]]:
    """
    贪心一对一匹配。优先标题精确命中缩小候选，再比全文。
    """
    print('[import] 正在准备匹配串…', flush=True)
    server_items = []
    for c in server_cards:
        title = _norm_text(c.contentTitle or '')
        blob = card_match_blob(c.contentTitle or '', c.content or '')
        server_items.append({
            'card': c,
            'title': title,
            'blob': blob,
            'used': False,
        })

    bundle_items = []
    for b in bundle_cards:
        title = _norm_text(b.get('contentTitle') or '')
        blob = card_match_blob(b.get('contentTitle') or '', b.get('content') or '')
        bundle_items.append({'bundle': b, 'title': title, 'blob': blob})

    title_index: Dict[str, List[int]] = defaultdict(list)
    for si, sitem in enumerate(server_items):
        if sitem['title']:
            title_index[sitem['title']].append(si)

    candidates: List[Tuple[float, int, int]] = []
    skipped_short = 0
    title_hit_scans = 0
    full_scans = 0
    n_b = len(bundle_items)

    for bi, bitem in enumerate(bundle_items):
        if (bi + 1) % 10 == 0 or bi == 0 or bi + 1 == n_b:
            print(f'[import] 匹配进度 {bi + 1}/{n_b}…', flush=True)

        if len(bitem['blob']) < MIN_MATCH_BLOB_LEN:
            skipped_short += 1
            continue

        if bitem['title'] and bitem['title'] in title_index:
            candidate_sis = list(title_index[bitem['title']])
            title_hit_scans += 1
        else:
            candidate_sis = [
                si for si, sitem in enumerate(server_items)
                if len(sitem['blob']) >= MIN_MATCH_BLOB_LEN
                and _length_can_reach(bitem['blob'], sitem['blob'], threshold)
            ]
            full_scans += 1

        best_si = -1
        best_score = -1.0
        for si in candidate_sis:
            sitem = server_items[si]
            if len(sitem['blob']) < MIN_MATCH_BLOB_LEN:
                continue
            if not _length_can_reach(bitem['blob'], sitem['blob'], threshold):
                continue
            if bitem['blob'] == sitem['blob']:
                best_si = si
                best_score = 1.0
                break
            score = same_char_ratio(bitem['blob'], sitem['blob'], threshold=threshold)
            if score > best_score:
                best_score = score
                best_si = si

        if best_si >= 0 and best_score >= threshold:
            candidates.append((best_score, bi, best_si))

    if skipped_short:
        print(
            f'[import] 跳过 bundle 中过短匹配串卡片 {skipped_short} 张'
            f'（归一化后 <{MIN_MATCH_BLOB_LEN} 字）',
            flush=True,
        )
    print(
        f'[import] 候选扫描：标题精确命中 {title_hit_scans} 张，'
        f'无标题/未命中走长度过滤 {full_scans} 张，'
        f'初步达标对数={len(candidates)}',
        flush=True,
    )

    candidates.sort(key=lambda x: (-x[0], x[1], x[2]))

    matched_b = set()
    matched_s = set()
    matches: List[Dict[str, Any]] = []
    for score, bi, si in candidates:
        if bi in matched_b or si in matched_s:
            continue
        matched_b.add(bi)
        matched_s.add(si)
        server_items[si]['used'] = True
        matches.append({
            'bundle': bundle_items[bi]['bundle'],
            'server': server_items[si]['card'],
            'score': score,
        })

    # 冲突后补配一轮（只扫未占用服务器卡）
    remaining_b = [i for i in range(len(bundle_items)) if i not in matched_b]
    remaining_s = [i for i in range(len(server_items)) if i not in matched_s]
    if remaining_b and remaining_s:
        print(
            f'[import] 补配：bundle剩余 {len(remaining_b)}，server剩余 {len(remaining_s)}…',
            flush=True,
        )
        extra: List[Tuple[float, int, int]] = []
        for bi in remaining_b:
            bitem = bundle_items[bi]
            if len(bitem['blob']) < MIN_MATCH_BLOB_LEN:
                continue
            best_si = -1
            best_score = -1.0
            for si in remaining_s:
                if si in matched_s:
                    continue
                sitem = server_items[si]
                if len(sitem['blob']) < MIN_MATCH_BLOB_LEN:
                    continue
                if not _length_can_reach(bitem['blob'], sitem['blob'], threshold):
                    continue
                if bitem['blob'] == sitem['blob']:
                    best_si, best_score = si, 1.0
                    break
                score = same_char_ratio(bitem['blob'], sitem['blob'], threshold=threshold)
                if score > best_score:
                    best_score, best_si = score, si
            if best_si >= 0 and best_score >= threshold:
                extra.append((best_score, bi, best_si))
        extra.sort(key=lambda x: (-x[0], x[1], x[2]))
        for score, bi, si in extra:
            if bi in matched_b or si in matched_s:
                continue
            matched_b.add(bi)
            matched_s.add(si)
            server_items[si]['used'] = True
            matches.append({
                'bundle': bundle_items[bi]['bundle'],
                'server': server_items[si]['card'],
                'score': score,
            })

    unmatched_bundle = [
        bundle_items[i]['bundle'] for i in range(len(bundle_items)) if i not in matched_b
    ]
    unmatched_server = [it['card'] for it in server_items if not it['used']]
    return matches, unmatched_bundle, unmatched_server


def _hierarchy_to_triples(hierarchy_links: List[Any]) -> List[Tuple[str, str, str]]:
    triples: List[Tuple[str, str, str]] = []
    for item in hierarchy_links or []:
        if not item or len(item) < 2:
            continue
        a = str(item[0] or '').strip()
        b = str(item[1] or '').strip()
        if not a or not b or a == b:
            continue
        s = str(item[2] or '').strip() if len(item) >= 3 else ''
        triples.append((a, b, s))
    return triples


def _parse_connect_text(text: str) -> List[Tuple[str, str, str]]:
    triples: List[Tuple[str, str, str]] = []
    for line in (text or '').splitlines():
        line = line.strip().replace('｜', '|')
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            continue
        s = parts[2].strip() if len(parts) >= 3 else ''
        triples.append((parts[0], parts[1], s))
    return triples


def main() -> int:
    parser = argparse.ArgumentParser(description='导入语义梳理 bundle 到目标本子')
    parser.add_argument('--username', default=DEFAULT_USERNAME, help='目标本子 username')
    parser.add_argument('--scene-name', default='', help='可选 scene_name')
    parser.add_argument(
        '--bundle',
        default=DEFAULT_BUNDLE,
        help=f'bundle 文件路径（默认当前目录 {DEFAULT_BUNDLE}）',
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=MATCH_THRESHOLD,
        help=f'相同文字占比阈值 = 相同字数/max(两端长度)（默认 {MATCH_THRESHOLD}）',
    )
    parser.add_argument('--dry-run', action='store_true', help='只打印匹配结果，不写库')
    args = parser.parse_args()

    username = (args.username or '').strip()
    bundle_path = (args.bundle or '').strip()
    if not username:
        print('username 不能为空', flush=True)
        return 2
    if not os.path.isfile(bundle_path):
        alt = os.path.join(_BACKEND_ROOT, os.path.basename(bundle_path))
        if os.path.isfile(alt):
            bundle_path = alt
        else:
            alt2 = os.path.join(_BACKEND_ROOT, bundle_path)
            if os.path.isfile(alt2):
                bundle_path = alt2
            else:
                print(f'找不到 bundle 文件: {args.bundle}', flush=True)
                return 2
    else:
        bundle_path = os.path.abspath(bundle_path)

    threshold = float(args.threshold)
    if not (0.5 <= threshold <= 1.0):
        print('threshold 建议在 0.5～1.0', flush=True)
        return 2

    try:
        bundle = load_bundle(bundle_path)
    except Exception as exc:
        print(f'[import] 读取 bundle 失败: {exc}', flush=True)
        return 1

    notebook = _load_notebook(username, args.scene_name or None)
    if not notebook:
        print(f'未找到目标本子 username={username}', flush=True)
        return 2

    server_cards = list(Card.objects.filter(username=username))
    bundle_cards = [c for c in (bundle.get('cards') or []) if isinstance(c, dict)]
    print(
        f'[import] bundle={bundle_path} source={bundle.get("source_username")} '
        f'bundle_cards={len(bundle_cards)} server_cards={len(server_cards)} '
        f'threshold={threshold:.0%}',
        flush=True,
    )

    matches, unmatched_bundle, unmatched_server = match_cards(
        bundle_cards, server_cards, threshold=threshold,
    )
    print(
        f'[import] 匹配成功={len(matches)} '
        f'bundle未匹配={len(unmatched_bundle)} server跳过(新增/微调过大)={len(unmatched_server)}',
        flush=True,
    )
    for m in matches[:20]:
        b = m['bundle']
        s = m['server']
        print(
            f'  ✓ {m["score"]:.2%} | local_cid={b.get("source_cid")} → server_cid={s.cid} | '
            f'title≈{(s.contentTitle or b.get("contentTitle") or "")[:40]}',
            flush=True,
        )
    if len(matches) > 20:
        print(f'  ... 另有 {len(matches) - 20} 条匹配', flush=True)
    if unmatched_bundle:
        print('[import] bundle 中未匹配到服务器卡片（不会写入）：', flush=True)
        for b in unmatched_bundle[:10]:
            print(
                f'  ✗ local_cid={b.get("source_cid")} title={(b.get("contentTitle") or "")[:50]}',
                flush=True,
            )
    if unmatched_server[:5]:
        print('[import] 服务器未匹配卡片（保留原样）示例：', flush=True)
        for c in unmatched_server[:5]:
            print(f'  · server_cid={c.cid} title={(c.contentTitle or "")[:50]}', flush=True)

    if not matches:
        print('[import] 没有任何匹配，中止', flush=True)
        return 1

    if args.dry_run:
        print('[import] dry-run：不写库/不写文件', flush=True)
        return 0

    try:
        selected_server_cids: List[int] = []
        for m in matches:
            b = m['bundle']
            s = m['server']
            kw = b.get('keyWords') or ''
            Card.objects.filter(username=username, cid=s.cid).update(keyWords=kw)
            selected_server_cids.append(int(s.cid))
            condense = b.get('condense') or ''
            if condense.strip():
                path = card_condense_path(username, int(s.cid))
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(condense if condense.endswith('\n') else condense + '\n')
            print(
                f'[import] 已更新 server_cid={s.cid} keyWords 词数≈'
                f'{len([x for x in kw.replace("，", ",").split(",") if x.strip()])}',
                flush=True,
            )

        issues = bundle.get('book_key_issues') or ''
        if issues.strip():
            issue_path = book_key_issue_path(username)
            with open(issue_path, 'w', encoding='utf-8') as f:
                f.write(issues if issues.endswith('\n') else issues + '\n')
            print(f'[import] 已写 {issue_path}', flush=True)

        hierarchy = list(bundle.get('hierarchy_links') or [])
        triples = _hierarchy_to_triples(hierarchy)
        if not triples:
            triples = _parse_connect_text(bundle.get('book_kw_connect_text') or '')
        if triples:
            finalized = _finalize_link_strengths(triples)
            _write_book_kw_connect(username, finalized)
            hierarchy_links = [[a, b, s] for a, b, s in finalized]
        else:
            hierarchy_links = []
            print('[import] 警告：bundle 中无连边数据', flush=True)

        export_map = bundle.get('keywordFourColorDMT') or {}
        if not isinstance(export_map, dict):
            export_map = {}
        server_map: Dict[str, Any] = {}
        if notebook.keywordFourColorDMT:
            try:
                server_map = json.loads(notebook.keywordFourColorDMT)
                if not isinstance(server_map, dict):
                    server_map = {}
            except Exception:
                server_map = {}
        merged_map = dict(server_map)
        merged_map.update(export_map)

        old_meta = _load_semantic_meta(notebook)
        new_meta = dict(old_meta or {})
        src_meta = bundle.get('semantic_meta') or {}
        new_meta['pipeline'] = src_meta.get('pipeline') or new_meta.get('pipeline') or 'v2_condense_hierarchy'
        new_meta['last_mode'] = src_meta.get('last_mode') or new_meta.get('last_mode') or 'full'
        new_meta['sampled'] = bool(src_meta.get('sampled')) if 'sampled' in src_meta else new_meta.get('sampled')
        if src_meta.get('card_selection'):
            new_meta['card_selection'] = src_meta.get('card_selection')
        new_meta['reorganize_selected_cids'] = sorted(set(selected_server_cids))
        new_meta['hierarchy_links'] = hierarchy_links
        new_meta['book_key_issue_path'] = book_key_issue_path(username)
        new_meta['book_kw_connect_path'] = book_kw_connect_path(username)
        new_meta['last_completed_at'] = datetime.now().isoformat(timespec='seconds')
        new_meta['imported_from'] = {
            'source_username': bundle.get('source_username'),
            'exported_at': bundle.get('exported_at'),
            'bundle_format': bundle.get('format'),
            'matched_cards': len(matches),
            'threshold': threshold,
        }

        _save_notebook_semantic_state(notebook, merged_map, new_meta)
        print(
            f'[import] 完成：匹配写入卡={len(matches)} '
            f'selected_cids={len(selected_server_cids)} '
            f'links={len(hierarchy_links)} attrs={len(merged_map)} '
            f'(export覆盖={len(export_map)})',
            flush=True,
        )
        return 0
    except Exception as exc:
        traceback.print_exc()
        print(f'[import] 写入失败: {exc}', flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
