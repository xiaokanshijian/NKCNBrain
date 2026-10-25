"""批改完成后钉本子结果卡；仅篇目诊断卡自动生图和 HTML。"""
import os
import re
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .explanation_layers import (
    build_diagnosis_card_body,
    build_excerpt_card_body,
    material_portrait_label,
)
from .utils import safe_json_dump, safe_json_load
from .yangqian_debug import debug_log

_PIN_JOBS: Dict[str, Dict[str, Any]] = {}
_PIN_JOBS_LOCK = threading.Lock()


def _completion_displayable(manifest: Dict[str, Any]) -> bool:
    completion = manifest.get('completion') or {}
    status = completion.get('status')
    if status == 'running':
        return False
    if completion.get('report_usable') or status in ('complete', 'unverified'):
        return True
    # 质量评分、终态复核、免检页未复核不挡钉卡；批改阶段完成即可把诊断卡钉进本子。
    return (manifest.get('stages') or {}).get('grading') == 'done'


def _skill_bundle(feedback_runtime) -> Dict[str, Any]:
    if feedback_runtime is None:
        return {}
    bundle = (feedback_runtime.dependencies or {}).get('references', {}).get('notebook_skills') or {}
    return bundle if isinstance(bundle, dict) else {}


def _skill_titles(feedback_runtime) -> list:
    bundle = _skill_bundle(feedback_runtime)
    if not bundle.get('enabled'):
        return []
    titles = []
    for member in bundle.get('members') or []:
        titles.append(str(member.get('title') or member.get('name') or '').strip())
    return [t for t in titles if t]


def _cross_essence(feedback_runtime) -> str:
    return str(_skill_bundle(feedback_runtime).get('cross_essence') or '').strip()[:600]


def _load_json(path: str) -> Dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {}
    try:
        data = safe_json_load(path)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _sample_id(analysis_id: str) -> str:
    return str(analysis_id or '').replace('homework_', '')[:8] or 'sample'


def _named_json(directory: str, subject: str, sample_id: str, suffix: str) -> Dict[str, Any]:
    if directory and subject and sample_id:
        named = os.path.join(directory, f'{subject}_{sample_id}{suffix}')
        data = _load_json(named)
        if data:
            return data
    if not directory or not os.path.isdir(directory):
        return {}
    skip_session = re.compile(r'_s\d+' + re.escape(suffix) + r'$')
    files = [
        path for path in sorted(Path(directory).glob('*' + suffix))
        if not skip_session.search(path.name)
    ]
    return _load_json(str(files[-1])) if files else {}


def _named_json_path(directory: str, subject: str, sample_id: str, suffix: str) -> str:
    if directory and subject and sample_id:
        named = os.path.join(directory, f'{subject}_{sample_id}{suffix}')
        if os.path.isfile(named):
            return named
    if not directory or not os.path.isdir(directory):
        return ''
    skip_session = re.compile(r'_s\d+' + re.escape(suffix) + r'$')
    files = [
        path for path in sorted(Path(directory).glob('*' + suffix))
        if not skip_session.search(path.name)
    ]
    return str(files[-1]) if files else ''


def _ensure_wgb_trust_for_cards(
    report: Dict[str, Any],
    ontology: Dict[str, Any],
    *,
    paths: Dict[str, str],
    subject: str,
    material_type: str,
    assigned_pages: Optional[list] = None,
    report_dir: str = '',
    sample_id: str = '',
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """钉卡前补齐 wgb_trust / user_verification，便于旧跑次重新沉淀也出「需核实」区。"""
    try:
        from .wgb_trust import build_user_verification_block, build_wgb_trust_summary, zones_for_verification
        from .utils import safe_json_dump
    except Exception:
        return report, ontology
    ont = dict(ontology or {})
    rep = dict(report or {})
    trust = ont.get('wgb_trust') if isinstance(ont.get('wgb_trust'), dict) else None
    if not trust or not trust.get('by_qid'):
        p1 = paths.get('pass1_json') or ''
        if p1 and os.path.isdir(p1):
            built = build_wgb_trust_summary(
                p1, subject or 'chinese',
                material_type=material_type or 'homework',
                assigned_pages=assigned_pages,
            )
            if built:
                trust = built
                ont['wgb_trust'] = {
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
                ont_path = os.path.join(paths.get('base') or '', 'student_ontology.json')
                if ont_path and os.path.isfile(ont_path):
                    try:
                        safe_json_dump(ont_path, ont)
                    except Exception:
                        pass
    uv = rep.get('user_verification')
    if trust and not (isinstance(uv, dict) and isinstance(uv.get('items'), list)):
        rep['user_verification'] = build_user_verification_block(trust, zones_for_verification(ont))
        rpath = _named_json_path(report_dir, subject, sample_id, '_report.json')
        if rpath:
            try:
                safe_json_dump(rpath, rep)
            except Exception:
                pass
    return rep, ont


def pin_grading_result_cards(paths: Dict[str, str], manifest: Dict[str, Any], *,
                             feedback_runtime=None) -> None:
    extra_dir = paths.get('base') or ''
    if not _completion_displayable(manifest):
        debug_log(
            f"[result_cards] 跳过钉卡：完成态不可展示 status={(manifest.get('completion') or {}).get('status')} "
            f"grading={(manifest.get('stages') or {}).get('grading')} analysis_id={manifest.get('analysis_id')}",
            extra_dir=extra_dir,
        )
        return
    username = str(manifest.get('username') or '').strip()
    filename = (manifest.get('selected_files') or [''])[0]
    if not username or not filename:
        debug_log(f'[result_cards] 跳过钉卡：缺 username/filename analysis_id={manifest.get("analysis_id")}', extra_dir=extra_dir)
        return
    scene_name = str(manifest.get('scene_name') or '').strip()
    sub_scene_name = str(manifest.get('sub_scene_name') or '').strip()
    if not scene_name or not sub_scene_name:
        try:
            from app_chat.scene_context_helper import get_scene_info_from_username
            sn, sub, _, _ = get_scene_info_from_username(username)
            scene_name = scene_name or str(sn or '').strip()
            sub_scene_name = sub_scene_name or str(sub or '').strip()
        except Exception:
            pass
    run_id = str(manifest.get('run_id') or '')
    analysis_id = str(manifest.get('analysis_id') or '')
    report_dir = paths.get('pass2_report') or ''
    ctx = (feedback_runtime.context if feedback_runtime is not None else None) or manifest.get('feedback_context') or {}
    subject = str(manifest.get('subject') or ctx.get('subject_code') or '').strip()
    sample_id = _sample_id(analysis_id)
    report = _named_json(report_dir, subject, sample_id, '_report.json')
    memory = _named_json(report_dir, subject, sample_id, '_memory.json')
    ontology = _load_json(os.path.join(paths.get('base') or '', 'student_ontology.json'))
    material_label = material_portrait_label(ctx, filename)
    titles = _skill_titles(feedback_runtime)
    essence = _cross_essence(feedback_runtime)
    assigned_pages_early = None
    gc_early = manifest.get('grading_config') if isinstance(manifest.get('grading_config'), dict) else {}
    if gc_early.get('assigned_pages'):
        try:
            assigned_pages_early = [int(p) for p in gc_early['assigned_pages']]
        except (TypeError, ValueError):
            assigned_pages_early = None
    material_type_early = str(
        (ctx.get('material_type') if isinstance(ctx, dict) else None)
        or (manifest.get('feedback_context') or {}).get('material_type')
        or 'homework'
    )
    report, ontology = _ensure_wgb_trust_for_cards(
        report, ontology,
        paths=paths,
        subject=subject or str(ctx.get('subject_code') or 'chinese'),
        material_type=material_type_early,
        assigned_pages=assigned_pages_early,
        report_dir=report_dir,
        sample_id=sample_id,
    )
    body = build_diagnosis_card_body(
        filename=filename, report=report, ontology=ontology, memory=memory,
        skill_titles=titles, material_label=material_label, cross_essence=essence,
    )
    effect = None
    if titles:
        try:
            from .skill_effect import judge_notebook_skill_effect
            effect = judge_notebook_skill_effect(
                username=username, card_text=body, skill_titles=titles,
                feedback_runtime=feedback_runtime,
            )
            if effect.get('level'):
                body = build_diagnosis_card_body(
                    filename=filename, report=report, ontology=ontology, memory=memory,
                    skill_titles=titles, effect=effect, material_label=material_label,
                    cross_essence=essence,
                )
        except Exception as exc:
            debug_log(f'[result_cards] 作用档判定失败: {exc}', extra_dir=extra_dir)
            effect = {'level': '', 'reason': str(exc)[:160], 'source': 'failed'}
    if titles and not (effect or {}).get('level'):
        manifest.setdefault('warnings', [])
        w = '本子方法作用档未写出（小模型与兜底均未成功），批改结果已保留。'
        if w not in manifest['warnings']:
            manifest['warnings'].append(w)
        debug_log(f'[result_cards] 作用档未写出 titles={titles} source={(effect or {}).get("source")}', extra_dir=extra_dir)
    elif titles:
        debug_log(
            f"[result_cards] 作用档={effect.get('level')} source={effect.get('source')} titles={titles}",
            extra_dir=extra_dir,
        )
    assigned_pages = None
    gc = manifest.get('grading_config') if isinstance(manifest.get('grading_config'), dict) else {}
    if gc.get('assigned_pages'):
        try:
            assigned_pages = [int(p) for p in gc['assigned_pages']]
        except (TypeError, ValueError):
            assigned_pages = None
    material_type = str(
        (ctx.get('material_type') if isinstance(ctx, dict) else None)
        or (manifest.get('feedback_context') or {}).get('material_type')
        or 'homework'
    )
    excerpt = build_excerpt_card_body(
        report,
        ontology,
        pass1_dir=paths.get('pass1_json') or '',
        subject=subject or str(ctx.get('subject_code') or 'chinese'),
        assigned_pages=assigned_pages,
        filename=filename,
        material_type=material_type,
        feedback_context=ctx if isinstance(ctx, dict) else None,
    )
    diag_cid = _upsert_card(
        username, scene_name, sub_scene_name, body,
        marker=f'批改·诊断|{analysis_id}|{run_id}',
        title_hint='诊断',
        filename=filename,
    )
    excerpt_cid = None
    if excerpt:
        excerpt_cid = _upsert_card(
            username, scene_name, sub_scene_name, excerpt,
            marker=f'批改·解释精要|{analysis_id}|{run_id}',
            title_hint='解释精要',
            filename=filename,
        )
    media_jobs = []
    if diag_cid:
        media_jobs.append((int(diag_cid), 'diagnosis'))
    if excerpt_cid:
        media_jobs.append((int(excerpt_cid), 'excerpt'))
    for cid, kind in media_jobs:
        try:
            from app_chat.views_card_image import mark_card_image_generating
            mark_card_image_generating(username, cid)
        except Exception as exc:
            debug_log(f'[result_cards] 登记生图队列失败 cid={cid}: {exc}', extra_dir=extra_dir)
        try:
            from app_chat.views_card_html import mark_card_html_generating
            mark_card_html_generating(username, cid)
        except Exception as exc:
            debug_log(f'[result_cards] 登记 HTML 队列失败 cid={cid}: {exc}', extra_dir=extra_dir)
        threading.Thread(
            target=_generate_media,
            args=(username, cid, analysis_id, run_id, extra_dir, kind),
            daemon=True,
        ).start()
    pinned = dict(manifest.get('result_cards') or {})
    pinned.update({
        'analysis_id': analysis_id, 'run_id': run_id,
        'diagnosis_cid': diag_cid, 'excerpt_cid': excerpt_cid,
        'skill_effect': effect or {},
    })
    manifest['result_cards'] = pinned
    debug_log(
        f'[result_cards] 已钉卡 analysis_id={analysis_id} run_id={run_id} '
        f'diagnosis_cid={diag_cid} excerpt_cid={excerpt_cid} scene={scene_name}/{sub_scene_name} file={filename}',
        extra_dir=extra_dir,
    )


def build_html_workspace_bundle(username: str, extra: Optional[Dict[str, Any]] = None,
                                card_content: str = '') -> str:
    """优先喂筛后卡片 Markdown；工作区只补短证据，禁止把未筛报告整墙塞进 HTML。"""
    extra = extra or {}
    analysis_id = str(extra.get('analysis_id') or '').strip()
    run_id = extra.get('run_id')
    if not analysis_id:
        marker = re.search(r'<!--nkcn_grading_card:批改·[^|]*\|([^|>]+)\|([^>]+)-->', card_content or '')
        if marker:
            analysis_id, run_id = marker.group(1).strip(), marker.group(2).strip()
    missing = []
    chunks = [
        '【HTML 构图纪律】先写 1 句枢纽；开放材料=线、诊断=面，职责不同；'
        '三区分栏短卡片（合计少而硬）；方法区写「因方法而改变的判断」禁止报名清单；'
        '循证后置。禁止复刻报告栏目墙。',
    ]
    refined = re.sub(r'<!--nkcn_grading_card:[^>]*-->\s*', '', card_content or '').strip()
    if refined:
        chunks.append('【筛后诊断卡正文·主素材】\n' + refined[:8000])
    if not analysis_id or not username:
        if refined:
            return '\n\n'.join(chunks)
        return '【批改工作区】本次未纳入（未定位到批改 run）。'
    try:
        from .service import prepare_homework_workspace
        paths = prepare_homework_workspace(username, analysis_id, None if run_id in (None, '', 'current') else run_id, create=False)
        manifest = _load_json(paths.get('manifest') or '')
        ctx = manifest.get('feedback_context') or {}
        subject = str(manifest.get('subject') or ctx.get('subject_code') or '').strip()
        sample_id = _sample_id(analysis_id)
        report = _named_json(paths.get('pass2_report') or '', subject, sample_id, '_report.json')
        memory = _named_json(paths.get('pass2_report') or '', subject, sample_id, '_memory.json')
        ontology = _load_json(os.path.join(paths.get('base') or '', 'student_ontology.json'))
        # 有筛后卡正文时，只补短摘，避免模型又复述整份报告
        if not refined and report:
            diagnosis = report.get('diagnosis') or {}
            overview = report.get('open_material_overview') or {}
            chunks.append('【整篇诊断·须放在 HTML 前部】\n' + str(diagnosis.get('summary') or '')[:2000])
            if overview:
                chunks.append('【开放材料概览·线·勿与诊断复述】\n' + json_preview(overview, 1200))
        elif not report:
            missing.append('Pass2 报告')
        if ontology and not refined:
            narrative = str(ontology.get('evolution_narrative') or '').strip()
            if narrative:
                chunks.append('【演化叙事·前部】\n' + narrative[:1600])
            chunks.append('【认知三区·前部分点】\n' + json_preview(ontology.get('zones') or {}, 1600))
        elif not ontology:
            missing.append('student_ontology')
        evidence = ['【循证依据·放 HTML 后部，勿抢前部】',
                    material_portrait_label(ctx, (manifest.get('selected_files') or [''])[0])]
        if memory:
            evidence.append('对错分布：' + json_preview(memory.get('verdict_distribution') or {}, 400))
            evidence.append('错因：' + json_preview(memory.get('error_type_distribution') or {}, 400))
        else:
            missing.append('记忆摘要')
        chunks.append('\n'.join(evidence))
    except Exception as exc:
        missing.append(f'工作区读取失败：{exc}')
    if missing:
        chunks.append('【本次未纳入】' + '、'.join(missing) + '。禁止据此编造课标句或 Hub/九论全文。')
    return '\n\n'.join(chunk for chunk in chunks if chunk and str(chunk).strip()) or '【批改工作区】本次未纳入。'


def json_preview(value: Any, limit: int) -> str:
    import json
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = str(value)
    return text[:limit]


def _upsert_card(username, scene_name, sub_scene_name, content, *, marker, title_hint, filename):
    from app_chat.models import Card
    from app_chat.views import (
        remove_emojis,
        resolve_subscene_title_prefix,
        generate_title_and_card_attrs_parallel,
        SEMANTIC_KEYWORDS_PENDING,
        start_fill_card_semantic_keywords_background,
    )

    stamped = remove_emojis(f'<!--nkcn_grading_card:{marker}-->\n' + content)
    existing = Card.objects.filter(username=username, content__contains=f'<!--nkcn_grading_card:{marker}-->').order_by('-cid').first()
    subSceneOrder, name_list, index = 'S0:', [], None
    if scene_name:
        try:
            subSceneOrder, name_list, index = resolve_subscene_title_prefix(scene_name, sub_scene_name)
        except Exception as exc:
            debug_log(f'[result_cards] 子场景前缀回退 S0: {exc}')
    stem = Path(filename).stem
    content_title = f'{subSceneOrder}批改·{title_hint}·{stem}'
    if existing:
        existing.content = stamped
        existing.contentTitle = content_title
        existing.save(update_fields=['content', 'contentTitle'])
        return existing.cid
    is_neuron = False
    try:
        is_neuron = index is not None and name_list and index + 1 == len(name_list)
    except Exception:
        pass
    four_color_type, dmt_level, is_analyzed = '紫', '', False
    try:
        _, four_color_type, dmt_level, is_analyzed = generate_title_and_card_attrs_parallel(
            stamped, username, scene_name, sub_scene_name,
            is_neuron=is_neuron, provisional_content_title=subSceneOrder,
        )
    except Exception as exc:
        debug_log(f'[result_cards] 卡片属性分析回退: {exc}')
    card = Card.objects.create(
        status=0, content=stamped, title='直接生成卡片', model_id=0, username=username,
        score=-2, color='紫', reason='', keyWords=SEMANTIC_KEYWORDS_PENDING,
        contentTitle=content_title, writer=username,
        four_color_type=four_color_type, dmt_level=dmt_level, is_neuron=is_neuron,
        is_analyzed_by_new_standard=is_analyzed,
    )
    try:
        start_fill_card_semantic_keywords_background(card.cid, username, username, scene_name, sub_scene_name, [])
    except Exception as exc:
        debug_log(f'[result_cards] 关键词后台任务跳过: {exc}')
    return card.cid


def _generate_media(
    username: str,
    cid: int,
    analysis_id: str = '',
    run_id: str = '',
    extra_dir: str = '',
    card_kind: str = 'diagnosis',
) -> None:
    debug_log(
        f'[result_cards] 开始生图/HTML cid={cid} kind={card_kind} '
        f'analysis_id={analysis_id} run_id={run_id}',
        extra_dir=extra_dir,
    )
    try:
        from app_chat.views_card_image import _run_batch, unmark_card_image_generating
        _run_batch(username, [cid], single_card=True)
        debug_log(f'[result_cards] 生图完成 cid={cid} kind={card_kind}', extra_dir=extra_dir)
    except Exception as exc:
        debug_log(f'[result_cards] 生图失败 cid={cid}: {exc}', extra_dir=extra_dir)
    finally:
        try:
            from app_chat.views_card_image import unmark_card_image_generating
            unmark_card_image_generating(username, cid)
        except Exception:
            pass
    try:
        from app_chat.views_card_html import generate_card_html_for_card, unmark_card_html_generating
        generate_card_html_for_card(
            username, cid,
            extra={
                'grading_result': True,
                'grading_excerpt': card_kind == 'excerpt',
                'analysis_id': analysis_id,
                'run_id': run_id,
            },
        )
        debug_log(f'[result_cards] HTML 完成 cid={cid} kind={card_kind}', extra_dir=extra_dir)
    except Exception as exc:
        debug_log(f'[result_cards] 生 HTML 失败 cid={cid}: {exc}', extra_dir=extra_dir)
    finally:
        try:
            from app_chat.views_card_html import unmark_card_html_generating
            unmark_card_html_generating(username, cid)
        except Exception:
            pass


def _set_pin_job(job_id: str, **kwargs) -> None:
    with _PIN_JOBS_LOCK:
        cur = _PIN_JOBS.get(job_id) or {}
        cur.update(kwargs)
        _PIN_JOBS[job_id] = cur


def get_pin_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _PIN_JOBS_LOCK:
        job = _PIN_JOBS.get(job_id)
        return dict(job) if job else None


def _rebuild_user_verification_for_pin(
    paths: Dict[str, str],
    manifest: Dict[str, Any],
) -> None:
    """按当前短名单规则重写 report.user_verification，供这次沉淀使用。"""
    from .wgb_trust import build_user_verification_block, build_wgb_trust_summary, zones_for_verification

    ctx = manifest.get('feedback_context') if isinstance(manifest.get('feedback_context'), dict) else {}
    subject = str(manifest.get('subject') or ctx.get('subject_code') or 'chinese').strip() or 'chinese'
    material_type = str(ctx.get('material_type') or ctx.get('material_key') or 'homework')
    assigned = None
    gc = manifest.get('grading_config') if isinstance(manifest.get('grading_config'), dict) else {}
    if gc.get('assigned_pages'):
        try:
            assigned = [int(p) for p in gc['assigned_pages']]
        except (TypeError, ValueError):
            assigned = None
    trust = build_wgb_trust_summary(
        paths.get('pass1_json') or '',
        subject,
        material_type=material_type,
        assigned_pages=assigned,
    ) or {}
    ont_path = os.path.join(paths.get('base') or '', 'student_ontology.json')
    ont = safe_json_load(ont_path) if ont_path and os.path.isfile(ont_path) else {}
    if not isinstance(ont, dict):
        ont = {}
    if trust:
        ont['wgb_trust'] = {
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
        if ont_path:
            safe_json_dump(ont_path, ont)
    block = build_user_verification_block(trust or ont.get('wgb_trust'), zones_for_verification(ont))
    sample_id = _sample_id(str(manifest.get('analysis_id') or ''))
    report_path = _named_json_path(paths.get('pass2_report') or '', subject, sample_id, '_report.json')
    report = safe_json_load(report_path) if report_path and os.path.isfile(report_path) else {}
    if isinstance(report, dict) and report_path:
        report['user_verification'] = block
        safe_json_dump(report_path, report)


def _suggestion_trust_for_current_list(
    paths: Dict[str, str],
    manifest: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """可点选项对着当前「需加强核实」名单生成。没有名单时返回 None，沿用原先的黑区/无白集合。"""
    from .wgb_trust import build_wgb_trust_summary

    ctx = manifest.get('feedback_context') if isinstance(manifest.get('feedback_context'), dict) else {}
    subject = str(manifest.get('subject') or ctx.get('subject_code') or 'chinese').strip() or 'chinese'
    material_type = str(ctx.get('material_type') or ctx.get('material_key') or 'homework')
    assigned = None
    gc = manifest.get('grading_config') if isinstance(manifest.get('grading_config'), dict) else {}
    if gc.get('assigned_pages'):
        try:
            assigned = [int(p) for p in gc['assigned_pages']]
        except (TypeError, ValueError):
            assigned = None
    trust = build_wgb_trust_summary(
        paths.get('pass1_json') or '',
        subject,
        material_type=material_type,
        assigned_pages=assigned,
    ) or {}
    sample_id = _sample_id(str(manifest.get('analysis_id') or ''))
    report_path = _named_json_path(paths.get('pass2_report') or '', subject, sample_id, '_report.json')
    report = safe_json_load(report_path) if report_path and os.path.isfile(report_path) else {}
    items = (report.get('user_verification') or {}).get('items') if isinstance(report, dict) else None
    if not isinstance(items, list) or not items:
        return None
    by_qid = trust.get('by_qid') or {}
    need = []
    for item in items:
        if not isinstance(item, dict):
            continue
        qid_global = str(item.get('qid_global') or '').strip()
        if not qid_global:
            continue
        row = dict(by_qid.get(qid_global) or {})
        row['qid_global'] = qid_global
        row['label'] = item.get('label') or row.get('label') or qid_global
        if row.get('page') is None and ':' in qid_global:
            head = qid_global.split(':', 1)[0].lstrip('pP')
            if head.isdigit():
                row['page'] = int(head)
        need.append(row)
    if not need:
        return None
    scoped = dict(trust)
    scoped['need_verify'] = need
    scoped['unit_word'] = (report.get('user_verification') or {}).get('unit_word') or trust.get('unit_word') or '题'
    return scoped


def run_pin_result_cards_job(
    username: str,
    analysis_id: str,
    *,
    job_id: str = '',
    force_regen_suggestions: bool = False,
    rebuild_user_verification: bool = False,
) -> Tuple[bool, str]:
    """手动重新沉淀：可选先（重新）生成可点短句，再钉卡。

    force_regen_suggestions=True：对需核实项全部重调模型（覆盖已有模型短句）。
    False：不调模型生成可点短句，直接用已有结果钉卡。
    与批改主流程无关：完整批改收尾本身会重出可点短句；核验后局部迭代才是「已有则跳过」。
    """
    from pathlib import Path as _Path
    from app_chat.homework_grading.service import prepare_homework_workspace
    from app_chat.homework_grading.feedback_runtime_service import restore_feedback_runtime
    from app_chat.homework_grading.verify_suggestions import generate_verify_suggestions

    try:
        _set_pin_job(job_id, status='running', phase='load', progress=5, msg='准备重新沉淀…', error='')
        paths = prepare_homework_workspace(username, analysis_id, None, create=False)
        manifest = safe_json_load(paths['manifest']) or {}
        if not isinstance(manifest, dict):
            raise ValueError('manifest 无效')
        runtime = None
        try:
            runtime = restore_feedback_runtime(_Path(paths['root']))
        except Exception:
            runtime = None

        if rebuild_user_verification:
            # 名单变了，可点选项必须按新名单重出，不能沿用旧题上的短句。
            force_regen_suggestions = True
            _set_pin_job(job_id, phase='verify_list', progress=12, msg='按当前规则重新给出需加强核实的位置…')
            _rebuild_user_verification_for_pin(paths, manifest)

        if force_regen_suggestions:
            suggest_trust = _suggestion_trust_for_current_list(paths, manifest)
            _set_pin_job(
                job_id,
                phase='verify_suggest',
                progress=20,
                msg='按需加强核实的位置重新生成可点短句（调用模型）…',
                page_index=0,
                pages_total=0,
            )

            def _on_suggest_progress(info: Dict[str, Any]) -> None:
                _set_pin_job(
                    job_id,
                    phase='verify_suggest',
                    progress=int(info.get('progress') or 20),
                    msg=str(info.get('msg') or '生成核验可点短句…'),
                    page_index=int(info.get('page_index') or 0),
                    pages_total=int(info.get('pages_total') or 0),
                    page_num=info.get('page_num'),
                )

            try:
                generate_verify_suggestions(
                    paths,
                    manifest,
                    feedback_runtime=runtime,
                    prefer_keep_llm=False,
                    trust=suggest_trust,
                    progress_cb=_on_suggest_progress,
                )
            except Exception as sug_exc:
                traceback.print_exc()
                debug_log(
                    f'[result_cards] 重新沉淀前生成可点短句失败: {sug_exc}',
                    extra_dir=paths.get('base'),
                )
            _set_pin_job(job_id, phase='verify_suggest', progress=55, msg='可点短句步骤完成，准备写入卡片…')
        else:
            _set_pin_job(
                job_id,
                phase='verify_suggest',
                progress=40,
                msg='跳过可点短句生成，沿用已有结果…',
            )

        existing_cards = manifest.get('result_cards') if isinstance(manifest.get('result_cards'), dict) else {}
        _set_pin_job(
            job_id,
            phase='cards',
            progress=70,
            msg='写入批改输出卡片（生图/HTML）…',
            result_cards=existing_cards,
        )
        pin_grading_result_cards(paths, manifest, feedback_runtime=runtime)
        safe_json_dump(paths['manifest'], manifest)
        pinned = manifest.get('result_cards') or {}
        _set_pin_job(job_id, result_cards=pinned, progress=92, msg='结果卡已写入，生图/HTML 进行中…')
        if not pinned.get('diagnosis_cid'):
            err = '当前结果尚不可沉淀（未完成项仍在），请先补齐批改。'
            _set_pin_job(
                job_id,
                status='failed',
                phase='done',
                progress=100,
                msg=err,
                error=err,
                result_cards=pinned,
                finished_at=time.time(),
            )
            return False, err

        _set_pin_job(
            job_id,
            status='ok',
            phase='done',
            progress=100,
            msg='重新沉淀完成',
            error='',
            result_cards=pinned,
            finished_at=time.time(),
        )
        return True, 'ok'
    except Exception as exc:
        traceback.print_exc()
        err = str(exc)[:400]
        _set_pin_job(
            job_id,
            status='failed',
            phase='done',
            progress=100,
            msg=err,
            error=err,
            finished_at=time.time(),
        )
        return False, err


def start_pin_result_cards_job(
    username: str,
    analysis_id: str,
    *,
    force_regen_suggestions: bool = False,
    rebuild_user_verification: bool = False,
) -> str:
    job_id = uuid.uuid4().hex[:16]
    _set_pin_job(
        job_id,
        status='running',
        phase='queued',
        progress=1,
        msg='排队中',
        username=username,
        analysis_id=analysis_id,
        error='',
        result_cards={},
        force_regen_suggestions=bool(force_regen_suggestions),
        rebuild_user_verification=bool(rebuild_user_verification),
        started_at=time.time(),
    )

    def _run():
        run_pin_result_cards_job(
            username,
            analysis_id,
            job_id=job_id,
            force_regen_suggestions=bool(force_regen_suggestions),
            rebuild_user_verification=bool(rebuild_user_verification),
        )

    threading.Thread(target=_run, daemon=True).start()
    return job_id
