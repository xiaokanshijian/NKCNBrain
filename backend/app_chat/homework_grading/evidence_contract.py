"""必要复核与事实依据；纯函数不调用模型、不修改已有运行。"""
import copy
import re


def material_dependency(question):
    if question.get('note_role') in ('teaching_prompt', 'self_question', 'reading_prompt', 'source_excerpt'):
        return {'labels': [], 'indirect': False, 'count': None, 'required': False}
    text = ' '.join(str(question.get(k) or '') for k in ('stem_excerpt', 'parent_stem_excerpt'))
    labels = sorted(set(re.findall(r'材料\s*([一二三四五六七八九十\d]+)', text)))
    indirect = bool(re.search(r'(上述|以上|以下|下列|前述|这|两|二|三|四).{0,8}材料|结合材料|根据材料', text))
    count = re.search(r'([两二三四五六七八九十\d]+)\s*则?材料', text)
    raw = count.group(1) if count else ''
    number = int(raw) if raw.isdigit() else {'两': 2, '二': 2, '三': 3, '四': 4}.get(raw)
    return {'labels': labels, 'indirect': indirect, 'count': number, 'required': bool(labels or indirect)}


def material_groups(pages, max_pages):
    groups, blocked = [], set()
    for page, data in pages.items():
        for q in data.get('questions', []):
            dependency = material_dependency(q)
            if not dependency['required']:
                continue
            candidates = {page}
            for other, source in pages.items():
                for unit in source.get('questions', []):
                    text = ' '.join(str(unit.get(k) or '') for k in ('stem_excerpt', 'parent_stem_excerpt', 'student_answer'))
                    if ('材料' in text and (dependency['indirect'] or any(
                            re.search(r'材料\s*' + re.escape(label), text) for label in dependency['labels']))):
                        candidates.add(other)
            if len(candidates) > max_pages:
                blocked.add(page)
                candidates = {page}
            group = sorted(candidates)
            if group not in groups:
                groups.append(group)
    return groups, blocked


def combine_material_groups(dependencies, boundaries, max_pages):
    """材料来源不能覆盖原有作答续页；合并超限时保留明确阻断。"""
    merged = []
    pending = [set(group) for group in boundaries]
    for group in dependencies:
        connected = set(group)
        while any(connected & old for old in merged + pending):
            for collection in (merged, pending):
                for old in list(collection):
                    if connected & old:
                        connected.update(old)
                        collection.remove(old)
        merged.append(connected)
    groups, blocked = [sorted(group) for group in pending], set()
    for group in merged:
        if len(group) > max_pages:
            blocked.update(group)
            groups.extend([[page] for page in sorted(group)])
        else:
            groups.append(sorted(group))
    return groups, blocked


def valid_material_quotes(evidence, units, dependency):
    labels, refs = set(), set()
    for entry in evidence or []:
        if not isinstance(entry, dict) or entry.get('qid_global') not in units:
            return False
        _, source = units[entry['qid_global']]
        text = ' '.join(str(source.get(k) or '') for k in ('stem_excerpt', 'parent_stem_excerpt', 'student_answer'))
        quote = re.sub(r'\s+', '', str(entry.get('quote') or ''))
        if not quote or quote not in re.sub(r'\s+', '', text):
            return False
        entry_labels = set(re.findall(r'材料\s*([一二三四五六七八九十\d]+)', str(entry.get('material_label') or '')))
        if not entry_labels <= set(re.findall(r'材料\s*([一二三四五六七八九十\d]+)', text)):
            return False
        labels.update(entry_labels)
        refs.add(entry['qid_global'])
    if dependency['required'] and not refs:
        return False
    if dependency['labels'] and not set(dependency['labels']) <= labels:
        return False
    return not dependency['count'] or max(len(labels), len(refs)) >= dependency['count']


def required_review_units(page):
    result = []
    for q in page.get('questions') or []:
        if not isinstance(q, dict) or not q.get('id'):
            continue
        if q.get('note_role') in ('teaching_prompt', 'self_question', 'reading_prompt', 'source_excerpt'):
            continue
        reasons = []
        verdict = q.get('verdict')
        if verdict in ('wrong', 'uncertain'):
            reasons.append('judgment')
        if verdict == 'partial' and (q.get('error_type') or q.get('assessment_status') not in ('observation', 'not_assessed')):
            reasons.append('partial_judgment')
        text = ' '.join(str(q.get(k) or '') for k in ('understanding', 'error_type', 'recognition_note'))
        if re.search(r'模糊|难辨|无法辨认|来源冲突|识别不确定', text):
            reasons.append('uncertain_evidence')
        check = q.get('material_check') or {}
        if check.get('blocks_assessment') or (material_dependency(q)['required'] and check.get('status') not in ('resolved', 'not_required')):
            reasons.append('material_dependency')
        if reasons:
            result.append({'qid_global': 'p{}:{}'.format(page.get('page', 0), q['id']), 'reasons': reasons})
    return result


def unit_coverage(required, details):
    by_page = {item.get('page'): item for item in details}
    result = []
    for unit in required:
        item = by_page.get(int(unit['qid_global'].split(':')[0][1:]), {})
        status = ('failed' if item.get('error') else 'quota_skipped' if item.get('quota_limited') or item.get('skip_reason') == 'gemini_quota_limited'
                  else 'not_reviewed' if not item or item.get('skipped') else 'completed')
        result.append(dict(unit, status=status))
    return result


def semantic_facts(pages):
    """保留所有单元的语义依据，排除审计时间、消费者标记等非事实字段。"""
    fields = ('id', 'stem_excerpt', 'parent_stem_excerpt', 'student_answer', 'verdict',
              'correct_answer', 'assessment_status', 'understanding', 'error_type',
              'note_role', 'material_check', 'supporting_qids', 'cross_page',
              'cross_page_resolved', 'position', 'requirements')
    return [{'page': p['page'], 'page_origin': p.get('page_origin'),
             'questions': [{k: copy.deepcopy(q.get(k)) for k in fields} for q in p.get('questions', [])]}
            for p in sorted(pages, key=lambda p: p['page'])]


_NOTE_OBSERVATION_ROLES = (
    'teaching_prompt', 'self_question', 'reading_prompt', 'source_excerpt', 'annotation', 'note',
)


def validate_final_evidence(report, ontology, pages, coverage, reviewed_pages=None):
    """确定诊断只能引用存在且没有材料阻断的单元；必要复核缺项由完成摘要阻断。"""
    units = {'p{}:{}'.format(p['page'], q['id']): q for p in pages for q in p.get('questions', []) if q.get('id')}
    coverage_status = {u['qid_global']: u.get('status') for u in coverage if isinstance(u, dict) and u.get('qid_global')}
    incomplete = {qid for qid, status in coverage_status.items() if status not in ('completed', 'quota_skipped')}
    def material_blocked(unit):
        check = unit.get('material_check') or {}
        return check.get('blocks_assessment') or (material_dependency(unit)['required'] and
                                                check.get('status') not in ('resolved', 'not_required'))
    from .semantic_checks import phrase_findings
    for item in report.get('per_question_feedback', []):
        ref = item.get('qid_global') or 'p{}:{}'.format(item.get('page'), item.get('id'))
        if ref not in units:
            raise ValueError('批语引用了不存在的题目：' + ref)
        unit = units[ref]
        # 笔记观察单元、以及策略免检页：掌握类断言由 note_evidence 约束，不按作业卷「必须已复核」打断整份终态。
        if unit.get('note_role') in _NOTE_OBSERVATION_ROLES or coverage_status.get(ref) == 'quota_skipped':
            continue
        text = str(item.get('comment') or '')
        negative = any(f['kind'] == 'assertion' for f in phrase_findings(text, r'不会|未掌握|答错|漏答|不正确'))
        if negative and (ref in incomplete or material_blocked(unit)
                         or (reviewed_pages is not None and int(ref.split(':')[0][1:]) not in reviewed_pages)):
            raise ValueError('批语中的负面结论尚无已复核证据：' + ref)
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('evidence', 'evidence_refs', 'supporting_qids') and isinstance(child, list):
                    for ref in child:
                        if not isinstance(ref, str) or not re.fullmatch(r'p\d+:.+', ref):
                            continue
                        if ref not in units:
                            raise ValueError('最终诊断引用了不存在的题目：' + ref)
                        if key != 'supporting_qids' and (ref in incomplete or material_blocked(units[ref])):
                            raise ValueError('最终诊断引用的证据尚未核验：' + ref)
                if key not in ('audit', 'content_validation'):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(ontology.get('zones', {}))
    walk(report.get('zone_classification', {}))
