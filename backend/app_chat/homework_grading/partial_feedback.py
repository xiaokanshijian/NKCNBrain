"""无法修复的单元隔离为待复核；保留已验证内容和完整错误审计。"""
import copy

from .validation_issues import ValidationIssues

_PLACEHOLDER_OVERVIEW = {
    'subject_and_layout': '材料已完成识别，部分反馈仍待复核。',
    'content_review': '请区分已核实的逐项反馈与标为待复核的内容。',
    'next_steps': ['先核实待复核内容，再采用相关建议。'],
}
_REVIEW_NOTICE = '部分逐条批语未通过核验，采用前请对照待复核项。'


def partial_ontology(previous, error, validate):
    if not isinstance(error, ValidationIssues) or not isinstance(previous.get('zones'), dict):
        return None
    candidate = copy.deepcopy(previous)
    paths = {x['path'] for x in error.issues}
    kept = 0
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        entries = candidate['zones'].get(bucket)
        if not isinstance(entries, list):
            entries = []
        accepted = []
        for index, entry in enumerate(entries):
            path = f'/zones/{bucket}/{index}'
            if any(path == p or path.startswith(p + '/') or p.startswith(path + '/') for p in paths):
                continue
            accepted.append(entry)
            kept += int(entry.get('knowledge_point') != 'no_observed' and bool(entry.get('evidence')))
        candidate['zones'][bucket] = accepted
    if not kept:
        return None
    candidate['mastery_trajectory'] = []
    candidate['evolution_narrative'] = '部分诊断未通过核验；以下仅展示已核实的观察，其余内容待复核。'
    candidate['status'] = 'needs_review'
    candidate['content_validation'] = {'status': 'needs_review', 'issues': copy.deepcopy(error.issues)}
    validate(candidate)
    return candidate


def partial_feedback(previous, error, memory, validate_item):
    if not isinstance(error, ValidationIssues):
        return None
    values = previous.get('per_question_feedback')
    if not isinstance(values, list):
        return None
    grouped = {}
    for item in values:
        if isinstance(item, dict) and isinstance(item.get('qid_global'), str):
            grouped.setdefault(item['qid_global'], []).append(item)
    accepted, kept = [], 0
    for question in memory.get('error_questions', []):
        qid = question['qid_global']
        matches = grouped.get(qid, [])
        try:
            if len(matches) != 1:
                raise ValueError('批语缺失或重复')
            item = copy.deepcopy(matches[0])
            validate_item(item, question)
        except ValueError:
            item = {'qid_global': qid, 'id': question['id'], 'page': question['page'], 'zone': '',
                    'comment': '此单元的反馈尚未通过核验，暂不作评价。', 'feedback_status': 'needs_review'}
        else:
            kept += 1
        accepted.append(item)
    if not kept:
        return None
    candidate = copy.deepcopy(previous)
    candidate['per_question_feedback'] = accepted
    if 'open_material_overview' in candidate:
        overview = candidate.get('open_material_overview')
        if isinstance(overview, dict) and str(overview.get('subject_and_layout') or '').strip() and str(
                overview.get('content_review') or '').strip() and overview.get('subject_and_layout') != _PLACEHOLDER_OVERVIEW['subject_and_layout']:
            steps = [str(x).strip() for x in (overview.get('next_steps') or []) if str(x).strip()]
            if _REVIEW_NOTICE not in steps:
                steps.append(_REVIEW_NOTICE)
            candidate['open_material_overview'] = dict(overview, next_steps=steps[:4])
        else:
            candidate['open_material_overview'] = copy.deepcopy(_PLACEHOLDER_OVERVIEW)
    candidate['content_validation'] = {'status': 'needs_review', 'issues': copy.deepcopy(error.issues)}
    return candidate
