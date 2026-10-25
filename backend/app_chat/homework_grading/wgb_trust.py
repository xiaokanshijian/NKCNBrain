# -*- coding: utf-8 -*-
"""逐题三步骤白灰黑交叉情形 → 整篇诊断可信度分层。

供 ontology 证据包、Pass2 批语、诊断卡/独立界面「需用户核实」共用。
交叉命名与解释精要卡「11 种交叉情形」对齐（互斥主标签 + 黑区步骤位）。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

# trust_tier: critical > careful > normal > confident
TRUST_CRITICAL = 'critical'   # 任一步黑区：采信更谨慎（一步轻、两/三步更重）
TRUST_CAREFUL = 'careful'     # 三步无白（含全灰）：说法留余地、建议留意
TRUST_NORMAL = 'normal'       # 两白一灰 / 一白两灰：正常分析
TRUST_CONFIDENT = 'confident' # 三步全白：可写得更明确细腻

# 与解释精要卡交叉命名对齐的主标签（每题一个互斥主情形）
_CROSS_TITLE = {
    'all_white': '三步都是白区',
    'two_white_one_gray': '两步白区、一步灰区',
    'one_white_two_gray': '一步白区、两步灰区',
    'all_gray': '三步都是灰区',
    'no_white': '三步都没有白区',
    'two_white_one_black': '两步白区、一步黑区',
    'one_black': '一步黑区',
    'two_black': '两步黑区',
    'three_black': '三步都是黑区',
    'other': '其他交叉情形',
}

_STEP_CN = {
    'layout': '版面',
    'understanding': '理解',
    'grading': '批改',
}

_TIER_CN = {
    TRUST_CRITICAL: '需加强核实（含黑区）',
    TRUST_CAREFUL: '建议留意加强核实（无白区）',
    TRUST_NORMAL: '可正常分析',
    TRUST_CONFIDENT: '可较有把握地分析',
}


def _is_white(s: str) -> bool:
    return s == 'white'


def _is_black(s: str) -> bool:
    return s == 'black'


def _is_gray(s: str) -> bool:
    return s in ('gray_deep', 'gray_mid', 'gray_light')


def classify_shades(layout: str, understanding: str, grading: str) -> Tuple[str, str, int, List[str]]:
    """返回 (cross_key, trust_tier, black_n, black_roles)。

    black_roles ∈ {layout, understanding, grading}，对应「版面/理解/批改黑区」维度。
    """
    shades = {
        'layout': layout or 'gray_mid',
        'understanding': understanding or 'gray_mid',
        'grading': grading or 'gray_mid',
    }
    black_roles = [k for k, s in shades.items() if _is_black(s)]
    black_n = len(black_roles)
    white_n = sum(1 for s in shades.values() if _is_white(s))
    gray_n = sum(1 for s in shades.values() if _is_gray(s))

    if black_n >= 3:
        return 'three_black', TRUST_CRITICAL, black_n, black_roles
    if black_n == 2:
        return 'two_black', TRUST_CRITICAL, black_n, black_roles
    if black_n == 1:
        # 与解释精要卡一致：两白一黑单独成类；其余一步黑归 one_black
        if white_n == 2:
            return 'two_white_one_black', TRUST_CRITICAL, black_n, black_roles
        return 'one_black', TRUST_CRITICAL, black_n, black_roles
    if white_n == 0:
        if gray_n == 3:
            return 'all_gray', TRUST_CAREFUL, 0, []
        return 'no_white', TRUST_CAREFUL, 0, []
    if white_n == 3:
        return 'all_white', TRUST_CONFIDENT, 0, []
    if white_n == 2 and gray_n == 1:
        return 'two_white_one_gray', TRUST_NORMAL, 0, []
    if white_n == 1 and gray_n == 2:
        return 'one_white_two_gray', TRUST_NORMAL, 0, []
    return 'other', TRUST_NORMAL, 0, []


def _cross_tags(cross_key: str, black_roles: List[str]) -> List[str]:
    """主情形 + 黑区步骤位（对应 11 种里的版面/理解/批改黑区）。"""
    tags = [_CROSS_TITLE.get(cross_key, cross_key)]
    for role in black_roles:
        tags.append(f'{_STEP_CN.get(role, role)}黑区')
    return tags


def collect_unit_trust(
    pass1_dir: str,
    subject: str = 'chinese',
    *,
    material_type: str = 'homework',
    assigned_pages: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """从 Pass1 逐页结果收集每题白灰黑与可信度分层。"""
    if not pass1_dir:
        return []
    try:
        from .excerpt_card_render import _collect_units
    except Exception:
        return []
    units, _pages = _collect_units(
        pass1_dir, subject, {},
        assigned_pages=assigned_pages,
        material_type=material_type or 'homework',
    )
    out: List[Dict[str, Any]] = []
    for u in units:
        cross_key, tier, black_n, black_roles = classify_shades(
            str(u.get('layout_shade') or ''),
            str(u.get('understanding_shade') or ''),
            str(u.get('grading_shade') or ''),
        )
        page = u.get('page')
        qid = str(u.get('qid') or '').strip() or '?'
        qid_global = f'p{page}:{qid}'
        tags = _cross_tags(cross_key, black_roles)
        out.append({
            'qid_global': qid_global,
            'page': page,
            'qid': qid,
            'label': u.get('label') or qid_global,
            'qtype': u.get('qtype') or '',
            'curriculum': u.get('curriculum') or '',
            'layout_shade': u.get('layout_shade'),
            'understanding_shade': u.get('understanding_shade'),
            'grading_shade': u.get('grading_shade'),
            'cross_key': cross_key,
            'cross_title': _CROSS_TITLE.get(cross_key, cross_key),
            'cross_tags': tags,
            'black_n': black_n,
            'black_roles': black_roles,
            'black_roles_cn': '、'.join(_STEP_CN.get(r, r) for r in black_roles),
            'trust_tier': tier,
            'trust_label': _TIER_CN.get(tier, tier),
            'unit_word': u.get('unit_word') or '题',
        })
    return out


def build_wgb_trust_summary(
    pass1_dir: str,
    subject: str = 'chinese',
    *,
    material_type: str = 'homework',
    assigned_pages: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """供证据包 / report / 诊断卡使用的汇总结构。"""
    units = collect_unit_trust(
        pass1_dir, subject,
        material_type=material_type,
        assigned_pages=assigned_pages,
    )
    if not units:
        return {}
    by_tier: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_cross: Dict[str, int] = Counter()
    for u in units:
        by_tier[u['trust_tier']].append(u)
        by_cross[u['cross_key']] += 1

    def _slim(u: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'qid_global': u['qid_global'],
            'page': u.get('page'),
            'qid': u.get('qid') or '',
            'label': u['label'],
            'curriculum': u.get('curriculum') or '',
            'cross_key': u['cross_key'],
            'cross_title': u['cross_title'],
            'cross_tags': u.get('cross_tags') or [u['cross_title']],
            'black_n': u.get('black_n') or 0,
            'black_roles': u.get('black_roles') or [],
            'black_roles_cn': u.get('black_roles_cn') or '',
            'trust_tier': u['trust_tier'],
            'layout_shade': u['layout_shade'],
            'understanding_shade': u['understanding_shade'],
            'grading_shade': u['grading_shade'],
            'qtype': u.get('qtype') or '',
        }

    # 黑区按步数从多到少排：三步黑 > 两步黑 > 一步黑（两白一黑）
    critical_raw = sorted(
        by_tier.get(TRUST_CRITICAL, []),
        key=lambda u: (-int(u.get('black_n') or 0), str(u.get('qid_global') or '')),
    )
    careful_raw = by_tier.get(TRUST_CAREFUL, [])
    critical = [_slim(u) for u in critical_raw]
    careful = [_slim(u) for u in careful_raw]
    need_verify = critical + careful
    word = '条目' if (material_type or '').lower() in (
        'notes', 'note', 'essay', 'composition', 'open', 'other',
    ) else '题'

    return {
        'material_type': material_type,
        'unit_word': word,
        'total_units': len(units),
        'tier_counts': {k: len(v) for k, v in by_tier.items()},
        'cross_counts': dict(by_cross),
        'by_qid': {u['qid_global']: _slim(u) for u in units},
        'need_verify': need_verify,
        'critical': critical,
        'careful': careful,
        'confident_count': len(by_tier.get(TRUST_CONFIDENT, [])),
        'normal_count': len(by_tier.get(TRUST_NORMAL, [])),
        'protocol_hint': _protocol_hint_text(word),
    }


def _protocol_hint_text(unit_word: str = '题') -> str:
    return (
        f'## 逐页素材可信度（三步骤白灰黑交叉）——分档把握，勿非黑即白\n'
        f'证据包中带有 `wgb_trust`：每道{unit_word}/条目已标 cross_title、cross_tags（含版面/理解/批改黑区位）、'
        f'black_n 与 trust_tier。用来调节「有多把握」，不是「能用或不能用」：\n'
        f'- **不要**因为某题有黑区就整题丢掉、整段诊断不写；也**不要**对全白素材写成百分之百肯定。\n'
        f'- **critical（含任一步黑区）**：采信更谨慎。优先用同知识点上 normal/confident 的{unit_word}支撑主要结论；'
        f'黑区题可作辅助参考。一步黑（尤其另两步仍白）只是把握低一些，不是全盘否定；'
        f'两步黑再谨慎一档；三步黑尽量不要单独支撑主要结论。提及黑区题时说法留余地，'
        f'并可写「建议对照原卷加强核实」。\n'
        f'- **careful（三步无白，含全灰）**：可照常参与分析，说法稍留余地，必要时写「建议留意加强核实」。\n'
        f'- **normal（两白一灰 / 一白两灰）**：正常分析、诊断、下一步与三区建议即可。\n'
        f'- **confident（三步全白）**：可写得更细腻、更明确，但仍是教育判断，勿说得太满。\n'
        f'Skill 与既有流程照常。主结论尽量落在较稳素材上；'
        f'若某判断**主要**靠黑区/无白区{unit_word}撑起来，再点明「需加强核实」——不要给每句话都贴核实标签。\n'
        f'对用户可见的文案只用「需加强核实」「建议留意加强核实」「对照原卷」这类平常说法，'
        f'不要自造生僻词。\n'
    )


def attach_trust_to_questions(
    questions: List[Dict[str, Any]],
    wgb_trust: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """给错题/开放单元列表附上 trust 字段（就地拷贝）。"""
    by_qid = (wgb_trust or {}).get('by_qid') or {}
    if not by_qid:
        return questions
    out = []
    for q in questions or []:
        item = dict(q)
        qid = str(item.get('qid_global') or '').strip()
        if not qid and item.get('page') is not None and item.get('id') is not None:
            qid = f"p{item.get('page')}:{item.get('id')}"
        meta = by_qid.get(qid)
        if meta:
            item['wgb_cross_title'] = meta.get('cross_title')
            item['wgb_cross_tags'] = meta.get('cross_tags') or []
            item['wgb_black_n'] = meta.get('black_n') or 0
            item['wgb_trust_tier'] = meta.get('trust_tier')
            item['wgb_trust_label'] = _TIER_CN.get(meta.get('trust_tier') or '', '')
            item['layout_shade'] = meta.get('layout_shade')
            item['understanding_shade'] = meta.get('understanding_shade')
            item['grading_shade'] = meta.get('grading_shade')
        out.append(item)
    return out


_OPEN_MATERIALS = {'notes', 'note', 'essay', 'composition', 'open', 'other'}
_ZONE_BUCKETS = (
    ('blind_spot', '盲区'),
    ('friction_zone', '内耗区'),
    ('zpd', '最近发展区'),
)


def zones_for_verification(ontology: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """三区每条建议自己的证据题号。只取 evidence，供短名单使用。"""
    zones = (ontology or {}).get('zones') or {}
    out: List[Dict[str, Any]] = []
    for bucket, name in _ZONE_BUCKETS:
        for entry in zones.get(bucket) or []:
            if not isinstance(entry, dict):
                continue
            evidence = []
            for item in entry.get('evidence') or []:
                if isinstance(item, str) and item.strip():
                    evidence.append(item.strip())
                elif isinstance(item, dict):
                    qid = str(item.get('qid_global') or item.get('qid') or '').strip()
                    if qid:
                        evidence.append(qid)
            if evidence:
                out.append({'name': name, 'evidence': evidence})
    return out


def build_user_verification_block(
    wgb_trust: Optional[Dict[str, Any]],
    zones: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """写入 report.user_verification。只改老师看到的短名单，不动 critical / careful。"""
    from .verify_shortlist import pack_verification_block, select_shortlist

    word = (wgb_trust or {}).get('unit_word') or '题'
    material = str((wgb_trust or {}).get('material_type') or '')
    # 开放材料没有离散题型。unit_word 为「条目」时同样跳过，避免打包时漏了 material_type。
    skip_qtype = material.lower() in _OPEN_MATERIALS or word == '条目'
    rows = select_shortlist(
        wgb_trust,
        zones,
        skip_qtype=skip_qtype,
    )
    block = pack_verification_block(rows, word)
    if wgb_trust:
        block['cross_counts'] = wgb_trust.get('cross_counts') or {}
    return block


def format_user_verification_markdown(block: Optional[Dict[str, Any]]) -> str:
    """诊断卡正文中的显眼区块；无待核实项时不占版面。理由不写进正文。"""
    if not block:
        return ''
    items = block.get('items') or []
    if not items:
        return ''
    title = block.get('title') or '需加强核实的位置'
    summary = block.get('summary') or ''
    lines = [f'## ⚠️ {title}', '', summary, '']
    headings = (
        ('I', 'I · 最应该优先核验的'),
        ('II', 'II · 其次应该先核验的'),
        ('III', 'III · 再次可做核验的'),
    )
    for level, heading in headings:
        group = [x for x in items if str(x.get('level') or '') == level]
        if not group:
            continue
        lines.append(f'### {heading}（{len(group)}）')
        labels = '、'.join(str(x.get('label') or x.get('qid_global') or '') for x in group)
        lines.append(f'- {labels}')
        lines.append('')
    return '\n'.join(lines).rstrip()
