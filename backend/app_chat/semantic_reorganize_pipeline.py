# encoding=utf-8
"""本子级语义关键词梳理精进流水线（抽样 / 并发抽词+浓缩 / 问题合并 / 补词 / 连边 / 属性）。"""
from __future__ import annotations
import nkcn_public_config as _public_config

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

from openai import OpenAI

from app_chat.keyword_utils import (
    parse_batch_keyword_attributes,
    split_semantic_keywords_raw,
    has_final_marker,
    find_rejected_semantic_keywords,
    DEFAULT_FINAL_MARKERS,
)
from app_chat.models import Card

CLAUDE_REORG_MODEL = 'claude-opus-4.8'
DEEPSEEK_FALLBACK = 'deepseek-v4-pro'
MAX_CARD_WORKERS = 5
MAX_ATTR_WORKERS = 5
ATTR_BATCH_SIZE = 50
SHALLOW_CAP = 40
SHALLOW_RECENT = 10
SHALLOW_RANDOM = 30
WHITE_EXTRA_CAP = 20
TOTAL_CARD_CAP = 60

FINAL_MARKER = '[FINAL]'
PART1_ISSUES = '[PART1_KEY_ISSUES]'
PART2_MERGE = '[PART2_MERGE]'
PART1_ADD = '[PART1_ADD_KEYWORDS]'
PART2_ASSIGN = '[PART2_ASSIGN]'
PART_CONNECTIONS = '[CONNECTIONS]'

# 层次连边强度（无「弱」档：能入边的至少为普通）
LINK_STRENGTH_STRONG = '强'
LINK_STRENGTH_MID = '强中'
LINK_STRENGTH_NORMAL = '普通'
LINK_STRENGTHS = (LINK_STRENGTH_STRONG, LINK_STRENGTH_MID, LINK_STRENGTH_NORMAL)
DEFAULT_LINK_STRENGTH = LINK_STRENGTH_NORMAL

# 层次连边验收：实际覆盖 ≥ 此比例即成功（prompt 仍要求尽量全覆盖，不改文案）
HIERARCHY_MIN_COVERAGE_RATIO = 2.0 / 3.0


def normalize_link_strength(raw: str) -> str:
    """归一化连接强度；无法识别则返回空串（由调用方决定是否默认普通）。"""
    s = (raw or '').strip().replace('　', '')
    if not s:
        return ''
    if s in LINK_STRENGTHS:
        return s
    aliases = {
        '强连接': LINK_STRENGTH_STRONG,
        '强关联': LINK_STRENGTH_STRONG,
        '高强度': LINK_STRENGTH_STRONG,
        '强中等': LINK_STRENGTH_MID,
        '中强': LINK_STRENGTH_MID,
        '中': LINK_STRENGTH_MID,
        '中等': LINK_STRENGTH_MID,
        '较强': LINK_STRENGTH_MID,
        '一般': LINK_STRENGTH_NORMAL,
        '普通强度': LINK_STRENGTH_NORMAL,
        '弱': LINK_STRENGTH_NORMAL,  # 无弱档，兜底为普通
        '较弱': LINK_STRENGTH_NORMAL,
    }
    return aliases.get(s, '')


def _link_strength_prompt_blurb(*, primary_is_topology: bool = True) -> str:
    """连接强度说明（主次分明）。"""
    head = (
        '【次要】顺带为每条边标注连接强度（像神经元连接权重），分三档：强 / 强中 / 普通。'
        if primary_is_topology
        else '为每条已有连边标注连接强度（像神经元连接权重），分三档：强 / 强中 / 普通。'
    )
    return (
        f'{head}\n'
        '- **强（宜少用）**：仅真正的核心骨架、最直接主干父子'
        '（如都江堰→鱼嘴、三类知识→传统知识、五层结构→存在层）。'
        '中层支撑、方法展开、近义/别名/外围挂接**不要**标强。\n'
        '- **强中**：重要支撑/典型下属，紧密但非最顶层主干。\n'
        '- **普通（默认档，应最多）**：合理但较外围的挂接、叶子细节、近义叠词、工具别名、'
        '可有可无的支撑边；拿不准时优先标普通'
        '（不要标「弱」——能入边的至少是普通）。\n'
        '**易偏**：把大量中层边抬成「强」，导致强虚高、普通过少——务必避免。\n'
        '大致比例（参考，勿硬凑个数）：'
        '**强约 10%–20%（宁少勿多）**，强中约 25%–40%，**普通约 40%–55%（应最多）**。\n'
        + (
            '主次：连边是否正确、是否全覆盖远比强度重要；'
            '绝不要为凑强度比例而乱连、漏连或删边。\n'
            if primary_is_topology
            else '不要新增或删除连边；只给已有边打强度；'
            '若自觉「强」明显超过约 20%，应回头把非主干边降为强中或普通。\n'
        )
    )


def _deepseek_client() -> OpenAI:
    api_key = os.environ.get('DEEPSEEK_API_KEY') or _public_config.secret('DEEPSEEK_API_KEY')
    return OpenAI(api_key=api_key, base_url='https://api.deepseek.com', timeout=180.0)


def _claude_client(model_abbr: str = CLAUDE_REORG_MODEL) -> Tuple[OpenAI, str]:
    from app_chat.config.config_manager import config_manager
    model_config = config_manager.get_model_config(model_abbr)
    cur = model_config.get_config()
    headers = cur.get('default_headers') or {'x-foo': 'true'}
    client = OpenAI(
        api_key=cur.get('openai_api_key'),
        base_url=cur.get('openai_api_base'),
        default_headers=headers,
        timeout=300.0,
    )
    return client, model_config.get_full_name() or cur.get('model_name') or model_abbr


def card_condense_dir(username: str) -> str:
    path = os.path.join('.', 'received_dir', 'user_raw_file', username, 'cardCondense')
    os.makedirs(path, exist_ok=True)
    return path


def book_key_issue_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookKeyIssue.txt')


def book_kw_connect_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookKWConnect.txt')


def book_kw_attrs_draft_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookKWAttrsDraft.txt')


def book_kw_attrs_verified_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookKWAttrsVerified.txt')


def book_kw_attrs_diff_path(username: str) -> str:
    return os.path.join(card_condense_dir(username), 'bookKWAttrsDiff.txt')


def card_condense_path(username: str, cid: int) -> str:
    return os.path.join(card_condense_dir(username), f'{cid}.txt')


def _format_attr_line(kw: str, attrs: Optional[Dict[str, str]]) -> str:
    a = attrs or {}
    return (
        f'{kw}|{a.get("four_color_type") or "?"}|'
        f'{a.get("dmt_level") or "?"}|{a.get("knowledge_type") or "?"}'
    )


def write_keyword_attrs_file(
    path: str,
    keywords: List[str],
    attr_map: Dict[str, Dict[str, str]],
    *,
    header: str = '',
) -> str:
    """按关键词顺序写入 词|四色|DMT|三类知识。"""
    lines: List[str] = []
    if header:
        lines.append(header.rstrip() + '\n')
    for kw in keywords:
        lines.append(_format_attr_line(kw, attr_map.get(kw)) + '\n')
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'[semantic_reorganize] 已写属性文件 → {path} 词数={len(keywords)}', flush=True)
    return path


def write_keyword_attrs_diff_file(
    path: str,
    keywords: List[str],
    draft_map: Dict[str, Dict[str, str]],
    verified_map: Dict[str, Dict[str, str]],
) -> int:
    """写入核验相对初判的改动行：词|初判四色/DMT/三类 → 核验四色/DMT/三类。"""
    changed_lines: List[str] = [
        '# 核验相对初判的改动（未改动的词不列出）\n',
        '# 格式：关键词|初判四色|初判DMT|初判三类 → 核验四色|核验DMT|核验三类\n',
    ]
    n = 0
    for kw in keywords:
        a0 = draft_map.get(kw) or {}
        a1 = verified_map.get(kw) or {}
        if (
            a0.get('four_color_type') != a1.get('four_color_type')
            or a0.get('dmt_level') != a1.get('dmt_level')
            or a0.get('knowledge_type') != a1.get('knowledge_type')
        ):
            n += 1
            changed_lines.append(
                f'{kw}|{a0.get("four_color_type") or "?"}|{a0.get("dmt_level") or "?"}|'
                f'{a0.get("knowledge_type") or "?"} → '
                f'{a1.get("four_color_type") or "?"}|{a1.get("dmt_level") or "?"}|'
                f'{a1.get("knowledge_type") or "?"}\n'
            )
    changed_lines.insert(2, f'# 改动条数={n}/{len(keywords)}\n')
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(changed_lines)
    print(
        f'[semantic_reorganize] 已写属性改动对照 → {path} changed={n}/{len(keywords)}',
        flush=True,
    )
    return n


def _split_even_batches(items: List[Any], max_per_batch: int = ATTR_BATCH_SIZE) -> List[List[Any]]:
    """关键词 > max_per_batch 时均分成多份，每份数量尽量接近且不超过上限。"""
    n = len(items)
    if n <= 0:
        return []
    if n <= max_per_batch:
        return [list(items)]
    n_batches = int(math.ceil(n / float(max_per_batch)))
    base = n // n_batches
    rem = n % n_batches
    batches: List[List[Any]] = []
    idx = 0
    for i in range(n_batches):
        sz = base + (1 if i < rem else 0)
        batches.append(list(items[idx:idx + sz]))
        idx += sz
    return batches


def _is_deep_card(card: Card) -> bool:
    return '永久' in (card.type or '') and bool((card.four_color_type or '').strip())


def _is_shallow_card(card: Card) -> bool:
    """浅卡：非永久深卡。"""
    return not _is_deep_card(card)


def _is_white_card(card: Card) -> bool:
    """白卡：尚无四色/DMT 卡片属性。"""
    return not (
        bool((card.four_color_type or '').strip())
        or bool((card.dmt_level or '').strip())
    )


def _card_recency_key(card: Card) -> Tuple[float, int]:
    dt = getattr(card, 'datetime', None)
    if dt is not None:
        try:
            return (float(dt.timestamp()), int(card.cid or 0))
        except Exception:
            pass
    return (0.0, int(card.cid or 0))


def select_reorganize_cards(cards: List[Card]) -> Tuple[List[Card], Dict[str, Any]]:
    """
    浅卡≤40 全取；>40 则最近10 + 其余随机30。
    再从其余白卡中随机最多20张。合计最多60。
    """
    shallow = [c for c in cards if _is_shallow_card(c)]
    if len(shallow) <= SHALLOW_CAP:
        selected_shallow = list(shallow)
        shallow_mode = 'all'
    else:
        shallow_sorted = sorted(shallow, key=_card_recency_key, reverse=True)
        recent = shallow_sorted[:SHALLOW_RECENT]
        recent_ids = {c.cid for c in recent}
        rest = [c for c in shallow if c.cid not in recent_ids]
        random_n = min(SHALLOW_RANDOM, len(rest))
        random_pick = random.sample(rest, random_n) if random_n else []
        selected_shallow = recent + random_pick
        shallow_mode = 'sample40'

    selected_ids = {c.cid for c in selected_shallow}
    white_extra_pool = [
        c for c in cards
        if _is_white_card(c) and c.cid not in selected_ids
    ]
    white_n = min(WHITE_EXTRA_CAP, len(white_extra_pool))
    white_extra = random.sample(white_extra_pool, white_n) if white_n else []

    selected = selected_shallow + white_extra
    if len(selected) > TOTAL_CARD_CAP:
        selected = selected[:TOTAL_CARD_CAP]

    stats = {
        'total_candidates': len(cards),
        'selected': len(selected),
        'skipped': len(cards) - len(selected),
        'shallow_total': len(shallow),
        'shallow_selected': len(selected_shallow),
        'shallow_mode': shallow_mode,
        'white_extra': len(white_extra),
        'sampled': len(selected) < len(cards),
        'pipeline': 'v2_condense_hierarchy',
    }
    print(
        f'[semantic_reorganize] 抽样 shallow={len(shallow)}→{len(selected_shallow)} '
        f'({shallow_mode}) white_extra={len(white_extra)} selected={len(selected)}/{len(cards)}',
        flush=True,
    )
    return selected, stats


def _extract_section(raw: str, start_marker: str, end_markers: Optional[List[str]] = None) -> str:
    text = str(raw or '')
    idx = text.find(start_marker)
    if idx < 0:
        return ''
    body = text[idx + len(start_marker):]
    if end_markers:
        cut = len(body)
        for em in end_markers:
            p = body.find(em)
            if p >= 0:
                cut = min(cut, p)
        body = body[:cut]
    return body.strip()


def _after_final(raw: str) -> str:
    text = str(raw or '')
    idx = text.rfind(FINAL_MARKER)
    if idx < 0:
        # 兼容旧属性标记
        alt = '【最终结果如下】'
        idx_alt = text.rfind(alt)
        if idx_alt >= 0:
            return text[idx_alt + len(alt):].strip()
        return text.strip()
    return text[idx + len(FINAL_MARKER):].strip()


def _ensure_final_marker(raw: str, *, model_tag: str = 'Claude') -> None:
    """输出缺少 [FINAL] 类标记则抛错，供调用失败重试。"""
    if not has_final_marker(raw, DEFAULT_FINAL_MARKERS):
        text = raw if isinstance(raw, str) else str(raw or '')
        print(
            f'[semantic_reorganize] {model_tag} 缺少最终标记 {FINAL_MARKER}（或兼容标记），'
            f'原始输出 chars={len(text)} 如下 ----BEGIN----\n{text}\n----END----',
            flush=True,
        )
        raise RuntimeError(
            f'{model_tag} 输出缺少最终标记 {FINAL_MARKER}（或兼容标记）'
        )


def _ensure_keywords_not_rejected(keywords: List[str], *, context: str = '') -> None:
    """合并/补词解析出的词若含 ≥10 个汉字或反引号 ` ，视为本轮调用异常。"""
    bad = find_rejected_semantic_keywords(keywords)
    if not bad:
        return
    preview = '、'.join(bad[:5])
    more = f'等共{len(bad)}个' if len(bad) > 5 else ''
    prefix = f'{context}: ' if context else ''
    raise RuntimeError(f'{prefix}关键词不合格（≥10汉字或含`）：{preview}{more}')


def call_claude_with_retry_fallback(
    system_prompt: str,
    user_prompt: str,
    *,
    username: Optional[str],
    action: str,
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
    max_tokens: int = 18888,
    temperature: float = 0.4,
    require_final: bool = True,
    validate_raw: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str]:
    """
    Claude 失败重试 1 次；仍失败降级 deepseek-v4-pro（thinking disabled）。
    默认要求输出含 [FINAL]；可另传 validate_raw 做额外验收（不合格则重试）。
    返回 (used_model_abbr, raw_text)。
    """
    if is_running_fn and username and not is_running_fn(username):
        raise RuntimeError('梳理任务已停止')

    def _accept(raw: str, *, model_tag: str) -> str:
        text = (raw or '').strip()
        if not text:
            raise RuntimeError(f'{model_tag} 返回空内容')
        if require_final:
            _ensure_final_marker(text, model_tag=model_tag)
        if validate_raw:
            validate_raw(text)
        return text

    last_err: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            if track_fn:
                track_fn(username, 'claude', action, f'attempt={attempt}/2')
            print(f'[semantic_reorganize] Claude {action} attempt={attempt}/2', flush=True)
            client, model_name = _claude_client(CLAUDE_REORG_MODEL)
            rsp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            raw = _accept(rsp.choices[0].message.content or '', model_tag='Claude')
            return CLAUDE_REORG_MODEL, raw
        except Exception as e:
            last_err = e
            print(f'[semantic_reorganize] Claude {action} 失败 attempt={attempt}/2: {e}', flush=True)

    print(
        f'[semantic_reorganize] Claude {action} 两次失败，降级 {DEEPSEEK_FALLBACK} '
        f'(thinking=disabled) last_err={last_err}',
        flush=True,
    )
    if track_fn:
        track_fn(username, 'deepseek', f'{action}-fallback', str(last_err)[:200])
    if is_running_fn and username and not is_running_fn(username):
        raise RuntimeError('梳理任务已停止')
    client = _deepseek_client()
    rsp = client.chat.completions.create(
        model=DEEPSEEK_FALLBACK,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={'thinking': {'type': 'disabled'}},
    )
    raw = _accept(rsp.choices[0].message.content or '', model_tag=DEEPSEEK_FALLBACK)
    return DEEPSEEK_FALLBACK, raw


def condense_card_content(
    content: str,
    title: str,
    *,
    username: Optional[str] = None,
    cid: Optional[int] = None,
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
) -> str:
    if is_running_fn and username and not is_running_fn(username):
        raise RuntimeError('梳理任务已停止')
    if track_fn:
        track_fn(username, 'deepseek', '卡片浓缩', f'cid={cid}')
    text = (content or '')[:12000]
    prompt = (
        '请将下列卡片内容浓缩为几十字的几句话。'
        '要求：尽可能将卡片内容浓缩涵盖完全；是浓缩不是摘要；只输出浓缩正文，不要标题或说明。\n\n'
        f'卡片标题：{title or "（无）"}\n'
        f'卡片正文：\n{text}'
    )
    client = _deepseek_client()
    rsp = client.chat.completions.create(
        model=DEEPSEEK_FALLBACK,
        messages=[
            {'role': 'system', 'content': '你擅长把长文浓缩成短而全的几句话。'},
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.3,
        max_tokens=400,
        extra_body={'thinking': {'type': 'disabled'}},
    )
    return (rsp.choices[0].message.content or '').strip()


def extract_and_condense_one_card(
    card: Card,
    *,
    keyword_pool: List[str],
    notebook_description: str,
    username: str,
    scene_name: Optional[str],
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    from app_chat.card_keyword_extract import extract_card_semantic_keywords

    close_old_connections()
    try:
        if is_running_fn and not is_running_fn(username):
            raise RuntimeError('梳理任务已停止')

        title = (card.contentTitle or card.title or '')[:200]
        content = card.content or ''

        def _do_extract() -> str:
            close_old_connections()
            try:
                if track_fn:
                    track_fn(username, 'extract', '建卡级语义关键词抽取', f'cid={card.cid}')
                return extract_card_semantic_keywords(
                    content,
                    key_topics=list(keyword_pool),
                    notebook_description=notebook_description,
                    with_candidates=bool(keyword_pool),
                    username=username,
                    scene_name=scene_name,
                )
            finally:
                close_old_connections()

        def _do_condense() -> str:
            close_old_connections()
            try:
                return condense_card_content(
                    content, title,
                    username=username, cid=card.cid,
                    track_fn=track_fn, is_running_fn=is_running_fn,
                )
            finally:
                close_old_connections()

        # 单卡内抽词与浓缩并行
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_kw = ex.submit(_do_extract)
            fut_cd = ex.submit(_do_condense)
            kw_str = fut_kw.result()
            condense = fut_cd.result()

        kws = split_semantic_keywords_raw(kw_str)
        path = card_condense_path(username, int(card.cid))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(condense or '')
        print(
            f'[semantic_reorganize] cid={card.cid} 抽词={len(kws)} 浓缩字数={len(condense or "")} → {path}',
            flush=True,
        )
        return {
            'cid': int(card.cid),
            'title': title,
            'keywords': kws,
            'keywords_str': '，'.join(kws),
            'condense': condense or '',
            'condense_path': path,
        }
    finally:
        close_old_connections()


def run_extract_condense_phase(
    cards: List[Card],
    *,
    username: str,
    scene_name: Optional[str],
    notebook_description: str,
    initial_pool: Optional[List[str]] = None,
    set_job_fn: Optional[Callable] = None,
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    """按批最多5并发抽词+浓缩；同批共用同一备选池快照。单卡失败跳过，不中断整批。"""
    pool: List[str] = list(initial_pool or [])
    results: List[Dict[str, Any]] = []
    failures: List[str] = []
    total = len(cards)
    for start in range(0, total, MAX_CARD_WORKERS):
        if is_running_fn and not is_running_fn(username):
            raise RuntimeError('梳理任务已停止')
        batch = cards[start:start + MAX_CARD_WORKERS]
        pool_snapshot = list(pool)
        print(
            f'[semantic_reorganize] 抽词+浓缩 batch {start + 1}-{start + len(batch)}/{total} '
            f'pool_size={len(pool_snapshot)}',
            flush=True,
        )
        if set_job_fn:
            set_job_fn(
                username,
                phase='extract_condense',
                current_index=start,
                total_cards=total,
                last_action='抽词+浓缩',
                last_action_detail=f'并发处理 {start + 1}-{start + len(batch)}/{total}',
            )

        batch_out: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=MAX_CARD_WORKERS) as ex:
            futs = {
                ex.submit(
                    extract_and_condense_one_card,
                    card,
                    keyword_pool=pool_snapshot,
                    notebook_description=notebook_description,
                    username=username,
                    scene_name=scene_name,
                    track_fn=track_fn,
                    is_running_fn=is_running_fn,
                ): card
                for card in batch
            }
            for fut in as_completed(futs):
                card = futs[fut]
                try:
                    out = fut.result()
                except Exception as exc:
                    err = f'cid={card.cid}: {exc}'
                    failures.append(err)
                    print(f'[semantic_reorganize] 单卡抽词+浓缩失败，跳过 {err}', flush=True)
                    traceback.print_exc()
                    if set_job_fn:
                        set_job_fn(
                            username,
                            current_index=start + len(batch_out) + len(failures),
                            current_cid=card.cid,
                            last_action_detail=f'跳过失败卡 cid={card.cid}',
                        )
                    continue
                batch_out.append(out)
                close_old_connections()
                Card.objects.filter(username=username, cid=card.cid).update(
                    keyWords=out['keywords_str']
                )
                close_old_connections()
                if set_job_fn:
                    set_job_fn(
                        username,
                        current_index=min(total, start + len(batch_out)),
                        current_cid=card.cid,
                        current_title=(out.get('title') or '')[:80],
                    )

        for out in batch_out:
            for kw in out['keywords']:
                if kw and kw not in pool:
                    pool.append(kw)
            results.append(out)

        if set_job_fn:
            set_job_fn(
                username,
                keyword_pool_size=len(pool),
                current_index=min(total, start + len(batch_out)),
            )

    if failures:
        print(
            f'[semantic_reorganize] 抽词+浓缩阶段跳过失败 {len(failures)}/{total}：'
            f'{failures[:5]}{"..." if len(failures) > 5 else ""}',
            flush=True,
        )
        if set_job_fn:
            set_job_fn(
                username,
                extract_failures=len(failures),
                last_action_detail=f'成功 {len(results)}/{total}，失败跳过 {len(failures)}',
            )
    if not results and total > 0:
        raise RuntimeError(
            f'全部 {total} 张卡片抽词+浓缩均失败：' + (failures[0] if failures else '未知错误')
        )

    by_cid = {r['cid']: r for r in results}
    ordered = [by_cid[c.cid] for c in cards if c.cid in by_cid]
    return ordered


def load_card_rows_by_cids(username: str, cids: List[int]) -> List[Dict[str, Any]]:
    """按 cid 从 DB + cardCondense 组装卡片上下文（供迭代时带上历史已梳理卡）。"""
    if not cids:
        return []
    close_old_connections()
    cards = list(Card.objects.filter(username=username, cid__in=cids))
    by_cid = {int(c.cid): c for c in cards}
    rows: List[Dict[str, Any]] = []
    for cid in cids:
        card = by_cid.get(int(cid))
        if not card:
            continue
        title = (card.contentTitle or card.title or '')[:200]
        kw_str = card.keyWords or ''
        kws = split_semantic_keywords_raw(kw_str)
        condense = ''
        p = card_condense_path(username, int(cid))
        if os.path.isfile(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    condense = f.read()
            except OSError:
                condense = ''
        rows.append({
            'cid': int(cid),
            'title': title,
            'keywords': kws,
            'keywords_str': kw_str,
            'condense': condense,
            'condense_path': p,
        })
    close_old_connections()
    return rows


def snapshot_card_condense_files(username: str) -> Dict[str, str]:
    """备份 cardCondense 目录下全部文本文件内容。"""
    d = card_condense_dir(username)
    out: Dict[str, str] = {}
    if not os.path.isdir(d):
        return out
    for name in os.listdir(d):
        path = os.path.join(d, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                out[name] = f.read()
        except OSError as exc:
            print(f'[semantic_reorganize] 备份 cardCondense 跳过 {name}: {exc}', flush=True)
    return out


def restore_card_condense_files(username: str, files: Dict[str, str]) -> int:
    """用备份快照精确恢复 cardCondense（先清空目录内文件再写入）。"""
    d = card_condense_dir(username)
    os.makedirs(d, exist_ok=True)
    removed = 0
    for name in list(os.listdir(d)):
        path = os.path.join(d, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed += 1
            except OSError as exc:
                print(f'[semantic_reorganize] 恢复前删除失败 {name}: {exc}', flush=True)
    written = 0
    for name, content in (files or {}).items():
        safe = os.path.basename(str(name))
        if not safe or safe in ('.', '..'):
            continue
        path = os.path.join(d, safe)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content if content is not None else '')
            written += 1
        except OSError as exc:
            print(f'[semantic_reorganize] 恢复写入失败 {safe}: {exc}', flush=True)
    print(
        f'[semantic_reorganize] 已恢复 cardCondense removed={removed} written={written}',
        flush=True,
    )
    return written


def _merge_card_rows_prefer_new(
    prior_rows: List[Dict[str, Any]],
    new_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """合并历史已梳理卡与本轮新卡；同 cid 以新卡为准。"""
    by_cid: Dict[int, Dict[str, Any]] = {}
    order: List[int] = []
    for row in prior_rows:
        cid = int(row['cid'])
        if cid not in by_cid:
            order.append(cid)
        by_cid[cid] = row
    for row in new_rows:
        cid = int(row['cid'])
        if cid not in by_cid:
            order.append(cid)
        by_cid[cid] = row
    return [by_cid[cid] for cid in order]


def _build_cards_context_block(card_rows: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for row in card_rows:
        parts.append(
            f"===== 卡片 cid={row['cid']} =====\n"
            f"标题(contentTitle)：{row.get('title') or '（无）'}\n"
            f"语义关键词：{row.get('keywords_str') or '（无）'}\n"
            f"浓缩(cid.txt)：\n{row.get('condense') or '（空）'}\n"
        )
    return '\n'.join(parts)


def run_key_issues_and_merge(
    *,
    username: str,
    notebook_description: str,
    card_rows: List[Dict[str, Any]],
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
) -> Tuple[str, Dict[int, List[str]]]:
    from app_chat.views import system_prompt_claude

    system = (
        f'{system_prompt_claude}\n\n'
        '请按人性化思考协议（thinking / checking）完成任务，再给出最终结果。\n'
        '最终结果必须严格按下列标记格式输出（便于程序解析）：\n'
        f'先单独一行 {FINAL_MARKER}\n'
        f'然后 {PART1_ISSUES}\n'
        '（写出本子要解决的核心问题，以及几个子问题；用清晰中文，可分点）\n'
        f'然后 {PART2_MERGE}\n'
        '（卡片之间语义关键词合并同类项结果。注意：只做卡片之间的同义合并，不要在单张卡片内部合并。'
        '因并发抽取，不同卡可能出现基本同义的词，如「组织协同」与「群组协作」、'
        '「传统知识」与「低维知识」——结合各卡浓缩理解后取其一。'
        '仅输出发生改动的卡片；每行格式：cid=<数字>: 词1，词2，词3\n'
        '若无需任何合并改动，PART2 下写一行：无）\n'
    )
    user = (
        f'本子中文名(bookdescription)：{notebook_description or "（未提供）"}\n\n'
        f'以下共 {len(card_rows)} 张已抽词卡片（含标题、关键词、浓缩）：\n\n'
        f'{_build_cards_context_block(card_rows)}\n\n'
        '请完成：①核心问题与子问题；②跨卡片语义关键词同类项合并。'
    )
    def _validate_merge_keywords(raw: str) -> None:
        after = _after_final(raw)
        merge_body = _extract_section(after, PART2_MERGE, None)
        collected: List[str] = []
        for line in (merge_body or '').splitlines():
            line = line.strip()
            if not line or line == '无':
                continue
            m = re.match(r'^cid\s*=\s*(\d+)\s*[:：]\s*(.+)$', line, flags=re.I)
            if not m:
                continue
            collected.extend(split_semantic_keywords_raw(m.group(2)))
        _ensure_keywords_not_rejected(collected, context='合并同类项')

    used, raw = call_claude_with_retry_fallback(
        system, user, username=username, action='核心问题与合并同类项',
        track_fn=track_fn, is_running_fn=is_running_fn, max_tokens=18888,
        validate_raw=_validate_merge_keywords,
    )
    print(f'[semantic_reorganize] key_issues_merge model={used} raw_len={len(raw)}', flush=True)
    after = _after_final(raw)
    issues = _extract_section(after, PART1_ISSUES, [PART2_MERGE])
    merge_body = _extract_section(after, PART2_MERGE, None)
    if not issues:
        # 兜底：FINAL 后整段前半
        issues = after.split(PART2_MERGE)[0].strip() if PART2_MERGE in after else after[:2000]

    issue_path = book_key_issue_path(username)
    with open(issue_path, 'w', encoding='utf-8') as f:
        f.write(issues.strip() + '\n')
    print(f'[semantic_reorganize] 已写 bookKeyIssue.txt → {issue_path}', flush=True)

    updates: Dict[int, List[str]] = {}
    for line in (merge_body or '').splitlines():
        line = line.strip()
        if not line or line == '无':
            continue
        m = re.match(r'^cid\s*=\s*(\d+)\s*[:：]\s*(.+)$', line, flags=re.I)
        if not m:
            continue
        cid = int(m.group(1))
        kws = split_semantic_keywords_raw(m.group(2))
        if kws:
            updates[cid] = kws
    return issues, updates


def apply_keyword_updates(username: str, updates: Dict[int, List[str]], card_rows: List[Dict[str, Any]]) -> None:
    if not updates:
        return
    close_old_connections()
    by_cid = {r['cid']: r for r in card_rows}
    for cid, kws in updates.items():
        kw_str = '，'.join(kws)
        Card.objects.filter(username=username, cid=cid).update(keyWords=kw_str)
        if cid in by_cid:
            by_cid[cid]['keywords'] = kws
            by_cid[cid]['keywords_str'] = kw_str
        print(f'[semantic_reorganize] 更新 cid={cid} keyWords → {kw_str}', flush=True)
    close_old_connections()


def run_enrich_keywords(
    *,
    username: str,
    notebook_description: str,
    book_key_issues: str,
    card_rows: List[Dict[str, Any]],
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
) -> Dict[int, List[str]]:
    from app_chat.views import system_prompt_claude

    system = (
        f'{system_prompt_claude}\n\n'
        '请按人性化思考协议完成任务。根据本子整体性本体语义层次感判断：\n'
        '①是否需要增加少量重要、必要的语义关键词（不宜多）；\n'
        '②若要增加，分别应放到哪些卡片中。\n'
        '参考层次感：要有总有分，如课设→除乘加→车联/纸联/体联除乘加→主题内涵词；'
        '或都江堰→渠首/灌区→鱼嘴/飞沙堰/宝瓶口；三类知识→传统/组织/部落及其细节。'
        '关键词须具体实在，禁空泛词。\n'
        '最终严格格式：\n'
        f'{FINAL_MARKER}\n'
        f'{PART1_ADD}\n'
        '词1，词2（无则写：无）\n'
        f'{PART2_ASSIGN}\n'
        'cid=<数字>: 要追加到该卡的词1，词2\n'
        '（无则写：无；只输出需要追加的卡片）\n'
    )
    user = (
        f'本子中文名(bookdescription)：{notebook_description or "（未提供）"}\n\n'
        f'本子核心问题与子问题：\n{book_key_issues or "（无）"}\n\n'
        f'已处理卡片（标题/关键词/浓缩）共 {len(card_rows)} 张：\n\n'
        f'{_build_cards_context_block(card_rows)}\n'
    )
    def _validate_enrich_keywords(raw: str) -> None:
        after = _after_final(raw)
        assign_body = _extract_section(after, PART2_ASSIGN, None)
        collected: List[str] = []
        for line in (assign_body or '').splitlines():
            line = line.strip()
            if not line or line == '无':
                continue
            m = re.match(r'^cid\s*=\s*(\d+)\s*[:：]\s*(.+)$', line, flags=re.I)
            if not m:
                continue
            collected.extend(split_semantic_keywords_raw(m.group(2)))
        # PART1 新增词列表也检查
        add_body = _extract_section(after, PART1_ADD, [PART2_ASSIGN])
        if add_body and add_body.strip() != '无':
            collected.extend(split_semantic_keywords_raw(add_body.splitlines()[0] if add_body else ''))
        _ensure_keywords_not_rejected(collected, context='补全层次语义关键词')

    used, raw = call_claude_with_retry_fallback(
        system, user, username=username, action='补全层次语义关键词',
        track_fn=track_fn, is_running_fn=is_running_fn, max_tokens=18888,
        validate_raw=_validate_enrich_keywords,
    )
    print(f'[semantic_reorganize] enrich model={used} raw_len={len(raw)}', flush=True)
    after = _after_final(raw)
    assign_body = _extract_section(after, PART2_ASSIGN, None)
    updates: Dict[int, List[str]] = {}
    by_cid = {r['cid']: r for r in card_rows}
    for line in (assign_body or '').splitlines():
        line = line.strip()
        if not line or line == '无':
            continue
        m = re.match(r'^cid\s*=\s*(\d+)\s*[:：]\s*(.+)$', line, flags=re.I)
        if not m:
            continue
        cid = int(m.group(1))
        add_kws = split_semantic_keywords_raw(m.group(2))
        if not add_kws:
            continue
        existing = list(by_cid.get(cid, {}).get('keywords') or [])
        merged = list(existing)
        for kw in add_kws:
            if kw and kw not in merged:
                merged.append(kw)
        updates[cid] = merged
    return updates


def parse_hierarchy_connection_text(
    raw: str,
    all_kws: List[str],
) -> Tuple[List[Tuple[str, str, str]], Dict[str, Any]]:
    """从模型输出解析「父|子」或「父|子|强度」；返回 (links, stats)。

    links 元素为 (父, 子, 强度)；强度可能为空串（模型未给出）。
    """
    after = _after_final(raw)
    body = _extract_section(after, PART_CONNECTIONS, None) or after
    links: List[Tuple[str, str, str]] = []
    seen_pairs: Set[Tuple[str, str]] = set()
    kw_set = set(all_kws)
    pipe_lines = 0
    skipped_not_in_set = 0
    with_strength = 0
    for line in body.splitlines():
        line = line.strip().lstrip('-*• ')
        if not line:
            continue
        line = (
            line.replace('｜', '|')
            .replace('→', '|')
            .replace('->', '|')
            .replace('⇒', '|')
        )
        if '|' not in line:
            continue
        pipe_lines += 1
        line = line.replace('`', '')
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 2:
            continue
        a, b = parts[0], parts[1]
        a = re.sub(r'^\d+[.\、\)]\s+', '', a).strip()
        b = re.sub(r'^\d+[.\、\)]\s+', '', b).strip()
        strength = normalize_link_strength(parts[2]) if len(parts) >= 3 else ''
        if not a or not b or a == b:
            continue
        if kw_set and (a not in kw_set or b not in kw_set):
            skipped_not_in_set += 1
            continue
        pair = (a, b)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        if strength:
            with_strength += 1
        links.append((a, b, strength))

    covered: Set[str] = set()
    for a, b, _s in links:
        covered.add(a)
        covered.add(b)
    orphans = [kw for kw in all_kws if kw not in covered]
    stats: Dict[str, Any] = {
        'pipe_lines': pipe_lines,
        'skipped_not_in_set': skipped_not_in_set,
        'parsed_links': len(links),
        'with_strength': with_strength,
        'covered': len(covered),
        'orphan_count': len(orphans),
        'orphans_preview': orphans[:20],
    }
    return links, stats


def parse_hierarchy_link_strength_text(
    raw: str,
    expected_pairs: List[Tuple[str, str]],
) -> Dict[Tuple[str, str], str]:
    """仅解析「父|子|强度」；只接受 expected_pairs 中的边。"""
    after = _after_final(raw)
    body = _extract_section(after, PART_CONNECTIONS, None) or after
    expected = set(expected_pairs)
    out: Dict[Tuple[str, str], str] = {}
    for line in body.splitlines():
        line = line.strip().lstrip('-*• ')
        if not line:
            continue
        line = (
            line.replace('｜', '|')
            .replace('→', '|')
            .replace('->', '|')
            .replace('⇒', '|')
            .replace('`', '')
        )
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 3:
            continue
        a = re.sub(r'^\d+[.\、\)]\s+', '', parts[0]).strip()
        b = re.sub(r'^\d+[.\、\)]\s+', '', parts[1]).strip()
        strength = normalize_link_strength(parts[2])
        if not a or not b or a == b or not strength:
            continue
        pair = (a, b)
        if pair not in expected:
            continue
        out[pair] = strength
    return out


def _merge_hierarchy_links(
    base: List[Tuple[str, str, str]],
    extra: List[Tuple[str, str, str]],
) -> List[Tuple[str, str, str]]:
    by_pair: Dict[Tuple[str, str], str] = {}
    order: List[Tuple[str, str]] = []
    for a, b, s in list(base) + list(extra):
        if not a or not b or a == b:
            continue
        pair = (a, b)
        if pair not in by_pair:
            by_pair[pair] = s or ''
            order.append(pair)
        elif s and not by_pair[pair]:
            by_pair[pair] = s
    return [(a, b, by_pair[(a, b)]) for a, b in order]


def _hierarchy_coverage_ok(
    links: List[Tuple[str, str, str]],
    all_kws: List[str],
    *,
    min_ratio: float = HIERARCHY_MIN_COVERAGE_RATIO,
) -> Tuple[bool, List[str]]:
    """
    覆盖率达标判定。
    prompt 仍要求尽量全覆盖；验收只要 covered/n ≥ min_ratio（默认 2/3）且至少有边。
    返回 (是否达标, 未入边词列表)。
    """
    if not all_kws:
        return bool(links), []
    if not links:
        return False, list(all_kws)
    covered: Set[str] = set()
    for a, b, _s in links:
        covered.add(a)
        covered.add(b)
    orphans = [kw for kw in all_kws if kw not in covered]
    covered_n = len(all_kws) - len(orphans)
    ok = (covered_n / len(all_kws)) >= float(min_ratio)
    return ok, orphans


def _finalize_link_strengths(
    links: List[Tuple[str, str, str]],
) -> List[Tuple[str, str, str]]:
    """落盘前：缺失强度默认普通。"""
    return [(a, b, s if s in LINK_STRENGTHS else DEFAULT_LINK_STRENGTH) for a, b, s in links]


def _write_book_kw_connect(
    username: str,
    links: List[Tuple[str, str, str]],
) -> str:
    path = book_kw_connect_path(username)
    finalized = _finalize_link_strengths(links)
    with open(path, 'w', encoding='utf-8') as f:
        for a, b, s in finalized:
            f.write(f'{a}|{b}|{s}\n')
    strong = sum(1 for _a, _b, s in finalized if s == LINK_STRENGTH_STRONG)
    mid = sum(1 for _a, _b, s in finalized if s == LINK_STRENGTH_MID)
    normal = sum(1 for _a, _b, s in finalized if s == LINK_STRENGTH_NORMAL)
    print(
        f'[semantic_reorganize] 已写 bookKWConnect.txt 边数={len(finalized)} '
        f'强={strong} 强中={mid} 普通={normal} → {path}',
        flush=True,
    )
    return path


def run_hierarchy_connections(
    *,
    username: str,
    notebook_description: str,
    book_key_issues: str,
    card_rows: List[Dict[str, Any]],
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
) -> List[Tuple[str, str, str]]:
    """
    层次连边分析（顺带强度）。
    - prompt 仍要求尽量全覆盖；验收：边数>0 且覆盖率 ≥ HIERARCHY_MIN_COVERAGE_RATIO（默认 2/3）
    - 未达标 → 视为失败并重试
    - Claude 最多 2 次 → 降级 deepseek-v4-pro；必要时再补一轮「孤立词挂接」
    - 仍不达覆盖率则抛错
    - 返回 (父, 子, 强度)；强度缺省时落盘前补为「普通」
    """
    from app_chat.views import system_prompt_claude

    all_kws: List[str] = []
    seen: Set[str] = set()
    for row in card_rows:
        for kw in row.get('keywords') or []:
            if kw and kw not in seen:
                seen.add(kw)
                all_kws.append(kw)

    n_kw = len(all_kws)
    min_edges_hint = max(n_kw - 1, 1) if n_kw else 1
    min_covered = max(1, math.ceil(n_kw * HIERARCHY_MIN_COVERAGE_RATIO)) if n_kw else 0

    system = (
        f'{system_prompt_claude}\n\n'
        '请按人性化思考协议完成任务。为下方「语义关键词集合」构建层次连边，'
        '整体应看起来像一棵（或少数几棵）语义树/森林：有总有分、上下层次清晰。\n'
        '连边规则（首要）：\n'
        '1. 只连直接上下层（父|子），如「渠首|鱼嘴」「三类知识|传统知识」；'
        '跨层间接不要连（有 A-B、B-C 就不要 A-C）；同层并列不要互连。\n'
        '2. 【硬性覆盖】集合中每一个关键词都必须至少出现在一条边的一端'
        '（作为父或子均可）；不允许留下孤立无边节点。\n'
        f'3. 关键词共 {n_kw} 个，边数通常应接近或超过 {min_edges_hint}'
        '（单树约 N-1；多根森林则各棵树边数之和）。宁可多一些合理的直接父子边，'
        '也不要只给顶层骨架而漏掉大量叶子。\n'
        '4. 父词、子词必须逐字来自关键词集合，禁止改写。\n'
        f'{_link_strength_prompt_blurb(primary_is_topology=True)}'
        '最终严格格式（必须遵守，否则视为失败）：\n'
        f'先单独一行 {FINAL_MARKER}\n'
        f'然后单独一行 {PART_CONNECTIONS}\n'
        '之后每行：父词|子词|强度\n'
        '强度只能是：强 / 强中 / 普通\n'
        '（用英文竖线 | 分隔；不要编号、不要其它说明文字）\n'
        '示例：都江堰|鱼嘴|强\n'
    )
    user = (
        f'本子中文名：{notebook_description or "（未提供）"}\n\n'
        f'核心问题与子问题：\n{book_key_issues or "（无）"}\n\n'
        f'语义关键词集合（共 {n_kw} 个，每个词都必须出现在至少一条边中）：\n'
        + '，'.join(all_kws)
        + '\n\n卡片上下文摘要（标题+关键词+浓缩，供理解层次）：\n'
        + _build_cards_context_block(card_rows)
    )

    def _invoke(model_kind: str, attempt_tag: str, sys_prompt: str, user_prompt: str) -> Tuple[str, str]:
        if is_running_fn and username and not is_running_fn(username):
            raise RuntimeError('梳理任务已停止')
        if model_kind == 'claude':
            if track_fn:
                track_fn(username, 'claude', '层次连边分析', attempt_tag)
            print(f'[semantic_reorganize] Claude 层次连边 {attempt_tag}', flush=True)
            client, model_name = _claude_client(CLAUDE_REORG_MODEL)
            rsp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {'role': 'system', 'content': sys_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                temperature=0.35,
                max_tokens=28888,
            )
            raw = (rsp.choices[0].message.content or '').strip()
            if not raw:
                raise RuntimeError('Claude 返回空内容')
            _ensure_final_marker(raw, model_tag='Claude')
            return CLAUDE_REORG_MODEL, raw
        if track_fn:
            track_fn(username, 'deepseek', '层次连边分析-fallback', attempt_tag)
        print(
            f'[semantic_reorganize] 降级 {DEEPSEEK_FALLBACK} 层次连边 {attempt_tag}',
            flush=True,
        )
        client = _deepseek_client()
        rsp = client.chat.completions.create(
            model=DEEPSEEK_FALLBACK,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            temperature=0.35,
            max_tokens=28888,
            extra_body={'thinking': {'type': 'disabled'}},
        )
        raw = (rsp.choices[0].message.content or '').strip()
        if not raw:
            raise RuntimeError(f'{DEEPSEEK_FALLBACK} 返回空内容')
        _ensure_final_marker(raw, model_tag=DEEPSEEK_FALLBACK)
        return DEEPSEEK_FALLBACK, raw

    def _save_and_return(links: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
        finalized = _finalize_link_strengths(links)
        _write_book_kw_connect(username, finalized)
        return finalized

    schedule = [
        ('claude', 'attempt=1/2'),
        ('claude', 'attempt=2/2'),
        ('deepseek', 'fallback'),
    ]
    last_stats: Dict[str, Any] = {}
    last_raw_len = 0
    last_model = ''
    last_exc: Optional[Exception] = None
    best_links: List[Tuple[str, str, str]] = []
    best_orphans: List[str] = list(all_kws)
    sys_prompt = system
    retry_hint_added = False

    for model_kind, tag in schedule:
        try:
            used, raw = _invoke(model_kind, tag, sys_prompt, user)
        except Exception as exc:
            last_exc = exc
            print(f'[semantic_reorganize] 层次连边调用失败 {tag}: {exc}', flush=True)
            continue
        last_model = used
        last_raw_len = len(raw or '')
        links, stats = parse_hierarchy_connection_text(raw, all_kws)
        last_stats = stats
        ok, orphans = _hierarchy_coverage_ok(links, all_kws)
        covered_n = n_kw - len(orphans)
        coverage_pct = (100.0 * covered_n / n_kw) if n_kw else 0.0
        print(
            f'[semantic_reorganize] connections model={used} raw_len={last_raw_len} '
            f'pipe_lines={stats["pipe_lines"]} skipped_not_in_set={stats["skipped_not_in_set"]} '
            f'links={stats["parsed_links"]} with_strength={stats["with_strength"]} '
            f'covered={covered_n}/{n_kw} ({coverage_pct:.1f}%, 验收≥{HIERARCHY_MIN_COVERAGE_RATIO:.0%}) '
            f'orphans={len(orphans)}',
            flush=True,
        )
        if links and (not best_links or len(orphans) < len(best_orphans)):
            best_links = links
            best_orphans = orphans
        if ok and links:
            print(
                f'[semantic_reorganize] 层次连边验收通过 covered={covered_n}/{n_kw} '
                f'links={len(links)} ({tag} model={used})',
                flush=True,
            )
            return _save_and_return(links)
        reason = (
            '边数=0'
            if not links
            else (
                f'覆盖 {covered_n}/{n_kw}（{coverage_pct:.1f}%）'
                f'未达验收线 {min_covered}/{n_kw}（≥{HIERARCHY_MIN_COVERAGE_RATIO:.0%}），'
                f'仍有 {len(orphans)} 个孤立词'
            )
        )
        print(
            f'[semantic_reorganize] 层次连边未达标（{reason}），按调用失败处理 ({tag} model={used})',
            flush=True,
        )
        if not retry_hint_added:
            preview = '、'.join(orphans[:30]) if orphans else ''
            more = f'等共{len(orphans)}个' if len(orphans) > 30 else ''
            sys_prompt = (
                system
                + '\n【重要重试】上次结果未达标：'
                + (f'存在孤立无边关键词：{preview}{more}。' if orphans else '边数为0。')
                + f'必须让全部 {n_kw} 个词都出现在边上；边数建议 ≥ {min_edges_hint}。'
                '只输出 [FINAL]/[CONNECTIONS] 与父|子行。\n'
            )
            retry_hint_added = True

    # 主循环未返回时：若最好结果已达验收线，直接采用（避免无谓补救/抛错）
    ok_best, best_orphans = _hierarchy_coverage_ok(best_links, all_kws)
    if ok_best and best_links:
        covered_n = n_kw - len(best_orphans)
        print(
            f'[semantic_reorganize] 层次连边采用最佳结果验收通过 '
            f'covered={covered_n}/{n_kw} links={len(best_links)} orphans={len(best_orphans)}',
            flush=True,
        )
        return _save_and_return(best_links)

    # 补救：在已有最好结果上，专补孤立词挂接
    if best_links and best_orphans:
        print(
            f'[semantic_reorganize] 启动孤立词挂接补救：已有边={len(best_links)} '
            f'孤立={len(best_orphans)}',
            flush=True,
        )
        repair_system = (
            f'{system_prompt_claude}\n\n'
            '任务：仅为「尚未入边的孤立语义关键词」补上必要的直接父子连边，'
            '使它们挂到已有层次树上最合适的父节点（或成为合理的父节点挂已有子词）。'
            '不要删改已有边；不要跨层乱连；同层并列不要互连。\n'
            '硬性：下列每个孤立词都必须出现在你新输出的至少一条边中。\n'
            f'{_link_strength_prompt_blurb(primary_is_topology=True)}'
            f'格式：先 {FINAL_MARKER}，再 {PART_CONNECTIONS}，然后每行 父词|子词|强度。\n'
            '父/子必须来自「全量关键词集合」原文；补边强度多为普通或强中。\n'
        )
        repair_user = (
            f'本子中文名：{notebook_description or "（未提供）"}\n\n'
            f'已有连边（勿重复输出也可，但新边不要与之矛盾）：\n'
            + '\n'.join(
                f'{a}|{b}|{s}' if s else f'{a}|{b}'
                for a, b, s in best_links
            )
            + f'\n\n孤立关键词（必须全部挂上，共 {len(best_orphans)} 个）：\n'
            + '，'.join(best_orphans)
            + f'\n\n全量关键词集合（共 {n_kw} 个）：\n'
            + '，'.join(all_kws)
            + '\n\n核心问题与子问题：\n'
            + (book_key_issues or '（无）')
            + '\n\n卡片上下文：\n'
            + _build_cards_context_block(card_rows)
        )
        for model_kind, tag in (('claude', 'orphan-repair-1'), ('deepseek', 'orphan-repair-fallback')):
            try:
                used, raw = _invoke(model_kind, tag, repair_system, repair_user)
            except Exception as exc:
                last_exc = exc
                print(f'[semantic_reorganize] 孤立词挂接失败 {tag}: {exc}', flush=True)
                continue
            extra, stats = parse_hierarchy_connection_text(raw, all_kws)
            merged = _merge_hierarchy_links(best_links, extra)
            ok, orphans = _hierarchy_coverage_ok(merged, all_kws)
            covered_n = n_kw - len(orphans)
            print(
                f'[semantic_reorganize] orphan-repair model={used} '
                f'new_parsed={stats["parsed_links"]} merged={len(merged)} '
                f'covered={covered_n}/{n_kw} orphans={len(orphans)}',
                flush=True,
            )
            best_links = merged
            best_orphans = orphans
            if ok:
                print(
                    f'[semantic_reorganize] 孤立词挂接后验收通过 '
                    f'covered={covered_n}/{n_kw} links={len(merged)}',
                    flush=True,
                )
                return _save_and_return(merged)

    ok_final, orphans_final = _hierarchy_coverage_ok(best_links, all_kws)
    if ok_final and best_links:
        covered_n = n_kw - len(orphans_final)
        print(
            f'[semantic_reorganize] 层次连边最终验收通过 '
            f'covered={covered_n}/{n_kw} links={len(best_links)} orphans={len(orphans_final)}',
            flush=True,
        )
        return _save_and_return(best_links)

    covered_n = n_kw - len(orphans_final) if n_kw else 0
    raise RuntimeError(
        f'层次连边分析失败：覆盖率未达 {HIERARCHY_MIN_COVERAGE_RATIO:.0%} '
        f'（实际 {covered_n}/{n_kw}，孤立 {len(orphans_final)}）。'
        f'model={last_model} raw_len={last_raw_len} stats={last_stats} '
        f'best_links={len(best_links)} best_orphans={len(orphans_final)}'
        + (f' last_exc={last_exc}' if last_exc else '')
    )


def load_hierarchy_links_from_file(username: str) -> List[List[str]]:
    """读取 bookKWConnect；兼容「父|子」与「父|子|强度」。返回 [父,子] 或 [父,子,强度]。"""
    path = book_kw_connect_path(username)
    if not os.path.isfile(path):
        return []
    links: List[List[str]] = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip().replace('｜', '|')
                if '|' not in line:
                    continue
                parts = [p.strip() for p in line.split('|')]
                if len(parts) < 2 or not parts[0] or not parts[1]:
                    continue
                if len(parts) >= 3:
                    s = normalize_link_strength(parts[2])
                    if s:
                        links.append([parts[0], parts[1], s])
                        continue
                links.append([parts[0], parts[1]])
    except Exception as e:
        print(f'[semantic_reorganize] 读取 bookKWConnect 失败: {e}', flush=True)
    return links


def load_hierarchy_link_pairs_from_file(username: str) -> List[Tuple[str, str]]:
    """只取父子对（忽略已有强度），供强度补做。"""
    pairs: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for item in load_hierarchy_links_from_file(username):
        if len(item) < 2:
            continue
        a, b = item[0], item[1]
        pair = (a, b)
        if pair in seen or a == b:
            continue
        seen.add(pair)
        pairs.append(pair)
    return pairs


def run_hierarchy_link_strength_fill(
    *,
    username: str,
    notebook_description: str,
    book_key_issues: str,
    card_rows: List[Dict[str, Any]],
    existing_links: List[Tuple[str, str]],
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str]]]:
    """
    仅补做已有连边的强度；不增删边。
    返回 (带强度的边列表, 模型未给出而默认普通的边列表)。
    """
    from app_chat.views import system_prompt_claude

    if not existing_links:
        return [], []

    all_kws: List[str] = []
    seen: Set[str] = set()
    for row in card_rows:
        for kw in row.get('keywords') or []:
            if kw and kw not in seen:
                seen.add(kw)
                all_kws.append(kw)
    for a, b in existing_links:
        for kw in (a, b):
            if kw and kw not in seen:
                seen.add(kw)
                all_kws.append(kw)

    n_links = len(existing_links)
    system = (
        f'{system_prompt_claude}\n\n'
        '请按人性化思考协议完成任务。\n'
        '【只做强度】下方「已有连边」已经确定，请为每一条边标注连接强度。\n'
        '禁止新增边、禁止删除边、禁止改写父/子词名。\n'
        f'{_link_strength_prompt_blurb(primary_is_topology=False)}'
        '硬性：输出行数应覆盖全部已有连边；漏标的边将无法采用你的判定。\n'
        '最终严格格式：\n'
        f'先单独一行 {FINAL_MARKER}\n'
        f'然后单独一行 {PART_CONNECTIONS}\n'
        '之后每行：父词|子词|强度\n'
        '强度只能是：强 / 强中 / 普通\n'
        '示例：都江堰|鱼嘴|强\n'
    )
    user = (
        f'本子中文名：{notebook_description or "（未提供）"}\n\n'
        f'核心问题与子问题：\n{book_key_issues or "（无）"}\n\n'
        f'语义关键词集合（共 {len(all_kws)} 个，供理解语境）：\n'
        + '，'.join(all_kws)
        + f'\n\n已有连边（共 {n_links} 条，必须全部给出强度，勿增删）：\n'
        + '\n'.join(f'{a}|{b}' for a, b in existing_links)
        + '\n\n提醒：强宜少、普通应最多；拿不准标普通。'
        '\n\n卡片上下文摘要：\n'
        + _build_cards_context_block(card_rows)
    )

    used, raw = call_claude_with_retry_fallback(
        system, user, username=username,
        action='连边强度补做',
        track_fn=track_fn, is_running_fn=is_running_fn,
        max_tokens=28888, temperature=0.25,
    )
    strength_map = parse_hierarchy_link_strength_text(raw, existing_links)
    print(
        f'[semantic_reorganize] 连边强度补做 model={used} '
        f'解析到强度={len(strength_map)}/{n_links}',
        flush=True,
    )

    missing_pairs = [p for p in existing_links if p not in strength_map]
    if missing_pairs:
        print(
            f'[semantic_reorganize] 连边强度仍缺 {len(missing_pairs)}，再补一轮',
            flush=True,
        )
        retry_user = (
            f'本子中文名：{notebook_description or "（未提供）"}\n\n'
            f'以下 {len(missing_pairs)} 条连边尚未给出强度，必须全部补全'
            f'（勿输出已有边、勿新增边）：\n'
            + '\n'.join(f'{a}|{b}' for a, b in missing_pairs)
            + '\n\n语义关键词集合：\n'
            + '，'.join(all_kws)
            + '\n'
        )
        used2, raw2 = call_claude_with_retry_fallback(
            system, retry_user, username=username,
            action='连边强度补缺',
            track_fn=track_fn, is_running_fn=is_running_fn,
            max_tokens=18888, temperature=0.2,
        )
        extra = parse_hierarchy_link_strength_text(raw2, missing_pairs)
        strength_map.update(extra)
        print(
            f'[semantic_reorganize] 连边强度补缺 model={used2} '
            f'本轮补上={len(extra)} 累计={len(strength_map)}/{n_links}',
            flush=True,
        )

    result: List[Tuple[str, str, str]] = []
    still_missing: List[Tuple[str, str]] = []
    for a, b in existing_links:
        s = strength_map.get((a, b), '')
        if s in LINK_STRENGTHS:
            result.append((a, b, s))
        else:
            still_missing.append((a, b))
            result.append((a, b, DEFAULT_LINK_STRENGTH))

    _write_book_kw_connect(username, result)
    return result, still_missing


def build_keyword_attribute_system_prompt() -> str:
    """四色/DMT/三类知识判定 + 都江堰类本子典型反例教训（供分析与核验共用）。"""
    from app_chat.views import system_prompt_claude

    return (
        f'{system_prompt_claude}\n\n'
        '请按人性化思考协议完成任务：为每个语义关键词判定四色、DMT、三类知识。\n'
        '三者是**相互独立的三个维度**，必须分别判断，禁止互相替代或绑定。\n\n'
        '## 〇、三维互不混淆\n'
        '1. **四色 ≠ DMT ≠ 三类知识**。任两维都不是同一回事，也不存在固定映射。\n'
        '2. **DMT 与三类知识尤其禁止混淆**：不是 D↔trad、M↔org、T↔trib。\n'
        '   - D、M、T **各自都可以**出现 trad / org / trib；\n'
        '   - trad、org、trib **各自也都可以**出现 D / M / T。\n'
        '3. 判定时先独立想清三个问题再填：'
        '（语境语言像什么色？）（粒度偏细节/中层/顶层？）（知识显性度与归属偏传统显性知识/组织半显性知识/高维部落隐性知识？）\n\n'
        '## 一、四色（R/B/P/G）——语言/语境维度\n'
        '- **R（红）**：行业/领域专业语言——课程概念、专业知识、学术规范、具名工程构件与专业术语。\n'
        '- **B（蓝）**：技术工具/效率语言——可操作方法、流程、工具、手段、协作机制、可落地规程。\n'
        '- **P（紫）**：场景思维/框架语言——系统性方法论、本体/层次框架、可向下击穿的统领概念'
        '（如都江堰整体框架、三类知识框架、五层结构、除乘加、Palantir本体论）。\n'
        '- **G（绿）**：自然语言——简单而深刻的自然表达、短箴言式表述；'
        '专业术语、工程构件名、框架名、工具/流程名**不宜**标为 G。\n'
        '**本批整体大致比例区间（参考，勿硬凑个数）**：'
        'R 约 25%–40%，B 约 25%–40%，P 约 15%–30%，G 约 5%–15%'
        '（G 通常最少；若专业词被大量标成 G，应回头纠正）。\n\n'
        '## 二、DMT（D/M/T）——粒度/层次维度\n'
        '- **D**：下层细节、具名实体、可直接指认的构件/操作/实例（鱼嘴、卧铁、UML、精准PSI）。\n'
        '- **M**：中层组织与过渡——连接、分类、制度环节、比较结构（岁修分段、知识管理、场知对应）。\n'
        '- **T**：顶层统领框架——能统摄一整枝语义树的大概念（都江堰、三类知识、五层结构、自然本体论）。\n'
        '注意：深刻 ≠ 更抽象 ≠ 必为 T；具体工程细节即使重要也多为 D。\n'
        '**易偏：勿把本可标 D 的具体项抬成 M**（具名实体、单步操作、专名工具等优先 D；'
        '仅真正的中层组织/分类/制度环节才用 M）。\n'
        '**本批整体大致比例区间（参考，勿硬凑个数）**：'
        'D:M:T ≈ 5:3:2，即 D 约 40%–55%，M 约 25%–35%，T 约 15%–25%。\n\n'
        '## 三、三类知识（trad/org/trib）——知识类型维度（与 DMT 不同维）\n'
        '- **trad（传统知识）**：低维显性、可书本/规范固化的一般知识'
        '（构件原理、公式、显性定义、教材概念等）。\n'
        '- **org（组织知识）**：组织治理/协作/责任/流程类半显性知识'
        '（岁修制度、组织协同、公能批改、群组自治等）。\n'
        '- **trib（部落知识）**：高维隐性专家经验/直觉/诀窍'
        '（复合判断、弱关联洞察、难以用规程穷尽的实践智慧等）。\n'
        '**本批整体大致比例区间（参考，勿硬凑个数）**：'
        'trad 约 40%–55%，org 约 25%–35%，trib 约 15%–30%'
        '（trib 通常少于 trad；勿把凡抽象词一律标 trib）。\n'
        '再次强调：三类知识字段与 D/M/T **无对应关系**；'
        '例如一个 D 词可以是 trib，一个 T 词也可以是 trad。\n\n'
        '## 四、共性问题与反例（务必避开）\n'
        '1. **框架词误标蓝/绿**：如「三类知识」「五层结构」「都江堰」「除乘加」应偏 **P+T**，'
        '不要标成 B（工具效率语境）或 G（自然语言）。\n'
        '2. **具名工程构件误标紫/T/trib**：如「鱼嘴」「飞沙堰」「宝瓶口」「卧铁」「杩槎」「百丈堤」'
        '应偏 **R+D+trad**（领域术语 + 细节粒度 + 显性传统知识），'
        '不要当成思维框架，也不要当成部落隐性知识。\n'
        '3. **制度/协作/组织实体误标绿或滥用 trib**：如「岁修制度」「组织协同」「公能批改」「先进小组」'
        '应偏 **B（或必要时 P）+ D/M + org**；组织实体/小组名不要标成 G，也不要无端标成 trib。\n'
        '4. **G 仅用于自然表达**：如「道法自然」「以柔克刚」「借势治水」「深淘滩低作堰」可标 G'
        '（自然语言、简单而深刻）；并再独立判断其 DMT 与三类知识；'
        '技术词、构件名、框架名、组织实体名不要大量标成 G。\n'
        '5. **箴言类宜保留 trib**：如「道法自然」「以柔克刚」等短箴言，常为 G+T+trib；'
        '不要因为「看起来像名言」就一律改成 trad。\n'
        '6. **知识类型名称本身**：「传统知识」「组织知识」「部落知识」是分类概念，'
        '四色偏 **P**，DMT 偏 **M/T**；三类知识字段可分别标 trad/org/trib，'
        '但不要因此把其下辖的工程细节词也一律标成 trib。\n'
        '7. **方法/算法**：如「弯道环流」「离心排沙」「无动力算法」偏 **B + D/M + trad**。\n'
        '8. **慎用 trib**：确属高维隐性经验/实践智慧才用 trib；'
        '教材级显性知识用 trad；流程协作/组织实体用 org；'
        '但箴言与隐性治理智慧不要强行改成 trad。\n\n'
        '## 五、输出格式（必须遵守）\n'
        f'先单独一行 {FINAL_MARKER}\n'
        '之后每行：关键词|四色|DMT|三类知识\n'
        '关键词须与输入原文完全一致（含前导数字，如 6字诀、271教育），勿改写词名。\n'
        '示例（注意三维各自独立组合）：\n'
        '鱼嘴|R|D|trad\n'
        '三类知识|P|T|trib\n'
        '岁修制度|B|M|org\n'
        '先进小组|B|D|org\n'
        '道法自然|G|T|trib\n'
        '深淘滩低作堰|G|M|trad\n'
        '都江堰|P|T|trad\n'
        '知识显性化|B|M|trad\n'
    )


def build_keyword_attribute_verify_system_prompt() -> str:
    """属性核验：补全缺失 + 保守微调；默认保留初判。"""
    from app_chat.views import system_prompt_claude

    return (
        f'{system_prompt_claude}\n\n'
        '你是质检员。下方是一批语义关键词的「初判」四色/DMT/三类知识。\n'
        '请按人性化思考协议做**保守核验**，目标是补全与微调，不是重判重写。\n\n'
        '## 核验原则（必须遵守）\n'
        '1. **默认保留初判**：多数条目应保持不变。\n'
        '2. **必须补全缺失（最高优先级）**：凡标有【缺失需补全】或含 `?` 的行，'
        '必须在输出中给出完整三维判定；词名须与初判行完全一致（含前导数字如 6字诀、271）。'
        '不得因「默认保留」而跳过缺失行；不得输出「无」若仍有缺失。\n'
        '3. **仅做必要微调**：只纠正明确违规；优先单字段微调，避免把整条改成另一套标签。\n'
        '4. **不要大幅重改**：尤其不要把顶层框架词从 P+T 改成 R+D 或 B+D；'
        '不要把「都江堰 / 三类知识 / 除乘加 / 五层结构 / ××本体论 / 传统知识 / 组织知识 / 部落知识」'
        '这类框架或分类总词改掉其合理的 P（及通常的 T/M）。\n'
        '5. **鼓励保留的微调方向**（有则小改，无则勿造）：\n'
        '   - 专业术语误标 G → 改为 R/B/P；\n'
        '   - 制度/协作/组织实体（如先进小组）误标 G 或 trib → 改为 org，四色偏 B；\n'
        '   - 具名工程构件误标 P/T/trib → 改为 R+D+trad；\n'
        '   - 明显滥用 trib 的显性教材概念 → trad；流程协作 → org；\n'
        '   - 具体项误抬 M → 降回 D（具名实体/单步操作/专名工具）。\n'
        '6. **不要乱改的方向**：\n'
        '   - 短箴言/自然智慧（道法自然、以柔克刚等）若初判为 G+T+trib，通常应保留 trib，勿改成 trad；\n'
        '   - 「深淘滩低作堰」类治水箴言标 G 是合理的，不要改成 B。\n'
        '7. **三维互不混淆**：四色 ≠ DMT ≠ 三类知识；'
        'D/M/T 各自都可有 trad/org/trib，三类知识各自也都可以有 D/M/T；'
        '禁止 D↔trad、M↔org、T↔trib 的错误对应。\n\n'
        '## 输出要求\n'
        '**必须输出全部缺失行的完整判定**；另外只再输出需要微调的行；'
        '完全正确、无需改动的词不要输出。\n'
        '关键词原文照抄（含数字前缀）。\n'
        f'先单独一行 {FINAL_MARKER}\n'
        '之后每行：关键词|四色|DMT|三类知识\n'
        '若本批无需任何改动、也无缺失，则在 [FINAL] 后单独一行写：无\n'
    )


def _attr_fields_complete(attrs: Optional[Dict[str, str]]) -> bool:
    if not attrs:
        return False
    return bool(
        (attrs.get('four_color_type') or '').strip()
        and (attrs.get('dmt_level') or '').strip()
        and (attrs.get('knowledge_type') or '').strip()
    )


def _merge_verify_overlay(
    batch: List[str],
    draft: Dict[str, Dict[str, str]],
    overlay: Dict[str, Dict[str, str]],
) -> Tuple[Dict[str, Dict[str, str]], int, int]:
    """
    以初判为底：缺失字段用核验补全；核验给出的行做覆盖微调。
    返回 (merged, filled_count, changed_count)。
    """
    merged: Dict[str, Dict[str, str]] = {}
    filled = 0
    changed = 0
    for kw in batch:
        base = dict(draft.get(kw) or {})
        ov = overlay.get(kw) or {}
        before_complete = _attr_fields_complete(base)
        out = dict(base)
        # 先补缺失
        for field in ('four_color_type', 'dmt_level', 'knowledge_type'):
            if not (out.get(field) or '').strip() and (ov.get(field) or '').strip():
                out[field] = ov[field]
                filled += 1
        # 再应用核验给出的微调（整行覆盖已有字段）
        if ov:
            for field in ('four_color_type', 'dmt_level', 'knowledge_type'):
                if (ov.get(field) or '').strip():
                    out[field] = ov[field]
        if before_complete and (
            base.get('four_color_type') != out.get('four_color_type')
            or base.get('dmt_level') != out.get('dmt_level')
            or base.get('knowledge_type') != out.get('knowledge_type')
        ):
            changed += 1
        elif (not before_complete) and _attr_fields_complete(out):
            filled += 0  # already counted per-field; mark as filled row via filled
        merged[kw] = out
    return merged, filled, changed


def run_attribute_analysis_concurrent(
    keywords: List[str],
    notebook_description: str,
    *,
    username: str,
    set_job_fn: Optional[Callable] = None,
    track_fn: Optional[Callable] = None,
    is_running_fn: Optional[Callable] = None,
) -> Dict[str, Dict[str, str]]:
    if not keywords:
        return {}

    def _analyze_batch(batch: List[str], batch_index: int) -> Dict[str, Dict[str, str]]:
        close_old_connections()
        try:
            if is_running_fn and not is_running_fn(username):
                raise RuntimeError('梳理任务已停止')
            system = build_keyword_attribute_system_prompt()
            kw_block = '\n'.join(f'- {kw}' for kw in batch)
            user = (
                f'本子描述：{notebook_description or "未提供"}\n\n'
                f'待分析关键词（共 {len(batch)} 个）：\n{kw_block}\n'
            )
            used, raw = call_claude_with_retry_fallback(
                system, user, username=username,
                action=f'属性分析batch{batch_index}',
                track_fn=track_fn, is_running_fn=is_running_fn,
                max_tokens=18888, temperature=0.25,
            )
            parsed = parse_batch_keyword_attributes(raw, batch, final_marker=FINAL_MARKER)
            if not parsed:
                parsed = parse_batch_keyword_attributes(raw, batch, final_marker='【最终结果如下】')
            print(
                f'[semantic_reorganize] 属性分析 batch={batch_index} model={used} '
                f'解析 {len(parsed)}/{len(batch)}',
                flush=True,
            )
            return parsed
        finally:
            close_old_connections()

    def _parse_attr_overlay(raw: str, expected: List[str]) -> Dict[str, Dict[str, str]]:
        parsed = parse_batch_keyword_attributes(raw, expected, final_marker=FINAL_MARKER)
        if not parsed:
            parsed = parse_batch_keyword_attributes(raw, expected, final_marker='【最终结果如下】')
        return parsed

    def _verify_call(
        batch: List[str],
        draft: Dict[str, Dict[str, str]],
        batch_index: int,
        *,
        missing_only: bool = False,
        attempt: int = 1,
    ) -> Dict[str, Dict[str, str]]:
        """核验一轮：补缺失 + 保守微调。missing_only 时只送仍缺词，强制补全。"""
        system = build_keyword_attribute_verify_system_prompt()
        focus = (
            [kw for kw in batch if not _attr_fields_complete(draft.get(kw))]
            if missing_only
            else list(batch)
        )
        if not focus:
            return dict(draft)
        missing = [kw for kw in focus if not _attr_fields_complete(draft.get(kw))]
        lines = []
        for kw in focus:
            attrs = draft.get(kw) or {}
            fc = attrs.get('four_color_type') or '?'
            dmt = attrs.get('dmt_level') or '?'
            kt = attrs.get('knowledge_type') or '?'
            mark = '  【缺失需补全】' if kw in missing else ''
            lines.append(f'{kw}|{fc}|{dmt}|{kt}{mark}')
        if missing_only:
            user = (
                f'本子描述：{notebook_description or "未提供"}\n\n'
                f'以下 {len(missing)} 条仍缺失，必须全部补全三维判定'
                f'（词名原文照抄，含数字前缀）：\n'
                + '\n'.join(lines)
                + '\n\n禁止输出「无」；必须输出上述每一词的完整行。\n'
            )
            action = f'属性核验补缺失batch{batch_index}-try{attempt}'
        else:
            user = (
                f'本子描述：{notebook_description or "未提供"}\n\n'
                f'初判结果（共 {len(focus)} 条；其中缺失 {len(missing)} 条必须补全；'
                f'其余默认保留，仅对明确违规做保守微调）：\n'
                + '\n'.join(lines)
                + '\n\n请输出全部缺失行的完整判定，以及需要微调的行；'
                '无需改动的不要输出。若有缺失禁止写「无」。\n'
            )
            action = f'属性核验batch{batch_index}-try{attempt}'
        used, raw = call_claude_with_retry_fallback(
            system, user, username=username,
            action=action,
            track_fn=track_fn, is_running_fn=is_running_fn,
            max_tokens=18888, temperature=0.15,
        )
        after = _after_final(raw)
        if after.strip() == '无':
            if missing:
                print(
                    f'[semantic_reorganize] 属性核验 batch={batch_index} '
                    f'attempt={attempt} model={used} 误答「无」但缺失={len(missing)}',
                    flush=True,
                )
                return dict(draft)
            print(
                f'[semantic_reorganize] 属性核验 batch={batch_index} '
                f'attempt={attempt} model={used} 无改动',
                flush=True,
            )
            return dict(draft)
        parsed = _parse_attr_overlay(raw, focus)
        if not parsed:
            print(
                f'[semantic_reorganize] 属性核验 batch={batch_index} '
                f'attempt={attempt} model={used} 解析为空，保留当前底稿',
                flush=True,
            )
            return dict(draft)
        # 合并：整批核验按 batch；仅补缺失时以 draft 为底只更新 focus
        merge_keys = batch if not missing_only else focus
        full_draft = dict(draft)
        merged, filled, changed = _merge_verify_overlay(merge_keys, full_draft, parsed)
        if missing_only:
            out = dict(draft)
            out.update(merged)
            merged = out
        print(
            f'[semantic_reorganize] 属性核验 batch={batch_index} '
            f'attempt={attempt} missing_only={missing_only} model={used} '
            f'覆盖行={len(parsed)} 微调={changed} 补全字段≈{filled} '
            f'缺失前={len(missing)}',
            flush=True,
        )
        return merged

    def _verify_batch(
        batch: List[str],
        draft: Dict[str, Dict[str, str]],
        batch_index: int,
    ) -> Dict[str, Dict[str, str]]:
        close_old_connections()
        try:
            if is_running_fn and not is_running_fn(username):
                raise RuntimeError('梳理任务已停止')
            merged = _verify_call(batch, draft, batch_index, missing_only=False, attempt=1)
            # 核验阶段内重试补全仍缺词（不另起初判炉灶）
            still = [kw for kw in batch if not _attr_fields_complete(merged.get(kw))]
            if still:
                print(
                    f'[semantic_reorganize] 属性核验 batch={batch_index} '
                    f'首轮后仍缺 {len(still)}，核验内再补一次',
                    flush=True,
                )
                merged = _verify_call(
                    batch, merged, batch_index, missing_only=True, attempt=2,
                )
                still2 = [kw for kw in batch if not _attr_fields_complete(merged.get(kw))]
                if still2:
                    print(
                        f'[semantic_reorganize] 属性核验 batch={batch_index} '
                        f'补全后仍缺 {len(still2)}: {still2[:8]}'
                        + ('...' if len(still2) > 8 else ''),
                        flush=True,
                    )
            return merged
        finally:
            close_old_connections()

    batches = _split_even_batches(keywords, ATTR_BATCH_SIZE)
    print(
        f'[semantic_reorganize] 属性分析+保守核验 keywords={len(keywords)} '
        f'batches={len(batches)} sizes={[len(b) for b in batches]} '
        f'max_workers={MAX_ATTR_WORKERS}',
        flush=True,
    )

    # 阶段1：分批并发初判
    draft_by_batch: Dict[int, Dict[str, Dict[str, str]]] = {}
    with ThreadPoolExecutor(max_workers=MAX_ATTR_WORKERS) as ex:
        futs = {
            ex.submit(_analyze_batch, batch, idx + 1): (idx, batch)
            for idx, batch in enumerate(batches)
        }
        done_kw = 0
        for fut in as_completed(futs):
            idx, batch = futs[fut]
            draft_by_batch[idx] = fut.result()
            done_kw += len(batch)
            if set_job_fn:
                set_job_fn(
                    username,
                    phase='attributes',
                    total_keywords=len(keywords),
                    attr_batch_end=min(done_kw, len(keywords)),
                    last_action='属性分析',
                    last_action_detail=f'初判约 {done_kw}/{len(keywords)} 词',
                )

    draft_map: Dict[str, Dict[str, str]] = {}
    for idx in range(len(batches)):
        draft_map.update(draft_by_batch.get(idx) or {})
    write_keyword_attrs_file(
        book_kw_attrs_draft_path(username),
        keywords,
        draft_map,
        header='# 并发初判结果 格式：关键词|四色|DMT|三类知识',
    )

    # 阶段2：各批再并发保守核验（补缺失 + 微调）
    if set_job_fn:
        set_job_fn(
            username,
            phase='attributes',
            last_action='属性核验',
            last_action_detail=f'开始保守核验 {len(batches)} 批',
            attr_batch_end=0,
        )
    results: Dict[str, Dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=MAX_ATTR_WORKERS) as ex:
        futs = {
            ex.submit(
                _verify_batch,
                batches[idx],
                draft_by_batch.get(idx) or {},
                idx + 1,
            ): (idx, batches[idx])
            for idx in range(len(batches))
        }
        done_kw = 0
        for fut in as_completed(futs):
            idx, batch = futs[fut]
            part = fut.result()
            results.update(part)
            done_kw += len(batch)
            if set_job_fn:
                set_job_fn(
                    username,
                    phase='attributes',
                    total_keywords=len(keywords),
                    attr_batch_end=min(done_kw, len(keywords)),
                    last_action='属性核验',
                    last_action_detail=f'核验约 {done_kw}/{len(keywords)} 词',
                )

    # 阶段3：跨批仍有缺失时，在核验流程内再补一轮（仍用核验 prompt，不另起初判）
    still_missing = [kw for kw in keywords if not _attr_fields_complete(results.get(kw))]
    if still_missing:
        if set_job_fn:
            set_job_fn(
                username,
                phase='attributes',
                last_action='属性核验',
                last_action_detail=f'核验内补全仍缺 {len(still_missing)} 词',
            )
        print(
            f'[semantic_reorganize] 属性核验终轮补缺失：{len(still_missing)} 词',
            flush=True,
        )
        fill_batches = _split_even_batches(still_missing, ATTR_BATCH_SIZE)

        def _verify_missing_batch(batch: List[str], batch_index: int) -> Dict[str, Dict[str, str]]:
            close_old_connections()
            try:
                if is_running_fn and not is_running_fn(username):
                    raise RuntimeError('梳理任务已停止')
                return _verify_call(
                    batch,
                    {kw: results.get(kw) or {} for kw in batch},
                    batch_index,
                    missing_only=True,
                    attempt=3,
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=MAX_ATTR_WORKERS) as ex:
            futs = {
                ex.submit(_verify_missing_batch, batch, 800 + idx + 1): batch
                for idx, batch in enumerate(fill_batches)
            }
            for fut in as_completed(futs):
                batch = futs[fut]
                part = fut.result() or {}
                for kw in batch:
                    if _attr_fields_complete(part.get(kw)):
                        results[kw] = part[kw]
                    elif part.get(kw):
                        entry = dict(results.get(kw) or {})
                        for field in ('four_color_type', 'dmt_level', 'knowledge_type'):
                            if not (entry.get(field) or '').strip() and (
                                (part[kw].get(field) or '').strip()
                            ):
                                entry[field] = part[kw][field]
                        results[kw] = entry
        still_missing2 = [kw for kw in keywords if not _attr_fields_complete(results.get(kw))]
        print(
            f'[semantic_reorganize] 属性核验终轮后仍缺 {len(still_missing2)}/{len(keywords)}',
            flush=True,
        )

    write_keyword_attrs_file(
        book_kw_attrs_verified_path(username),
        keywords,
        results,
        header='# 保守核验后结果 格式：关键词|四色|DMT|三类知识',
    )
    write_keyword_attrs_diff_file(
        book_kw_attrs_diff_path(username),
        keywords,
        draft_map,
        results,
    )
    return results


def collect_union_keywords(card_rows: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for row in card_rows:
        for kw in row.get('keywords') or []:
            if kw and kw not in seen:
                seen.add(kw)
                out.append(kw)
    return out


def run_full_pipeline(
    *,
    username: str,
    scene_name: Optional[str],
    notebook_description: str,
    cards: List[Card],
    selection_stats: Dict[str, Any],
    incremental: bool,
    existing_map: Dict[str, Dict[str, str]],
    preserved_keyword_map: Dict[str, Dict[str, str]],
    all_cards: List[Card],
    initial_pool: Optional[List[str]],
    prior_selected_cids: Optional[List[int]] = None,
    set_job_fn: Callable,
    track_fn: Callable,
    is_running_fn: Callable,
    save_state_fn: Callable,
    notebook: Any,
) -> Dict[str, Any]:
    """执行精进梳理全流程，返回 meta 片段。"""
    total = len(cards)
    prior_selected_cids = [int(x) for x in (prior_selected_cids or [])]
    if total <= 0:
        print('[semantic_reorganize] 无待处理卡片，跳过流水线', flush=True)
        set_job_fn(
            username,
            running=True,
            phase='attributes',
            mode='incremental' if incremental else 'full',
            total_cards=0,
            selected_cards=0,
            skipped_cards=selection_stats.get('skipped', 0),
            card_selection=selection_stats,
            total_keywords=0,
            last_action='无待处理卡片',
            last_action_detail='抽样结果为空',
        )
        prior_links = load_hierarchy_links_from_file(username)
        return {
            'final_map': dict(existing_map or {}) if incremental else dict(preserved_keyword_map or {}),
            'meta_partial': {
                'processed_cids': [],
                'reorganize_selected_cids': list(prior_selected_cids),
                'last_completed_at': datetime.now().isoformat(timespec='seconds'),
                'last_mode': 'incremental' if incremental else 'full',
                'sampled': bool(selection_stats.get('sampled')),
                'card_selection': selection_stats,
                'hierarchy_links': prior_links,
                'pipeline': 'v2_condense_hierarchy',
                'book_key_issue_path': book_key_issue_path(username),
                'book_kw_connect_path': book_kw_connect_path(username),
            },
            'newly_processed_cids': [],
            'reorganize_selected_cids': list(prior_selected_cids),
            'keyword_count': len(existing_map or {}) if incremental else 0,
            'hierarchy_links': prior_links,
        }

    set_job_fn(
        username,
        running=True,
        phase='extract_condense',
        mode='incremental' if incremental else 'full',
        total_cards=total,
        selected_cards=total,
        skipped_cards=selection_stats.get('skipped', 0),
        card_selection=selection_stats,
        current_index=0,
        error='',
        last_action='抽词+浓缩',
        last_action_detail=f'共 {total} 张，最大并发 {MAX_CARD_WORKERS}',
    )

    card_rows = run_extract_condense_phase(
        cards,
        username=username,
        scene_name=scene_name,
        notebook_description=notebook_description,
        initial_pool=initial_pool,
        set_job_fn=set_job_fn,
        track_fn=track_fn,
        is_running_fn=is_running_fn,
    )

    # 刷新关键词字符串（DB 已更新）
    for row in card_rows:
        c = Card.objects.filter(username=username, cid=row['cid']).values('keyWords').first()
        if c:
            row['keywords_str'] = c.get('keyWords') or row['keywords_str']
            row['keywords'] = split_semantic_keywords_raw(row['keywords_str'])

    newly_cids = [r['cid'] for r in card_rows]
    # 迭代：带上历史已梳理卡，避免只用本批重写全书核心问题/连边
    if incremental and prior_selected_cids:
        prior_only = [c for c in prior_selected_cids if c not in set(newly_cids)]
        prior_rows = load_card_rows_by_cids(username, prior_only)
        analysis_rows = _merge_card_rows_prefer_new(prior_rows, card_rows)
        print(
            f'[semantic_reorganize] 迭代全书级分析上下文 '
            f'prior={len(prior_rows)} new={len(card_rows)} union={len(analysis_rows)}',
            flush=True,
        )
    else:
        analysis_rows = list(card_rows)

    selected_union = sorted({int(r['cid']) for r in analysis_rows})

    set_job_fn(
        username,
        phase='key_issues_merge',
        last_action='核心问题与合并同类项',
        last_action_detail=f'Claude 分析中…（{len(analysis_rows)} 张）',
        current_index=total,
    )
    issues, merge_updates = run_key_issues_and_merge(
        username=username,
        notebook_description=notebook_description,
        card_rows=analysis_rows,
        track_fn=track_fn,
        is_running_fn=is_running_fn,
    )
    apply_keyword_updates(username, merge_updates, analysis_rows)

    set_job_fn(
        username,
        phase='enrich',
        last_action='补全层次语义关键词',
        last_action_detail='Claude 分析中…',
    )
    for row in analysis_rows:
        p = card_condense_path(username, row['cid'])
        if os.path.isfile(p):
            with open(p, 'r', encoding='utf-8') as f:
                row['condense'] = f.read()
    enrich_updates = run_enrich_keywords(
        username=username,
        notebook_description=notebook_description,
        book_key_issues=issues,
        card_rows=analysis_rows,
        track_fn=track_fn,
        is_running_fn=is_running_fn,
    )
    apply_keyword_updates(username, enrich_updates, analysis_rows)

    set_job_fn(
        username,
        phase='connect',
        last_action='层次连边分析',
        last_action_detail='Claude 分析中…',
    )
    links = run_hierarchy_connections(
        username=username,
        notebook_description=notebook_description,
        book_key_issues=issues,
        card_rows=analysis_rows,
        track_fn=track_fn,
        is_running_fn=is_running_fn,
    )
    hierarchy_links = [[a, b, s] for a, b, s in links]

    keyword_list = collect_union_keywords(analysis_rows)
    set_job_fn(
        username,
        phase='attributes',
        total_keywords=len(keyword_list),
        attr_batch_end=0,
        last_action='四色/DMT/三类知识分析',
        last_action_detail=f'共 {len(keyword_list)} 词，最大 {MAX_ATTR_WORKERS} 并发批',
    )
    # 迭代：已有属性的词可跳过，只分析缺失项，降低重复调用
    if incremental and existing_map:
        need_attr = [
            kw for kw in keyword_list
            if not (existing_map.get(kw) or {}).get('four_color_type')
            or not (existing_map.get(kw) or {}).get('dmt_level')
            or not (existing_map.get(kw) or {}).get('knowledge_type')
        ]
    else:
        need_attr = list(keyword_list)
    attr_results = run_attribute_analysis_concurrent(
        need_attr,
        notebook_description,
        username=username,
        set_job_fn=set_job_fn,
        track_fn=track_fn,
        is_running_fn=is_running_fn,
    ) if need_attr else {}

    final_map: Dict[str, Dict[str, str]] = {}
    if incremental:
        final_map = dict(existing_map or {})
        for kw, attrs in (attr_results or {}).items():
            entry = dict(final_map.get(kw) or {})
            entry.update({k: v for k, v in attrs.items() if v})
            final_map[kw] = entry
        for kw in keyword_list:
            final_map.setdefault(kw, final_map.get(kw) or {})
        # 图谱只用新梳理选中卡：去掉不再属于 selected 语义空间的旧词属性也可保留在 map 里无妨；
        # 前端按 selected 卡过滤节点。这里额外清理：仅保留 analysis 关键词 + 仍被选中卡使用的词
        keep = set(keyword_list)
        final_map = {k: v for k, v in final_map.items() if k in keep}
    else:
        for kw, attrs in (attr_results or {}).items():
            final_map[kw] = dict(attrs or {})
        for kw in keyword_list:
            final_map.setdefault(kw, {})
        # 全量抽样：未入选卡的旧词不再进入属性库（图谱也不再展示旧词）
        # 不再把 preserved_keyword_map 中未抽样卡的旧词并入 final_map

    meta = {
        'processed_cids': None,  # filled by caller
        'reorganize_selected_cids': selected_union,
        'last_completed_at': datetime.now().isoformat(timespec='seconds'),
        'last_mode': 'incremental' if incremental else 'full',
        'sampled': bool(selection_stats.get('sampled')),
        'card_selection': selection_stats,
        'hierarchy_links': hierarchy_links,
        'pipeline': 'v2_condense_hierarchy',
        'book_key_issue_path': book_key_issue_path(username),
        'book_kw_connect_path': book_kw_connect_path(username),
    }
    return {
        'final_map': final_map,
        'meta_partial': meta,
        'newly_processed_cids': newly_cids,
        'reorganize_selected_cids': selected_union,
        'keyword_count': len(keyword_list),
        'hierarchy_links': hierarchy_links,
    }
