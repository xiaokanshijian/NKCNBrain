"""逐页前言：事实来自冻结材料信息，摘要与最终逐页证据绑定。"""
import hashlib
import json
import re


PAGE_FEEDBACK_PROTOCOL = '''另外输出 page_feedback_contexts 数组，每页一项（含全对页和空白页）：
page（PDF序号）、unit_kind（unit/topic/unconfirmed）、unit_title、unit_evidence_quote、
understanding_summary（1—2句中文）、evidence_qids（本页真实全局题号数组）。
依据 page_understanding 的全部单元总结，不只总结错题。教学单元必须有原页标题摘录；
只识别内容主题时用topic，不能确认时用unconfirmed且标题与摘录留空。
区分印刷正文、作答、笔记、颜色事实和推测意图；局部难辨只说明局部限制。
不输出或猜测年级学段，不根据页序推断进退步，不把待确认、未作答的教材提示判成不会。
空白页写“本页未提取到可供概述的内容”，引用为空。'''

UNIT_FIELDS = ('stem_excerpt', 'student_answer', 'understanding', 'verdict', 'assessment_status',
               'note_role', 'printed_text_marked', 'handwritten_text_marked', 'annotation_links',
               'material_check', 'diagnostic_eligible')


def page_evidence(page_data, page_num):
    units = []
    for q in page_data.get('questions') or []:
        units.append({'qid_global': f"p{page_num}:{q.get('id')}",
                      **{k: q[k] for k in UNIT_FIELDS if k in q}})
    return {'page': int(page_num), 'units': units}


def evidence_fingerprint(page):
    return hashlib.sha256(json.dumps(page, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _text(value):
    return value.strip() if isinstance(value, str) else ''


def _brief(text):
    sentences = [s.strip() for s in re.split(r'(?<=[。！？])\s*', text) if s.strip()]
    return ''.join(sentences[:2])[:300]


def fallback_context(page, reason):
    units = page.get('units') or []
    # 保守摘录最终理解，不从缺失信息推断能力，也不自行补出教学单元。
    excerpts = [_text(q.get('understanding')) or _text(q.get('stem_excerpt')) for q in units]
    excerpts = list(dict.fromkeys(x for x in excerpts if x))[:2]
    summary = _brief('本页内容摘录：' + '；'.join(x[:120] for x in excerpts) + '。') if excerpts else (
        '本页未提取到可供概述的内容。' if not units else '本页已有识别单元，理解摘要暂不可用。')
    return {'page': page['page'], 'unit_kind': 'unconfirmed', 'unit_title': '',
            'unit_evidence_quote': '', 'understanding_summary': summary,
            'evidence_qids': [q['qid_global'] for q in units], 'status': 'fallback',
            'warning': reason, 'source_fingerprint': evidence_fingerprint(page)}


def normalize_page_contexts(items, pages):
    """缺失/重复/异页证据/复核改写均逐页降级，不阻断有效批语。"""
    items = items if isinstance(items, list) else []
    result = []
    for page in pages:
        matches = [x for x in items if isinstance(x, dict) and type(x.get('page')) is int
                   and x['page'] == page['page']]
        reason = ''
        item = matches[0] if len(matches) == 1 else {}
        qids = {q['qid_global'] for q in page.get('units') or []}
        refs = item.get('evidence_qids')
        summary = _text(item.get('understanding_summary'))
        if len(matches) != 1:
            reason = '本页摘要缺失或重复，采用最终理解摘录。'
        elif item.get('source_fingerprint') and item['source_fingerprint'] != evidence_fingerprint(page):
            reason = '复核已更新本页依据，原摘要失效，采用最终理解摘录。'
        elif (not isinstance(refs, list) or any(not isinstance(q, str) or q not in qids for q in refs)
              or (qids and not refs) or not summary or len(summary) > 600):
            reason = '本页摘要或引用无效，采用最终理解摘录。'
        if reason:
            result.append(fallback_context(page, reason))
            continue
        kind = item.get('unit_kind')
        title, quote = _text(item.get('unit_title')), _text(item.get('unit_evidence_quote'))
        source_text = '\n'.join(_text(q.get(k)) for q in page.get('units') or []
                                for k in ('stem_excerpt', 'student_answer'))
        warning = _text(item.get('warning'))
        if kind not in ('unit', 'topic') or not title or not quote or quote not in source_text or title not in quote:
            if title:
                warning = '教学单元缺少可核实的原页摘录，未展示推测标题。'
            kind, title, quote = 'unconfirmed', '', ''
        result.append({'page': page['page'], 'unit_kind': kind, 'unit_title': title,
                       'unit_evidence_quote': quote, 'understanding_summary': _brief(summary),
                       'evidence_qids': list(dict.fromkeys(refs)),
                       'source_fingerprint': evidence_fingerprint(page),
                       'status': item.get('status', 'ready'), 'warning': warning})
    return result


def display_context(page, report, context=None, manifest=None):
    context, manifest = context or {}, manifest or {}
    attrs = manifest.get('homework_attributes') or {}
    level = context.get('education_level_name') or {
        'primary': '小学', 'junior': '初中', 'senior': '高中',
    }.get(attrs.get('homework_stage'), '学段未确认')
    grade = context.get('grade_label') if context.get('grade_status') == 'resolved' else ''
    if not context and attrs.get('homework_grade'):
        grade = f"{attrs['homework_grade']}年级"
    item = next((x for x in report.get('page_feedback_contexts', [])
                 if isinstance(x, dict) and x.get('page') == page), {})
    return {**item, 'education_level_label': level, 'grade_label': grade or '年级未确认',
            'subject_label': context.get('subject_name') or manifest.get('subject_label') or '学科未确认',
            'unit_label': ('教学单元：' if item.get('unit_kind') == 'unit' else '本页主题：') + item['unit_title']
                if item.get('unit_title') else '教学单元未确认',
            'understanding_summary': item.get('understanding_summary') or '本版本未生成逐页理解摘要'}
