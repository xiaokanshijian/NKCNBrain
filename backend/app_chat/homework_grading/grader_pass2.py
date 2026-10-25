"""Pass2 unified homework report generation.

Consumes memory and, when available, student_ontology.json as the authority for
zone_classification, matching yq's single-report convergence.
"""

from .stage_dependencies import artifact_compatible
from .feedback_runtime import stamp_feedback
from .page_feedback import PAGE_FEEDBACK_PROTOCOL, normalize_page_contexts
from .model_output import request_json_object, object_list, validate_zones

import json
import logging
import os
from typing import Any, Dict, List, Optional

from app_chat.homework_grading.llm_clients import (
    _deepseek_client,
    _loads_json_with_retry_text,
    _write_text,
    homework_deepseek_model,
)
from app_chat.homework_grading.prompts import (
    pass2_feedback_system,
    pass2_feedback_user,
    pass2_system,
)
from app_chat.homework_grading.utils import safe_json_dump, normalize_question_evidence

logger = logging.getLogger(__name__)


def pass2_user_prompt(memory: Dict[str, Any]) -> str:
    slim_memory = _slim_memory_for_pass2(memory)
    return (
        '以下是这份作业的批改记忆，请按照系统提示中的 schema 输出 JSON 分析报告。'
        '不要为信息不足的题目强行编造结论。\n\n'
        + (PAGE_FEEDBACK_PROTOCOL + '\n' if memory.get('page_understanding') else '')
        + json.dumps(slim_memory, ensure_ascii=False)
    )


def _slim_memory_for_pass2(memory: Dict[str, Any]) -> Dict[str, Any]:
    error_fields = (
        'page',
        'id',
        'qid_global',
        'verdict',
        'stem_excerpt',
        'student_answer',
        'correct_answer',
        'error_type',
        'knowledge_point',
        'cross_page',
        'cross_page_note',
        'cross_page_resolved',
        'uncertain_reason',
    )
    accuracy = memory.get('accuracy') or {}
    return {
        'subject': memory.get('subject'),
        'sample_id': memory.get('sample_id'),
        'page_count': memory.get('page_count', 0),
        'page_understanding': memory.get('page_understanding', []),
        'question_count': memory.get('question_count', 0),
        'accuracy_overall': accuracy.get('overall', 0.0),
        'verdict_distribution': memory.get('verdict_distribution') or {},
        'uncertain_count': memory.get('uncertain_count', 0),
        'error_questions': [
            {key: question.get(key) for key in error_fields if key in question}
            for question in memory.get('error_questions') or []
        ],
        'knowledge_point_frequency': memory.get('knowledge_point_frequency') or [],
        'error_type_distribution': memory.get('error_type_distribution') or {},
    }


def _validate_pass2_result(result: Dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise ValueError('Pass 2 返回不是 JSON 对象')
    for key in ('diagnosis', 'zone_classification', 'per_question_feedback'):
        if key not in result:
            raise ValueError(f'Pass 2 返回缺少 {key}')
    if not isinstance(result['diagnosis'], dict):
        raise ValueError('diagnosis必须为对象')
    validate_zones(result['zone_classification'], 'zone_classification')
    object_list(result['per_question_feedback'], 'per_question_feedback')


def _flatten_ontology_evidence(entry: Dict[str, Any]) -> List[str]:
    evidence: List[str] = normalize_question_evidence(entry.get('evidence'))
    evidence.extend(normalize_question_evidence(entry.get('content_context_evidence')))
    for cluster in entry.get('error_clusters') or []:
        evidence.extend(normalize_question_evidence(cluster.get('evidence')))
    return list(dict.fromkeys(qid for qid in evidence if qid))


def _ontology_entry_to_zone_item(entry: Dict[str, Any]) -> Dict[str, Any]:
    curriculum_id = entry.get('curriculum_id') or ''
    return {
        'knowledge_point': entry.get('knowledge_point', ''),
        'evidence_question_ids': _flatten_ontology_evidence(entry),
        'evidence_curriculum_ids': [curriculum_id] if curriculum_id else [],
        'comment': entry.get('rationale', ''),
        'stability': entry.get('stability'),
        'trend': entry.get('trend'),
        'first_session': entry.get('first_session'),
        'last_session': entry.get('last_session'),
        'confidence': entry.get('confidence'),
        'fallback': entry.get('fallback'),
        'suggested_next_step': entry.get('suggested_next_step'),
        'error_clusters': entry.get('error_clusters', []),
        'source': 'ontology',
        'evidence_basis': entry.get('evidence_basis', 'content'),
        **({'content_context_evidence': list(entry['content_context_evidence'])} if entry.get('content_context_evidence') else {}),
    }


def _build_zone_classification_from_ontology(ontology: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    zones = ontology.get('zones') or {}
    out = {
        bucket: [
            _ontology_entry_to_zone_item(entry)
            for entry in (zones.get(bucket) or [])
        ]
        for bucket in ('blind_spot', 'friction_zone', 'zpd')
    }
    out['uncertain'] = []
    return out


def _build_diagnosis_from_ontology(ontology: Dict[str, Any]) -> Dict[str, Any]:
    zones = ontology.get('zones') or {}
    blind = zones.get('blind_spot') or []
    persistent_friction = [
        entry for entry in (zones.get('friction_zone') or [])
        if entry.get('stability') == 'persistent'
    ]
    weakest = [
        entry.get('knowledge_point')
        for entry in (blind + persistent_friction)
        if entry.get('knowledge_point') and entry.get('knowledge_point') != 'no_observed'
    ]
    weakest = list(dict.fromkeys(weakest))[:3]

    recs: List[str] = []
    for entry in (zones.get('zpd') or [])[:3]:
        rec = entry.get('suggested_next_step') or entry.get('rationale') or ''
        if rec:
            recs.append(rec)

    narrative = ontology.get('evolution_narrative', '') or ''
    cognitive_stage = narrative if len(narrative) <= 80 else narrative[:78] + '…'
    main_problems = [
        entry.get('rationale') or entry.get('knowledge_point')
        for entry in (blind + persistent_friction)
        if (entry.get('rationale') or entry.get('knowledge_point'))
        and entry.get('knowledge_point') != 'no_observed'
    ][:3]
    return {
        'summary': narrative,
        'cognitive_stage': cognitive_stage,
        'strengths': [],
        'main_problems': main_problems,
        'weakest_areas': weakest,
        'zpd_recommendations': recs,
        'next_actions': recs,
    }


def _validate_open_material_overview(payload: Dict[str, Any]) -> Dict[str, Any]:
    overview = payload.get('open_material_overview')
    if not isinstance(overview, dict):
        raise ValueError('开放材料批语缺少 open_material_overview')
    normalized: Dict[str, Any] = {}
    for field in ('subject_and_layout', 'content_review'):
        value = overview.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'开放材料批语缺少 {field}')
        normalized[field] = value.strip()
    steps = overview.get('next_steps')
    if (not isinstance(steps, list) or not 1 <= len(steps) <= 2
            or any(not isinstance(step, str) or not step.strip() for step in steps)):
        raise ValueError('开放材料下一步建议必须包含一至两条非空文字')
    normalized['next_steps'] = [step.strip() for step in steps]
    return normalized


def _call_pass2_feedback_batch(
    memory: Dict[str, Any],
    subject: str,
    sample_id: str,
    ontology: Dict[str, Any],
    out_thinking_path: str,
    iteration_guidance: str = '',
*, feedback_runtime=None, include_overview=True, document_context=None) -> Dict[str, Any]:
    """yq v2.5 Pass2：只让 LLM 基于 ontology 三区生成逐题批语。"""
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if not memory.get('error_questions') and not memory.get('page_understanding'):
        return {'per_question_feedback': []}

    from .feedback_material_kinds import is_open_material
    open_material = bool(
        feedback_runtime is not None
        and is_open_material((feedback_runtime.context or {}).get('material_type'))
    )

    client = _deepseek_client()
    from .feedback_model import runtime_client
    client = runtime_client(client, feedback_runtime, "deepseek")
    messages = [
        {'role': 'system', 'content': pass2_feedback_system(subject, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
        {
            'role': 'user',
            'content': pass2_feedback_user(
                memory, ontology,
                **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}),
            ) + (iteration_guidance or ''),
        },
    ]
    if document_context is not None:
        messages.append({'role': 'user', 'content': (
            '本次为分批反馈。所有批次共用同一份诊断，不能新增或改动三区归属。'
            '仅返回以下全局题号的逐项反馈，全文上下文中的其他单元不属于本批输出：'
            + json.dumps([q['qid_global'] for q in memory.get('error_questions', [])], ensure_ascii=False) + '\n'
            + ('请基于以下完整上下文生成一次整份材料概览。\n' if include_overview else
               '整份概览已另行生成，本批无需open_material_overview。\n')
            + json.dumps(document_context, ensure_ascii=False))})
    kwargs = {
        'model': homework_deepseek_model(),
        'max_tokens': 32768,
        'response_format': {'type': 'json_object'},
        'extra_body': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'},
    }
    feedback_thinking_path = os.path.join(
        os.path.dirname(out_thinking_path),
        f'{subject}_{sample_id}_feedback.thinking.txt',
    )
    from .validation_issues import ValidationIssues, issue, raise_issues, feedback_repair_plan

    def validate(data):
        issues = []
        feedback = object_list(data.get('per_question_feedback'), 'per_question_feedback')
        result = {'per_question_feedback': feedback}
        result['page_feedback_contexts'] = normalize_page_contexts(
            data.get('page_feedback_contexts'), memory.get('page_understanding', []))
        if open_material and include_overview:
            try:
                result['open_material_overview'] = _validate_open_material_overview(data)
            except ValueError as exc:
                issues.append(issue(exc, '/open_material_overview', code='overview_schema'))
        if feedback_runtime is not None:
            try:
                _validate_runtime_feedback(result, memory)
            except ValidationIssues as exc:
                issues.extend(exc.issues)
        if open_material:
            from .note_evidence import validate_note_feedback, normalize_feedback_zones
            for index, item in enumerate(feedback):
                try:
                    one = {'per_question_feedback': [item]}
                    normalize_feedback_zones(one, ontology)
                    if one.get('_zone_normalizations'):
                        result.setdefault('_zone_normalizations', []).extend(one['_zone_normalizations'])
                    validate_note_feedback(one, memory, ontology, material_type=feedback_runtime.context['material_type'])
                except ValueError as exc:
                    issues.append(issue(exc, f'/per_question_feedback/{index}', qid=item.get('qid_global')))
            try:
                validate_note_feedback({key: value for key, value in result.items() if key != 'per_question_feedback'},
                    memory, ontology, material_type=feedback_runtime.context['material_type'])
            except ValidationIssues as exc:
                issues.extend(exc.issues)
        raise_issues(issues)
        return result

    def partial(data, error):
        from .partial_feedback import partial_feedback

        def validate_item(item, question):
            _validate_runtime_feedback({'per_question_feedback': [item]}, {'error_questions': [question]})
            if open_material:
                from .note_evidence import validate_note_feedback, normalize_feedback_zones
                one = {'per_question_feedback': [item]}
                normalize_feedback_zones(one, ontology)
                validate_note_feedback(one, memory, ontology, material_type=feedback_runtime.context['material_type'])
        return partial_feedback(data, error, memory, validate_item)

    return request_json_object(
        lambda current: client.chat.completions.create(messages=current, **kwargs), messages,
        parser=_loads_json_with_retry_text, validate=validate,
        audit_path=feedback_thinking_path.replace('.thinking.txt', '.responses.json'),
        stage='逐题批语', thinking_path=feedback_thinking_path,
        error_path=feedback_thinking_path.replace('.thinking.txt', '.error.txt'),
        repair_plan=feedback_repair_plan, on_exhausted=partial, split_on_truncation=True,
        allow_reasoning_json=True)


def _call_pass2_feedback_llm(memory, subject, sample_id, ontology, out_thinking_path,
                             iteration_guidance='', *, feedback_runtime=None):
    """长材料限制每批输出，截断时二分；全部批次复用同一诊断和全文依据。"""
    import copy
    from .execution_control import setting
    from .model_output import OutputTruncatedError
    from .execution_checkpoints import digest
    questions = memory.get('error_questions') or []
    size = setting(feedback_runtime, 'HOMEWORK_PASS2_BATCH_SIZE', 12, maximum=50)
    context = {'document_memory': memory, 'ontology_fingerprint': digest(ontology)}
    parts = []

    def run(items, label, first, batched):
        selected = dict(memory, error_questions=items)
        if batched:
            pages = {q.get('page') for q in items}
            selected['page_understanding'] = [p for p in memory.get('page_understanding', []) if p.get('page') in pages]
        try:
            value = _call_pass2_feedback_batch(selected, subject,
                sample_id + ('_batch_' + label if batched else ''), copy.deepcopy(ontology), out_thinking_path,
                iteration_guidance, feedback_runtime=feedback_runtime, include_overview=first,
                document_context=context if batched else None)
        except OutputTruncatedError:
            if len(items) <= 1:
                raise
            middle = len(items) // 2
            run(items[:middle], label + 'a', first, True)
            run(items[middle:], label + 'b', False, True)
        else:
            parts.append(value)

    if len(questions) <= size:
        run(questions, '0', True, False)
    else:
        for start in range(0, len(questions), size):
            run(questions[start:start + size], str(start // size), start == 0, True)
    combined = copy.deepcopy(parts[0])
    combined['per_question_feedback'] = [item for part in parts for item in part['per_question_feedback']]
    contexts = {}
    for part in parts:
        for page in part.get('page_feedback_contexts', []):
            contexts.setdefault(page['page'], page)
    combined['page_feedback_contexts'] = normalize_page_contexts(list(contexts.values()), memory.get('page_understanding', []))
    normalizations = [item for part in parts for item in part.get('_zone_normalizations', [])]
    if normalizations:
        combined['_zone_normalizations'] = normalizations
    issues = [item for part in parts for item in part.get('content_validation', {}).get('issues', [])]
    if issues:
        combined['content_validation'] = {'status': 'needs_review', 'issues': issues}
    if feedback_runtime is not None:
        _validate_runtime_feedback(combined, memory)
    return combined


def _validate_unified_report(report: Dict[str, Any], memory: Dict[str, Any]) -> None:
    for key in ('diagnosis', 'zone_classification', 'per_question_feedback'):
        if key not in report:
            raise ValueError(f'Pass 2 统一报告缺少 {key}')
    valid_ids: set = set()
    for question in memory.get('error_questions') or []:
        if question.get('qid_global'):
            valid_ids.add(str(question['qid_global']))
        if question.get('id') is not None:
            valid_ids.add(str(question['id']))
    for feedback in report.get('per_question_feedback') or []:
        feedback_id = feedback.get('qid_global') or feedback.get('id')
        if feedback_id and str(feedback_id) not in valid_ids:
            logger.warning('Pass2 feedback id %r not found in error_questions', feedback_id)
        if feedback.get('zone') not in ('blind_spot', 'friction_zone', 'zpd', 'uncertain', ''):
            logger.warning('Pass2 feedback invalid zone: %r', feedback.get('zone'))


def _overlay_ontology_zones(result: Dict[str, Any], ontology: Dict[str, Any]) -> None:
    """以 ontology.zones 作为 zone_classification 权威来源，并写入 _ontology_metadata。"""
    zones = ontology.get('zones') or {}
    overlay: Dict[str, List[Dict[str, Any]]] = {}
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        items = []
        for entry in zones.get(bucket, []) or []:
            ev = normalize_question_evidence(entry.get('evidence'))
            ev.extend(normalize_question_evidence(entry.get('content_context_evidence')))
            for ec in entry.get('error_clusters', []) or []:
                ev.extend(normalize_question_evidence(ec.get('evidence')))
            items.append({
                'knowledge_point': entry.get('knowledge_point'),
                'curriculum_id': entry.get('curriculum_id', ''),
                'evidence_question_ids': list(dict.fromkeys(ev)),
                'evidence_curriculum_ids': [entry.get('curriculum_id')] if entry.get('curriculum_id') else [],
                'comment': entry.get('rationale', ''),
                'stability': entry.get('stability'),
                'trend': entry.get('trend'),
                'confidence': entry.get('confidence'),
                'first_session': entry.get('first_session'),
                'last_session': entry.get('last_session'),
                'error_clusters': entry.get('error_clusters', []),
                'suggested_next_step': entry.get('suggested_next_step', ''),
                'evidence_basis': entry.get('evidence_basis', 'content'),
                **({'content_context_evidence': list(entry['content_context_evidence'])} if entry.get('content_context_evidence') else {}),
            })
        overlay[bucket] = items
    existing_uncertain = (result.get('zone_classification') or {}).get('uncertain') or []
    overlay['uncertain'] = existing_uncertain
    result['zone_classification'] = overlay
    result['_ontology_metadata'] = {
        'non_empty_guaranteed': bool(ontology.get('non_empty_guaranteed')),
        'fallback_used': bool(ontology.get('fallback_used')),
        'built_by': ontology.get('built_by', ''),
        'evolution_narrative': ontology.get('evolution_narrative', ''),
    }


def _validate_runtime_feedback(report, memory):
    from .validation_issues import issue, raise_issues
    questions = {str(q.get('qid_global')): q for q in memory.get('error_questions', []) if q.get('qid_global')}
    feedback = report.get('per_question_feedback')
    if not isinstance(feedback, list):
        raise_issues([issue(ValueError('题目批语缺失，不能返回空成功'), '/per_question_feedback')])
    issues, seen = [], set()
    counts = {}
    for item in feedback:
        if isinstance(item, dict) and isinstance(item.get('qid_global'), str):
            counts[item['qid_global']] = counts.get(item['qid_global'], 0) + 1
    for index, item in enumerate(feedback):
        path = f'/per_question_feedback/{index}'
        if not isinstance(item, dict):
            issues.append(issue(ValueError('批语必须为对象'), path))
            continue
        qid = item.get('qid_global')
        if not isinstance(qid, str) or qid not in questions or counts[qid] != 1:
            issues.append(issue(ValueError('批语引用无效或重复的全局题号'), path, qid=qid if isinstance(qid, str) else None))
            continue
        seen.add(qid)
        question = questions[qid]
        if str(item.get('id')) != str(question.get('id')) or type(item.get('page')) is not int or item['page'] != question['page']:
            issues.append(issue(ValueError('批语页码与题号不一致'), path, qid=qid))
        if not isinstance(item.get('comment'), str) or not item['comment'].strip():
            issues.append(issue(ValueError('题目批语为空'), path, qid=qid))
    if set(questions) - seen:
        issues.append(issue(ValueError('部分待反馈题目缺少批语：' + ', '.join(sorted(set(questions)-seen))), '/per_question_feedback'))
    raise_issues(issues)


def analyze_pass2(
    memory: Dict[str, Any],
    subject: str,
    sample_id: str,
    out_report_path: str,
    out_thinking_path: str,
    profile: Optional[Dict[str, Any]] = None,
    ontology: Optional[Dict[str, Any]] = None,
    iteration_guidance: str = '',
*, feedback_runtime=None) -> Dict[str, Any]:
    from .feedback_material_kinds import is_open_material
    open_material = bool(
        feedback_runtime is not None
        and is_open_material((feedback_runtime.context or {}).get('material_type'))
    )
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
        if not artifact_compatible(memory, feedback_runtime):
            raise ValueError('批语记忆配置不一致')
        if ontology is not None and not artifact_compatible(ontology, feedback_runtime):
            raise ValueError('批语诊断配置不一致')
        if ontology is not None and ontology.get('status') == 'failed':
            raise ValueError('前序诊断失败，不能生成成功批语')
    from .note_evidence import validate_note_feedback, validate_note_ontology, align_note_report, normalize_feedback_zones
    if open_material:
        if ontology is None:
            raise ValueError('作文／笔记缺少证据诊断，不能回退到题目卷批语')
        from .material_markings import open_units
        validate_note_ontology(ontology, open_units(memory, feedback_runtime.context['material_type']))
    if ontology:
        feedback_result = _call_pass2_feedback_llm(
            memory=memory,
            subject=subject,
            sample_id=sample_id,
            ontology=ontology,
            out_thinking_path=out_thinking_path,
            iteration_guidance=iteration_guidance,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        report = {
            'subject': subject,
            'sample_id': sample_id,
            'grade': ontology.get('grade'),
            'stage': ontology.get('stage'),
            'diagnosis': _build_diagnosis_from_ontology(ontology),
            'zone_classification': _build_zone_classification_from_ontology(ontology),
            'per_question_feedback': feedback_result['per_question_feedback'],
            'page_feedback_contexts': normalize_page_contexts(
                feedback_result.get('page_feedback_contexts'), memory.get('page_understanding', [])),
            '_ontology_metadata': {
                'session_count': ontology.get('session_count'),
                'non_empty_guaranteed': bool(ontology.get('non_empty_guaranteed')),
                'fallback_used': bool(ontology.get('fallback_used')),
                'evolution_narrative': ontology.get('evolution_narrative', ''),
                'built_at': ontology.get('built_at', ''),
                'built_by': ontology.get('built_by', ''),
            },
        }
        try:
            from .wgb_trust import build_user_verification_block, zones_for_verification
            uv = build_user_verification_block(
                ontology.get('wgb_trust') if isinstance(ontology, dict) else None,
                zones_for_verification(ontology if isinstance(ontology, dict) else None),
            )
            report['user_verification'] = uv
        except Exception:
            pass
        validations = [value.get('content_validation', {}) for value in (ontology, feedback_result)]
        pending = [entry for value in validations if value.get('status') == 'needs_review' for entry in value.get('issues', [])]
        if pending:
            report['content_validation'] = {'status': 'needs_review', 'issues': pending}
        if 'open_material_overview' in feedback_result:
            report['open_material_overview'] = feedback_result['open_material_overview']
        if feedback_result.get('_zone_normalizations'):
            report['_zone_normalizations'] = feedback_result['_zone_normalizations']
        if open_material:
            normalize_feedback_zones(report, ontology)
            validate_note_feedback(report, memory, ontology, material_type=feedback_runtime.context['material_type'])
            align_note_report(report)
        _validate_unified_report(report, memory)
        if feedback_runtime is not None:
            _validate_runtime_feedback(report, memory)
        safe_json_dump(out_report_path, stamp_feedback(report, feedback_runtime, 'pass2'))
        return report

    client = _deepseek_client()
    from .feedback_model import runtime_client
    client = runtime_client(client, feedback_runtime, "deepseek")
    base_messages = [
        {'role': 'system', 'content': pass2_system(subject, memory=memory, profile=profile, ontology=ontology, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
        {
            'role': 'user',
            'content': pass2_user_prompt(memory) + (iteration_guidance or ''),
        },
    ]
    kwargs = {
        'model': homework_deepseek_model(),
        'max_tokens': 32768,
        'response_format': {'type': 'json_object'},
        'extra_body': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'},
    }
    def validate(result):
        _validate_pass2_result(result)
        result['page_feedback_contexts'] = normalize_page_contexts(
            result.get('page_feedback_contexts'), memory.get('page_understanding', []))
        if open_material:
            result['open_material_overview'] = _validate_open_material_overview(result)
        if ontology:
            _overlay_ontology_zones(result, ontology)
        if feedback_runtime is not None:
            _validate_runtime_feedback(result, memory)
            result['subject'] = subject
        return result

    result = request_json_object(
        lambda current: client.chat.completions.create(messages=current, **kwargs), base_messages,
        parser=_loads_json_with_retry_text, validate=validate,
        audit_path=os.path.splitext(out_report_path)[0] + '.responses.json', stage='综合批语',
        thinking_path=out_thinking_path,
        error_path=os.path.splitext(out_report_path)[0] + '.error.txt')
    safe_json_dump(out_report_path, stamp_feedback(result, feedback_runtime, 'pass2'))
    return result
