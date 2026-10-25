# -*- coding: utf-8 -*-
"""批改·解释精要卡：业务可读正文 / 生图摘要 / 模板 HTML（不调模型）。"""
from __future__ import annotations

import html
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .confidence_zones import (
    SHADE_DISPLAY,
    SHADE_ORDER,
    clamp_confidence,
    combined_recognition_understanding_confidence,
    count_shade_distribution,
    gray_shade,
)
from .curriculum import humanize_knowledge_point, id_to_cn
from .utils import parse_page_num, safe_json_load, sorted_json_pages

CARD_PAGE_BREAK = '\n\n---NKCN_CARD_PAGE---\n\n'
MARKER_RE = re.compile(r'<!--\s*nkcn_grading_card:[^>]*-->\s*', re.I)
CURRICULUM_ID_RE = re.compile(r'^[A-Z]{2}_S\d+_\d+$')

_VERDICT_CN = {
    'correct': '正确',
    'wrong': '错误',
    'partial': '半对',
    'unanswered': '未答',
    'uncertain': '待确认',
}
_STAGE_CN = {
    'layout': '无损版面',
    'understanding': '无损理解',
    'grading': '三区批改',
}
_ZONE_CN = {
    'blind_spot': '盲区',
    'friction_zone': '内耗区',
    'zpd': '最近发展区',
}
_SHADE_SCORE = {
    'white': 100,
    'gray_light': 75,
    'gray_mid': 50,
    'gray_deep': 25,
    'black': 0,
}
_MATERIAL_CN = {
    'homework': '作业',
    'exam': '试卷',
    'test': '试卷',
    'notes': '笔记',
    'note': '笔记',
    'essay': '作文',
    'composition': '作文',
    'open': '开放材料',
    'other': '其他',
}
_SHADE_COLOR = {
    'white': '#f4f4f2',
    'gray_light': '#c5c5c0',
    'gray_mid': '#8e8e88',
    'gray_deep': '#555550',
    'black': '#1f1f1f',
}
_SHADE_INK = {
    'white': '#2a2a28',
    'gray_light': '#2a2a28',
    'gray_mid': '#fff',
    'gray_deep': '#fff',
    'black': '#fff',
}
_VERDICT_META = {
    '正确': ('ok', '✓'),
    '错误': ('bad', '✗'),
    '半对': ('half', '◐'),
    '未答': ('empty', '○'),
    '待确认': ('wait', '?'),
    'correct': ('ok', '✓'),
    'wrong': ('bad', '✗'),
    'partial': ('half', '◐'),
    'unanswered': ('empty', '○'),
    'uncertain': ('wait', '?'),
}


def strip_grading_card_marker(text: str) -> str:
    return MARKER_RE.sub('', text or '').lstrip()


def _esc(text: Any) -> str:
    return html.escape(str(text or ''), quote=True)


def _clip(text: Any, limit: int = 220) -> str:
    s = re.sub(r'\s+', ' ', str(text or '')).strip()
    if not s:
        return ''
    return s if len(s) <= limit else (s[: max(1, limit - 1)] + '…')


def _clip_keep_lines(text: Any, limit: int = 480) -> str:
    s = str(text or '').strip()
    if not s:
        return ''
    if len(s) <= limit:
        return s
    # 业务展示避免「…」省略号；在句读处截断
    cut = s[:limit].rstrip('，,；;、 \n')
    return cut


def _resolve_feedback_context(
    report: Optional[Dict[str, Any]] = None,
    ontology: Optional[Dict[str, Any]] = None,
    feedback_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if isinstance(feedback_context, dict) and feedback_context:
        return feedback_context
    for src in (ontology or {}, report or {}):
        ctx = src.get('feedback_context')
        if isinstance(ctx, dict) and ctx:
            return ctx
    return {}


def _shade_dot_html(shade_key: str, label: str = '') -> str:
    """图例/标签芯片：底白，文字始终深色，避免深灰/黑区白字看不见。"""
    color = _SHADE_COLOR.get(shade_key, '#8e8e88')
    border = '#c8c4ba' if shade_key == 'white' else color
    text = _esc(label or SHADE_DISPLAY.get(shade_key, '灰区'))
    # 芯片背景是白底，标签字必须深色；色点本身用 --dot
    return (
        f'<span class="shade-chip shade-{_esc(shade_key)}" '
        f'style="--dot:{color};--ink:#1c2430;--bd:{border}">'
        f'<i class="shade-dot" aria-hidden="true"></i>{text}</span>'
    )


def _verdict_badge_html(verdict: str) -> str:
    v = str(verdict or '').strip()
    if not v:
        return ''
    kind, icon = _VERDICT_META.get(v, ('wait', '·'))
    return f'<span class="verdict verdict-{kind}"><b>{icon}</b>{_esc(v)}</span>'


def _comment_layers(comment: str) -> Dict[str, str]:
    from .explanation_layers import parse_layers, has_layer_markers, SEE, MEAN, NEXT
    text = str(comment or '').strip()
    if not text:
        return {}
    if has_layer_markers(text):
        layers = parse_layers(text)
        return {k: layers.get(k) or '' for k in (SEE, MEAN, NEXT) if layers.get(k)}
    return {}


def _format_comment_md(comment: str) -> List[str]:
    from .explanation_layers import SEE, MEAN, NEXT
    layers = _comment_layers(comment)
    if not layers:
        return [f"- **批语**：{_clip(comment, 280)}"] if comment else []
    out = ['- **批语**：']
    label = {SEE: '看到', MEAN: '说明', NEXT: '下一步'}
    for key in (SEE, MEAN, NEXT):
        if layers.get(key):
            out.append(f"  - **{label[key]}**：{_clip(layers[key], 220)}")
    return out


def _comment_html(comment: str) -> str:
    from .explanation_layers import SEE, MEAN, NEXT
    layers = _comment_layers(comment)
    if not layers:
        return f'<p class="comment-plain"><strong>批语</strong> {_esc(comment)}</p>' if comment else ''
    label = {SEE: '看到', MEAN: '说明', NEXT: '下一步'}
    items = []
    for key in (SEE, MEAN, NEXT):
        if layers.get(key):
            items.append(
                f'<div class="layer"><span class="layer-k">{label[key]}</span>'
                f'<p>{_esc(_clip(layers[key], 360))}</p></div>'
            )
    return f'<div class="comment-layers"><div class="layer-title">批语</div>{"".join(items)}</div>'


def _shade_only(value: Any, mode: str, subject: str) -> str:
    n = clamp_confidence(value)
    if n is None:
        return '灰区'
    shade = gray_shade(n, mode=mode, subject=subject)  # type: ignore[arg-type]
    return SHADE_DISPLAY.get(shade, '灰区')


def _shade_key(value: Any, mode: str, subject: str) -> str:
    n = clamp_confidence(value)
    if n is None:
        return 'gray_mid'
    return gray_shade(n, mode=mode, subject=subject)  # type: ignore[arg-type]


def _count_line(counts: Dict[str, int]) -> str:
    parts = []
    for key in SHADE_ORDER:
        n = int(counts.get(key) or 0)
        if n:
            parts.append(f'{SHADE_DISPLAY.get(key, key)} {n}')
    return ' · '.join(parts) if parts else '（本步暂无置信分）'


def _unit_word(material_type: str = 'homework') -> str:
    mt = (material_type or '').lower()
    if mt in ('notes', 'note', 'essay', 'composition', 'open', 'other'):
        return '条目'
    return '题'


def _human_qid(page: int, qid: str, *, material_type: str = 'homework') -> str:
    qid = str(qid or '').strip() or '?'
    word = _unit_word(material_type)
    if qid.startswith('auto-'):
        qid = qid[5:]
    return f'第{page}页 · {qid}{word}'


def _human_evidence(qid: Any, *, material_type: str = 'homework') -> str:
    text = str(qid or '').strip()
    m = re.match(r'^p(\d+)[:：](.+)$', text, re.I)
    if m:
        return _human_qid(int(m.group(1)), m.group(2), material_type=material_type)
    return text


def _hub_title(subject: str, entry: Dict[str, Any]) -> str:
    from .curriculum import strip_curriculum_codes
    raw = str(entry.get('knowledge_point') or '').strip()
    cid = str(entry.get('curriculum_id') or '').strip()
    title = humanize_knowledge_point(subject, raw) if raw else ''
    if not title and cid:
        title = id_to_cn(subject, cid)
    title = strip_curriculum_codes(title) if title else title
    # 仍只剩课标码、或空：再回退
    if not title or CURRICULUM_ID_RE.match(title) or re.search(r'[A-Z]{2}_S\d+_\d+', title or ''):
        rationale = strip_curriculum_codes(
            _clip(entry.get('rationale') or entry.get('comment') or '', 28)
        )
        title = rationale or title or '要点'
    return title


def _infer_qtype(question: Dict[str, Any], *, subject: str, material_type: str) -> str:
    mt = (material_type or '').lower()
    if mt in ('notes', 'note'):
        role = str(question.get('note_role') or '').strip()
        return {'note': '笔记要点', 'example': '例题摘录', 'exercise': '练习摘录'}.get(role, '笔记内容')
    if mt in ('essay', 'composition'):
        return '作文段落'
    stem = ' '.join(str(question.get(k) or '') for k in ('parent_stem_excerpt', 'stem_excerpt'))
    compact = re.sub(r'\s+', '', stem)
    try:
        from .question_type import (
            is_math_fill_blank_style_question,
            normalize_application_major_problem,
        )
        if subject == 'math' and normalize_application_major_problem(question, 'math'):
            return '应用题'
        if subject == 'math' and is_math_fill_blank_style_question(question):
            return '填空题'
    except Exception:
        pass
    if any(x in compact for x in ('选择题', '下列正确', '选一选')) or (
        '选择' in compact and ('正确' in compact or '下列' in compact)
    ):
        return '选择题'
    if '判断' in compact and ('对错' in compact or '√' in compact or '×' in compact):
        return '判断题'
    if '连线' in compact:
        return '连线题'
    if '计算' in compact or '列式' in compact:
        return '计算题'
    if '填空' in compact or '填表' in compact:
        return '填空题'
    if '简答' in compact or '解答' in compact:
        return '解答题'
    return '综合题'


def _page_feedback_map(report: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for item in report.get('page_feedback_contexts') or []:
        if not isinstance(item, dict):
            continue
        try:
            page = int(item.get('page'))
        except (TypeError, ValueError):
            continue
        out[page] = item
    return out


def _comment_map(report: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in report.get('per_question_feedback') or []:
        if not isinstance(item, dict):
            continue
        qid = str(item.get('qid_global') or '').strip()
        if not qid and item.get('page') is not None and item.get('id') is not None:
            qid = f"p{item.get('page')}:{item.get('id')}"
        comment = str(item.get('comment') or '').strip()
        if qid and comment:
            out[qid] = comment
    return out


def _collect_units(
    pass1_dir: str,
    subject: str,
    report: Dict[str, Any],
    *,
    assigned_pages: Optional[List[int]] = None,
    material_type: str = 'homework',
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回 (units, pages_meta)。"""
    allow = set(int(p) for p in assigned_pages) if assigned_pages else None
    pf_map = _page_feedback_map(report)
    comments = _comment_map(report)
    units: List[Dict[str, Any]] = []
    pages_meta: List[Dict[str, Any]] = []

    for path in sorted_json_pages(pass1_dir):
        page_num = parse_page_num(os.path.basename(path))
        if page_num <= 0 or (allow is not None and page_num not in allow):
            continue
        try:
            data = safe_json_load(path)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        questions = [q for q in (data.get('questions') or []) if isinstance(q, dict)]
        page_layout: List[int] = []
        page_und: List[int] = []
        page_grade: List[int] = []
        page_units: List[Dict[str, Any]] = []
        for q in questions:
            lc = clamp_confidence(q.get('layout_confidence'))
            uc = combined_recognition_understanding_confidence(q)
            gc = clamp_confidence(q.get('grading_confidence'))
            if lc is not None:
                page_layout.append(lc)
            if uc is not None:
                page_und.append(uc)
            if gc is not None:
                page_grade.append(gc)
            qid = str(q.get('id') or '').strip() or '?'
            global_id = str(q.get('qid_global') or f'p{page_num}:{qid}')
            kp_raw = str(q.get('knowledge_point') or '').strip()
            cid = str(q.get('curriculum_id') or '').strip()
            kp = humanize_knowledge_point(subject, kp_raw) or id_to_cn(subject, cid) or ''
            unit = {
                'page': page_num,
                'qid': qid,
                'label': _human_qid(page_num, qid, material_type=material_type),
                'unit_word': _unit_word(material_type),
                'material_type': material_type,
                'layout_shade': _shade_key(lc, 'layout', subject),
                'understanding_shade': _shade_key(uc, 'understanding', subject),
                'grading_shade': _shade_key(gc, 'grading', subject),
                'layout_label': _shade_only(lc, 'layout', subject),
                'understanding_label': _shade_only(uc, 'understanding', subject),
                'grading_label': _shade_only(gc, 'grading', subject),
                'qtype': _infer_qtype(q, subject=subject, material_type=material_type),
                'knowledge_point': kp,
                'curriculum': id_to_cn(subject, cid) or kp,
                'stem': _clip(q.get('stem_excerpt') or q.get('parent_stem_excerpt'), 180),
                'student': _clip(q.get('student_answer'), 160),
                'understanding': _clip(q.get('understanding'), 200),
                'correct': _clip(q.get('correct_answer'), 120),
                'verdict': _VERDICT_CN.get(str(q.get('verdict') or ''), '') or str(q.get('verdict') or ''),
                'comment': _clip_keep_lines(
                    comments.get(global_id) or q.get('teacher_comment') or q.get('comment'), 520
                ),
                'zone': _ZONE_CN.get(str(q.get('zone') or ''), ''),
                'verdict_key': str(q.get('verdict') or ''),
            }
            page_units.append(unit)
            units.append(unit)

        ctx = pf_map.get(page_num) or {}
        pages_meta.append({
            'page': page_num,
            'header': _clip(data.get('page_header'), 80),
            'unit_title': _clip(ctx.get('unit_title'), 80),
            'quote': _clip(ctx.get('unit_evidence_quote'), 160),
            'summary': _clip_keep_lines(ctx.get('understanding_summary'), 520),
            'layout_line': _count_line(count_shade_distribution(page_layout, 'layout', subject=subject)),
            'understanding_line': _count_line(count_shade_distribution(page_und, 'understanding', subject=subject)),
            'grading_line': _count_line(count_shade_distribution(page_grade, 'grading', subject=subject)),
            'units': page_units,
        })
    return units, pages_meta


def _bucket_breakdown(units: List[Dict[str, Any]], key: str = 'qtype') -> str:
    if not units:
        return '—'
    total = len(units)
    counter = Counter(str(u.get(key) or '未标注') for u in units)
    parts = []
    for name, count in counter.most_common(6):
        pct = round(100.0 * count / total)
        parts.append(f'{name} {count}（{pct}%）')
    return '；'.join(parts)


def _format_loc_list(units: List[Dict[str, Any]], limit: int = 18) -> str:
    labels = [u['label'] for u in units[:limit]]
    more = f' 等共{len(units)}处' if len(units) > limit else ''
    return '、'.join(labels) + more if labels else '—'


def _is_white(s: str) -> bool:
    return s == 'white'


def _is_black(s: str) -> bool:
    return s == 'black'


def _is_gray(s: str) -> bool:
    return s in ('gray_deep', 'gray_mid', 'gray_light')


def _build_rich_overview(
    units: List[Dict[str, Any]],
    subject: str,
    *,
    material_type: str = 'homework',
) -> str:
    if not units:
        return ''
    layout_counts = {k: 0 for k in SHADE_ORDER}
    und_counts = {k: 0 for k in SHADE_ORDER}
    grade_counts = {k: 0 for k in SHADE_ORDER}
    for u in units:
        layout_counts[u['layout_shade']] = layout_counts.get(u['layout_shade'], 0) + 1
        und_counts[u['understanding_shade']] = und_counts.get(u['understanding_shade'], 0) + 1
        grade_counts[u['grading_shade']] = grade_counts.get(u['grading_shade'], 0) + 1

    rows = [
        f"| {_STAGE_CN['layout']} | {_count_line(layout_counts)} |",
        f"| {_STAGE_CN['understanding']} | {_count_line(und_counts)} |",
        f"| {_STAGE_CN['grading']} | {_count_line(grade_counts)} |",
    ]

    all_white = [u for u in units if all(_is_white(u[k]) for k in ('layout_shade', 'understanding_shade', 'grading_shade'))]
    black_layout = [u for u in units if _is_black(u['layout_shade'])]
    black_und = [u for u in units if _is_black(u['understanding_shade'])]
    black_grade = [u for u in units if _is_black(u['grading_shade'])]
    black_count = lambda u: sum(1 for k in ('layout_shade', 'understanding_shade', 'grading_shade') if _is_black(u[k]))
    gray_count = lambda u: sum(1 for k in ('layout_shade', 'understanding_shade', 'grading_shade') if _is_gray(u[k]))
    white_count = lambda u: sum(1 for k in ('layout_shade', 'understanding_shade', 'grading_shade') if _is_white(u[k]))

    three_black = [u for u in units if black_count(u) == 3]
    two_black = [u for u in units if black_count(u) == 2]
    two_white_one_black = [u for u in units if white_count(u) == 2 and black_count(u) == 1]
    two_white_one_gray = [u for u in units if white_count(u) == 2 and gray_count(u) == 1]
    one_white_two_gray = [u for u in units if white_count(u) == 1 and gray_count(u) == 2]
    all_gray = [u for u in units if gray_count(u) == 3]
    no_white = [u for u in units if white_count(u) == 0]

    gray_shade_parts = []
    for shade in ('gray_deep', 'gray_mid', 'gray_light'):
        n = sum(
            1 for u in two_white_one_gray
            for k in ('layout_shade', 'understanding_shade', 'grading_shade')
            if u[k] == shade
        )
        if n:
            pct = round(100.0 * n / max(len(two_white_one_gray), 1))
            gray_shade_parts.append(f'{SHADE_DISPLAY[shade]} {n}（{pct}%）')

    # weighted composite
    scores = []
    for u in units:
        s = (
            _SHADE_SCORE.get(u['layout_shade'], 50)
            + _SHADE_SCORE.get(u['understanding_shade'], 50)
            + _SHADE_SCORE.get(u['grading_shade'], 50)
        ) / 3.0
        scores.append(s)
    avg = sum(scores) / len(scores) if scores else 50
    if avg >= 85:
        composite = '综合偏白区（三步整体把握较稳）'
    elif avg >= 60:
        composite = '综合偏浅灰（多数可信，个别步骤需留意）'
    elif avg >= 40:
        composite = '综合偏中灰（建议抽查灰/黑交界处）'
    elif avg >= 20:
        composite = '综合偏深灰（需重点核对）'
    else:
        composite = '综合偏黑区（建议优先人工复核）'

    n = len(units)
    pct = lambda xs: f'{len(xs)}（{round(100.0 * len(xs) / n)}%）'
    show_qtype = (material_type or '').lower() not in (
        'notes', 'note', 'essay', 'composition', 'open', 'other',
    )

    cross_named = [
        ('三步都是白区', all_white),
        ('版面黑区出现位置', black_layout),
        ('理解黑区出现位置', black_und),
        ('批改黑区出现位置', black_grade),
        ('三步都是黑区', three_black),
        ('两步黑区', two_black),
        ('两步白区、一步黑区', two_white_one_black),
        ('两步白区、一步灰区', two_white_one_gray),
        ('一步白区、两步灰区', one_white_two_gray),
        ('三步都是灰区', all_gray),
        ('三步都没有白区', no_white),
    ]

    lines = [
        '## 总览：三步骤 × 白灰黑',
        '',
        '白区=把握很稳；深灰/中灰/浅灰=越靠白越稳、越靠黑越要再看；黑区=建议人工核一眼。',
        '下面统计与逐页条目用同一套分区，方便对照批改界面里的框色/圆点。',
        '',
        '| 步骤 | 白灰黑分布 |',
        '| --- | --- |',
        *rows,
        '',
        '### 交叉情况（三步骤合起来看）',
        '',
        f'- **三步都是白区**：{pct(all_white)}'
        + (f' · 题型：{_bucket_breakdown(all_white)}' if all_white and show_qtype else ''),
        f'- **版面黑区出现位置**：{_format_loc_list(black_layout)}'
        + (f' · 题型：{_bucket_breakdown(black_layout)}' if black_layout and show_qtype else ''),
        f'- **理解黑区出现位置**：{_format_loc_list(black_und)}'
        + (f' · 题型：{_bucket_breakdown(black_und)}' if black_und and show_qtype else ''),
        f'- **批改黑区出现位置**：{_format_loc_list(black_grade)}'
        + (f' · 题型：{_bucket_breakdown(black_grade)}' if black_grade and show_qtype else ''),
        f'- **三步都是黑区**：{pct(three_black)}'
        + (f' · {_format_loc_list(three_black, 10)}' if three_black else ''),
        f'- **两步黑区**：{pct(two_black)}'
        + (f' · {_format_loc_list(two_black, 10)}' if two_black else ''),
        f'- **两步白区、一步黑区**（那两步「白」的可信度可能下降，建议核验）：{pct(two_white_one_black)}'
        + (f' · {_format_loc_list(two_white_one_black, 12)}' if two_white_one_black else '')
        + (f' · 题型：{_bucket_breakdown(two_white_one_black)}' if two_white_one_black and show_qtype else ''),
        f'- **两步白区、一步灰区**：{pct(two_white_one_gray)}'
        + (f' · 灰档：{"；".join(gray_shade_parts) if gray_shade_parts else "—"}' if two_white_one_gray else '')
        + (f' · 题型：{_bucket_breakdown(two_white_one_gray)}' if two_white_one_gray and show_qtype else ''),
        f'- **一步白区、两步灰区**：{pct(one_white_two_gray)}'
        + (f' · 题型：{_bucket_breakdown(one_white_two_gray)}' if one_white_two_gray and show_qtype else ''),
        f'- **三步都是灰区**：{pct(all_gray)}'
        + (f' · 题型：{_bucket_breakdown(all_gray)}' if all_gray and show_qtype else ''),
        f'- **三步都没有白区**：{pct(no_white)}'
        + (f' · 题型：{_bucket_breakdown(no_white)}' if no_white and show_qtype else ''),
    ]

    if show_qtype:
        lines.extend(['', '#### 各交叉情形的题型占比', ''])
        for name, bucket in cross_named:
            if bucket:
                lines.append(f'- **{name}**：{_bucket_breakdown(bucket)}')
        # 各题型落在哪些交叉情形
        from collections import defaultdict
        by_qtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for u in units:
            by_qtype[str(u.get('qtype') or '未标注')].append(u)
        lines.extend(['', '#### 各题型的交叉情形占比', ''])
        for qtype, q_units in sorted(by_qtype.items(), key=lambda x: -len(x[1])):
            parts = []
            total = len(q_units) or 1
            for name, bucket in cross_named:
                ids = {(x.get('page'), x.get('qid')) for x in bucket}
                cnt = sum(1 for u in q_units if (u.get('page'), u.get('qid')) in ids)
                if cnt:
                    parts.append(f'{name} {cnt}（{round(100.0 * cnt / total)}%）')
            if parts:
                lines.append(f'- **{qtype}**：{"；".join(parts)}')

    # curriculum for notable buckets（说法面向用户，避免内部简称）
    notable = [
        ('多数步骤很稳（白区）、仅一步需人工核验', two_white_one_black),
        ('有两步需人工核验', two_black),
        ('三步都偏灰或黑、建议优先复核', no_white),
        ('三步都很稳（白区）', all_white),
    ]
    curr_lines = []
    for name, bucket in notable:
        with_c = [u for u in bucket if u.get('curriculum')]
        if not with_c:
            continue
        curr_lines.append(
            f'- **{name}时，对应课标要求集中于**：{_bucket_breakdown(with_c, "curriculum")}'
        )
    if curr_lines:
        lines.extend(['', '### 课标分布', ''] + curr_lines)

    lines.extend(['', '### 综合白灰黑（三步加权）', '', f'- {composite}（均分约 {round(avg)}）'])
    return '\n'.join(lines)


def _unit_heading(unit: Dict[str, Any]) -> str:
    qid = str(unit.get('qid') or '').strip()
    word = unit.get('unit_word') or _unit_word(str(unit.get('material_type') or 'homework'))
    if qid.startswith('auto-'):
        return f"{word} {qid[5:]}"
    return f"{word} {qid or '?'}"


def _format_question_block(unit: Dict[str, Any]) -> str:
    title_bits = [_unit_heading(unit)]
    if unit.get('verdict'):
        title_bits.append(unit['verdict'])
    title_bits.append(f"批改·{unit['grading_label']}")
    lines = [f"#### {' · '.join(title_bits)}", '']
    stem = unit.get('stem') or ''
    stem_fallback = '条目内容已切出' if unit.get('unit_word') == '条目' else '题框已切出'
    lines.append(f"- **无损版面**（{unit['layout_label']}）" + (f'：{stem}' if stem else f'：{stem_fallback}'))
    lines.append('')
    und_parts = []
    if unit.get('student'):
        und_parts.append(f"学生作答「{unit['student']}」")
    if unit.get('understanding'):
        und_parts.append(unit['understanding'])
    lines.append(
        f"- **无损理解**（{unit['understanding_label']}）"
        + ('：' + '；'.join(und_parts) if und_parts else '：已完成识别与题意理解')
    )
    lines.append('')
    grade_parts = []
    if unit.get('verdict'):
        grade_parts.append(unit['verdict'])
    if unit.get('correct'):
        grade_parts.append(f"参考「{unit['correct']}」")
    if unit.get('zone'):
        grade_parts.append(f"学习分区·{unit['zone']}")
    lines.append(
        f"- **三区批改**（{unit['grading_label']}）"
        + ('：' + '；'.join(grade_parts) if grade_parts else '：本单元已完成批改')
    )
    lines.append('')
    if unit.get('comment'):
        lines.extend(_format_comment_md(unit['comment']))
        lines.append('')
    return '\n'.join(lines)


def _build_material_context_section(
    report: Dict[str, Any],
    ontology: Dict[str, Any],
    feedback_context: Dict[str, Any],
    *,
    filename: str = '',
    material_type: str = 'homework',
) -> str:
    """总览与逐页之间：学段/年级/学科/品类 + 主体理解要点（全品类通用）。"""
    from .explanation_layers import (
        material_portrait_label,
        parse_layers,
        has_layer_markers,
        SEE,
        MEAN,
        NEXT,
        _fallback_layers,
    )

    lines = ['## 材料与学情理解', '']
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
    # 只保留一行画像，避免与学段/年级重复两遍
    if bits:
        lines.append(f'- **学段 / 年级 / 学科 / 品类**：{" · ".join(bits)}')
    elif portrait:
        lines.append(f'- **材料画像**：{portrait}')
    else:
        lines.append('- **学段 / 年级 / 学科 / 品类**：材料未标明')
    for key, label in (
        ('term', '学期'),
        ('textbook', '教材'),
        ('school_system', '学制'),
    ):
        val = str(feedback_context.get(key) or '').strip()
        if val and val not in ('unknown', '未知', 'None'):
            lines.append(f'- **{label}**：{val}')

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
        hub = _clip(overview.get('content_review') or diagnosis.get('cognitive_stage') or '', 120)
    if hub:
        lines.append(f'- **主体理解（枢纽）**：{_clip_keep_lines(hub, 420)}')
    if layers.get(SEE):
        lines.append(f'- **看到**：{_clip_keep_lines(layers[SEE], 900)}')
    if layers.get(MEAN):
        lines.append(f'- **说明**：{_clip_keep_lines(layers[MEAN], 700)}')
    if layers.get(NEXT):
        lines.append(f'- **下一步**：{_clip_keep_lines(layers[NEXT], 360)}')

    # 开放材料：补充 overview 短线；作业/试卷：补充对错概况若有
    if isinstance(overview, dict):
        layout = _clip_keep_lines(overview.get('subject_and_layout'), 420)
        if layout and layout not in (layers.get(SEE) or ''):
            lines.append(f'- **材料事实线**：{layout}')
    strengths = diagnosis.get('strengths') or []
    problems = diagnosis.get('main_problems') or []
    if isinstance(strengths, list) and strengths:
        lines.append(f'- **已看见的稳点**：{_clip_keep_lines("；".join(str(x) for x in strengths[:3]), 360)}')
    if isinstance(problems, list) and problems:
        lines.append(f'- **需盯的筛点**：{_clip_keep_lines("；".join(str(x) for x in problems[:3]), 360)}')

    if len(lines) <= 3:
        return ''
    return '\n'.join(lines)


def _hub_section(
    report: Dict[str, Any],
    ontology: Dict[str, Any],
    subject: str,
    *,
    limit: int = 5,
    material_type: str = 'homework',
) -> str:
    from .explanation_layers import format_layers, parse_layers, SEE, MEAN, NEXT

    items = []
    zones = (ontology or {}).get('zones') or {}
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        for entry in zones.get(bucket) or []:
            if not isinstance(entry, dict):
                continue
            title = _hub_title(subject, entry)
            if not title:
                continue
            qids = entry.get('evidence') or entry.get('evidence_question_ids') or []
            see = '、'.join(
                _human_evidence(x, material_type=material_type)
                for x in (qids[:2] if isinstance(qids, list) else [])
            )
            rationale = str(entry.get('rationale') or entry.get('comment') or '').strip()
            nxt = str(entry.get('suggested_next_step') or '').strip()
            if not rationale and not nxt:
                continue
            combined = format_layers(see or title, rationale, nxt)
            layers = parse_layers(combined)
            block = [f'### {_ZONE_CN.get(bucket, bucket)} · {title}']
            if layers.get(SEE):
                block.append(f'- **看到**：{_clip_keep_lines(layers[SEE], 280)}')
            if layers.get(MEAN):
                block.append(f'- **说明**：{_clip_keep_lines(layers[MEAN], 420)}')
            if layers.get(NEXT):
                block.append(f'- **下一步**：{_clip_keep_lines(layers[NEXT], 240)}')
            items.append('\n'.join(block))
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    if not items:
        return ''
    return '## 整篇枢纽\n\n' + '\n\n'.join(items)


def build_excerpt_payload(
    report: Optional[Dict[str, Any]] = None,
    ontology: Optional[Dict[str, Any]] = None,
    *,
    pass1_dir: str = '',
    subject: str = 'chinese',
    assigned_pages: Optional[List[int]] = None,
    filename: str = '',
    material_type: str = 'homework',
    feedback_context: Optional[Dict[str, Any]] = None,
    analysis_id: str = '',
    run_id: str = '',
) -> Dict[str, Any]:
    report = report or {}
    ontology = ontology or {}
    ctx = _resolve_feedback_context(report, ontology, feedback_context)
    subject = str(
        subject or ctx.get('subject_code') or 'chinese'
    ).strip().lower() or 'chinese'
    material_type = str(
        material_type
        or ctx.get('material_type')
        or ctx.get('material_key')
        or 'homework'
    ).strip().lower() or 'homework'
    units: List[Dict[str, Any]] = []
    pages_meta: List[Dict[str, Any]] = []
    if pass1_dir and os.path.isdir(pass1_dir):
        units, pages_meta = _collect_units(
            pass1_dir, subject, report,
            assigned_pages=assigned_pages, material_type=material_type,
        )
    return {
        'subject': subject,
        'material_type': material_type,
        'filename': filename,
        'units': units,
        'pages': pages_meta,
        'report': report,
        'ontology': ontology,
        'feedback_context': ctx,
        'analysis_id': str(analysis_id or '').strip(),
        'run_id': str(run_id or '').strip(),
    }


def build_excerpt_markdown(payload: Dict[str, Any], *, pages_per_card_page: int = 2) -> str:
    """完整 Markdown；用 CARD_PAGE_BREAK 分页（总览+枢纽为第1页，随后每 pages_per_card_page 页材料一页）。"""
    subject = payload.get('subject') or 'chinese'
    filename = _clip(payload.get('filename'), 80)
    material_cn = _MATERIAL_CN.get(payload.get('material_type') or '', '材料')
    units = payload.get('units') or []
    pages = payload.get('pages') or []
    report = payload.get('report') or {}
    ontology = payload.get('ontology') or {}

    head = ['# 批改·解释精要', '']
    if filename:
        head.append(f'> 材料：{filename}（{material_cn}）· 把批改界面里逐页三步结果留存在本子卡片里，便于通读。')
    else:
        head.append(f'> {material_cn}批改结果留存：三步骤与白灰黑一并展示，便于通读。')
    head.append('')

    overview = _build_rich_overview(
        units, subject,
        material_type=str(payload.get('material_type') or 'homework'),
    )
    ctx = payload.get('feedback_context') or {}
    material_sec = _build_material_context_section(
        report, ontology, ctx,
        filename=filename,
        material_type=str(payload.get('material_type') or 'homework'),
    )
    hub = _hub_section(
        report, ontology, subject,
        material_type=str(payload.get('material_type') or 'homework'),
    )
    first = '\n'.join(head)
    if overview:
        first += '\n\n' + overview
    if material_sec:
        first += '\n\n' + material_sec
    if hub:
        first += '\n\n' + hub

    page_chunks: List[str] = []
    if pages:
        note = f'共 {len(pages)} 页'
        page_chunks.append(f'## 逐页留存（{note}）')
        for meta in pages:
            block = [
                f"### 第 {meta['page']} 页" + (f" · {meta['header']}" if meta.get('header') else ''),
                '',
                f"- 本页置信：版面 {meta['layout_line']}；理解 {meta['understanding_line']}；批改 {meta['grading_line']}",
                '',
            ]
            if meta.get('unit_title'):
                block.append(f"- **本页单元**：{meta['unit_title']}")
                block.append('')
            if meta.get('quote'):
                block.append(f"- **原页摘录**：{meta['quote']}")
                block.append('')
            if meta.get('summary'):
                layers = _comment_layers(meta['summary'])
                if layers:
                    block.append('- **页评·理解**：')
                    from .explanation_layers import SEE, MEAN, NEXT
                    label = {SEE: '看到', MEAN: '说明', NEXT: '下一步'}
                    for key in (SEE, MEAN, NEXT):
                        if layers.get(key):
                            block.append(f"  - **{label[key]}**：{_clip(layers[key], 220)}")
                else:
                    block.append(f"- **页评·理解**：{meta['summary']}")
                block.append('')
            if not meta.get('units'):
                block.append('- （本页未切出教学单元）')
                block.append('')
            else:
                for unit in meta['units']:
                    block.append(_format_question_block(unit))
            page_chunks.append('\n'.join(block).rstrip() + '\n')

    card_pages = [first.strip()]
    if page_chunks:
        # first page of archive starts with ## 逐页留存 header + first N content pages
        header = page_chunks[0]
        content_pages = page_chunks[1:]
        if not content_pages:
            card_pages[0] = (card_pages[0] + '\n\n' + header).strip()
        else:
            for i in range(0, len(content_pages), max(1, pages_per_card_page)):
                group = content_pages[i:i + max(1, pages_per_card_page)]
                if i == 0:
                    card_pages.append((header + '\n\n' + '\n\n'.join(group)).strip())
                else:
                    card_pages.append('\n\n'.join(group).strip())
    return CARD_PAGE_BREAK.join(p for p in card_pages if p)


def build_excerpt_image_brief(payload: Dict[str, Any]) -> str:
    """生图只用：总览 + 枢纽 + 每页整体信息（不含逐题细节）。"""
    subject = payload.get('subject') or 'chinese'
    filename = _clip(payload.get('filename'), 60)
    units = payload.get('units') or []
    pages = payload.get('pages') or []
    report = payload.get('report') or {}
    ontology = payload.get('ontology') or {}
    parts = ['# 批改·解释精要（生图摘要）']
    if filename:
        parts.append(f'材料：{filename}')
    overview = _build_rich_overview(
        units, subject,
        material_type=str(payload.get('material_type') or 'homework'),
    )
    if overview:
        parts.append(overview)
    ctx = payload.get('feedback_context') or {}
    material_sec = _build_material_context_section(
        report, ontology, ctx,
        filename=filename,
        material_type=str(payload.get('material_type') or 'homework'),
    )
    if material_sec:
        parts.append(material_sec)
    hub = _hub_section(
        report, ontology, subject,
        material_type=str(payload.get('material_type') or 'homework'),
    )
    if hub:
        parts.append(hub)
    if pages:
        parts.append('## 各页整体')
        for meta in pages:
            line = [
                f"### 第 {meta['page']} 页" + (f" · {meta['header']}" if meta.get('header') else ''),
                f"- 本页置信：版面 {meta['layout_line']}；理解 {meta['understanding_line']}；批改 {meta['grading_line']}",
            ]
            if meta.get('summary'):
                line.append(f"- **页评·理解**：{meta['summary']}")
            parts.append('\n'.join(line))
    return '\n\n'.join(parts)


def build_excerpt_card_body(
    report: Optional[Dict[str, Any]] = None,
    ontology: Optional[Dict[str, Any]] = None,
    *,
    limit: int = 5,
    pass1_dir: Optional[str] = None,
    subject: str = 'chinese',
    assigned_pages: Optional[List[int]] = None,
    filename: str = '',
    material_type: str = 'homework',
    feedback_context: Optional[Dict[str, Any]] = None,
) -> str:
    payload = build_excerpt_payload(
        report, ontology,
        pass1_dir=pass1_dir or '',
        subject=subject,
        assigned_pages=assigned_pages,
        filename=filename,
        material_type=material_type,
        feedback_context=feedback_context,
    )
    body = build_excerpt_markdown(payload)
    if body.strip():
        return body
    # 无 Pass1 时尽量仍给枢纽
    hub = _hub_section(report or {}, ontology or {}, subject, limit=limit)
    return hub



def build_excerpt_html(payload: Dict[str, Any]) -> str:
    """Template HTML: charts/icons/nav; no LLM."""
    from .excerpt_html_views import render_excerpt_html
    return render_excerpt_html(payload)



def is_excerpt_grading_card(content: str = '', title: str = '') -> bool:
    text = content or ''
    t = title or ''
    return (
        '批改·解释精要' in text
        or '批改·解释精要' in t
        or ('解释精要' in t and '批改' in t)
        or '<!--nkcn_grading_card:批改·解释精要' in text
    )


def _trim_excerpt_page_block(block: str) -> str:
    """逐页块只留标题、本页置信、页评·理解（去掉逐题细节等）。"""
    kept: List[str] = []
    in_summary = False
    for raw in (block or '').splitlines():
        s = raw.strip()
        if re.match(r'^###\s*第\s*\d+\s*页', s):
            kept.append(raw.rstrip())
            in_summary = False
            continue
        if re.match(r'^-\s*本页置信', s):
            kept.append(raw.rstrip())
            in_summary = False
            continue
        if '页评·理解' in s:
            kept.append(raw.rstrip())
            in_summary = True
            continue
        if not in_summary:
            continue
        if s.startswith('####') or re.match(r'^###\s', s):
            in_summary = False
            continue
        # 页评子项（缩进或 看到/说明/下一步）；其它顶级 bullet 结束页评
        indented = raw.startswith(' ') or raw.startswith('\t')
        if re.match(r'^-\s+', s) and not indented:
            if any(k in s for k in ('看到', '说明', '下一步')):
                kept.append(raw.rstrip())
            else:
                in_summary = False
            continue
        if indented or not s:
            kept.append(raw.rstrip())
            continue
        kept.append(raw.rstrip())
    return '\n'.join(kept).strip()


def trim_excerpt_card_for_qa(content: str = '', title: str = '') -> str:
    """
    问答勾选解释精要卡时的输入截取：
    总览（三步骤×白灰黑）、材料与学情理解、整篇枢纽全文保留；
    逐页只留页头 + 本页置信 + 页评·理解，不含逐题细节。
    """
    if not is_excerpt_grading_card(content, title):
        return content or ''
    text = strip_grading_card_marker(content or '')
    if not text.strip():
        return text
    text = text.replace(CARD_PAGE_BREAK, '\n\n')
    m = re.search(r'^##\s*逐页留存[^\n]*$', text, re.M)
    if not m:
        m = re.search(r'^##\s*各页整体[^\n]*$', text, re.M)
    if not m:
        return text.strip()
    head = text[:m.start()].rstrip()
    tail = text[m.start():]
    page_header = re.match(r'^##[^\n]*\n?', tail)
    page_intro = page_header.group(0).rstrip() if page_header else '## 逐页留存'
    body_after = tail[len(page_header.group(0)):] if page_header else tail
    page_blocks = []
    for part in re.split(r'(?=^###\s*第\s*\d+\s*页)', body_after, flags=re.M):
        part = part.strip()
        if part and re.match(r'^###\s*第\s*\d+\s*页', part):
            trimmed = _trim_excerpt_page_block(part)
            if trimmed:
                page_blocks.append(trimmed)
    if not page_blocks:
        return head
    return (head + '\n\n' + page_intro + '\n\n' + '\n\n'.join(page_blocks)).strip()
