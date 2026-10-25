"""笔记的来源、观察状态与诊断证据协议；不依赖特定样例或题号。"""
import copy
import re


NOTE_ROLES = {'written_answer', 'note', 'annotation', 'teaching_prompt',
              'self_question', 'reading_prompt', 'source_excerpt', 'unknown'}
NON_ASSESSED_ROLES = {'teaching_prompt', 'self_question', 'reading_prompt', 'source_excerpt'}
NOTE_FIELDS = ('note_role', 'annotation_links', 'assessment_status', 'diagnostic_eligible',
               'material_check', 'assessment_reason')

# 只豁免同一分句中直接否定该断言的措辞；不能用前句的“不能推断”放行后句的误诊。
from .semantic_checks import phrase_findings, evaluation_texts
from .validation_issues import TextConstraintError, ValidationIssues, issue, raise_issues


def _has_asserted_phrase(text, pattern):
    return bool(phrase_findings(text, pattern))


def _check_text(text, pattern, message):
    findings = phrase_findings(text, pattern)
    if findings:
        raise TextConstraintError(message, findings)


def is_notes(runtime):
    return runtime is not None and runtime.context.get('material_type') == 'notes'


def normalize_note_fields(question):
    from .material_markings import normalize_markings
    normalize_markings(question)
    role = question.get('note_role', 'unknown')
    question['note_role'] = role if role in NOTE_ROLES else 'unknown'
    links = question.get('annotation_links')
    question['annotation_links'] = [
        {key: str(item.get(key) or '').strip() for key in ('marked_text', 'annotation_text', 'relation')}
        for item in (links if isinstance(links, list) else []) if isinstance(item, dict)
    ][:20]
    check = question.get('material_check')
    question['material_check'] = check if isinstance(check, dict) else {}
    status = 'observed'
    if question['note_role'] in NON_ASSESSED_ROLES:
        status = 'not_assessed'
    elif (not str(question.get('student_answer') or '').strip()
          or question.get('verdict') not in ('correct', 'partial', 'wrong')):
        status = 'unconfirmed'
    elif (question['note_role'] in ('written_answer', 'unknown') and question.get('cross_page')
          and not question.get('cross_page_resolved')):
        status = 'unconfirmed'
    if status == 'observed' and question['material_check'].get('blocks_assessment'):
        status = 'unconfirmed'
    question['assessment_status'] = status
    question['diagnostic_eligible'] = status == 'observed'
    question['assessment_reason'] = '' if status == 'observed' else (
        question['material_check'].get('reason') or question.get('assessment_reason')
        or ('此单元为提示、自问或原文材料，不作为必答题。' if status == 'not_assessed'
            else question.get('cross_page_note') or '当前转写或作答依据尚不足，保留观察。'))
    if status == 'observed' and question.get('verdict') == 'correct' and question.get('error_type'):
        question.setdefault('note_assessment_audit', []).append({
            'reason': '当前判断为正确，清理不再成立的错因。', 'error_type': question['error_type'],
        })
        question['error_type'] = ''
    if status != 'observed':
        if question.get('verdict') in ('correct', 'partial', 'wrong'):
            question.setdefault('note_assessment_audit', []).append({
                'reason': question['assessment_reason'], 'verdict': question['verdict'], 'after_verdict': 'uncertain'})
            question['verdict'] = 'uncertain'
        previous_answer = question.get('correct_answer')
        if question.get('correct_answer') or question.get('error_type'):
            question.setdefault('note_assessment_audit', []).append({
                'reason': question['assessment_reason'],
                'correct_answer': question.get('correct_answer'),
                'error_type': question.get('error_type'),
            })
        question['correct_answer'] = None
        question['error_type'] = ''
        if (isinstance(previous_answer, str) and len(previous_answer.strip()) >= 6
                and previous_answer.strip() in str(question.get('understanding') or '')):
            question['understanding'] = ('可见书写：' + str(question.get('student_answer') or '')
                                         + '；' + question['assessment_reason'])
    question['recurrence_hint'] = 'na'
    return question


def reconcile_note_review(question, before, fix, reason):
    """复核改字后，旧评价不能作为新转写的默认结论。"""
    changed_text = question.get('student_answer') != before.get('student_answer')
    if changed_text:
        complete = (fix.get('verdict') in ('correct', 'partial', 'wrong')
                    and 'correct_answer' in fix and 'error_type' in fix
                    and bool(str(reason or '').strip())
                    and (fix['verdict'] == 'correct' or bool(str(fix['error_type'] or '').strip()))
                    and not question.get('self_review', {}).get('verdict_fix_blocked'))
        if not complete:
            question.update(verdict='uncertain', correct_answer=None, error_type='',
                            assessment_reason='转写已修正，复核未同时确认评价依据。')
            question['understanding'] = '已核对的书写：' + str(question.get('student_answer') or '') + '；评价待确认。'
        else:
            question['understanding'] = str(reason).strip()
    if question.get('verdict') == 'correct':
        question['error_type'] = ''
    normalize_note_fields(question)
    after = {key: question.get(key) for key in before}
    if after != before:
        question.setdefault('self_review', {})['assessment_reconciliation'] = {
            'before': before, 'after': after, 'reason': reason or question['assessment_reason'],
        }


def normalize_note_dir(pass1_dir, *, feedback_runtime, page_nums=None):
    """仅在计算链路中同步落盘；历史查看不调用此函数。"""
    from .utils import safe_json_load, safe_json_dump, sorted_json_pages
    from .feedback_runtime import stamp_feedback
    for path in sorted_json_pages(pass1_dir):
        data = safe_json_load(path)
        if page_nums is not None and data.get('page') not in page_nums:
            continue
        for question in data.get('questions') or []:
            normalize_note_fields(question)
        safe_json_dump(path, stamp_feedback(data, feedback_runtime, 'note_evidence'))


def normalize_page_origin(value):
    value = value if isinstance(value, dict) else {}
    number = value.get('printed_page_number')
    return {
        'source_kind': value.get('source_kind') if value.get('source_kind') in
                       ('workbook', 'textbook', 'handwritten') else 'unknown',
        'source_title': str(value.get('source_title') or '').strip()[:200],
        'printed_page_number': number if type(number) is int and number > 0 else None,
    }


def note_units(memory):
    return [normalize_note_fields(copy.deepcopy(q)) for q in memory.get('error_questions', [])]


def _validate_annotation_context(item, by_id):
    """辅助内容只补充同页标注的上下文，不获得内容判分资格。"""
    refs = item.get('content_context_evidence') or []
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise ValueError('标注辅助内容必须为题号数组')
    if not refs:
        return
    if item.get('evidence_basis') != 'annotation' or not item.get('evidence'):
        raise ValueError('辅助内容必须依附于真实标注证据')
    from .material_markings import observation_eligible
    anchors = item['evidence']
    if any(ref not in by_id or not observation_eligible(by_id[ref]) for ref in anchors):
        raise ValueError('辅助内容缺少有效的主要标注证据')
    pages = {ref.split(':', 1)[0] for ref in anchors}
    for ref in refs:
        if ref not in by_id or not by_id[ref].get('diagnostic_eligible'):
            raise ValueError('标注辅助内容引用待确认或非作答证据：' + ref)
        if ref in anchors or ref.split(':', 1)[0] not in pages:
            raise ValueError('标注辅助内容必须是同页的独立已确认单元：' + ref)


def _normalize_annotation_context_item(ontology, units):
    """将混合引用中的已确认回答明确记为背景，不更改原单元资格或诊断正文。"""
    from .material_markings import observation_eligible
    by_id = {q['qid_global']: q for q in units if q.get('qid_global')}
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        for index, item in enumerate((ontology.get('zones') or {}).get(bucket) or []):
            if not isinstance(item, dict) or item.get('evidence_basis') != 'annotation':
                continue
            refs = item.get('evidence')
            if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                raise ValueError('标注观察证据必须为题号数组')
            anchors = [ref for ref in refs if ref in by_id and observation_eligible(by_id[ref])]
            contexts = [ref for ref in refs if ref not in anchors]
            if not contexts:
                continue
            if not anchors:
                raise ValueError('标注观察缺少主要标注证据；已确认回答应使用content类型')
            candidate = copy.deepcopy(item)
            previous_context = candidate.get('content_context_evidence') or []
            if not isinstance(previous_context, list) or any(not isinstance(ref, str) for ref in previous_context):
                raise ValueError('标注辅助内容必须为题号数组')
            candidate['evidence'] = list(dict.fromkeys(anchors))
            candidate['content_context_evidence'] = list(dict.fromkeys(previous_context + contexts))
            _validate_annotation_context(candidate, by_id)
            item.update(evidence=candidate['evidence'], content_context_evidence=candidate['content_context_evidence'])
            ontology.setdefault('_annotation_context_normalizations', []).append({
                'zone': bucket, 'index': index, 'original_evidence': refs,
                'evidence': list(item['evidence']), 'content_context_evidence': list(item['content_context_evidence']),
                'reason': '保留主要标注，并将同页已确认回答记录为辅助内容；单元评价状态与诊断正文未改变。'})


def normalize_annotation_context(ontology, units):
    issues = []
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        for index, entry in enumerate((ontology.get('zones') or {}).get(bucket) or []):
            single = {'zones': {bucket: [entry]}}
            try:
                _normalize_annotation_context_item(single, units)
            except ValueError as exc:
                issues.append(issue(exc, f'/zones/{bucket}/{index}'))
            for audit in single.get('_annotation_context_normalizations', []):
                audit['index'] = index
                if audit not in ontology.setdefault('_annotation_context_normalizations', []):
                    ontology['_annotation_context_normalizations'].append(audit)
    raise_issues(issues)


def _validate_note_ontology_item(ontology, units):
    """缺证据的诊断进入现有重试/失败路径，不把模型的错误文字静默留下。"""
    if not isinstance(ontology, dict) or not isinstance(ontology.get('zones'), dict):
        raise ValueError('笔记诊断必须包含zones对象')
    by_id = {q['qid_global']: q for q in units if q.get('qid_global')}
    if ontology.get('mastery_trajectory'):
        raise ValueError('笔记没有练习时间依据，mastery_trajectory必须为空')
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        entries = ontology['zones'].get(bucket)
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise ValueError('笔记诊断三区必须为对象数组')
        for item in entries:
            basis = item.get('evidence_basis', 'content')
            if basis not in ('content', 'annotation'):
                raise ValueError('分区依据类型无效')
            refs = list(item.get('evidence') or [])
            for cluster in item.get('error_clusters') or []:
                refs.extend(cluster.get('evidence') or [])
            if item.get('knowledge_point') == 'no_observed':
                if refs or item.get('content_context_evidence'):
                    raise ValueError('无观察项不能引用题号')
                continue
            _validate_annotation_context(item, by_id)
            if not refs:
                raise ValueError('笔记诊断缺少可定位证据')
            for ref in refs:
                q = by_id.get(ref)
                from .material_markings import observation_eligible
                eligible = q and (observation_eligible(q) if basis == 'annotation' else q.get('diagnostic_eligible'))
                if not eligible:
                    if q and basis == 'annotation' and q.get('diagnostic_eligible'):
                        raise ValueError('已确认内容不能作为主要标注证据：' + str(ref) + '；请使用content或同页标注辅助内容')
                    raise ValueError('笔记诊断引用待确认或非作答证据：' + str(ref))
                if ('evidence_basis' not in item and bucket in ('blind_spot', 'friction_zone')
                        and q.get('verdict') not in ('wrong', 'partial')):
                    raise ValueError('错误区域引用了正确内容：' + str(ref))
            if basis == 'annotation':
                if item.get('error_clusters'):
                    raise ValueError('标注观察不能生成作答错误簇')
                for key in ('rationale', 'suggested_next_step'):
                    _check_text(str(item.get(key) or ''),
                        r'未掌握|已掌握|已经掌握|完全掌握|不会|未得分|失分|必须补答|要点不全|概念未建立',
                        '标注观察不能代替内容评价')
            if any(item.get(key) is not None for key in ('trend', 'stability', 'first_session', 'last_session')):
                raise ValueError('笔记区域不得生成时序趋势或跨次稳定性')
    validate_note_temporal_text(ontology)


def validate_note_ontology(ontology, units):
    if not isinstance(ontology, dict) or not isinstance(ontology.get('zones'), dict):
        raise ValidationIssues([issue(ValueError('笔记诊断必须包含zones对象'), '/')])
    issues = []
    if ontology.get('mastery_trajectory'):
        issues.append(issue(ValueError('笔记没有练习时间依据，mastery_trajectory必须为空'), '/mastery_trajectory'))
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        entries = ontology['zones'].get(bucket)
        if not isinstance(entries, list):
            issues.append(issue(ValueError('笔记诊断三区必须为对象数组'), '/zones/' + bucket))
            continue
        for index, entry in enumerate(entries):
            single = {'zones': {key: [] for key in ('blind_spot', 'friction_zone', 'zpd')}}
            single['zones'][bucket] = [entry]
            try:
                _validate_note_ontology_item(single, units)
            except ValueError as exc:
                issues.append(issue(exc, f'/zones/{bucket}/{index}'))
    try:
        validate_note_temporal_text({key: value for key, value in ontology.items() if key != 'zones'})
    except ValidationIssues as exc:
        issues.extend(exc.issues)
    raise_issues(issues)


def validate_note_temporal_text(value):
    issues = []
    for path, text in evaluation_texts(value):
        try:
            _check_text(text, r'第[一二三四五六七八九十\d]+次练习|由错转对|进步明显|明显进步|均未得分|整页正确率',
                        '笔记反馈将页序或待确认状态解释为成绩／学习变化')
        except TextConstraintError as exc:
            issues.append(issue(exc, path or '/', code='unsupported_temporal_claim'))
    raise_issues(issues)


def normalize_feedback_zones(payload, ontology):
    """兼容模型把多个有据分区写进单值字段；不扩充诊断证据或删除无据分区。"""
    buckets = ('blind_spot', 'friction_zone', 'zpd')
    memberships = {}
    for bucket in buckets:
        for entry in (ontology.get('zones') or {}).get(bucket) or []:
            refs = list(entry.get('evidence') or []) + list(entry.get('content_context_evidence') or [])
            for cluster in entry.get('error_clusters') or []:
                refs.extend(cluster.get('evidence') or [])
            for ref in refs:
                memberships.setdefault(ref, set()).add(bucket)
    for item in payload.get('per_question_feedback') or []:
        raw = item.get('zone')
        if raw is None or raw == '':
            continue
        qid = item.get('qid_global')
        if isinstance(raw, str):
            candidates = re.split(r'[,，、;；/|]', raw)
        elif isinstance(raw, list):
            candidates = raw
        else:
            raise ValueError('批语分区必须为有效分区名称：' + str(qid))
        if (not candidates or any(not isinstance(value, str) or not value.strip() for value in candidates)):
            raise ValueError('批语分区含空值或无效名称：' + str(qid))
        candidates = list(dict.fromkeys(value.strip() for value in candidates))
        allowed = memberships.get(qid, set())
        if any(value not in buckets or value not in allowed for value in candidates):
            raise ValueError('批语分区与诊断证据不一致：' + str(qid))
        # API和题框沿用单值zone；完整多维结论仍在ontology和zone_classification中。
        selected = candidates[0]
        if raw != selected:
            audit = {'qid_global': qid, 'original_zone': copy.deepcopy(raw), 'zone': selected,
                     'supported_zones': [bucket for bucket in buckets if bucket in allowed],
                     'reason': '多个分区均有本单元证据，按返回顺序保留首个作为单值展示；完整三区结论保留。'}
            records = payload.setdefault('_zone_normalizations', [])
            if audit not in records:
                records.append(audit)
            item['zone'] = selected


def _validate_note_feedback_item(payload, memory, ontology, *, material_type='notes'):
    validate_note_temporal_text(payload)
    from .material_markings import open_units
    units = {q['qid_global']: q for q in open_units(memory, material_type) if q.get('qid_global')}
    zones = {}
    annotation_refs, content_refs = set(), set()
    context_by_zone = {}
    for bucket, entries in (ontology.get('zones') or {}).items():
        for entry in entries:
            context_by_zone.setdefault(bucket, set()).update(entry.get('content_context_evidence') or [])
            refs = list(entry.get('evidence') or []) + list(entry.get('content_context_evidence') or [])
            for cluster in entry.get('error_clusters') or []:
                refs.extend(cluster.get('evidence') or [])
            for ref in refs:
                zones.setdefault(ref, set()).add(bucket)
                (annotation_refs if entry.get('evidence_basis') == 'annotation' else content_refs).add(ref)
    for item in payload.get('per_question_feedback') or []:
        qid = item.get('qid_global')
        q = units.get(qid)
        if not q:
            raise ValueError('笔记批语引用未知单元')
        zone = item.get('zone') or ''
        if zone and zone not in zones.get(qid, set()):
            raise ValueError('笔记批语分区与证据不一致：' + qid)
        comment = str(item.get('comment') or '')
        if re.search(r'未(?:列入|纳入|进入).*三区|未列入.*区域', comment):
            _check_text(comment, r'(?:需要|必须|应当|请|建议)(?:再|重新)?(?:人工)?(?:补写|补答|复核)|信息不足',
                        '不得以未进入三区为由要求补写或复核')
        if not q['diagnostic_eligible']:
            _check_text(comment, r'未掌握|不会|未得分|失分|盲区|必须补答|要点不全',
                        '待确认或非作答单元不能生成确定的能力缺陷：' + qid)
        if qid in annotation_refs and qid not in content_refs:
            _check_text(comment, r'未掌握|已掌握|已经掌握|完全掌握|不会|未得分|失分|必须补答|要点不全|概念未建立',
                        '标注观察批语不能推定内容掌握：' + qid)
    # 最终报告的三区同样须符合当前证据，后处理不得加回不确定题的盲区。
    if 'zone_classification' in payload:
        for bucket in ('blind_spot', 'friction_zone', 'zpd'):
            for entry in payload['zone_classification'].get(bucket, []):
                for ref in entry.get('content_context_evidence') or []:
                    if ref not in context_by_zone.get(bucket, set()):
                        raise ValueError('标注辅助内容与诊断证据不一致：' + ref)
                for ref in entry.get('evidence_question_ids') or []:
                    if bucket not in zones.get(ref, set()):
                        raise ValueError('笔记报告三区与诊断证据不一致：' + ref)


def validate_note_feedback(payload, memory, ontology, *, material_type='notes'):
    issues = []
    for index, item in enumerate(payload.get('per_question_feedback') or []):
        try:
            _validate_note_feedback_item({'per_question_feedback': [item]}, memory, ontology, material_type=material_type)
        except ValueError as exc:
            issues.append(issue(exc, f'/per_question_feedback/{index}', qid=item.get('qid_global')))
    for bucket, entries in (payload.get('zone_classification') or {}).items():
        for index, entry in enumerate(entries):
            try:
                _validate_note_feedback_item({'zone_classification': {bucket: [entry]}}, memory, ontology, material_type=material_type)
            except ValueError as exc:
                issues.append(issue(exc, f'/zone_classification/{bucket}/{index}'))
    try:
        validate_note_temporal_text({key: value for key, value in payload.items()
                                    if key not in ('per_question_feedback', 'zone_classification')})
    except ValidationIssues as exc:
        issues.extend(exc.issues)
    raise_issues(issues)


def align_note_report(report):
    """一个报告只保留同一组优先建议，逐单元仍保留具体观察。"""
    overview = report.get('open_material_overview') or {}
    steps = overview.get('next_steps') if isinstance(overview, dict) else None
    if not isinstance(steps, list) or not steps:
        return
    placeholder = '先核实待复核内容，再采用相关建议。'
    if steps == [placeholder] or (len(steps) == 1 and placeholder in str(steps[0])):
        return
    report.setdefault('diagnosis', {})
    report['diagnosis']['next_actions'] = list(steps)
    report['diagnosis']['zpd_recommendations'] = list(steps)
