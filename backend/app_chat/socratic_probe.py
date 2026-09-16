# -*- coding: utf-8 -*-
"""窗口问答「是否先反问」判定（deepseek-v4-flash）。

严格流程约定见产品需求：
- 输入：本子名、（若做过语义梳理）核心问题/语义关键词150/层次连线、近期问答卡提问链、当前问题
- 输出：≤50字分析 + [FINAL] + 是/否
- 连续反问最多两次（第三次强制否）
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from openai import OpenAI

FINAL_MARKER = '[FINAL]'
PROBE_MODEL_ABBR = 'deepseek-v4-flash'
KEYWORD_TAKE = 150
RECENT_QA_CARD_LIMIT = 10
MAX_CONSECUTIVE_COUNTER = 2
_PROBE_CACHE_TTL_SEC = 120.0
PRESUMMARY_MAX_DOCS = 3
PRESUMMARY_MAX_CHARS_EACH = 1800
PREV_ANSWER_MAX_CHARS = 2500

_LOCK = threading.Lock()
# streak_key(=notebook username) -> 连续已生效反问次数
_COUNTER_STREAK: Dict[str, int] = {}
# 以「本子 + 原问题」去重：同一轮多窗口/不同 ctx 只判定一次、只计一次
# key = (streak_key, msg_fp) -> {ts, result}
_RESULT_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}
_INFLIGHT: Dict[Tuple[str, str], threading.Event] = {}
_INFLIGHT_RESULTS: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _msg_fp(message: str) -> str:
    raw = (message or '').strip().encode('utf-8')
    return hashlib.sha1(raw).hexdigest()[:20] if raw else 'empty'


def _streak_file_path(streak_key: str) -> str:
    """放到子目录，避免出现在「文档导入区」根目录列表里。"""
    safe = str(streak_key or '').strip() or '_unknown'
    return os.path.join(
        '.', 'received_dir', 'user_raw_file', safe, '_socratic_meta', 'socratic_counter_streak.json',
    )


def _legacy_streak_file_path(streak_key: str) -> str:
    safe = str(streak_key or '').strip() or '_unknown'
    return os.path.join('.', 'received_dir', 'user_raw_file', safe, 'socratic_counter_streak.json')


def _load_streak_state(streak_key: str) -> Dict[str, Any]:
    """读落盘 streak 状态；字段：streak / last_fp / last_decision / updated_at。"""
    key = str(streak_key or '').strip()
    empty = {'streak': 0, 'last_fp': '', 'last_decision': '', 'updated_at': 0.0}
    if not key:
        return empty
    path = _streak_file_path(key)
    legacy = _legacy_streak_file_path(key)
    try:
        if (not os.path.isfile(path)) and os.path.isfile(legacy):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                os.replace(legacy, path)
            except Exception:
                try:
                    import shutil
                    shutil.copy2(legacy, path)
                    os.remove(legacy)
                except Exception:
                    traceback.print_exc()
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
            disk = max(0, int(data.get('streak') or 0))
            # 硬钳制：磁盘异常值也不允许超过上限（防止历史脏数据）
            if disk > MAX_CONSECUTIVE_COUNTER:
                disk = MAX_CONSECUTIVE_COUNTER
            _COUNTER_STREAK[key] = disk
            return {
                'streak': disk,
                'last_fp': str(data.get('last_fp') or ''),
                'last_decision': str(data.get('last_decision') or ''),
                'updated_at': float(data.get('updated_at') or 0),
            }
    except Exception:
        traceback.print_exc()
    mem = max(0, int(_COUNTER_STREAK.get(key, 0) or 0))
    if mem > MAX_CONSECUTIVE_COUNTER:
        mem = MAX_CONSECUTIVE_COUNTER
    return {'streak': mem, 'last_fp': '', 'last_decision': '', 'updated_at': 0.0}


def _load_streak(streak_key: str) -> int:
    return int(_load_streak_state(streak_key).get('streak') or 0)


def _save_streak_state(
    streak_key: str,
    *,
    streak: int,
    last_fp: str = '',
    last_decision: str = '',
) -> None:
    key = str(streak_key or '').strip()
    n = max(0, min(int(streak or 0), MAX_CONSECUTIVE_COUNTER))
    if not key:
        return
    _COUNTER_STREAK[key] = n
    path = _streak_file_path(key)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    'streak': n,
                    'last_fp': str(last_fp or ''),
                    'last_decision': str(last_decision or ''),
                    'updated_at': time.time(),
                },
                f,
                ensure_ascii=False,
            )
    except Exception:
        traceback.print_exc()


def _save_streak(streak_key: str, value: int) -> None:
    state = _load_streak_state(streak_key)
    _save_streak_state(
        streak_key,
        streak=value,
        last_fp=str(state.get('last_fp') or ''),
        last_decision=str(state.get('last_decision') or ''),
    )


def _beijing_today_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    beijing = now + timedelta(hours=8)
    today_start_bj = datetime(beijing.year, beijing.month, beijing.day, tzinfo=timezone.utc) - timedelta(hours=8)
    return today_start_bj


def _parse_card_dt(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    text = str(raw).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(text[:19], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def notebook_has_semantic_reorganize(username: str, notebook: Any = None) -> bool:
    """与前端 KeywordNetworkGraph.maxNodeDisplayOption 的 v2 判定对齐。"""
    try:
        from app_chat.semantic_keyword_service import (
            _load_notebook,
            semantic_reorganize_meta_for_api,
        )
        nb = notebook or _load_notebook(username, None)
        meta = semantic_reorganize_meta_for_api(nb, full_username=username) if nb else {}
        if meta.get('pipeline') == 'v2_condense_hierarchy':
            return True
        if meta.get('reorganize_selected_cids'):
            return True
        if meta.get('hierarchy_links'):
            return True
        if meta.get('last_completed_at'):
            return True
    except Exception:
        traceback.print_exc()
    return False


def _load_book_description(username: str, notebook: Any = None) -> str:
    try:
        from app_chat.scene_context_helper import get_notebook_description
        return (get_notebook_description(username) or '').strip()
    except Exception:
        pass
    try:
        if notebook is not None:
            return (getattr(notebook, 'bookdescription', None) or '').strip()
        from app_chat.semantic_keyword_service import _load_notebook
        nb = _load_notebook(username, None)
        return ((nb.bookdescription if nb else '') or '').strip()
    except Exception:
        return ''


def _load_book_key_issue(username: str) -> str:
    try:
        from app_chat.semantic_reorganize_pipeline import book_key_issue_path
        path = book_key_issue_path(username)
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip()
    except Exception:
        traceback.print_exc()
    return ''


def _load_hierarchy_text(username: str, notebook: Any = None) -> str:
    links: List[Any] = []
    try:
        from app_chat.semantic_keyword_service import (
            _load_notebook,
            semantic_reorganize_meta_for_api,
        )
        nb = notebook or _load_notebook(username, None)
        meta = semantic_reorganize_meta_for_api(nb, full_username=username) if nb else {}
        links = list(meta.get('hierarchy_links') or [])
    except Exception:
        links = []
    if not links:
        try:
            from app_chat.semantic_reorganize_pipeline import load_hierarchy_links_from_file
            links = load_hierarchy_links_from_file(username) or []
        except Exception:
            links = []
    lines: List[str] = []
    for item in links:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            a, b = str(item[0]).strip(), str(item[1]).strip()
            s = str(item[2]).strip() if len(item) >= 3 else ''
            if a and b:
                lines.append(f'{a}|{b}|{s}' if s else f'{a}|{b}')
        elif isinstance(item, str) and item.strip():
            lines.append(item.strip())
    return '\n'.join(lines)


def _load_keyword_attr_map(notebook: Any) -> Dict[str, Dict[str, str]]:
    raw = ''
    try:
        raw = (getattr(notebook, 'keywordFourColorDMT', None) or '') if notebook else ''
    except Exception:
        raw = ''
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _collect_keyword_pool_and_cards(username: str, notebook: Any = None) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Dict[str, str]]]:
    """复刻前端 graphKeywordPool + 卡片词频/时间所需最小字段。"""
    from app_chat.keyword_utils import split_semantic_keywords_raw
    from app_chat.models import Card
    from app_chat.semantic_keyword_service import (
        _load_notebook,
        semantic_reorganize_meta_for_api,
    )

    nb = notebook or _load_notebook(username, None)
    attr_map = _load_keyword_attr_map(nb)
    meta = semantic_reorganize_meta_for_api(nb, full_username=username) if nb else {}
    selected = [int(x) for x in (meta.get('reorganize_selected_cids') or [])]
    use_selected_only = (
        meta.get('pipeline') == 'v2_condense_hierarchy' and bool(selected)
    ) or bool(meta.get('sampled'))

    qs = Card.objects.filter(username=username).exclude(keyWords__isnull=True).exclude(keyWords='')
    if use_selected_only and selected:
        qs = qs.filter(cid__in=selected)
    cards_raw = list(qs.only('cid', 'keyWords', 'datetime').order_by('-datetime')[:800])

    card_rows: List[Dict[str, Any]] = []
    pool: List[str] = []
    seen: Set[str] = set()
    for card in cards_raw:
        kws = split_semantic_keywords_raw(card.keyWords or '')
        if not kws:
            continue
        card_rows.append({
            'cid': int(card.cid),
            'keyWords': card.keyWords or '',
            'keywords': kws,
            'datetime': card.datetime,
        })
        for kw in kws:
            if kw and kw not in seen:
                seen.add(kw)
                pool.append(kw)
    # 属性库中有、但卡上未出现的词也纳入池（与前端 keywords∪attrs 习惯兼容）
    for kw in attr_map.keys():
        k = str(kw).strip()
        if k and k not in seen:
            seen.add(k)
            pool.append(k)
    return pool, card_rows, attr_map


def _tribal_keywords(attr_map: Dict[str, Dict[str, str]]) -> List[str]:
    out: List[str] = []
    for kw, attrs in (attr_map or {}).items():
        if not isinstance(attrs, dict):
            continue
        if attrs.get('is_tribal') or str(attrs.get('knowledge_type') or '').lower() in ('trib', 'tribal', '部落'):
            out.append(str(kw).strip())
    return [k for k in out if k]


def smart_filter_keywords_default(
    keywords: List[str],
    card_rows: List[Dict[str, Any]],
    attr_map: Dict[str, Dict[str, str]],
    *,
    max_count: int = KEYWORD_TAKE,
) -> List[str]:
    """对齐 KeywordNetworkGraph.getSmartFilteredKeywords 默认策略（无前端「当前节点/本地修改」态）。"""
    if not keywords:
        return []
    tribal_list = [k for k in _tribal_keywords(attr_map) if k in keywords]
    effective_max = max_count + len(tribal_list)
    if len(keywords) <= effective_max:
        return list(keywords)

    keyword_frequency: Dict[str, int] = {}
    keyword_first: Dict[str, Optional[datetime]] = {}
    for kw in keywords:
        earliest = None
        count = 0
        for row in card_rows:
            if kw in (row.get('keywords') or []):
                count += 1
                dt = _parse_card_dt(row.get('datetime'))
                if dt and (earliest is None or dt < earliest):
                    earliest = dt
        keyword_frequency[kw] = count
        keyword_first[kw] = earliest

    sorted_by_freq = sorted(keywords, key=lambda k: keyword_frequency.get(k, 0), reverse=True)
    top3 = sorted_by_freq[:3]
    sorted_by_time = sorted(
        keywords,
        key=lambda k: keyword_first.get(k) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    today_start = _beijing_today_start_utc()
    color_groups: Dict[str, List[str]] = {'R': [], 'B': [], 'P': [], 'G': [], 'none': []}
    dmt_groups: Dict[str, List[str]] = {'D': [], 'M': [], 'T': [], 'none': []}
    new_keywords: List[str] = []
    for kw in keywords:
        attrs = attr_map.get(kw) or {}
        four = str(attrs.get('four_color_type') or '').strip().upper()
        dmt = str(attrs.get('dmt_level') or '').strip().upper()
        if four in color_groups:
            color_groups[four].append(kw)
        else:
            color_groups['none'].append(kw)
        if dmt in dmt_groups:
            dmt_groups[dmt].append(kw)
        else:
            dmt_groups['none'].append(kw)
        is_new = False
        for row in card_rows:
            if kw not in (row.get('keywords') or []):
                continue
            dt = _parse_card_dt(row.get('datetime'))
            if dt and dt >= today_start:
                is_new = True
                break
        if is_new:
            new_keywords.append(kw)

    selected: Set[str] = set()
    for k in top3:
        selected.add(k)
    for k in sorted_by_time[:4]:
        selected.add(k)
    for k in new_keywords[:10]:
        selected.add(k)

    for color in ('R', 'B', 'P', 'G'):
        group = color_groups.get(color) or []
        if not group:
            continue
        pick = next((k for k in group if k in new_keywords and k not in selected), None)
        if not pick:
            pick = next((k for k in sorted_by_time if k in group and k not in selected), None)
        if pick:
            selected.add(pick)

    for dmt in ('D', 'M', 'T'):
        group = dmt_groups.get(dmt) or []
        if not group:
            continue
        pick = next((k for k in group if k in new_keywords and k not in selected), None)
        if not pick:
            pick = next((k for k in sorted_by_time if k in group and k not in selected), None)
        if pick:
            selected.add(pick)

    green_not = [k for k in color_groups.get('G', []) if k not in selected]
    current_green = sum(
        1 for k in selected
        if str((attr_map.get(k) or {}).get('four_color_type') or '').upper() == 'G'
    )
    if green_not and current_green < 5 and len(selected) < max_count:
        for k in green_not[: min(3, max_count - len(selected))]:
            selected.add(k)

    t_not = [k for k in dmt_groups.get('T', []) if k not in selected]
    current_t = sum(
        1 for k in selected
        if str((attr_map.get(k) or {}).get('dmt_level') or '').upper() == 'T'
    )
    if t_not and current_t < 3 and len(selected) < max_count:
        for k in t_not[: min(2, max_count - len(selected))]:
            selected.add(k)

    remaining = [k for k in keywords if k not in selected]
    needed = max_count - len(selected)
    for k in remaining[: max(0, needed)]:
        selected.add(k)

    for k in tribal_list:
        selected.add(k)

    # 保持相对稳定顺序：按原 pool 顺序输出
    ordered = [k for k in keywords if k in selected]
    return ordered[: effective_max]


def load_recent_qa_questions(username: str, limit: int = RECENT_QA_CARD_LIMIT) -> List[str]:
    """取本子最近期至多 limit 张问答卡，抽取其中用户提问链（只要「提问：」部分）。"""
    from app_chat.models import Card

    cards = (
        Card.objects.filter(username=username)
        .exclude(content__isnull=True)
        .exclude(content='')
        .order_by('-datetime')[:300]
    )
    qa_cards = []
    for card in cards:
        content = card.content or ''
        if ('提问：' not in content and '提问:' not in content):
            continue
        if ('回答：' not in content and '回答:' not in content):
            continue
        qa_cards.append(card)
        if len(qa_cards) >= limit:
            break

    # 卡片按时间从旧到新，便于呈现「提问链」
    qa_cards = list(reversed(qa_cards))
    questions: List[str] = []
    pattern = re.compile(r'提问[：:]\s*([^\n\r]+)')
    for card in qa_cards:
        for q in pattern.findall(card.content or ''):
            q = (q or '').strip()
            if q:
                questions.append(q)
    return questions


def _presummary_path_for_doc(username: str, doc_name: str) -> str:
    base = os.path.splitext(str(doc_name or ''))[0]
    ext = os.path.splitext(str(doc_name or ''))[1].lstrip('.')
    if not base:
        return ''
    return os.path.join(
        '.', 'received_dir', 'user_raw_file', str(username),
        'pre_summary', f'{base}_Presummary_{ext}.md',
    )


def load_selected_doc_presummaries(
    username: str,
    file_list: Optional[List[str]],
    *,
    max_docs: int = PRESUMMARY_MAX_DOCS,
    max_chars_each: int = PRESUMMARY_MAX_CHARS_EACH,
) -> Tuple[List[str], List[Dict[str, str]]]:
    """返回 (全部勾选文档名, 抽样后的 [{name, summary}])。超过 max_docs 时随机抽 Presummary。"""
    names = [str(x).strip() for x in (file_list or []) if str(x).strip()]
    if not names:
        return [], []
    with_summary: List[Dict[str, str]] = []
    for name in names:
        path = _presummary_path_for_doc(username, name)
        text = ''
        try:
            if path and os.path.isfile(path):
                with open(path, 'r', encoding='utf-8') as f:
                    text = (f.read() or '').strip()
        except Exception:
            text = ''
        if text and len(text) > max_chars_each:
            text = text[:max_chars_each] + '…'
        with_summary.append({'name': name, 'summary': text or '（暂无 Presummary）'})
    picked = with_summary
    if len(with_summary) > max_docs:
        picked = random.sample(with_summary, max_docs)
    return names, picked


def build_socratic_probe_system_prompt() -> str:
    return (
        '你是本子语义问答的快速判定器。结合本子语义空间、用户近期发问链、'
        '（若有）窗口上一轮问答、以及（若有）勾选文档的 Presummary 素材覆盖情况，'
        '判断对用户最新问题：应直接回答，还是应先有针对性、精准而深刻地反问。\n'
        '目标：该反问时反问；信息已够可直接答时不要强行反问。均衡用户体验。\n\n'
        '【判定原则】\n'
        '- 「是」=应先反问：问题宽泛/目标不清/关键前提缺失/与本子核心语义偏离需纠偏/素材未覆盖或覆盖含糊。\n'
        '- 「否」=应直接回答：问题具体可答、上下文已对齐、勾选素材已大致覆盖、接续上一轮只需补全/落实。\n\n'
        '【典型应反问（是）】\n'
        '1) 问题过于宽泛（如“如何理解X的精妙/怎么看X”）且未限定角度、层次或用途；\n'
        '2) 缺少关键约束（对象、场景、目标、评价标准）导致多种合理解差异很大；\n'
        '3) 与本子核心问题/语义关键词明显错位，直接答容易跑偏；\n'
        '4) 用户在“赶进度要答案”，但概念基础不牢，一针见血反问更能激活思考；\n'
        '5) 勾选了文档，但 Presummary 未覆盖最新问题，或只沾边、关键点不清。\n\n'
        '【典型应直接答（否）】\n'
        '1) 问题已具体（定义、对比、步骤、某机制如何运作），可一次性讲清；\n'
        '2) 窗口上一轮已澄清目标，本轮是在此基础上的追问/落地，信息量已够；\n'
        '3) 勾选文档 Presummary 已大致覆盖最新问题，素材足以支撑直接回答；\n'
        '4) 用户在求核对、总结、改写、举例等操作性请求，反问收益低；\n'
        '5) 连续反问已达上限场景下（由系统另行强制）本判定仍按内容判断，但倾向可答则答。\n\n'
        '【边界情况】\n'
        '- 素材“部分覆盖”：能答主干则「否」；缺口恰好是理解关键且会误导则「是」。\n'
        '- 问题短但承接上文：有上一轮问答且已对齐时偏「否」；无承接、语义悬空时偏「是」。\n'
        '- 文档很多仅抽样摘要：未抽中不等于无素材；若文档名/抽样摘要已显示主题匹配，可「否」。\n'
        '- 宁可不反问也不要为反问而反问：用户已给出足够信息时选「否」。\n\n'
        '输出必须严格按顺序：\n'
        '1) 先输出一句话分析（严格50字以内，不要换行堆砌）；\n'
        f'2) 再单独一行输出标记 {FINAL_MARKER}；\n'
        '3) 最后只输出一个字：是 或 否。\n'
        '「是」=应先反问；「否」=应直接回答。不要输出其它内容。'
    )


def build_socratic_probe_user_prompt(
    *,
    book_description: str,
    has_semantic: bool,
    book_key_issue: str,
    keywords: List[str],
    hierarchy_text: str,
    recent_questions: List[str],
    prev_question: str,
    prev_answer: str,
    doc_names: List[str],
    doc_presummaries: List[Dict[str, str]],
    current_question: str,
) -> str:
    if has_semantic:
        semantic_user = (
            f'【本子核心问题 bookKeyIssue】\n{book_key_issue or "（无）"}\n\n'
            f'【语义关键词（默认策略取至多{KEYWORD_TAKE}个）】\n'
            f'{("、".join(keywords) if keywords else "（无）")}\n\n'
            f'【层次连线】\n{hierarchy_text or "（无）"}\n\n'
        )
    else:
        semantic_user = '【本子语义梳理】未做过，不提供核心问题/语义关键词/层次连线。\n\n'

    recent_text = '\n'.join(f'{i + 1}. {q}' for i, q in enumerate(recent_questions)) or '（无）'

    prev_block = ''
    pq = (prev_question or '').strip()
    pa = (prev_answer or '').strip()
    if pq or pa:
        if pa and len(pa) > PREV_ANSWER_MAX_CHARS:
            pa = pa[:PREV_ANSWER_MAX_CHARS] + '…'
        prev_block = (
            '【窗口上一轮接续上下文（主窗口）】\n'
            f'上一问：{pq or "（无）"}\n'
            f'主窗口回答：{pa or "（无）"}\n'
            '说明：当前最新问题是对该轮对话的接续；若上一轮已澄清目标且本轮可直接推进，倾向直接回答。\n\n'
        )

    docs_block = ''
    if doc_names:
        names_line = '、'.join(doc_names)
        parts = [
            '【勾选文档与 Presummary（已知素材）】\n'
            f'勾选文档名：{names_line}\n'
            '说明：以下 Presummary 为已知素材摘要。'
            f'若勾选超过{PRESUMMARY_MAX_DOCS}个，仅随机附带其中{PRESUMMARY_MAX_DOCS}份摘要。\n'
            '若素材已大致覆盖最新问题 → 倾向「否」（直接答）；'
            '若未覆盖或涉及但含糊 → 可考虑「是」（先反问）。\n'
        ]
        if doc_presummaries:
            for i, item in enumerate(doc_presummaries, 1):
                parts.append(
                    f'--- 素材{i}：{item.get("name") or "（未命名）"} ---\n'
                    f'{item.get("summary") or "（暂无 Presummary）"}\n'
                )
        else:
            parts.append('（未读到可用 Presummary）\n')
        docs_block = '\n'.join(parts) + '\n'

    return (
        f'本子中文名（bookdescription）：{book_description or "（未提供）"}\n\n'
        f'{semantic_user}'
        f'【用户近期提问链】（本子最近问答卡，至多{RECENT_QA_CARD_LIMIT}张）\n{recent_text}\n\n'
        f'{prev_block}'
        f'{docs_block}'
        f'【用户最新发送的问题】\n{current_question}\n'
    )


def _call_deepseek_v4_flash(system_prompt: str, user_prompt: str) -> str:
    from app_chat.scene_models import resolve_openai_cfg_from_abbr
    from app_chat.config.config_manager import config_manager

    cfg = resolve_openai_cfg_from_abbr(PROBE_MODEL_ABBR)
    headers = {'x-foo': 'true'}
    model_name = str(cfg.get('model') or PROBE_MODEL_ABBR)
    try:
        mc = config_manager.get_model_config(PROBE_MODEL_ABBR)
        if mc:
            cur = mc.get_config() or {}
            if cur.get('default_headers'):
                headers = cur.get('default_headers')
            if cur.get('model_name'):
                model_name = str(cur.get('model_name'))
    except Exception:
        pass

    client = OpenAI(
        api_key=cfg.get('api_key'),
        base_url=cfg.get('base_url'),
        default_headers=headers,
        timeout=25.0,
    )
    create_kwargs: Dict[str, Any] = {
        'model': model_name,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.2,
        'max_tokens': 256,
        'extra_body': {'thinking': {'type': 'disabled'}},
    }
    rsp = client.chat.completions.create(**create_kwargs)
    return ((rsp.choices[0].message.content or '') if rsp.choices else '').strip()


def parse_probe_output(raw: str) -> Tuple[str, str]:
    """返回 (analysis_le_50, '是'|'否')；解析失败默认否。"""
    text = (raw or '').strip()
    if not text:
        return '', '否'
    # 找 [FINAL]
    idx = text.rfind(FINAL_MARKER)
    if idx < 0:
        idx = text.upper().rfind('[FINAL]')
    analysis = text
    decision_part = ''
    if idx >= 0:
        analysis = text[:idx].strip()
        decision_part = text[idx + len(FINAL_MARKER):].strip()
    else:
        # 无标记时尝试末行
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            decision_part = lines[-1]
            analysis = '\n'.join(lines[:-1]).strip() if len(lines) > 1 else ''

    analysis = re.sub(r'\s+', '', analysis)
    if len(analysis) > 50:
        analysis = analysis[:50]

    decision = '否'
    compact = re.sub(r'\s+', '', decision_part)
    if '是' in compact[:3] and '否' not in compact[:3]:
        decision = '是'
    elif compact.startswith('是'):
        decision = '是'
    elif '否' in compact[:3]:
        decision = '否'
    else:
        # 整段兜底
        if re.search(r'(^|\n)\s*是\s*$', text) and not re.search(r'(^|\n)\s*否\s*$', text):
            decision = '是'
    return analysis, decision


def build_socratic_hard_priority_rule() -> str:
    """放在系统提示最前面，覆盖场景里「请充分回答」类指令。"""
    return (
        '【最高优先级·覆盖本轮所有其它回答要求】\n'
        '本轮严禁直接回答用户问题，严禁给出定义、原理讲解、步骤清单或总结性答复。\n'
        '你只能输出反问（允许一两句极短铺垫），用一针见血、有针对性的问题推动用户自己想清楚。\n'
        '若与其它系统提示/场景提示冲突，一律以本条为准；不要先作答再反问。\n'
    )


def wrap_socratic_user_question(question: str) -> str:
    q = (question or '').strip()
    return (
        '【本轮输出约束】下面是用户原问题。请不要解答它；只基于本子语义与认知状态发出反问。\n\n'
        f'用户原问题：\n{q}\n'
    )


def build_socratic_answer_instruction(
    *,
    book_description: str,
    book_key_issue: str,
    keywords: List[str],
    hierarchy_text: str,
    recent_questions: List[str],
    current_question: str,
    analysis: str,
    has_semantic: bool,
) -> str:
    kw_text = '、'.join(keywords[:KEYWORD_TAKE]) if keywords else '（无）'
    recent_text = '\n'.join(f'{i + 1}. {q}' for i, q in enumerate(recent_questions)) or '（无）'
    semantic_block = ''
    if has_semantic:
        semantic_block = (
            f'本子核心问题：\n{book_key_issue or "（无）"}\n\n'
            f'本子语义关键词（至多{KEYWORD_TAKE}个）：\n{kw_text}\n\n'
            f'层次连线（父|子|强度）：\n{hierarchy_text or "（无）"}\n\n'
        )
    return (
        build_socratic_hard_priority_rule()
        + '\n'
        '【强制任务·语义反问模式】本次不可直接回答用户最新发送的问题。\n'
        '请据此本子要解决的核心问题、此本子语义空间、近期用户提问情况和当前问题，'
        '反问用户一个或一些一针见血、有针对性、精准而深刻的反问问题，'
        '激活用户的思考，但要适合用户当前的认知状态：'
        '对当前认知水平一般的用户，反问要比用户拔高一些，有明显的点拨和开悟价值，'
        '但又不要高出太多导致用户听不懂；'
        '若用户认知水平已经比较高或中偏高，则基本没有这个顾虑。\n'
        '不要给出直接答案、步骤清单或总结性答复；输出以反问为主。\n\n'
        f'本子中文名（bookdescription）：{book_description or "（未提供）"}\n\n'
        f'{semantic_block}'
        f'用户近期提问链：\n{recent_text}\n\n'
        f'用户最新问题：{current_question}\n\n'
        f'前置判定分析（仅供参考）：{analysis or "（无）"}\n'
    )


def apply_socratic_to_system_prompt(system_prompt: str, probe: Optional[Dict[str, Any]]) -> str:
    """把反问指令前置到系统提示最前，避免被长场景提示淹没。"""
    if not (probe and probe.get('should_counter_ask') and (probe.get('instruction') or '').strip()):
        return system_prompt or ''
    instruction = str(probe.get('instruction') or '').strip()
    base = (system_prompt or '').strip()
    if not base:
        return instruction
    return instruction + '\n\n——以下为原场景/系统提示（若冲突，以上方反问指令为准）——\n\n' + base


def apply_socratic_to_user_text(user_text: str, probe: Optional[Dict[str, Any]]) -> str:
    if not (probe and probe.get('should_counter_ask') and (probe.get('instruction') or '').strip()):
        return user_text or ''
    return wrap_socratic_user_question(user_text or '')



def build_socratic_iteration_deepen_suffix() -> str:
    """慢思考第二次迭代：在保持反问前提下加深反问内容。"""
    return (
        '\n\n【慢思考·迭代加深反问】本次是对上一轮反问的迭代改进。'
        '请继续只做反问、不可直接回答用户原问题；'
        '在上一轮反问基础上把反问内容迭代加深——更一针见血、更有针对性、更精准深刻，'
        '更贴合本子核心问题与语义空间，并更适合用户当前认知状态；'
        '仍然禁止给出直接答案、步骤清单或总结性答复。'
    )


def preserve_socratic_for_iteration(prev_probe: Optional[Dict[str, Any]], *, mode: str) -> Dict[str, Any]:
    """iteration 不再次判定：若首答已是反问，则延续反问并追加加深指令。"""
    prev = dict(prev_probe or {})
    if prev.get('should_counter_ask') and (prev.get('instruction') or '').strip():
        out = dict(prev)
        out['ok'] = True
        out['skipped_rejudge'] = True
        out['skip_reason'] = mode
        out['phase'] = 'iteration_deepen'
        base_instruction = str(prev.get('instruction') or '').strip()
        if '【慢思考·迭代加深反问】' not in base_instruction:
            base_instruction = base_instruction + build_socratic_iteration_deepen_suffix()
        out['instruction'] = base_instruction
        return out
    return {
        'ok': True,
        'should_counter_ask': False,
        'decision': '否',
        'skipped_rejudge': True,
        'skip_reason': mode,
        'phase': 'iteration_normal',
        'instruction': '',
        'analysis': prev.get('analysis') or '',
    }


class _SocraticEarlyReturn(Exception):
    """内部控制流：跳过 flash / 提前结束判定。"""


def run_socratic_probe(
    *,
    username: str,
    message: str,
    name2lock: str,
    file_list: Optional[List[str]] = None,
    prev_question: str = '',
    prev_answer: str = '',
) -> Dict[str, Any]:
    """执行判定；处理缓存与连续反问上限。失败则 should_counter_ask=False。

    连续反问按「本子 username + 用户发送轮次」计：
    - 同一轮多窗口（同原问题）只判定一次、只 +1 一次
    - 已连续反问满 MAX 次后，本轮不再调 flash，直接强制「否」并清零
    """
    msg = (message or '').strip()
    prev_q = (prev_question or '').strip()
    prev_a = (prev_answer or '').strip()
    docs = [str(x).strip() for x in (file_list or []) if str(x).strip()]
    streak_key = str(username or name2lock).strip()
    fp = _msg_fp(msg)
    # 关键：去重键只用本子+原问题，绝不能把 prev/docs 拼进 key，
    # 否则三窗口稍有字段差异会各跑一次，某次「否」会把 streak 清零，上限形同虚设。
    key = (streak_key, fp)
    now = time.time()

    with _LOCK:
        cached = _RESULT_CACHE.get(key)
        if cached and (now - float(cached.get('ts') or 0)) <= _PROBE_CACHE_TTL_SEC:
            cached_result = dict(cached.get('result') or {})
            print(
                f'[socratic_probe] 复用缓存 streak_key={streak_key} fp={fp} '
                f'streak={cached_result.get("streak_before")}->{cached_result.get("streak_after")} '
                f'decision={cached_result.get("decision")}',
                flush=True,
            )
            return cached_result
        if key in _INFLIGHT:
            wait_event = _INFLIGHT[key]
            is_leader = False
        else:
            wait_event = threading.Event()
            _INFLIGHT[key] = wait_event
            is_leader = True

    if not is_leader:
        wait_event.wait(timeout=40)
        with _LOCK:
            if key in _INFLIGHT_RESULTS:
                return dict(_INFLIGHT_RESULTS[key])
            cached = _RESULT_CACHE.get(key)
            if cached:
                return dict(cached.get('result') or {})
        return {
            'ok': False,
            'should_counter_ask': False,
            'decision': '否',
            'error': 'wait_inflight_timeout',
        }

    result: Dict[str, Any] = {
        'ok': False,
        'should_counter_ask': False,
        'decision': '否',
        'analysis': '',
        'forced_by_streak': False,
        'streak_before': 0,
        'streak_after': 0,
        'has_semantic': False,
        'book_description': '',
        'book_key_issue': '',
        'keywords': [],
        'hierarchy_text': '',
        'recent_questions': [],
        'instruction': '',
        'raw': '',
        'elapsed_sec': 0.0,
        'error': '',
    }

    t0 = time.time()
    try:
        from django.db import close_old_connections
        close_old_connections()

        with _LOCK:
            state = _load_streak_state(streak_key)
            streak_before = int(state.get('streak') or 0)
            same_msg = (
                str(state.get('last_fp') or '') == fp
                and str(state.get('last_decision') or '') in ('是', '否')
            )

        # 同题重入：不改计数、不因 streak==MAX 误杀本轮已生效的「是」
        if same_msg:
            reused = str(state.get('last_decision') or '否')
            result.update({
                'ok': True,
                'should_counter_ask': reused == '是',
                'decision': reused,
                'raw_decision': reused,
                'analysis': '同题复用上次判定，不重复计数',
                'forced_by_streak': False,
                'streak_before': streak_before,
                'streak_after': streak_before,
                'streak_key': streak_key,
                'skipped_rejudge': True,
                'skip_reason': 'same_message_idempotent',
            })
            print(
                f'[socratic_probe] 同题幂等 decision={reused} streak={streak_before} '
                f'key={streak_key} fp={fp}',
                flush=True,
            )
            if reused == '是':
                from app_chat.semantic_keyword_service import _load_notebook
                notebook = _load_notebook(username, None)
                book_description = _load_book_description(username, notebook)
                has_semantic = notebook_has_semantic_reorganize(username, notebook)
                book_key_issue = _load_book_key_issue(username) if has_semantic else ''
                hierarchy_text = _load_hierarchy_text(username, notebook) if has_semantic else ''
                keywords = []
                if has_semantic:
                    pool, card_rows, attr_map = _collect_keyword_pool_and_cards(username, notebook)
                    keywords = smart_filter_keywords_default(
                        pool, card_rows, attr_map, max_count=KEYWORD_TAKE,
                    )
                recent_questions = load_recent_qa_questions(username, RECENT_QA_CARD_LIMIT)
                result.update({
                    'has_semantic': has_semantic,
                    'book_description': book_description,
                    'book_key_issue': book_key_issue,
                    'keywords': keywords,
                    'hierarchy_text': hierarchy_text,
                    'recent_questions': recent_questions,
                    'instruction': build_socratic_answer_instruction(
                        book_description=book_description,
                        book_key_issue=book_key_issue,
                        keywords=keywords,
                        hierarchy_text=hierarchy_text,
                        recent_questions=recent_questions,
                        current_question=msg,
                        analysis='同题复用',
                        has_semantic=has_semantic,
                    ),
                })
            raise _SocraticEarlyReturn()

        # 新问题且已连续反问满上限：强制直接答，不再调用 flash
        if streak_before >= MAX_CONSECUTIVE_COUNTER:
            with _LOCK:
                _save_streak_state(streak_key, streak=0, last_fp=fp, last_decision='否')
            result.update({
                'ok': True,
                'should_counter_ask': False,
                'decision': '否',
                'raw_decision': '是',
                'analysis': f'已连续反问{MAX_CONSECUTIVE_COUNTER}轮，本轮强制直接回答',
                'forced_by_streak': True,
                'streak_before': streak_before,
                'streak_after': 0,
                'streak_key': streak_key,
                'instruction': '',
            })
            print(
                f'[socratic_probe] 强制否（连续反问已满{MAX_CONSECUTIVE_COUNTER}） '
                f'streak={streak_before}->0 key={streak_key} fp={fp}',
                flush=True,
            )
            raise _SocraticEarlyReturn()

        from app_chat.semantic_keyword_service import _load_notebook
        notebook = _load_notebook(username, None)
        book_description = _load_book_description(username, notebook)
        has_semantic = notebook_has_semantic_reorganize(username, notebook)
        book_key_issue = ''
        hierarchy_text = ''
        keywords: List[str] = []
        if has_semantic:
            book_key_issue = _load_book_key_issue(username)
            hierarchy_text = _load_hierarchy_text(username, notebook)
            pool, card_rows, attr_map = _collect_keyword_pool_and_cards(username, notebook)
            keywords = smart_filter_keywords_default(
                pool, card_rows, attr_map, max_count=KEYWORD_TAKE,
            )

        recent_questions = load_recent_qa_questions(username, RECENT_QA_CARD_LIMIT)
        doc_names, doc_presummaries = load_selected_doc_presummaries(username, docs)

        system_prompt = build_socratic_probe_system_prompt()
        user_prompt = build_socratic_probe_user_prompt(
            book_description=book_description,
            has_semantic=has_semantic,
            book_key_issue=book_key_issue,
            keywords=keywords,
            hierarchy_text=hierarchy_text,
            recent_questions=recent_questions,
            prev_question=prev_q,
            prev_answer=prev_a,
            doc_names=doc_names,
            doc_presummaries=doc_presummaries,
            current_question=msg,
        )

        raw = _call_deepseek_v4_flash(system_prompt, user_prompt)
        analysis, decision = parse_probe_output(raw)

        with _LOCK:
            # 再次读取，防止并发夹缝（理论上同 key 只有 leader）
            streak_before = _load_streak(streak_key)
            forced = False
            final_decision = decision
            if decision == '是' and streak_before >= MAX_CONSECUTIVE_COUNTER:
                final_decision = '否'
                forced = True
            if final_decision == '是':
                streak_after = min(streak_before + 1, MAX_CONSECUTIVE_COUNTER)
            else:
                streak_after = 0
            _save_streak_state(
                streak_key,
                streak=streak_after,
                last_fp=fp,
                last_decision=final_decision,
            )

        should = final_decision == '是'
        instruction = ''
        if should:
            instruction = build_socratic_answer_instruction(
                book_description=book_description,
                book_key_issue=book_key_issue,
                keywords=keywords,
                hierarchy_text=hierarchy_text,
                recent_questions=recent_questions,
                current_question=msg,
                analysis=analysis,
                has_semantic=has_semantic,
            )

        result.update({
            'ok': True,
            'should_counter_ask': should,
            'decision': final_decision,
            'raw_decision': decision,
            'analysis': analysis,
            'forced_by_streak': forced,
            'streak_before': streak_before,
            'streak_after': streak_after,
            'streak_key': streak_key,
            'has_semantic': has_semantic,
            'book_description': book_description,
            'book_key_issue': book_key_issue,
            'keywords': keywords,
            'hierarchy_text': hierarchy_text,
            'recent_questions': recent_questions,
            'instruction': instruction,
            'raw': raw,
            'elapsed_sec': round(time.time() - t0, 3),
        })
        print(
            f'[socratic_probe] ok decision={final_decision} forced={forced} '
            f'streak={streak_before}->{streak_after} key={streak_key} fp={fp} semantic={has_semantic} '
            f'kw={len(keywords)} recent_q={len(recent_questions)} '
            f'prev_turn={bool(prev_q or prev_a)} docs={len(doc_names)} presum={len(doc_presummaries)} '
            f'elapsed={result["elapsed_sec"]}s analysis={analysis}',
            flush=True,
        )
    except _SocraticEarlyReturn:
        result['elapsed_sec'] = round(time.time() - t0, 3)
    except Exception as exc:
        traceback.print_exc()
        result['error'] = str(exc)[:300]
        result['elapsed_sec'] = round(time.time() - t0, 3)
        print(f'[socratic_probe] 失败，按否处理: {exc}', flush=True)
    finally:
        try:
            from django.db import close_old_connections
            close_old_connections()
        except Exception:
            pass

    with _LOCK:
        _RESULT_CACHE[key] = {'ts': time.time(), 'result': dict(result)}
        _INFLIGHT_RESULTS[key] = dict(result)
        ev = _INFLIGHT.pop(key, None)
        if ev is not None:
            ev.set()
        dead = [
            k for k, v in _RESULT_CACHE.items()
            if time.time() - float(v.get('ts') or 0) > _PROBE_CACHE_TTL_SEC
        ]
        for k in dead:
            _RESULT_CACHE.pop(k, None)
            _INFLIGHT_RESULTS.pop(k, None)

    return result


def get_socratic_probe_from_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    value = params.get('socratic_probe')
    return value if isinstance(value, dict) else {}


# 按「本子 + 用户原问题」共享本轮判定，保证多窗口同轮策略一致
_ROUND_PROBE: Dict[Tuple[str, str], Dict[str, Any]] = {}
_ROUND_LATEST_MSG: Dict[str, str] = {}
_ROUND_PROBE_TTL_SEC = 900.0


def _round_owner_candidates(*owners: Any) -> List[str]:
    out: List[str] = []
    for o in owners:
        k = str(o or '').strip()
        if k and k not in out:
            out.append(k)
    return out


def get_latest_round_message(*owner_keys: Any) -> str:
    with _LOCK:
        for ok in _round_owner_candidates(*owner_keys):
            msg = str(_ROUND_LATEST_MSG.get(ok) or '').strip()
            if msg:
                return msg
    return ''


def extract_original_question_from_iteration_message(text: str) -> str:
    """从慢思考迭代文案中提取「原问题」。"""
    raw = text or ''
    m = re.search(r'原问题：\s*\n([\s\S]*?)(?:\n\n第一次|$)', raw)
    if m:
        return (m.group(1) or '').strip()
    m2 = re.search(r'原问题：\s*([^\n]+)', raw)
    if m2:
        return (m2.group(1) or '').strip()
    return ''


def publish_round_socratic_probe(
    *,
    owner_keys: List[Any],
    bound_message: str,
    probe: Dict[str, Any],
    mode: str = 'normal',
) -> Dict[str, Any]:
    """发布本轮共享判定：同一 bound_message 下所有窗口读到同一份。"""
    msg = (bound_message or '').strip()
    mode_n = str(mode or 'normal').strip().lower()
    payload = dict(probe or {})
    payload['bound_message'] = msg
    payload['bound_mode'] = mode_n
    payload['bound_ts'] = time.time()
    owners = _round_owner_candidates(*owner_keys)
    if not msg or not owners:
        return payload
    now = time.time()
    with _LOCK:
        # 清理过期
        dead = [
            k for k, v in _ROUND_PROBE.items()
            if now - float((v or {}).get('bound_ts') or 0) > _ROUND_PROBE_TTL_SEC
        ]
        for k in dead:
            _ROUND_PROBE.pop(k, None)
        for ok in owners:
            key = (ok, msg)
            if mode_n == 'iteration':
                prev = _ROUND_PROBE.get(key)
                # 若该原问题已被更新的 normal「否/是」覆盖且时间更新，仍允许 iteration 加深同题
                # 但若 latest normal 已切到另一题，则不要把旧题 iteration 写成 latest
                latest = _ROUND_LATEST_MSG.get(ok)
                if latest and latest != msg and prev is None:
                    # 旧题 iteration 过期，不发布
                    print(
                        f'[socratic_probe] 跳过过期 iteration 发布 ok={ok} '
                        f'latest_len={len(latest)} bound_len={len(msg)}',
                        flush=True,
                    )
                    continue
            _ROUND_PROBE[key] = dict(payload)
            if mode_n in ('normal', 'merge'):
                _ROUND_LATEST_MSG[ok] = msg
    return payload


def resolve_round_socratic_probe(
    *,
    owner_keys: List[Any],
    bound_message: str = '',
    current_message: str = '',
    prefer_mode: str = 'normal',
) -> Dict[str, Any]:
    """按原问题读取共享判定；iteration 可用 bound_message 或从迭代文案解析。"""
    mode = str(prefer_mode or 'normal').strip().lower()
    msg = (bound_message or '').strip()
    cur = (current_message or '').strip()
    if not msg and mode == 'iteration':
        msg = extract_original_question_from_iteration_message(cur)
    if not msg:
        msg = cur
    if not msg:
        return {}
    owners = _round_owner_candidates(*owner_keys)
    with _LOCK:
        for ok in owners:
            hit = _ROUND_PROBE.get((ok, msg))
            if isinstance(hit, dict) and hit:
                # TTL
                if time.time() - float(hit.get('bound_ts') or 0) > _ROUND_PROBE_TTL_SEC:
                    continue
                return dict(hit)
        # 兜底：normal 且精确消息未命中时，不误用最新其它题
    return {}


def store_socratic_probe_on_params(
    params: Dict[str, Any],
    *,
    probe: Dict[str, Any],
    bound_message: str,
    mode: str,
    window_id: str = '',
) -> Dict[str, Any]:
    """写入 params 镜像（按消息索引），便于调试；真正跨窗口一致性靠 publish_round_socratic_probe。"""
    if not isinstance(params, dict):
        return dict(probe or {})
    payload = dict(probe or {})
    payload['bound_message'] = (bound_message or '').strip()
    payload['bound_mode'] = str(mode or 'normal').strip().lower()
    payload['bound_window'] = str(window_id or '').strip()
    payload['bound_ts'] = time.time()
    by_msg = params.get('socratic_by_message')
    if not isinstance(by_msg, dict):
        by_msg = {}
        params['socratic_by_message'] = by_msg
    if payload['bound_message']:
        by_msg[payload['bound_message']] = payload
        # 控制体积
        if len(by_msg) > 12:
            for old_k in list(by_msg.keys())[:-12]:
                by_msg.pop(old_k, None)
    params['socratic_probe'] = payload
    params['socratic_round_message'] = payload['bound_message']
    return payload


# 兼容旧函数名
def store_socratic_probe_for_window(
    params: Dict[str, Any],
    *,
    window_id: str,
    probe: Dict[str, Any],
    bound_message: str,
    mode: str,
) -> None:
    store_socratic_probe_on_params(
        params,
        probe=probe,
        bound_message=bound_message,
        mode=mode,
        window_id=window_id,
    )


def resolve_socratic_probe_for_request(
    store: Optional[Dict[str, Any]],
    *,
    name_keys: List[Any],
    window_id: str = '',
    current_message: str = '',
    prefer_mode: str = 'normal',
    bound_message: str = '',
) -> Dict[str, Any]:
    """优先按「原问题」读取共享判定，保证主辅窗口同轮一致。"""
    mode = str(prefer_mode or 'normal').strip().lower()
    cur = (current_message or '').strip()
    bound = (bound_message or '').strip()
    if not bound and mode == 'iteration':
        bound = extract_original_question_from_iteration_message(cur)
    if not bound:
        bound = cur

    probe = resolve_round_socratic_probe(
        owner_keys=list(name_keys or []),
        bound_message=bound,
        current_message=cur,
        prefer_mode='normal',  # 共享表只存首轮判定；iteration 在读取时加深
    )
    if not probe:
        # 兜底：params 内按消息镜像
        if isinstance(store, dict):
            params = None
            for key in name_keys or []:
                if key is None:
                    continue
                k = str(key).strip()
                if not k:
                    continue
                cand = store.get(k)
                if isinstance(cand, dict) and (
                    'socratic_by_message' in cand or 'socratic_probe' in cand
                ):
                    params = cand
                    break
            if isinstance(params, dict):
                by_msg = params.get('socratic_by_message')
                if isinstance(by_msg, dict) and bound and isinstance(by_msg.get(bound), dict):
                    probe = dict(by_msg.get(bound) or {})
                else:
                    latest = get_socratic_probe_from_params(params)
                    latest_bound = str((latest or {}).get('bound_message') or '').strip()
                    if latest and (mode == 'iteration' or not latest_bound or latest_bound == bound):
                        probe = latest
                    elif latest and latest_bound and bound and latest_bound != bound:
                        return {
                            'ok': True,
                            'should_counter_ask': False,
                            'decision': '否',
                            'skipped_stale': True,
                            'instruction': '',
                        }
    if not probe:
        return {}
    if mode == 'iteration' and probe.get('should_counter_ask'):
        return preserve_socratic_for_iteration(probe, mode='iteration')
    return probe


def resolve_socratic_probe_from_store(store: Optional[Dict[str, Any]], *keys: Any) -> Dict[str, Any]:
    """兼容旧调用：不区分窗口时，取第一个含 socratic_probe 的参数块。"""
    if not isinstance(store, dict):
        return {}
    tried = []
    for key in keys:
        if key is None:
            continue
        k = str(key).strip()
        if not k or k in tried:
            continue
        tried.append(k)
        params = store.get(k)
        if isinstance(params, dict) and 'socratic_probe' in params:
            return get_socratic_probe_from_params(params)
    return {}
