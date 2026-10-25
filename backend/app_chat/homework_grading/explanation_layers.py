"""解释链白话三问：骨架固定，内标签随材料。不改判分字段。"""
import re
from typing import Any, Dict, List, Optional, Tuple

SEE = '看到了什么'
MEAN = '这说明什么'
NEXT = '下一步做什么'
MARKERS = (SEE, MEAN, NEXT)
MARKER_RE = re.compile(
    r'【(看到了什么|这说明什么|下一步做什么)】\s*',
)
INNER_TAG_RE = re.compile(
    r'【(?!看到了什么|这说明什么|下一步做什么)([^】]{1,12})】\s*',
)
GRADE_IN_NAME_RE = re.compile(
    r'(小学|初中|高中|大学)?(?:[一二三四五六七八九十\d]+年级|[四五六]年级|初[一二三]|高[一二三]|大[一二三四]|四年级|五年级|六年级)'
)
SUBJECT_IN_NAME_RE = re.compile(r'(语文|数学|英语|物理|化学|生物|历史|地理|道德与法治|科学)')
KIND_IN_NAME_RE = re.compile(r'(试卷|作业|作文|笔记|练习|测验)')

# 精炼自《导师思维与可用内容标准》+《内容水准加强方案》：进解释链 / 整篇 / 卡片 / HTML。
MENTOR_QUALITY_BLOCK = '''
【专家内容水准·必须遵守】
1) 微批是筛不是附录：看见证据→判当前环节→下一环节一小步；最小干预。禁止九论全文、方法名清单。
2) 先边界再方法：写清「能判断什么 / 材料未纳入什么」。未标明练习次数、书写人是否学生：保持未知，不推断进步退步。
3) 结构=枢纽+分栏+边界。禁止一面墙、禁止同一段复制两处。写法像 SKILL.md：短标题、主张一句、编号短句。
4) 知识是载体，证据是筛，人是目的。对错仍在；解释升到判断/真实目标。不改鸡汤，不取消对错。
5) 四阶段是 Skill 用懂后的一个自然判断面（流转不是站名），不是要硬删：整体感知/探究建构/应用迁移/重构拓展。有依据时该写就写，并点清「更贴近哪一段、凭哪页」。但横上不止这一个点——真实目标停在哪、结构边界清不清、该筛还是放过、下一小步是什么，也要自然出现。禁止所有条目都缩成同一句阶段口号。育人落点（好奇→合作→获得感→发现自我）写在整篇，逐页默认不写合作。
6) 下一步必须可做可验收（自己出题验算、画出数轴），禁止「加强理解」「多练习」。
7) 验收：只剩阶段词、看不出其它方法判断 → 浅用；硬删阶段后与未启用 Skill 几乎同构 → 也未达标。竖（批改话术）长在横（作者视角）上。
8) 认知三区≠关键词空间「盲区」。禁用英文方法名。
'''

REPORT_DUTY_PROTOCOL = '''
【报告块职责·禁止互相复述】
· open_material_overview（开放材料反馈）= 线：材料画像与页序事实链；判断≤3条短点；不要写完整育人落点与三区处方。
  - subject_and_layout：看到了什么（事实总账）
  - content_review：这说明什么（克制判断，不要抄诊断全文）
  - next_steps：1～2条可执行动作（可与诊断对齐，但不要再写一遍三问墙）
· evolution_narrative / diagnosis.summary（整篇诊断）= 面：先写一句枢纽判断（如「整理已成串，差一步自己做出来」），再按白话三问分点支撑该枢纽；禁止把开放材料段扩写一遍。
· zones（认知三区）：整篇合计 4～6 条硬点（宁少勿滥）。每条=短标题+证据一句+判断一句+下一步一句。禁止每条再套完整三问墙。
· 主要问题：只留支撑枢纽的 1～2 个筛点，与下一步一一对应。
'''

# 精炼自数学课标 mkb-feedback（指向育人的反馈微批）中跨学科可复用的通则；
# 非课标原文「必须这样写批语」，而是评价原则的推导性参考建议。
CURRICULUM_MICRO_FEEDBACK_BLOCK = '''
【课标导向·反馈微批参考建议】
（通则参考，各科可用；勿写成「课标原文规定必须这样批」。用语优先课标/教材教师通用语言。）
1) 反馈是素养证据的对话，含判分但不只是判分：把表现看成在哪一档、往哪走，优先用「追问问题/变式/小任务/牵引反思」引发下一次思考，可以不直接点明。
2) 维度多元：有页上证据时，除知识技能外尽量点到思想方法、活动经验、发现/提出问题中至少一面；无证据不臆测、不硬凑。
'''

LAYER_PROTOCOL = '''
【整篇解释分层（白话三问）】
整篇诊断必须用下面三个行首（界面就显示这三句，禁止再用「见」「关系」当标题）。
作业/试卷的单题 comment 仍然短评、不要写这三问；三问写在整篇 diagnosis.summary / evolution_narrative / open_material_overview。
作文/笔记的页评和整篇都可以写这三问：分点短句，不要糊成一面墙。

【看到了什么】页上可见事实（页码、原句、圈画）。没有就写材料未标明，禁止编人格结论。
凡写页号、题号或条目号，须同句带上该处内容或考查点的简要说明，禁止只抛编号让读者去翻卷。
【这说明什么】判断。可带短标签（最多 5 个），例如「现在处在」「育人上」「方法上」「错因」「文体」。
标签名≤12字，每个标签值≤24字。禁止九论全文、英文方法名、段落墙。
删掉环节名/方法词后，「看到了什么」+「下一步做什么」仍须独立读懂。
271 已勾选：四阶段是理解面之一，有依据就写（整体感知/探究建构/应用迁移/重构拓展），不够则「还不好判断」。
同时要自然带出其它面（真实目标/结构边界/筛分取舍/可做下一步），不要每条只剩同一句阶段口号，也不要为「去阶段」而硬删。
育人落点（好奇/合作/获得感/发现自我）写在整篇，逐页默认不写合作。
未勾 271：不要套四阶段/四落点。
【下一步做什么】学生接着能做的一小步，禁止「加强理解」「多练习」。

材料学段年级：只写材料设置、配置卡或文件名里出现过的；读不到写「材料未标明」，禁止推定。
''' + MENTOR_QUALITY_BLOCK + REPORT_DUTY_PROTOCOL + CURRICULUM_MICRO_FEEDBACK_BLOCK

QUESTION_COMMENT_GUARD = (
    '作业/试卷逐题 per_question_feedback.comment 仍不超过 50 字，直接指出问题和方向，不要写入上述三问行首。'
    '并可合理吸收课标反馈通则。'
)


def parse_layers(text: str) -> Dict[str, str]:
    raw = str(text or '')
    found = list(MARKER_RE.finditer(raw))
    out = {SEE: '', MEAN: '', NEXT: ''}
    if not found:
        return out
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(raw)
        key = m.group(1)
        if not out[key]:
            out[key] = raw[m.end():end].strip()
    return out


def has_layer_markers(text: str) -> bool:
    layers = parse_layers(text)
    return bool(layers[SEE] or layers[MEAN] or layers[NEXT])


def parse_mean_tags(text: str) -> List[Tuple[str, str]]:
    tags, _ = split_mean_tags(text)
    return tags


def split_mean_tags(text: str) -> Tuple[List[Tuple[str, str]], str]:
    raw = str(text or '').strip()
    if not raw:
        return [], ''
    found = list(INNER_TAG_RE.finditer(raw))
    if not found:
        return [], raw
    tags = []
    pieces = []
    last = 0
    for i, m in enumerate(found):
        if len(tags) >= 5:
            break
        pieces.append(raw[last:m.start()])
        end = found[i + 1].start() if i + 1 < len(found) else len(raw)
        name = m.group(1).strip()[:12]
        value = raw[m.end():end].strip()[:24]
        if name:
            tags.append((name, value))
        last = end
    pieces.append(raw[last:])
    leftover = re.sub(r'\s+', ' ', ''.join(pieces)).strip(' ；,，、。.\n')
    return tags, leftover


def _as_text(value: Any) -> str:
    if value is None or value is False:
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, (list, tuple)):
        return '；'.join(part for part in (_as_text(item) for item in value) if part)
    if isinstance(value, dict):
        return ''
    return str(value).strip()


def format_mean_section(mean: str) -> str:
    text = _as_text(mean)
    tags, leftover = split_mean_tags(text)
    if not tags:
        return text
    lines = [f'【{name}】{value}'.strip() for name, value in tags]
    if leftover:
        lines.append(leftover[:240])
    return '\n'.join(lines)


def format_layers(see: str = '', mean: str = '', nxt: str = '') -> str:
    see, mean, nxt = _as_text(see), _as_text(mean), _as_text(nxt)
    parts = []
    if see:
        parts.append(f'【{SEE}】{see}')
    if mean:
        parts.append(f'【{MEAN}】{format_mean_section(mean)}')
    if nxt:
        parts.append(f'【{NEXT}】{nxt}')
    return '\n'.join(parts)


def _first_layered(*chunks) -> str:
    seen = set()
    for chunk in chunks:
        if isinstance(chunk, list):
            text = '；'.join(str(x).strip() for x in chunk if x and str(x).strip())
        else:
            text = str(chunk or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        if has_layer_markers(text):
            return text
    return ''


def collect_explanation_text(report: Optional[Dict[str, Any]] = None,
                             ontology: Optional[Dict[str, Any]] = None) -> str:
    report = report or {}
    ontology = ontology or {}
    diagnosis = report.get('diagnosis') if isinstance(report.get('diagnosis'), dict) else {}
    overview = report.get('open_material_overview') if isinstance(report.get('open_material_overview'), dict) else {}
    layered = _first_layered(
        diagnosis.get('summary'),
        ontology.get('evolution_narrative'),
        format_layers(
            overview.get('subject_and_layout') or '',
            overview.get('content_review') or '',
            overview.get('next_steps') or '',
        ),
    )
    if layered:
        return layered
    chunks = [
        overview.get('subject_and_layout'),
        overview.get('content_review'),
        overview.get('next_steps'),
        diagnosis.get('cognitive_stage'),
        diagnosis.get('summary'),
        ontology.get('evolution_narrative'),
    ]
    for key in ('next_actions', 'zpd_recommendations'):
        val = diagnosis.get(key)
        if isinstance(val, list):
            chunks.extend(val)
        elif val:
            chunks.append(val)
    return '\n'.join(str(x).strip() for x in chunks if x and str(x).strip())


def _zone_cn(zone: str) -> str:
    return {
        'blind_spot': '盲区',
        'friction_zone': '内耗区',
        'zpd': '最近发展区',
        'uncertain': '待确认',
    }.get(str(zone or ''), str(zone or ''))


def _verdict_summary(memory: Optional[Dict[str, Any]]) -> str:
    if not isinstance(memory, dict):
        return ''
    dist = memory.get('verdict_distribution')
    counts = {'correct': 0, 'wrong': 0, 'partial': 0, 'blank': 0, 'uncertain': 0}
    if isinstance(dist, dict) and any(k in dist for k in counts):
        for key in counts:
            try:
                counts[key] = int(dist.get(key) or 0)
            except (TypeError, ValueError):
                counts[key] = 0
    else:
        for q in memory.get('questions') or []:
            v = str((q or {}).get('verdict') or '')
            if v in counts:
                counts[v] += 1
    parts = [f'{label}{counts[k]}'
             for k, label in (
                 ('correct', '对'), ('partial', '半对'), ('wrong', '错'),
                 ('blank', '未答'), ('uncertain', '不确定')) if counts[k]]
    return '；'.join(parts)


def _error_cause_summary(memory: Optional[Dict[str, Any]], limit: int = 4) -> str:
    if not isinstance(memory, dict):
        return ''
    dist = memory.get('error_type_distribution')
    items: List[Tuple[str, int]] = []
    if isinstance(dist, dict):
        for key, value in dist.items():
            name = str(key or '').strip()
            if not name or name in ('correct', 'none', '空', '无'):
                continue
            try:
                count = int(value or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                items.append((name, count))
    if not items:
        tallies: Dict[str, int] = {}
        for q in memory.get('questions') or []:
            name = str((q or {}).get('error_type') or '').strip()
            if not name:
                continue
            tallies[name] = tallies.get(name, 0) + 1
        items = list(tallies.items())
    items.sort(key=lambda pair: (-pair[1], pair[0]))
    if not items:
        return ''
    return '；'.join(f'{name}×{count}' for name, count in items[:limit])


def _short_clause(text: str, limit: int = 90) -> str:
    text = re.sub(r'\s+', ' ', _as_text(text))
    if has_layer_markers(text):
        layers = parse_layers(text)
        text = layers.get(MEAN) or layers.get(SEE) or text
        text = re.sub(r'\s+', ' ', text)
    return text[:limit].rstrip('；,，、。.')


def _zone_mentor_lines(ontology: Optional[Dict[str, Any]], *, per_bucket: int = 2) -> List[str]:
    """三区少而硬：每区最多 per_bucket 条，Markdown 短卡。"""
    zones = ((ontology or {}).get('zones') or {})
    lines = []
    total = 0
    hard_cap = 6
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        entries = zones.get(bucket) or []
        if not isinstance(entries, list):
            continue
        pieces = []
        for entry in entries:
            if not isinstance(entry, dict) or total >= hard_cap:
                break
            kp_raw = str(entry.get('knowledge_point') or '').strip()
            if kp_raw in ('', 'no_observed'):
                continue
            try:
                from .curriculum import humanize_knowledge_point, id_to_cn, strip_curriculum_codes
                subject = str((ontology or {}).get('subject') or '').strip() or 'chinese'
                kp = humanize_knowledge_point(subject, kp_raw) or id_to_cn(
                    subject, str(entry.get('curriculum_id') or '')
                ) or strip_curriculum_codes(
                    _short_clause(str(entry.get('rationale') or entry.get('comment') or ''), 24)
                ) or '要点'
                kp = strip_curriculum_codes(kp) or kp
                # 只禁止课标码露脸；[label, 认知, 领域] 与中文说明可保留
                if re.search(r'[A-Z]{2}_S\d+_\d+', kp):
                    kp = strip_curriculum_codes(kp) or '要点'
            except Exception:
                from .curriculum import strip_curriculum_codes as _strip_codes
                kp = _strip_codes(kp_raw) or (
                    kp_raw if not re.search(r'[A-Z]{2}_S\d+_\d+', kp_raw) else '要点'
                )
            see = ''
            qids = entry.get('evidence') or entry.get('evidence_question_ids') or []
            if isinstance(qids, list) and qids:
                see_parts = []
                for x in qids[:2]:
                    m = re.match(r'^p(\d+)[:：](.+)$', str(x), re.I)
                    see_parts.append(f'第{m.group(1)}页·题{m.group(2)}' if m else str(x))
                see = '、'.join(see_parts)
            rationale = _short_clause(str(entry.get('rationale') or entry.get('comment') or ''), 100)
            nxt = _short_clause(str(entry.get('suggested_next_step') or ''), 80)
            if not rationale and not nxt:
                continue
            block = [f'#### {kp}']
            if see:
                block.append(f'- 证据：{see}')
            if rationale:
                block.append(f'- 判断：{rationale}')
            if nxt:
                block.append(f'- 下一步：{nxt}')
            pieces.append('\n'.join(block))
            total += 1
            if len(pieces) >= per_bucket:
                break
        if pieces:
            lines.append(f'### {_zone_cn(bucket)}\n' + '\n\n'.join(pieces))
    return lines


def _skill_usage_block(skill_titles: Optional[List[str]], effect: Optional[Dict[str, Any]],
                       cross_essence: str = '') -> str:
    titles = [str(t).strip() for t in (skill_titles or []) if str(t).strip()]
    essence = _as_text(cross_essence)[:600]
    if not titles and not essence and not (isinstance(effect, dict) and effect.get('level')):
        return ''
    parts = ['## 本子方法如何改变了判断', '（禁止只报名；写因方法而改变的取舍）']
    if essence:
        parts.append(essence)
    elif titles:
        parts.append('本轮方法底托已注入；正文判断须看得出筛分取舍，不要复述包名清单。')
    if isinstance(effect, dict) and effect.get('level'):
        reason = str(effect.get('reason') or '').strip()
        line = f"作用档：{effect['level']}"
        if reason:
            line += '。' + reason[:240]
        parts.append(line)
    return '\n'.join(parts)


def _ctx_text(ctx: Optional[Dict[str, Any]], *keys) -> str:
    ctx = ctx or {}
    for key in keys:
        value = ctx.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in ('unknown', '未知', '未知学段', '未知年级'):
            return text
    return ''


def material_portrait_label(ctx: Optional[Dict[str, Any]] = None, filename: str = '') -> str:
    ctx = ctx or {}
    parts = []
    level = _ctx_text(ctx, 'education_level_name')
    grade = _ctx_text(ctx, 'grade_label')
    if ctx.get('grade_status') not in ('resolved', None, '') and not grade:
        grade = ''
    subject = _ctx_text(ctx, 'subject_name')
    kind = _ctx_text(ctx, 'material_name')
    stem = str(filename or '')
    if not level:
        if '小学' in stem:
            level = '小学'
        elif '初中' in stem:
            level = '初中'
        elif '高中' in stem:
            level = '高中'
    if not grade:
        m = GRADE_IN_NAME_RE.search(stem)
        if m:
            grade = m.group(0)
    if not subject:
        m = SUBJECT_IN_NAME_RE.search(stem)
        if m:
            subject = m.group(1)
    if not kind:
        m = KIND_IN_NAME_RE.search(stem)
        if m:
            kind = m.group(1)
    for item in (level, grade, subject, kind):
        if item and item not in parts:
            parts.append(item)
    return '【材料画像】' + (' · '.join(parts) if parts else '材料未标明')


def _fallback_layers(report: Optional[Dict[str, Any]], ontology: Optional[Dict[str, Any]]) -> Dict[str, str]:
    diagnosis = (report or {}).get('diagnosis') or {}
    overview = (report or {}).get('open_material_overview') or {}
    see = str(overview.get('subject_and_layout') or '').strip()
    mean = str(overview.get('content_review') or diagnosis.get('cognitive_stage') or '').strip()
    nxt = overview.get('next_steps') or diagnosis.get('next_actions') or diagnosis.get('zpd_recommendations')
    if isinstance(nxt, list):
        nxt = '；'.join(str(x) for x in nxt if x)
    nxt = str(nxt or '').strip()
    if not see:
        problems = diagnosis.get('main_problems') or diagnosis.get('strengths') or []
        if isinstance(problems, list):
            see = '；'.join(str(x) for x in problems[:3] if x)
        see = see or '材料未标明页上可核对事实，不能据此写人格结论。'
    if not mean:
        mean = '材料未标明，还不好判断所处环节。'
    if not nxt:
        nxt = '先回到页上已有原句，核对一处再往下一步。'
    return {SEE: see[:1200], MEAN: mean[:1200], NEXT: nxt[:800]}


def _md_three_q(see: str, mean: str, nxt: str) -> str:
    parts = []
    if see:
        parts.append(f'### {SEE}\n' + '\n'.join(f'- {line}' for line in _split_points(see)))
    if mean:
        parts.append(f'### {MEAN}\n' + '\n'.join(f'- {line}' for line in _split_points(mean)))
    if nxt:
        parts.append(f'### {NEXT}\n' + '\n'.join(f'- {line}' for line in _split_points(nxt)))
    return '\n\n'.join(parts)


def _split_points(text: str, limit: int = 5) -> List[str]:
    raw = _as_text(text)
    if not raw:
        return []
    chunks = re.split(r'(?:[；;]\s*|\n+|(?<=[。！？])\s*)', raw)
    out = []
    for c in chunks:
        c = c.strip(' ；;·•-')
        if c and c not in out:
            out.append(c[:160])
        if len(out) >= limit:
            break
    return out or [raw[:200]]


def _hub_sentence(mean: str, see: str = '') -> str:
    """从「这说明什么」抽一句枢纽；失败则回退短摘要。"""
    points = _split_points(mean, 3)
    for p in points:
        if any(k in p for k in ('成串', '自己', '真实目标', '差一步', '还停在', '整理')):
            return p[:80]
    if points:
        return points[0][:80]
    return _short_clause(see or mean, 60) or '材料未标明，枢纽判断待补。'


def build_diagnosis_card_body(
    *,
    filename: str,
    report: Optional[Dict[str, Any]] = None,
    ontology: Optional[Dict[str, Any]] = None,
    memory: Optional[Dict[str, Any]] = None,
    skill_titles: Optional[List[str]] = None,
    effect: Optional[Dict[str, Any]] = None,
    material_label: str = '',
    cross_essence: str = '',
) -> str:
    text = collect_explanation_text(report, ontology)
    layers = parse_layers(text)
    if not layers[SEE] and not layers[MEAN] and not layers[NEXT]:
        layers = _fallback_layers(report, ontology)
    portrait = _as_text(material_label) or material_portrait_label(None, filename)
    hub = _hub_sentence(layers[MEAN], layers[SEE])
    blocks = [
        f'# 批改·诊断\n\n**材料**：{filename}\n\n**枢纽**：{hub}',
        '## 白话三问\n\n' + _md_three_q(layers[SEE], layers[MEAN], layers[NEXT]),
    ]
    # 需加强核实：紧随三问后按 I / II / III 列出题号
    try:
        from .wgb_trust import build_user_verification_block, format_user_verification_markdown
        uv = None
        if isinstance(report, dict) and isinstance(report.get('user_verification'), dict):
            uv = report.get('user_verification')
        elif isinstance(ontology, dict) and ontology.get('wgb_trust'):
            from .wgb_trust import zones_for_verification
            uv = build_user_verification_block(
                ontology.get('wgb_trust'),
                zones_for_verification(ontology),
            )
        verify_md = format_user_verification_markdown(uv)
        if verify_md:
            blocks.append(verify_md)
    except Exception:
        pass
    zone_lines = _zone_mentor_lines(ontology, per_bucket=2)
    if zone_lines:
        blocks.append('## 认知三区\n\n' + '\n\n'.join(zone_lines))
    skill_block = _skill_usage_block(skill_titles, effect, cross_essence=cross_essence)
    if skill_block:
        blocks.append(skill_block)
    blocks.append(
        '## 边界\n\n'
        '- 未标明练习次数、书写人是否学生本人：保持未知，不据此推断进步或退步。\n'
        '- 无页上证据的人格结论一律不写。'
    )
    evidence = []
    if portrait:
        evidence.append(portrait.replace('【材料画像】', ''))
    verdict = _verdict_summary(memory)
    if verdict:
        evidence.append('对错：' + verdict)
    causes = _error_cause_summary(memory)
    if causes:
        evidence.append('高频错因：' + causes)
    if evidence:
        blocks.append('## 循证依据（后置）\n\n' + '\n'.join(f'- {e}' for e in evidence))
    return '\n\n'.join(p.strip() for p in blocks if p and str(p).strip())


def _excerpt_from_layers(prefix: str, text: str) -> str:
    layers = parse_layers(text)
    if not (layers[SEE] or layers[MEAN] or layers[NEXT]):
        return ''
    see = _short_clause(layers[SEE], 100)
    mean = _short_clause(layers[MEAN], 100)
    nxt = _short_clause(layers[NEXT], 80)
    lines = [f'### {prefix}']
    if see:
        lines.append(f'- **看到**：{see}')
    if mean:
        lines.append(f'- **说明**：{mean}')
    if nxt:
        lines.append(f'- **下一步**：{nxt}')
    return '\n'.join(lines)


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
    """解释精要卡：总览×白灰黑交叉统计 + 材料学情 + 整篇枢纽 + 逐页三步留存。"""
    from .excerpt_card_render import build_excerpt_card_body as _build
    return _build(
        report, ontology,
        limit=limit,
        pass1_dir=pass1_dir,
        subject=subject,
        assigned_pages=assigned_pages,
        filename=filename,
        material_type=material_type,
        feedback_context=feedback_context,
    )
