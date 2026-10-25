# -*- coding: utf-8 -*-
"""人机核验闭环：保存核对结果 → 仅重批已核验题/条 → 回写当次批改 → 白区化 → 刷新报告与卡片。"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import threading
import time
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app_chat.homework_grading.utils import safe_json_dump, safe_json_load

VERIFY_FILE = 'user_verifications.json'
JOB_FILE = 'verify_iterate_job.json'

_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_RUN_LOCKS: Dict[str, threading.Lock] = {}
_RUN_LOCKS_GUARD = threading.Lock()


def _run_key(username: str, analysis_id: str) -> str:
    return f'{username}::{analysis_id}'


def _run_lock(username: str, analysis_id: str) -> threading.Lock:
    key = _run_key(username, analysis_id)
    with _RUN_LOCKS_GUARD:
        lk = _RUN_LOCKS.get(key)
        if not lk:
            lk = threading.Lock()
            _RUN_LOCKS[key] = lk
        return lk


def _set_job(job_id: str, **kwargs) -> None:
    with _JOBS_LOCK:
        cur = _JOBS.get(job_id) or {}
        cur.update(kwargs)
        _JOBS[job_id] = cur


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
        return dict(j) if j else None


def _paths_for(username: str, analysis_id: str) -> Dict[str, str]:
    from app_chat.homework_grading.service import prepare_homework_workspace
    return prepare_homework_workspace(username, analysis_id, None, create=False)


def _verify_path(paths: Dict[str, str]) -> str:
    return os.path.join(paths.get('base') or paths.get('root') or '', VERIFY_FILE)


def _job_path(paths: Dict[str, str]) -> str:
    return os.path.join(paths.get('base') or paths.get('root') or '', JOB_FILE)


def load_verifications(username: str, analysis_id: str) -> Dict[str, Any]:
    paths = _paths_for(username, analysis_id)
    path = _verify_path(paths)
    data = safe_json_load(path) if os.path.isfile(path) else None
    if not isinstance(data, dict):
        data = {
            'schema_version': 1,
            'analysis_id': analysis_id,
            'items': {},
            'updated_at': '',
        }
    if not isinstance(data.get('items'), dict):
        data['items'] = {}
    return data


def save_verification_item(
    username: str,
    analysis_id: str,
    *,
    qid_global: str,
    label: str = '',
    verdict: str,
    step_notes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """保存单条核验。verdict: correct | incorrect。"""
    qid = str(qid_global or '').strip()
    if not qid:
        raise ValueError('缺少 qid_global')
    if verdict not in ('correct', 'incorrect'):
        raise ValueError('verdict 须为 correct 或 incorrect')
    notes = step_notes if isinstance(step_notes, dict) else {}
    cleaned_notes = {}
    for role in ('layout', 'understanding', 'grading'):
        raw = notes.get(role) if isinstance(notes.get(role), dict) else {}
        has_error = bool(raw.get('has_error')) if verdict == 'incorrect' else False
        text = str(raw.get('note') or raw.get('text') or '').strip()[:2000]
        cleaned_notes[role] = {'has_error': has_error, 'note': text}

    with _run_lock(username, analysis_id):
        paths = _paths_for(username, analysis_id)
        data = load_verifications(username, analysis_id)
        data['items'][qid] = {
            'qid_global': qid,
            'label': str(label or qid)[:120],
            'verdict': verdict,
            'step_notes': cleaned_notes,
            'updated_at': datetime.now().isoformat(timespec='seconds'),
        }
        data['updated_at'] = data['items'][qid]['updated_at']
        data['analysis_id'] = analysis_id
        safe_json_dump(_verify_path(paths), data)
        return data['items'][qid]


def _parse_qid(qid_global: str) -> Tuple[Optional[int], str]:
    m = re.match(r'^p(\d+)[:：](.+)$', str(qid_global or '').strip(), re.I)
    if not m:
        return None, ''
    return int(m.group(1)), str(m.group(2)).strip()


def _force_white_question(q: Dict[str, Any]) -> None:
    """人工核验后三步骤一律视为白区（置信度拉满）。"""
    for key in (
        'layout_confidence',
        'recognition_confidence',
        'understanding_confidence',
        'grading_confidence',
    ):
        q[key] = 100
    q['user_verified'] = True
    q['user_verified_at'] = datetime.now().isoformat(timespec='seconds')


def _build_iteration_guidance(items: List[Dict[str, Any]], page_num: int) -> str:
    lines = [
        f'\n\n【人工核验绝对对齐·第{page_num}页】以下题/条目已经用户核对，重批时必须严格服从，不得违背：',
    ]
    for it in items:
        qid = it.get('qid_global') or ''
        _, local_id = _parse_qid(qid)
        verdict = it.get('verdict')
        label = it.get('label') or qid
        if verdict == 'correct':
            lines.append(f'- {label}（id={local_id}）：用户确认原批改结果无误；保持结论一致，仅可润色表述。')
            continue
        lines.append(f'- {label}（id={local_id}）：用户确认原批改有误，须按下列说明修正：')
        notes = it.get('step_notes') or {}
        role_cn = {
            'layout': '无损版面',
            'understanding': '无损理解',
            'grading': '三区批改',
        }
        for role, cn in role_cn.items():
            n = notes.get(role) or {}
            if n.get('has_error'):
                lines.append(f'  · {cn}有误：{n.get("note") or "（用户未写细节，请对照原卷重判）"}')
            else:
                lines.append(f'  · {cn}：用户未标有误，可保持或微调。')
    lines.append('只允许改写上述 id 对应条目；其他题目/条目原样保留语义。')
    return '\n'.join(lines)


def _merge_questions(
    old_page: Dict[str, Any],
    new_page: Dict[str, Any],
    local_ids: set,
) -> Dict[str, Any]:
    """把 new_page 中指定 id 的题目抽到 old_page，其余不变。"""
    out = copy.deepcopy(old_page)
    old_qs = [q for q in (out.get('questions') or []) if isinstance(q, dict)]
    new_map = {
        str(q.get('id') or '').strip(): q
        for q in (new_page.get('questions') or [])
        if isinstance(q, dict) and str(q.get('id') or '').strip()
    }
    merged = []
    seen = set()
    for q in old_qs:
        qid = str(q.get('id') or '').strip()
        if qid in local_ids and qid in new_map:
            nq = copy.deepcopy(new_map[qid])
            # 保留原 qid_global 等稳定键
            if q.get('qid_global') and not nq.get('qid_global'):
                nq['qid_global'] = q.get('qid_global')
            merged.append(nq)
            seen.add(qid)
        else:
            merged.append(q)
            seen.add(qid)
    # 新检出的、属于核验集合但旧页没有的（少见）也并入
    for qid in local_ids:
        if qid not in seen and qid in new_map:
            merged.append(copy.deepcopy(new_map[qid]))
    out['questions'] = merged
    return out


def _apply_force_white(page_data: Dict[str, Any], local_ids: set) -> None:
    for q in page_data.get('questions') or []:
        if not isinstance(q, dict):
            continue
        if str(q.get('id') or '').strip() in local_ids:
            _force_white_question(q)


def _recover_notebook_skill_selection(root: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """尽量从当次残留快照还原「用户当时勾选的 Skill」，以便按原流程重冻。"""
    from pathlib import Path
    candidates = [
        Path(root) / 'reference_snapshot.json',
        Path(root) / 'homework_grading' / 'reference_snapshot.json',
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        refs = raw.get('data') if isinstance(raw, dict) and 'data' in raw else raw
        if not isinstance(refs, dict):
            continue
        ns = refs.get('notebook_skills')
        if not isinstance(ns, dict):
            continue
        names = ns.get('user_selected_names')
        if not isinstance(names, list):
            names = [
                m.get('name') for m in (ns.get('members') or [])
                if isinstance(m, dict) and m.get('name')
            ]
        names = [str(n).strip() for n in names if str(n or '').strip()]
        enabled = bool(ns.get('enabled')) if 'enabled' in ns else bool(names)
        return {'enabled': enabled and bool(names), 'names': names}
    # manifest 里偶发留下的选择痕迹
    for key in ('notebook_skill_selection', 'skill_selection'):
        sel = manifest.get(key)
        if isinstance(sel, dict) and isinstance(sel.get('names'), list):
            names = [str(n).strip() for n in sel.get('names') if str(n or '').strip()]
            return {'enabled': bool(sel.get('enabled', True) and names), 'names': names}
    return {'enabled': False, 'names': []}


def _recover_reference_text(root: str, manifest: Dict[str, Any]) -> str:
    from pathlib import Path
    for path in (Path(root) / 'reference_snapshot.json', Path(root) / 'homework_grading' / 'reference_snapshot.json'):
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            refs = raw.get('data') if isinstance(raw, dict) and 'data' in raw else raw
            if isinstance(refs, dict) and isinstance(refs.get('reference_text'), str):
                return refs.get('reference_text') or ''
        except Exception:
            continue
    ctx = manifest.get('feedback_context') if isinstance(manifest.get('feedback_context'), dict) else {}
    return str(ctx.get('reference_text') or '')


def resolve_feedback_runtime_for_verify(
    username: str,
    paths: Dict[str, str],
    manifest: Dict[str, Any],
) -> Tuple[Any, str]:
    """优先恢复当次冻结运行依据；失败则按原启动流程重冻（含 Skill 冻结文本）。"""
    from pathlib import Path
    from app_chat.homework_grading.feedback_runtime_service import (
        restore_feedback_runtime,
        build_request_runtime,
    )

    root = Path(paths.get('root') or paths.get('base') or '')
    try:
        runtime = restore_feedback_runtime(root)
        return runtime, 'restored'
    except Exception as restore_exc:
        traceback.print_exc()
        print(f'[verify_loop] restore_feedback_runtime 失败，将按原流程重冻: {restore_exc}', flush=True)

    context = manifest.get('feedback_context')
    if not isinstance(context, dict) or not context.get('subject_code'):
        raise ValueError(
            '当次批改运行快照无法恢复，且 manifest 缺少 feedback_context，无法按原流程重冻 Skill'
        )

    exec_cfg = manifest.get('feedback_execution') if isinstance(manifest.get('feedback_execution'), dict) else {}
    preprocess_mode = None
    try:
        preprocess_mode = (exec_cfg.get('preprocessing') or {}).get('mode')
    except Exception:
        preprocess_mode = None
    curriculum_selection = 'auto'
    try:
        curriculum_selection = (exec_cfg.get('retrieval') or {}).get('curriculum_selection') or 'auto'
    except Exception:
        curriculum_selection = 'auto'

    filename = ''
    files = manifest.get('selected_files') or []
    if isinstance(files, list) and files:
        filename = str(files[0] or '')
    sample_id = str(manifest.get('analysis_id') or '').replace('homework_', '')[:24]

    data = {
        'filename': filename,
        'sample_id': sample_id,
        'reference_text': _recover_reference_text(str(root), manifest),
        'notebook_skill_selection': _recover_notebook_skill_selection(str(root), manifest),
        'curriculum_selection': curriculum_selection,
        'preprocess_mode': preprocess_mode,
    }
    runtime = build_request_runtime(
        context,
        data,
        preprocess_mode=preprocess_mode,
        workspace=username,
    )
    return runtime, 'rebuilt'


def _rebuild_downstream(
    username: str,
    analysis_id: str,
    paths: Dict[str, str],
    manifest: Dict[str, Any],
    *,
    job_id: str,
    feedback_runtime=None,
    verified_qids=None,
) -> None:
    from app_chat.homework_grading.grader_pass2 import analyze_pass2
    from app_chat.homework_grading.ontology_builder import build_ontology
    from app_chat.homework_grading.result_cards import pin_grading_result_cards, _sample_id
    from app_chat.homework_grading.wgb_trust import build_wgb_trust_summary
    from app_chat.homework_grading.memory import build_memory, save_memory
    from app_chat.homework_grading.sessions import build_all_session_memories
    from app_chat.homework_grading.utils import load_sample_meta

    subject = str(manifest.get('subject') or 'chinese').strip() or 'chinese'
    if feedback_runtime is not None:
        try:
            subject = feedback_runtime.context.get('subject_code') or subject
        except Exception:
            pass
    sample_id = _sample_id(analysis_id)
    ctx = (feedback_runtime.context if feedback_runtime is not None else None) or manifest.get('feedback_context') or {}
    material_type = str(ctx.get('material_type') or ctx.get('material_key') or 'homework')
    assigned = (manifest.get('grading_config') or {}).get('assigned_pages')
    runtime_kwargs = {'feedback_runtime': feedback_runtime} if feedback_runtime is not None else {}

    _set_job(job_id, phase='memory', progress=58, msg='按更新后的逐页结果重建记忆')
    memory = build_memory(paths['pass1_json'], subject, sample_id, **runtime_kwargs)
    save_memory(memory, paths['pass2_report'], subject, sample_id, **runtime_kwargs)
    session_memories = build_all_session_memories(
        paths['pass1_json'], paths['pass2_report'], subject, sample_id,
        sessions_json_path=os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_sessions.json'),
        **runtime_kwargs,
    )

    _set_job(job_id, phase='ontology', progress=68, msg='重建学生本体与可信度')
    sample_meta = load_sample_meta(paths['base']) or {'subject': subject, 'analysis_id': analysis_id}
    ontology = build_ontology(
        subject=subject,
        sample_id=sample_id,
        base_dir=paths['base'],
        report_dir=paths['pass2_report'],
        sample_meta=sample_meta,
        session_memories=session_memories or [],
        profile=None,
        pass1_dir=paths.get('pass1_json') or '',
        **runtime_kwargs,
    ) or {}
    trust = build_wgb_trust_summary(
        paths['pass1_json'], subject,
        material_type=material_type,
        assigned_pages=assigned,
    )
    if isinstance(ontology, dict) and trust:
        ontology['wgb_trust'] = {
            'total_units': trust.get('total_units'),
            'tier_counts': trust.get('tier_counts'),
            'cross_counts': trust.get('cross_counts'),
            'critical': (trust.get('critical') or [])[:40],
            'careful': (trust.get('careful') or [])[:40],
            'need_verify': (trust.get('need_verify') or [])[:60],
            'by_qid': trust.get('by_qid') or {},
            'material_type': trust.get('material_type') or material_type,
            'unit_word': trust.get('unit_word'),
            'protocol_hint': trust.get('protocol_hint'),
            'confident_count': trust.get('confident_count'),
            'normal_count': trust.get('normal_count'),
        }
        safe_json_dump(os.path.join(paths['base'], 'student_ontology.json'), ontology)

    _set_job(job_id, phase='pass2', progress=80, msg='更新整体批改报告')
    report_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}_report.json')
    thinking_path = os.path.join(paths['pass2_report'], f'{subject}_{sample_id}.thinking.txt')
    previous_uv = None
    if verified_qids and os.path.isfile(report_path):
        previous = safe_json_load(report_path) or {}
        if isinstance(previous, dict) and isinstance(previous.get('user_verification'), dict):
            previous_uv = previous.get('user_verification')
    analyze_pass2(
        memory, subject, sample_id, report_path, thinking_path,
        profile=None, ontology=ontology,
        **runtime_kwargs,
    )
    if os.path.isfile(report_path):
        report = safe_json_load(report_path) or {}
        if isinstance(report, dict):
            if previous_uv is not None:
                from app_chat.homework_grading.verify_shortlist import drop_verified_items
                report['user_verification'] = drop_verified_items(previous_uv, verified_qids or [])
            report['verify_loop'] = {
                'updated_at': datetime.now().isoformat(timespec='seconds'),
                'note': '已按人工核验回写部分题/条，并刷新白灰黑与报告',
            }
            safe_json_dump(report_path, report)

    _set_job(job_id, phase='verify_suggest', progress=88, msg='更新需核实位置的可点短句')
    try:
        from app_chat.homework_grading.verify_suggestions import generate_verify_suggestions
        # 已有模型成功解析的页跳过；规则兜底页再试模型
        generate_verify_suggestions(
            paths, manifest,
            feedback_runtime=feedback_runtime,
            prefer_keep_llm=True,
            trust=trust if isinstance(trust, dict) else None,
        )
    except Exception:
        traceback.print_exc()

    _set_job(job_id, phase='cards', progress=92, msg='更新批改输出卡片与 HTML')
    pin_grading_result_cards(paths, manifest, feedback_runtime=feedback_runtime)


def run_verify_iterate(
    username: str,
    analysis_id: str,
    *,
    job_id: str = '',
) -> Tuple[bool, str]:
    job_id = job_id or uuid.uuid4().hex[:16]
    with _run_lock(username, analysis_id):
        try:
            _set_job(job_id, status='running', phase='load', progress=5, msg='读取核验记录', error='')
            paths = _paths_for(username, analysis_id)
            manifest = safe_json_load(paths['manifest'])
            if not isinstance(manifest, dict):
                raise ValueError('找不到当次批改 manifest')
            data = load_verifications(username, analysis_id)
            items = [v for v in (data.get('items') or {}).values() if isinstance(v, dict)]
            if not items:
                raise ValueError('尚未提交任何核验结果')

            # 按页分组
            by_page: Dict[int, List[Dict[str, Any]]] = {}
            for it in items:
                page_num, local_id = _parse_qid(it.get('qid_global') or '')
                if page_num is None or not local_id:
                    continue
                it = dict(it)
                it['_local_id'] = local_id
                by_page.setdefault(page_num, []).append(it)
            if not by_page:
                raise ValueError('核验条目无法解析页码/题号')

            from app_chat.homework_grading.staged_pipeline import (
                _question_json_path,
                load_homework_clean_pages,
            )
            from app_chat.homework_grading.grader_pass1 import (
                grade_page,
                grade_page_from_detect,
                pass1_two_stage_enabled,
            )
            from app_chat.homework_grading.fixed_sample_crossout import MODEL_IMAGE_PATH_KEY

            _set_job(job_id, phase='runtime', progress=6, msg='恢复/重冻当次批改 Skill 与运行依据')
            feedback_runtime, runtime_mode = resolve_feedback_runtime_for_verify(
                username, paths, manifest,
            )
            print(
                f'[verify_loop] feedback_runtime mode={runtime_mode} '
                f'user={username} analysis={analysis_id}',
                flush=True,
            )

            pages = load_homework_clean_pages(paths)
            page_map = {p['page']: p for p in pages}
            subject = str(manifest.get('subject') or 'chinese')
            grade = 4
            stage = 2
            attrs = manifest.get('homework_attributes') if isinstance(manifest.get('homework_attributes'), dict) else {}
            if attrs.get('homework_subject'):
                subject = str(attrs.get('homework_subject') or subject)
            if attrs.get('homework_grade'):
                try:
                    grade = int(attrs.get('homework_grade') or grade)
                except Exception:
                    pass
            try:
                from app_chat.homework_grading.utils import stage_of_grade
                stage = stage_of_grade(grade)
            except Exception:
                stage = 2
            if feedback_runtime is not None:
                try:
                    from app_chat.homework_grading.feedback_runtime import runtime_attributes
                    subj_rt, grade_rt, stage_rt = runtime_attributes(feedback_runtime)
                    if subj_rt:
                        subject = str(subj_rt)
                    if grade_rt:
                        grade = int(grade_rt)
                    if stage_rt:
                        stage = int(stage_rt)
                except Exception:
                    pass

            touched_pages: set = set()
            total_pages = len(by_page)
            done = 0
            for page_num, page_items in sorted(by_page.items()):
                done += 1
                pct = 8 + int(50 * done / max(total_pages, 1))
                _set_job(
                    job_id,
                    phase='regrade',
                    progress=pct,
                    msg=f'回写第{page_num}页已核验题/条（{done}/{total_pages}）',
                )
                page = page_map.get(page_num)
                if not page:
                    continue
                official = _question_json_path(paths['pass1_json'], page['clean_abs_path'])
                if not os.path.isfile(official):
                    continue
                old_page = safe_json_load(official) or {}
                if not isinstance(old_page, dict):
                    continue
                local_ids = {str(it.get('_local_id') or '').strip() for it in page_items}
                local_ids.discard('')
                incorrect_ids = {
                    str(it.get('_local_id') or '').strip()
                    for it in page_items
                    if it.get('verdict') == 'incorrect' and str(it.get('_local_id') or '').strip()
                }
                # 页内仅有「无误」→ 不调模型，只抬白区。
                # 页内有「有误」→ 调模型重批该页，但只抽出有误题/条回写；同页「无误」仍只抬白区。
                if incorrect_ids:
                    guidance = _build_iteration_guidance(
                        [it for it in page_items if it.get('verdict') == 'incorrect'],
                        page_num,
                    )
                    tmp_dir = tempfile.mkdtemp(prefix='nkcn_verify_')
                    try:
                        tmp_json = os.path.join(tmp_dir, os.path.basename(official))
                        image_path = page.get(MODEL_IMAGE_PATH_KEY) or page['clean_abs_path']
                        if pass1_two_stage_enabled(feedback_runtime=feedback_runtime):
                            from app_chat.homework_grading.staged_pipeline import _page_detect_path
                            detect_src = _page_detect_path(paths, page)
                            if os.path.isfile(detect_src):
                                detect_dst = tmp_json.replace('.json', '.detect.json')
                                shutil.copy2(detect_src, detect_dst)
                                grade_page_from_detect(
                                    image_path, subject, page_num, tmp_json,
                                    prior_context=None, grade=grade, stage=stage,
                                    iteration_guidance=guidance,
                                    feedback_runtime=feedback_runtime,
                                )
                            else:
                                grade_page(
                                    page['clean_abs_path'], subject, page_num, tmp_json,
                                    prior_context=None, grade=grade, stage=stage,
                                    iteration_guidance=guidance,
                                    feedback_runtime=feedback_runtime,
                                )
                        else:
                            grade_page(
                                page['clean_abs_path'], subject, page_num, tmp_json,
                                prior_context=None, grade=grade, stage=stage,
                                iteration_guidance=guidance,
                                feedback_runtime=feedback_runtime,
                            )
                        new_page = safe_json_load(tmp_json) if os.path.isfile(tmp_json) else {}
                        if isinstance(new_page, dict) and new_page.get('questions'):
                            old_page = _merge_questions(old_page, new_page, incorrect_ids)
                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)

                _apply_force_white(old_page, local_ids)
                safe_json_dump(official, old_page)
                touched_pages.add(page_num)

            if touched_pages:
                _set_job(job_id, phase='render', progress=54, msg='刷新已改页的批改标注图')
                try:
                    from app_chat.homework_grading.staged_pipeline import _render_pages
                    _render_pages(
                        paths, pages,
                        modes=('layout', 'understanding', 'grading'),
                        scope_page_nums=touched_pages,
                    )
                except Exception:
                    traceback.print_exc()

            _rebuild_downstream(
                username, analysis_id, paths, manifest,
                job_id=job_id, feedback_runtime=feedback_runtime,
                verified_qids=[str(it.get('qid_global') or '') for it in items if it.get('qid_global')],
            )

            # 落盘 job 终态
            fin = {
                'status': 'ok',
                'updated_at': datetime.now().isoformat(timespec='seconds'),
                'verified_count': len(items),
                'pages': sorted(by_page.keys()),
            }
            try:
                safe_json_dump(_job_path(paths), fin)
            except Exception:
                pass
            data['last_iterate'] = fin
            safe_json_dump(_verify_path(paths), data)
            _set_job(job_id, status='ok', phase='done', progress=100, msg='核验闭环完成', finished_at=time.time())
            return True, ''
        except Exception as e:
            traceback.print_exc()
            err = str(e)[:400]
            _set_job(job_id, status='failed', phase='done', progress=100, msg=err, error=err, finished_at=time.time())
            return False, err


def start_verify_iterate_job(username: str, analysis_id: str) -> str:
    job_id = uuid.uuid4().hex[:16]
    _set_job(
        job_id,
        status='running',
        phase='queued',
        progress=1,
        msg='排队中',
        username=username,
        analysis_id=analysis_id,
        error='',
        started_at=time.time(),
    )

    def _run():
        run_verify_iterate(username, analysis_id, job_id=job_id)

    threading.Thread(target=_run, daemon=True).start()
    return job_id
