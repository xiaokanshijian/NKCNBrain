"""面向中小学作业批改质量的“证据 × 教学”红蓝卡标。"""
from __future__ import annotations

import datetime as dt
from .feedback_runtime import stamp_feedback

import json
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Set

from app_chat.homework_grading.llm_clients import (
    HOMEWORK_RED_BLUE_MODEL,
    HOMEWORK_RED_BLUE_REASONING_EFFORT,
    _call_homework_red_blue_json,
    _loads_json_with_retry_text,
    _write_text,
)
from app_chat.homework_grading.utils import (
    load_sample_meta,
    make_qid_global,
    parse_page_num,
    safe_json_dump,
    safe_json_load,
    sorted_json_pages,
)


SCHEMA_VERSION = 'homework-red-blue-v1'
PROMPT_VERSION = 'evidence-teaching-v1'
REVIEW_FILENAME = 'red_blue_review.json'
REASONING_FILENAME = 'red_blue_review.thinking.txt'
ITERATION_CONTEXT_FILENAME = 'iteration_context.json'
EARLY_STAGE_FEEDBACK_ENV = 'NKCN_HOMEWORK_RED_BLUE_EARLY_STAGE_FEEDBACK_ENABLED'

DIMENSION_SPECS = {
    'evidence_fidelity': {'label': '证据忠实度', 'rail': 'blue', 'weight': Decimal('0.30')},
    'judgment_consistency': {'label': '判分一致性与不确定性边界', 'rail': 'blue', 'weight': Decimal('0.20')},
    'diagnostic_value': {'label': '学科诊断价值', 'rail': 'red', 'weight': Decimal('0.20')},
    'actionability': {'label': '建议可行动性', 'rail': 'red', 'weight': Decimal('0.20')},
    'closed_loop_fusion': {'label': '证据教学闭环', 'rail': 'fusion', 'weight': Decimal('0.10')},
}

SYSTEM_PROMPT = """你是中小学作业批改质量审计专家。你评价的是“AI批改结果的质量”，绝不是学生成绩、能力或品行。

请以“证据 × 教学”双轨框架审计：
1. 证据忠实度：题目、学生答案、判分、整篇诊断之间是否可追溯。
2. 判分一致性与不确定性边界：跨页、字迹不清、复核修正和幻觉风险是否被诚实处理。
3. 学科诊断价值：是否结合学科、年级、真实错因给出适龄诊断。
4. 建议可行动性：教师或学生是否能据此立即行动。
5. 证据教学闭环：诊断、优先级、行动是否由真实证据支撑。

每项按0到5分评分，可保留一位小数。低正确率不等于低批改质量；不得因为学生错题多而扣分。
建议只能引用输入 allowed_evidence_refs 中存在的题号，target_stage 只能是 layout、understanding、grading、all。
scope=global 仅用于确实适用于所有篇目的流程级建议；其余建议使用 scope=evidence。
只输出一个 JSON 对象，不要输出 Markdown。"""


def red_blue_feedback_policy(*, feedback_runtime=None) -> Dict[str, bool]:
    from .feedback_runtime import frozen_environment
    enabled = str(frozen_environment(feedback_runtime, EARLY_STAGE_FEEDBACK_ENV) or '').strip().lower() in (
        '1',
        'true',
        'yes',
        'on',
    )
    return {
        'early_stages_enabled': enabled,
        'layout_enabled': enabled,
        'understanding_enabled': enabled,
        'grading_enabled': True,
    }


def review_path(paths: Dict[str, str]) -> str:
    return os.path.join(paths['pass2_report'], REVIEW_FILENAME)


def reasoning_path(paths: Dict[str, str]) -> str:
    return os.path.join(paths['pass2_report'], REASONING_FILENAME)


def iteration_context_path(paths: Dict[str, str]) -> str:
    return os.path.join(paths['base'], ITERATION_CONTEXT_FILENAME)


def load_red_blue_review(paths: Dict[str, str]) -> Dict[str, Any]:
    path = review_path(paths)
    if not os.path.isfile(path):
        return {'status': 'missing', 'schema_version': SCHEMA_VERSION}
    try:
        value = safe_json_load(path)
        return value if isinstance(value, dict) else {'status': 'failed', 'schema_version': SCHEMA_VERSION}
    except Exception:
        return {'status': 'failed', 'schema_version': SCHEMA_VERSION, 'error': '卡标文件不可读'}


def load_iteration_context(paths: Dict[str, str]) -> Dict[str, Any]:
    path = iteration_context_path(paths)
    if not os.path.isfile(path):
        return {}
    try:
        value = safe_json_load(path)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def save_iteration_context(paths: Dict[str, str], context: Dict[str, Any]) -> Dict[str, Any]:
    value = dict(context or {})
    value.setdefault('schema_version', 'homework-iteration-context-v1')
    value.setdefault('created_at', dt.datetime.now().isoformat(timespec='seconds'))
    safe_json_dump(iteration_context_path(paths), value)
    return value


def clear_red_blue_review(paths: Dict[str, str]) -> None:
    for path in (review_path(paths), reasoning_path(paths)):
        if os.path.isfile(path):
            os.remove(path)


def _sample_id(manifest: Dict[str, Any]) -> str:
    return str(manifest.get('group_id') or '').replace('homework_', '')[:8] or 'sample'


def _load_report(paths: Dict[str, str], subject: str, sample_id: str) -> Dict[str, Any]:
    path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_report.json')
    if not os.path.isfile(path):
        return {}
    value = safe_json_load(path)
    return value if isinstance(value, dict) else {}


def _load_optional(path: str) -> Dict[str, Any]:
    if not path:
        return {}
    try:
        value = safe_json_load(path)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _question_risk(question: Dict[str, Any]) -> tuple:
    verdict = str(question.get('verdict') or 'uncertain')
    try:
        confidence = float(question.get('grading_confidence') or 100)
    except (TypeError, ValueError):
        confidence = 100.0
    return (
        0 if verdict == 'uncertain' else 1 if verdict in ('wrong', 'partial') else 2,
        0 if question.get('corrected') else 1,
        0 if str(question.get('recurrence_hint') or '') == 'recurring' else 1,
        confidence,
    )


def _valid_qids_from_pages(paths: Dict[str, str]) -> tuple[List[Dict[str, Any]], Set[str]]:
    questions: List[Dict[str, Any]] = []
    valid_qids: Set[str] = set()
    for page_file in sorted_json_pages(paths['pass1_json']):
        try:
            page_data = safe_json_load(page_file)
        except Exception:
            continue
        if not isinstance(page_data, dict):
            continue
        page = page_data.get('page') or parse_page_num(os.path.basename(page_file))
        for item in page_data.get('questions') or []:
            if not isinstance(item, dict):
                continue
            qid = str(item.get('qid_global') or make_qid_global(page, item.get('id')))
            if not qid:
                continue
            self_review = item.get('self_review') if isinstance(item.get('self_review'), dict) else {}
            verification_result = (
                item.get('verification_result')
                if isinstance(item.get('verification_result'), dict)
                else {}
            )
            valid_qids.add(qid)
            questions.append({
                'qid_global': qid,
                'page': page,
                'id': item.get('id'),
                'stem_excerpt': item.get('stem_excerpt') or '',
                'student_answer': item.get('student_answer') or '',
                'correct_answer': item.get('correct_answer'),
                'verdict': item.get('verdict') or 'uncertain',
                'error_type': item.get('error_type') or '',
                'knowledge_point': item.get('knowledge_point') or '',
                'recurrence_hint': item.get('recurrence_hint') or 'na',
                'cross_page': bool(item.get('cross_page')),
                'cross_page_resolved': bool(item.get('cross_page_resolved')),
                'uncertain_reason': item.get('uncertain_reason') or '',
                'corrected': bool(self_review.get('applied') or verification_result),
                'review_correction': {
                    'applied': bool(self_review.get('applied')),
                    'reason': self_review.get('reason') or '',
                    'previous': self_review.get('previous') or {},
                    'verdict_fix_blocked': bool(self_review.get('verdict_fix_blocked')),
                },
                'verification_result': verification_result,
                'recognition_confidence': item.get('recognition_confidence'),
                'understanding_confidence': item.get('understanding_confidence'),
                'grading_confidence': item.get('grading_confidence'),
            })
    return questions, valid_qids


def _zone_evidence(report: Dict[str, Any]) -> tuple[int, int]:
    total = 0
    invalid = 0
    zones = report.get('zone_classification')
    if not isinstance(zones, dict):
        zones = {}
    for items in zones.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            refs = item.get('evidence_question_ids') or []
            total += len(refs)
            invalid += sum(1 for ref in refs if not str(ref or '').strip())
    return total, invalid


def _slim_audit(value: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = {
        key: value.get(key)
        for key in (
            'total_discrepancies',
            'corrections_applied',
            'corrections_applied_count',
            'total_issues',
            'type_counts',
        )
        if key in value
    }
    for key in ('details', 'issues', 'corrections'):
        if isinstance(value.get(key), list):
            result[key] = value[key][:12]
    return result


def _take_list(value: Any, limit: int) -> List[Any]:
    return list(value[:limit]) if isinstance(value, list) else []


def build_review_evidence(paths: Dict[str, str], manifest: Dict[str, Any], *, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None:
        manifest = dict(manifest, subject=feedback_runtime.context['subject_code'])
    subject = str(manifest.get('subject') or 'unknown')
    sample_id = _sample_id(manifest)
    questions, valid_qids = _valid_qids_from_pages(paths)
    if not questions:
        raise ValueError('没有可评估的最终题目结果')
    report = _load_report(paths, subject, sample_id)
    if not report:
        raise ValueError('没有可评估的整篇批改报告')
    ontology = _load_optional(os.path.join(paths['base'], 'student_ontology.json'))
    if feedback_runtime is not None:
        from .utils import sorted_json_pages, safe_json_load
        for value in [report, ontology] + [safe_json_load(p) for p in sorted_json_pages(paths['pass1_json'])]:
            if value.get('feedback_execution', {}).get('config_fingerprint') != feedback_runtime.fingerprint:
                raise ValueError('质量检查输入配置不一致')
    verification = _load_optional(os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_verification.json'))
    answer_verification = _load_optional(
        os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_answer_statement_verification.json')
    )
    hallucination = _load_optional(os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_hallucination.json'))
    meta = load_sample_meta(paths['base']) or {}
    if not isinstance(meta, dict):
        meta = {}
    if feedback_runtime is not None:
        from .feedback_runtime import runtime_attributes
        _, actual_grade, actual_stage = runtime_attributes(feedback_runtime)
        meta = {'grade': actual_grade, 'stage': actual_stage}
    homework_attributes = (
        manifest.get('homework_attributes')
        if isinstance(manifest.get('homework_attributes'), dict)
        else {}
    )
    verdict_distribution: Dict[str, int] = {}
    for question in questions:
        verdict = str(question.get('verdict') or 'uncertain')
        verdict_distribution[verdict] = verdict_distribution.get(verdict, 0) + 1
    feedback = report.get('per_question_feedback')
    if not isinstance(feedback, list):
        feedback = []
    feedback_refs = {
        str(item.get('qid_global') or item.get('id') or '')
        for item in feedback if isinstance(item, dict)
    }
    error_qids = {
        item['qid_global'] for item in questions
        if item.get('verdict') in ('wrong', 'partial', 'uncertain', 'unanswered')
    }
    covered = len(error_qids & feedback_refs)
    zone_ref_total, zone_ref_invalid = _zone_evidence(report)
    representative = sorted(questions, key=_question_risk)[:12]
    representative_qids = {item['qid_global'] for item in representative}
    representative_feedback = sorted(
        [item for item in feedback if isinstance(item, dict)],
        key=lambda item: (
            0
            if str(item.get('qid_global') or item.get('id') or '') in representative_qids
            else 1
        ),
    )[:12]
    ontology_zones = ontology.get('zones') if isinstance(ontology.get('zones'), dict) else {}
    return stamp_feedback({
        'evaluation_target': 'AI批改结果质量，不是学生成绩',
        'sample_meta': {
            'subject': subject,
            'subject_label': manifest.get('subject_label') or '',
            'grade': meta.get('grade') if feedback_runtime is not None else meta.get('grade') or homework_attributes.get('homework_grade'),
            'stage': meta.get('stage'),
            'page_count': len({item.get('page') for item in questions}),
            'question_count': len(questions),
        },
        'quality_metrics': {
            'verdict_distribution': verdict_distribution,
            'uncertain_count': verdict_distribution.get('uncertain', 0),
            'feedback_count': len(feedback),
            'error_feedback_coverage': round(covered / len(error_qids), 4) if error_qids else 1.0,
            'zone_evidence_count': zone_ref_total,
            'empty_zone_evidence_count': zone_ref_invalid,
            'verification_discrepancies': verification.get('total_discrepancies', 0),
            'answer_statement_discrepancies': answer_verification.get('total_discrepancies', 0),
            'answer_statement_corrections': answer_verification.get('corrections_applied', 0),
            'hallucination_issues': hallucination.get('total_issues', 0),
            'ontology_fallback_used': bool(ontology.get('fallback_used')),
        },
        'diagnosis': report.get('diagnosis') or {},
        'zone_classification': report.get('zone_classification') or {},
        'ontology': {
            'built_by': ontology.get('built_by') or '',
            'fallback_used': bool(ontology.get('fallback_used')),
            'evolution_narrative': ontology.get('evolution_narrative') or '',
            'mastery_trajectory': _take_list(ontology.get('mastery_trajectory'), 12),
            'zones': {
                key: _take_list(ontology_zones.get(key), 8)
                for key in ('blind_spot', 'friction_zone', 'zpd')
            },
        },
        'audits': {
            'rule_verification': _slim_audit(verification),
            'answer_statement_verification': _slim_audit(answer_verification),
            'hallucination': _slim_audit(hallucination),
        },
        'per_question_feedback': representative_feedback,
        'representative_questions': representative,
        'allowed_evidence_refs': sorted(valid_qids),
        'iteration_lineage': load_iteration_context(paths),
    }, feedback_runtime, 'quality_evidence')


def _clamp_score(value: Any) -> Decimal:
    try:
        score = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f'维度分数无效: {value}') from exc
    clamped = min(Decimal('5'), max(Decimal('0'), score))
    return clamped.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)


def _round_one(value: Decimal) -> float:
    return float(value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def _clean_text(value: Any, limit: int = 600) -> str:
    return ' '.join(str(value or '').split())[:limit]


def _reasoning_text(message: Any) -> str:
    value = (
        getattr(message, 'reasoning_content', None)
        or getattr(message, 'reasoning', None)
        or ''
    )
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or '')


def _clean_refs(values: Iterable[Any], valid_qids: Set[str]) -> List[str]:
    refs: List[str] = []
    for value in values or []:
        ref = str(value or '').strip()
        if ref in valid_qids and ref not in refs:
            refs.append(ref)
    return refs


def normalize_review(raw: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError('Kimi 卡标返回不是 JSON 对象')
    raw_dimensions = raw.get('dimensions')
    if not isinstance(raw_dimensions, dict):
        raise ValueError('Kimi 卡标缺少 dimensions')
    valid_qids = set(evidence.get('allowed_evidence_refs') or [])
    dimensions: List[Dict[str, Any]] = []
    scores: Dict[str, Decimal] = {}
    for key, spec in DIMENSION_SPECS.items():
        item = raw_dimensions.get(key)
        if not isinstance(item, dict):
            raise ValueError(f'Kimi 卡标缺少维度 {key}')
        score = _clamp_score(item.get('score'))
        dimension_reason = _clean_text(item.get('reason'), 240)
        if not dimension_reason:
            raise ValueError(f'Kimi 卡标维度 {key} 缺少评分理由')
        scores[key] = score
        dimensions.append({
            'key': key,
            'label': spec['label'],
            'rail': spec['rail'],
            'weight': float(spec['weight']),
            'score': _round_one(score),
            'reason': dimension_reason,
            'evidence_refs': _clean_refs(item.get('evidence_refs') or [], valid_qids),
        })
    total = sum((scores[key] * spec['weight'] for key, spec in DIMENSION_SPECS.items()), Decimal('0'))
    blue = (scores['evidence_fidelity'] * Decimal('0.30') + scores['judgment_consistency'] * Decimal('0.20')) / Decimal('0.50')
    red = (scores['diagnostic_value'] * Decimal('0.20') + scores['actionability'] * Decimal('0.20')) / Decimal('0.40')
    delta = red - blue
    color = 'red' if delta > Decimal('0.5') else 'blue' if delta < Decimal('-0.5') else 'purple'
    color_label = {'red': '红·教学偏重', 'blue': '蓝·证据偏重', 'purple': '紫·平衡'}[color]

    suggestions: List[Dict[str, Any]] = []
    for index, item in enumerate(raw.get('suggestions') or []):
        if not isinstance(item, dict):
            continue
        target = str(item.get('target_stage') or 'all').strip().lower()
        if target not in ('layout', 'understanding', 'grading', 'all'):
            target = 'all'
        action = _clean_text(item.get('action'), 360)
        acceptance = _clean_text(item.get('acceptance_criteria'), 300)
        evidence_refs = _clean_refs(item.get('evidence_refs') or [], valid_qids)
        if not action or not acceptance or not evidence_refs:
            continue
        priority = str(item.get('priority') or 'medium').strip().lower()
        if priority not in ('high', 'medium', 'low'):
            priority = 'medium'
        scope = str(item.get('scope') or 'evidence').strip().lower()
        if scope not in ('evidence', 'global'):
            scope = 'evidence'
        suggestions.append({
            'id': str(item.get('id') or f's{index + 1}'),
            'priority': priority,
            'scope': scope,
            'target_stage': target,
            'action': action,
            'why': _clean_text(item.get('why'), 300),
            'acceptance_criteria': acceptance,
            'evidence_refs': evidence_refs,
        })
        if len(suggestions) >= 3:
            break
    if not suggestions:
        raise ValueError('Kimi 卡标未给出可执行建议')

    reason = _clean_text(raw.get('reason'), 500)
    if not reason:
        raise ValueError('Kimi 卡标缺少综合评分理由')

    return {
        'status': 'ready',
        'schema_version': SCHEMA_VERSION,
        'score': _round_one(total),
        'color': color,
        'color_label': color_label,
        'red_score': _round_one(red),
        'blue_score': _round_one(blue),
        'dimensions': dimensions,
        'reason': reason,
        'suggestions': suggestions,
        'generated_at': dt.datetime.now().isoformat(timespec='seconds'),
        'model': HOMEWORK_RED_BLUE_MODEL,
        'reasoning_effort': HOMEWORK_RED_BLUE_REASONING_EFFORT,
        'prompt_version': PROMPT_VERSION,
        'iteration_lineage': evidence.get('iteration_lineage') or {},
    }


def _runtime_quality_prompt(runtime):
    from .feedback_prompts import context_block, reference_block, stage_instructions
    return (SYSTEM_PROMPT + context_block(runtime) + reference_block(runtime)
            + stage_instructions(runtime, 'quality')
            + '\n未绑定课标或未覆盖专项不等于批改失败；应核对真实题目反馈和可追溯证据。')


def _messages(evidence: Dict[str, Any], *, feedback_runtime=None) -> List[Dict[str, Any]]:
    schema = {
        'dimensions': {
            key: {'score': 0.0, 'reason': '具体理由', 'evidence_refs': ['p1:1']}
            for key in DIMENSION_SPECS
        },
        'reason': '本次批改质量的综合理由',
        'suggestions': [{
            'id': 's1',
            'priority': 'high|medium|low',
            'scope': 'evidence|global',
            'target_stage': 'layout|understanding|grading|all',
            'action': '下一轮要执行的具体动作',
            'why': '为什么要调整',
            'acceptance_criteria': '如何判断调整已生效',
            'evidence_refs': ['p1:1'],
        }],
    }
    return [
        {'role': 'system', 'content': (SYSTEM_PROMPT if feedback_runtime is None else _runtime_quality_prompt(feedback_runtime))},
        {
            'role': 'user',
            'content': (
                '请严格按以下结构审计，并给出1至3条建议：\n'
                + json.dumps(schema, ensure_ascii=False)
                + '\n\n待审计证据包：\n'
                + json.dumps(evidence, ensure_ascii=False)
            ),
        },
    ]


def evaluate_homework_red_blue(paths: Dict[str, str], manifest: Dict[str, Any], *, feedback_runtime=None) -> Dict[str, Any]:
    """生成卡标；任何失败都落盘为 failed，不阻断正式批改结果。"""
    if feedback_runtime is not None:
        manifest = dict(manifest, subject=feedback_runtime.context['subject_code'])
    reasoning_parts: List[str] = []
    try:
        evidence = build_review_evidence(paths, manifest, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        messages = _messages(evidence, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        response = _call_homework_red_blue_json(messages, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        message = response.choices[0].message
        raw_text = message.content or ''
        reasoning = _reasoning_text(message)
        if reasoning:
            reasoning_parts.append(reasoning)
        try:
            parsed = _loads_json_with_retry_text(raw_text)
            review = normalize_review(parsed, evidence)
        except Exception as first_error:
            retry_messages = list(messages) + [
                {'role': 'assistant', 'content': raw_text},
                {
                    'role': 'user',
                    'content': f'上次返回无法通过 JSON/结构校验（{first_error}）。请只输出符合既定结构的 JSON 对象。',
                },
            ]
            retry_response = _call_homework_red_blue_json(retry_messages, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
            retry_message = retry_response.choices[0].message
            raw_text = retry_message.content or ''
            retry_reasoning = _reasoning_text(retry_message)
            if retry_reasoning:
                reasoning_parts.append(retry_reasoning)
            parsed = _loads_json_with_retry_text(raw_text)
            review = normalize_review(parsed, evidence)
    except Exception as exc:
        review = {
            'status': 'failed',
            'schema_version': SCHEMA_VERSION,
            'error': _clean_text(exc, 300),
            'generated_at': dt.datetime.now().isoformat(timespec='seconds'),
            'model': HOMEWORK_RED_BLUE_MODEL,
            'reasoning_effort': HOMEWORK_RED_BLUE_REASONING_EFFORT,
            'prompt_version': PROMPT_VERSION,
        }
    if reasoning_parts:
        _write_text(reasoning_path(paths), '\n\n---\n\n'.join(reasoning_parts))
    iteration_context = load_iteration_context(paths)
    if iteration_context:
        review['iteration_lineage'] = {
            'source_run_id': iteration_context.get('source_run_id', ''),
            'source_score': iteration_context.get('source_score'),
            'used_red_blue_feedback': bool(iteration_context.get('enabled')),
            'rerun_stage': iteration_context.get('rerun_stage', ''),
            'session_ids': list(iteration_context.get('session_ids') or []),
            'feedback_policy': dict(iteration_context.get('feedback_policy') or {}),
        }
    safe_json_dump(review_path(paths), stamp_feedback(review, feedback_runtime, 'quality'))
    return review


def build_iteration_context(
    review: Dict[str, Any],
    enabled: bool,
    source_run_id: str,
    rerun_stage: str,
    session_ids: Optional[List[str]] = None,
    *, feedback_runtime=None,
) -> Dict[str, Any]:
    ready = isinstance(review, dict) and review.get('status') == 'ready'
    if enabled and not ready:
        raise ValueError('当前版本没有可参考的红蓝卡标')
    return {
        'schema_version': 'homework-iteration-context-v1',
        'enabled': bool(enabled and ready),
        'feedback_policy': red_blue_feedback_policy(feedback_runtime=feedback_runtime),
        'source_run_id': source_run_id or 'current',
        'source_score': review.get('score') if ready else None,
        'source_color': review.get('color') if ready else '',
        'source_reason': review.get('reason') if ready else '',
        'suggestions': list(review.get('suggestions') or []) if ready else [],
        'rerun_stage': rerun_stage,
        'session_ids': list(session_ids or []),
        'created_at': dt.datetime.now().isoformat(timespec='seconds'),
    }


def compile_iteration_guidance(
    context: Dict[str, Any],
    target_stage: str,
    page_nums: Optional[Set[int]] = None,
    *, feedback_runtime=None,
) -> str:
    if not isinstance(context, dict) or not context.get('enabled'):
        return ''
    policy = context.get('feedback_policy')
    if not isinstance(policy, dict):
        policy = red_blue_feedback_policy(feedback_runtime=feedback_runtime)
    if (
        target_stage in ('layout', 'understanding')
        and not bool(policy.get('early_stages_enabled'))
    ):
        return ''
    selected: List[Dict[str, Any]] = []
    for item in context.get('suggestions') or []:
        if not isinstance(item, dict):
            continue
        if item.get('target_stage') not in ('all', target_stage):
            continue
        refs = [str(ref or '') for ref in item.get('evidence_refs') or []]
        if page_nums and refs and item.get('scope') != 'global':
            relevant = False
            for ref in refs:
                try:
                    page = int(ref.split(':', 1)[0].lstrip('p'))
                except Exception:
                    continue
                if page in page_nums:
                    relevant = True
                    break
            if not relevant:
                continue
        selected.append(item)
    if not selected:
        return ''
    payload = {
        'source_score': context.get('source_score'),
        'source_color': context.get('source_color'),
        'source_reason': context.get('source_reason'),
        'suggestions': selected,
    }
    return (
        '\n\n【上轮批改质量卡标（仅作改进约束）】\n'
        + json.dumps(payload, ensure_ascii=False)
        + '\n必须以当前原图、结构化证据和学科规则为准；不得仅因卡标建议翻转题目判定。'
    )
