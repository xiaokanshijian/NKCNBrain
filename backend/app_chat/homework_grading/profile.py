"""规则基线聚合（M-Mid → L4 baseline，nkcn 自有，改编自 yq v2.5 profile_builder）。

将一份作业的所有 session memory 聚合为 L5 evidence 所需的规则基线：
stable_blind_spots / friction_zones / zpd_candidates / improved / erase_log。
该结果不是对外并列的综合画像，默认只内嵌到 student_ontology_evidence.json。
"""

from __future__ import annotations
from .stage_dependencies import artifact_compatible

import datetime as dt
import glob
from .feedback_runtime import stamp_feedback
from .feedback_curriculum import curriculum_entries

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app_chat.homework_grading.curriculum import label_to_id_map
from app_chat.homework_grading.utils import safe_json_dump, safe_json_load


def _classify_kp_zone(entry: Dict[str, Any], kp_importance: str, kp_trend: str) -> Optional[str]:
    err = entry.get('error_rate', 0)
    err_count = entry.get('error_count', 0)
    total = entry.get('total_count', 0)
    correct = total - err_count
    if total == 0:
        return None
    if correct == 0 and err_count > 0:
        return 'blind_spot'
    if err > 0.4 and correct >= 1:
        return 'friction_zone'
    if kp_importance == 'LOW':
        return 'zpd'
    if kp_trend == 'improving' and (1 - err) >= 0.6:
        return 'zpd'
    return None


def _load_session_memories(report_dir: str, subject: str, sample_id: str) -> List[Dict[str, Any]]:
    pattern = os.path.join(report_dir, f'{subject}_{sample_id}_s*_memory.json')
    files = glob.glob(pattern)

    def _idx(path: str) -> int:
        m = re.search(r'_s(\d+)_memory\.json$', os.path.basename(path))
        return int(m.group(1)) if m else 0

    files.sort(key=_idx)
    return [safe_json_load(p) for p in files]


def _evidence_for_kp(session: Dict[str, Any], kp: str, limit: int = 5) -> List[str]:
    out: List[str] = []
    for q in session.get('error_questions', []):
        if q.get('knowledge_point') == kp:
            qid = q.get('qid_global')
            if not qid and q.get('page') and q.get('id'):
                qid = f"p{q['page']}:{q['id']}"
            if qid:
                out.append(str(qid))
            if len(out) >= limit:
                break
    return out


def _confidence(session_count: int, streak: int) -> float:
    base = session_count / max(2, session_count + 1)
    return round(min(1.0, base + 0.05 * streak), 3)


def _longest_streak(indices: List[int]) -> int:
    if not indices:
        return 0
    indices = sorted(set(indices))
    longest = run = 1
    for i in range(1, len(indices)):
        if indices[i] == indices[i - 1] + 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    return longest


def build_student_profile(report_dir: str, subject: str, sample_id: str, *, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    sessions = _load_session_memories(report_dir, subject, sample_id)
    if feedback_runtime is not None:
        for item in sessions:
            if not artifact_compatible(item, feedback_runtime):
                raise ValueError('规则画像的记忆配置不一致')
    if not sessions:
        return stamp_feedback({
            'subject': subject, 'sample_id': sample_id,
            'built_at': dt.datetime.now().isoformat(timespec='seconds'),
            'session_count': 0, 'session_index_range': [0, 0],
            'stable_blind_spots': [], 'friction_zones': [],
            'zpd_candidates': [], 'improved': [], 'erase_log': [],
        }, feedback_runtime, 'profile')
    label_to_id = ({e['label']: e['id'] for e in curriculum_entries(feedback_runtime)}
                   if feedback_runtime is not None else label_to_id_map(subject))

    zones_by_kp: Dict[str, List[Tuple[int, str]]] = {}
    last_acc_by_kp: Dict[str, Tuple[int, float]] = {}
    evidence_by_kp_zone: Dict[Tuple[str, str], List[str]] = {}

    for sm in sessions:
        si = sm['session_index']
        kp_imp = sm.get('kp_importance', {})
        kp_trend = sm.get('kp_trend', {})
        for entry in sm.get('knowledge_point_frequency', []):
            kp = entry['point']
            zone = _classify_kp_zone(entry, kp_imp.get(kp, 'MID'), kp_trend.get(kp, 'stable'))
            if zone:
                zones_by_kp.setdefault(kp, []).append((si, zone))
                ev = evidence_by_kp_zone.setdefault((kp, zone), [])
                if len(ev) < 5:
                    ev.extend(_evidence_for_kp(sm, kp, limit=5 - len(ev)))
            last_acc_by_kp[kp] = (si, 1 - entry.get('error_rate', 0))

    stable_blind_spots: List[Dict[str, Any]] = []
    friction_zones: List[Dict[str, Any]] = []
    zpd_candidates: List[Dict[str, Any]] = []
    improved: List[Dict[str, Any]] = []
    latest_si = sessions[-1]['session_index']

    for kp, observations in zones_by_kp.items():
        blind_idx = [si for si, z in observations if z == 'blind_spot']
        friction_idx = [si for si, z in observations if z == 'friction_zone']
        zpd_idx = [si for si, z in observations if z == 'zpd']
        cur_si, latest_acc = last_acc_by_kp[kp]
        cids = [label_to_id[kp]] if kp in label_to_id else []

        earlier_negative = [si for si in blind_idx + friction_idx if si < cur_si]
        if earlier_negative and latest_acc >= 0.6:
            improved.append({
                'knowledge_point': kp, 'curriculum_ids': cids,
                'earlier_state': 'blind_spot' if blind_idx and min(blind_idx) < cur_si else 'friction_zone',
                'earlier_session': min(earlier_negative), 'latest_session': cur_si,
                'latest_accuracy': round(latest_acc, 3),
            })
            continue

        if len(blind_idx) >= 2:
            streak = _longest_streak(blind_idx)
            stable_blind_spots.append({
                'knowledge_point': kp, 'curriculum_ids': cids,
                'first_seen_session': min(blind_idx), 'last_seen_session': max(blind_idx),
                'session_count': len(blind_idx), 'consecutive_streak': streak,
                'confidence': _confidence(len(blind_idx), streak),
                'evidence_question_ids': evidence_by_kp_zone.get((kp, 'blind_spot'), []),
            })
        if len(friction_idx) >= 2:
            streak = _longest_streak(friction_idx)
            friction_zones.append({
                'knowledge_point': kp, 'curriculum_ids': cids,
                'session_count': len(friction_idx), 'consecutive_streak': streak,
                'latest_accuracy': round(latest_acc, 3),
                'confidence': _confidence(len(friction_idx), streak),
                'evidence_question_ids': evidence_by_kp_zone.get((kp, 'friction_zone'), []),
            })
        if zpd_idx and zpd_idx[-1] == latest_si:
            trend = sessions[-1].get('kp_trend', {}).get(kp, 'stable')
            zpd_candidates.append({
                'knowledge_point': kp, 'curriculum_ids': cids,
                'latest_session': cur_si, 'latest_accuracy': round(latest_acc, 3),
                'trend': trend, 'evidence_question_ids': evidence_by_kp_zone.get((kp, 'zpd'), []),
            })

    # erase_log：LOW importance 且连续 ≥2 个会话缺席
    absence_count: Dict[str, int] = {}
    last_seen: Dict[str, int] = {}
    erase_log: List[Dict[str, Any]] = []
    erased_already: set = set()
    for sm in sessions:
        si = sm['session_index']
        present = {e['point'] for e in sm.get('knowledge_point_frequency', [])}
        for kp in present:
            absence_count[kp] = 0
            last_seen[kp] = si
        for ec in sm.get('erase_candidates', []):
            kp = ec['knowledge_point']
            absence_count[kp] = absence_count.get(kp, 0) + 1
            if absence_count[kp] >= 2 and kp not in erased_already:
                erase_log.append({
                    'knowledge_point': kp,
                    'curriculum_ids': [label_to_id[kp]] if kp in label_to_id else [],
                    'last_seen_session': last_seen.get(kp), 'erased_at_session': si,
                    'reason': 'LOW importance, absent for >=2 consecutive sessions',
                })
                erased_already.add(kp)

    stable_blind_spots.sort(key=lambda x: x['confidence'], reverse=True)
    friction_zones.sort(key=lambda x: x['confidence'], reverse=True)
    zpd_candidates.sort(key=lambda x: x['latest_accuracy'], reverse=True)
    improved.sort(key=lambda x: x['latest_accuracy'], reverse=True)

    return stamp_feedback({
        'subject': subject, 'sample_id': sample_id,
        'built_at': dt.datetime.now().isoformat(timespec='seconds'),
        'session_count': len(sessions),
        'session_index_range': [sessions[0]['session_index'], latest_si],
        'stable_blind_spots': stable_blind_spots,
        'friction_zones': friction_zones,
        'zpd_candidates': zpd_candidates,
        'improved': improved,
        'erase_log': erase_log,
    }, feedback_runtime, 'profile')


def save_rule_baseline_profile(profile: Dict[str, Any], report_dir: str, subject: str, sample_id: str) -> str:
    path = os.path.join(report_dir, f'{subject}_{sample_id}_rule_baseline_profile.json')
    safe_json_dump(path, profile)
    return path


def save_student_profile(profile: Dict[str, Any], report_dir: str, subject: str, sample_id: str) -> str:
    """兼容旧调用名；Stage 3.5 起写入规则基线调试路径。"""
    return save_rule_baseline_profile(profile, report_dir, subject, sample_id)
