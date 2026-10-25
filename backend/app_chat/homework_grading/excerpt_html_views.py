# -*- coding: utf-8 -*-
"""批改·解释精要卡 HTML 视图：图表切换 / 白灰黑与对错图标 / 侧栏导航。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .confidence_zones import SHADE_DISPLAY, SHADE_ORDER
from .excerpt_card_render import (
    _MATERIAL_CN,
    _SHADE_COLOR,
    _SHADE_INK,
    _ZONE_CN,
    _bucket_breakdown,
    _build_rich_overview,
    _clip_keep_lines,
    _comment_html,
    _esc,
    _hub_title,
    _human_evidence,
    _is_black,
    _is_gray,
    _is_white,
    _shade_dot_html,
    _unit_heading,
    _verdict_badge_html,
)


def _esc_json(value: Any) -> str:
    """嵌入 <script type=application/json>，防 </script> 打断。"""
    text = json.dumps(value if value is not None else {}, ensure_ascii=False)
    return text.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

_OPEN_NO_QTYPE = frozenset({'notes', 'note', 'essay', 'composition', 'open', 'other'})
_HUB_ZONE_STYLE = {
    'blind_spot': {'border': '#e05252', 'bg': '#fff6f6', 'ink': '#b5342a'},
    'friction_zone': {'border': '#e07c28', 'bg': '#fff8f2', 'ink': '#a05a14'},
    'zpd': {'border': '#3a9e6a', 'bg': '#f4fbf7', 'ink': '#236b45'},
}


def _has_discrete_qtype(material_type: str) -> bool:
    return (material_type or '').lower() not in _OPEN_NO_QTYPE


def _unit_evidence_ref(unit: Dict[str, Any]) -> str:
    qid = str(unit.get('qid') or '').strip() or '?'
    try:
        page = int(unit.get('page'))
    except (TypeError, ValueError):
        return qid
    return f'p{page}:{qid}'


def _chip_label(page: Any, qid: str, *, material_type: str = 'homework') -> str:
    """与批改独立界面题号芯片一致：第21页 · 4题。"""
    qid = str(qid or '').strip() or '?'
    word = '条目' if (material_type or '').lower() in _OPEN_NO_QTYPE else '题'
    if qid.startswith('auto-'):
        qid = qid[5:]
    try:
        page_n = int(page)
    except (TypeError, ValueError):
        page_n = page
    return f'第{page_n}页 · {qid}{word}'


def _loc_chip_html(label: str, evidence: str) -> str:
    return (
        f'<a href="#" class="loc-jump" data-evidence="{_esc(evidence)}" '
        f'title="在批改独立界面打开对应位置">{_esc(label)}</a>'
    )


def _loc_chips_html(
    units: List[Dict[str, Any]],
    *,
    fold_after: int = 6,
    material_type: str = 'homework',
) -> str:
    if not units:
        return '—'
    chips = []
    for u in units:
        ref = _unit_evidence_ref(u)
        label = _chip_label(u.get('page'), u.get('qid') or '?', material_type=material_type)
        chips.append(_loc_chip_html(label, ref))
    return _fold_chip_list(chips, fold_after=fold_after)


def _loc_chips_from_evidence(
    qids: List[Any],
    *,
    fold_after: int = 6,
    material_type: str = 'homework',
) -> str:
    chips = []
    for raw in qids or []:
        text = str(raw or '').strip()
        if not text:
            continue
        m = re.match(r'^p(\d+)[:：](.+)$', text, re.I)
        if m:
            label = _chip_label(m.group(1), m.group(2), material_type=material_type)
        else:
            label = _human_evidence(text, material_type=material_type)
        chips.append(_loc_chip_html(label, text))
    if not chips:
        return '—'
    return _fold_chip_list(chips, fold_after=fold_after)


def _fold_chip_list(chips: List[str], *, fold_after: int = 6) -> str:
    if len(chips) <= fold_after:
        return f'<span class="loc-list">{"".join(chips)}</span>'
    short = ''.join(chips[:fold_after])
    full = ''.join(chips)
    n = len(chips)
    return (
        f'<span class="loc-wrap" data-folded="1">'
        f'<span class="loc-short">{short}</span>'
        f'<span class="loc-all" hidden>{full}</span>'
        f'<button type="button" class="loc-toggle" aria-expanded="false">展开全部 {n}</button>'
        f'</span>'
    )


def _stage_counts(units: List[Dict[str, Any]]):
    layout = {k: 0 for k in SHADE_ORDER}
    und = {k: 0 for k in SHADE_ORDER}
    grade = {k: 0 for k in SHADE_ORDER}
    for u in units:
        layout[u['layout_shade']] = layout.get(u['layout_shade'], 0) + 1
        und[u['understanding_shade']] = und.get(u['understanding_shade'], 0) + 1
        grade[u['grading_shade']] = grade.get(u['grading_shade'], 0) + 1
    return layout, und, grade


def _stack_bar_html(counts: Dict[str, int]) -> str:
    segs = []
    for k in SHADE_ORDER:
        n = int(counts.get(k) or 0)
        if not n:
            continue
        # 浅底用深字，深底用浅字，保证条上字可读
        ink = '#1c2430' if k in ('white', 'gray_light') else _SHADE_INK.get(k, '#fff')
        segs.append(
            f'<span class="seg" style="flex:{n};background:{_SHADE_COLOR[k]};color:{ink}" '
            f'title="{_esc(SHADE_DISPLAY[k])} {n}">{_esc(SHADE_DISPLAY[k])} {n}</span>'
        )
    empty = '<span class="seg empty">暂无</span>'
    return f'<div class="stack" role="img">{"".join(segs) or empty}</div>'


def _cross_buckets(units: List[Dict[str, Any]], *, show_qtype: bool = True) -> List[Dict[str, Any]]:
    black_count = lambda u: sum(
        1 for k in ('layout_shade', 'understanding_shade', 'grading_shade') if _is_black(u[k])
    )
    gray_count = lambda u: sum(
        1 for k in ('layout_shade', 'understanding_shade', 'grading_shade') if _is_gray(u[k])
    )
    white_count = lambda u: sum(
        1 for k in ('layout_shade', 'understanding_shade', 'grading_shade') if _is_white(u[k])
    )
    # 每张卡都给位置；题型仅题目型材料（作文/笔记/其他等开放材料无题型）
    base = {'show_loc': True, 'show_qtype': bool(show_qtype)}
    return [
        {
            'key': 'all_white',
            'title': '三步都是白区',
            'hint': '三步把握都很稳（白区）',
            'color': '#2f7d4a',
            'units': [u for u in units if white_count(u) == 3],
            **base,
        },
        {
            'key': 'black_layout',
            'title': '版面黑区位置',
            'hint': '版面步骤落在黑区',
            'color': '#1f1f1f',
            'units': [u for u in units if _is_black(u['layout_shade'])],
            **base,
        },
        {
            'key': 'black_und',
            'title': '理解黑区位置',
            'hint': '理解步骤落在黑区',
            'color': '#1f1f1f',
            'units': [u for u in units if _is_black(u['understanding_shade'])],
            **base,
        },
        {
            'key': 'black_grade',
            'title': '批改黑区位置',
            'hint': '批改步骤落在黑区',
            'color': '#1f1f1f',
            'units': [u for u in units if _is_black(u['grading_shade'])],
            **base,
        },
        {
            'key': 'three_black',
            'title': '三步都是黑区',
            'hint': '优先人工复核',
            'color': '#1f1f1f',
            'units': [u for u in units if black_count(u) == 3],
            **base,
        },
        {
            'key': 'two_black',
            'title': '两步黑区',
            'hint': '两步需核验',
            'color': '#555550',
            'units': [u for u in units if black_count(u) == 2],
            **base,
        },
        {
            'key': 'two_white_one_black',
            'title': '两步白区、一步黑区',
            'hint': '那两步「白」的可信度可能下降，建议核验',
            'color': '#b4453b',
            'units': [u for u in units if white_count(u) == 2 and black_count(u) == 1],
            **base,
        },
        {
            'key': 'two_white_one_gray',
            'title': '两步白区、一步灰区',
            'hint': '整体较稳，灰档那一步留意',
            'color': '#8e8e88',
            'units': [u for u in units if white_count(u) == 2 and gray_count(u) == 1],
            'show_gray': True,
            **base,
        },
        {
            'key': 'one_white_two_gray',
            'title': '一步白区、两步灰区',
            'hint': '需抽查灰区步骤',
            'color': '#8a6828',
            'units': [u for u in units if white_count(u) == 1 and gray_count(u) == 2],
            **base,
        },
        {
            'key': 'all_gray',
            'title': '三步都是灰区',
            'hint': '整体把握一般',
            'color': '#8e8e88',
            'units': [u for u in units if gray_count(u) == 3],
            **base,
        },
        {
            'key': 'no_white',
            'title': '三步都没有白区',
            'hint': '建议优先回看',
            'color': '#555550',
            'units': [u for u in units if white_count(u) == 0],
            **base,
        },
    ]


def _pattern_bars_html(buckets: List[Dict[str, Any]], total: int) -> str:
    total = max(total, 1)
    rows = []
    for b in buckets:
        n = len(b['units'])
        pct = round(100.0 * n / total)
        width = max(2, pct) if n else 0
        rows.append(
            f'<div class="pat-row">'
            f'<div class="pat-label">{_esc(b["title"])}</div>'
            f'<div class="pat-track"><span class="pat-fill" style="width:{width}%;background:{b["color"]}"></span></div>'
            f'<div class="pat-num">{n}（{pct}%）</div></div>'
        )
    return f'<div class="pat-bars">{"".join(rows)}</div>'


def _qtype_bars_html(units: List[Dict[str, Any]], *, color: str = '#2c6b5a') -> str:
    if not units:
        return '<p class="muted">暂无</p>'
    from collections import Counter
    total = len(units) or 1
    counter = Counter(str(u.get('qtype') or '未标注') for u in units)
    rows = []
    for name, count in counter.most_common(12):
        pct = round(100.0 * count / total)
        width = max(2, pct) if count else 0
        rows.append(
            f'<div class="pat-row">'
            f'<div class="pat-label">{_esc(name)}</div>'
            f'<div class="pat-track"><span class="pat-fill" style="width:{width}%;background:{color}"></span></div>'
            f'<div class="pat-num">{count}（{pct}%）</div></div>'
        )
    return f'<div class="pat-bars">{"".join(rows)}</div>'


def _pattern_qtype_panels_html(buckets: List[Dict[str, Any]]) -> str:
    blocks = []
    for b in buckets:
        if not b['units']:
            continue
        blocks.append(
            f'<div class="cross-block">'
            f'<div class="cross-block-head">'
            f'<span class="cross-block-title">{_esc(b["title"])}</span>'
            f'<span class="cross-block-n">{len(b["units"])}</span></div>'
            f'{_qtype_bars_html(b["units"], color=b.get("color") or "#2c6b5a")}'
            f'</div>'
        )
    return ''.join(blocks) or '<p class="muted">暂无题型分布</p>'


def _qtype_pattern_panels_html(buckets: List[Dict[str, Any]], units: List[Dict[str, Any]]) -> str:
    from collections import defaultdict
    if not units:
        return '<p class="muted">暂无</p>'
    by_qtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for u in units:
        by_qtype[str(u.get('qtype') or '未标注')].append(u)
    # 预计算每题所属第一匹配桶（按桶顺序，黑区位置类与交叉类可能重叠；展示时按全部桶计数）
    blocks = []
    for qtype, q_units in sorted(by_qtype.items(), key=lambda x: -len(x[1])):
        rows = []
        total = len(q_units) or 1
        for b in buckets:
            ids = {(x.get('page'), x.get('qid')) for x in b['units']}
            matched = [u for u in q_units if (u.get('page'), u.get('qid')) in ids]
            if not matched:
                continue
            pct = round(100.0 * len(matched) / total)
            width = max(2, pct)
            rows.append(
                f'<div class="pat-row">'
                f'<div class="pat-label">{_esc(b["title"])}</div>'
                f'<div class="pat-track"><span class="pat-fill" style="width:{width}%;background:{b["color"]}"></span></div>'
                f'<div class="pat-num">{len(matched)}（{pct}%）</div></div>'
            )
        if not rows:
            continue
        blocks.append(
            f'<div class="cross-block">'
            f'<div class="cross-block-head">'
            f'<span class="cross-block-title">{_esc(qtype)}</span>'
            f'<span class="cross-block-n">{len(q_units)}</span></div>'
            f'<div class="pat-bars">{"".join(rows)}</div></div>'
        )
    return ''.join(blocks) or '<p class="muted">暂无交叉情形分布</p>'


def _cross_qtype_detail_md(buckets: List[Dict[str, Any]], units: List[Dict[str, Any]]) -> str:
    """文字版：各情形题型占比 + 各题型交叉情形占比。"""
    from collections import defaultdict
    lines = ['', '#### 各交叉情形的题型占比', '']
    for b in buckets:
        if not b['units']:
            continue
        lines.append(f'- **{b["title"]}**：{_bucket_breakdown(b["units"])}')
    lines.extend(['', '#### 各题型的交叉情形占比', ''])
    by_qtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for u in units:
        by_qtype[str(u.get('qtype') or '未标注')].append(u)
    for qtype, q_units in sorted(by_qtype.items(), key=lambda x: -len(x[1])):
        parts = []
        total = len(q_units) or 1
        for b in buckets:
            ids = {(x.get('page'), x.get('qid')) for x in b['units']}
            n = sum(1 for u in q_units if (u.get('page'), u.get('qid')) in ids)
            if n:
                parts.append(f'{b["title"]} {n}（{round(100.0 * n / total)}%）')
        if parts:
            lines.append(f'- **{qtype}**：{"；".join(parts)}')
    return '\n'.join(lines)


def _verify_banner_html(
    user_verification: Optional[Dict[str, Any]],
    *,
    material_type: str = 'homework',
) -> str:
    """复刻独立批改面板「需加强核实的位置」，并带核验按钮。"""
    block = user_verification if isinstance(user_verification, dict) else {}
    items = [x for x in (block.get('items') or []) if isinstance(x, dict)]
    if not items:
        return ''
    title = _esc(block.get('title') or '需加强核实的位置')
    summary = _esc(block.get('summary') or '')
    tier_counts = block.get('tier_counts') if isinstance(block.get('tier_counts'), dict) else {}
    headings = (
        ('I', 'I · 最应该优先核验的', 'i'),
        ('II', 'II · 其次应该先核验的', 'ii'),
        ('III', 'III · 再次可做核验的', 'iii'),
    )
    grouped = {level: [] for level, _heading, _cls in headings}
    other = []
    for it in items:
        qid = str(it.get('qid_global') or '').strip()
        if not qid:
            continue
        level = str(it.get('level') or '')
        (grouped[level] if level in grouped else other).append(it)
    counts = []
    tiers_html = []
    for level, heading, cls in headings:
        group = grouped[level]
        if not group:
            continue
        n = int(tier_counts.get(level) or len(group))
        counts.append(f'<em class="uv-c-{cls}">{level} {n}</em>')
        rows = []
        for it in group:
            qid = str(it.get('qid_global') or '').strip()
            label = _esc(it.get('label') or qid)
            reason = _esc(it.get('reason') or '')
            rows.append(
                f'<div class="uv-row" data-qid="{_esc(qid)}" data-label="{label}" data-level="{_esc(level)}">'
                f'<a class="loc-jump uv-chip is-{cls}" href="#" data-evidence="{_esc(qid)}" title="{reason}">{label}</a>'
                f'<button type="button" class="uv-verify-btn" data-qid="{_esc(qid)}" data-label="{label}">提交核验</button>'
                f'<span class="uv-done-mark" hidden>已核验</span>'
                f'</div>'
            )
        tiers_html.append(
            f'<div class="uv-tier" data-tier="{level}">'
            f'<div class="uv-tier-name">{_esc(heading)} <em>{len(group)}</em></div>'
            f'{"".join(rows)}</div>'
        )
    if other:
        rows = []
        for it in other:
            qid = str(it.get('qid_global') or '').strip()
            label = _esc(it.get('label') or qid)
            reason = _esc(it.get('reason') or '')
            rows.append(
                f'<div class="uv-row" data-qid="{_esc(qid)}" data-label="{label}">'
                f'<a class="loc-jump uv-chip" href="#" data-evidence="{_esc(qid)}" title="{reason}">{label}</a>'
                f'<button type="button" class="uv-verify-btn" data-qid="{_esc(qid)}" data-label="{label}">提交核验</button>'
                f'<span class="uv-done-mark" hidden>已核验</span>'
                f'</div>'
            )
        tiers_html.append(f'<div class="uv-tier">{"".join(rows)}</div>')
    return (
        f'<section class="uv-banner" id="uv-verify-banner" aria-label="需加强核实">'
        f'<div class="uv-head"><strong>{title}</strong>'
        f'<span class="uv-counts">{"".join(counts)}</span></div>'
        f'<p class="uv-summary">{summary}</p>'
        f'<div class="uv-list" data-folded="0">'
        f'<div class="uv-short">{"".join(tiers_html)}</div></div>'
        f'<div class="uv-actions">'
        f'<button type="button" class="uv-iterate-btn" id="uv-iterate-btn">迭代更新批改结果</button>'
        f'<span class="uv-iterate-hint">可只核验部分位置；点此按已提交核验回写当次批改（不新开归档）。</span>'
        f'</div></section>'
    )


def _cross_visual_html(
    units: List[Dict[str, Any]],
    detail_md: str,
    *,
    material_type: str = 'homework',
    user_verification: Optional[Dict[str, Any]] = None,
) -> str:
    show_qtype = _has_discrete_qtype(material_type)
    buckets = _cross_buckets(units, show_qtype=show_qtype)
    n = len(units)
    cards = []
    for b in buckets:
        body_bits = []
        if b.get('show_loc') and b['units']:
            body_bits.append(
                f'<p class="meta"><strong>位置</strong> '
                f'{_loc_chips_html(b["units"], fold_after=6, material_type=material_type)}</p>'
            )
        if b.get('show_qtype') and b['units']:
            body_bits.append(f'<p class="meta"><strong>题型</strong> {_esc(_bucket_breakdown(b["units"]))}</p>')
        if b.get('show_gray') and b['units']:
            gray_parts = []
            for shade in ('gray_deep', 'gray_mid', 'gray_light'):
                cnt = sum(
                    1 for u in b['units']
                    for k in ('layout_shade', 'understanding_shade', 'grading_shade')
                    if u[k] == shade
                )
                if cnt:
                    gray_parts.append(f'{SHADE_DISPLAY[shade]} {cnt}')
            if gray_parts:
                body_bits.append(f'<p class="meta"><strong>灰档</strong> {" · ".join(gray_parts)}</p>')
        pct = round(100.0 * len(b['units']) / max(n, 1))
        cards.append(
            f'<article class="stat-card" style="--accent:{b["color"]}">'
            f'<header><span class="stat-title">{_esc(b["title"])}</span>'
            f'<span class="stat-count">{len(b["units"])}（{pct}%）</span></header>'
            f'<p class="stat-hint">{_esc(b["hint"])}</p>'
            f'{"".join(body_bits)}</article>'
        )

    # 完整说明：原 markdown + 题型交叉文字（题目型材料）
    detail_body = detail_md or ''
    if show_qtype:
        extra = _cross_qtype_detail_md(buckets, units)
        if extra.strip() and '各交叉情形的题型占比' not in detail_body:
            detail_body = (detail_body.rstrip() + '\n' + extra).strip()
    verify_html = _verify_banner_html(user_verification, material_type=material_type)
    detail = (
        f'<details class="more"><summary>展开完整交叉说明</summary>{_md_lite(detail_body)}</details>'
        if detail_body else ''
    )

    pattern_pane = (
        f'{_pattern_bars_html(buckets, n)}'
        f'<div class="stat-grid">{"".join(cards)}</div>'
    )
    if show_qtype:
        subtabs = (
            '<div class="cross-subtabs" role="tablist">'
            '<button type="button" class="cross-subtab active" data-cross-view="pattern">交叉情形分布</button>'
            '<button type="button" class="cross-subtab" data-cross-view="by-pattern-qtype">各情形的题型占比</button>'
            '<button type="button" class="cross-subtab" data-cross-view="by-qtype-pattern">各题型的交叉情形占比</button>'
            '</div>'
        )
        panes = (
            f'<div class="cross-pane active" data-cross-view="pattern">{pattern_pane}</div>'
            f'<div class="cross-pane" data-cross-view="by-pattern-qtype">'
            f'<p class="hint">每种交叉情形下，题型如何分布。</p>'
            f'{_pattern_qtype_panels_html(buckets)}</div>'
            f'<div class="cross-pane" data-cross-view="by-qtype-pattern">'
            f'<p class="hint">每种题型分别落在哪些交叉情形、占比多少。</p>'
            f'{_qtype_pattern_panels_html(buckets, units)}</div>'
        )
        qtype_hint = '位置与题型'
        return (
            f'<h3>交叉情况</h3>{subtabs}'
            f'<p class="hint">先看比例条找规律，再看卡片里的{qtype_hint}；点位置芯片可跳到批改独立界面。</p>'
            f'{panes}{verify_html}{detail}'
        )
    return (
        f'<h3>交叉情况</h3>'
        f'<p class="hint">先看比例条找规律，再看卡片里的位置；点位置芯片可跳到批改独立界面。</p>'
        f'{pattern_pane}{verify_html}{detail}'
    )


def _curr_visual_html(units: List[Dict[str, Any]], curr_md: str, composite_md: str) -> str:
    white = lambda u: sum(
        1 for k in ('layout_shade', 'understanding_shade', 'grading_shade') if _is_white(u[k])
    )
    black = lambda u: sum(
        1 for k in ('layout_shade', 'understanding_shade', 'grading_shade') if _is_black(u[k])
    )
    buckets = [
        (
            '多数步骤很稳（白区）、仅一步需人工核验时，对应课标要求集中于',
            [u for u in units if white(u) == 2 and black(u) == 1],
        ),
        (
            '有两步需人工核验时，对应课标要求集中于',
            [u for u in units if black(u) == 2],
        ),
        (
            '三步都偏灰或黑、建议优先复核时，对应课标要求集中于',
            [u for u in units if white(u) == 0],
        ),
        (
            '三步都很稳（白区）时，对应课标要求集中于',
            [
                u for u in units
                if all(_is_white(u[k]) for k in ('layout_shade', 'understanding_shade', 'grading_shade'))
            ],
        ),
    ]
    cards = []
    from collections import Counter
    for title, bucket in buckets:
        with_c = [u for u in bucket if u.get('curriculum')]
        if not with_c:
            continue
        total = len(with_c) or 1
        counter = Counter(str(u.get('curriculum') or '未标注') for u in with_c)
        bars = []
        for name, count in counter.most_common(6):
            pct = round(100.0 * count / total)
            bars.append(
                f'<div class="curr-row"><span class="curr-name">{_esc(name)}</span>'
                f'<span class="curr-track"><i style="width:{max(4, pct)}%"></i></span>'
                f'<span class="curr-n">{count}（{pct}%）</span></div>'
            )
        cards.append(
            f'<article class="curr-card">'
            f'<h4>{_esc(title)}</h4>'
            f'{"".join(bars)}</article>'
        )
    comp = ''
    if composite_md:
        body = re.sub(r'^###[^\n]*\n?', '', composite_md).strip()
        body = re.sub(r'^（三步加权）\s*', '', body)
        comp = (
            f'<article class="composite-card">'
            f'<h4>综合白灰黑（三步加权）</h4>'
            f'{_md_lite(body)}</article>'
        )
    detail = f'<details class="more"><summary>展开完整课标说明</summary>{_md_lite(curr_md)}</details>' if curr_md else ''
    return (
        f'<h3>课标分布与综合把握</h3>'
        f'<p class="hint">按交叉情形看对应课标要求集中于哪里；「很稳」=白区。下方是三步加权后的综合白灰黑。</p>'
        f'<div class="curr-grid">{"".join(cards) or "<p>暂无课标归属统计</p>"}</div>'
        f'{comp}{detail}'
    )


def _md_lite(text: str) -> str:
    if not text:
        return ''
    out: List[str] = []
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('| ') and i + 1 < len(lines) and set(
            lines[i + 1].replace('|', '').replace('-', '').replace(' ', '')
        ) == set():
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                if '---' in lines[i]:
                    i += 1
                    continue
                cells = [c.strip() for c in lines[i].strip('|').split('|')]
                rows.append(cells)
                i += 1
            if rows:
                out.append('<table>')
                out.append('<thead><tr>' + ''.join(f'<th>{_esc(c)}</th>' for c in rows[0]) + '</tr></thead>')
                out.append('<tbody>')
                for r in rows[1:]:
                    out.append('<tr>' + ''.join(f'<td>{_esc(c)}</td>' for c in r) + '</tr>')
                out.append('</tbody></table>')
            continue
        if line.startswith('#### '):
            out.append(f'<h4>{_esc(line[5:])}</h4>')
        elif line.startswith('### '):
            out.append(f'<h3>{_esc(line[4:])}</h3>')
        elif line.startswith('## '):
            out.append(f'<h2>{_esc(line[3:])}</h2>')
        elif line.startswith('# '):
            out.append(f'<h1>{_esc(line[2:])}</h1>')
        elif line.startswith('- '):
            out.append('<ul>')
            while i < len(lines) and lines[i].startswith('- '):
                t = lines[i][2:]
                parts = re.split(r'(\*\*.+?\*\*)', t)
                buf = []
                for p in parts:
                    if p.startswith('**') and p.endswith('**'):
                        buf.append('<strong>' + _esc(p[2:-2]) + '</strong>')
                    else:
                        buf.append(_esc(p))
                out.append('<li>' + ''.join(buf) + '</li>')
                i += 1
            out.append('</ul>')
            continue
        elif line.strip():
            out.append(f'<p>{_esc(line)}</p>')
        i += 1
    return '\n'.join(out)


def _split_overview_chunks(overview_md: str) -> Dict[str, str]:
    text = overview_md or ''
    chunks = {'cross': '', 'curr': '', 'composite': ''}

    def _body_after(heading_prefix: str) -> str:
        if heading_prefix not in text:
            return ''
        part = text.split(heading_prefix, 1)[1]
        # 去掉标题残留括号行，避免「（三步骤合起来看）」再出现一次
        part = re.sub(r'^（[^）]{0,24}）\s*\n?', '', part.lstrip())
        if '\n### ' in part:
            part = part.split('\n### ', 1)[0]
        if '\n## ' in part:
            part = part.split('\n## ', 1)[0]
        return part.strip()

    chunks['cross'] = _body_after('### 交叉情况')
    chunks['curr'] = _body_after('### 课标分布')
    chunks['composite'] = _body_after('### 综合白灰黑')
    return chunks


def _overview_visual_html(
    units: List[Dict[str, Any]],
    overview_md: str,
    *,
    material_type: str = 'homework',
    user_verification: Optional[Dict[str, Any]] = None,
) -> str:
    if not units:
        return f'<div class="panel">{_md_lite(overview_md)}</div>'
    layout, und, grade = _stage_counts(units)
    legend = ''.join(f'<span class="legend-item">{_shade_dot_html(k)}</span>' for k in SHADE_ORDER)
    rows = [
        ('layout', '无损版面', layout),
        ('understanding', '无损理解', und),
        ('grading', '三区批改', grade),
    ]
    bar_rows = []
    table_rows = []
    for _key, title, counts in rows:
        bar_rows.append(
            f'<div class="bar-row"><div class="bar-label">{_esc(title)}</div>'
            f'{_stack_bar_html(counts)}</div>'
        )
        cells = ''.join(f'<td>{int(counts.get(k) or 0)}</td>' for k in SHADE_ORDER)
        table_rows.append(f'<tr><th>{_esc(title)}</th>{cells}</tr>')
    chunks = _split_overview_chunks(overview_md)
    cross_html = _cross_visual_html(
        units, chunks['cross'],
        material_type=material_type,
        user_verification=user_verification,
    )
    curr_html = _curr_visual_html(units, chunks['curr'], chunks['composite'])
    ths = ''.join(f'<th>{_esc(SHADE_DISPLAY[k])}</th>' for k in SHADE_ORDER)
    return f'''
<section class="panel overview-visual" id="sec-overview">
  <div class="panel-head">
    <h2>总览：三步骤 × 白灰黑</h2>
    <div class="view-tabs" role="tablist">
      <button type="button" class="tab active" data-view="bars">堆叠图</button>
      <button type="button" class="tab" data-view="table">分布表</button>
      <button type="button" class="tab" data-view="cross">交叉情况</button>
      <button type="button" class="tab" data-view="curr">课标/综合</button>
    </div>
  </div>
  <p class="hint">白区=把握很稳；深灰/中灰/浅灰=越靠白越稳、越靠黑越要再看；黑区=建议人工核一眼。可切换比对视角。</p>
  <div class="legend">{legend}</div>
  <div class="view-pane active" data-view="bars">
    <div class="bars">{''.join(bar_rows)}</div>
  </div>
  <div class="view-pane" data-view="table">
    <table class="shade-table">
      <thead><tr><th>步骤</th>{ths}</tr></thead>
      <tbody>{''.join(table_rows)}</tbody>
    </table>
  </div>
  <div class="view-pane" data-view="cross">{cross_html}</div>
  <div class="view-pane" data-view="curr">{curr_html}</div>
</section>'''


def _page_conf_chips(meta: Dict[str, Any]) -> str:
    loc = {k: 0 for k in SHADE_ORDER}
    und = {k: 0 for k in SHADE_ORDER}
    gra = {k: 0 for k in SHADE_ORDER}
    for u in meta.get('units') or []:
        loc[u['layout_shade']] = loc.get(u['layout_shade'], 0) + 1
        und[u['understanding_shade']] = und.get(u['understanding_shade'], 0) + 1
        gra[u['grading_shade']] = gra.get(u['grading_shade'], 0) + 1

    def line(title: str, counts: Dict[str, int]) -> str:
        chips = ''.join(
            _shade_dot_html(k, f'{SHADE_DISPLAY[k]} {n}')
            for k, n in ((kk, int(counts.get(kk) or 0)) for kk in SHADE_ORDER)
            if n
        )
        empty = '<span class="muted">暂无</span>'
        return (
            f'<div class="conf-line"><span class="conf-k">{title}</span>'
            f'{chips or empty}</div>'
        )

    return (
        f'<div class="conf-block">'
        f'{line("版面", loc)}{line("理解", und)}{line("批改", gra)}'
        f'</div>'
    )



def _material_visual_html(
    report: Dict[str, Any],
    ontology: Dict[str, Any],
    feedback_context: Dict[str, Any],
    *,
    filename: str = '',
    material_type: str = 'homework',
) -> str:
    """材料与学情：三组配色（画像/枢纽 · 看到说明 · 下一步筛点）。"""
    from .explanation_layers import (
        material_portrait_label,
        parse_layers,
        has_layer_markers,
        SEE,
        MEAN,
        NEXT,
        _fallback_layers,
    )

    portrait = material_portrait_label(feedback_context, filename).replace('【材料画像】', '')
    level = str(feedback_context.get('education_level_name') or '').strip()
    grade = str(feedback_context.get('grade_label') or '').strip()
    subject_name = str(feedback_context.get('subject_name') or '').strip()
    kind = str(
        feedback_context.get('material_name')
        or _MATERIAL_CN.get(material_type, '')
        or ''
    ).strip()
    bits = [x for x in (level, grade, subject_name, kind) if x]
    meta_line = ' · '.join(bits) if bits else (portrait or '材料未标明')

    extra_meta = []
    for key, label in (
        ('term', '学期'),
        ('textbook', '教材'),
        ('school_system', '学制'),
    ):
        val = str(feedback_context.get(key) or '').strip()
        if val and val not in ('unknown', '未知', 'None'):
            extra_meta.append(f'<div class="mat-line"><strong>{_esc(label)}</strong> {_esc(val)}</div>')

    narrative = str((ontology or {}).get('evolution_narrative') or '').strip()
    diagnosis = ((report or {}).get('diagnosis') or {})
    summary = str(diagnosis.get('summary') or '').strip()
    overview = (report or {}).get('open_material_overview') or {}
    layered_src = narrative or summary
    layers = parse_layers(layered_src) if has_layer_markers(layered_src) else {}
    if not (layers.get(SEE) or layers.get(MEAN) or layers.get(NEXT)):
        layers = _fallback_layers(report, ontology)
    hub = ''
    if narrative:
        hub = re.split(r'\n{2,}|【看到了什么】', narrative, maxsplit=1)[0].strip()
        hub = re.sub(r'^枢纽判断[：:]\s*', '', hub)
    if not hub:
        hub = _clip_keep_lines(overview.get('content_review') or diagnosis.get('cognitive_stage') or '', 120)

    g1 = [
        f'<div class="mat-line"><strong>学段 / 年级 / 学科 / 品类</strong> {_esc(meta_line)}</div>',
        *extra_meta,
    ]
    if hub:
        g1.append(
            f'<div class="mat-line"><strong>主体理解（枢纽）</strong> '
            f'{_esc(_clip_keep_lines(hub, 420))}</div>'
        )

    g2 = []
    if layers.get(SEE):
        g2.append(
            f'<div class="mat-line"><strong>看到</strong> '
            f'{_esc(_clip_keep_lines(layers[SEE], 900))}</div>'
        )
    if layers.get(MEAN):
        g2.append(
            f'<div class="mat-line"><strong>说明</strong> '
            f'{_esc(_clip_keep_lines(layers[MEAN], 700))}</div>'
        )
    if isinstance(overview, dict):
        layout = _clip_keep_lines(overview.get('subject_and_layout'), 420)
        if layout and layout not in (layers.get(SEE) or ''):
            g2.append(f'<div class="mat-line"><strong>材料事实线</strong> {_esc(layout)}</div>')

    g3 = []
    if layers.get(NEXT):
        g3.append(
            f'<div class="mat-line"><strong>下一步</strong> '
            f'{_esc(_clip_keep_lines(layers[NEXT], 360))}</div>'
        )
    strengths = diagnosis.get('strengths') or []
    problems = diagnosis.get('main_problems') or []
    if isinstance(strengths, list) and strengths:
        g3.append(
            f'<div class="mat-line"><strong>已看见的稳点</strong> '
            f'{_esc(_clip_keep_lines("；".join(str(x) for x in strengths[:3]), 360))}</div>'
        )
    if isinstance(problems, list) and problems:
        g3.append(
            f'<div class="mat-line"><strong>需盯的筛点</strong> '
            f'{_esc(_clip_keep_lines("；".join(str(x) for x in problems[:3]), 360))}</div>'
        )

    if not (g1 or g2 or g3):
        return ''

    blocks = []
    if g1:
        blocks.append(f'<div class="mat-group mat-g1">{"".join(g1)}</div>')
    if g2:
        blocks.append(f'<div class="mat-group mat-g2">{"".join(g2)}</div>')
    if g3:
        blocks.append(f'<div class="mat-group mat-g3">{"".join(g3)}</div>')
    return (
        f'<section class="panel panel-soft" id="sec-material">'
        f'<div class="panel-kicker">材料画像与学情</div>'
        f'<h2>材料与学情理解</h2>'
        f'{"".join(blocks)}</section>'
    )


def _hub_visual_html(
    report: Dict[str, Any],
    ontology: Dict[str, Any],
    subject: str,
    *,
    limit: int = 8,
    material_type: str = 'homework',
) -> str:
    """整篇枢纽：三区配色与批改独立界面一致（红/橙黄/绿），位置可点跳。"""
    from .explanation_layers import format_layers, parse_layers, SEE, MEAN, NEXT

    items = []
    zones = (ontology or {}).get('zones') or {}
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        style = _HUB_ZONE_STYLE.get(bucket) or _HUB_ZONE_STYLE['zpd']
        for entry in zones.get(bucket) or []:
            if not isinstance(entry, dict):
                continue
            title = _hub_title(subject, entry)
            if not title:
                continue
            qids = entry.get('evidence') or entry.get('evidence_question_ids') or []
            if not isinstance(qids, list):
                qids = []
            rationale = str(entry.get('rationale') or entry.get('comment') or '').strip()
            nxt = str(entry.get('suggested_next_step') or '').strip()
            if not rationale and not nxt and not qids:
                continue
            see_text = '、'.join(
                _human_evidence(x, material_type=material_type) for x in qids[:2]
            ) or title
            combined = format_layers(see_text, rationale, nxt)
            layers = parse_layers(combined)
            loc_html = _loc_chips_from_evidence(
                qids, fold_after=6, material_type=material_type
            )
            body = [
                f'<div class="hub-row hub-see"><span class="hub-k">看到</span>'
                f'<span class="hub-v">{loc_html}</span></div>'
            ]
            if layers.get(MEAN) or rationale:
                body.append(
                    f'<div class="hub-row hub-mean"><span class="hub-k">说明</span>'
                    f'<span class="hub-v">{_esc(_clip_keep_lines(layers.get(MEAN) or rationale, 420))}</span></div>'
                )
            if layers.get(NEXT) or nxt:
                body.append(
                    f'<div class="hub-row hub-next"><span class="hub-k">下一步</span>'
                    f'<span class="hub-v">{_esc(_clip_keep_lines(layers.get(NEXT) or nxt, 240))}</span></div>'
                )
            items.append(
                f'<article class="hub-card" style="--hub-border:{style["border"]};'
                f'--hub-bg:{style["bg"]};--hub-ink:{style["ink"]}">'
                f'<h3><span class="hub-zone">{_esc(_ZONE_CN.get(bucket, bucket))}</span>'
                f'<span class="hub-title">{_esc(title)}</span></h3>'
                f'{"".join(body)}</article>'
            )
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    if not items:
        return ''
    return (
        f'<section class="panel panel-hub" id="sec-hub">'
        f'<div class="panel-kicker">认知三区枢纽</div>'
        f'<h2>整篇枢纽</h2>'
        f'<div class="hub-grid">{"".join(items)}</div></section>'
    )


def render_excerpt_html(payload: Dict[str, Any]) -> str:
    subject = payload.get('subject') or 'chinese'
    filename = _esc(payload.get('filename') or '批改材料')
    material_type = str(payload.get('material_type') or 'homework')
    material_cn = _MATERIAL_CN.get(material_type, '材料')
    units = payload.get('units') or []
    pages = payload.get('pages') or []
    report = payload.get('report') or {}
    ontology = payload.get('ontology') or {}
    ctx = payload.get('feedback_context') or {}
    overview_md = _build_rich_overview(units, subject, material_type=material_type)
    uv = None
    if isinstance(report, dict):
        uv = report.get('user_verification')
    if not (isinstance(uv, dict) and uv.get('items')) and isinstance(ontology, dict):
        try:
            from .wgb_trust import build_user_verification_block, zones_for_verification
            uv = build_user_verification_block(
                ontology.get('wgb_trust'),
                zones_for_verification(ontology),
            )
        except Exception:
            uv = None
    overview_html = _overview_visual_html(
        units, overview_md,
        material_type=material_type,
        user_verification=uv if isinstance(uv, dict) else None,
    )
    material_html = _material_visual_html(
        report, ontology, ctx,
        filename=str(payload.get('filename') or ''),
        material_type=material_type,
    )
    hub_html = _hub_visual_html(
        report, ontology, subject,
        material_type=material_type,
    )
    # 侧栏链接仍依赖是否有内容
    material_md = material_html
    hub_md = hub_html

    page_sections = []
    for meta in pages:
        qs_html = []
        for u in meta.get('units') or []:
            und_bits = []
            if u.get('student'):
                und_bits.append(f'学生作答「{u["student"]}」')
            if u.get('understanding'):
                und_bits.append(str(u['understanding']))
            und_text = '；'.join(und_bits) or '已完成识别与题意理解'
            grade_bits = []
            if u.get('correct'):
                grade_bits.append(f'参考「{u["correct"]}」')
            if u.get('zone'):
                grade_bits.append(f'学习分区·{u["zone"]}')
            grade_text = '；'.join(grade_bits)
            stem_fallback = '条目内容已切出' if (u.get('unit_word') == '条目') else '题框已切出'
            qs_html.append(
                f'<article class="q">'
                f'<div class="q-head">'
                f'<h4>{_esc(_unit_heading(u))}</h4>'
                f'{_verdict_badge_html(u.get("verdict") or "")}'
                f'</div>'
                f'<div class="step">'
                f'<div class="step-head">{_shade_dot_html(u.get("layout_shade") or "gray_mid", "版面·" + (u.get("layout_label") or ""))}'
                f'<span class="step-name">无损版面</span></div>'
                f'<p>{_esc(u.get("stem") or stem_fallback)}</p></div>'
                f'<div class="step">'
                f'<div class="step-head">{_shade_dot_html(u.get("understanding_shade") or "gray_mid", "理解·" + (u.get("understanding_label") or ""))}'
                f'<span class="step-name">无损理解</span></div>'
                f'<p>{_esc(und_text)}</p></div>'
                f'<div class="step">'
                f'<div class="step-head">{_shade_dot_html(u.get("grading_shade") or "gray_mid", "批改·" + (u.get("grading_label") or ""))}'
                f'<span class="step-name">三区批改</span>'
                f'{_verdict_badge_html(u.get("verdict") or "")}</div>'
                + (f'<p>{_esc(grade_text)}</p>' if grade_text else '')
                + _comment_html(u.get('comment') or '')
                + '</div></article>'
            )
        page_sections.append(
            f'<section class="page-block" id="page-{meta["page"]}" data-page="{meta["page"]}">'
            f'<h3>第 {_esc(meta["page"])} 页'
            + (f' · {_esc(meta["header"])}' if meta.get('header') else '')
            + '</h3>'
            + _page_conf_chips(meta)
            + (
                (
                    f'<div class="page-sum"><strong>页评·理解</strong>'
                    + _comment_html(meta['summary']).replace(
                        '<div class="layer-title">批语</div>',
                        '',
                    )
                    + '</div>'
                )
                if meta.get('summary') and '【看到了什么】' in str(meta.get('summary') or '')
                else (
                    f'<p class="page-sum"><strong>页评·理解：</strong>{_esc(meta["summary"])}</p>'
                    if meta.get('summary') else ''
                )
            )
            + ''.join(qs_html)
            + '</section>'
        )

    side_links = ['<a href="#sec-overview" data-goto="0">总览</a>']
    if material_md:
        side_links.append('<a href="#sec-material" data-goto="0">材料理解</a>')
    if hub_md:
        side_links.append('<a href="#sec-hub" data-goto="0">整篇枢纽</a>')
    if page_sections:
        side_links.append('<a href="#" data-goto="1">逐页留存</a>')

    html_pages = [
        f'<div class="card-page active" data-i="0">'
        f'<header class="hero">'
        f'<p class="eyebrow">{_esc(material_cn)}批改留存</p>'
        f'<h1>批改·解释精要</h1>'
        f'<p class="sub">{filename}</p></header>'
        f'{overview_html}{material_html}{hub_html}</div>'
    ]
    group = 2
    for i in range(0, len(page_sections), group):
        idx = len(html_pages)
        chunk = page_sections[i:i + group]
        html_pages.append(
            f'<div class="card-page" data-i="{idx}">'
            f'<h2>逐页留存</h2>{"".join(chunk)}</div>'
        )
    total = len(html_pages)

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>批改·解释精要</title>
<style>
:root {{
  --bg:#f3efe6; --card:#fffcf7; --ink:#1c2430; --muted:#5c6573;
  --line:#e2dccf; --accent:#2c6b5a;
  --ok:#2f7d4a; --bad:#b4453b; --half:#c27a22; --empty:#7a7f88; --wait:#5b6472;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  color:var(--ink); background:
    radial-gradient(1200px 500px at 10% -10%, #e7efe8 0%, transparent 55%),
    radial-gradient(900px 420px at 100% 0%, #efe6d6 0%, transparent 50%),
    linear-gradient(180deg,#efe8db,#f6f3ec);
  line-height:1.7;
}}
.shell {{ display:grid; grid-template-columns:200px minmax(0,1fr); gap:0; min-height:100vh; }}
.sidenav {{
  position:sticky; top:0; align-self:start; height:100vh; padding:22px 14px;
  border-right:1px solid var(--line); background:rgba(255,252,247,.88);
}}
.sidenav .brand {{ font-size:13px; color:var(--accent); letter-spacing:.06em; margin:0 0 14px; }}
.sidenav a {{
  display:block; text-decoration:none; color:var(--ink); font-size:14px;
  padding:8px 10px; border-radius:6px; margin-bottom:4px;
}}
.sidenav a:hover {{ background:#ebe4d6; }}
.wrap {{ max-width:980px; margin:0 auto; padding:28px 22px 96px; }}
.hero {{ margin-bottom:18px; }}
.eyebrow {{ color:var(--accent); letter-spacing:.08em; font-size:13px; margin:0 0 6px; }}
h1 {{ font-size:30px; margin:0 0 8px; letter-spacing:.02em; }}
.sub {{ color:var(--muted); margin:0; }}
h2 {{ font-size:20px; margin:0 0 12px; }}
h3 {{ font-size:17px; margin:0 0 12px; }}
h4 {{ font-size:15px; margin:0; }}
p {{ margin:8px 0; }}
.panel {{
  background:rgba(255,252,247,.9); border:1px solid var(--line); border-radius:12px;
  padding:16px 18px 18px; margin:0 0 16px;
}}
.panel-head {{ display:flex; flex-wrap:wrap; gap:10px; justify-content:space-between; align-items:center; }}
.hint {{ color:var(--muted); font-size:13px; margin:8px 0 12px; }}
.view-tabs {{ display:flex; flex-wrap:wrap; gap:6px; }}
.view-tabs .tab {{
  appearance:none; border:1px solid var(--line); background:#fff; color:var(--ink);
  border-radius:6px; padding:6px 12px; cursor:pointer; font-size:13px;
}}
.view-tabs .tab.active {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.view-pane {{ display:none; margin-top:12px; }}
.view-pane.active {{ display:block; }}
.legend {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; }}
.bars {{ display:flex; flex-direction:column; gap:12px; }}
.bar-row {{ display:grid; grid-template-columns:88px 1fr; gap:10px; align-items:center; }}
.bar-label {{ font-size:13px; color:var(--muted); }}
.stack {{ display:flex; height:28px; border-radius:6px; overflow:hidden; border:1px solid var(--line); background:#fff; }}
.stack .seg {{ display:flex; align-items:center; justify-content:center; font-size:11px; min-width:0; padding:0 4px; white-space:nowrap; overflow:hidden; }}
.shade-table {{ width:100%; border-collapse:collapse; }}
.shade-table th,.shade-table td {{ border-bottom:1px solid var(--line); padding:8px 10px; text-align:center; font-size:13px; }}
.shade-table th:first-child,.shade-table td:first-child {{ text-align:left; }}
.shade-chip {{
  display:inline-flex; align-items:center; gap:6px; font-size:12px;
  padding:2px 8px 2px 4px; border-radius:4px; border:1px solid var(--bd);
  background:#fff; color:#1c2430 !important; margin:2px 4px 2px 0;
}}
.shade-dot {{
  width:12px; height:12px; border-radius:50%; background:var(--dot);
  border:1px solid var(--bd); display:inline-block; flex:0 0 auto;
}}
.pat-bars {{ display:flex; flex-direction:column; gap:8px; margin:10px 0 16px; }}
.pat-row {{ display:grid; grid-template-columns:150px 1fr 88px; gap:8px; align-items:center; }}
.pat-label {{ font-size:12px; color:var(--muted); }}
.pat-track {{ height:10px; background:#efe8db; border-radius:4px; overflow:hidden; }}
.pat-fill {{ display:block; height:100%; border-radius:4px; }}
.pat-num {{ font-size:12px; text-align:right; }}
.stat-grid,.curr-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; }}
.stat-card,.curr-card,.composite-card {{
  background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 14px;
  border-left:4px solid var(--accent, var(--accent));
}}
.stat-card header {{ display:flex; justify-content:space-between; gap:8px; align-items:baseline; }}
.stat-title {{ font-weight:600; font-size:14px; }}
.stat-count {{ color:var(--accent); font-size:13px; white-space:nowrap; }}
.stat-hint {{ color:var(--muted); font-size:12px; margin:4px 0 8px; }}
.stat-card .meta {{ font-size:12px; margin:4px 0; }}
.curr-row {{ display:grid; grid-template-columns:1fr 90px 64px; gap:6px; align-items:center; margin:6px 0; font-size:12px; }}
.curr-track {{ height:8px; background:#efe8db; border-radius:4px; overflow:hidden; }}
.curr-track i {{ display:block; height:100%; background:#2c6b5a; }}
.curr-n {{ text-align:right; color:var(--muted); }}
.composite-card {{ margin-top:12px; background:#f3faf6; border-left-color:#2c6b5a; }}
.panel-soft {{ background:linear-gradient(180deg,#f7fbf8,#fffcf7); }}
.panel-hub {{ background:linear-gradient(180deg,#fbf8f2,#fffcf7); }}
.panel-kicker {{
  display:inline-block; font-size:12px; color:#fff; background:var(--accent);
  border-radius:4px; padding:2px 8px; margin-bottom:10px;
}}
.panel-hub h3 {{
  display:flex; align-items:center; gap:8px; font-size:15px;
  padding:8px 10px; border-radius:8px; background:#f4f1ea;
}}
.more {{ margin-top:12px; font-size:13px; color:var(--muted); }}
.more summary {{ cursor:pointer; color:var(--accent); }}
.verdict {{
  display:inline-flex; align-items:center; gap:4px; font-size:12px;
  padding:2px 8px; border-radius:4px; margin:0 6px 0 0; border:1px solid var(--line);
}}
.verdict b {{ font-weight:700; }}
.verdict-ok {{ color:var(--ok); background:#e8f5ec; }}
.verdict-bad {{ color:var(--bad); background:#f8ecea; }}
.verdict-half {{ color:var(--half); background:#f8efdf; }}
.verdict-empty,.verdict-wait {{ color:var(--empty); background:#f1f1ef; }}
.page-block {{
  background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:18px; margin:16px 0;
}}
.conf-block {{ display:flex; flex-direction:column; gap:6px; margin:0 0 12px; }}
.conf-line {{ display:flex; flex-wrap:wrap; align-items:center; gap:4px; }}
.conf-k {{ width:42px; color:var(--muted); font-size:12px; }}
.page-sum {{ margin:8px 0 14px; }}
.q {{ border-top:1px dashed var(--line); padding:16px 0 8px; margin-top:8px; }}
.q-head {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:10px; }}
.step {{ margin:12px 0 16px; padding:10px 12px; background:#faf7f1; border-radius:8px; border:1px solid #efe8db; }}
.step-head {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:6px; }}
.step-name {{ font-size:12px; color:var(--muted); }}
.comment-layers {{ margin-top:10px; border-left:3px solid var(--accent); padding-left:10px; }}
.layer-title {{ font-size:12px; color:var(--muted); margin-bottom:4px; }}
.layer {{ margin:6px 0; }}
.layer-k {{
  display:inline-block; font-size:12px; color:#fff; background:var(--accent);
  border-radius:4px; padding:1px 6px; margin-bottom:4px;
}}
.comment-plain {{ margin-top:8px; }}
.muted {{ color:var(--muted); font-size:12px; }}
ul {{ padding-left:1.15em; }}
li {{ margin:7px 0; }}
table {{ width:100%; border-collapse:collapse; margin:8px 0 12px; }}
th,td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; font-size:13px; }}
.card-page {{ display:none; }}
.card-page.active {{ display:block; animation:fade .22s ease; }}
@keyframes fade {{ from {{ opacity:.45; transform:translateY(4px); }} to {{ opacity:1; transform:none; }} }}
.pager {{
  position:fixed; left:200px; right:0; bottom:0; display:flex; justify-content:center; gap:12px;
  padding:12px; background:rgba(246,243,236,.94); border-top:1px solid var(--line);
}}
.pager button {{
  appearance:none; border:1px solid var(--line); background:#fff; color:var(--ink);
  border-radius:6px; padding:8px 16px; cursor:pointer; font-size:14px;
}}
.pager button:disabled {{ opacity:.4; cursor:not-allowed; }}
.pager .idx {{ color:var(--muted); align-self:center; font-size:13px; min-width:72px; text-align:center; }}
@media (max-width:860px) {{
  .shell {{ grid-template-columns:1fr; }}
  .sidenav {{ position:relative; height:auto; display:flex; flex-wrap:wrap; gap:4px; border-right:0; border-bottom:1px solid var(--line); }}
  .sidenav a {{ margin:0; }}
  .pager {{ left:0; }}
  .bar-row {{ grid-template-columns:1fr; }}
}}

.loc-list, .loc-short, .loc-all {{
  display:inline-flex; flex-wrap:wrap; align-items:center; gap:6px; vertical-align:middle;
}}
/* 必须盖过上面的 display，否则 [hidden] 失效 → 短列表+全列表叠在一起像「重复」 */
.loc-short[hidden], .loc-all[hidden] {{ display:none !important; }}
.loc-wrap {{ display:inline-flex; flex-wrap:wrap; align-items:center; gap:6px; }}
.loc-jump {{
  display:inline-flex; align-items:center; padding:3px 10px; margin:0;
  border-radius:6px; background:#e8eef5; color:#3b6ea5; text-decoration:none !important;
  font-size:12px; line-height:1.4; border:1px solid #d0dbe8; cursor:pointer;
  white-space:nowrap;
}}
.loc-jump:hover {{ background:#dce7f4; color:#2a5685; border-color:#b8cce0; }}
.loc-toggle {{
  appearance:none; display:inline-flex; align-items:center; gap:4px;
  margin:0; padding:3px 10px; border-radius:6px; cursor:pointer; font-size:12px;
  background:#f3f4f6; color:#5c6573; border:1px dashed #b8c0cc; text-decoration:none;
  white-space:nowrap;
}}
.loc-toggle:hover {{ background:#e8eaee; color:#3d4654; border-color:#9aa3b0; }}
.cross-subtabs {{ display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 10px; }}
.cross-subtab {{
  appearance:none; border:1px solid var(--line); background:#fff; color:var(--ink);
  border-radius:6px; padding:6px 12px; cursor:pointer; font-size:13px;
}}
.cross-subtab.active {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.cross-pane {{ display:none; margin-top:4px; }}
.cross-pane.active {{ display:block; }}
.cross-block {{
  background:#fff; border:1px solid var(--line); border-radius:10px;
  padding:12px 14px; margin:0 0 10px;
}}
.cross-block-head {{
  display:flex; justify-content:space-between; align-items:baseline; gap:8px; margin-bottom:8px;
}}
.cross-block-title {{ font-weight:600; font-size:14px; }}
.cross-block-n {{ color:var(--muted); font-size:12px; }}
.mat-group {{
  border-radius:10px; padding:12px 14px; margin:0 0 10px; border:1px solid var(--line);
}}
.mat-g1 {{ background:#eef5f7; border-color:#c5d8de; }}
.mat-g1 strong {{ color:#2a5f6e; }}
.mat-g2 {{ background:#f7f1e6; border-color:#e2d3b8; }}
.mat-g2 strong {{ color:#7a5a28; }}
.mat-g3 {{ background:#eef7f1; border-color:#c3dbcb; }}
.mat-g3 strong {{ color:#2b6b45; }}
.mat-line {{ margin:6px 0; font-size:13.5px; line-height:1.7; }}
.hub-grid {{ display:flex; flex-direction:column; gap:10px; }}
.hub-card {{
  background:var(--hub-bg, #f4f1ea); border:1px solid var(--line);
  border-left:4px solid var(--hub-border, #8a8a8a); border-radius:10px; padding:12px 14px;
}}
.hub-card h3 {{
  display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:0 0 8px;
  padding:0; background:transparent; font-size:15px;
}}
.hub-zone {{
  display:inline-block; font-size:12px; font-weight:700; color:#fff;
  background:var(--hub-border, #8a8a8a); border-radius:4px; padding:2px 8px;
}}
.hub-title {{ color:var(--hub-ink, var(--ink)); font-weight:600; }}
.hub-row {{ display:grid; grid-template-columns:52px 1fr; gap:8px; margin:6px 0; font-size:13px; }}
.hub-k {{ font-weight:600; }}
.hub-see .hub-k, .hub-mean .hub-k {{ color:#5a6472; }}
.hub-next .hub-k {{ color:#2b6b45; }}
.hub-v {{ min-width:0; }}
.uv-banner {{
  margin: 14px 0 10px; padding: 12px 14px;
  border: 1px solid #e8b4b0; border-left: 4px solid #c45c54; border-radius: 8px;
  background: linear-gradient(180deg, #fff6f5 0%, #fffaf8 100%); color: #5a2e2a;
}}
.uv-head {{ display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:8px; margin-bottom:6px; }}
.uv-head strong {{ font-size:14px; }}
.uv-counts {{ display:flex; gap:8px; font-size:12px; }}
.uv-counts em {{ font-style:normal; padding:1px 8px; border-radius:999px; background:#f8e4e2; color:#a33d36; }}
.uv-counts .uv-c-i {{ background:#f8e4e2; color:#a33d36; }}
.uv-counts .uv-c-ii {{ background:#fff4e5; color:#8a5a14; }}
.uv-counts .uv-c-iii {{ background:#f4f1ea; color:#5c5346; }}
.uv-tier {{ margin: 0 0 8px; }}
.uv-tier-name {{ font-size: 12px; font-weight: 700; margin: 2px 0 4px; color: #5a2e2a; }}
.uv-tier-name em {{ font-style: normal; font-weight: 600; margin-left: 4px; }}
.uv-chip.is-i {{ background:#fdecea; border-color:#ecc0bc; color:#a5342c; }}
.uv-chip.is-ii {{ background:#fff4e5; border-color:#edd2a8; color:#8a5a14; }}
.uv-chip.is-iii {{ background:#f4f1ea; border-color:#ddd4c4; color:#5c5346; }}
.uv-summary {{ margin:0 0 10px; font-size:13px; line-height:1.55; color:#6b3f3a; }}
.uv-list {{ display:flex; flex-direction:column; gap:8px; }}
.uv-row {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; }}
.uv-chip {{
  appearance:none; border:1px solid #d0dbe8; background:#e8eef5; color:#3b6ea5;
  border-radius:6px; padding:3px 10px; font-size:12px; text-decoration:none; line-height:1.4;
}}
.uv-chip.is-critical {{ background:#fdecea; border-color:#ecc0bc; color:#a5342c; }}
.uv-chip.is-careful {{ background:#fff4e5; border-color:#edd2a8; color:#8a5a14; }}
.uv-verify-btn {{
  appearance:none; border:1px solid #c45c54; background:#fff; color:#a5342c;
  border-radius:6px; padding:3px 10px; font-size:12px; cursor:pointer;
}}
.uv-verify-btn:hover {{ background:#fff1ef; }}
.uv-row.is-done .uv-verify-btn {{ display:none; }}
.uv-done-mark {{ font-size:12px; color:#2f6b4a; font-weight:600; }}
.uv-row.is-done .uv-done-mark {{ display:inline; }}
.uv-more {{
  appearance:none; align-self:flex-start; border:1px dashed #c4a8a4; background:#fff;
  color:#7a4a44; border-radius:6px; padding:3px 10px; font-size:12px; cursor:pointer;
}}
.uv-actions {{
  margin-top:12px; padding-top:10px; border-top:1px dashed #e0c4bf;
  display:flex; flex-wrap:wrap; align-items:center; gap:10px;
}}
.uv-iterate-btn {{
  appearance:none; border:none; background:#c45c54; color:#fff;
  border-radius:8px; padding:8px 14px; font-size:13px; font-weight:600; cursor:pointer;
}}
.uv-iterate-btn:disabled {{ opacity:.55; cursor:not-allowed; }}
.uv-iterate-hint {{ font-size:12px; color:#7a4a44; line-height:1.45; max-width:36em; }}
.uv-modal-mask {{
  position:fixed; inset:0; background:rgba(20,24,32,.45); z-index:40;
  display:flex; align-items:center; justify-content:center; padding:16px;
}}
.uv-modal {{
  width:min(520px, 96vw); background:#fff; border-radius:12px; padding:16px 16px 14px;
  box-shadow:0 12px 40px rgba(0,0,0,.18); color:#243447;
  max-height:90vh; overflow:auto;
}}
.uv-modal h3 {{ margin:0 0 8px; font-size:16px; }}
.uv-modal .uv-qid {{ font-size:12px; color:#6b7c8f; margin-bottom:10px; }}
.uv-verdict {{ display:flex; gap:8px; margin-bottom:12px; }}
.uv-verdict label {{
  flex:1; border:1px solid #d8e0e8; border-radius:8px; padding:8px 10px; cursor:pointer; font-size:13px;
}}
.uv-verdict input {{ margin-right:6px; }}
.uv-steps {{ display:none; flex-direction:column; gap:8px; margin-bottom:12px; }}
.uv-steps.show {{ display:flex; }}
.uv-step {{ border:1px solid #e8eef4; border-radius:8px; padding:8px 10px; background:#f7f9fb; }}
.uv-step label {{ display:flex; align-items:center; gap:6px; font-size:13px; font-weight:600; }}
.uv-step textarea {{
  width:100%; margin-top:6px; min-height:52px; border:1px solid #d8e0e8; border-radius:6px;
  padding:6px 8px; font-size:12px; resize:vertical; font-family:inherit;
}}
.uv-chips {{
  display:flex; flex-wrap:wrap; gap:6px; margin-top:8px;
}}
.uv-chip {{
  appearance:none; border:1px solid #c9d5e4; background:#fff; color:#3a4a63;
  border-radius:10px; padding:5px 10px; font-size:11px; line-height:1.4;
  cursor:pointer; text-align:left; max-width:100%;
  white-space:normal; word-break:break-word; overflow-wrap:anywhere;
}}
.uv-chip:hover {{ border-color:#2d6fae; color:#2d6fae; background:#f0f6fc; }}
.uv-chip.is-active {{ border-color:#2d6fae; background:#e8f1fb; color:#1f5f9a; }}
.uv-chips-hint {{ width:100%; font-size:11px; color:#8a97ab; margin-top:2px; }}
.uv-chip-choice {{
  display:none; margin-top:8px; padding:8px 10px; border:1px solid #d7e3f2;
  border-radius:8px; background:#f3f7fc; font-size:12px; color:#3a4a63;
  align-items:center; flex-wrap:wrap; gap:8px;
}}
.uv-chip-choice.is-show {{ display:flex; }}
.uv-chip-choice span {{ flex:1 1 auto; min-width:140px; line-height:1.4; }}
.uv-chip-choice button {{
  appearance:none; border:1px solid #c9d5e4; background:#fff; border-radius:6px;
  padding:4px 10px; font-size:12px; cursor:pointer; color:#3a4a63;
}}
.uv-chip-choice button.primary {{ background:#2d6fae; border-color:#2d6fae; color:#fff; }}
.uv-modal-actions {{ display:flex; justify-content:flex-end; gap:8px; }}
.uv-modal-actions button {{
  appearance:none; border:1px solid #d8e0e8; background:#fff; border-radius:8px;
  padding:7px 12px; font-size:13px; cursor:pointer;
}}
.uv-modal-actions .primary {{ background:#c45c54; border-color:#c45c54; color:#fff; }}
</style>
</head>
<body data-analysis-id="{_esc(payload.get("analysis_id") or "")}" data-run-id="{_esc(payload.get("run_id") or "")}">
<script type="application/json" id="uv-suggest-data">{_esc_json(payload.get("verify_suggestions") or {})}</script>
<div class="shell">
<aside class="sidenav">
  <p class="brand">解释精要</p>
  {''.join(side_links)}
</aside>
<main class="wrap">
{''.join(html_pages)}
</main>
</div>
<div class="pager">
  <button id="prev" type="button">上一页</button>
  <span class="idx"><span id="cur">1</span> / {total}</span>
  <button id="next" type="button">下一页</button>
</div>
<div id="uv-modal-root" hidden></div>
<script>
(function(){{
  var pages=[].slice.call(document.querySelectorAll('.card-page'));
  var i=0;
  function show(n){{
    i=Math.max(0, Math.min(pages.length-1, n));
    pages.forEach(function(p,idx){{ p.classList.toggle('active', idx===i); }});
    document.getElementById('cur').textContent=String(i+1);
    document.getElementById('prev').disabled=i===0;
    document.getElementById('next').disabled=i===pages.length-1;
    window.scrollTo({{top:0,behavior:'smooth'}});
  }}
  document.getElementById('prev').onclick=function(){{ show(i-1); }};
  document.getElementById('next').onclick=function(){{ show(i+1); }};
  document.querySelectorAll('.sidenav a[data-goto]').forEach(function(a){{
    a.addEventListener('click', function(e){{
      var g=parseInt(a.getAttribute('data-goto')||'0',10);
      show(g);
      var href=a.getAttribute('href')||'';
      if(href.charAt(0)==='#'){{
        e.preventDefault();
        setTimeout(function(){{
          var el=document.querySelector(href);
          if(el) el.scrollIntoView({{behavior:'smooth',block:'start'}});
        }}, 60);
      }}
    }});
  }});
  document.querySelectorAll('.overview-visual').forEach(function(box){{
    var tabs=box.querySelectorAll('.tab');
    var panes=box.querySelectorAll('.view-pane');
    tabs.forEach(function(tab){{
      tab.addEventListener('click', function(){{
        var v=tab.getAttribute('data-view');
        tabs.forEach(function(t){{ t.classList.toggle('active', t===tab); }});
        panes.forEach(function(p){{ p.classList.toggle('active', p.getAttribute('data-view')===v); }});
      }});
    }});
  }});

  document.querySelectorAll('.view-pane[data-view="cross"]').forEach(function(box){{
    var subs=box.querySelectorAll('.cross-subtab');
    var panes=box.querySelectorAll('.cross-pane');
    if(!subs.length) return;
    subs.forEach(function(tab){{
      tab.addEventListener('click', function(){{
        var v=tab.getAttribute('data-cross-view');
        subs.forEach(function(t){{ t.classList.toggle('active', t===tab); }});
        panes.forEach(function(p){{ p.classList.toggle('active', p.getAttribute('data-cross-view')===v); }});
      }});
    }});
  }});
  function postHomeworkJump(evidence){{
    var payload={{
      type:'nkcn-homework-jump',
      evidence: evidence,
      analysisId: (document.body && document.body.getAttribute('data-analysis-id')) || '',
      runId: (document.body && document.body.getAttribute('data-run-id')) || ''
    }};
    var targets=[];
    try {{ if(window.parent && window.parent!==window) targets.push(window.parent); }} catch(e1){{}}
    try {{ if(window.top && window.top!==window && targets.indexOf(window.top)<0) targets.push(window.top); }} catch(e2){{}}
    try {{ if(window.opener && targets.indexOf(window.opener)<0) targets.push(window.opener); }} catch(e3){{}}
    var sent=false;
    targets.forEach(function(w){{
      try {{ w.postMessage(payload, '*'); sent=true; }} catch(err){{}}
    }});
    return sent;
  }}
  document.addEventListener('click', function(e){{
    var t = e.target;
    if(!t) return;
    if(t.classList && t.classList.contains('loc-toggle')){{
      e.preventDefault();
      var wrap = t.closest('.loc-wrap');
      if(!wrap) return;
      var folded = wrap.getAttribute('data-folded') !== '0';
      var shortEl = wrap.querySelector('.loc-short');
      var allEl = wrap.querySelector('.loc-all');
      if(folded){{
        if(shortEl) shortEl.hidden = true;
        if(allEl) allEl.hidden = false;
        wrap.setAttribute('data-folded','0');
        t.setAttribute('aria-expanded','true');
        t.textContent = '收起';
      }} else {{
        if(shortEl) shortEl.hidden = false;
        if(allEl) allEl.hidden = true;
        wrap.setAttribute('data-folded','1');
        t.setAttribute('aria-expanded','false');
        var n = (allEl && allEl.querySelectorAll('.loc-jump').length) || 0;
        t.textContent = '展开全部 ' + n;
      }}
      return;
    }}
    var a = t.closest ? t.closest('a.loc-jump') : null;
    if(a){{
      e.preventDefault();
      var evidence = a.getAttribute('data-evidence') || '';
      if(!evidence) return;
      var ok = postHomeworkJump(evidence);
      if(!ok){{
        a.classList.add('loc-jump-flash');
        setTimeout(function(){{ a.classList.remove('loc-jump-flash'); }}, 600);
      }}
      return;
    }}
    if(t.classList && t.classList.contains('uv-more')){{
      e.preventDefault();
      var list = t.closest('.uv-list');
      if(!list) return;
      var folded = list.getAttribute('data-folded') !== '0';
      var shortEl = list.querySelector('.uv-short');
      var allEl = list.querySelector('.uv-all');
      if(folded){{
        if(shortEl) shortEl.hidden = true;
        if(allEl) allEl.hidden = false;
        list.setAttribute('data-folded','0');
        t.textContent = '收起';
      }} else {{
        if(shortEl) shortEl.hidden = false;
        if(allEl) allEl.hidden = true;
        list.setAttribute('data-folded','1');
        var n = (allEl && allEl.querySelectorAll('.uv-row').length) || 0;
        t.textContent = '展开全部 ' + n;
      }}
      return;
    }}
    var vbtn = t.closest ? t.closest('.uv-verify-btn') : null;
    if(vbtn){{
      e.preventDefault();
      openVerifyModal(vbtn.getAttribute('data-qid')||'', vbtn.getAttribute('data-label')||'');
      return;
    }}
    if(t.id === 'uv-iterate-btn' || (t.classList && t.classList.contains('uv-iterate-btn'))){{
      e.preventDefault();
      startVerifyIterate();
    }}
  }});

  function apiUsername(){{
    try {{ return new URLSearchParams(window.location.search).get('username') || ''; }} catch(e){{ return ''; }}
  }}
  function postToParents(payload){{
    var targets=[];
    try {{ if(window.parent && window.parent!==window) targets.push(window.parent); }} catch(e1){{}}
    try {{ if(window.top && window.top!==window && targets.indexOf(window.top)<0) targets.push(window.top); }} catch(e2){{}}
    try {{ if(window.opener && targets.indexOf(window.opener)<0) targets.push(window.opener); }} catch(e3){{}}
    targets.forEach(function(w){{ try {{ w.postMessage(payload, '*'); }} catch(err){{}} }});
  }}
  function markVerified(qid){{
    document.querySelectorAll('.uv-row[data-qid="'+qid+'"]').forEach(function(row){{
      row.classList.add('is-done');
      var mark = row.querySelector('.uv-done-mark');
      if(mark) mark.hidden = false;
    }});
  }}
  function closeVerifyAssist(){{
    postToParents({{ type:'nkcn-homework-verify-assist-close' }});
  }}
  function openVerifyAssist(qid){{
    if(!qid) return;
    postToParents({{
      type:'nkcn-homework-verify-assist',
      evidence: qid,
      analysisId: (document.body && document.body.getAttribute('data-analysis-id')) || '',
      analysis_id: (document.body && document.body.getAttribute('data-analysis-id')) || '',
      runId: (document.body && document.body.getAttribute('data-run-id')) || 'current',
      run_id: (document.body && document.body.getAttribute('data-run-id')) || 'current'
    }});
  }}
  function loadVerifySuggestions(){{
    try {{
      var el = document.getElementById('uv-suggest-data');
      if(!el) return {{}};
      var raw = (el.textContent || '').trim();
      if(!raw) return {{}};
      var data = JSON.parse(raw);
      return (data && typeof data === 'object') ? data : {{}};
    }} catch(e){{ return {{}}; }}
  }}
  function escHtml(s){{
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }}
  function chipsHtmlForRole(sug, role){{
    var list = (sug && Array.isArray(sug[role])) ? sug[role] : [];
    if(!list.length){{
      return '<div class="uv-chips"><span class="uv-chips-hint">暂无预置短句，可直接手写</span></div>';
    }}
    return '<div class="uv-chips" data-role="'+role+'">' + list.map(function(t){{
      return '<button type="button" class="uv-chip" data-text="'+escHtml(t)+'">'+escHtml(t)+'</button>';
    }}).join('') + '<div class="uv-chips-hint">点选填入下方说明；仍可手改</div></div>';
  }}
  function hideChipChoice(stepEl){{
    if(!stepEl) return;
    var bar = stepEl.querySelector('.uv-chip-choice');
    if(bar){{
      bar.classList.remove('is-show');
      bar.setAttribute('data-pending','');
    }}
  }}
  function applyChipText(stepEl, text, mode){{
    if(!stepEl || !text) return;
    var box = stepEl.querySelector('.uv-step-err');
    var ta = stepEl.querySelector('textarea');
    if(box) box.checked = true;
    if(!ta) return;
    var cur = (ta.value || '').trim();
    if(mode === 'append' && cur){{
      ta.value = cur + '；' + text;
    }} else {{
      ta.value = text;
    }}
  }}
  function applyChipToStep(stepEl, text, chipBtn){{
    if(!stepEl || !text) return;
    var box = stepEl.querySelector('.uv-step-err');
    var ta = stepEl.querySelector('textarea');
    if(box) box.checked = true;
    if(!ta) return;
    var cur = (ta.value || '').trim();
    if(chipBtn){{
      stepEl.querySelectorAll('.uv-chip').forEach(function(b){{ b.classList.remove('is-active'); }});
      chipBtn.classList.add('is-active');
    }}
    if(!cur){{
      ta.value = text;
      return;
    }}
    var bar = stepEl.querySelector('.uv-chip-choice');
    if(!bar){{
      // 兜底：无选择条时默认替换
      ta.value = text;
      return;
    }}
    // 已有内容：弹出「替换 / 追加 / 取消」，取消不改动文本框
    rootQueryAllChipChoicesHide(stepEl.parentNode);
    bar.setAttribute('data-pending', text);
    bar.classList.add('is-show');
  }}
  function rootQueryAllChipChoicesHide(stepsRoot){{
    if(!stepsRoot) return;
    stepsRoot.querySelectorAll('.uv-chip-choice').forEach(function(bar){{
      bar.classList.remove('is-show');
      bar.setAttribute('data-pending','');
    }});
  }}
  function openVerifyModal(qid, label){{
    var root = document.getElementById('uv-modal-root');
    if(!root || !qid) return;
    var allSug = loadVerifySuggestions();
    var sug = allSug[qid] || {{}};
    root.hidden = false;
    root.innerHTML =
      '<div class="uv-modal-mask"><div class="uv-modal" role="dialog">' +
      '<h3>提交核验结果</h3>' +
      '<div class="uv-qid">'+ (label || qid) +' · '+ qid +'</div>' +
      '<div class="uv-verdict">' +
      '<label><input type="radio" name="uv-v" value="correct" checked>原批改结果无误</label>' +
      '<label><input type="radio" name="uv-v" value="incorrect">原批改结果有误</label>' +
      '</div>' +
      '<div class="uv-steps" id="uv-steps">' +
      ['layout|无损版面','understanding|无损理解','grading|三区批改'].map(function(pair){{
        var p=pair.split('|');
        return '<div class="uv-step" data-role="'+p[0]+'">' +
          '<label><input type="checkbox" class="uv-step-err"> '+p[1]+' 有误</label>' +
          '<textarea placeholder="若有误：误认/误判在哪里…"></textarea>' +
          chipsHtmlForRole(sug, p[0]) +
          '<div class="uv-chip-choice" data-pending="">' +
          '<span>说明框已有内容，请选择：</span>' +
          '<button type="button" class="primary" data-act="replace">替换</button>' +
          '<button type="button" data-act="append">追加</button>' +
          '<button type="button" data-act="cancel">取消</button>' +
          '</div>' +
          '</div>';
      }}).join('') +
      '</div>' +
      '<div class="uv-modal-actions">' +
      '<button type="button" id="uv-cancel">取消</button>' +
      '<button type="button" class="primary" id="uv-save">保存核验</button>' +
      '</div></div></div>';
    // 提交弹窗逻辑不变；额外打开左侧可收起的逐页批改对照
    openVerifyAssist(qid);
    function syncSteps(){{
      var inc = root.querySelector('input[name="uv-v"][value="incorrect"]');
      var steps = root.querySelector('#uv-steps');
      if(steps) steps.classList.toggle('show', !!(inc && inc.checked));
      if(!(inc && inc.checked)) rootQueryAllChipChoicesHide(steps);
    }}
    root.querySelectorAll('input[name="uv-v"]').forEach(function(r){{ r.addEventListener('change', syncSteps); }});
    syncSteps();
    root.querySelectorAll('.uv-chip').forEach(function(btn){{
      btn.addEventListener('click', function(){{
        var step = btn.closest('.uv-step');
        var text = btn.getAttribute('data-text') || btn.textContent || '';
        applyChipToStep(step, text, btn);
      }});
    }});
    root.querySelectorAll('.uv-chip-choice').forEach(function(bar){{
      bar.addEventListener('click', function(ev){{
        var actBtn = ev.target && ev.target.closest ? ev.target.closest('button[data-act]') : null;
        if(!actBtn) return;
        var act = actBtn.getAttribute('data-act') || '';
        var step = bar.closest('.uv-step');
        var pending = bar.getAttribute('data-pending') || '';
        if(act === 'replace'){{
          applyChipText(step, pending, 'replace');
        }} else if(act === 'append'){{
          applyChipText(step, pending, 'append');
        }}
        hideChipChoice(step);
      }});
    }});
    root.querySelector('#uv-cancel').onclick = function(){{
      root.hidden = true; root.innerHTML='';
      closeVerifyAssist();
    }};
    root.querySelector('#uv-save').onclick = function(){{
      var verdict = (root.querySelector('input[name="uv-v"]:checked')||{{}}).value || 'correct';
      var step_notes = {{}};
      root.querySelectorAll('.uv-step').forEach(function(st){{
        var role = st.getAttribute('data-role');
        var has = !!(st.querySelector('.uv-step-err') && st.querySelector('.uv-step-err').checked);
        var note = (st.querySelector('textarea') && st.querySelector('textarea').value) || '';
        step_notes[role] = {{ has_error: has, note: note }};
      }});
      var body = {{
        username: apiUsername(),
        analysis_id: (document.body && document.body.getAttribute('data-analysis-id')) || '',
        run_id: 'current',
        qid_global: qid,
        label: label || qid,
        verdict: verdict,
        step_notes: step_notes
      }};
      fetch('/api/ci/homework/verify_save', {{
        method:'POST', headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify(body), credentials:'same-origin'
      }}).then(function(r){{ return r.json(); }}).then(function(res){{
        if(res && res.error_num === 0){{
          markVerified(qid);
          root.hidden = true; root.innerHTML='';
          closeVerifyAssist();
          postToParents({{ type:'nkcn-homework-verify-saved', qid:qid, verifiedCount: res.verified_count||0 }});
        }} else {{
          alert((res && res.msg) || '保存失败');
        }}
      }}).catch(function(){{ alert('保存失败'); }});
    }};
  }}
  function startVerifyIterate(){{
    var username = apiUsername();
    var analysisId = (document.body && document.body.getAttribute('data-analysis-id')) || '';
    if(!username || !analysisId){{ alert('缺少本子或批改标识'); return; }}
    var btn = document.getElementById('uv-iterate-btn');
    // 优先交给宿主页弹进度条；若无宿主则本地启动并轮询
    var hasParent = false;
    try {{ hasParent = !!(window.parent && window.parent !== window); }} catch(e){{ hasParent = false; }}
    if(hasParent){{
      if(btn) btn.disabled = true;
      postToParents({{
        type:'nkcn-homework-verify-iterate',
        username: username,
        analysisId: analysisId,
        analysis_id: analysisId,
        runId: (document.body && document.body.getAttribute('data-run-id')) || 'current',
        run_id: (document.body && document.body.getAttribute('data-run-id')) || 'current'
      }});
      // 宿主弹进度条；按钮短暂禁用避免连点（宿主未响应时恢复）
      setTimeout(function(){{ if(btn) btn.disabled = false; }}, 1600);
      return;
    }}
    if(btn) btn.disabled = true;
    fetch('/api/ci/homework/verify_iterate', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{ username:username, analysis_id:analysisId, run_id:'current' }}),
      credentials:'same-origin'
    }}).then(function(r){{ return r.json(); }}).then(function(res){{
      if(!(res && res.error_num===0 && res.job_id)){{
        if(btn) btn.disabled = false;
        alert((res && res.msg) || '启动失败');
        return;
      }}
      var jobId = res.job_id;
      var timer = setInterval(function(){{
        fetch('/api/ci/homework/verify_iterate_status', {{
          method:'POST', headers:{{'Content-Type':'application/json'}},
          body: JSON.stringify({{ job_id: jobId }}), credentials:'same-origin'
        }}).then(function(r){{ return r.json(); }}).then(function(st){{
          var job = (st && st.job) || {{}};
          if(job.status && job.status !== 'running'){{
            clearInterval(timer);
            if(btn) btn.disabled = false;
            if(job.status === 'ok'){{
              alert('迭代更新完成，请刷新解释精要卡查看。');
            }} else {{
              alert(job.error || job.msg || '迭代更新失败');
            }}
          }}
        }}).catch(function(){{}});
      }}, 2000);
    }}).catch(function(){{ if(btn) btn.disabled = false; alert('启动失败'); }});
  }}
  // 回填已核验标记
  (function loadVerified(){{
    var username = apiUsername();
    var analysisId = (document.body && document.body.getAttribute('data-analysis-id')) || '';
    if(!username || !analysisId) return;
    fetch('/api/ci/homework/verify_list', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{ username:username, analysis_id:analysisId }}),
      credentials:'same-origin'
    }}).then(function(r){{ return r.json(); }}).then(function(res){{
      var items = ((res && res.verifications) || {{}}).items || {{}};
      Object.keys(items).forEach(function(qid){{ markVerified(qid); }});
    }}).catch(function(){{}});
  }})();

  show(0);
}})();
</script>
</body>
</html>'''
