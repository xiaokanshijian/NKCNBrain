"""Pass3 双科交叉诊断编排（nkcn 自有）。

负责：在 CI 索引中配对同一学生两份不同学科的已完成作业批改 →
加载各自 memory + pass2 report → 调用 pass3.cross_subject_analyze →
落盘并在索引登记 analysis_type='cross_subject'。
"""

from __future__ import annotations

import datetime
import hashlib
import os
import traceback
from typing import Any, Dict, List, Optional, Tuple

from app_chat.ci._utils import _ci_dmt_root, _update_task
from app_chat.ci.index_manager import CIIndexManager
from app_chat.homework_grading.service import prepare_homework_workspace, _sample_id
from app_chat.homework_grading.pass3 import cross_subject_analyze
from app_chat.homework_grading.utils import SUBJECT_LABELS, safe_json_dump, safe_json_load

CROSS_ANALYSIS_TYPE = 'cross_subject'


def is_cross_subject_analysis_id(analysis_id: str) -> bool:
    return str(analysis_id or '').startswith('cross_')


def build_cross_analysis_id(analysis_id_a: str, analysis_id_b: str) -> str:
    key = '|'.join(sorted([analysis_id_a, analysis_id_b]))
    digest = hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]
    return f'cross_{digest}'


def _completed_homework_records(username: str) -> List[Dict[str, Any]]:
    out = []
    for rec in CIIndexManager.load(username):
        if rec.get('analysis_type') == 'homework_grading' and rec.get('status') == 'completed':
            subject = rec.get('homework_subject') or 'unknown'
            if subject and subject != 'unknown':
                out.append(rec)
    return out


def find_pass3_pairs(username: str) -> List[Dict[str, Any]]:
    """返回可进行双科交叉的候选配对（不同学科，两两组合）。"""
    records = _completed_homework_records(username)
    pairs: List[Dict[str, Any]] = []
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            ra, rb = records[i], records[j]
            sa = ra.get('homework_subject')
            sb = rb.get('homework_subject')
            if sa == sb:
                continue
            cross_id = build_cross_analysis_id(ra['analysis_id'], rb['analysis_id'])
            existing = CIIndexManager.find_by_id(username, cross_id)
            pairs.append({
                'cross_analysis_id': cross_id,
                'analysis_id_a': ra['analysis_id'],
                'analysis_id_b': rb['analysis_id'],
                'subject_a': sa,
                'subject_b': sb,
                'subject_a_label': SUBJECT_LABELS.get(sa, sa),
                'subject_b_label': SUBJECT_LABELS.get(sb, sb),
                'files_a': ra.get('files', []),
                'files_b': rb.get('files', []),
                'status': (existing or {}).get('status', 'none'),
            })
    return pairs


def _load_memory_and_report(username: str, analysis_id: str) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    rec = CIIndexManager.find_by_id(username, analysis_id)
    if not rec:
        raise ValueError(f'分析记录不存在: {analysis_id}')
    subject = rec.get('homework_subject') or 'unknown'
    paths = prepare_homework_workspace(username, analysis_id)
    sample_id = _sample_id(analysis_id)
    report_dir = paths['pass2_report']
    memory_path = os.path.join(report_dir, f'{subject}_{sample_id}_memory.json')
    report_path = os.path.join(report_dir, f'{subject}_{sample_id}_report.json')
    if not os.path.exists(memory_path) or not os.path.exists(report_path):
        raise ValueError(f'{SUBJECT_LABELS.get(subject, subject)} 作业批改结果不完整，无法进行交叉分析')
    return subject, safe_json_load(memory_path), safe_json_load(report_path)


def _cross_paths(username: str, cross_id: str) -> Dict[str, str]:
    root = os.path.join(_ci_dmt_root(username), cross_id)
    base = os.path.join(root, 'cross_subject')
    os.makedirs(base, exist_ok=True)
    return {
        'root': root,
        'base': base,
        'manifest': os.path.join(root, 'manifest.json'),
        'report': os.path.join(base, 'cross_subject_report.json'),
        'summary': os.path.join(base, 'summary.md'),
        'thinking': os.path.join(base, 'thinking.txt'),
    }


def run_pass3(task_id: str, username: str, analysis_id_a: str, analysis_id_b: str) -> None:
    cross_id = build_cross_analysis_id(analysis_id_a, analysis_id_b)
    paths = _cross_paths(username, cross_id)
    now = datetime.datetime.now().isoformat()
    CIIndexManager.add_or_update(username, {
        'analysis_id': cross_id,
        'mode': 'cross',
        'analysis_type': CROSS_ANALYSIS_TYPE,
        'source_analysis_ids': [analysis_id_a, analysis_id_b],
        'status': 'running',
        'created_at': now,
        'updated_at': now,
    })
    try:
        _update_task(task_id, current_item=0, total_items=2, current_section='加载双科批改结果', completed=False, error='')
        subject_a, memory_a, report_a = _load_memory_and_report(username, analysis_id_a)
        subject_b, memory_b, report_b = _load_memory_and_report(username, analysis_id_b)
        student_id = username or 'student'

        _update_task(task_id, current_item=1, total_items=2, current_section='生成双科交叉诊断')
        result = cross_subject_analyze(
            student_id, subject_a, subject_b,
            memory_a, memory_b, report_a, report_b,
            paths['base'],
        )

        manifest = {
            'analysis_type': CROSS_ANALYSIS_TYPE,
            'group_id': cross_id,
            'username': username,
            'mode': 'cross',
            'source_analysis_ids': [analysis_id_a, analysis_id_b],
            'subject_a': subject_a,
            'subject_b': subject_b,
            'subject_a_label': SUBJECT_LABELS.get(subject_a, subject_a),
            'subject_b_label': SUBJECT_LABELS.get(subject_b, subject_b),
            'status': 'completed',
            'created_at': now,
            'updated_at': datetime.datetime.now().isoformat(),
        }
        safe_json_dump(paths['manifest'], manifest)
        CIIndexManager.update_status(username, cross_id, 'completed')
        _update_task(task_id, current_item=2, total_items=2, current_section='完成', completed=True, error='')
        _ = result
    except Exception as exc:
        traceback.print_exc()
        _update_task(task_id, current_section='失败', completed=True, error=str(exc))
        CIIndexManager.update_status(username, cross_id, 'failed')


def get_pass3_result(username: str, analysis_id: str) -> Optional[Dict[str, Any]]:
    rec = CIIndexManager.find_by_id(username, analysis_id)
    paths = _cross_paths(username, analysis_id)
    if not os.path.exists(paths['manifest']):
        return None
    manifest = safe_json_load(paths['manifest'])
    report = safe_json_load(paths['report']) if os.path.exists(paths['report']) else {}
    summary_md = ''
    if os.path.exists(paths['summary']):
        with open(paths['summary'], 'r', encoding='utf-8') as f:
            summary_md = f.read()
    return {
        'analysis_id': analysis_id,
        'analysis_type': CROSS_ANALYSIS_TYPE,
        'status': (rec or manifest).get('status', 'completed'),
        'subject_a': manifest.get('subject_a'),
        'subject_b': manifest.get('subject_b'),
        'subject_a_label': manifest.get('subject_a_label'),
        'subject_b_label': manifest.get('subject_b_label'),
        'source_analysis_ids': manifest.get('source_analysis_ids', []),
        'cross_subject_report': report,
        'summary_md': summary_md,
    }
