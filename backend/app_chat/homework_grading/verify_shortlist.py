# -*- coding: utf-8 -*-
"""老师看到的「需加强核实」短名单。

只服务这份名单。诊断用的 critical / careful 不在这里改。
高低和截取与《需加强核实的位置精进方案》及已跑通的模拟一致。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

TIER_LABEL = {
    'I': 'I · 最应该优先核验的',
    'II': 'II · 其次应该先核验的',
    'III': 'III · 再次可做核验的',
}


@dataclass
class _Unit:
    qid: str
    page: int
    qtype: str
    curriculum: str
    layout: str
    understanding: str
    grading: str
    label: str = ''


@dataclass
class _Zone:
    name: str
    evidence: List[str]


@dataclass
class _Scored:
    item: _Unit
    base: float
    q_bonus: float
    c_bonus: float
    run_bonus: float
    score: float
    reasons: List[str] = field(default_factory=list)
    tier: str = ''
    run_id: int = -1


def _is_white(s: str) -> bool:
    return s == 'white'


def _is_black(s: str) -> bool:
    return s == 'black'


def _is_gray(s: str) -> bool:
    return str(s or '').startswith('gray')


def _shades(it: _Unit) -> Tuple[str, str, str]:
    return it.layout or 'gray_mid', it.understanding or 'gray_mid', it.grading or 'gray_mid'


def _in_pool(it: _Unit) -> bool:
    shades = _shades(it)
    blacks = sum(1 for s in shades if _is_black(s))
    whites = sum(1 for s in shades if _is_white(s))
    if blacks:
        return True
    if whites == 0:
        return True
    if whites == 1:
        return True
    if whites == 2:
        gray = next(s for s in shades if not _is_white(s))
        return gray in ('gray_deep', 'gray_mid')
    return False


def _base_score(it: _Unit) -> Tuple[float, str]:
    shades = _shades(it)
    blacks = [name for name, s in zip(('版面', '理解', '批改'), shades) if _is_black(s)]
    whites = sum(1 for s in shades if _is_white(s))
    bonus = 0.0
    if '批改' in blacks:
        bonus += 8
    elif blacks == ['理解']:
        bonus += 3
    if len(blacks) >= 3:
        return 100 + bonus, '三步都偏黑'
    if len(blacks) == 2:
        return 80 + bonus, f"{'、'.join(blacks)}两步偏黑"
    if len(blacks) == 1:
        return 55 + bonus, f'{blacks[0]}一步偏黑'
    if whites == 0:
        return 62, '三步都没有白'
    if whites == 1:
        return 40, '一白两灰'
    gray = next(s for s in shades if not _is_white(s))
    if gray == 'gray_deep':
        return 28, '两白加深灰'
    return 18, '两白加中灰'


def _qid_key(qid: str):
    parts = re.split(r'[-_.]', qid)
    out = []
    for part in parts:
        out.append(int(part) if part.isdigit() else part)
    return out


def _order_key(it: _Unit):
    return (it.page, _qid_key(it.qid))


def _share(counter: Counter, key: str, total: int) -> float:
    if total <= 0 or not key:
        return 0.0
    return counter[key] / total


def _zone_factor(it: _Unit, zones: Sequence[_Zone], by_id: Dict[str, _Unit]) -> Tuple[float, List[str]]:
    cited_names = []
    sole = False
    for zone in zones:
        if it.qid not in zone.evidence:
            continue
        cited_names.append(zone.name)
        if len(zone.evidence) <= 2:
            sole = True
    if cited_names:
        reason = '被' + '、'.join(cited_names) + '建议用到'
        if sole:
            reason += '，且这条建议靠的题很少'
        return (1.0 if sole else 0.7), [reason]
    for zone in zones:
        for evid in zone.evidence:
            other = by_id.get(evid)
            if other and other.curriculum and other.curriculum == it.curriculum:
                return 0.5, [f'和{zone.name}用到的题同一课标']
    return 0.3, []


def _neighbor_unstable(it: _Unit, ordered: Sequence[_Unit], pool_ids: set) -> bool:
    ids = [x.qid for x in ordered]
    index = ids.index(it.qid)
    for j in (index - 1, index + 1):
        if 0 <= j < len(ids) and ids[j] in pool_ids:
            return True
    return False


def _paper_runs(ordered_all: Sequence[_Unit], pool_ids: set) -> List[List[str]]:
    runs: List[List[str]] = []
    cur: List[str] = []
    for it in ordered_all:
        if it.qid in pool_ids:
            cur.append(it.qid)
        else:
            if len(cur) >= 3:
                runs.append(cur)
            cur = []
    if len(cur) >= 3:
        runs.append(cur)
    return runs


def _page_of(raw: Dict[str, Any], qid: str) -> int:
    page = raw.get('page')
    if isinstance(page, int):
        return page
    try:
        if page is not None and str(page).strip().isdigit():
            return int(page)
    except (TypeError, ValueError):
        pass
    match = re.match(r'p(\d+):', qid)
    return int(match.group(1)) if match else 0


def _units_from_trust(wgb_trust: Dict[str, Any], *, skip_qtype: bool) -> List[_Unit]:
    by_qid = wgb_trust.get('by_qid') or {}
    units = []
    for qid, raw in by_qid.items():
        if not isinstance(raw, dict):
            continue
        qid = str(raw.get('qid_global') or qid or '').strip()
        if not qid:
            continue
        qtype = '' if skip_qtype else str(raw.get('qtype') or '').strip()
        units.append(_Unit(
            qid=qid,
            page=_page_of(raw, qid),
            qtype=qtype,
            curriculum=str(raw.get('curriculum') or '').strip(),
            layout=str(raw.get('layout_shade') or 'gray_mid'),
            understanding=str(raw.get('understanding_shade') or 'gray_mid'),
            grading=str(raw.get('grading_shade') or 'gray_mid'),
            label=str(raw.get('label') or '').strip(),
        ))
    return units


def _zones_from(raw_zones: Optional[Sequence[Dict[str, Any]]]) -> List[_Zone]:
    out = []
    for zone in raw_zones or []:
        if not isinstance(zone, dict):
            continue
        evidence = []
        for item in zone.get('evidence') or []:
            if isinstance(item, str) and item.strip():
                evidence.append(item.strip())
            elif isinstance(item, dict):
                qid = str(item.get('qid_global') or item.get('qid') or '').strip()
                if qid:
                    evidence.append(qid)
        if evidence:
            out.append(_Zone(str(zone.get('name') or '三区'), evidence))
    return out


def select_shortlist(
    wgb_trust: Optional[Dict[str, Any]],
    zones: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    skip_qtype: bool = False,
) -> List[Dict[str, Any]]:
    """返回已分档的名单。每条含 qid_global、label、level、reason。"""
    if not wgb_trust or not wgb_trust.get('by_qid'):
        return []
    ordered = sorted(_units_from_trust(wgb_trust, skip_qtype=skip_qtype), key=_order_key)
    zone_objs = _zones_from(zones)
    picked = _select(ordered, zone_objs)
    rows = []
    for scored in picked:
        it = scored.item
        local = it.qid.split(':', 1)[1] if ':' in it.qid else it.qid
        label = it.label or (f'第{it.page}页 · {local}题' if it.page else it.qid)
        rows.append({
            'qid_global': it.qid,
            'label': label,
            'level': scored.tier,
            'level_label': TIER_LABEL.get(scored.tier, scored.tier),
            'reason': '；'.join(scored.reasons),
            'page': it.page,
        })
    return rows


def _select(items: Sequence[_Unit], zones: Sequence[_Zone]) -> List[_Scored]:
    ordered = list(items)
    by_id = {it.qid: it for it in ordered}
    pool = [it for it in ordered if _in_pool(it)]
    pool_ids = {it.qid for it in pool}
    n = len(ordered)
    if n < 8:
        quota = len(pool)
    else:
        quota = min(30, max(3, round(n * 0.12)))
        quota = min(quota, len(pool))
    if quota <= 0:
        return []

    all_q = Counter(it.qtype for it in ordered if it.qtype)
    all_c = Counter(it.curriculum for it in ordered if it.curriculum)
    pool_q = Counter(it.qtype for it in pool if it.qtype)
    pool_c = Counter(it.curriculum for it in pool if it.curriculum)
    n_q = sum(all_q.values())
    n_c = sum(all_c.values())
    pn_q = sum(pool_q.values())
    pn_c = sum(pool_c.values())

    def lift(counter_pool, counter_all, key, pn, na):
        if not key:
            return 0.0
        return _share(counter_pool, key, pn) - _share(counter_all, key, na)

    q_lifts = {k: lift(pool_q, all_q, k, pn_q, n_q) for k in all_q}
    c_lifts = {k: lift(pool_c, all_c, k, pn_c, n_c) for k in all_c}
    q_cut = 0.08
    c_cut = 0.08
    runs = _paper_runs(ordered, pool_ids)
    run_of = {}
    for index, run in enumerate(runs):
        for qid in run:
            run_of[qid] = index

    scored: List[_Scored] = []
    for it in pool:
        base, base_reason = _base_score(it)
        ql = q_lifts.get(it.qtype, 0.0) if it.qtype else 0.0
        cl = c_lifts.get(it.curriculum, 0.0) if it.curriculum else 0.0
        factor, z_reasons = _zone_factor(it, zones, by_id)
        q_bonus = max(0.0, ql) * 80 * factor
        c_bonus = max(0.0, cl) * 80 * factor
        run = runs[run_of[it.qid]] if it.qid in run_of else []
        run_bonus = min(24.0, 12 + 3 * (len(run) - 3)) if run else 0.0
        reasons = [base_reason]
        if it.qtype and ql >= q_cut:
            reasons.append('重点关注的题型')
        if it.curriculum and cl >= c_cut:
            reasons.append('重点关注的课标要求')
        reasons.extend(z_reasons)
        if run:
            reasons.append('和前后题连成一段')
        scored.append(_Scored(
            it, base, q_bonus, c_bonus, run_bonus,
            base + q_bonus + c_bonus + run_bonus,
            reasons, '', run_of.get(it.qid, -1),
        ))
    by_scored = {s.item.qid: s for s in scored}

    def high_q(it: _Unit) -> bool:
        return bool(it.qtype) and q_lifts.get(it.qtype, 0) >= q_cut and q_lifts.get(it.qtype, 0) > 0

    def high_c(it: _Unit) -> bool:
        return bool(it.curriculum) and c_lifts.get(it.curriculum, 0) >= c_cut and c_lifts.get(it.curriculum, 0) > 0

    def some_lift(it: _Unit) -> bool:
        return (it.qtype and q_lifts.get(it.qtype, 0) > 0) or (it.curriculum and c_lifts.get(it.curriculum, 0) > 0)

    def cited(it: _Unit) -> bool:
        return any(it.qid in zone.evidence for zone in zones)

    def sole(it: _Unit) -> bool:
        return any(it.qid in zone.evidence and len(zone.evidence) <= 2 for zone in zones)

    def blacks_whites(it: _Unit):
        shades = _shades(it)
        return sum(1 for s in shades if _is_black(s)), sum(1 for s in shades if _is_white(s))

    def isolated(sc: _Scored) -> bool:
        blacks, whites = blacks_whites(sc.item)
        return blacks == 1 and whites == 2 and not cited(sc.item) and sc.run_id < 0

    def page_room(page: int, selected: Sequence[_Scored], ignore: Optional[str] = None) -> bool:
        n_page = sum(1 for s in selected if s.item.page == page and s.item.qid != ignore)
        return n_page < 3

    def take(groups: Sequence[Sequence[_Scored]]) -> List[_Scored]:
        selected: List[_Scored] = []
        seen = set()
        for group in groups:
            for sc in group:
                if len(selected) >= quota:
                    return selected
                if sc.item.qid in seen or not page_room(sc.item.page, selected):
                    continue
                selected.append(sc)
                seen.add(sc.item.qid)
        return selected

    dark = sorted((s for s in scored if blacks_whites(s.item)[0] >= 2), key=lambda s: -s.score)
    soles = sorted((s for s in scored if sole(s.item)), key=lambda s: -s.score)
    rest_scored = sorted((s for s in scored if not isolated(s)), key=lambda s: -s.score)
    chosen = take([dark, soles, rest_scored])

    def diversify(chosen_list: List[_Scored], attr: str) -> List[_Scored]:
        pool_vals = {getattr(s.item, attr) for s in scored if getattr(s.item, attr)}
        if len(pool_vals) < 3:
            return chosen_list
        selected = list(chosen_list)
        for _ in range(4):
            vals = [getattr(s.item, attr) for s in selected if getattr(s.item, attr)]
            if len(set(vals)) >= min(3, len(pool_vals)):
                break
            missing = pool_vals - set(vals)
            outside = [
                s for s in scored
                if s.item.qid not in {x.item.qid for x in selected}
                and getattr(s.item, attr) in missing
                and not isolated(s)
            ]
            if not outside:
                break
            incoming = max(outside, key=lambda s: s.score)
            counts = Counter(vals)
            donors = [
                s for s in selected
                if getattr(s.item, attr) and counts[getattr(s.item, attr)] > 1
                and not sole(s.item) and blacks_whites(s.item)[0] < 2
            ]
            if not donors:
                break
            outgoing = min(donors, key=lambda s: s.score)
            if incoming.score + 70 < outgoing.score:
                break
            if not page_room(incoming.item.page, selected, ignore=outgoing.item.qid):
                break
            selected = [incoming if s is outgoing else s for s in selected]
        return selected

    if any(s.item.qtype for s in scored):
        chosen = diversify(chosen, 'qtype')
    if any(s.item.curriculum for s in scored):
        chosen = diversify(chosen, 'curriculum')
    chosen_ids = {s.item.qid for s in chosen}
    for sc in sorted((s for s in scored if isolated(s)), key=lambda s: -s.score):
        if len(chosen) >= quota:
            break
        if sc.item.qid not in chosen_ids and page_room(sc.item.page, chosen):
            chosen.append(sc)
            chosen_ids.add(sc.item.qid)
    if len(chosen) < quota:
        for sc in sorted(scored, key=lambda s: -s.score):
            if len(chosen) >= quota:
                break
            if sc.item.qid in chosen_ids or not page_room(sc.item.page, chosen):
                continue
            chosen.append(sc)
            chosen_ids.add(sc.item.qid)

    def initial_i(sc: _Scored) -> bool:
        blacks, whites = blacks_whites(sc.item)
        semantic = high_q(sc.item) or high_c(sc.item)
        in_run = sc.run_id >= 0
        if blacks >= 2 and (cited(sc.item) or in_run or semantic):
            return True
        if (blacks == 1 or whites == 0) and (
            (sole(sc.item) and _neighbor_unstable(sc.item, ordered, pool_ids)) or semantic
        ):
            return True
        return False

    selected = [by_scored[s.item.qid] for s in chosen]
    band_i = [s for s in selected if initial_i(s)]
    rest = [s for s in selected if s not in band_i]
    lo = math.ceil(quota / 4) if quota else 0
    hi = max(lo, math.ceil(quota / 3)) if quota else 0
    if 0 < quota <= 2:
        lo, hi = 1, 1

    def keep_rank(sc: _Scored) -> Tuple[int, float]:
        blacks, _whites = blacks_whites(sc.item)
        if blacks >= 2 and sole(sc.item):
            return (5, sc.score)
        if blacks >= 2 and cited(sc.item):
            return (4, sc.score)
        if blacks >= 2:
            return (3, sc.score)
        return (1 if (high_q(sc.item) or high_c(sc.item)) else 0, sc.score)

    band_i.sort(key=keep_rank, reverse=True)
    rest.sort(key=lambda s: -s.score)
    if len(band_i) > hi:
        rest = band_i[hi:] + rest
        band_i = band_i[:hi]
    while len(band_i) < lo and rest:
        band_i.append(rest.pop(0))

    def is_ii(sc: _Scored) -> bool:
        blacks, whites = blacks_whites(sc.item)
        shades = _shades(sc.item)
        if blacks >= 2:
            return True
        if (blacks == 1 or whites == 0) and (some_lift(sc.item) or sc.run_id >= 0):
            return True
        if whites == 1 and blacks == 0 and cited(sc.item):
            return True
        if whites == 2 and blacks == 0 and any(s == 'gray_deep' for s in shades) and cited(sc.item):
            return True
        return False

    band_ii, band_iii = [], []
    for sc in rest:
        (band_ii if is_ii(sc) else band_iii).append(sc)
    for sc in band_i:
        sc.tier = 'I'
    for sc in band_ii:
        sc.tier = 'II'
    for sc in band_iii:
        sc.tier = 'III'

    listed_ids = {s.item.qid for s in band_i + band_ii + band_iii}
    pending = [sc for sc in scored if sc.item.qid not in listed_ids and cited(sc.item)]

    def insert_urgency(sc: _Scored) -> Tuple[int, int, float]:
        blacks, whites = blacks_whites(sc.item)
        shades = _shades(sc.item)
        if blacks >= 3:
            shade_rank = 6
        elif blacks == 2:
            shade_rank = 5
        elif blacks == 1 or whites == 0:
            shade_rank = 4
        elif whites == 1:
            shade_rank = 3
        elif any(s == 'gray_deep' for s in shades):
            shade_rank = 2
        else:
            shade_rank = 1
        return (shade_rank, 1 if sole(sc.item) else 0, sc.score)

    already_i = [sc for sc in pending if initial_i(sc)]
    rest_pending = [sc for sc in pending if sc not in already_i]
    rest_pending.sort(key=insert_urgency, reverse=True)
    promote_n = max(0, math.ceil(len(pending) / 2) - len(already_i)) if pending else 0
    promote = {id(sc) for sc in rest_pending[:promote_n]}
    for sc in sorted(pending, key=lambda s: _order_key(s.item)):
        if sc in already_i or id(sc) in promote:
            band_i.append(sc)
            sc.tier = 'I'
        elif is_ii(sc):
            band_ii.append(sc)
            sc.tier = 'II'
        else:
            band_iii.append(sc)
            sc.tier = 'III'

    def sort_tier(group: List[_Scored]) -> List[_Scored]:
        return sorted(group, key=lambda s: _order_key(s.item))

    return sort_tier(band_i) + sort_tier(band_ii) + sort_tier(band_iii)


def pack_verification_block(items: Sequence[Dict[str, Any]], unit_word: str = '题') -> Dict[str, Any]:
    rows = [x for x in items if isinstance(x, dict) and x.get('qid_global')]
    counts = Counter(str(x.get('level') or '') for x in rows)
    n_i, n_ii, n_iii = counts.get('I', 0), counts.get('II', 0), counts.get('III', 0)
    if not rows:
        return {
            'status': 'ok',
            'title': '需加强核实的位置',
            'summary': '当前逐页素材中，未发现需要特别加强核实的位置。',
            'conclusion_note': '',
            'items': [],
            'critical_count': 0,
            'careful_count': 0,
            'tier_counts': {'I': 0, 'II': 0, 'III': 0},
            'unit_word': unit_word or '题',
        }
    summary = (
        f'共 {len(rows)} 处。I {n_i} 处最应该优先核验，II {n_ii} 处其次，III {n_iii} 处再次可做核验。'
        f'鼠标停在题号上可看到为什么核这道。'
    )
    return {
        'status': 'needs_review',
        'title': '需加强核实的位置',
        'summary': summary,
        'conclusion_note': '',
        'items': list(rows),
        'critical_count': 0,
        'careful_count': 0,
        'tier_counts': {'I': n_i, 'II': n_ii, 'III': n_iii},
        'unit_word': unit_word or '题',
    }


def drop_verified_items(block: Optional[Dict[str, Any]], verified_qids: Sequence[str]) -> Dict[str, Any]:
    """核验后的迭代更新：不重算档位，只去掉已经核过的题。"""
    verified = {str(qid) for qid in (verified_qids or []) if qid}
    src = block if isinstance(block, dict) else {}
    kept = [
        dict(item) for item in (src.get('items') or [])
        if isinstance(item, dict) and str(item.get('qid_global') or '') not in verified
    ]
    packed = pack_verification_block(kept, src.get('unit_word') or '题')
    if src.get('cross_counts'):
        packed['cross_counts'] = src.get('cross_counts')
    return packed
