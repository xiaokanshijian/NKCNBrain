"""Pass2 unified homework report generation.

Consumes memory and, when available, student_ontology.json as the authority for
zone_classification, matching yq's single-report convergence.
"""

from .feedback_runtime import stamp_feedback

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


def _flatten_ontology_evidence(entry: Dict[str, Any]) -> List[str]:
    evidence: List[str] = normalize_question_evidence(entry.get('evidence'))
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


def _call_pass2_feedback_llm(
    memory: Dict[str, Any],
    subject: str,
    sample_id: str,
    ontology: Dict[str, Any],
    out_thinking_path: str,
    iteration_guidance: str = '',
*, feedback_runtime=None) -> List[Dict[str, Any]]:
    """yq v2.5 Pass2：只让 LLM 基于 ontology 三区生成逐题批语。"""
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if not memory.get('error_questions'):
        return []

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
    last_raw = ''
    last_error: Exception | None = None
    for attempt in range(2):
        call_messages = list(messages)
        if attempt == 1:
            call_messages.extend([
                {'role': 'assistant', 'content': last_raw},
                {'role': 'user', 'content': f'上次返回不是合法 JSON（{last_error}），请只输出 JSON 对象，不含 Markdown 围栏。'},
            ])
        response = client.chat.completions.create(messages=call_messages, **kwargs)
        message = response.choices[0].message
        reasoning = getattr(message, 'reasoning_content', None) or ''
        if reasoning:
            _write_text(feedback_thinking_path, reasoning)
        last_raw = message.content or ''
        try:
            data = _loads_json_with_retry_text(last_raw)
            return list(data.get('per_question_feedback') or [])
        except json.JSONDecodeError as exc:
            last_error = exc

    error_path = out_thinking_path.replace('.thinking.txt', '_feedback.error.txt')
    _write_text(error_path, last_raw)
    raise ValueError(f'Pass 2 逐题批语返回不是合法 JSON，原始返回已保存到 {error_path}: {last_error}')


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
    """新链路不能以空批语或不一致的全局题号伪装完成。"""
    questions={str(q.get('qid_global')): q for q in memory.get('error_questions', []) if q.get('qid_global')}
    feedback=report.get('per_question_feedback')
    if not isinstance(feedback, list) or (questions and not feedback):
        raise ValueError('题目批语缺失，不能返回空成功')
    seen=set()
    for item in feedback:
        qid=str(item.get('qid_global') or '')
        if qid not in questions or qid in seen:
            raise ValueError('批语引用无效或重复的全局题号')
        question=questions[qid]
        if str(item.get('id'))!=str(question.get('id')) or item.get('page')!=question.get('page'):
            raise ValueError('批语页码与题号不一致')
        if not str(item.get('comment') or '').strip():
            raise ValueError('题目批语为空')
        seen.add(qid)
    if seen!=set(questions):
        raise ValueError('部分待反馈题目缺少批语')


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
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
        if memory.get('feedback_execution', {}).get('config_fingerprint') != feedback_runtime.fingerprint:
            raise ValueError('批语记忆配置不一致')
        if ontology is not None and ontology.get('feedback_execution', {}).get('config_fingerprint') != feedback_runtime.fingerprint:
            raise ValueError('批语诊断配置不一致')
        if ontology is not None and ontology.get('status') == 'failed':
            raise ValueError('前序诊断失败，不能生成成功批语')
    if ontology:
        per_question_feedback = _call_pass2_feedback_llm(
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
            'per_question_feedback': per_question_feedback,
            '_ontology_metadata': {
                'session_count': ontology.get('session_count'),
                'non_empty_guaranteed': bool(ontology.get('non_empty_guaranteed')),
                'fallback_used': bool(ontology.get('fallback_used')),
                'evolution_narrative': ontology.get('evolution_narrative', ''),
                'built_at': ontology.get('built_at', ''),
                'built_by': ontology.get('built_by', ''),
            },
        }
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
    last_raw = ''
    last_error: Exception | None = None
    for attempt in range(2):
        messages = list(base_messages)
        if attempt == 1:
            messages.extend([
                {'role': 'assistant', 'content': last_raw},
                {
                    'role': 'user',
                    'content': (
                        '上次返回不是合法 JSON，解析错误为：'
                        f'{last_error}。请在保持原有内容和字段结构的前提下，'
                        '只输出一个完整、可被 json.loads 解析的 JSON 对象；不要输出 Markdown 围栏、注释或额外文字。'
                    ),
                },
            ])
        response = client.chat.completions.create(messages=messages, **kwargs)
        message = response.choices[0].message
        reasoning = getattr(message, 'reasoning_content', None) or ''
        if reasoning:
            _write_text(out_thinking_path, reasoning)
        last_raw = message.content or ''
        try:
            result = _loads_json_with_retry_text(last_raw)
            _validate_pass2_result(result)
            if ontology:
                _overlay_ontology_zones(result, ontology)
            if feedback_runtime is not None:
                _validate_runtime_feedback(result, memory)
                result['subject'] = subject
            safe_json_dump(out_report_path, stamp_feedback(result, feedback_runtime, 'pass2'))
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc

    error_path = out_report_path.replace('_report.json', '_report.error.txt')
    _write_text(error_path, last_raw)
    raise ValueError(f'Pass 2 返回不是合法 JSON，原始返回已保存到 {error_path}: {last_error}')
