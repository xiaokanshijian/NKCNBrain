# encoding=utf-8
"""场景 / 任务簇「大本体」语义关键词梳理流水线。

严格按产品约定：
- 从可见本子中筛 1～5 本（卡片+文档数 Top5；排除卡片数为 0；
  排除 bookName 含 demo 且卡片数 <30；同名多本只取组本；
  xxx/xxxCopyN/xxxSharedN 同族只留卡片最多的一本）
- 无完整中本体的本子：简化浓缩（最多20卡）+ 简化抽词（_simplified，不算本子内已梳理）
- 有完整中本体的本子：直接取 xx 个关键词及属性，不调模型
- 场景/任务簇级：100 词 → 层次连边(≥2/3) + 属性(≥4/5)
- 结果目录：received_dir/scene_cluster_semantic/{username}/
  （history 在同级 history/；文件名仍为 {sid}_scene* / {cid}_cluster*）
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from django.db import close_old_connections
from app_chat.keyword_utils import (
    parse_batch_keyword_attributes,
    split_semantic_keywords_raw,
    _reflective_pitfall_examples,
)
from app_chat.models import Card
from app_chat.semantic_reorganize_pipeline import (
    DEFAULT_LINK_STRENGTH,
    FINAL_MARKER,
    HIERARCHY_MIN_COVERAGE_RATIO,
    LINK_STRENGTHS,
    PART1_ISSUES,
    _after_final,
    _ensure_keywords_not_rejected,
    _extract_section,
    _finalize_link_strengths,
    _hierarchy_coverage_ok,
    _is_shallow_card,
    _is_white_card,
    _card_recency_key,
    call_claude_with_retry_fallback,
    card_condense_dir,
    card_condense_path,
    condense_card_content,
    normalize_link_strength,
    _link_strength_prompt_blurb,
    build_keyword_attribute_system_prompt,
)
from app_chat.task_cluster_service import (
    _list_doc_filenames,
    get_accessible_notebooks,
    load_task_cluster_result,
)
from zym.models import UserNotebook, scene as SceneModel

# 简化抽样
SIMPLIFIED_SHALLOW_CAP = 15
SIMPLIFIED_SHALLOW_RECENT = 5
SIMPLIFIED_SHALLOW_RANDOM = 10
SIMPLIFIED_WHITE_EXTRA = 5
SIMPLIFIED_TOTAL_CAP = 20
MAX_CONDENSE_WORKERS = 5
MAX_BOOK_PARALLEL = 5
DOC_NAME_CAP = 20
SCENE_KEYWORD_TARGET = 100
ATTR_MIN_COVERAGE_RATIO = 4.0 / 5.0

PART2_KEYWORDS = '[PART2_KEYWORDS]'
PART1_LINKS = '[PART1_LINKS]'
PART2_ATTRS = '[PART2_ATTRS]'

SCOPE_SCENE = 'scene'
SCOPE_TASK_CLUSTER = 'task_cluster'

_RESULT_ROOT = os.path.join('.', 'received_dir', 'scene_cluster_semantic')


def _safe_username(username: str) -> str:
    """结果目录用户名：禁止路径穿越，仅保留安全字符。空用户名直接报错，避免写到错误目录。"""
    name = str(username or '').strip().replace('\\', '/')
    name = name.split('/')[-1].strip()
    name = re.sub(r'[^\w.\-]', '_', name)
    if not name:
        raise ValueError('scene_cluster_semantic 需要非空 username（当前登录用户名）')
    return name


def user_result_dir(username: str) -> str:
    return os.path.join(_RESULT_ROOT, _safe_username(username))


def user_history_dir(username: str) -> str:
    return os.path.join(user_result_dir(username), 'history')


def _log(msg: str) -> None:
    print(f'[scene_cluster_semantic] {msg}', flush=True)


def ensure_result_dir(username: str) -> str:
    base = user_result_dir(username)
    hist = user_history_dir(username)
    os.makedirs(base, exist_ok=True)
    os.makedirs(hist, exist_ok=True)
    return base


def scope_file_prefix(scope_type: str, scope_id: str) -> str:
    sid = re.sub(r'[^\w\-.]', '_', str(scope_id or '').strip()) or 'unknown'
    if scope_type == SCOPE_TASK_CLUSTER:
        return f'{sid}_cluster'
    return f'{sid}_scene'


def result_paths(scope_type: str, scope_id: str, username: str) -> Dict[str, str]:
    """大本体结果路径：received_dir/scene_cluster_semantic/{username}/…"""
    base = ensure_result_dir(username)
    hist = user_history_dir(username)
    prefix = scope_file_prefix(scope_type, scope_id)
    return {
        'key_issue': os.path.join(base, f'{prefix}KeyIssue.txt'),
        'keywords': os.path.join(base, f'{prefix}KW.txt'),
        'connect': os.path.join(base, f'{prefix}KWConnect.txt'),
        'attrs': os.path.join(base, f'{prefix}KWAttrs.txt'),
        'meta': os.path.join(base, f'{prefix}_meta.json'),
        'backup': os.path.join(hist, f'{prefix}_backup_latest.json'),
        'dir': base,
        'history_dir': hist,
        'username': _safe_username(username),
    }


def xx_for_book_count(n: int) -> int:
    if n <= 1:
        return 100
    if n <= 3:
        return 50
    return 30


def list_subscene_names(scene_name: str) -> List[str]:
    """读取场景下全部子场景名（excel 优先，summary.json 兜底）。"""
    names: List[str] = []
    scene_name = (scene_name or '').strip()
    if not scene_name:
        return names
    try:
        import pandas as pd
        xlsx = os.path.join('.', 'received_dir', 'scene_excel', scene_name, 'prompt.xlsx')
        if os.path.isfile(xlsx):
            data = pd.read_excel(xlsx)
            if data is not None and len(data.columns) > 1:
                first = str(data.columns[1])
                order = data.iloc[:, 1].dropna().astype(str).tolist()
                order = [first] + order
                names = [x.strip() for x in order if x and str(x).strip() and str(x).strip().lower() != 'nan']
                # 去重保序
                seen = set()
                uniq = []
                for n in names:
                    if n not in seen:
                        seen.add(n)
                        uniq.append(n)
                return uniq
    except Exception as exc:
        _log(f'读取子场景 excel 失败: {exc}')
    try:
        summary_path = os.path.join('.', 'received_dir', 'summary.json')
        if os.path.isfile(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                all_summaries = json.load(f)
            for s in all_summaries or []:
                if (s.get('scene') or '').strip() == scene_name:
                    for sub in s.get('subscenes') or []:
                        n = (sub.get('subscene') or '').strip()
                        if n and n not in names:
                            names.append(n)
                    break
    except Exception as exc:
        _log(f'读取 summary.json 子场景失败: {exc}')
    return names


def notebook_has_full_mid_ontology(notebook: UserNotebook, full_username: str) -> bool:
    """是否已有完整本子中本体梳理结果（非 _simplified）。"""
    try:
        ctx = {}
        if notebook.context_data:
            ctx = json.loads(notebook.context_data) if isinstance(notebook.context_data, str) else (notebook.context_data or {})
        meta = (ctx or {}).get('semantic_reorganize') or {}
    except Exception:
        meta = {}
    links = meta.get('hierarchy_links') or []
    if not links:
        connect_path = os.path.join(card_condense_dir(full_username), 'bookKWConnect.txt')
        if os.path.isfile(connect_path):
            try:
                with open(connect_path, 'r', encoding='utf-8') as f:
                    links = [ln for ln in f if ln.strip() and '|' in ln]
            except Exception:
                links = []
    kw_map: Dict[str, Any] = {}
    if notebook.keywordFourColorDMT:
        try:
            kw_map = json.loads(notebook.keywordFourColorDMT) or {}
        except Exception:
            kw_map = {}
    completed = bool(meta.get('last_completed_at')) or meta.get('pipeline') == 'v2_condense_hierarchy'
    return bool(links) and bool(kw_map) and completed


def _load_notebook_obj(nb_info: Dict[str, Any]) -> Optional[UserNotebook]:
    try:
        return UserNotebook.objects.filter(
            username=(nb_info.get('username') or '').strip(),
            bookName=(nb_info.get('bookName') or '').strip(),
            sid=int(nb_info.get('sid') or 0),
        ).first()
    except Exception:
        return None


def _book_name_family_key(book_name: str) -> str:
    """
    xxx / xxxCopy1 / xxxShared2 视为同一族，族键为去掉末尾 Copy数字 或 Shared数字 后的前缀。
    """
    name = str(book_name or '').strip()
    if not name:
        return ''
    base = re.sub(r'(?:Copy|Shared)\d+$', '', name, flags=re.IGNORECASE)
    return base or name


def select_scope_notebooks(
    *,
    scope_type: str,
    scope_id: str,
    viewer: str,
    scene_name: str = '',
) -> List[Dict[str, Any]]:
    """筛 1～5 本：可见、排除空本、demo 且卡<30 排除、同名只取组本、同族留卡最多、按卡+文档 Top5。"""
    viewer = (viewer or '').strip()
    accessible = get_accessible_notebooks(viewer)
    if scope_type == SCOPE_SCENE:
        sid = int(scope_id)
        candidates = [n for n in accessible if int(n.get('sid') or 0) == sid]
    else:
        # 任务簇：取该簇内 notebook_keys
        result = load_task_cluster_result(viewer) or {}
        keys: Set[str] = set()
        for cl in result.get('clusters') or []:
            if str(cl.get('cluster_id') or '') == str(scope_id):
                for k in cl.get('notebook_keys') or []:
                    keys.add(str(k).strip())
                for nb in cl.get('notebooks') or []:
                    k = str(nb.get('notebook_key') or nb.get('full_username') or '').strip()
                    if k:
                        keys.add(k)
                break
        candidates = [n for n in accessible if (n.get('notebook_key') or n.get('full_username')) in keys]

    # 排除卡片数为 0；排除 bookName 含 demo 且卡片数 < 30（demo 且 ≥30 张卡仍保留）
    kept: List[Dict[str, Any]] = []
    skipped_empty = 0
    skipped_demo_small = 0
    for n in candidates:
        cards = int(n.get('cardNum') or 0)
        book = str(n.get('bookName') or '')
        if cards <= 0:
            skipped_empty += 1
            continue
        if 'demo' in book.lower() and cards < 30:
            skipped_demo_small += 1
            continue
        kept.append(n)
    if skipped_empty or skipped_demo_small:
        _log(
            f'筛本前置过滤: 空本跳过={skipped_empty} '
            f'demo且卡<30跳过={skipped_demo_small} 剩余={len(kept)}'
        )
    candidates = kept

    # 同 bookName：多本时只取组本
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for n in candidates:
        name = str(n.get('bookName') or '').strip()
        by_name.setdefault(name, []).append(n)

    deduped: List[Dict[str, Any]] = []
    for name, group in by_name.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        group_ones = [g for g in group if str(g.get('syncUsers') or '').strip()]
        if not group_ones:
            _log(f'同名多本且无组本，跳过 bookName={name}')
            continue
        # 多组本同名时取内容量最大
        group_ones.sort(
            key=lambda x: int(x.get('cardNum') or 0) + len(x.get('documents') or []),
            reverse=True,
        )
        deduped.append(group_ones[0])

    # xxx / xxxCopyN / xxxSharedN：同族只保留卡片数最多的一本
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for n in deduped:
        fam = _book_name_family_key(n.get('bookName') or '')
        by_family.setdefault(fam, []).append(n)

    family_picked: List[Dict[str, Any]] = []
    for fam, group in by_family.items():
        if len(group) == 1:
            family_picked.append(group[0])
            continue
        # 卡片数最多；并列时：文档多者优先，再优先无 Copy/Shared 后缀的本名
        group.sort(
            key=lambda x: (
                int(x.get('cardNum') or 0),
                len(x.get('documents') or []),
                1 if str(x.get('bookName') or '') == fam else 0,
            ),
            reverse=True,
        )
        chosen = group[0]
        skipped = [str(g.get('bookName') or '') for g in group[1:]]
        _log(
            f'Copy/Shared 同族保留卡片最多: family={fam} keep={chosen.get("bookName")} '
            f'cards={chosen.get("cardNum")} skip={skipped}'
        )
        family_picked.append(chosen)

    deduped = family_picked

    # 刷新文档列表与计数
    for n in deduped:
        full = n.get('full_username') or n.get('notebook_key') or ''
        docs = _list_doc_filenames(full, limit=200)
        n['documents'] = docs
        n['doc_count'] = len(docs)
        n['content_score'] = int(n.get('cardNum') or 0) + len(docs)

    deduped.sort(key=lambda x: int(x.get('content_score') or 0), reverse=True)
    selected = deduped[:5]
    _log(
        f'筛本 scope={scope_type}:{scope_id} viewer={viewer} '
        f'候选={len(candidates)} 去重后={len(deduped)} 入选={len(selected)} '
        f'xx={xx_for_book_count(len(selected))}'
    )
    return selected


def select_balanced_keywords_from_map(
    keyword_map: Dict[str, Dict[str, Any]],
    xx: int,
) -> List[Tuple[str, Dict[str, str]]]:
    """从完整中本体属性中取 xx 个，尽量覆盖 D/M/T、四色、三类知识。"""
    items: List[Tuple[str, Dict[str, str]]] = []
    for kw, raw in (keyword_map or {}).items():
        k = str(kw or '').strip()
        if not k:
            continue
        attrs = {
            'four_color_type': str((raw or {}).get('four_color_type') or '').strip().upper(),
            'dmt_level': str((raw or {}).get('dmt_level') or '').strip().upper(),
            'knowledge_type': str((raw or {}).get('knowledge_type') or '').strip().lower(),
        }
        items.append((k, attrs))
    if not items or xx <= 0:
        return []
    if len(items) <= xx:
        return items

    # 按 DMT 分层轮询，再兼顾四色/三类
    buckets: Dict[str, List[Tuple[str, Dict[str, str]]]] = {'D': [], 'M': [], 'T': [], '_': []}
    for it in items:
        d = it[1].get('dmt_level') or '_'
        if d not in ('D', 'M', 'T'):
            d = '_'
        buckets[d].append(it)
    for b in buckets.values():
        random.shuffle(b)

    # 目标比例约 5:3:2
    target = {
        'D': max(1, int(round(xx * 0.5))),
        'M': max(1, int(round(xx * 0.3))),
        'T': max(1, int(round(xx * 0.2))),
    }
    # 修正总和
    while sum(target.values()) > xx:
        for key in ('D', 'M', 'T'):
            if sum(target.values()) <= xx:
                break
            if target[key] > 1:
                target[key] -= 1
    while sum(target.values()) < xx:
        target['D'] += 1

    picked: List[Tuple[str, Dict[str, str]]] = []
    seen: Set[str] = set()
    for key in ('D', 'M', 'T', '_'):
        need = target.get(key, 0) if key != '_' else xx
        for it in buckets.get(key) or []:
            if len(picked) >= xx:
                break
            if key != '_' and sum(1 for _k, a in picked if a.get('dmt_level') == key) >= need:
                continue
            if it[0] in seen:
                continue
            seen.add(it[0])
            picked.append(it)
        if len(picked) >= xx:
            break

    if len(picked) < xx:
        for it in items:
            if it[0] in seen:
                continue
            seen.add(it[0])
            picked.append(it)
            if len(picked) >= xx:
                break

    # 二次微调：尽量补齐四色与三类知识覆盖
    have_color = {a.get('four_color_type') for _, a in picked}
    have_kt = {a.get('knowledge_type') for _, a in picked}
    for want_c in ('R', 'B', 'P', 'G'):
        if want_c in have_color:
            continue
        for it in items:
            if it[0] in seen:
                continue
            if it[1].get('four_color_type') == want_c:
                # 替换一个重复最多的
                if picked:
                    picked[-1] = it
                    seen.add(it[0])
                    have_color.add(want_c)
                break
    for want_k in ('trad', 'org', 'trib'):
        if want_k in have_kt:
            continue
        for it in items:
            if it[0] in {p[0] for p in picked}:
                continue
            if it[1].get('knowledge_type') == want_k:
                if picked:
                    picked[0] = it
                    have_kt.add(want_k)
                break
    return picked[:xx]


def select_simplified_cards(cards: List[Card]) -> List[Card]:
    """浅卡≤15全取；>15则最近5+其余随机10；另从其余白卡随机最多5；合计≤20。"""
    shallow = [c for c in cards if _is_shallow_card(c)]
    if len(shallow) <= SIMPLIFIED_SHALLOW_CAP:
        selected_shallow = list(shallow)
    else:
        shallow_sorted = sorted(shallow, key=_card_recency_key, reverse=True)
        recent = shallow_sorted[:SIMPLIFIED_SHALLOW_RECENT]
        recent_ids = {c.cid for c in recent}
        rest = [c for c in shallow if c.cid not in recent_ids]
        n = min(SIMPLIFIED_SHALLOW_RANDOM, len(rest))
        random_pick = random.sample(rest, n) if n else []
        selected_shallow = recent + random_pick

    selected_ids = {c.cid for c in selected_shallow}
    white_pool = [c for c in cards if _is_white_card(c) and c.cid not in selected_ids]
    white_n = min(SIMPLIFIED_WHITE_EXTRA, len(white_pool))
    white_extra = random.sample(white_pool, white_n) if white_n else []
    selected = selected_shallow + white_extra
    if len(selected) > SIMPLIFIED_TOTAL_CAP:
        selected = selected[:SIMPLIFIED_TOTAL_CAP]
    return selected


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write((content or '').rstrip() + '\n')


def _read_text(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ''
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def simplified_paths(full_username: str) -> Dict[str, str]:
    d = card_condense_dir(full_username)
    os.makedirs(d, exist_ok=True)
    return {
        'key_issue': os.path.join(d, 'bookKeyIssue_simplified.txt'),
        'keywords': os.path.join(d, 'bookKW_simplified.txt'),
    }


def run_simplified_condense_for_book(
    full_username: str,
    *,
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
    job_key: str = '',
) -> List[Dict[str, Any]]:
    """步骤(1)：最多20卡 deepseek-v4-pro 浓缩，5并发。"""
    close_old_connections()
    cards = list(
        Card.objects.filter(username=full_username)
        .exclude(content__isnull=True)
        .exclude(content='')
    )
    selected = select_simplified_cards(cards)
    _log(f'{full_username} 简化浓缩选卡 {len(selected)}/{len(cards)}')
    rows: List[Dict[str, Any]] = []

    def _one(card: Card) -> Dict[str, Any]:
        close_old_connections()
        try:
            if is_running_fn and job_key and not is_running_fn(job_key):
                raise RuntimeError('任务已停止')
            title = (card.contentTitle or card.title or '')[:200]
            content = card.content or ''
            text = condense_card_content(
                content, title,
                username=full_username, cid=card.cid,
                track_fn=track_fn, is_running_fn=None,
            )
            path = card_condense_path(full_username, int(card.cid))
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text or '')
            return {
                'cid': int(card.cid),
                'title': title,
                'condense': text or '',
            }
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=MAX_CONDENSE_WORKERS) as ex:
        futs = {ex.submit(_one, c): c for c in selected}
        for fut in as_completed(futs):
            try:
                rows.append(fut.result())
            except Exception as exc:
                c = futs[fut]
                _log(f'浓缩失败 cid={getattr(c, "cid", "?")}: {exc}')
                traceback.print_exc()
    rows.sort(key=lambda r: r.get('cid') or 0)
    return rows


def run_simplified_book_keywords(
    *,
    full_username: str,
    bookdescription: str,
    doc_names: List[str],
    card_rows: List[Dict[str, Any]],
    xx: int,
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
    job_key: str = '',
) -> Tuple[str, List[str]]:
    """步骤(2)无中本体：Claude 核心问题 + xx 关键词 → _simplified 文件。"""
    from app_chat.views import system_prompt_claude

    docs = list(doc_names or [])
    if len(docs) > DOC_NAME_CAP:
        docs = random.sample(docs, DOC_NAME_CAP)

    card_blocks = []
    for row in card_rows:
        card_blocks.append(
            f"===== 卡片 cid={row.get('cid')} =====\n"
            f"标题(contentTitle)：{row.get('title') or '（无）'}\n"
            f"浓缩(cid.txt)：\n{row.get('condense') or '（空）'}\n"
        )

    quality = _reflective_pitfall_examples()
    system = (
        f'{system_prompt_claude}\n\n'
        '请按人性化思考协议（thinking / checking）完成任务，再给出最终结果。\n'
        '最终结果必须严格按下列标记格式输出（便于程序解析）：\n'
        f'先单独一行 {FINAL_MARKER}\n'
        f'然后 {PART1_ISSUES}\n'
        '（写出本子要解决的核心问题，以及几个子问题；用清晰中文，可分点）\n'
        f'然后 {PART2_KEYWORDS}\n'
        f'（给出恰好约 {xx} 个本子关键语义关键词；只输出关键词，不要连线、不要属性。'
        '每行一个关键词，或同一行用中文逗号分隔均可。'
        '质量要求与本子内语义关键词一致：具体、可层次、忌发虚；尽量不自造词；'
        '汉字数勿≥10（字母数字不计）；禁止含反引号`）\n\n'
        f'{quality}\n'
    )
    user = (
        f'本子中文名(bookdescription)：{bookdescription or "（未提供）"}\n'
        f'文档名列表（最多{DOC_NAME_CAP}个）：{"、".join(docs) if docs else "（无）"}\n\n'
        f'以下共 {len(card_rows)} 张卡片的标题与浓缩（无关键词）：\n\n'
        f'{"".join(card_blocks)}\n\n'
        f'请完成：①核心问题与子问题；②给出约 {xx} 个关键语义关键词。'
    )

    def _validate(raw: str) -> None:
        if PART1_ISSUES not in raw or PART2_KEYWORDS not in raw:
            raise RuntimeError('输出缺少 [PART1_KEY_ISSUES] 或 [PART2_KEYWORDS] 标记')
        after = _after_final(raw)
        body = _extract_section(after, PART2_KEYWORDS, None) or _extract_section(raw, PART2_KEYWORDS, None)
        if not body.strip():
            raise RuntimeError('PART2 关键词为空')
        kws = split_semantic_keywords_raw(body.replace('\n', '，'))
        if not kws:
            raise RuntimeError('未能解析出关键词')
        _ensure_keywords_not_rejected(kws, context='本子简化抽词')

    used, raw = call_claude_with_retry_fallback(
        system, user, username=job_key or full_username,
        action=f'简化本子关键词:{full_username}',
        track_fn=track_fn, is_running_fn=is_running_fn,
        max_tokens=8192, temperature=0.35,
        validate_raw=_validate,
    )
    _log(f'{full_username} 简化抽词 model={used}')
    after = _after_final(raw)
    issues = _extract_section(after, PART1_ISSUES, [PART2_KEYWORDS])
    kw_body = _extract_section(after, PART2_KEYWORDS, None)
    if not issues:
        issues = after.split(PART2_KEYWORDS)[0].strip() if PART2_KEYWORDS in after else after[:2000]
    kws = split_semantic_keywords_raw((kw_body or '').replace('\n', '，'))
    # 截到 xx（略多时截；略少保留）
    if len(kws) > xx:
        kws = kws[:xx]
    paths = simplified_paths(full_username)
    _write_text(paths['key_issue'], issues.strip())
    _write_text(paths['keywords'], '，'.join(kws))
    _log(f'已写 {paths["key_issue"]} / {paths["keywords"]} 词数={len(kws)}')
    return issues.strip(), kws


def load_book_key_issues(full_username: str, *, has_full: bool) -> str:
    d = card_condense_dir(full_username)
    if has_full:
        p = os.path.join(d, 'bookKeyIssue.txt')
        text = _read_text(p)
        if text.strip():
            return text
    return _read_text(os.path.join(d, 'bookKeyIssue_simplified.txt'))


def run_scope_keywords(
    *,
    scope_type: str,
    scope_name: str,
    sub_names: List[str],
    book_blocks: List[Dict[str, Any]],
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
    job_key: str = '',
) -> Tuple[str, List[str]]:
    """步骤(3)：场景/任务簇核心问题 + 100 语义关键词。"""
    from app_chat.views import system_prompt_claude

    label = '任务簇' if scope_type == SCOPE_TASK_CLUSTER else '场景'
    quality = _reflective_pitfall_examples()
    books_txt_parts = []
    for b in book_blocks:
        attr_lines = []
        for kw, attrs in (b.get('keywords_with_attrs') or []):
            if attrs and (attrs.get('four_color_type') or attrs.get('dmt_level') or attrs.get('knowledge_type')):
                attr_lines.append(
                    f"{kw}|{attrs.get('four_color_type') or '?'}|"
                    f"{attrs.get('dmt_level') or '?'}|{attrs.get('knowledge_type') or '?'}"
                )
            else:
                attr_lines.append(kw)
        books_txt_parts.append(
            f"----- 本子：{b.get('bookdescription') or ''} -----\n"
            f"核心问题：\n{b.get('key_issues') or '（无）'}\n"
            f"本子语义关键词（预期约 {b.get('xx')} 个）：\n"
            + '\n'.join(attr_lines)
            + '\n'
        )

    system = (
        f'{system_prompt_claude}\n\n'
        '请按人性化思考协议（thinking / checking）完成任务，再给出最终结果。\n'
        '最终结果必须严格按下列标记格式输出（便于程序解析）：\n'
        f'先单独一行 {FINAL_MARKER}\n'
        f'然后 {PART1_ISSUES}\n'
        f'（写出这个{label}（含若干子场景/组成部分）要解决的核心问题，以及几个子问题）\n'
        f'然后 {PART2_KEYWORDS}\n'
        f'（给出恰好约 {SCENE_KEYWORD_TARGET} 个{label}级语义关键词；只输出关键词，不要连线、不要属性。'
        '每行一个或中文逗号分隔。'
        f'质量上仍须遵循本子内语义关键词要求，且要大于本子内、有{label}这一大本体的语义指向；'
        '仍应具体，切忌发虚、模糊；尽量不自造词汇，扎根于本子级语义关键词，进行增删改微调，'
        '目的是合并同类项、剪枝、整合，并加一些拔高。'
        '汉字数勿≥10（字母数字不计）；禁止含反引号`）\n\n'
        f'{quality}\n'
    )
    sub_txt = '、'.join(sub_names) if sub_names else '（无或未配置）'
    user = (
        f'{label}名：{scope_name or "（未提供）"}\n'
        f'子场景名列表：{sub_txt}\n\n'
        f'以下为本{label}下入选的 {len(book_blocks)} 个本子汇总：\n\n'
        f'{"".join(books_txt_parts)}\n'
        f'请完成：①{label}核心问题与子问题；②给出约 {SCENE_KEYWORD_TARGET} 个{label}级语义关键词。'
    )

    def _validate(raw: str) -> None:
        if PART1_ISSUES not in raw or PART2_KEYWORDS not in raw:
            raise RuntimeError('输出缺少 [PART1_KEY_ISSUES] 或 [PART2_KEYWORDS] 标记')
        after = _after_final(raw)
        body = _extract_section(after, PART2_KEYWORDS, None)
        if not (body or '').strip():
            raise RuntimeError('PART2 关键词为空')
        kws = split_semantic_keywords_raw(body.replace('\n', '，'))
        if len(kws) < max(20, int(SCENE_KEYWORD_TARGET * 0.5)):
            raise RuntimeError(f'关键词过少：{len(kws)}')
        _ensure_keywords_not_rejected(kws, context=f'{label}级抽词')

    used, raw = call_claude_with_retry_fallback(
        system, user, username=job_key or scope_name,
        action=f'{label}级关键词',
        track_fn=track_fn, is_running_fn=is_running_fn,
        max_tokens=8192, temperature=0.35,
        validate_raw=_validate,
    )
    _log(f'{label}级抽词 model={used}')
    after = _after_final(raw)
    issues = _extract_section(after, PART1_ISSUES, [PART2_KEYWORDS])
    kw_body = _extract_section(after, PART2_KEYWORDS, None)
    if not issues:
        issues = after.split(PART2_KEYWORDS)[0].strip() if PART2_KEYWORDS in after else after[:2000]
    kws = split_semantic_keywords_raw((kw_body or '').replace('\n', '，'))
    if len(kws) > SCENE_KEYWORD_TARGET:
        kws = kws[:SCENE_KEYWORD_TARGET]
    return issues.strip(), kws


def _parse_links_from_section(body: str, allowed: Set[str]) -> List[Tuple[str, str, str]]:
    links: List[Tuple[str, str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for line in (body or '').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        line = re.sub(r'^\d+[.\、\)]\s*', '', line)
        parts = [p.strip() for p in re.split(r'[|｜\t]', line)]
        if len(parts) < 2:
            # 尝试 父→子 或 父->子
            m = re.split(r'\s*(?:→|->|=>|—>|－>|⇒)\s*', line)
            if len(m) >= 2:
                parts = [m[0].strip(), m[1].strip()]
                if len(m) >= 3:
                    parts.append(m[2].strip())
        if len(parts) < 2:
            continue
        a, b = parts[0], parts[1]
        strength = normalize_link_strength(parts[2]) if len(parts) >= 3 else ''
        if not strength:
            strength = DEFAULT_LINK_STRENGTH
        if a not in allowed or b not in allowed or a == b:
            continue
        pair = (a, b)
        if pair in seen:
            continue
        seen.add(pair)
        links.append((a, b, strength if strength in LINK_STRENGTHS else DEFAULT_LINK_STRENGTH))
    return links


def run_scope_connect_and_attrs(
    *,
    scope_type: str,
    scope_name: str,
    sub_names: List[str],
    key_issues: str,
    book_descriptions: List[str],
    keywords: List[str],
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
    job_key: str = '',
) -> Tuple[List[Tuple[str, str, str]], Dict[str, Dict[str, str]]]:
    """步骤(4)：层次连边(≥2/3) + 属性(≥4/5)，同一调用内两段。"""
    from app_chat.views import system_prompt_claude

    label = '任务簇' if scope_type == SCOPE_TASK_CLUSTER else '场景'
    kw_set = set(keywords)
    n_kw = len(keywords)
    min_covered = max(1, math.ceil(n_kw * HIERARCHY_MIN_COVERAGE_RATIO)) if n_kw else 0
    min_attrs = max(1, math.ceil(n_kw * ATTR_MIN_COVERAGE_RATIO)) if n_kw else 0

    # 属性判定细则与本子内一致（复用完整准则，去掉其自带 FINAL 输出段以免冲突）
    attr_rules = build_keyword_attribute_system_prompt()
    attr_rules = attr_rules.split('## 五、输出格式')[0].strip()
    system = (
        f'{system_prompt_claude}\n\n'
        '请按人性化思考协议完成任务，再给出最终结果。\n'
        f'先单独一行 {FINAL_MARKER}\n'
        f'然后 {PART1_LINKS}\n'
        f'为下方「{label}语义关键词集合」构建层次连边（父|子|强度），要求与本子内层次连边类似：'
        '尽量全覆盖、有总有分、可多层；强度三档：强/强中/普通。\n'
        f'{_link_strength_prompt_blurb(primary_is_topology=True)}\n'
        '每行格式：父关键词|子关键词|强度\n'
        f'然后 {PART2_ATTRS}\n'
        '为每个语义关键词判定四色、DMT、三类知识（三维独立）。\n'
        '每行格式：关键词|四色|DMT|三类知识\n'
        '关键词须与输入原文完全一致。\n\n'
        f'{attr_rules}\n'
    )
    sub_txt = '、'.join(sub_names) if sub_names else '（无）'
    user = (
        f'{label}名：{scope_name}\n'
        f'子场景：{sub_txt}\n'
        f'本子中文名列表：{"、".join(book_descriptions) if book_descriptions else "（无）"}\n\n'
        f'{label}核心问题：\n{key_issues or "（无）"}\n\n'
        f'{label}语义关键词（共 {n_kw} 个，须尽量全部进入连边与属性）：\n'
        + '\n'.join(f'- {kw}' for kw in keywords)
        + '\n\n请完成：①层次连边；②全部词的属性标注。'
    )

    def _validate(raw: str) -> None:
        if PART1_LINKS not in raw or PART2_ATTRS not in raw:
            raise RuntimeError('输出缺少 [PART1_LINKS] 或 [PART2_ATTRS] 标记')
        after = _after_final(raw)
        link_body = _extract_section(after, PART1_LINKS, [PART2_ATTRS]) or _extract_section(raw, PART1_LINKS, [PART2_ATTRS])
        attr_body = _extract_section(after, PART2_ATTRS, None) or _extract_section(raw, PART2_ATTRS, None)
        links = _parse_links_from_section(link_body, kw_set)
        ok, orphans = _hierarchy_coverage_ok(links, keywords, min_ratio=HIERARCHY_MIN_COVERAGE_RATIO)
        if not ok:
            covered = n_kw - len(orphans)
            raise RuntimeError(
                f'连边覆盖未达 2/3：covered={covered}/{n_kw}（需≥{min_covered}）'
            )
        fake = f'{FINAL_MARKER}\n{attr_body}'
        parsed = parse_batch_keyword_attributes(fake, keywords, final_marker=FINAL_MARKER)
        complete_n = sum(
            1 for kw in keywords
            if (parsed.get(kw) or {}).get('four_color_type')
            and (parsed.get(kw) or {}).get('dmt_level')
            and (parsed.get(kw) or {}).get('knowledge_type')
        )
        if complete_n < min_attrs:
            raise RuntimeError(
                f'属性覆盖未达 4/5：complete={complete_n}/{n_kw}（需≥{min_attrs}）'
            )

    used, raw = call_claude_with_retry_fallback(
        system, user, username=job_key or scope_name,
        action=f'{label}连边+属性',
        track_fn=track_fn, is_running_fn=is_running_fn,
        max_tokens=16000, temperature=0.3,
        validate_raw=_validate,
    )
    _log(f'{label}连边+属性 model={used}')
    after = _after_final(raw)
    link_body = _extract_section(after, PART1_LINKS, [PART2_ATTRS]) or _extract_section(raw, PART1_LINKS, [PART2_ATTRS])
    attr_body = _extract_section(after, PART2_ATTRS, None) or _extract_section(raw, PART2_ATTRS, None)
    links = _finalize_link_strengths(_parse_links_from_section(link_body, kw_set))
    fake = f'{FINAL_MARKER}\n{attr_body}'
    attrs = parse_batch_keyword_attributes(fake, keywords, final_marker=FINAL_MARKER)
    return links, attrs


def write_scope_results(
    scope_type: str,
    scope_id: str,
    *,
    username: str,
    key_issues: str,
    keywords: List[str],
    links: List[Tuple[str, str, str]],
    attrs: Dict[str, Dict[str, str]],
    meta: Dict[str, Any],
) -> Dict[str, str]:
    paths = result_paths(scope_type, scope_id, username)
    _write_text(paths['key_issue'], key_issues)
    _write_text(paths['keywords'], '，'.join(keywords))
    with open(paths['connect'], 'w', encoding='utf-8') as f:
        for a, b, s in links:
            f.write(f'{a}|{b}|{s}\n')
    with open(paths['attrs'], 'w', encoding='utf-8') as f:
        for kw in keywords:
            a = attrs.get(kw) or {}
            f.write(
                f"{kw}|{a.get('four_color_type') or ''}|"
                f"{a.get('dmt_level') or ''}|{a.get('knowledge_type') or ''}\n"
            )
    payload = dict(meta or {})
    payload.update({
        'scope_type': scope_type,
        'scope_id': str(scope_id),
        'viewer': _safe_username(username),
        'keywords': keywords,
        'hierarchy_links': [[a, b, s] for a, b, s in links],
        'keywordFourColorDMT': attrs,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
        'has_result': True,
    })
    with open(paths['meta'], 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    _log(
        f'已写结果 user={paths["username"]} scope={scope_type}:{scope_id} '
        f'kw={len(keywords)} links={len(links)}'
    )
    return paths


def load_scope_result(scope_type: str, scope_id: str, username: str) -> Optional[Dict[str, Any]]:
    paths = result_paths(scope_type, scope_id, username)
    if not os.path.isfile(paths['meta']):
        # 兼容：仅有关键词文件也算有结果雏形，但完整需 meta
        if os.path.isfile(paths['keywords']) and os.path.isfile(paths['connect']):
            kws = split_semantic_keywords_raw(_read_text(paths['keywords']))
            links = []
            for line in _read_text(paths['connect']).splitlines():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 2:
                    links.append([parts[0], parts[1], parts[2] if len(parts) > 2 else DEFAULT_LINK_STRENGTH])
            attrs: Dict[str, Dict[str, str]] = {}
            if os.path.isfile(paths['attrs']):
                for line in _read_text(paths['attrs']).splitlines():
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 4:
                        attrs[parts[0]] = {
                            'four_color_type': parts[1],
                            'dmt_level': parts[2],
                            'knowledge_type': parts[3],
                        }
            return {
                'has_result': True,
                'keywords': kws,
                'hierarchy_links': links,
                'keywordFourColorDMT': attrs,
                'key_issues': _read_text(paths['key_issue']),
                'scope_type': scope_type,
                'scope_id': str(scope_id),
                'viewer': _safe_username(username),
            }
        return None
    try:
        with open(paths['meta'], 'r', encoding='utf-8') as f:
            data = json.load(f)
        data['has_result'] = True
        data['key_issues'] = data.get('key_issues') or _read_text(paths['key_issue'])
        data['viewer'] = data.get('viewer') or _safe_username(username)
        return data
    except Exception as exc:
        _log(f'读取 meta 失败: {exc}')
        return None


def update_scope_hierarchy_link_strength(
    scope_type: str,
    scope_id: str,
    *,
    username: str,
    parent: str,
    child: str,
    strength: str,
) -> Dict[str, Any]:
    """手动更新大本体单条层次连边强度，写回 connect 文件 + meta。"""
    parent = (parent or '').strip()
    child = (child or '').strip()
    strength_norm = normalize_link_strength(strength) or DEFAULT_LINK_STRENGTH
    if strength_norm not in LINK_STRENGTHS:
        return {'ok': False, 'msg': f'无效强度: {strength}'}
    if not parent or not child or parent == child:
        return {'ok': False, 'msg': 'parent/child 无效'}

    scope_type = SCOPE_TASK_CLUSTER if scope_type == SCOPE_TASK_CLUSTER else SCOPE_SCENE
    current = load_scope_result(scope_type, scope_id, username)
    if not current or not current.get('has_result'):
        return {'ok': False, 'msg': '尚无大本体结果'}

    links_raw = list(current.get('hierarchy_links') or [])
    if not links_raw:
        paths0 = result_paths(scope_type, scope_id, username)
        if os.path.isfile(paths0['connect']):
            for line in _read_text(paths0['connect']).splitlines():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 2:
                    links_raw.append([
                        parts[0],
                        parts[1],
                        parts[2] if len(parts) > 2 else DEFAULT_LINK_STRENGTH,
                    ])

    normalized: List[List[str]] = []
    for item in links_raw:
        if not item or len(item) < 2:
            continue
        a = str(item[0] or '').strip()
        b = str(item[1] or '').strip()
        if not a or not b or a == b:
            continue
        s = normalize_link_strength(item[2] if len(item) >= 3 else '') or DEFAULT_LINK_STRENGTH
        normalized.append([a, b, s])

    matched_idx = -1
    matched_reverse = False
    for i, (a, b, _s) in enumerate(normalized):
        if a == parent and b == child:
            matched_idx = i
            break
        if a == child and b == parent:
            matched_idx = i
            matched_reverse = True
            break
    if matched_idx < 0:
        return {'ok': False, 'msg': f'未找到连边: {parent}|{child}'}

    if matched_reverse:
        parent_out, child_out = normalized[matched_idx][0], normalized[matched_idx][1]
    else:
        parent_out, child_out = parent, child
    normalized[matched_idx][2] = strength_norm

    paths = result_paths(scope_type, scope_id, username)
    with open(paths['connect'], 'w', encoding='utf-8') as f:
        for a, b, s in normalized:
            f.write(f'{a}|{b}|{s}\n')

    # 同步 meta.json
    meta = dict(current)
    meta['hierarchy_links'] = [[a, b, s] for a, b, s in normalized]
    meta['updated_at'] = datetime.now().isoformat(timespec='seconds')
    meta['has_result'] = True
    with open(paths['meta'], 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    _log(
        f'已更新连边强度 user={paths["username"]} scope={scope_type}:{scope_id} '
        f'{parent_out}|{child_out}|{strength_norm}'
    )
    return {
        'ok': True,
        'msg': 'ok',
        'parent': parent_out,
        'child': child_out,
        'strength': strength_norm,
        'hierarchy_links': meta['hierarchy_links'],
    }


def update_scope_keyword_attrs(
    scope_type: str,
    scope_id: str,
    *,
    username: str,
    keyword: str,
    four_color_type: str = '',
    dmt_level: str = '',
    knowledge_type: str = '',
) -> Dict[str, Any]:
    """手动更新大本体关键词的四色 / DMT / 三类知识。"""
    keyword = (keyword or '').strip()
    if not keyword:
        return {'ok': False, 'msg': 'keyword 无效'}
    scope_type = SCOPE_TASK_CLUSTER if scope_type == SCOPE_TASK_CLUSTER else SCOPE_SCENE
    current = load_scope_result(scope_type, scope_id, username)
    if not current or not current.get('has_result'):
        return {'ok': False, 'msg': '尚无大本体结果'}

    attrs = dict(current.get('keywordFourColorDMT') or {})
    keywords = list(current.get('keywords') or [])
    if keyword not in keywords and keyword not in attrs:
        # 仍允许写入（兼容局部显示池）
        pass
    prev = dict(attrs.get(keyword) or {})
    four = (four_color_type or '').strip().upper() or (prev.get('four_color_type') or '')
    dmt = (dmt_level or '').strip().upper() or (prev.get('dmt_level') or '')
    kt = (knowledge_type or '').strip().lower() or (prev.get('knowledge_type') or '')
    attrs[keyword] = {
        'four_color_type': four,
        'dmt_level': dmt,
        'knowledge_type': kt,
    }

    paths = result_paths(scope_type, scope_id, username)
    # 写 attrs 文件：按 keywords 顺序，再补 attrs 中多余键
    ordered = list(keywords) if keywords else list(attrs.keys())
    for k in attrs.keys():
        if k not in ordered:
            ordered.append(k)
    with open(paths['attrs'], 'w', encoding='utf-8') as f:
        for kw in ordered:
            a = attrs.get(kw) or {}
            f.write(
                f"{kw}|{a.get('four_color_type') or ''}|"
                f"{a.get('dmt_level') or ''}|{a.get('knowledge_type') or ''}\n"
            )

    meta = dict(current)
    meta['keywordFourColorDMT'] = attrs
    meta['updated_at'] = datetime.now().isoformat(timespec='seconds')
    meta['has_result'] = True
    with open(paths['meta'], 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    _log(f'已更新属性 user={paths["username"]} scope={scope_type}:{scope_id} kw={keyword} {four}/{dmt}/{kt}')
    return {
        'ok': True,
        'msg': 'ok',
        'keyword': keyword,
        'four_color_type': four,
        'dmt_level': dmt,
        'knowledge_type': kt,
        'keywordFourColorDMT': attrs,
    }


def rename_scope_keyword(
    scope_type: str,
    scope_id: str,
    *,
    username: str,
    old_keyword: str,
    new_keyword: str,
) -> Dict[str, Any]:
    """大本体关键词重命名（含合并到已有词）；同步词表、属性、连边文件。"""
    old_keyword = (old_keyword or '').strip()
    new_keyword = (new_keyword or '').strip()
    if not old_keyword or not new_keyword:
        return {'ok': False, 'msg': 'old/new keyword 无效'}
    if old_keyword == new_keyword:
        return {'ok': True, 'msg': '无变化', 'need_reanalyze': False}

    scope_type = SCOPE_TASK_CLUSTER if scope_type == SCOPE_TASK_CLUSTER else SCOPE_SCENE
    current = load_scope_result(scope_type, scope_id, username)
    if not current or not current.get('has_result'):
        return {'ok': False, 'msg': '尚无大本体结果'}

    keywords = list(current.get('keywords') or [])
    attrs = dict(current.get('keywordFourColorDMT') or {})
    links_raw = list(current.get('hierarchy_links') or [])

    if old_keyword not in keywords and old_keyword not in attrs:
        return {'ok': False, 'msg': f'未找到关键词: {old_keyword}'}

    merging = new_keyword in keywords or new_keyword in attrs
    # 词表
    new_keywords: List[str] = []
    seen = set()
    for kw in keywords:
        out = new_keyword if kw == old_keyword else kw
        if out in seen:
            continue
        seen.add(out)
        new_keywords.append(out)
    if new_keyword not in seen:
        new_keywords.append(new_keyword)

    # 属性：合并则保留目标词已有属性；非合并则迁移旧属性
    old_attrs = dict(attrs.get(old_keyword) or {})
    if old_keyword in attrs:
        del attrs[old_keyword]
    if merging:
        # 保留 new 已有；若 new 缺字段可用 old 补
        base = dict(attrs.get(new_keyword) or {})
        for field in ('four_color_type', 'dmt_level', 'knowledge_type'):
            if not (base.get(field) or '').strip() and (old_attrs.get(field) or '').strip():
                base[field] = old_attrs[field]
        attrs[new_keyword] = base
        need_reanalyze = False
    else:
        attrs[new_keyword] = old_attrs
        need_reanalyze = not bool(
            (old_attrs.get('four_color_type') or '').strip()
            and (old_attrs.get('dmt_level') or '').strip()
            and (old_attrs.get('knowledge_type') or '').strip()
        )

    # 连边：端点替换；合并后去重
    new_links: List[List[str]] = []
    seen_pairs = set()
    for item in links_raw:
        if not item or len(item) < 2:
            continue
        a = new_keyword if str(item[0]).strip() == old_keyword else str(item[0]).strip()
        b = new_keyword if str(item[1]).strip() == old_keyword else str(item[1]).strip()
        s = str(item[2]).strip() if len(item) >= 3 else DEFAULT_LINK_STRENGTH
        if not a or not b or a == b:
            continue
        key = (a, b)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        new_links.append([a, b, s if s in LINK_STRENGTHS else DEFAULT_LINK_STRENGTH])

    paths = result_paths(scope_type, scope_id, username)
    _write_text(paths['keywords'], '，'.join(new_keywords))
    with open(paths['connect'], 'w', encoding='utf-8') as f:
        for a, b, s in new_links:
            f.write(f'{a}|{b}|{s}\n')
    with open(paths['attrs'], 'w', encoding='utf-8') as f:
        for kw in new_keywords:
            a = attrs.get(kw) or {}
            f.write(
                f"{kw}|{a.get('four_color_type') or ''}|"
                f"{a.get('dmt_level') or ''}|{a.get('knowledge_type') or ''}\n"
            )

    meta = dict(current)
    meta['keywords'] = new_keywords
    meta['keywordFourColorDMT'] = attrs
    meta['hierarchy_links'] = new_links
    meta['updated_at'] = datetime.now().isoformat(timespec='seconds')
    meta['has_result'] = True
    with open(paths['meta'], 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    _log(
        f'已重命名关键词 user={paths["username"]} scope={scope_type}:{scope_id} '
        f'{old_keyword} → {new_keyword} merge={merging}'
    )
    return {
        'ok': True,
        'msg': 'ok',
        'old_keyword': old_keyword,
        'new_keyword': new_keyword,
        'need_reanalyze': need_reanalyze,
        'keywords': new_keywords,
        'keywordFourColorDMT': attrs,
        'hierarchy_links': new_links,
    }


def backup_scope_result(scope_type: str, scope_id: str, username: str) -> Optional[Dict[str, Any]]:
    """重新梳理前备份现有完整结果（供回退）。

    依赖「成功前不落盘覆盖」：磁盘上要么是上一版完整结果，要么尚无结果，
    因此每次重新梳理开始时可安全覆盖备份为当前完整版。
    """
    current = load_scope_result(scope_type, scope_id, username)
    if not current or not current.get('has_result'):
        return None
    # 要求至少有 meta 或 connect，避免残缺半成品被当成可回退点
    paths = result_paths(scope_type, scope_id, username)
    if not os.path.isfile(paths['meta']) and not os.path.isfile(paths['connect']):
        return None
    files = {}
    for key in ('key_issue', 'keywords', 'connect', 'attrs', 'meta'):
        p = paths[key]
        if os.path.isfile(p):
            with open(p, 'r', encoding='utf-8') as f:
                files[key] = f.read()
    if not files:
        return None
    backup = {
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'scope_type': scope_type,
        'scope_id': str(scope_id),
        'viewer': _safe_username(username),
        'files': files,
        'snapshot': current,
    }
    with open(paths['backup'], 'w', encoding='utf-8') as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    _log(f'已备份 {paths["backup"]}')
    return backup


def load_scope_backup(scope_type: str, scope_id: str, username: str) -> Optional[Dict[str, Any]]:
    paths = result_paths(scope_type, scope_id, username)
    if not os.path.isfile(paths['backup']):
        return None
    try:
        with open(paths['backup'], 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def restore_scope_backup(scope_type: str, scope_id: str, username: str) -> Dict[str, Any]:
    backup = load_scope_backup(scope_type, scope_id, username)
    if not backup:
        return {'ok': False, 'msg': '没有可回退的备份'}
    paths = result_paths(scope_type, scope_id, username)
    files = backup.get('files') or {}
    if not files:
        return {'ok': False, 'msg': '备份内容为空'}
    for key, content in files.items():
        p = paths.get(key)
        if not p:
            continue
        os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content if content is not None else '')
    try:
        os.remove(paths['backup'])
    except OSError:
        pass
    return {'ok': True, 'msg': '已回退到梳理前结果'}


def run_full_pipeline(
    *,
    scope_type: str,
    scope_id: str,
    viewer: str,
    set_job_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
    job_key: str = '',
) -> Dict[str, Any]:
    """首次/重新梳理完整流程。"""
    def _set(**kwargs):
        if set_job_fn:
            set_job_fn(job_key, **kwargs)

    def _running() -> bool:
        if is_running_fn:
            return bool(is_running_fn(job_key))
        return True

    close_old_connections()
    scope_type = SCOPE_TASK_CLUSTER if scope_type == SCOPE_TASK_CLUSTER else SCOPE_SCENE
    viewer = (viewer or '').strip()

    # 场景名 / 任务簇名
    scene_name = ''
    sub_names: List[str] = []
    scope_name = ''
    if scope_type == SCOPE_SCENE:
        sid = int(scope_id)
        obj = SceneModel.objects.filter(sid=sid).first()
        if not obj:
            raise RuntimeError(f'场景不存在 sid={sid}')
        scene_name = (obj.sceneDescription or '').strip()
        scope_name = scene_name
        sub_names = list_subscene_names(scene_name)
    else:
        result = load_task_cluster_result(viewer) or {}
        for cl in result.get('clusters') or []:
            if str(cl.get('cluster_id') or '') == str(scope_id):
                scope_name = (cl.get('cluster_name') or str(scope_id)).strip()
                break
        if not scope_name:
            scope_name = str(scope_id)
        # 任务簇：收集其本子所属场景的子场景并集
        selected_preview = select_scope_notebooks(
            scope_type=scope_type, scope_id=scope_id, viewer=viewer,
        )
        scene_names = sorted({(n.get('scene_name') or '').strip() for n in selected_preview if n.get('scene_name')})
        for sn in scene_names:
            for sub in list_subscene_names(sn):
                if sub not in sub_names:
                    sub_names.append(sub)

    _set(phase='select_books', progress_percent=5, message='筛选本子…', running=True)
    selected = select_scope_notebooks(
        scope_type=scope_type, scope_id=scope_id, viewer=viewer, scene_name=scene_name,
    )
    if not selected:
        raise RuntimeError('没有可分析的本子（可见本子经筛选后为空）')

    xx = xx_for_book_count(len(selected))
    _set(
        phase='select_books',
        progress_percent=8,
        message=f'已选 {len(selected)} 本，每本取 {xx} 词',
        selected_books=[n.get('notebook_key') for n in selected],
        xx=xx,
    )

    # —— 步骤(1)(2) 本子并行 ——
    book_blocks: List[Dict[str, Any]] = []

    def _process_one_book(nb_info: Dict[str, Any]) -> Dict[str, Any]:
        close_old_connections()
        try:
            if not _running():
                raise RuntimeError('任务已停止')
            full = nb_info.get('full_username') or nb_info.get('notebook_key')
            notebook = _load_notebook_obj(nb_info)
            has_full = bool(notebook and notebook_has_full_mid_ontology(notebook, full))
            bookdescription = (nb_info.get('bookdescription') or nb_info.get('description') or '').strip()
            docs = list(nb_info.get('documents') or _list_doc_filenames(full))

            if has_full:
                _log(f'{full} 已有完整中本体，跳过浓缩与简化抽词')
                kw_map = {}
                try:
                    kw_map = json.loads(notebook.keywordFourColorDMT or '{}') or {}
                except Exception:
                    kw_map = {}
                picked = select_balanced_keywords_from_map(kw_map, xx)
                if not picked:
                    raise RuntimeError(f'{full} 已有中本体但未能取出关键词')
                key_issues = load_book_key_issues(full, has_full=True)
                return {
                    'notebook_key': full,
                    'bookdescription': bookdescription,
                    'has_full': True,
                    'xx': xx,
                    'key_issues': key_issues,
                    'keywords_with_attrs': picked,
                    'keywords': [k for k, _a in picked],
                }

            # 无完整中本体：简化浓缩 + 简化抽词
            _log(f'{full} 无完整中本体，走简化流程')
            card_rows = run_simplified_condense_for_book(
                full, track_fn=None, is_running_fn=is_running_fn, job_key=job_key,
            )
            if not card_rows:
                raise RuntimeError(f'{full} 简化浓缩后无可用卡片')
            issues, kws = run_simplified_book_keywords(
                full_username=full,
                bookdescription=bookdescription,
                doc_names=docs,
                card_rows=card_rows,
                xx=xx,
                track_fn=None,
                is_running_fn=is_running_fn,
                job_key=job_key,
            )
            return {
                'notebook_key': full,
                'bookdescription': bookdescription,
                'has_full': False,
                'xx': xx,
                'key_issues': issues,
                'keywords_with_attrs': [(k, {}) for k in kws],
                'keywords': kws,
            }
        finally:
            close_old_connections()

    _set(phase='book_prepare', progress_percent=12, message='并行处理各本子（浓缩/取词）…')
    with ThreadPoolExecutor(max_workers=min(MAX_BOOK_PARALLEL, len(selected))) as ex:
        futs = [ex.submit(_process_one_book, nb) for nb in selected]
        for i, fut in enumerate(as_completed(futs), 1):
            if not _running():
                raise RuntimeError('任务已停止')
            block = fut.result()
            book_blocks.append(block)
            pct = 12 + int(40 * i / max(1, len(selected)))
            _set(
                phase='book_prepare',
                progress_percent=min(52, pct),
                message=f'本子处理完成 {i}/{len(selected)}：{block.get("notebook_key")}',
            )

    # 保持与筛本顺序一致
    order = {n.get('notebook_key'): i for i, n in enumerate(selected)}
    book_blocks.sort(key=lambda b: order.get(b.get('notebook_key'), 999))

    if not _running():
        raise RuntimeError('任务已停止')

    # —— 步骤(3) ——
    # 注意：成功前不落盘覆盖正式结果文件，避免失败重跑污染 / 冲掉可回退备份
    _set(phase='scope_keywords', progress_percent=55, message='生成大本体语义关键词…')
    key_issues, keywords = run_scope_keywords(
        scope_type=scope_type,
        scope_name=scope_name,
        sub_names=sub_names,
        book_blocks=book_blocks,
        track_fn=None,
        is_running_fn=is_running_fn,
        job_key=job_key,
    )
    if not keywords:
        raise RuntimeError('大本体语义关键词为空')

    if not _running():
        raise RuntimeError('任务已停止')

    # —— 步骤(4) ——
    _set(phase='scope_connect_attrs', progress_percent=75, message='层次连边与属性分析…')
    links, attrs = run_scope_connect_and_attrs(
        scope_type=scope_type,
        scope_name=scope_name,
        sub_names=sub_names,
        key_issues=key_issues,
        book_descriptions=[b.get('bookdescription') or '' for b in book_blocks],
        keywords=keywords,
        track_fn=None,
        is_running_fn=is_running_fn,
        job_key=job_key,
    )

    meta = {
        'scope_name': scope_name,
        'scene_name': scene_name,
        'sub_scene_names': sub_names,
        'viewer': viewer,
        'selected_books': [
            {
                'notebook_key': b.get('notebook_key'),
                'bookdescription': b.get('bookdescription'),
                'has_full': b.get('has_full'),
                'xx': b.get('xx'),
                'keyword_count': len(b.get('keywords') or []),
            }
            for b in book_blocks
        ],
        'xx_per_book': xx,
        'key_issues': key_issues,
        'last_completed_at': datetime.now().isoformat(timespec='seconds'),
        'pipeline': 'scene_cluster_v1',
    }
    write_scope_results(
        scope_type, scope_id,
        username=viewer,
        key_issues=key_issues,
        keywords=keywords,
        links=links,
        attrs=attrs,
        meta=meta,
    )
    _set(
        phase='completed',
        progress_percent=100,
        message='完成',
        running=False,
        keywords_count=len(keywords),
        links_count=len(links),
    )
    return {
        'ok': True,
        'keywords': keywords,
        'hierarchy_links': [[a, b, s] for a, b, s in links],
        'keywordFourColorDMT': attrs,
        'key_issues': key_issues,
        'meta': meta,
    }
