#!/usr/bin/env python
"""Re-run Pass1 review + downstream pipeline with Gemini wrong-page review logic.

Uses an existing completed homework run (e.g. homework_a96de3a8ba9d):
  1. Restore pass1 page JSON to the state *before* the old Qwen all-page self-review
  2. Run new Gemini review (wrong pages only)
  3. Run the same downstream steps as service.run_homework_grading:
     L4 verify → memory → sessions → ontology → Pass2 → hallucination → render

Outputs go to ``homework_grading/gemini_rerun/`` (original run is not modified).

Usage (from 本地backend):
  python -m app_chat.homework_grading.rerun_gemini_review_pipeline \\
      --homework-dir homework_a96de3a8ba9d

Optional:
  --output-subdir gemini_rerun
  --workers 5
  --pages 5,11,15      # only call Gemini/render for these pages
  --skip-pass2          # skip DeepSeek Pass2 / ontology (review+verify+memory only)
"""

from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import re
import shutil
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

# Allow running as script from backend root
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app_chat.homework_grading.grader_pass1_review import review_pass1_dir
from app_chat.homework_grading.grader_pass2 import analyze_pass2
from app_chat.homework_grading.answer_statement_verifier import verify_answer_statements
from app_chat.homework_grading.hallucination_filter import run_hallucination_filter
from app_chat.homework_grading.memory import build_memory, save_memory
from app_chat.homework_grading.ontology_builder import build_ontology
from app_chat.homework_grading.profile import build_student_profile
from app_chat.homework_grading.render import render_all_page_modes
from app_chat.homework_grading.sessions import (
    build_all_session_memories,
    session_page_bounds,
)
from app_chat.homework_grading.utils import (
    load_sample_meta,
    parse_page_num,
    safe_json_dump,
    safe_json_load,
    sorted_json_pages,
    stage_of_grade,
)
from app_chat.homework_grading.verifiers import verify_pass1_dir


def _restore_question_before_self_review(question: Dict[str, Any]) -> Dict[str, Any]:
    q = copy.deepcopy(question)
    self_review = q.pop('self_review', None)
    if isinstance(self_review, dict) and self_review.get('applied'):
        previous = self_review.get('previous') or {}
        for field in ('verdict', 'student_answer', 'correct_answer', 'error_type'):
            if field in previous:
                q[field] = previous[field]
    q.pop('verification_result', None)
    if q.get('uncertain_reason') == 'verifier_override':
        q.pop('uncertain_reason', None)
    return q


def restore_page_before_self_review(page_data: Dict[str, Any]) -> Dict[str, Any]:
    data = copy.deepcopy(page_data)
    data['questions'] = [
        _restore_question_before_self_review(q)
        for q in data.get('questions') or []
        if isinstance(q, dict)
    ]
    return data


def _page_image_path(base_grading_dir: str, page_num: int, sample_id: str, subject: str) -> Optional[str]:
    name = f'{subject}_{sample_id}_page{page_num}.png'
    for sub in ('clean', 'raw'):
        path = os.path.join(base_grading_dir, sub, name)
        if os.path.isfile(path):
            return path
    return None


def build_pages_list(
    base_grading_dir: str,
    subject: str,
    sample_id: str,
    review_image_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    seen = set()
    image_dirs = (
        [os.path.abspath(review_image_dir)]
        if review_image_dir
        else [
            os.path.join(base_grading_dir, 'clean'),
            os.path.join(base_grading_dir, 'raw'),
        ]
    )
    for subdir in image_dirs:
        if not os.path.isdir(subdir):
            continue
        for name in os.listdir(subdir):
            if not name.endswith('.png'):
                continue
            page_num = parse_page_num(name)
            if page_num <= 0 or page_num in seen:
                continue
            abs_path = os.path.join(subdir, name)
            if not os.path.isfile(abs_path):
                continue
            seen.add(page_num)
            pages.append({'page': page_num, 'clean_abs_path': abs_path})
    return sorted(pages, key=lambda item: item['page'])


def parse_target_pages(raw: Optional[str]) -> Optional[List[int]]:
    text = str(raw or '').strip()
    if not text:
        return None
    pages = set()
    for token in re.split(r'[\s,，]+', text):
        if not token:
            continue
        if not token.isdigit() or int(token) <= 0:
            raise ValueError(f'非法页码: {token}')
        pages.add(int(token))
    if not pages:
        raise ValueError('未提供有效页码')
    return sorted(pages)


def select_target_pages(
    pages: List[Dict[str, Any]],
    target_pages: Optional[List[int]],
) -> List[Dict[str, Any]]:
    if target_pages is None:
        return list(pages)
    by_page = {
        int(page.get('page') or 0): page
        for page in pages
        if isinstance(page, dict) and int(page.get('page') or 0) > 0
    }
    missing = [page for page in target_pages if page not in by_page]
    if missing:
        raise ValueError(f'找不到指定页图像: {missing}')
    return [by_page[page] for page in target_pages]


def prepare_pre_review_pass1_json(src_pass1_dir: str, dst_pass1_dir: str) -> Dict[str, int]:
    os.makedirs(dst_pass1_dir, exist_ok=True)
    stats = {'pages': 0, 'questions_restored': 0}
    for src_path in sorted_json_pages(src_pass1_dir):
        data = safe_json_load(src_path)
        restored = restore_page_before_self_review(data)
        restored_count = sum(
            1
            for old, new in zip(data.get('questions') or [], restored.get('questions') or [])
            if isinstance(old, dict) and isinstance(new, dict)
            and (
                old.get('verdict') != new.get('verdict')
                or old.get('student_answer') != new.get('student_answer')
                or old.get('correct_answer') != new.get('correct_answer')
                or old.get('error_type') != new.get('error_type')
            )
        )
        stats['questions_restored'] += restored_count
        dst_path = os.path.join(dst_pass1_dir, os.path.basename(src_path))
        safe_json_dump(dst_path, restored)
        stats['pages'] += 1
    return stats


def _verdict_histogram(pass1_dir: str) -> Dict[str, int]:
    hist: Dict[str, int] = {}
    for path in sorted_json_pages(pass1_dir):
        data = safe_json_load(path)
        for q in data.get('questions') or []:
            if not isinstance(q, dict):
                continue
            verdict = str(q.get('verdict') or 'uncertain')
            hist[verdict] = hist.get(verdict, 0) + 1
    return hist


def _collect_question_verdicts(pass1_dir: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for path in sorted_json_pages(pass1_dir):
        page = parse_page_num(os.path.basename(path))
        data = safe_json_load(path)
        for q in data.get('questions') or []:
            if not isinstance(q, dict):
                continue
            qid = str(q.get('id') or '').strip()
            if not qid:
                continue
            out[f'p{page}:{qid}'] = str(q.get('verdict') or 'uncertain')
    return out


def compare_pass1_outcomes(original_dir: str, rerun_dir: str) -> Dict[str, Any]:
    orig = _collect_question_verdicts(original_dir)
    new = _collect_question_verdicts(rerun_dir)
    all_keys = sorted(set(orig) | set(new))
    changed = []
    for key in all_keys:
        o = orig.get(key)
        n = new.get(key)
        if o != n:
            changed.append({'qid': key, 'original': o, 'gemini_rerun': n})
    return {
        'original_verdict_hist': _verdict_histogram(original_dir),
        'gemini_rerun_verdict_hist': _verdict_histogram(rerun_dir),
        'verdict_changes': changed,
        'verdict_change_count': len(changed),
    }


def _session_title(session: Dict[str, Any]) -> str:
    return str(session.get('title') or session.get('session_title') or '').strip()


def _render_selected_pages(
    *,
    paths: Dict[str, str],
    subject: str,
    sample_id: str,
    pages: List[Dict[str, Any]],
    sessions_json_path: Optional[str],
) -> int:
    session_map = safe_json_load(sessions_json_path) if sessions_json_path and os.path.isfile(sessions_json_path) else {}
    page_session_label: Dict[int, str] = {}
    if isinstance(session_map.get('sessions'), list):
        for session in session_map['sessions']:
            start, _end = session_page_bounds(session)
            page_session_label[start] = _session_title(session)

    os.makedirs(paths['annotated'], exist_ok=True)
    layout_dir = os.path.join(paths['base'], 'annotated_layout')
    understanding_dir = os.path.join(paths['base'], 'annotated_understanding')
    os.makedirs(layout_dir, exist_ok=True)
    os.makedirs(understanding_dir, exist_ok=True)
    rendered = 0
    for page in pages:
        json_path = os.path.join(
            paths['pass1_json'],
            f'{subject}_{sample_id}_page{page["page"]}.json',
        )
        if not os.path.isfile(json_path):
            continue
        render_all_page_modes(
            json_path,
            page['clean_abs_path'],
            paths['annotated'],
            layout_dir,
            understanding_dir,
            session_label=page_session_label.get(page['page']),
        )
        rendered += 1
    return rendered


def run_downstream_pipeline(
    *,
    paths: Dict[str, str],
    subject: str,
    sample_id: str,
    grade: int,
    stage: int,
    pages: List[Dict[str, Any]],
    sessions_json_path: Optional[str],
    skip_pass2: bool,
    source_document_sha256: str = '',
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    os.makedirs(paths['pass2_report'], exist_ok=True)

    verification_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_verification.json')
    verification_report = verify_pass1_dir(
        subject,
        paths['pass1_json'],
        verification_path,
        apply=True,
        source_document_sha256=source_document_sha256,
    )
    summary['verification'] = {'total_discrepancies': verification_report.get('total_discrepancies', 0)}

    os.makedirs(paths['pass2_report'], exist_ok=True)
    answer_statement_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_answer_statement_verification.json')
    answer_statement_report = verify_answer_statements(
        subject, paths['pass1_json'], answer_statement_path, apply=True,
    )
    summary['answer_statement_verification'] = {
        'total_discrepancies': answer_statement_report.get('total_discrepancies', 0),
        'corrections_applied': answer_statement_report.get('corrections_applied', 0),
    }

    memory = build_memory(paths['pass1_json'], subject, sample_id)
    save_memory(memory, paths['pass2_report'], subject, sample_id)
    summary['memory'] = {
        'total_questions': memory.get('total_questions', 0),
        'error_count': memory.get('error_count', 0),
    }

    session_memories: List[Dict[str, Any]] = []
    profile = None
    ontology = None
    try:
        session_memories = build_all_session_memories(
            paths['pass1_json'],
            paths['pass2_report'],
            subject,
            sample_id,
            sessions_json_path=sessions_json_path,
        )
        profile = build_student_profile(paths['pass2_report'], subject, sample_id)
    except Exception:
        traceback.print_exc()
    summary['session_count'] = len(session_memories)

    if skip_pass2:
        summary['pass2_skipped'] = True
        summary['annotated_pages'] = _render_selected_pages(
            paths=paths,
            subject=subject,
            sample_id=sample_id,
            pages=pages,
            sessions_json_path=sessions_json_path,
        )
        return summary

    sample_meta = load_sample_meta(paths['base']) or {
        'subject': subject,
        'grade': grade,
        'stage': stage,
    }
    ontology = build_ontology(
        subject=subject,
        sample_id=sample_id,
        base_dir=paths['base'],
        report_dir=paths['pass2_report'],
        sample_meta=sample_meta,
        session_memories=session_memories,
        profile=profile,
    )
    summary['ontology'] = {
        'built': bool(ontology),
        'fallback_used': bool(ontology.get('fallback_used')) if ontology else False,
    }

    report_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_report.json')
    thinking_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}.thinking.txt')
    analyze_pass2(memory, subject, sample_id, report_path, thinking_path, profile=None, ontology=ontology)
    summary['pass2_report'] = report_path

    hallucination_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_hallucination.json')
    ontology_path = os.path.join(paths['base'], 'student_ontology.json')
    try:
        hallucination_report = run_hallucination_filter(
            subject,
            paths['pass1_json'],
            report_path,
            hallucination_path,
            ontology_path=ontology_path if os.path.exists(ontology_path) else None,
            stage=stage,
        )
    except Exception:
        traceback.print_exc()
        hallucination_report = {'total_issues': 0}
    summary['hallucination'] = {
        'total_issues': hallucination_report.get('total_issues', 0),
        'corrections_applied': hallucination_report.get('corrections_applied_count', 0),
    }

    summary['annotated_pages'] = _render_selected_pages(
        paths=paths,
        subject=subject,
        sample_id=sample_id,
        pages=pages,
        sessions_json_path=sessions_json_path,
    )
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Re-run Gemini wrong-page review + downstream pipeline')
    parser.add_argument(
        '--homework-dir',
        default='homework_a96de3a8ba9d',
        help='Homework root directory (contains manifest.json and homework_grading/)',
    )
    parser.add_argument('--output-subdir', default='gemini_rerun', help='Subdir under homework_grading for outputs')
    parser.add_argument('--workers', type=int, default=5, help='Parallel workers for Gemini review')
    parser.add_argument('--pages', default='', help='Comma-separated pages to review and render; omitted means all')
    parser.add_argument(
        '--review-image-dir',
        default='',
        help='Optional directory containing preprocessed review PNGs; defaults to clean/ then raw/',
    )
    parser.add_argument('--skip-pass2', action='store_true', help='Skip Pass2/ontology/hallucination (LLM-heavy steps)')
    args = parser.parse_args(argv)

    try:
        target_pages = parse_target_pages(args.pages)
    except ValueError as exc:
        parser.error(str(exc))

    homework_root = os.path.abspath(args.homework_dir)
    if not os.path.isdir(homework_root):
        print(f'[error] homework dir not found: {homework_root}')
        return 1

    src_grading = os.path.join(homework_root, 'homework_grading')
    src_pass1 = os.path.join(src_grading, 'pass1_json')
    if not os.path.isdir(src_pass1):
        print(f'[error] pass1_json not found: {src_pass1}')
        return 1

    sample_meta = load_sample_meta(src_grading) or {}
    manifest_path = os.path.join(homework_root, 'manifest.json')
    manifest = safe_json_load(manifest_path) if os.path.isfile(manifest_path) else {}
    subject = sample_meta.get('subject') or manifest.get('subject') or 'math'
    sample_id = sample_meta.get('sample_id') or 'a96de3a8'
    grade = int(sample_meta.get('grade') or 4)
    stage = int(sample_meta.get('stage') or stage_of_grade(grade))

    out_root = os.path.join(src_grading, args.output_subdir)
    paths = {
        'base': out_root,
        'pass1_json': os.path.join(out_root, 'pass1_json'),
        'pass2_report': os.path.join(out_root, 'pass2_report'),
        'annotated': os.path.join(out_root, 'annotated'),
    }
    for key in ('base', 'pass1_json', 'pass2_report', 'annotated'):
        os.makedirs(paths[key], exist_ok=True)

    print('[1/4] Restore pass1 JSON to pre-self-review state …')
    restore_stats = prepare_pre_review_pass1_json(src_pass1, paths['pass1_json'])
    print(f'      pages={restore_stats["pages"]}, questions_reverted={restore_stats["questions_restored"]}')

    sessions_src = os.path.join(src_grading, 'pass2_report', f'{subject}_{sample_id}_sessions.json')
    sessions_dst = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_sessions.json')
    if os.path.isfile(sessions_src):
        shutil.copy2(sessions_src, sessions_dst)

    review_image_dir = os.path.abspath(args.review_image_dir) if args.review_image_dir else None
    if review_image_dir and not os.path.isdir(review_image_dir):
        print(f'[error] review image dir not found: {review_image_dir}')
        return 1
    all_pages = build_pages_list(
        src_grading,
        subject,
        sample_id,
        review_image_dir=review_image_dir,
    )
    try:
        pages = select_target_pages(all_pages, target_pages)
    except ValueError as exc:
        print(f'[error] {exc}')
        return 1
    if not pages:
        print('[warn] No page PNG found under clean/ or raw/; Gemini review will likely skip all pages.')
    else:
        label = 'targeted' if target_pages is not None else 'total'
        print(f'      found {len(pages)} {label} page images for review')

    print('[2/4] Gemini wrong-page self-review …')
    os.environ['HOMEWORK_PASS1_SELF_REVIEW'] = '1'
    review_stats = review_pass1_dir(
        paths['pass1_json'],
        pages,
        subject,
        grade=grade,
        stage=stage,
        workers=max(1, args.workers),
        source_document_sha256=str(
            sample_meta.get('source_document_sha256') or ''
        ).strip(),
    )
    print(
        f'      model={review_stats.get("model")} '
        f'reviewed={review_stats.get("pages_reviewed", 0)} '
        f'skipped={review_stats.get("pages_skipped", 0)} '
        f'issues={review_stats.get("issues_found", 0)} '
        f'applied={review_stats.get("corrections_applied", 0)}'
    )

    print('[3/4] Downstream pipeline (verify → memory → Pass2 …) …')
    downstream = run_downstream_pipeline(
        paths=paths,
        subject=subject,
        sample_id=sample_id,
        grade=grade,
        stage=stage,
        pages=pages,
        sessions_json_path=sessions_dst if os.path.isfile(sessions_dst) else None,
        skip_pass2=args.skip_pass2,
        source_document_sha256=str(
            sample_meta.get('source_document_sha256') or ''
        ).strip(),
    )

    print('[4/4] Compare with original final pass1 …')
    comparison = compare_pass1_outcomes(src_pass1, paths['pass1_json'])

    original_manifest_review = (manifest.get('pass1_review') or {}) if isinstance(manifest, dict) else {}
    rerun_manifest = {
        'analysis_type': 'homework_grading_gemini_rerun',
        'source_homework_dir': homework_root,
        'created_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'subject': subject,
        'sample_id': sample_id,
        'target_pages': target_pages,
        'review_image_dir': review_image_dir,
        'restore_stats': restore_stats,
        'original_pass1_review': original_manifest_review,
        'gemini_pass1_review': review_stats,
        'downstream': downstream,
        'comparison': comparison,
        'output_paths': paths,
    }
    safe_json_dump(os.path.join(out_root, 'rerun_manifest.json'), rerun_manifest)
    safe_json_dump(os.path.join(out_root, 'comparison_summary.json'), comparison)

    print('\n=== Done ===')
    print(f'Output root: {out_root}')
    print(f'Original verdict hist: {comparison["original_verdict_hist"]}')
    print(f'Gemini rerun hist:     {comparison["gemini_rerun_verdict_hist"]}')
    print(f'Verdict changes:       {comparison["verdict_change_count"]}')
    if comparison['verdict_changes'][:5]:
        print('Sample changes:')
        for item in comparison['verdict_changes'][:5]:
            print(f'  {item["qid"]}: {item["original"]} -> {item["gemini_rerun"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
