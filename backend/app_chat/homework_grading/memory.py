from .feedback_runtime import stamp_feedback
from .feedback_verification import validate_page

import collections
import copy
import os
import re
from typing import Any, Dict, List

from app_chat.homework_grading.utils import make_qid_global, parse_page_num, safe_json_load, safe_json_dump, sorted_json_pages
from app_chat.homework_grading.semantic_config import importance_of, max_importance


ERROR_VERDICTS = {'wrong', 'partial', 'uncertain', 'unanswered'}
_LISTENING_PATTERN = re.compile(r'听力|听写|\blisten', re.IGNORECASE)


def _is_listening_question(question: Dict[str, Any]) -> bool:
    for field in ('stem_excerpt', 'error_type', 'knowledge_point'):
        if _LISTENING_PATTERN.search(str(question.get(field) or '')):
            return True
    return False


def aggregate_pages(page_files: List[str], *, feedback_runtime=None) -> Dict[str, Any]:
    """聚合一组 Pass1 页面 JSON，产出 memory 主体（不含 subject/sample_id 包装）。"""
    from .feedback_material_kinds import is_open_material
    open_material = bool(
        feedback_runtime is not None
        and is_open_material((feedback_runtime.context or {}).get('material_type'))
    )
    from .note_evidence import is_notes, normalize_note_fields, NOTE_FIELDS
    from .material_markings import MARKING_FIELDS, normalize_markings
    notes = is_notes(feedback_runtime)
    question_count = 0
    verdict_dist: Dict[str, int] = collections.defaultdict(int)
    accuracy_by_page: Dict[str, float] = {}
    error_questions: List[Dict[str, Any]] = []
    kp_errors: Dict[str, int] = collections.defaultdict(int)
    kp_total: Dict[str, int] = collections.defaultdict(int)
    kp_importance_levels: Dict[str, List[str]] = collections.defaultdict(list)
    error_type_dist: Dict[str, int] = collections.defaultdict(int)
    listening_skipped_count = 0
    cross_page_uncertain_count = 0
    page_understanding = []

    for page_file in page_files:
        page_data = safe_json_load(page_file)
        if feedback_runtime is not None:
            validate_page(page_data, feedback_runtime)
        page_num = page_data.get('page') or parse_page_num(os.path.basename(page_file))
        questions = page_data.get('questions') or []
        from .page_feedback import page_evidence
        page_understanding.append(page_evidence(page_data, page_num))
        page_correct = 0
        for question in questions:
            if open_material:
                question = normalize_markings(copy.deepcopy(question))
            if notes:
                question = normalize_note_fields(copy.deepcopy(question))
            eligible = not notes or question['diagnostic_eligible']
            question_count += 1
            verdict = str(question.get('verdict') or 'uncertain')
            verdict_dist[verdict] += 1
            knowledge_point = str(question.get('knowledge_point') or '').strip()
            if knowledge_point and eligible:
                kp_total[knowledge_point] += 1
            if verdict == 'correct':
                page_correct += 1
            include_for_feedback = verdict in ERROR_VERDICTS or (open_material and verdict == 'correct')
            if include_for_feedback:
                error_type = str(question.get('error_type') or '').strip()
                if verdict == 'uncertain' and not open_material and _is_listening_question(question):
                    listening_skipped_count += 1
                    continue
                if verdict == 'uncertain' and question.get('cross_page') and not question.get('cross_page_resolved'):
                    cross_page_uncertain_count += 1
                    if not open_material:
                        continue
                if verdict == 'uncertain' and not knowledge_point and not error_type and not open_material:
                    continue
                if knowledge_point and eligible and verdict in ERROR_VERDICTS:
                    kp_errors[knowledge_point] += 1
                    kp_importance_levels[knowledge_point].append(importance_of(error_type))
                if error_type and eligible and verdict in ERROR_VERDICTS:
                    error_type_dist[error_type] += 1
                entry = {
                    'cross_page': bool(question.get('cross_page')),
                    'cross_page_note': question.get('cross_page_note') or '',
                    'cross_page_resolved': bool(question.get('cross_page_resolved')),
                    'page': page_num,
                    'id': question.get('id'),
                    'qid_global': make_qid_global(page_num, question.get('id')),
                    'recurrence_hint': str(question.get('recurrence_hint') or 'na'),
                    'verdict': verdict,
                    'stem_excerpt': question.get('stem_excerpt', ''),
                    'student_answer': question.get('student_answer', ''),
                    'understanding': question.get('understanding', ''),
                    'correct_answer': question.get('correct_answer'),
                    'error_type': error_type,
                    'knowledge_point': knowledge_point,
                    'is_application_major_problem': bool(question.get('is_application_major_problem')),
                    'position': question.get('position', []),
                    'importance': importance_of(error_type),
                }
                if notes:
                    entry.update({key: question[key] for key in NOTE_FIELDS})
                    entry['page_origin'] = page_data.get('page_origin', {})
                if open_material:
                    entry.update({key: copy.deepcopy(question[key]) for key in (*MARKING_FIELDS, 'note_role') if key in question})
                if verdict == 'uncertain':
                    entry['uncertain_reason'] = (
                        'cross_page_attempted'
                        if question.get('cross_page_resolved')
                        else 'cross_page_unresolved'
                        if question.get('cross_page')
                        else 'single_page'
                    )
                error_questions.append(entry)
        if questions:
            accuracy_by_page[str(page_num)] = round(page_correct / len(questions), 4)

    total_correct = verdict_dist.get('correct', 0)
    kp_frequency = sorted(
        [
            {
                'point': point,
                'error_count': kp_errors.get(point, 0),
                'total_count': total,
                'error_rate': round(kp_errors.get(point, 0) / total, 4),
                'correct_rate': round(1 - kp_errors.get(point, 0) / total, 4),
            }
            for point, total in kp_total.items()
        ],
        key=lambda item: item['error_count'],
        reverse=True,
    )
    kp_importance = {point: max_importance(levels) for point, levels in kp_importance_levels.items()}
    return stamp_feedback({
        'page_count': len(page_files),
        'page_understanding': page_understanding,
        'question_count': question_count,
        'accuracy': {
            'overall': None if notes else round(total_correct / question_count, 4) if question_count else 0.0,
            'by_page': {} if notes else accuracy_by_page,
        },
        **({'evidence_mode': 'notes', 'temporal_evidence': False} if notes else {}),
        **({'material_type': feedback_runtime.context['material_type']} if open_material else {}),
        'verdict_distribution': dict(verdict_dist),
        'uncertain_count': verdict_dist.get('uncertain', 0),
        'listening_skipped_count': listening_skipped_count,
        'cross_page_uncertain_count': cross_page_uncertain_count,
        'error_questions': error_questions,
        'knowledge_point_frequency': kp_frequency,
        'error_type_distribution': dict(error_type_dist),
        'kp_importance': kp_importance,
    }, feedback_runtime, 'memory')


def build_memory(pass1_dir: str, subject: str, sample_id: str, *, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    body = aggregate_pages(sorted_json_pages(pass1_dir), **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
    return stamp_feedback({'subject': subject, 'sample_id': sample_id, **body}, feedback_runtime, 'memory')


def save_memory(memory: Dict[str, Any], report_dir: str, subject: str, sample_id: str, *, feedback_runtime=None) -> str:
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    path = os.path.join(report_dir, f'{subject}_{sample_id}_memory.json')
    safe_json_dump(path, stamp_feedback(memory, feedback_runtime, 'memory'))
    return path
