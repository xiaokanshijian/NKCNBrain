#!/usr/bin/env python
"""补全 Pass1 新增字段（layout_confidence / understanding / 三项置信度）。

与正常 Pass1 两阶段流程对齐：
  1. 先做与线上一致的 detect 跨页/大题/同页回填（无 LLM，不改动已有版面坐标）
  2. Stage A：仅对缺 layout_confidence 的页调用 supplement_detect_layout_confidence
  3. Stage B：仅对缺 understanding/置信度的页调用 supplement_grade_understanding_fields
     （输入已锁定 student_answer/verdict 等，保证理解与已有批改一致）
  4. 将 detect/grade 中**新增字段**补丁写入已有 *.json（保留原 merge 结构与内容，不做全量重拼）

**跳过**：完整 detect/grade 重跑、Pass1.5（resolve_cross_pages）、Pass2。

页面 PNG 默认：homework_xxx/homework_grading/clean/{stem}.png

Usage (from 本地backend):
  python -m app_chat.homework_grading.pass1_confidence_fields_backfill --docs-dir docs

Optional:
  --homework-id homework_856def1549aa   # 可逗号分隔多个
  --exclude-homework-id homework_a96de3a8ba9d,homework_7965e9e9cd0a
  --max-pages 5                    # 仅处理页码 1..N（如前 5 页）
  --pages 1-5                      # 或指定页码范围/列表，如 1-5 或 1,3,5
  --dry-run
  --skip-detect-context-backfill   # 跳过跨页 detect 规则回填（不推荐）
  --skip-detect / --skip-grade / --skip-merge
  --merge-only                     # 仅把 detect/grade 新增字段写入 *.json（需已恢复原始 merge）
  --render-only                    # 仅渲染三种 PNG
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional, Tuple

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')
import django  # noqa: E402
django.setup()

from app_chat.homework_grading.cross_page_detect_backfill import backfill_cross_page_detect_dir  # noqa: E402
from app_chat.homework_grading.grader_pass1 import (  # noqa: E402
    _clamp_confidence,
    supplement_detect_layout_confidence,
    supplement_grade_understanding_fields,
)
from app_chat.homework_grading.parent_stem_backfill import backfill_parent_stems_in_detect_dir  # noqa: E402
from app_chat.homework_grading.same_page_detect_backfill import backfill_same_page_detect_dir  # noqa: E402
from app_chat.homework_grading.render import render_all_page_modes  # noqa: E402
from app_chat.homework_grading.utils import (  # noqa: E402
    load_sample_meta,
    parse_page_num,
    safe_json_dump,
    safe_json_load,
    stage_of_grade,
)

logger = logging.getLogger(__name__)

DEFAULT_PARALLELISM = 4


def _parse_homework_id_list(value: str) -> List[str]:
    return [part.strip() for part in (value or '').split(',') if part.strip()]


def _iter_homework_dirs(
    docs_dir: str,
    homework_id: Optional[str] = None,
    exclude_homework_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    exclude = set(exclude_homework_ids or ())
    if homework_id:
        selected: List[str] = []
        for hw_id in _parse_homework_id_list(homework_id):
            if hw_id in exclude:
                continue
            path = os.path.join(docs_dir, hw_id)
            if os.path.isdir(path):
                selected.append(path)
        return sorted(selected)
    return sorted(
        os.path.join(docs_dir, name)
        for name in os.listdir(docs_dir)
        if name.startswith('homework_')
        and os.path.isdir(os.path.join(docs_dir, name))
        and name not in exclude
    )


def _grading_paths(homework_dir: str) -> Dict[str, str]:
    base = os.path.join(homework_dir, 'homework_grading')
    return {
        'base': base,
        'clean': os.path.join(base, 'clean'),
        'pass1_json': os.path.join(base, 'pass1_json'),
        'annotated': os.path.join(base, 'annotated'),
        'annotated_layout': os.path.join(base, 'annotated_layout'),
        'annotated_understanding': os.path.join(base, 'annotated_understanding'),
    }


def _page_stem(name: str) -> str:
    for suffix in ('.detect.json', '.grade.json', '.json'):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def _clean_image_path(clean_dir: str, stem: str) -> str:
    return os.path.join(clean_dir, f'{stem}.png')


def _list_page_jobs(pass1_dir: str, clean_dir: str) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    seen = set()
    for name in sorted(os.listdir(pass1_dir)):
        if not name.endswith('.detect.json'):
            continue
        stem = _page_stem(name)
        if stem in seen:
            continue
        seen.add(stem)
        detect_path = os.path.join(pass1_dir, name)
        grade_path = os.path.join(pass1_dir, f'{stem}.grade.json')
        merged_path = os.path.join(pass1_dir, f'{stem}.json')
        image_path = _clean_image_path(clean_dir, stem)
        try:
            detect_data = safe_json_load(detect_path)
        except Exception:
            continue
        page_num = int(detect_data.get('page') or parse_page_num(stem) or 0)
        subject = str(detect_data.get('subject') or 'unknown')
        jobs.append({
            'stem': stem,
            'page': page_num,
            'subject': subject,
            'detect_path': detect_path,
            'grade_path': grade_path,
            'merged_path': merged_path,
            'image_path': image_path,
        })
    return sorted(jobs, key=lambda item: (item['page'], item['stem']))


def _detect_needs_backfill(detect_data: Dict[str, Any], force: bool = False) -> bool:
    if force:
        return bool(detect_data.get('questions'))
    for question in detect_data.get('questions') or []:
        if isinstance(question, dict) and 'layout_confidence' not in question:
            return True
    return False


def _grade_needs_backfill(grade_data: Dict[str, Any], force: bool = False) -> bool:
    if force:
        return bool(grade_data.get('questions'))
    for question in grade_data.get('questions') or []:
        if not isinstance(question, dict):
            continue
        if not str(question.get('understanding') or '').strip():
            return True
        for field in ('recognition_confidence', 'understanding_confidence', 'grading_confidence'):
            if field not in question:
                return True
    return False


def _parse_page_filter(pages: str, max_pages: Optional[int]) -> Optional[set]:
    if max_pages is not None and max_pages > 0:
        return set(range(1, max_pages + 1))
    text = (pages or '').strip()
    if not text:
        return None
    result: set = set()
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            bounds = part.split('-', 1)
            start = int(bounds[0].strip())
            end = int(bounds[1].strip())
            result.update(range(start, end + 1))
        else:
            result.add(int(part))
    return result or None


def _verify_page_fields(job: Dict[str, Any]) -> Dict[str, str]:
    """补全后校验各题新字段是否齐全。"""
    detect_ok = grade_ok = '—'
    try:
        detect_data = safe_json_load(job['detect_path'])
        questions = detect_data.get('questions') or []
        if questions:
            missing = sum(
                1 for q in questions
                if isinstance(q, dict) and 'layout_confidence' not in q
            )
            detect_ok = 'OK' if missing == 0 else f'缺{missing}题'
    except Exception as exc:
        detect_ok = f'读失败:{exc}'
    if os.path.isfile(job['grade_path']):
        try:
            grade_data = safe_json_load(job['grade_path'])
            questions = grade_data.get('questions') or []
            if not questions:
                grade_ok = '无题'
            else:
                incomplete = 0
                for q in questions:
                    if not isinstance(q, dict):
                        continue
                    if not str(q.get('understanding') or '').strip():
                        incomplete += 1
                        continue
                    for field in ('recognition_confidence', 'understanding_confidence', 'grading_confidence'):
                        if field not in q:
                            incomplete += 1
                            break
                grade_ok = 'OK' if incomplete == 0 else f'缺{incomplete}题'
        except Exception as exc:
            grade_ok = f'读失败:{exc}'
    else:
        grade_ok = '无grade'
    merge_ok = 'OK' if os.path.isfile(job['merged_path']) else '—'
    return {'detect_fields': detect_ok, 'grade_fields': grade_ok, 'merged_file': merge_ok}


def _print_summary_table(
    rows: List[Dict[str, Any]],
    *,
    dry_run: bool,
) -> None:
    if not rows:
        print('\n[补全汇总] 无处理页面')
        return
    headers = [
        '作业', '页', 'detect补全', 'grade补全', 'merge', 'detect字段', 'grade字段', '合并文件', '备注',
    ]
    col_widths = [22, 4, 10, 10, 8, 10, 10, 8, 24]
    sep = '+' + '+'.join('-' * (w + 2) for w in col_widths) + '+'

    def _cell(text: str, width: int) -> str:
        s = str(text or '')
        if len(s) > width:
            return s[: width - 1] + '…'
        return s.ljust(width)

    print('\n' + sep)
    print('| ' + ' | '.join(_cell(h, col_widths[i]) for i, h in enumerate(headers)) + ' |')
    print(sep)
    for row in rows:
        print('| ' + ' | '.join(
            _cell(row.get(key, ''), col_widths[i])
            for i, key in enumerate([
                'homework', 'page', 'detect', 'grade', 'merge',
                'detect_fields', 'grade_fields', 'merged_file', 'note',
            ])
        ) + ' |')
    print(sep)

    total = len(rows)
    detect_done = sum(1 for r in rows if r.get('detect') in ('patched', 'would_patch', 'skip'))
    grade_done = sum(1 for r in rows if r.get('grade') in ('patched', 'would_patch', 'skip', 'skip_no_grade'))
    merge_done = sum(1 for r in rows if r.get('merge') == 'OK')
    errors = sum(1 for r in rows if r.get('note', '').startswith('ERROR'))
    mode = 'dry-run' if dry_run else '正式'
    print(
        f'\n[补全汇总 · {mode}] 共 {total} 页 | '
        f'detect处理 {detect_done} | grade处理 {grade_done} | merge成功 {merge_done} | 失败 {errors}'
    )


def _run_detect_context_backfill(pass1_dir: str, skip: bool) -> Dict[str, Any]:
    if skip:
        return {'skipped': True}
    cross_page_stats = backfill_cross_page_detect_dir(pass1_dir)
    parent_stem_patched = backfill_parent_stems_in_detect_dir(pass1_dir)
    same_page_stats = backfill_same_page_detect_dir(pass1_dir)
    return {
        'cross_page': cross_page_stats,
        'parent_stem_patched': parent_stem_patched,
        'same_page': same_page_stats,
    }


def _resolve_grade_stage(subject: str, grading_base: str) -> Tuple[int, int]:
    meta = load_sample_meta(grading_base) or {}
    grade = int(meta.get('grade') or 4)
    stage = int(meta.get('stage') or stage_of_grade(grade))
    if meta.get('subject') and str(meta.get('subject')) != subject:
        logger.warning('sample_meta subject=%s differs from page subject=%s', meta.get('subject'), subject)
    return grade, stage


def _supplement_detect_job(job: Dict[str, Any], grade: int, stage: int, dry_run: bool, force: bool = False) -> str:
    detect_data = safe_json_load(job['detect_path'])
    if not _detect_needs_backfill(detect_data, force=force):
        return 'skip'
    if dry_run:
        return 'would_patch'
    if not os.path.isfile(job['image_path']):
        raise FileNotFoundError(f"缺少 clean 页面图: {job['image_path']}")
    supplement_detect_layout_confidence(
        job['image_path'],
        job['subject'],
        job['page'],
        detect_data,
        job['detect_path'],
        grade=grade,
        stage=stage,
        force=force,
    )
    return 'patched'


def _supplement_grade_job(job: Dict[str, Any], grade: int, stage: int, dry_run: bool, force: bool = False) -> str:
    if not os.path.isfile(job['grade_path']):
        return 'skip_no_grade'
    grade_data = safe_json_load(job['grade_path'])
    if not _grade_needs_backfill(grade_data, force=force):
        return 'skip'
    if dry_run:
        return 'would_patch'
    if not os.path.isfile(job['image_path']):
        raise FileNotFoundError(f"缺少 clean 页面图: {job['image_path']}")
    detect_data = safe_json_load(job['detect_path'])
    supplement_grade_understanding_fields(
        job['image_path'],
        job['subject'],
        job['page'],
        detect_data,
        grade_data,
        job['grade_path'],
        prior_context=None,
        grade=grade,
        stage=stage,
        force=force,
    )
    return 'patched'


def _questions_by_id(questions: Any) -> Dict[str, Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    if not isinstance(questions, list):
        return by_id
    for question in questions:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        if qid:
            by_id[qid] = question
    return by_id


def _patch_merged_new_fields(
    merged_data: Dict[str, Any],
    detect_data: Dict[str, Any],
    grade_data: Dict[str, Any],
) -> int:
    """将 detect/grade 新增字段写入已有 merged，不改动题目顺序与其他字段。"""
    detect_by_id = _questions_by_id(detect_data.get('questions'))
    grade_by_id = _questions_by_id(grade_data.get('questions'))
    merged_questions = merged_data.get('questions')
    if not isinstance(merged_questions, list):
        return 0

    patched = 0
    for question in merged_questions:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        if not qid:
            continue

        changed = False
        detect_q = detect_by_id.get(qid, {})
        if 'layout_confidence' in detect_q:
            confidence = _clamp_confidence(detect_q.get('layout_confidence'))
            if confidence is not None:
                question['layout_confidence'] = confidence
                changed = True

        grade_q = grade_by_id.get(qid, {})
        if 'understanding' in grade_q:
            understanding = str(grade_q.get('understanding') or '').strip()
            if understanding:
                question['understanding'] = understanding
                changed = True
        for field in ('recognition_confidence', 'understanding_confidence', 'grading_confidence'):
            if field not in grade_q:
                continue
            confidence = _clamp_confidence(grade_q.get(field))
            if confidence is not None:
                question[field] = confidence
                changed = True

        if changed:
            patched += 1
    return patched


def _merge_job(job: Dict[str, Any], dry_run: bool) -> bool:
    """把 detect/grade 新增字段补丁进已有 merged json，不做全量 detect+grade 重拼。"""
    if dry_run:
        return False
    merged_path = job['merged_path']
    if not os.path.isfile(merged_path):
        logger.warning('merged json 不存在，跳过补丁: %s', merged_path)
        return False
    merged = safe_json_load(merged_path)
    detect_data = safe_json_load(job['detect_path'])
    grade_data = safe_json_load(job['grade_path']) if os.path.isfile(job['grade_path']) else {}
    patched = _patch_merged_new_fields(merged, detect_data, grade_data)
    if patched == 0:
        logger.warning('page=%s 无题被补丁（检查 id 是否与 detect/grade 对齐）', job['page'])
    safe_json_dump(merged_path, merged)
    return True


def _render_jobs(jobs: List[Dict[str, Any]], paths: Dict[str, str]) -> int:
    for key in ('annotated', 'annotated_layout', 'annotated_understanding'):
        os.makedirs(paths[key], exist_ok=True)
    rendered = 0
    for job in jobs:
        merged_path = job.get('merged_path') or os.path.join(paths['pass1_json'], f"{job['stem']}.json")
        if not os.path.isfile(merged_path):
            continue
        if not os.path.isfile(job['image_path']):
            continue
        render_all_page_modes(
            merged_path,
            job['image_path'],
            paths['annotated'],
            paths['annotated_layout'],
            paths['annotated_understanding'],
        )
        rendered += 1
    return rendered


def backfill_homework_dir(
    homework_dir: str,
    *,
    dry_run: bool = False,
    skip_detect_context_backfill: bool = False,
    skip_detect: bool = False,
    skip_grade: bool = False,
    skip_merge: bool = False,
    skip_render: bool = False,
    workers: int = DEFAULT_PARALLELISM,
    page_filter: Optional[set] = None,
    force: bool = False,
) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    paths = _grading_paths(homework_dir)
    pass1_dir = paths['pass1_json']
    clean_dir = paths['clean']
    homework_id = os.path.basename(homework_dir)
    stats = {
        'detect_context_ran': 0,
        'detect_patched': 0,
        'detect_skipped': 0,
        'grade_patched': 0,
        'grade_skipped': 0,
        'merged': 0,
        'rendered': 0,
        'errors': 0,
    }
    page_rows: List[Dict[str, Any]] = []
    if not os.path.isdir(pass1_dir):
        logger.warning('pass1_json not found: %s', pass1_dir)
        return stats, page_rows
    if not os.path.isdir(clean_dir):
        logger.warning('clean dir not found: %s', clean_dir)
        return stats, page_rows

    all_jobs = _list_page_jobs(pass1_dir, clean_dir)
    if not all_jobs:
        logger.warning('no detect.json pages under %s', pass1_dir)
        return stats, page_rows

    jobs = all_jobs
    if page_filter:
        jobs = [j for j in all_jobs if j['page'] in page_filter]
        logger.info(
            '页码过滤 %s → %d / %d 页',
            sorted(page_filter),
            len(jobs),
            len(all_jobs),
        )
        if not jobs:
            logger.warning('过滤后无页面可处理')
            return stats, page_rows

    if not skip_detect_context_backfill:
        ctx = _run_detect_context_backfill(pass1_dir, skip=False)
        logger.info('detect context backfill: %s', ctx)
        stats['detect_context_ran'] = 1

    sample_subject = jobs[0]['subject']
    grade, stage = _resolve_grade_stage(sample_subject, paths['base'])
    worker_count = max(1, min(workers, len(jobs)))

    job_status: Dict[str, Dict[str, str]] = {
        job['stem']: {
            'homework': homework_id,
            'page': job['page'],
            'detect': '—',
            'grade': '—',
            'merge': '—',
            'detect_fields': '—',
            'grade_fields': '—',
            'merged_file': '—',
            'note': '',
        }
        for job in jobs
    }

    if not skip_detect:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(_supplement_detect_job, job, grade, stage, dry_run, force): job
                for job in jobs
            }
            for future in as_completed(futures):
                job = futures[future]
                stem = job['stem']
                try:
                    status = future.result()
                    job_status[stem]['detect'] = status
                    if status == 'patched' or status == 'would_patch':
                        stats['detect_patched'] += 1
                    else:
                        stats['detect_skipped'] += 1
                except Exception as exc:
                    stats['errors'] += 1
                    job_status[stem]['detect'] = 'ERROR'
                    job_status[stem]['note'] = f'ERROR detect: {exc}'
                    logger.exception('detect supplement failed page=%s: %s', job['page'], exc)

    if not skip_grade:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(_supplement_grade_job, job, grade, stage, dry_run, force): job
                for job in jobs
            }
            for future in as_completed(futures):
                job = futures[future]
                stem = job['stem']
                try:
                    status = future.result()
                    job_status[stem]['grade'] = status
                    if status == 'patched' or status == 'would_patch':
                        stats['grade_patched'] += 1
                    elif status.startswith('skip'):
                        stats['grade_skipped'] += 1
                except Exception as exc:
                    stats['errors'] += 1
                    job_status[stem]['grade'] = 'ERROR'
                    note = f'ERROR grade: {exc}'
                    job_status[stem]['note'] = (
                        job_status[stem]['note'] + '; ' + note if job_status[stem]['note'] else note
                    )
                    logger.exception('grade supplement failed page=%s: %s', job['page'], exc)

    if not skip_merge:
        for job in jobs:
            stem = job['stem']
            try:
                if _merge_job(job, dry_run):
                    stats['merged'] += 1
                    job_status[stem]['merge'] = 'OK'
                elif dry_run:
                    job_status[stem]['merge'] = 'dry-run'
                else:
                    job_status[stem]['merge'] = 'skip'
            except Exception as exc:
                stats['errors'] += 1
                job_status[stem]['merge'] = 'ERROR'
                note = f'ERROR merge: {exc}'
                job_status[stem]['note'] = (
                    job_status[stem]['note'] + '; ' + note if job_status[stem]['note'] else note
                )
                logger.exception('merge failed page=%s: %s', job['page'], exc)

    if not dry_run:
        for job in jobs:
            stem = job['stem']
            verified = _verify_page_fields(job)
            job_status[stem].update(verified)

    if not dry_run and not skip_render:
        try:
            stats['rendered'] = _render_jobs(jobs, paths)
            logger.info('rendered %d pages (grading + layout + understanding)', stats['rendered'])
        except Exception as exc:
            stats['errors'] += 1
            logger.exception('render failed: %s', exc)

    page_rows = [job_status[job['stem']] for job in sorted(jobs, key=lambda j: j['page'])]
    return stats, page_rows


def main() -> None:
    parser = argparse.ArgumentParser(description='补全 Pass1 新增字段（对齐正常批改流程，仅补缺失项）')
    parser.add_argument('--docs-dir', default='docs', help='含 homework_* 的目录（相对 backend 根）')
    parser.add_argument('--homework-id', default='', help='仅处理指定 homework_xxx（可逗号分隔多个）')
    parser.add_argument(
        '--exclude-homework-id',
        default='',
        help='跳过指定 homework_xxx（逗号分隔，如 homework_a96de3a8ba9d,homework_7965e9e9cd0a）',
    )
    parser.add_argument('--max-pages', type=int, default=None, help='仅处理页码 1..N（如前 5 页用 --max-pages 5）')
    parser.add_argument('--pages', default='', help='指定页码，如 1-5 或 1,3,5（与 --max-pages 二选一，max-pages 优先）')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--skip-detect-context-backfill', action='store_true')
    parser.add_argument('--skip-detect', action='store_true')
    parser.add_argument('--skip-grade', action='store_true')
    parser.add_argument('--skip-merge', action='store_true')
    parser.add_argument('--skip-render', action='store_true', help='跳过三种标注 PNG 渲染')
    parser.add_argument('--render-only', action='store_true', help='仅渲染标注 PNG（不补字段、不改 merge）')
    parser.add_argument(
        '--merge-only',
        action='store_true',
        help='仅将 detect/grade 新增字段补丁写入 *.json（不补字段、不渲染）',
    )
    parser.add_argument('--force', action='store_true', help='强制覆盖已有 layout_confidence / understanding / 置信度')
    parser.add_argument('--workers', type=int, default=DEFAULT_PARALLELISM)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    docs_dir = args.docs_dir
    if not os.path.isabs(docs_dir):
        docs_dir = os.path.join(_BACKEND_ROOT, docs_dir)
    logger.info('BACKEND_ROOT=%s', _BACKEND_ROOT)
    logger.info('docs_dir=%s', docs_dir)

    exclude_homework_ids = _parse_homework_id_list(args.exclude_homework_id)
    if exclude_homework_ids:
        logger.info('跳过作业: %s', ', '.join(exclude_homework_ids))

    homework_dirs = _iter_homework_dirs(
        docs_dir,
        args.homework_id or None,
        exclude_homework_ids,
    )
    if not homework_dirs:
        logger.error('未找到 homework_* 目录: %s', docs_dir)
        sys.exit(1)

    page_filter = _parse_page_filter(args.pages, args.max_pages)

    totals = {
        'detect_context_ran': 0,
        'detect_patched': 0,
        'detect_skipped': 0,
        'grade_patched': 0,
        'grade_skipped': 0,
        'merged': 0,
        'rendered': 0,
        'errors': 0,
    }
    all_page_rows: List[Dict[str, Any]] = []
    for hw_dir in homework_dirs:
        logger.info('Processing %s', os.path.basename(hw_dir))
        stats, page_rows = backfill_homework_dir(
            hw_dir,
            dry_run=args.dry_run,
            skip_detect_context_backfill=(
                args.skip_detect_context_backfill or args.render_only or args.merge_only
            ),
            skip_detect=args.skip_detect or args.render_only or args.merge_only,
            skip_grade=args.skip_grade or args.render_only or args.merge_only,
            skip_merge=args.skip_merge or args.render_only,
            skip_render=args.skip_render or args.merge_only,
            workers=args.workers,
            page_filter=page_filter,
            force=args.force,
        )
        all_page_rows.extend(page_rows)
        for key in totals:
            totals[key] += stats.get(key, 0)
        logger.info('  stats: %s', stats)

    _print_summary_table(all_page_rows, dry_run=args.dry_run)
    logger.info('Done. totals: %s', totals)
    if totals['errors']:
        sys.exit(2)


if __name__ == '__main__':
    main()
