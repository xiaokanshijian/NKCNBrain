"""L5 数字孪生体构建器（nkcn 自有，改编自 yq v2.5 ontology_builder.py）。

输入：session_memories（按 order_index 升序） + memory + profile + sample_meta。
处理：组装时序证据包 → 调 DeepSeek V4 Flash（thinking high） → 解析校验 → 三区非空兜底。
输出：{base_dir}/student_ontology.json + student_ontology_evidence.json
     + {pass2_report}/{subject}_{sample_id}_ontology.thinking.txt
"""

from __future__ import annotations
from .stage_dependencies import artifact_compatible

import datetime as dt
from .feedback_runtime import runtime_attributes, stamp_feedback

import json
import logging
import os
import re
import time
import traceback
from typing import Any, Dict, List, Optional

from app_chat.homework_grading.llm_clients import _deepseek_client, homework_deepseek_model
from app_chat.homework_grading.prompts import ontology_system, ontology_user
from app_chat.homework_grading.sessions import session_page_bounds
from app_chat.homework_grading.utils import safe_json_dump

logger = logging.getLogger(__name__)

_VALID_TRENDS = {'improving', 'stable', 'worsening'}
_VALID_STATES = {'struggling', 'consolidating', 'acquired'}
_VALID_STABILITY = {'persistent', 'transient'}

_DISPLAY_TEXT_FIELDS = {
    'evolution_narrative',
    'rationale',
    'suggested_next_step',
    'cause',
}

_TERM_REPLACEMENTS = {
    'blind_spot': '盲区',
    'friction_zone': '内耗区',
    'zpd': '最近发展区',
    'transient': '阶段性',
    'persistent': '持续性',
    'improving': '有进步',
    'worsening': '有反复',
    'stable': '相对稳定',
    'struggling': '困难较多',
    'consolidating': '正在巩固',
    'acquired': '基本掌握',
    'student_ontology': '学科诊断结果',
    'ontology': '学科诊断结果',
}

_DEFAULT_LABEL_CN = {
    'none': '本次未观察到显著问题',
    'word_problem': '应用题',
    'operation_law': '运算律',
    'algebraic_expression': '代数表达',
    'algebra_expression': '代数表达',
    'letter_representation': '字母表示数量关系',
    'mul_div_algorithm': '乘除法算法',
    'rectangle_perimeter_area': '长方形周长与面积',
    'number_pattern': '规律探索',
    'extension_recommendation': '拓展提升建议',
    'no_observed': '本次未观察到显著问题',
}

_INTERNAL_TERM_RE = re.compile(r'(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*(?![A-Za-z0-9_])')
_SESSION_RANGE_RE = re.compile(
    r'(?<![A-Za-z0-9_])session\s*(\d+)\s*[-~—–至、,]\s*(\d+)(?![A-Za-z0-9_])',
    re.IGNORECASE,
)
_SESSION_REF_RE = re.compile(
    r'(?<![A-Za-z0-9_])session\s*(\d+)(?![A-Za-z0-9_])',
    re.IGNORECASE,
)
_SESSION_WORD_RE = re.compile(r'(?<![A-Za-z0-9_])sessions?(?![A-Za-z0-9_])', re.IGNORECASE)


def _load_label_display_map(subject: str) -> Dict[str, str]:
    """加载 KP 内部标签到中文展示名的映射，用于面向教师/家长的自然语言审校。"""
    mapping = dict(_DEFAULT_LABEL_CN)
    path = os.path.join(os.path.dirname(__file__), 'data', f'{subject}_curriculum_label_mapping.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as file:
                loaded = json.load(file)
            mapping.update({str(k): str(v) for k, v in loaded.items() if k and v})
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning('[L5] label display map load failed: %s', exc)
    return mapping


def _replace_internal_terms(text: str, label_map: Dict[str, str]) -> str:
    """审校一个展示文本字段；保留 qid_global 等合法证据编号。"""
    if not isinstance(text, str) or not text:
        return text

    out = text
    for label, zh in sorted(label_map.items(), key=lambda kv: len(kv[0]), reverse=True):
        out = re.sub(
            rf'(?<![A-Za-z0-9_]){re.escape(label)}(?![A-Za-z0-9_])',
            zh,
            out,
        )
    for raw, zh in sorted(_TERM_REPLACEMENTS.items(), key=lambda kv: len(kv[0]), reverse=True):
        out = re.sub(
            rf'(?<![A-Za-z0-9_]){re.escape(raw)}(?![A-Za-z0-9_])',
            zh,
            out,
            flags=re.IGNORECASE,
        )

    out = _SESSION_RANGE_RE.sub(lambda m: f'第{m.group(1)}至{m.group(2)}次练习', out)
    out = _SESSION_REF_RE.sub(lambda m: f'第{m.group(1)}次练习', out)
    out = _SESSION_WORD_RE.sub('练习阶段', out)
    out = out.replace('KP', '知识点')
    out = out.replace('文字题', '应用题')
    out = out.replace('最后练习阶段', '最后一次练习')
    out = re.sub(r'第(\d+)次练习[、,](\d+)', r'第\1至\2次练习', out)
    out = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', out)
    out = re.sub(r'\s+([。；，、）])', r'\1', out)
    out = re.sub(r'（\s+', '（', out)
    return out


def _walk_display_texts(obj: Any):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in _DISPLAY_TEXT_FIELDS and isinstance(value, str):
                yield value
            else:
                yield from _walk_display_texts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_display_texts(item)


def _polish_display_texts(ontology: Dict[str, Any], subject: str) -> Dict[str, Any]:
    """对自然语言展示字段做中文教育诊断风格审校。"""
    label_map = _load_label_display_map(subject)

    def visit(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in list(obj.items()):
                if key in _DISPLAY_TEXT_FIELDS and isinstance(value, str):
                    obj[key] = _replace_internal_terms(value, label_map)
                else:
                    visit(value)
        elif isinstance(obj, list):
            for item in obj:
                visit(item)

    visit(ontology)
    return ontology


def _display_text_style_issues(ontology: Dict[str, Any]) -> List[str]:
    """检查展示文本中是否泄露英文/内部术语；排除 qid_global 与简单数学符号。"""
    allowed = {'p', 'x'}
    issues: List[str] = []
    for text in _walk_display_texts(ontology):
        for token in _INTERNAL_TERM_RE.findall(text):
            lower = token.lower()
            if lower in allowed or re.fullmatch(r'p\d+', token, flags=re.IGNORECASE):
                continue
            if len(token) == 1 and token.isalpha() and token.islower():
                continue
            issues.append(f'display text contains internal/English term: {token}')
    return sorted(set(issues))


def _slim_session(memory: Dict[str, Any]) -> Dict[str, Any]:
    if memory.get('evidence_mode') == 'notes' or memory.get('material_type') == 'composition':
        from .material_markings import open_units
        units = open_units(memory, memory.get('material_type', 'notes'))
        return {
            'page_start': memory.get('page_start'), 'page_end': memory.get('page_end'),
            'session_title': memory.get('session_title', ''),
            'kp_observations': [
                {'kp': q.get('knowledge_point', ''), 'verdict': q.get('verdict'),
                 'evidence': [q['qid_global']]}
                for q in units if q['diagnostic_eligible'] or q['observation_eligible']
            ],
        }
    kp_freq = memory.get('knowledge_point_frequency', []) or []
    kp_trend = memory.get('kp_trend', {}) or {}
    kp_importance = memory.get('kp_importance', {}) or {}

    err_by_kp: Dict[str, List[Dict[str, Any]]] = {}
    for q in memory.get('error_questions', []) or []:
        kp = q.get('knowledge_point') or ''
        if not kp:
            continue
        err_by_kp.setdefault(kp, []).append(q)

    obs = []
    for entry in kp_freq:
        kp = entry['point']
        errs = err_by_kp.get(kp, [])
        evidence = [e['qid_global'] for e in errs if e.get('qid_global')][:5]
        error_types = [e.get('error_type', '') for e in errs if e.get('error_type')][:5]
        recurrence_hints = [e.get('recurrence_hint', 'na') for e in errs][:5]
        obs.append({
            'kp': kp,
            'total': entry['total_count'],
            'wrong': entry['error_count'],
            'correct_rate': entry.get('correct_rate', round(1 - entry.get('error_rate', 0), 4)),
            'error_types': error_types,
            'importance': kp_importance.get(kp, 'MID'),
            'trend_vs_prior': kp_trend.get(kp, 'new'),
            'recurrence_hints': recurrence_hints,
            'evidence': evidence,
        })

    try:
        page_start, page_end = session_page_bounds(memory)
    except Exception:
        page_start, page_end = None, None

    return {
        'order_index': memory.get('session_index'),
        'session_id': memory.get('session_id'),
        'page_start': page_start,
        'page_end': page_end,
        'session_title': memory.get('session_title', ''),
        'unit_title': memory.get('unit_title', ''),
        'module_title': memory.get('module_title', ''),
        'submodules': memory.get('submodules', []),
        'accuracy': (memory.get('accuracy') or {}).get('overall'),
        'question_count': memory.get('question_count'),
        'kp_observations': obs,
    }


def _slim_profile_baseline(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not profile:
        return {k: [] for k in ('stable_blind_spots', 'friction_zones', 'zpd_candidates', 'improved', 'erase_log')}
    keep = ('stable_blind_spots', 'friction_zones', 'zpd_candidates', 'improved', 'erase_log')
    return {k: profile.get(k, []) for k in keep}


def assemble_evidence_pack(
    subject: str,
    sample_id: str,
    sample_meta: Dict[str, Any],
    session_memories: List[Dict[str, Any]],
    profile: Optional[Dict[str, Any]],
*, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
        sample_meta = dict(sample_meta, subject=subject, grade=grade, stage=stage)
    timeline = [_slim_session(m) for m in session_memories]
    from .note_evidence import is_notes
    notes = is_notes(feedback_runtime)
    from .material_markings import open_material_runtime, open_units
    opened = open_material_runtime(feedback_runtime)
    observations = [q for m in session_memories for q in open_units(
        m, feedback_runtime.context['material_type'])] if opened else []
    return {
        'sample_meta': {
            'subject': sample_meta.get('subject') or subject,
            'grade': sample_meta.get('grade'),
            'stage': sample_meta.get('stage'),
            'sample_id': sample_id,
        },
        'temporal_assumption': 'document_order_only; no practice chronology' if opened else 'order_index ascending == chronological',
        'session_count': len(timeline),
        'session_timeline': timeline,
        'rule_baseline_profile': _slim_profile_baseline(None if opened else profile),
        **({'open_observations': observations, 'material_type': feedback_runtime.context['material_type']} if opened else {}),
        **({'evidence_mode': 'notes', 'note_observations': observations} if notes else {}),
    }


def _strip_json_text(raw: str) -> str:
    clean = (raw or '').strip()
    if clean.startswith('```'):
        lines = clean.splitlines()
        if lines and lines[0].strip().startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith('```'):
            lines = lines[:-1]
        clean = '\n'.join(lines).strip()
    if clean and not clean.startswith('{'):
        start = clean.find('{')
        end = clean.rfind('}')
        if start >= 0 and end > start:
            clean = clean[start:end + 1].strip()
    return clean


def _call_l5(
    evidence_pack: Dict[str, Any],
    subject: str,
    thinking_path: str,
    model: str = '',
    reasoning_effort: str = 'high',
    max_tokens: int = 32768,
    iteration_guidance: str = '',
*, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    active_model = str(model or '').strip() or homework_deepseek_model()
    client = _deepseek_client()
    from .feedback_model import runtime_client
    client = runtime_client(client, feedback_runtime, "deepseek")
    stage = evidence_pack['sample_meta'].get('stage')
    base_messages = [
        {'role': 'system', 'content': ontology_system(subject, stage, evidence_pack, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))},
        {
            'role': 'user',
            'content': ontology_user(evidence_pack) + (iteration_guidance or ''),
        },
    ]
    kwargs = {
        'model': active_model,
        'max_tokens': max_tokens,
        'response_format': {'type': 'json_object'},
        'extra_body': {'thinking': {'type': 'enabled'}, 'reasoning_effort': reasoning_effort},
    }
    from .model_output import request_json_object, validate_zones, object_list, optional_text_fields
    response_path = ((thinking_path[:-len('.thinking.txt')] if thinking_path.endswith('.thinking.txt') else thinking_path)
                     + '.responses.json') if thinking_path else ''
    open_evidence = 'open_observations' in evidence_pack or evidence_pack.get('evidence_mode') == 'notes'

    from .validation_issues import ValidationIssues, issue, raise_issues, ontology_repair_plan

    def validate(result):
        validate_zones(result.get('zones'))
        optional_text_fields(result, ('evolution_narrative',))
        for trajectory in object_list(result.get('mastery_trajectory') or [], 'mastery_trajectory'):
            optional_text_fields(trajectory, ('trend',))
            for point in object_list(trajectory.get('timeline') or [], 'timeline'):
                optional_text_fields(point, ('state',))
        issues = []
        if open_evidence:
            from .note_evidence import validate_note_ontology, normalize_annotation_context
            observations = evidence_pack.get('open_observations', evidence_pack.get('note_observations', []))
            for check in (normalize_annotation_context, validate_note_ontology):
                try:
                    check(result, observations)
                except ValidationIssues as exc:
                    issues.extend(exc.issues)
        else:
            valid_ids = _valid_qids_from_pack(evidence_pack)
            for bucket, entries in result['zones'].items():
                for index, entry in enumerate(entries):
                    refs = list(entry.get('evidence') or []) + list(entry.get('content_context_evidence') or [])
                    refs += [ref for group in entry.get('error_clusters') or [] for ref in group.get('evidence') or []]
                    if any(ref not in valid_ids for ref in refs):
                        issues.append(issue(ValueError('诊断引用不存在的单元'), f'/zones/{bucket}/{index}'))
        raise_issues(issues)
        return result

    def partial(data, error):
        from .partial_feedback import partial_ontology
        return partial_ontology(data, error, validate)

    def retry_hint(error):
        hint = ('请按输入单元的diagnostic_eligible与observation_eligible核对证据类型，'
                '主要标注只能引用observation_eligible=true；同页已确认回答另列content_context_evidence，'
                '没有标注依据则改用content评价。不得升级待确认状态或只删除引用而保留无据结论。'
                if open_evidence else '')
        return f'上次输出未满足协议：{error}。' + hint + '请修正后输出完整JSON对象，不含Markdown围栏。'

    return request_json_object(
        lambda current: client.chat.completions.create(messages=current, **kwargs), base_messages,
        parser=lambda raw: json.loads(_strip_json_text(raw)), validate=validate,
        audit_path=response_path, stage='整篇诊断', retry_prompt=retry_hint, thinking_path=thinking_path,
        repair_plan=ontology_repair_plan, on_exhausted=partial)


def _valid_qids_from_pack(pack: Dict[str, Any]) -> set:
    if 'open_observations' in pack:
        return {q['qid_global'] for q in pack['open_observations'] if q.get('qid_global')
                and (q.get('diagnostic_eligible') or q.get('observation_eligible'))}
    out: set = set()
    for s in pack.get('session_timeline', []) or []:
        for obs in s.get('kp_observations', []) or []:
            for ev in obs.get('evidence', []) or []:
                if ev:
                    out.add(ev)
    return out


def _sanitize_ontology_evidence(ontology: Dict[str, Any], evidence_pack: Dict[str, Any]) -> Dict[str, Any]:
    """落盘前净化 L5 证据，防止占位题号污染 Pass2 和前端报告。"""
    valid_qids = _valid_qids_from_pack(evidence_pack)
    zones = ontology.get('zones') or {}
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        for entry in zones.get(bucket, []) or []:
            kp = str(entry.get('knowledge_point') or '').strip().lower()
            is_no_observed = kp in {'', 'none', 'no_observed', '无', '无显著盲区', '无显著内耗'}
            if is_no_observed and bucket in {'blind_spot', 'friction_zone'}:
                entry['knowledge_point'] = 'no_observed'
                entry['curriculum_id'] = ''
                entry['evidence'] = []
                entry['error_clusters'] = []
                if 'content_context_evidence' in entry:
                    entry['content_context_evidence'] = []
                entry.setdefault('fallback', 'no_observed')
                continue

            if 'evidence' in entry:
                entry['evidence'] = [
                    q for q in (entry.get('evidence') or []) if q in valid_qids
                ]
            if 'content_context_evidence' in entry:
                entry['content_context_evidence'] = [q for q in entry['content_context_evidence'] if q in valid_qids]
            for cluster in entry.get('error_clusters', []) or []:
                cluster['evidence'] = [
                    q for q in (cluster.get('evidence') or []) if q in valid_qids
                ]
    return ontology


def _validate_schema(ontology: Dict[str, Any], evidence_pack: Dict[str, Any]) -> List[str]:
    warns: List[str] = []
    for key in ('subject', 'sample_id', 'session_count', 'mastery_trajectory', 'zones', 'evolution_narrative'):
        if key not in ontology:
            warns.append(f'missing top-level field: {key}')
    valid_qids = _valid_qids_from_pack(evidence_pack)
    zones = ontology.get('zones') or {}
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        for entry in zones.get(bucket, []) or []:
            ev_list: List[str] = list(entry.get('evidence') or []) + list(entry.get('content_context_evidence') or [])
            for ec in entry.get('error_clusters', []) or []:
                ev_list.extend(ec.get('evidence', []) or [])
            for q in ev_list:
                if q not in valid_qids:
                    warns.append(f'{bucket}: unknown qid_global {q!r}')
            tr = entry.get('trend')
            if tr and tr not in _VALID_TRENDS:
                warns.append(f'{bucket}: invalid trend {tr!r}')
            st = entry.get('stability')
            if st and st not in _VALID_STABILITY:
                warns.append(f'{bucket}: invalid stability {st!r}')
    for mt in ontology.get('mastery_trajectory', []) or []:
        for tl in mt.get('timeline', []) or []:
            s = tl.get('state')
            if s and s not in _VALID_STATES:
                warns.append(f'mastery_trajectory: invalid state {s!r}')
        if mt.get('trend') and mt['trend'] not in _VALID_TRENDS:
            warns.append(f'mastery_trajectory: invalid trend {mt.get("trend")!r}')
    return warns


def _pick_zpd_fallback_kp(evidence_pack: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    baseline = evidence_pack.get('rule_baseline_profile') or {}
    for c in baseline.get('zpd_candidates', []) or []:
        kp = c.get('knowledge_point')
        if kp:
            return {
                'knowledge_point': kp,
                'curriculum_id': (c.get('curriculum_ids') or [''])[0],
                'stability': 'transient',
                'evidence': list(c.get('evidence_question_ids', []))[:3],
                'first_session': c.get('latest_session'),
                'last_session': c.get('latest_session'),
                'trend': c.get('trend') or 'improving',
                'rationale': (
                    f"规则基线显示 {kp} 最近正确率 {c.get('latest_accuracy')}，趋势 "
                    f"{c.get('trend','improving')}，稍加巩固即可突破——作为 ZPD 兜底建议。"
                ),
                'suggested_next_step': f'再练 2–3 道 {kp} 相关题，重点核对易错环节。',
                'confidence': 0.5,
                'fallback': 'rule_baseline',
            }
    for s in reversed(evidence_pack.get('session_timeline', []) or []):
        for obs in s.get('kp_observations', []):
            if obs.get('trend_vs_prior') == 'improving':
                kp = obs['kp']
                return {
                    'knowledge_point': kp,
                    'curriculum_id': '',
                    'stability': 'transient',
                    'evidence': list(obs.get('evidence', []))[:3],
                    'first_session': s.get('order_index'),
                    'last_session': s.get('order_index'),
                    'trend': 'improving',
                    'rationale': f"第 {s.get('order_index')} 次练习中 {kp} 出现 improving 趋势，选作 ZPD 兜底建议。",
                    'suggested_next_step': f'再练 2–3 道 {kp} 相关题，巩固进步。',
                    'confidence': 0.4,
                    'fallback': 'timeline_improving',
                }
    return None


def _generic_zpd_extension(subject: str) -> Dict[str, Any]:
    text_by_subject = {
        'math': '本份作业整体表现良好。建议从拓展提升角度切入：尝试一道结合实际情境的应用题，练习把数学方法用到陌生场景，发展模型意识。',
        'chinese': '本份作业整体表现良好。建议从拓展提升角度切入：阅读一篇略高于本年级难度的短文，练习概括主旨与品味语言，发展审美鉴赏。',
        'english': '本份作业整体表现良好。建议从拓展提升角度切入：尝试用本单元词汇造一段 3–5 句的小短文，练习表达连贯性。',
    }
    return {
        'knowledge_point': 'extension_recommendation',
        'curriculum_id': '',
        'stability': 'transient',
        'evidence': [],
        'first_session': None,
        'last_session': None,
        'trend': 'improving',
        'rationale': text_by_subject.get(subject, text_by_subject['math']),
        'suggested_next_step': '尝试一道略高于当前难度的拓展题，体会方法在新情境下的应用。',
        'confidence': 0.3,
        'fallback': 'generic_extension',
    }


def _generic_blind_or_friction_placeholder(bucket: str) -> Dict[str, Any]:
    return {
        'knowledge_point': 'no_observed',
        'curriculum_id': '',
        'evidence': [],
        'error_clusters': [],
        'stability': 'transient',
        'first_session': None,
        'last_session': None,
        'trend': 'stable',
        'rationale': (
            f"本份作业未观察到显著{('盲区' if bucket=='blind_spot' else '内耗')}，建议保持现有学习节奏，下次评估再观察。"
        ),
        'confidence': 0.2,
        'fallback': 'no_observed',
    }


def _ensure_non_empty(ontology: Dict[str, Any], evidence_pack: Dict[str, Any], *, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None:
        return _runtime_ontology(ontology, evidence_pack, feedback_runtime)
    zones = ontology.setdefault('zones', {})
    fallback_used = False
    for bucket in ('blind_spot', 'friction_zone'):
        zones.setdefault(bucket, [])
        if not zones[bucket]:
            zones[bucket].append(_generic_blind_or_friction_placeholder(bucket))
            fallback_used = True
    zones.setdefault('zpd', [])
    if not zones['zpd']:
        picked = _pick_zpd_fallback_kp(evidence_pack)
        if picked is None:
            picked = _generic_zpd_extension(evidence_pack.get('sample_meta', {}).get('subject', 'math'))
        zones['zpd'].append(picked)
        fallback_used = True
    ontology['non_empty_guaranteed'] = True
    ontology['fallback_used'] = fallback_used
    return ontology


def _runtime_ontology(ontology, pack, runtime):
    """三区保留结构，结论必须有现有题号证据；无观察不伪造拓展结论。"""
    valid = _valid_qids_from_pack(pack)
    if 'open_observations' in pack or pack.get('evidence_mode') == 'notes':
        from .note_evidence import validate_note_ontology, normalize_annotation_context
        observations = pack.get('open_observations', pack.get('note_observations', []))
        normalize_annotation_context(ontology, observations)
        validate_note_ontology(ontology, observations)
    zones = ontology.setdefault('zones', {})
    for bucket in ('blind_spot', 'friction_zone', 'zpd'):
        kept = []
        for entry in zones.get(bucket, []) or []:
            if not isinstance(entry, dict):
                continue
            evidence = [q for q in entry.get('evidence', []) if q in valid]
            for cluster in entry.get('error_clusters', []) or []:
                cluster['evidence'] = [q for q in cluster.get('evidence', []) if q in valid]
                evidence.extend(cluster['evidence'])
            if entry.get('knowledge_point') != 'no_observed' and evidence:
                entry['evidence'] = list(dict.fromkeys(evidence))
                kept.append(entry)
        zones[bucket] = kept or [{'knowledge_point': 'no_observed', 'curriculum_id': '',
            'evidence': [], 'error_clusters': [], 'rationale': '现有材料中暂无足够观察证据。',
            'suggested_next_step': '补充可定位的作答证据后再判断。', 'fallback': 'no_observed'}]
    ontology.setdefault('mastery_trajectory', [])
    ontology.setdefault('evolution_narrative', '依据本份材料中的可定位证据记录学习情况。')
    ontology['subject'] = runtime.context['subject_code']
    ontology['grade'] = runtime.context.get('grade_global')
    ontology['stage'] = runtime_attributes(runtime)[2]
    ontology['non_empty_guaranteed'] = True
    ontology['fallback_used'] = any(zones[b][0].get('knowledge_point') == 'no_observed' for b in zones)
    ontology.setdefault('status', 'completed')
    return stamp_feedback(ontology, runtime, 'ontology')


def build_ontology(
    subject: str,
    sample_id: str,
    base_dir: str,
    report_dir: str,
    sample_meta: Dict[str, Any],
    session_memories: List[Dict[str, Any]],
    profile: Optional[Dict[str, Any]] = None,
    model: str = '',
    reasoning_effort: str = 'high',
    iteration_guidance: str = '',
    pass1_dir: str = '',
*, feedback_runtime=None) -> Optional[Dict[str, Any]]:
    """构建诊断；冻结运行失败时返回显式failed，旧链路仍返回None。"""
    if feedback_runtime is not None:
        subject, grade, stage = runtime_attributes(feedback_runtime)
        sample_meta = dict(sample_meta, subject=subject, grade=grade, stage=stage)
        for item in session_memories:
            if not artifact_compatible(item, feedback_runtime):
                raise ValueError('诊断记忆配置不一致')
    if not session_memories and feedback_runtime is not None:
        result = _runtime_ontology({'status': 'insufficient_evidence'}, {}, feedback_runtime)
        safe_json_dump(os.path.join(base_dir, 'student_ontology.json'), result)
        return result
    if not session_memories:
        logger.warning('[L5] 无 session_memories，跳过 ontology 构建')
        return None
    try:
        pack = assemble_evidence_pack(subject, sample_id, sample_meta, session_memories, profile, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        # 注入逐题白灰黑交叉可信度，供 L5 按分层取证/措辞
        try:
            from .wgb_trust import build_wgb_trust_summary
            mt = 'homework'
            if feedback_runtime is not None:
                mt = str((feedback_runtime.context or {}).get('material_type') or 'homework')
            p1 = pass1_dir or ''
            if not p1 and base_dir:
                for cand in (
                    os.path.join(base_dir, 'pass1_json'),
                    os.path.join(os.path.dirname(base_dir), 'pass1_json'),
                ):
                    if os.path.isdir(cand):
                        p1 = cand
                        break
            trust = build_wgb_trust_summary(p1, subject, material_type=mt) if p1 else {}
            if trust:
                pack['wgb_trust'] = {
                    'total_units': trust.get('total_units'),
                    'tier_counts': trust.get('tier_counts'),
                    'cross_counts': trust.get('cross_counts'),
                    'critical': (trust.get('critical') or [])[:40],
                    'careful': (trust.get('careful') or [])[:40],
                    'need_verify': (trust.get('need_verify') or [])[:60],
                    'by_qid': trust.get('by_qid') or {},
                    'material_type': trust.get('material_type') or mt,
                    'unit_word': trust.get('unit_word'),
                    'protocol_hint': trust.get('protocol_hint'),
                    'confident_count': trust.get('confident_count'),
                    'normal_count': trust.get('normal_count'),
                }
        except Exception as exc:
            logger.warning('[L5] wgb_trust 注入失败（不阻断）: %s', exc)
        evidence_path = os.path.join(base_dir, 'student_ontology_evidence.json')
        safe_json_dump(evidence_path, stamp_feedback(pack, feedback_runtime, 'ontology_evidence'))

        thinking_path = os.path.join(report_dir, f'{subject}_{sample_id}_ontology.thinking.txt')
        ontology = _call_l5(
            pack,
            subject,
            thinking_path,
            model=model,
            reasoning_effort=reasoning_effort,
            iteration_guidance=iteration_guidance,
        **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))

        if feedback_runtime is not None:
            ontology['subject'] = subject
        ontology.setdefault('subject', subject)
        ontology.setdefault('sample_id', sample_id)
        ontology['grade'] = pack['sample_meta'].get('grade')
        ontology['stage'] = pack['sample_meta'].get('stage')
        ontology['session_count'] = pack['session_count']
        ontology['built_at'] = dt.datetime.now().isoformat(timespec='seconds')
        ontology['built_by'] = f'ontology_builder/{model}/{reasoning_effort}'
        if feedback_runtime is not None:
            from .feedback_model import model_spec
            ontology['built_by'] = 'ontology_builder/' + model_spec(feedback_runtime, 'deepseek')['model']
        ontology = _sanitize_ontology_evidence(ontology, pack)
        if pack.get('wgb_trust'):
            # 持久化到 ontology，供 Pass2 / 诊断卡 / 独立界面读取
            ontology['wgb_trust'] = pack['wgb_trust']

        warns = _validate_schema(ontology, pack)
        if warns:
            ontology['_validation_warnings'] = warns
            for w in warns[:10]:
                logger.warning('[L5] schema warning: %s', w)

        ontology = _ensure_non_empty(ontology, pack, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        ontology = _sanitize_ontology_evidence(ontology, pack)
        if feedback_runtime is None:
            ontology = _polish_display_texts(ontology, subject)

        style_issues = _display_text_style_issues(ontology)
        if style_issues:
            ontology['_style_warnings'] = style_issues
            for w in style_issues[:10]:
                logger.warning('[L5] style warning: %s', w)
        else:
            ontology.pop('_style_warnings', None)

        out_path = os.path.join(base_dir, 'student_ontology.json')
        safe_json_dump(out_path, stamp_feedback(ontology, feedback_runtime, 'ontology'))
        logger.info('[L5] ontology saved: %s fallback_used=%s', out_path, ontology.get('fallback_used'))
        return ontology
    except Exception as exc:
        traceback.print_exc()
        logger.warning('[L5] 诊断失败%s: %s', '，将保存失败状态' if feedback_runtime is not None else '，返回旧链路兜底', exc)
        if feedback_runtime is not None:
            result = _runtime_ontology({'status': 'failed', 'error': str(exc)}, {}, feedback_runtime)
            safe_json_dump(os.path.join(base_dir, 'student_ontology.json'), result)
            return result
        return None


def polish_existing_ontology(base_dir: str, subject: str) -> Optional[Dict[str, Any]]:
    """只审校既有 student_ontology.json 的展示文本，不调用模型。"""
    out_path = os.path.join(base_dir, 'student_ontology.json')
    if not os.path.exists(out_path):
        logger.warning('[L5] 无既有 ontology 可审校: %s', out_path)
        return None
    try:
        with open(out_path, 'r', encoding='utf-8') as file:
            ontology = json.load(file)
        ontology = _polish_display_texts(ontology, subject)
        style_issues = _display_text_style_issues(ontology)
        if style_issues:
            ontology['_style_warnings'] = style_issues
        else:
            ontology.pop('_style_warnings', None)
        safe_json_dump(out_path, ontology)
        return ontology
    except Exception as exc:
        traceback.print_exc()
        logger.warning('[L5] 既有 ontology 审校失败: %s', exc)
        return None
