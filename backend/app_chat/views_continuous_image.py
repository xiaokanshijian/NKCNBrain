import nkcn_public_config as _public_config
import base64
import json
import os
import mimetypes
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from django.http import JsonResponse, FileResponse, Http404, HttpResponseNotModified
from django.views.decorators.csrf import csrf_exempt
from app_chat.ci_access import ci_access, assert_workspace_path

# 作业批改页图多为 300DPI 原图，前端逐页查看用缩放预览即可（显著降延迟）
_CI_LAYOUT_PREVIEW_WIDTHS = frozenset({800, 1200, 1600, 2000})

from llm_langchain import global_var
from openai import OpenAI
from app_chat.continuous_image_service import (
    # 新架构
    build_analysis_id,
    CIIndexManager,
    prepare_analysis_workspace,
    query_ci_analyses,
    run_ci_analysis,
    redo_ci_analysis,
    run_ci_sketch_r_quickstart,
    start_ci_reproduction,
    iterate_ci_reproduction_unit,
    save_ci_reproduction_file,
    save_ci_reproduction_iter_context,
    _is_reproduction_iterating,
    _parse_reference_image_payload,
    get_ci_result,
    rollback_ci_reproduction_unit,
    _ci_dmt_root,
    _ci_d_cache_root,
    # 旧架构兼容
    build_group_id,
    get_continuous_image_result,
    run_continuous_image_analysis,
)

import datetime as _datetime
from app_chat.ci.overlay_layer import (
    build_ci_overlay_result,
    can_start_ci_overlay_job,
    get_ci_overlay_item,
    get_ci_overlay_job,
    load_ci_overlay_history,
    run_ci_sketch_handwriting_estimate_and_persist,
    save_ci_overlay_file,
    start_ci_overlay_generate_job,
    start_ci_overlay_iterate_job,
    stream_ci_dmt_overlay_prompt,
    _load_ci_context,
)
from app_chat.ci.auto_iteration import (
    evaluate_ci_d_regions_confidence,
    get_ci_auto_iter_low_confidence_candidates,
    load_ci_d_regions_confidence_result,
    mark_ci_auto_iter_regions_used,
    preview_ci_auto_iteration_round,
    recognize_ci_d_region,
    run_ci_apply_lite_bundle_to_reproduction,
    run_ci_auto_iteration_round,
)
from app_chat.ci.layout_iteration import iterate_ci_layout_regions
from app_chat.homework_classifier import ensure_homework_attrs_for_file, is_homework_pdf_attrs, is_pdf_filename, load_document_attrs
from app_chat.homework_grading.feedback_request import resolve_feedback_request
from app_chat.feedback_material_settings import merge_saved_material_settings
from app_chat.homework_grading.service import (
    build_homework_analysis_id,
    check_homework_stage_ready,
    get_homework_grading_result,
    is_homework_analysis_id,
    normalize_homework_target_stage,
    prepare_homework_workspace,
    run_homework_grading,
    run_homework_red_blue_review,
)
from app_chat.homework_grading.red_blue_review import (
    build_iteration_context,
    load_iteration_context,
    load_red_blue_review,
    save_iteration_context,
)
from app_chat.homework_grading.grader_pass1 import pass1_two_stage_enabled
from app_chat.homework_grading.preprocess import (
    PREPROCESS_MODE_AUTO,
    normalize_preprocess_mode,
    preprocess_mode_from_manifest,
    preprocess_mode_matches_manifest,
)
from app_chat.homework_grading.homework_versions import (
    archive_homework_run_if_exists,
    clear_homework_workspace_for_rerun,
    get_homework_rerun_sessions,
    invalidate_homework_stage_for_rerun,
    list_homework_versions,
    normalize_homework_rerun_stage,
    prepare_homework_session_rerun,
    set_homework_version_key,
)
from app_chat.homework_grading.pass3_service import (
    build_cross_analysis_id,
    find_pass3_pairs,
    get_pass3_result,
    is_cross_subject_analysis_id,
    run_pass3,
)
from app_chat.ci._utils import _safe_json_dump, _safe_json_load


_REFINE_GEMINI_BASE = _public_config.endpoint('NKCN_REVIEW_GATEWAY_V1_URL', 'http://localhost:9999/v1')
_REFINE_GEMINI_KEY = _public_config.secret('NKCN_LLM_DMXAPI_API_KEY')
_REFINE_GEMINI_MODEL = 'gemini-3.1-pro-preview'
_REFINE_QWEN_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
_REFINE_QWEN_KEY = (
    os.environ.get('DEEPSEEK_API_KEY_ALI')
    or os.environ.get('DASHSCOPE_API_KEY')
    or os.environ.get('NKCN_SNIPPET_QWEN_API_KEY')
    or _public_config.secret('NKCN_LLM_DASHSCOPE_API_KEY')
)
_REFINE_QWEN_MODEL = 'qwen3.6-plus'
_REFINE_T_HISTORY_FILE = 't_layer_refine_history.json'
_GRADE_GEMINI_MODEL_ABBR = 'gemini-3.1-pro-preview'
_GRADE_CLAUDE_MODEL_ABBR = 'claude-sonnet-4.6'


def _ci_sm(key, default):
    from app_chat.scene_models import get_scene_value
    return get_scene_value(key, default)


def _load_runtime_model_cfg(model_abbr: str, default_model: str, default_base: str, default_key: str = '') -> Dict[str, str]:
    cfg_path = os.path.join(os.path.dirname(__file__), 'config', 'model_config', f'{model_abbr}.json')
    if not os.path.isfile(cfg_path):
        return {'model': default_model, 'base_url': default_base, 'api_key': default_key}
    try:
        raw = _safe_json_load(cfg_path)
        cfg = raw.get('config') if isinstance(raw, dict) else {}
        model = str((cfg or {}).get('model_name') or default_model).strip()
        base = str((cfg or {}).get('openai_api_base') or default_base).strip()
        key = str((cfg or {}).get('openai_api_key') or default_key).strip()
        return {'model': model or default_model, 'base_url': base or default_base, 'api_key': key or default_key}
    except Exception:
        return {'model': default_model, 'base_url': default_base, 'api_key': default_key}


def _coerce_images_to_data_urls(images: Any) -> List[str]:
    if isinstance(images, str):
        items = [images]
    elif isinstance(images, list):
        items = images
    else:
        items = []
    out: List[str] = []
    for item in items:
        val = str(item or '').strip()
        if not val:
            continue
        if val.startswith('data:image/'):
            out.append(val)
            continue
        out.append(f'data:image/png;base64,{val}')
    return out


def _build_multimodal_content(text: str, image_data_urls: List[str]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = [{'type': 'text', 'text': text}]
    for idx, image_url in enumerate(image_data_urls, start=1):
        payload.append({'type': 'text', 'text': f'【图片{idx}】'})
        payload.append({'type': 'image_url', 'image_url': {'url': image_url}})
    return payload


def _chat_completion_with_retry(
    cfg: Dict[str, str],
    messages: List[Dict[str, Any]],
    temperature: float,
    max_tokens: int,
    retries: int = 2,
) -> Tuple[str, int]:
    attempts = max(0, int(retries)) + 1
    last_error = ''
    for idx in range(attempts):
        try:
            client = OpenAI(
                api_key=cfg.get('api_key') or '',
                base_url=str(cfg.get('base_url') or '').rstrip('/') + '/',
                timeout=240,
            )
            rsp = client.chat.completions.create(
                model=cfg.get('model') or '',
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = str(rsp.choices[0].message.content or '').strip()
            if text:
                return text, idx + 1
            raise RuntimeError('empty_model_output')
        except Exception as e:
            last_error = str(e)
    raise RuntimeError(last_error or 'model_call_failed_after_retry')


def _extract_claude_sections(text: str) -> Dict[str, str]:
    raw = str(text or '')
    raw = raw.replace('\r\n', '\n').replace('\r', '\n').strip()
    parts = {'part1': '', 'part2': '', 'part3': ''}

    m1 = raw.find('【一】')
    m2 = raw.find('【二】', m1 + 1 if m1 >= 0 else 0)
    m3 = raw.find('【三】', m2 + 1 if m2 >= 0 else 0)

    if m1 >= 0:
        end1 = m2 if m2 >= 0 else None
        parts['part1'] = raw[m1 + len('【一】'): end1].strip() if end1 is not None else raw[m1 + len('【一】'):].strip()
    if m2 >= 0:
        end2 = m3 if m3 >= 0 else None
        parts['part2'] = raw[m2 + len('【二】'): end2].strip() if end2 is not None else raw[m2 + len('【二】'):].strip()
    if m3 >= 0:
        parts['part3'] = raw[m3 + len('【三】'):].strip()

    # 若 markers 没找到或三段都为空，兜底：把全文塞到 part2 里
    if not any(parts.values()):
        parts['part2'] = raw

    return parts
def _to_data_url_by_file(abs_path: str) -> str:
    ext = os.path.splitext(abs_path or '')[1].lower()
    mime = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
    }.get(ext, 'image/png')
    raw = open(abs_path, 'rb').read()
    return f'data:{mime};base64,{base64.b64encode(raw).decode("utf-8")}'


def _to_data_url_by_file_doc_import(abs_path: str) -> str:
    """与文档导入区一致：util.encode_image 默认 >2MB 压到约 1MB 以内。"""
    from llm_langchain import util  # noqa: PLC0415

    if not abs_path or not os.path.isfile(abs_path):
        raise ValueError('missing_image_file')
    file_size_mb = os.path.getsize(abs_path) / (1024 * 1024)
    ext = os.path.splitext(abs_path)[1].lower().lstrip('.')
    mime = {
        'jpg': 'jpeg',
        'jpeg': 'jpeg',
        'png': 'png',
        'webp': 'webp',
        'gif': 'gif',
        'bmp': 'bmp',
    }.get(ext, 'jpeg')
    b64 = util.encode_image(abs_path)
    if file_size_mb > 2:
        mime = 'jpeg'
    return f'data:image/{mime};base64,{b64}'


def _sample_card_content_2000(text: str) -> str:
    content = str(text or '')
    if len(content) <= 2000:
        return content
    head = content[:700]
    tail = content[-700:]
    middle: List[str] = []
    for ratio in (0.25, 0.5, 0.75):
        center = int(len(content) * ratio)
        start = max(700, min(center - 100, len(content) - 900))
        middle.append(content[start:start + 200])
    return '\n...\n'.join([head] + middle + [tail])


def _serialize_struct_value(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                pairs = [f'{str(k)}={str(v)}' for k, v in item.items() if str(v).strip()]
                if pairs:
                    lines.append('- ' + '；'.join(pairs))
            elif str(item).strip():
                lines.append('- ' + str(item).strip())
        return '\n'.join(lines).strip()
    if isinstance(value, dict):
        pairs = [f'{str(k)}={str(v)}' for k, v in value.items() if str(v).strip()]
        return '；'.join(pairs)
    return str(value).strip()


def _build_t_layer_structured_text(t_layer: Dict[str, Any]) -> str:
    sec = [
        ('📝 总体理解', _serialize_struct_value(t_layer.get('overall_summary'))),
        ('🎯 核心主题', _serialize_struct_value(t_layer.get('core_theme'))),
        ('🔗 多图关系', _serialize_struct_value(t_layer.get('group_relations'))),
        ('📄 图文关联', _serialize_struct_value(t_layer.get('doc_relations'))),
        ('🌐 场景意义', _serialize_struct_value(t_layer.get('scene_meaning'))),
        ('💡 认知建议-盲区', _serialize_struct_value(t_layer.get('blind_spots'))),
        ('💡 认知建议-内耗区', _serialize_struct_value(t_layer.get('internal_friction'))),
        ('💡 认知建议-最近发展区', _serialize_struct_value(t_layer.get('zpd_next_step'))),
        ('💡 认知建议-下一步建议', _serialize_struct_value(t_layer.get('next_actions'))),
        ('🧩 本体萃取-升维语义萃取', _serialize_struct_value(t_layer.get('semantic_layer_candidate'))),
        ('🧩 本体萃取-部落知识萃取', _serialize_struct_value(t_layer.get('tribal_candidate'))),
    ]
    return '\n\n'.join([f'【{title}】\n{body or "（空）"}' for title, body in sec]).strip()


def _parse_t_layer_structured_text(text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(fallback or {})
    raw = str(text or '')
    markers = [
        ('📝 总体理解', 'overall_summary'),
        ('🎯 核心主题', 'core_theme'),
        ('🔗 多图关系', 'group_relations'),
        ('📄 图文关联', 'doc_relations'),
        ('🌐 场景意义', 'scene_meaning'),
        ('💡 认知建议-盲区', 'blind_spots'),
        ('💡 认知建议-内耗区', 'internal_friction'),
        ('💡 认知建议-最近发展区', 'zpd_next_step'),
        ('💡 认知建议-下一步建议', 'next_actions'),
        ('🧩 本体萃取-升维语义萃取', 'semantic_layer_candidate'),
        ('🧩 本体萃取-部落知识萃取', 'tribal_candidate'),
    ]
    for idx, (title, key) in enumerate(markers):
        next_title = markers[idx + 1][0] if idx + 1 < len(markers) else ''
        if next_title:
            pattern = rf'【{re.escape(title)}】\s*([\s\S]*?)\s*(?=【{re.escape(next_title)}】)'
        else:
            pattern = rf'【{re.escape(title)}】\s*([\s\S]*?)$'
        match = re.search(pattern, raw, flags=re.MULTILINE)
        if not match:
            continue
        value = (match.group(1) or '').strip()
        if value in ('（空）', '(空)', '空'):
            value = ''
        out[key] = value
    return out


def _collect_ci_refine_context_text(
    username: str,
    manifest: Dict[str, Any],
    context_docs: Optional[List[str]] = None,
    context_card_ids: Optional[List[int]] = None,
) -> Tuple[str, str]:
    context_cfg = manifest.get('context_config') if isinstance(manifest, dict) else {}
    docs_raw = context_docs if context_docs is not None else (context_cfg.get('user_selected_docs') if isinstance(context_cfg, dict) else [])
    cards_raw = context_card_ids if context_card_ids is not None else (context_cfg.get('user_selected_card_ids') if isinstance(context_cfg, dict) else [])
    selected_docs = [str(name or '').strip() for name in (docs_raw or []) if str(name or '').strip()]
    card_ids = [int(item) for item in (cards_raw or []) if str(item).strip().isdigit()]
    base_dir = os.path.join('.', 'received_dir', 'user_raw_file', username)

    doc_blocks: List[str] = []
    for doc_name in selected_docs:
        base = os.path.splitext(os.path.basename(doc_name))[0]
        ext = os.path.splitext(doc_name)[1].lower().lstrip('.')
        pre_summary_path = os.path.join(base_dir, 'pre_summary', f'{base}_Presummary_{ext}.md')
        pre_image_path = os.path.join(base_dir, 'pre_image_summary', f'{base}_PreImageSummary_pdf.md')
        pre_summary = ''
        pre_image = ''
        if os.path.isfile(pre_summary_path):
            pre_summary = open(pre_summary_path, 'r', encoding='utf-8').read().strip()
        if os.path.isfile(pre_image_path):
            pre_image = open(pre_image_path, 'r', encoding='utf-8').read().strip()
        if pre_summary or pre_image:
            doc_blocks.append(
                f'【文档】{doc_name}\n'
                f'【PreSummary】\n{(pre_summary or "（无）")[:3200]}\n'
                f'【PreImageSummary】\n{(pre_image or "（无）")[:3200]}'
            )

    card_blocks: List[str] = []
    if card_ids:
        from app_chat.models import Card  # noqa: PLC0415
        cards = list(Card.objects.filter(username=username, cid__in=card_ids).order_by('cid'))
        if not cards:
            cards = list(Card.objects.filter(cid__in=card_ids).order_by('cid'))
        for card in cards:
            card_blocks.append(
                f'【卡片#{card.cid}】\n'
                f'标题：{(card.contentTitle or card.title or "").strip()}\n'
                f'关键词：{(card.keyWords or "").strip()}\n'
                f'内容：\n{_sample_card_content_2000(card.content or "")}'
            )
    return '\n\n'.join(doc_blocks).strip(), '\n\n'.join(card_blocks).strip()

# ════════════════════════════════════════════════════════════════
# 新架构主流程 API（/api/ci/*）
# ════════════════════════════════════════════════════════════════


def _optional_sketch_preprocess_flag(data: dict) -> Optional[bool]:
    """解析 sketch_preprocess：None 表示沿用服务端环境默认；否则 True/False 覆盖。"""
    raw = data.get('sketch_preprocess')
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(int(raw))
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ('0', 'false', 'off', 'no', ''):
            return False
        if s in ('1', 'true', 'on', 'yes'):
            return True
    return bool(raw)


def _optional_context_flag(data: dict, key: str, default: bool = True) -> bool:
    raw = data.get(key, default)
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if text in ('0', 'false', 'no', 'n', 'off'):
        return False
    return default


@csrf_exempt
@ci_access
def ci_query(request):
    """查询指定文件关联的所有分析记录。
    POST { username, files }
    → { error_num, singles, groups, superset_match }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        files = data.get('files', [])
        scene_name = (data.get('scene_name') or data.get('sceneName') or '').strip()
        if not username:
            return JsonResponse({'error_num': 1, 'msg': '缺少username'})
        clean_files = [f for f in files if f]
        feedback_request = None
        if len(clean_files) == 1 and is_pdf_filename(clean_files[0]):
            effective_data, _ = merge_saved_material_settings(
                getattr(request, 'ci_workspace', '') or username,
                clean_files[0],
                data,
            )
            feedback_request = resolve_feedback_request(
                clean_files[0], effective_data.get('feedback_overrides'), effective_data.get('requested_action', 'auto'),
                legacy_attrs=load_document_attrs(username, clean_files[0], scene_name=scene_name),
            )
        result = query_ci_analyses(username, clean_files)
        from app_chat.homework_grading.feedback_task_recovery import enrich_query_records
        enrich_query_records(username, result.get('singles', []))
        if feedback_request is not None:
            from app_chat.ci._utils import _resolve_user_file_path
            from app_chat.homework_grading.feedback_observation import collect_observation
            feedback_request['content_validation'] = collect_observation(
                _resolve_user_file_path(username, clean_files[0]), feedback_request['feedback_context'])
            result['homework_status'] = {
                'filename': clean_files[0],
                **feedback_request,
                'analysis_type': feedback_request['route'],
            }
            result.update({key: feedback_request[key] for key in (
                'feedback_eligible', 'parse_status', 'feedback_context', 'warnings', 'recommended_action')})
        return JsonResponse({'error_num': 0, **result})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'查询失败: {e}'})


@csrf_exempt
@ci_access
def ci_start(request):
    """启动单图/多图分析。
    POST { username, files, mode, context_docs?, context_card_ids?, preprocess_mode? }
    → { error_num, task_id, analysis_id, msg }
      msg: 'success' | 'existing_result' | 'superset_exists'
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        files = [f for f in (data.get('files') or []) if f]
        mode = (data.get('mode') or ('single' if len(files) == 1 else 'group')).strip()
        model_id = data.get('model_id')
        scene_name = (data.get('scene_name') or data.get('sceneName') or '').strip()
        context_docs = data.get('context_docs') or None          # 用户勾选的辅助文档名列表
        context_card_ids = data.get('context_card_ids') or None  # 用户勾选的辅助卡片ID列表

        if not username:
            return JsonResponse({'error_num': 1, 'msg': '缺少username'})
        if not files:
            return JsonResponse({'error_num': 1, 'msg': 'files不能为空'})

        requested_action = data.get('requested_action', 'auto')
        if requested_action not in ('auto', 'grading', 'understanding'):
            return JsonResponse({'error_num': 1, 'msg': '操作意图无效'})
        if requested_action == 'grading' and (mode != 'single' or len(files) != 1 or not is_pdf_filename(files[0])):
            return JsonResponse({'error_num': 1, 'msg': '批改当前仅支持单份PDF'})
        if mode == 'single' and len(files) == 1 and is_pdf_filename(files[0]):
            data, _ = merge_saved_material_settings(
                getattr(request, 'ci_workspace', '') or username,
                files[0],
                data,
            )
            resolution = resolve_feedback_request(
                files[0], data.get('feedback_overrides'), requested_action,
                legacy_attrs=load_document_attrs(username, files[0], scene_name=scene_name),
            )
            if resolution['route'] == 'unsupported':
                return JsonResponse({'error_num': 1, 'msg': '本阶段仅支持作业和试卷批改',
                                     'warnings': resolution['warnings']})
            if resolution['route'] == 'homework_grading':
                from app_chat.homework_grading.feedback_start_service import start_grading_request
                return JsonResponse(start_grading_request(username, files[0],
                                                          data, resolution=resolution))

        analysis_id = build_analysis_id(mode, files)
        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'

        # ── 检查是否已有完成结果 ──────────────────────────────────
        rec = CIIndexManager.find_by_id(username, analysis_id)
        if rec and rec.get('status') == 'completed':
            global_var.tasks[task_id] = {
                'current_item': 1, 'total_items': 1,
                'current_section': '完成', 'completed': True, 'error': '',
            }
            return JsonResponse({
                'error_num': 0, 'task_id': task_id,
                'analysis_id': analysis_id, 'msg': 'existing_result',
            })

        # ── 多图时检查是否有超集已完成（直接展示超集结果）─────────
        if mode == 'group' and len(files) > 1:
            sup = CIIndexManager.find_superset_group(username, files)
            if sup:
                global_var.tasks[task_id] = {
                    'current_item': 1, 'total_items': 1,
                    'current_section': '完成', 'completed': True, 'error': '',
                }
                return JsonResponse({
                    'error_num': 0, 'task_id': task_id,
                    'analysis_id': sup['analysis_id'], 'msg': 'superset_exists',
                })

        # ── 注册到索引 ──────────────────────────────────────────
        now = _datetime.datetime.now().isoformat()
        CIIndexManager.add_or_update(username, {
            'analysis_id': analysis_id,
            'mode': mode,
            'files': files,
            'status': 'running',
            'created_at': now,
            'updated_at': now,
        })

        global_var.tasks[task_id] = {
            'current_item': 0, 'total_items': 0,
            'current_section': '准备中', 'completed': False, 'error': '',
        }

        t = threading.Thread(
            target=run_ci_analysis,
            kwargs={
                'task_id': task_id,
                'username': username,
                'mode': mode,
                'selected_files': files,
                'analysis_id': analysis_id,
                'force_rebuild_mt': False,
                'model_id': model_id,
                'context_docs': context_docs,
                'context_card_ids': context_card_ids,
            },
            daemon=True,
        )
        t.start()

        return JsonResponse({
            'error_num': 0, 'task_id': task_id,
            'analysis_id': analysis_id, 'msg': 'success',
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动失败: {e}'})


@csrf_exempt
@ci_access
def ci_progress(request, task_id):
    """任务进度轮询（与旧接口相同结构）。"""
    task = getattr(request, 'ci_task', None) or global_var.tasks.get(task_id)
    if not task:
        return JsonResponse({
            'error_num': 1, 'msg': '任务不存在',
            'error_code': 'task_not_found', 'retryable': False,
            'current_item': 0, 'total_items': 0,
            'current_section': '任务记录缺失', 'completed': False, 'error': '任务不存在',
        })
    if task.get('_ci_persistent'):
        from app_chat.homework_grading.feedback_task_recovery import recover_abandoned_task
        try:
            task = recover_abandoned_task(task)
        except (OSError, ValueError, KeyError) as exc:
            return JsonResponse({'error_num': 1, 'msg': f'任务恢复检查失败: {exc}',
                                 'error_code': 'recovery_unavailable', 'retryable': True,
                                 'completed': False, 'failure_stage': 'recovery', 'error': str(exc)})
    completion = task.get('completion')
    if task.get('_ci_persistent') and task.get('task_kind') in ('homework_grading', 'homework_red_blue_review'):
        from app_chat.homework_grading.feedback_task_recovery import completion_for_task
        try:
            completion = completion_for_task(task)
        except (OSError, ValueError, KeyError):
            return JsonResponse({'error_num': 1, 'msg': '批改状态暂不可读，请重新连接',
                                 'error_code': 'result_state_unavailable', 'retryable': True})
    return JsonResponse({
        'error_num': 0,
        'current_item': task.get('current_item', 0),
        'run_id': task.get('run_id', ''),
        'completion': completion,
        'workspace': task.get('_ci_workspace') or task.get('username', ''),
        'config_fingerprint': task.get('config_fingerprint', ''),
        'status': task.get('status', ''),
        'failure_stage': task.get('failure_stage', ''),
        'content_validation': task.get('content_validation', {'status': 'inconclusive'}),
        'warnings': task.get('warnings', []),
        'total_items': task.get('total_items', 0),
        'current_section': task.get('current_section', '准备中'),
        'completed': task.get('completed', False),
        'error': task.get('error', ''),
        'analysis_id': task.get('analysis_id', ''),
        'unit_id': task.get('unit_id', ''),
        'task_kind': task.get('task_kind', ''),
        'analysis_type': task.get('analysis_type', 'homework_grading' if task.get('task_kind') == 'homework_grading' else ''),
    })


@csrf_exempt
@ci_access
def ci_result(request):
    """按 analysis_id 获取分析结果。
    POST { username, analysis_id }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        if not username or not analysis_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username 或 analysis_id'})
        rec = CIIndexManager.find_by_id(username, analysis_id)
        if is_cross_subject_analysis_id(analysis_id) or (rec and rec.get('analysis_type') == 'cross_subject'):
            result = get_pass3_result(username, analysis_id)
            if result is None:
                return JsonResponse({'error_num': 1, 'msg': '双科交叉分析结果不存在'})
            return JsonResponse({'error_num': 0, **result})
        if is_homework_analysis_id(analysis_id) or (rec and rec.get('analysis_type') == 'homework_grading'):
            run_id = (data.get('run_id') or data.get('runId') or '').strip()
            return JsonResponse(get_homework_grading_result(username, analysis_id, run_id=run_id or None))
        result = get_ci_result(username, analysis_id)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'读取结果失败: {e}'})


@csrf_exempt
@ci_access
def ci_pass3_pairs(request):
    """列出可进行双科交叉诊断的候选配对。
    POST { username }
    → { error_num, pairs: [...] }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        if not username:
            return JsonResponse({'error_num': 1, 'msg': '缺少username'})
        return JsonResponse({'error_num': 0, 'pairs': find_pass3_pairs(username)})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'查询失败: {e}'})


@csrf_exempt
@ci_access
def ci_pass3_start(request):
    """启动双科交叉诊断（Pass3）。
    POST { username, analysis_id_a, analysis_id_b }
    → { error_num, task_id, analysis_id, analysis_type }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id_a = (data.get('analysis_id_a') or '').strip()
        analysis_id_b = (data.get('analysis_id_b') or '').strip()
        if not username or not analysis_id_a or not analysis_id_b:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username 或 analysis_id'})
        if analysis_id_a == analysis_id_b:
            return JsonResponse({'error_num': 1, 'msg': '需要两份不同学科的作业'})

        cross_id = build_cross_analysis_id(analysis_id_a, analysis_id_b)
        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'

        rec = CIIndexManager.find_by_id(username, cross_id)
        if rec and rec.get('status') == 'completed':
            global_var.tasks[task_id] = {
                'current_item': 1, 'total_items': 1,
                'current_section': '完成', 'completed': True, 'error': '',
                'analysis_id': cross_id,
                'task_kind': 'cross_subject',
                'analysis_type': 'cross_subject',
            }
            return JsonResponse({
                'error_num': 0, 'task_id': task_id,
                'analysis_id': cross_id, 'analysis_type': 'cross_subject',
                'msg': 'existing_result',
            })

        global_var.tasks[task_id] = {
            'current_item': 0, 'total_items': 0,
            'current_section': '准备双科交叉诊断', 'completed': False, 'error': '',
            'analysis_id': cross_id,
            'task_kind': 'cross_subject',
            'analysis_type': 'cross_subject',
        }
        t = threading.Thread(
            target=run_pass3,
            kwargs={
                'task_id': task_id,
                'username': username,
                'analysis_id_a': analysis_id_a,
                'analysis_id_b': analysis_id_b,
            },
            daemon=True,
        )
        t.start()
        return JsonResponse({
            'error_num': 0, 'task_id': task_id,
            'analysis_id': cross_id, 'analysis_type': 'cross_subject',
            'msg': 'success',
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动失败: {e}'})


@csrf_exempt
@ci_access
def ci_redo(request):
    """迭代 M/T 层（不迭代 D 层 OCR）。
        POST { username, analysis_id, redo_scope? }
            redo_scope: 'mt' | 't'（默认 mt）
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        redo_scope = (data.get('redo_scope') or 'mt').strip().lower()
        if redo_scope not in ('mt', 't'):
            redo_scope = 'mt'
        if not username or not analysis_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username 或 analysis_id'})

        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})

        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'
        CIIndexManager.update_status(username, analysis_id, 'running')
        global_var.tasks[task_id] = {
            'current_item': 0, 'total_items': 0,
            'current_section': '准备中', 'completed': False, 'error': '',
            'analysis_id': analysis_id,
            'unit_id': '',
            'task_kind': 'redo_t_only' if redo_scope == 't' else 'redo_analysis',
        }
        t = threading.Thread(
            target=redo_ci_analysis,
            kwargs={
                'task_id': task_id,
                'username': username,
                'analysis_id': analysis_id,
                'redo_scope': redo_scope,
            },
            daemon=True,
        )
        t.start()
        return JsonResponse({'error_num': 0, 'task_id': task_id, 'analysis_id': analysis_id, 'redo_scope': redo_scope})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'迭代失败: {e}'})


@csrf_exempt
@ci_access
def ci_homework_versions(request):
    """列出作业批改的历史版本（含当前）。
    POST { username, analysis_id }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        if not username or not analysis_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username 或 analysis_id'})
        if not is_homework_analysis_id(analysis_id):
            return JsonResponse({'error_num': 1, 'msg': '非作业批改分析'})
        return JsonResponse({
            'error_num': 0,
            'analysis_id': analysis_id,
            'versions': list_homework_versions(username, analysis_id),
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'读取版本列表失败: {e}'})


@csrf_exempt
@ci_access
def ci_homework_version_key(request):
    """设置或取消关键历史版本。
    POST { username, analysis_id, run_id, is_key }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        run_id = (data.get('run_id') or '').strip()
        raw_is_key = data.get('is_key')
        is_key = raw_is_key is True or str(raw_is_key).strip().lower() in ('1', 'true', 'yes', 'on')
        if not username or not analysis_id or not run_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username、analysis_id 或 run_id'})
        if not is_homework_analysis_id(analysis_id):
            return JsonResponse({'error_num': 1, 'msg': '非作业批改分析'})
        item = set_homework_version_key(username, analysis_id, run_id, is_key)
        return JsonResponse({
            'error_num': 0,
            'analysis_id': analysis_id,
            'run_id': run_id,
            'is_key_version': bool(item.get('is_key_version')),
            'versions': list_homework_versions(username, analysis_id),
            'msg': 'success',
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'设置关键历史版本失败: {e}'})


@csrf_exempt
@ci_access
def ci_homework_rerun(request):
    """当前版本重跑，依据继承和副本发布由统一启动服务处理。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        from app_chat.homework_grading.feedback_start_service import start_grading_request
        from app_chat.homework_grading.homework_versions import resolve_homework_run_root
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        if not username or not is_homework_analysis_id(analysis_id):
            raise ValueError('缺少本子或有效批改标识')
        if data.get('run_id') not in (None, '', 'current'):
            raise ValueError('请先查看历史版本；重跑操作当前仅针对当前版本')
        root = resolve_homework_run_root(username, analysis_id)
        manifest = _safe_json_load(os.path.join(root, 'manifest.json'))
        files = manifest.get('selected_files') or []
        if len(files) != 1 or not isinstance(files[0], str):
            raise ValueError('原运行未保存单份PDF文件名，请从材料入口完整新跑')
        from app_chat.feedback_material_identity import resolve_source_filename
        filename = resolve_source_filename(username, files[0], manifest.get('source_document_sha256'))
        return JsonResponse(start_grading_request(username, filename, data, rerun=True))
    except Exception as exc:
        return JsonResponse({'error_num': 1, 'msg': f'迭代失败: {exc}'})


@csrf_exempt
@ci_access
def ci_homework_red_blue_retry(request):
    """只重试当前完成版本的红蓝卡标，不触发批改流水线。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        if data.get('run_id') not in (None, '', 'current'):
            return JsonResponse({'error_num': 1, 'msg': '历史版本仅供查看，请切回当前版本再评分'})
        if not username or not analysis_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username 或 analysis_id'})
        if not is_homework_analysis_id(analysis_id):
            return JsonResponse({'error_num': 1, 'msg': '非作业批改分析'})
        from app_chat.homework_grading.feedback_quality_retry import start_quality_retry
        return JsonResponse(start_quality_retry(username, analysis_id, sid=data.get('sid')))
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'重新评分失败: {e}'})


@csrf_exempt
@ci_access
def ci_homework_pin_result_cards(request):
    """重新沉淀：可选重调模型生成可点短句，再钉卡（异步任务，前端右下角轮询进度）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        run_id = data.get('run_id')
        force_regen = bool(
            data.get('force_regen_suggestions')
            or data.get('regen_suggestions')
            or data.get('force_regen')
        )
        rebuild_verification = bool(
            data.get('rebuild_user_verification')
            or data.get('regen_user_verification')
        )
        if rebuild_verification:
            force_regen = True
        if run_id not in (None, '', 'current'):
            return JsonResponse({'error_num': 1, 'msg': '历史版本仅供查看，请切回当前版本再沉淀'})
        if not username or not analysis_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username 或 analysis_id'})
        if not is_homework_analysis_id(analysis_id):
            return JsonResponse({'error_num': 1, 'msg': '非作业批改分析'})
        from app_chat.homework_grading.result_cards import start_pin_result_cards_job
        job_id = start_pin_result_cards_job(
            username,
            analysis_id,
            force_regen_suggestions=force_regen,
            rebuild_user_verification=rebuild_verification,
        )
        return JsonResponse({
            'error_num': 0,
            'msg': 'started',
            'job_id': job_id,
            'force_regen_suggestions': force_regen,
            'rebuild_user_verification': rebuild_verification,
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'重新沉淀失败: {e}'})


@csrf_exempt
@ci_access
def ci_homework_pin_result_cards_status(request):
    """轮询重新沉淀任务进度。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        job_id = str(data.get('job_id') or '').strip()
        if not job_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 job_id'})
        from app_chat.homework_grading.result_cards import get_pin_job
        job = get_pin_job(job_id)
        if not job:
            return JsonResponse({'error_num': 1, 'msg': '任务不存在或已过期'})
        return JsonResponse({'error_num': 0, 'msg': 'success', 'job': job})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'查询进度失败: {e}'})


@csrf_exempt
@ci_access
def ci_homework_verify_save(request):
    """解释精要/核实闭环：保存单条人工核验结果（不立刻重批）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        if data.get('run_id') not in (None, '', 'current'):
            return JsonResponse({'error_num': 1, 'msg': '历史版本仅供查看，请切回当前版本再核验'})
        if not username or not is_homework_analysis_id(analysis_id):
            return JsonResponse({'error_num': 1, 'msg': '缺少本子或有效批改标识'})
        from app_chat.homework_grading import verify_loop as vl
        item = vl.save_verification_item(
            username,
            analysis_id,
            qid_global=str(data.get('qid_global') or '').strip(),
            label=str(data.get('label') or '').strip(),
            verdict=str(data.get('verdict') or '').strip(),
            step_notes=data.get('step_notes') if isinstance(data.get('step_notes'), dict) else {},
        )
        bundle = vl.load_verifications(username, analysis_id)
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'item': item,
            'verified_count': len(bundle.get('items') or {}),
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'保存核验失败: {e}'})


@csrf_exempt
@ci_access
def ci_homework_verify_list(request):
    """列出当次批改已提交的核验记录。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        if not username or not is_homework_analysis_id(analysis_id):
            return JsonResponse({'error_num': 1, 'msg': '缺少本子或有效批改标识'})
        from app_chat.homework_grading import verify_loop as vl
        bundle = vl.load_verifications(username, analysis_id)
        return JsonResponse({'error_num': 0, 'msg': 'success', 'verifications': bundle})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'读取核验失败: {e}'})


@csrf_exempt
@ci_access
def ci_homework_verify_iterate(request):
    """按已提交核验局部重批并回写当次结果（异步任务）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        if data.get('run_id') not in (None, '', 'current'):
            return JsonResponse({'error_num': 1, 'msg': '历史版本仅供查看，请切回当前版本再迭代更新'})
        if not username or not is_homework_analysis_id(analysis_id):
            return JsonResponse({'error_num': 1, 'msg': '缺少本子或有效批改标识'})
        from app_chat.homework_grading import verify_loop as vl
        bundle = vl.load_verifications(username, analysis_id)
        if not (bundle.get('items') or {}):
            return JsonResponse({'error_num': 1, 'msg': '请先至少提交一条核验结果'})
        job_id = vl.start_verify_iterate_job(username, analysis_id)
        return JsonResponse({'error_num': 0, 'msg': 'started', 'job_id': job_id})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动迭代更新失败: {e}'})


@csrf_exempt
@ci_access
def ci_homework_verify_iterate_status(request):
    """轮询核验迭代任务进度。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        job_id = str(data.get('job_id') or '').strip()
        if not job_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 job_id'})
        from app_chat.homework_grading import verify_loop as vl
        job = vl.get_job(job_id)
        if not job:
            return JsonResponse({'error_num': 1, 'msg': '任务不存在或已过期'})
        return JsonResponse({'error_num': 0, 'msg': 'success', 'job': job})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'查询进度失败: {e}'})


@csrf_exempt
def ci_sketch_r_quickstart(request):
    """无完整 M/T 理解时，原草图直出 R 层复现图并建立最小分析工作区。
    POST { username, files: [filename] }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        files = [f for f in (data.get('files') or []) if f]
        if not username:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username'})
        if not files:
            return JsonResponse({'error_num': 1, 'msg': 'files 不能为空'})

        mode = 'single' if len(files) == 1 else 'group'
        analysis_id = build_analysis_id(mode, files)
        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'

        global_var.tasks[task_id] = {
            'current_item': 0,
            'total_items': 0,
            'current_section': '准备中',
            'completed': False,
            'error': '',
            'analysis_id': analysis_id,
            'task_kind': 'reproduction_generate',
        }

        def _run():
            try:
                run_ci_sketch_r_quickstart(task_id, username, files)
            except Exception as exc:
                global_var.tasks[task_id]['error'] = str(exc)
                global_var.tasks[task_id]['completed'] = True
                global_var.tasks[task_id]['current_section'] = '失败'

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        return JsonResponse({
            'error_num': 0,
            'task_id': task_id,
            'analysis_id': analysis_id,
            'msg': 'success',
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动失败: {e}'})


@csrf_exempt
def ci_reproduction_start(request):
    """启动指定分析的复现图生成。
    POST { username, analysis_id, force_rebuild?, use_sketch_input?, use_original_sketch_as_r? }
    当 use_sketch_input 为 true 且 use_original_sketch_as_r 为 true 时，跳过模型升维，将原草图复制为 R 层复现图。
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        force_rebuild = bool(data.get('force_rebuild', False))
        use_sketch_input = bool(data.get('use_sketch_input', True))
        use_original_sketch_as_r = bool(data.get('use_original_sketch_as_r', False))
        if not username or not analysis_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username 或 analysis_id'})

        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})

        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'
        global_var.tasks[task_id] = {
            'current_item': 0, 'total_items': 0,
            'current_section': '准备中', 'completed': False, 'error': '',
            'analysis_id': analysis_id,
            'unit_id': '',
            'task_kind': 'reproduction_generate',
        }

        t = threading.Thread(
            target=start_ci_reproduction,
            kwargs={
                'task_id': task_id,
                'username': username,
                'analysis_id': analysis_id,
                'force_rebuild': force_rebuild,
                'use_sketch_input': use_sketch_input,
                'use_original_sketch_as_r': use_original_sketch_as_r,
            },
            daemon=True,
        )
        t.start()
        return JsonResponse({'error_num': 0, 'task_id': task_id, 'analysis_id': analysis_id})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动复现图生成失败: {e}'})


@csrf_exempt
def ci_reproduction_update_context(request):
    """同步保存R层单页生成依据。
    POST { username, analysis_id, unit_id, iter_context }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        iter_context = data.get('iter_context') or {}
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        saved_item = save_ci_reproduction_iter_context(username, analysis_id, unit_id, iter_context)
        return JsonResponse({'error_num': 0, 'msg': 'success', 'analysis_id': analysis_id, 'unit_id': unit_id, 'r_item': saved_item})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'保存R层生成依据失败: {e}'})


@csrf_exempt
def ci_reproduction_iterate(request):
    """启动R层单页图片迭代。
    POST { username, analysis_id, unit_id, revision_instruction?, reference_image?, image_quality?, iter_context? }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        revision_instruction = (data.get('revision_instruction') or '').strip() or None
        reference_image_b64, reference_image_mime = _parse_reference_image_payload(data.get('reference_image'))
        image_quality = (data.get('image_quality') or 'normal').strip().lower()
        if image_quality not in ('normal', 'high'):
            image_quality = 'normal'
        iter_context = data.get('iter_context') or None
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        if _is_reproduction_iterating(username, analysis_id, unit_id):
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'
        global_var.tasks[task_id] = {
            'current_item': 0, 'total_items': 1,
            'current_section': '准备中', 'completed': False, 'error': '',
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'task_kind': 'reproduction_iterate_unit',
        }

        from app_chat.continuous_image_service import _set_reproduction_iterating
        _set_reproduction_iterating(username, analysis_id, unit_id, True)

        t = threading.Thread(
            target=iterate_ci_reproduction_unit,
            kwargs={
                'task_id': task_id,
                'username': username,
                'analysis_id': analysis_id,
                'unit_id': unit_id,
                'revision_instruction': revision_instruction,
                'reference_image_b64': reference_image_b64,
                'reference_image_mime': reference_image_mime,
                'image_quality': image_quality,
                'iter_context_updates': iter_context,
            },
            daemon=True,
        )
        t.start()
        return JsonResponse({'error_num': 0, 'msg': 'success', 'task_id': task_id, 'analysis_id': analysis_id, 'unit_id': unit_id})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动R层单页迭代失败: {e}'})


@csrf_exempt
def ci_reproduction_iterate_layout_regions(request):
    """启动基于覆盖层版面的单页定向迭代。
    POST { username, analysis_id, unit_id, selected_regions, iteration_mode?, reference_image?, image_quality?, iter_context? }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        selected_regions = data.get('selected_regions') or []
        iteration_mode = str(data.get('iteration_mode') or 'rewrite').strip().lower()
        if iteration_mode not in ('rewrite', 'crop'):
            iteration_mode = 'rewrite'
        reference_image_b64, reference_image_mime = _parse_reference_image_payload(data.get('reference_image'))
        image_quality = (data.get('image_quality') or 'normal').strip().lower()
        if image_quality not in ('normal', 'high'):
            image_quality = 'normal'
        iter_context = data.get('iter_context') or None
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        if _is_reproduction_iterating(username, analysis_id, unit_id):
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'
        global_var.tasks[task_id] = {
            'current_item': 0, 'total_items': 1,
            'current_section': '准备中', 'completed': False, 'error': '',
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'task_kind': 'reproduction_iterate_layout_regions',
            'iteration_mode': iteration_mode,
        }

        from app_chat.continuous_image_service import _set_reproduction_iterating
        _set_reproduction_iterating(username, analysis_id, unit_id, True)

        t = threading.Thread(
            target=iterate_ci_layout_regions,
            kwargs={
                'task_id': task_id,
                'username': username,
                'analysis_id': analysis_id,
                'unit_id': unit_id,
                'selected_regions': selected_regions,
                'iteration_mode': iteration_mode,
                'reference_image_b64': reference_image_b64,
                'reference_image_mime': reference_image_mime,
                'image_quality': image_quality,
                'iter_context_updates': iter_context,
            },
            daemon=True,
        )
        t.start()
        return JsonResponse({'error_num': 0, 'msg': 'success', 'task_id': task_id, 'analysis_id': analysis_id, 'unit_id': unit_id, 'iteration_mode': iteration_mode})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动版面级单页迭代失败: {e}'})


@csrf_exempt
def ci_reproduction_auto_iterate_preview(request):
    """预览基于 D 版面的单图自动迭代识别结果。
    POST { username, analysis_id, unit_id, selected_region_ids, mode?, sketch_preprocess?, use_recognition_context? }
    sketch_preprocess: 可选 bool，是否先做整图 handwriting_isolate 再裁切识字；不传则 NKCN_CI_SNIPPET_SKETCH_PREPROCESS。
    use_recognition_context: 可选 bool，是否向识字模型注入 card/doc 上下文和候选词表（默认 true）。
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        selected_region_ids = data.get('selected_region_ids') or []
        mode = str(data.get('mode') or 'semi').strip().lower()
        if mode not in ('semi', 'full', 'full_lite'):
            mode = 'semi'
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        if _is_reproduction_iterating(username, analysis_id, unit_id):
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

        sketch_preprocess = _optional_sketch_preprocess_flag(data)
        use_recognition_context = _optional_context_flag(data, 'use_recognition_context', True)
        preview = preview_ci_auto_iteration_round(
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
            selected_region_ids=selected_region_ids,
            mode=mode,
            sketch_preprocess=sketch_preprocess,
            use_recognition_context=use_recognition_context,
        )
        return JsonResponse({'error_num': 0, 'msg': 'success', **preview})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'预览单图自动迭代失败: {e}'})


@csrf_exempt
def ci_reproduction_recognize_d_region(request):
    """单 D 版面 Gemini+Qwen 识字预览，并写入分析目录 ci_audit/d_region_recognition_audit.jsonl。
    POST { username, analysis_id, unit_id, region_id, sketch_preprocess?, use_recognition_context?, preview_only? }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        region_id = str(data.get('region_id') or '').strip()
        if not username or not analysis_id or not unit_id or not region_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id / region_id'})

        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        if _is_reproduction_iterating(username, analysis_id, unit_id):
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

        sketch_preprocess = _optional_sketch_preprocess_flag(data)
        use_recognition_context = _optional_context_flag(data, 'use_recognition_context', True)
        preview_only = _optional_context_flag(data, 'preview_only', False)
        out = recognize_ci_d_region(
            username,
            analysis_id,
            unit_id,
            region_id,
            sketch_preprocess=sketch_preprocess,
            use_recognition_context=use_recognition_context,
            preview_only=preview_only,
        )
        if not out.get('success'):
            return JsonResponse({'error_num': 1, 'msg': out.get('msg') or 'd_region_recognize_failed'})
        if out.get('preview_only'):
            return JsonResponse({
                'error_num': 0,
                'msg': 'success',
                'preview_only': True,
                'model_input_crop_b64': out.get('model_input_crop_b64') or '',
                'analysis_id': out.get('analysis_id') or analysis_id,
                'unit_id': out.get('unit_id') or unit_id,
                'region_id': out.get('region_id') or region_id,
            })
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'recognition_payload': out.get('recognition_payload') or {},
            'audit_log_path': out.get('audit_log_path') or '',
            'analysis_id': out.get('analysis_id') or analysis_id,
            'unit_id': out.get('unit_id') or unit_id,
            'region_id': out.get('region_id') or region_id,
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'D 版面识字失败: {e}'})


@csrf_exempt
def ci_reproduction_d_confidence_batch(request):
    """批量评估 D 区字迹识别置信度（支持 qwen / gemini）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        confidence_model = (data.get('confidence_model') or 'qwen').strip()
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        if _is_reproduction_iterating(username, analysis_id, unit_id):
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

        out = evaluate_ci_d_regions_confidence(
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
            confidence_model=confidence_model,
        )
        if not out.get('success'):
            return JsonResponse({'error_num': 1, 'msg': out.get('msg') or 'd_confidence_failed'})
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'analysis_id': out.get('analysis_id') or analysis_id,
            'unit_id': out.get('unit_id') or unit_id,
            'result_file_path': out.get('result_file_path') or '',
            'model': out.get('model') or '',
            'reference_region_id': out.get('reference_region_id') or '',
            'results': out.get('results') or [],
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'D 区置信度评估失败: {e}'})


@csrf_exempt
def ci_reproduction_d_confidence_result(request):
    """读取当前 analysis/unit 已有 D 区字迹识别置信度结果文件。"""
    if request.method != 'GET':
        return JsonResponse({'error_num': 1, 'msg': '仅支持GET'})
    try:
        username = (request.GET.get('username') or '').strip()
        analysis_id = (request.GET.get('analysis_id') or '').strip()
        unit_id = (request.GET.get('unit_id') or '').strip()
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        out = load_ci_d_regions_confidence_result(
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
        )
        if not out.get('success'):
            return JsonResponse({'error_num': 1, 'msg': out.get('msg') or 'not_found', 'result_file_path': out.get('result_file_path') or ''})
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'analysis_id': out.get('analysis_id') or analysis_id,
            'unit_id': out.get('unit_id') or unit_id,
            'result_file_path': out.get('result_file_path') or '',
            'model': out.get('model') or '',
            'reference_region_id': out.get('reference_region_id') or '',
            'results': out.get('results') or [],
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'读取 D 区置信度结果失败: {e}'})


@csrf_exempt
def ci_reproduction_d_confidence_pick_auto_regions(request):
    """按置信度升序自动挑选待迭代 D 区（默认前9，排除已成功取用）。"""
    if request.method != 'GET':
        return JsonResponse({'error_num': 1, 'msg': '仅支持GET'})
    try:
        username = (request.GET.get('username') or '').strip()
        analysis_id = (request.GET.get('analysis_id') or '').strip()
        unit_id = (request.GET.get('unit_id') or '').strip()
        limit_raw = request.GET.get('limit')
        try:
            limit = int(limit_raw) if limit_raw is not None else 9
        except Exception:
            limit = 9
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        out = get_ci_auto_iter_low_confidence_candidates(username, analysis_id, unit_id, limit=limit)
        if not out.get('success'):
            return JsonResponse({'error_num': 1, 'msg': out.get('msg') or 'pick_failed'})
        return JsonResponse({'error_num': 0, 'msg': 'success', **out})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'自动挑选 D 区失败: {e}'})


@csrf_exempt
def ci_reproduction_d_confidence_mark_used(request):
    """记录本次自动挑选 D 区是否已成功完成迭代。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        region_ids = data.get('region_ids') or []
        status = (data.get('status') or 'success').strip().lower()
        note = str(data.get('note') or '').strip()
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        out = mark_ci_auto_iter_regions_used(
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
            region_ids=region_ids if isinstance(region_ids, list) else [],
            status='success' if status == 'success' else 'failed',
            note=note,
        )
        if not out.get('success'):
            return JsonResponse({'error_num': 1, 'msg': out.get('msg') or 'mark_failed'})
        return JsonResponse({'error_num': 0, 'msg': 'success', **out})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'记录自动挑选 D 区失败: {e}'})


@csrf_exempt
def ci_reproduction_auto_iterate_round(request):
    """启动基于 D 版面的单图自动迭代轮次。
    POST { username, analysis_id, unit_id, mode?, selected_region_ids?, gray_resolutions?, start_region_id?, continue_from_cursor?, image_quality?, iter_context?, sketch_preprocess?, use_recognition_context? }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        mode = str(data.get('mode') or 'full').strip().lower()
        if mode not in ('semi', 'full', 'full_lite'):
            mode = 'full'
        selected_region_ids = data.get('selected_region_ids') or []
        gray_resolutions = data.get('gray_resolutions') or []
        start_region_id = (data.get('start_region_id') or '').strip()
        continue_from_cursor = bool(data.get('continue_from_cursor', True))
        image_quality = (data.get('image_quality') or 'normal').strip().lower()
        if image_quality not in ('normal', 'high'):
            image_quality = 'normal'
        iter_context = data.get('iter_context') or None
        sketch_preprocess = _optional_sketch_preprocess_flag(data)
        use_recognition_context = _optional_context_flag(data, 'use_recognition_context', True)
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        if _is_reproduction_iterating(username, analysis_id, unit_id):
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'
        global_var.tasks[task_id] = {
            'current_item': 0, 'total_items': 1,
            'current_section': '准备中', 'completed': False, 'error': '',
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'task_kind': 'reproduction_auto_iterate_round',
        }

        from app_chat.continuous_image_service import _set_reproduction_iterating
        _set_reproduction_iterating(username, analysis_id, unit_id, True)

        t = threading.Thread(
            target=run_ci_auto_iteration_round,
            kwargs={
                'task_id': task_id,
                'username': username,
                'analysis_id': analysis_id,
                'unit_id': unit_id,
                'start_region_id': start_region_id,
                'continue_from_cursor': continue_from_cursor,
                'image_quality': image_quality,
                'iter_context_updates': iter_context,
                'mode': mode,
                'selected_region_ids': selected_region_ids,
                'gray_resolutions': gray_resolutions,
                'sketch_preprocess': sketch_preprocess,
                'use_recognition_context': use_recognition_context,
            },
            daemon=True,
        )
        t.start()
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'task_id': task_id,
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'mode': mode,
            'selected_region_ids': selected_region_ids,
            'start_region_id': start_region_id,
            'continue_from_cursor': continue_from_cursor,
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动单图自动迭代失败: {e}'})


@csrf_exempt
def ci_reproduction_apply_lite_bundle(request):
    """将已保存的「全自动-直接执行&平衡效率和质量」D 区识字结果贴补到当前 R 层复现图。
    POST { username, analysis_id, unit_id, image_quality?, iter_context? }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        image_quality = (data.get('image_quality') or 'normal').strip().lower()
        if image_quality not in ('normal', 'high'):
            image_quality = 'normal'
        iter_context = data.get('iter_context') or None
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        rec = CIIndexManager.find_by_id(username, analysis_id)
        if not rec:
            return JsonResponse({'error_num': 1, 'msg': f'分析 {analysis_id} 不存在'})
        if _is_reproduction_iterating(username, analysis_id, unit_id):
            return JsonResponse({'error_num': 1, 'msg': 'generating', 'generating': True})

        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'
        global_var.tasks[task_id] = {
            'current_item': 0, 'total_items': 1,
            'current_section': '准备中', 'completed': False, 'error': '',
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'task_kind': 'reproduction_apply_lite_bundle',
        }

        from app_chat.continuous_image_service import _set_reproduction_iterating
        _set_reproduction_iterating(username, analysis_id, unit_id, True)

        t = threading.Thread(
            target=run_ci_apply_lite_bundle_to_reproduction,
            kwargs={
                'task_id': task_id,
                'username': username,
                'analysis_id': analysis_id,
                'unit_id': unit_id,
                'image_quality': image_quality,
                'iter_context_updates': iter_context,
            },
            daemon=True,
        )
        t.start()
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'task_id': task_id,
            'analysis_id': analysis_id,
            'unit_id': unit_id,
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动轻量识字贴补R层失败: {e}'})


@csrf_exempt
def ci_reproduction_rollback(request):
    """回滚R层单页复现图到上一版本。
    POST { username, analysis_id, unit_id }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        saved_item = rollback_ci_reproduction_unit(username, analysis_id, unit_id)
        return JsonResponse({'error_num': 0, 'msg': 'success', 'analysis_id': analysis_id, 'unit_id': unit_id, 'r_item': saved_item})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'回滚R层复现图失败: {e}'})


@csrf_exempt
def ci_reproduction_save(request):
    """保存当前页手工编辑后的复现图。
    POST { username, analysis_id, unit_id, reproduction_image }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        reproduction_image = data.get('reproduction_image')
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        saved_item = save_ci_reproduction_file(username, analysis_id, unit_id, reproduction_image)
        return JsonResponse({'error_num': 0, 'msg': 'success', 'analysis_id': analysis_id, 'unit_id': unit_id, 'r_item': saved_item})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'保存R层复现图失败: {e}'})


@csrf_exempt
def ci_overlay_prompt_stream(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        include_tm_context = data.get('include_tm_context', True)
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        stream = stream_ci_dmt_overlay_prompt(username, analysis_id, unit_id, include_tm_context=include_tm_context)
        from django.http import StreamingHttpResponse  # noqa: PLC0415

        result = StreamingHttpResponse(stream, content_type='text/plain; charset=utf-8')
        result['Cache-Control'] = 'no-cache'
        result['X-Accel-Buffering'] = 'no'
        return result
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': str(e)})


@csrf_exempt
def ci_overlay_estimate_handwriting(request):
    """仅估算原草图手写区域占比并写入 overlay_layer（与 DMT 流式分离）。
    POST { username, analysis_id, unit_id }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        out = run_ci_sketch_handwriting_estimate_and_persist(username, analysis_id, unit_id)
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'handwriting_area_ratio': out.get('handwriting_area_ratio'),
            'coarse_layout': out.get('coarse_layout'),
            'estimate_note': out.get('estimate_note') or '',
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'手写占比估算失败: {e}'})


@csrf_exempt
def ci_overlay_generate(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        instruction_text = (data.get('instruction_text') or '').strip()
        include_tm_context = data.get('include_tm_context', True)
        dmt_generated = data.get('dmt_generated', False)
        reference_image_b64, reference_image_mime = _parse_reference_image_payload(data.get('reference_image'))
        image_quality = (data.get('image_quality') or 'normal').strip().lower()
        if image_quality not in ('normal', 'high'):
            image_quality = 'normal'
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        ok, reason = can_start_ci_overlay_job(username, analysis_id, unit_id)
        if not ok:
            return JsonResponse({'error_num': 1, 'msg': reason, 'generating': reason == 'generating'})
        start_ci_overlay_generate_job(
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
            instruction_text=instruction_text,
            reference_image_b64=reference_image_b64,
            reference_image_mime=reference_image_mime,
            image_quality=image_quality,
            include_tm_context=include_tm_context,
            dmt_generated=dmt_generated,
        )
        return JsonResponse({'error_num': 0, 'msg': 'queued'})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动覆盖层生成失败: {e}'})


@csrf_exempt
def ci_overlay_status(request):
    if request.method != 'GET':
        return JsonResponse({'error_num': 1, 'msg': '仅支持GET'})
    try:
        username = (request.GET.get('username') or '').strip()
        analysis_id = (request.GET.get('analysis_id') or '').strip()
        unit_id = (request.GET.get('unit_id') or '').strip()
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        job = get_ci_overlay_job(username, analysis_id, unit_id)
        overlay_item = get_ci_overlay_item(username, analysis_id, unit_id)
        if not job:
            return JsonResponse({'error_num': 0, 'status': 'idle', 'overlay_item': overlay_item})
        return JsonResponse({'error_num': 0, **job, 'overlay_item': job.get('overlay_item') or overlay_item})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': str(e)})


@csrf_exempt
def ci_overlay_history(request):
    if request.method != 'GET':
        return JsonResponse({'error_num': 1, 'msg': '仅支持GET'})
    try:
        username = (request.GET.get('username') or '').strip()
        analysis_id = (request.GET.get('analysis_id') or '').strip()
        unit_id = (request.GET.get('unit_id') or '').strip()
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        items = load_ci_overlay_history(username, analysis_id, unit_id)
        overlay_item = get_ci_overlay_item(username, analysis_id, unit_id)
        return JsonResponse({'error_num': 0, 'msg': 'success', 'items': items, 'overlay_item': overlay_item})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': str(e)})


@csrf_exempt
def ci_overlay_save(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    req_t0 = time.perf_counter()
    try:
        parse_t0 = time.perf_counter()
        data = json.loads(request.body)
        print(
            f'[CI overlay save] request parse: {time.perf_counter() - parse_t0:.3f}s | '
            f'body_bytes={len(request.body)}',
            flush=True,
        )
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        overlay_image = data.get('overlay_image')
        target = (data.get('target') or 'current').strip().lower()
        overlay_level = (data.get('overlay_level') or '').strip().lower()
        preserve_exact = bool(data.get('preserve_exact', False))
        regions = data.get('regions')
        if target not in ('prev', 'current'):
            target = 'current'
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        save_t0 = time.perf_counter()
        saved = save_ci_overlay_file(
            username,
            analysis_id,
            unit_id,
            overlay_image,
            target,
            preserve_exact=preserve_exact,
            overlay_level=overlay_level,
            regions=regions if isinstance(regions, list) else None,
        )
        print(f'[CI overlay save] save_ci_overlay_file call: {time.perf_counter() - save_t0:.3f}s', flush=True)
        print(f'[CI overlay save] request total: {time.perf_counter() - req_t0:.3f}s', flush=True)
        return JsonResponse({'error_num': 0, 'msg': 'success', 'overlay_item': saved})
    except Exception as e:
        print(f'[CI overlay save] request failed after {time.perf_counter() - req_t0:.3f}s: {e}', flush=True)
        return JsonResponse({'error_num': 1, 'msg': str(e)})


@csrf_exempt
def ci_overlay_iterate(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        overlay_image = data.get('overlay_image')
        instruction_text = (data.get('instruction_text') or '').strip()
        reference_image_b64, reference_image_mime = _parse_reference_image_payload(data.get('reference_image'))
        image_quality = (data.get('image_quality') or 'normal').strip().lower()
        if image_quality not in ('normal', 'high'):
            image_quality = 'normal'
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        ok, reason = can_start_ci_overlay_job(username, analysis_id, unit_id)
        if not ok:
            return JsonResponse({'error_num': 1, 'msg': reason, 'generating': reason == 'generating'})
        start_ci_overlay_iterate_job(
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
            overlay_image=overlay_image,
            instruction_text=instruction_text,
            reference_image_b64=reference_image_b64,
            reference_image_mime=reference_image_mime,
            image_quality=image_quality,
        )
        return JsonResponse({'error_num': 0, 'msg': 'queued'})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动覆盖层迭代失败: {e}'})


# ════════════════════════════════════════════════════════════════
# 新架构资源/辅助 API（/api/ci/*）
# ════════════════════════════════════════════════════════════════


def _ci_layout_preview_path(abs_path: str, max_w: int) -> str:
    from app_chat.homework_grading.layout_preview import preview_path
    return preview_path(abs_path, max_w)


def _ci_ensure_layout_preview(abs_path: str, max_w: int) -> Tuple[str, str]:
    """按需生成并落盘预览 JPEG；失败则回退原图。"""
    from app_chat.homework_grading.layout_preview import ensure_preview
    return ensure_preview(abs_path, max_w, force=False)


def _ci_file_etag(abs_path: str) -> str:
    st = os.stat(abs_path)
    return f'"{int(st.st_mtime)}-{st.st_size}"'


@csrf_exempt
@ci_access
def ci_layout_visual(request):
    """服务版面可视化文件（新架构：优先查 d_cache）。

    可选 query：
      w=800|1200|1600|2000  → 返回等比缩放 JPEG 预览（磁盘缓存），用于作业批改逐页查看降延迟
    """
    path = (request.GET.get('path') or '').strip()
    username = (request.GET.get('username') or '').strip()
    analysis_id = (request.GET.get('analysis_id') or '').strip()
    run_id = (request.GET.get('run_id') or request.GET.get('runId') or '').strip()
    raw_w = (request.GET.get('w') or request.GET.get('max_w') or '').strip()
    preview_w = 0
    if raw_w.isdigit():
        candidate = int(raw_w)
        if candidate in _CI_LAYOUT_PREVIEW_WIDTHS:
            preview_w = candidate
    if not path:
        raise Http404('缺少 path 参数')

    allowed_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.gif', '.pdf'}
    ext = os.path.splitext(path)[1].lower()
    if ext not in allowed_exts:
        raise Http404('不支持的文件类型')

    abs_path = ''
    if os.path.isabs(path):
        abs_path = os.path.normpath(path)
    else:
        rel = os.path.normpath(path).replace('\\', os.sep)
        candidates = []
        if username and analysis_id:
            from app_chat.homework_grading.homework_versions import resolve_homework_run_root
            try:
                base_root = resolve_homework_run_root(username, analysis_id, run_id or None)
            except ValueError as exc:
                raise Http404(str(exc))
            candidates.append(os.path.join(base_root, rel))
        if username:
            candidates.append(os.path.join(_ci_d_cache_root(username), rel))
            candidates.append(os.path.join('.', 'received_dir', 'user_raw_file', username, rel))
        for c in candidates:
            c = os.path.normpath(c)
            if os.path.isfile(c):
                abs_path = c
                break

    if not abs_path or not os.path.isfile(abs_path):
        raise Http404(f'文件不存在: {path}')

    abs_path = assert_workspace_path(username, abs_path)
    serve_path = abs_path
    mime_type, _ = mimetypes.guess_type(abs_path)
    mime_type = mime_type or 'application/octet-stream'
    # PDF 不缩放；光栅图可按需出预览
    if preview_w and ext != '.pdf':
        serve_path, mime_type = _ci_ensure_layout_preview(abs_path, preview_w)

    # 前端带 &_= 缓存戳时禁止长缓存，迭代回写后才能立刻看到新预览
    cache_bust = (request.GET.get('_') or '').strip()
    cache_control = 'private, no-cache' if cache_bust else 'private, max-age=86400'

    etag = _ci_file_etag(serve_path)
    if_none_match = (request.META.get('HTTP_IF_NONE_MATCH') or '').strip()
    if if_none_match and if_none_match == etag and not cache_bust:
        resp = HttpResponseNotModified()
        resp['ETag'] = etag
        resp['Cache-Control'] = cache_control
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Cross-Origin-Resource-Policy'] = 'cross-origin'
        return resp

    try:
        f = open(serve_path, 'rb')
        resp = FileResponse(f, content_type=mime_type)
        resp['Content-Disposition'] = f'inline; filename="{os.path.basename(serve_path)}"'
        resp['ETag'] = etag
        resp['Cache-Control'] = cache_control
        resp['X-Frame-Options'] = 'SAMEORIGIN'
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Cross-Origin-Resource-Policy'] = 'cross-origin'
        return resp
    except OSError as exc:
        raise Http404(f'文件读取失败: {exc}') from exc


@csrf_exempt
@ci_access
def ci_pdf_page_count(request):
    """查询 PDF 文件的页数。
    POST { username, filename }
    → { error_num, page_count }
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        import fitz
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        filename = (data.get('filename') or '').strip()
        if not username or not filename:
            return JsonResponse({'error_num': 1, 'msg': '缺少username或filename'})

        from app_chat.continuous_image_service import _resolve_user_file_path
        abs_path = _resolve_user_file_path(username, filename)
        if not abs_path or not os.path.isfile(abs_path):
            return JsonResponse({'error_num': 1, 'msg': '文件不存在'})

        ext = os.path.splitext(abs_path)[1].lower()
        if ext not in ('.pdf',):
            return JsonResponse({'error_num': 0, 'page_count': 1})

        doc = fitz.open(abs_path)
        page_count = len(doc)
        doc.close()
        return JsonResponse({'error_num': 0, 'page_count': page_count})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'查询页数失败: {e}'})


def _find_unit_section(m_layer: Dict[str, Any], unit_id: str) -> Dict[str, Any]:
    for section in (m_layer.get('sections') or []):
        if str((section or {}).get('unit_id') or '').strip() == str(unit_id or '').strip():
            return section
    return {}


def _normalize_d_lite_refine_model(raw: Any) -> str:
    model = str(raw or 'gemini').strip().lower()
    if model in ('qwen', 'qwen3.6-plus', 'qwen3_6_plus', 'qwen3.6plus'):
        return 'qwen'
    return 'gemini'


def _resolve_d_lite_refine_model_name(provider: str) -> str:
    return _ci_sm('ci_refine_qwen', _REFINE_QWEN_MODEL) if provider == 'qwen' else _ci_sm('ci_refine_gemini', _REFINE_GEMINI_MODEL)


_D_LITE_REFINE_QWEN_PROMPT_TAIL = (
    "\n\n"
    "【注意事项】\n"
    "1. 图片识别与内容理解更新必须以「各D版面轻量识字汇总」为准；原草图仅作辅助与信息补充，"
    "不得主要依据读图结果覆盖或改写已给出的 D 区识字文本。\n"
    "2. 在现有正文框架内做微调、精修、补漏：仅做错误信息矫正与缺失信息补充；"
    "不得打乱原有结构与段落顺序，不得另起炉灶，"
    "不得自行添加 Markdown 格式（如 *、**、#、列表符号等），请输出 plain 文本。\n"
    "3. 叙述时尽量不用 D1、D2、M3 等版面序号代称；"
    "而要说具体是哪一块区域、其实际含义或内容是什么。"
)


def _append_d_lite_refine_qwen_prompt_tail(user_prompt: str, refine_model: str) -> str:
    if _normalize_d_lite_refine_model(refine_model) != 'qwen':
        return user_prompt
    return f'{user_prompt}{_D_LITE_REFINE_QWEN_PROMPT_TAIL}'


def _call_gemini_refine_with_images(system_text: str, user_text: str, original_abs: str, repro_abs: str) -> str:
    if not _REFINE_GEMINI_KEY:
        raise ValueError('missing_gemini_api_key')
    content = [
        {'type': 'text', 'text': user_text},
        {'type': 'text', 'text': '【原图】'},
        {'type': 'image_url', 'image_url': {'url': _to_data_url_by_file(original_abs)}},
        {'type': 'text', 'text': '【最新R层复现图】'},
        {'type': 'image_url', 'image_url': {'url': _to_data_url_by_file(repro_abs)}},
    ]
    client = OpenAI(api_key=_REFINE_GEMINI_KEY, base_url=_REFINE_GEMINI_BASE.rstrip('/') + '/', timeout=240)
    rsp = client.chat.completions.create(
        model=_ci_sm('ci_refine_gemini', _REFINE_GEMINI_MODEL),
        messages=[
            {'role': 'system', 'content': system_text},
            {'role': 'user', 'content': content},
        ],
        temperature=0.1,
        max_tokens=8000,
    )
    return str(rsp.choices[0].message.content or '').strip()


def _call_gemini_refine_original_sketch_only(system_text: str, user_text: str, original_abs: str) -> str:
    """仅用原草图（无 R 层复现图）做多模态迭代，供「轻量 D 识字→校正 T/三层」路径使用。"""
    if not _REFINE_GEMINI_KEY:
        raise ValueError('missing_gemini_api_key')
    if not original_abs or not os.path.isfile(original_abs):
        raise ValueError('missing_original_sketch')
    content = [
        {'type': 'text', 'text': user_text},
        {'type': 'text', 'text': '【原草图】'},
        {'type': 'image_url', 'image_url': {'url': _to_data_url_by_file_doc_import(original_abs)}},
    ]
    client = OpenAI(api_key=_REFINE_GEMINI_KEY, base_url=_REFINE_GEMINI_BASE.rstrip('/') + '/', timeout=240)
    rsp = client.chat.completions.create(
        model=_ci_sm('ci_refine_gemini', _REFINE_GEMINI_MODEL),
        messages=[
            {'role': 'system', 'content': system_text},
            {'role': 'user', 'content': content},
        ],
        temperature=0.1,
        max_tokens=8000,
    )
    return str(rsp.choices[0].message.content or '').strip()


def _call_qwen_refine_original_sketch_only(system_text: str, user_text: str, original_abs: str) -> str:
    if not _REFINE_QWEN_KEY:
        raise ValueError('missing_qwen_api_key')
    if not original_abs or not os.path.isfile(original_abs):
        raise ValueError('missing_original_sketch')
    content = [
        {'type': 'text', 'text': user_text},
        {'type': 'text', 'text': '【原草图】'},
        {'type': 'image_url', 'image_url': {'url': _to_data_url_by_file_doc_import(original_abs)}},
    ]
    client = OpenAI(api_key=_REFINE_QWEN_KEY, base_url=_REFINE_QWEN_BASE.rstrip('/') + '/', timeout=240)
    rsp = client.chat.completions.create(
        model=_ci_sm('ci_refine_qwen', _REFINE_QWEN_MODEL),
        messages=[
            {'role': 'system', 'content': system_text},
            {'role': 'user', 'content': content},
        ],
        temperature=0.1,
        max_tokens=8000,
        extra_body={'enable_thinking': False},
    )
    return str(rsp.choices[0].message.content or '').strip()


def _call_refine_original_sketch_only(model_provider: str, system_text: str, user_text: str, original_abs: str) -> str:
    provider = _normalize_d_lite_refine_model(model_provider)
    if provider == 'qwen':
        return _call_qwen_refine_original_sketch_only(system_text, user_text, original_abs)
    return _call_gemini_refine_original_sketch_only(system_text, user_text, original_abs)


def _ci_lite_bundle_abs_path(paths: Dict[str, Any], unit_id: str) -> str:
    return os.path.join(paths['root'], 'ci_audit', f'd_region_lite_recognition_{unit_id}.json')


def _load_ci_lite_recognition_bundle(paths: Dict[str, Any], unit_id: str) -> Dict[str, Any]:
    bundle_path = _ci_lite_bundle_abs_path(paths, unit_id)
    if not os.path.isfile(bundle_path):
        raise ValueError('lite_bundle_missing')
    with open(bundle_path, 'r', encoding='utf-8') as handle:
        bundle = json.load(handle)
    return bundle if isinstance(bundle, dict) else {}


def _aggregate_ci_lite_regions_plain_text(bundle: Dict[str, Any]) -> str:
    regions = bundle.get('regions') if isinstance(bundle.get('regions'), list) else []
    blocks: List[str] = []
    for item in regions:
        if not isinstance(item, dict):
            continue
        rid = str(item.get('region_id') or '').strip()
        title = str(item.get('title') or '').strip()
        pay = item.get('payload') if isinstance(item.get('payload'), dict) else {}
        chunk = ''
        preds = pay.get('model_predictions') if isinstance(pay.get('model_predictions'), dict) else {}
        qw = preds.get('qwen') if isinstance(preds.get('qwen'), dict) else {}
        chunk = str(qw.get('text') or '').strip()
        if not chunk:
            chunk = str(pay.get('suggested_target_text') or pay.get('recognized_text') or '').strip()
        head = f'【D区 {rid}' + (f' {title}' if title else '') + '】'
        blocks.append(f'{head}\n{chunk}'.strip())
    return '\n\n'.join(blocks).strip()


_D_LITE_IU_PREVIEW_CACHE_PREFIX = 'd_lite_image_understanding_preview_'


def _d_lite_iu_preview_cache_abs_path(paths: Dict[str, Any], unit_id: str, date_str: Optional[str] = None) -> str:
    day = (date_str or _datetime.datetime.now().strftime('%Y%m%d')).strip()
    audit_dir = os.path.join(paths['root'], 'ci_audit')
    os.makedirs(audit_dir, exist_ok=True)
    return os.path.join(audit_dir, f'{_D_LITE_IU_PREVIEW_CACHE_PREFIX}{unit_id}_{day}.json')


def _d_lite_iu_recent_cache_date_strings():
    """当日与前一日的 YYYYMMDD，用于预览缓存命中（批量可昨夜生成、今日查看）。"""
    now = _datetime.datetime.now()
    today = now.strftime('%Y%m%d')
    yesterday = (now - _datetime.timedelta(days=1)).strftime('%Y%m%d')
    return today, yesterday


def _load_d_lite_iu_preview_cache(paths: Dict[str, Any], unit_id: str, *, today_only: bool = True) -> Optional[Dict[str, Any]]:
    today, yesterday = _d_lite_iu_recent_cache_date_strings()
    try_days = [today, yesterday] if today_only else [today]
    allowed_days = {today, yesterday} if today_only else None
    for day in try_days:
        cache_path = _d_lite_iu_preview_cache_abs_path(paths, unit_id, day)
        if not os.path.isfile(cache_path):
            continue
        try:
            with open(cache_path, 'r', encoding='utf-8') as handle:
                payload = json.load(handle)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        saved_day = str(payload.get('date') or '').strip()
        if today_only and saved_day and saved_day not in allowed_days:
            continue
        out = dict(payload)
        out['_cache_abs_path'] = cache_path
        return out
    return None


def _save_d_lite_iu_preview_cache(
    paths: Dict[str, Any],
    unit_id: str,
    analysis_id: str,
    preview_payload: Dict[str, Any],
) -> str:
    now = _datetime.datetime.now()
    today = now.strftime('%Y%m%d')
    cache_path = _d_lite_iu_preview_cache_abs_path(paths, unit_id, today)
    body = {
        'unit_id': unit_id,
        'analysis_id': analysis_id,
        'date': today,
        'saved_at': now.isoformat(timespec='seconds'),
        'refine_source': 'd_lite_bundle',
        **preview_payload,
    }
    with open(cache_path, 'w', encoding='utf-8') as handle:
        json.dump(body, handle, ensure_ascii=False, indent=2)
    rel = os.path.relpath(cache_path, paths['root']).replace('\\', '/')
    return rel


@csrf_exempt
def ci_single_d_lite_image_understanding_preview_cache(request):
    """读取近两日（当日或前一日）轻量 D 三层理解预览缓存（批量自动化预生成结果）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        paths, _manifest, _r_layer, _r_item, _overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
        cached = _load_d_lite_iu_preview_cache(paths, unit_id, today_only=True)
        if not cached:
            return JsonResponse({'error_num': 1, 'msg': '无近两日预览缓存', 'has_cache': False})
        cache_abs = str(cached.get('_cache_abs_path') or '').strip()
        if not cache_abs:
            cache_abs = _d_lite_iu_preview_cache_abs_path(paths, unit_id)
        rel_path = os.path.relpath(cache_abs, paths['root']).replace('\\', '/')
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'has_cache': True,
            'cache_rel_path': rel_path,
            'preview_text': str(cached.get('preview_text') or '').strip(),
            'existing_text': str(cached.get('existing_text') or '').strip(),
            'source_file': str(cached.get('source_file') or '').strip(),
            'imgid': int(cached.get('imgid') or 0),
            'refine_model': str(cached.get('refine_model') or '').strip(),
            'refine_model_name': str(cached.get('refine_model_name') or '').strip(),
            'saved_at': str(cached.get('saved_at') or '').strip(),
            'date': str(cached.get('date') or '').strip(),
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'读取预览缓存失败: {e}'})


@csrf_exempt
def ci_single_refine_t_layer(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        context_docs = data.get('context_docs')
        context_card_ids = data.get('context_card_ids')
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        paths, manifest, r_layer, r_item, _overlay_item, repro_abs = _load_ci_context(username, analysis_id, unit_id)
        t_layer = _safe_json_load(paths['t_layer']) if os.path.isfile(paths['t_layer']) else {}
        m_layer = _safe_json_load(paths['m_layer']) if os.path.isfile(paths['m_layer']) else {}
        section = _find_unit_section(m_layer, unit_id)
        if not section:
            return JsonResponse({'error_num': 1, 'msg': '未找到 unit 对应 M层 section'})

        original_abs = ''
        for unit in (manifest.get('input_units') or []):
            if str((unit or {}).get('unit_id') or '').strip() != unit_id:
                continue
            asset_rel = str((unit or {}).get('asset_path') or '').strip()
            candidate = os.path.normpath(os.path.join(paths['root'], asset_rel))
            if os.path.isfile(candidate):
                original_abs = candidate
            break
        if not original_abs:
            return JsonResponse({'error_num': 1, 'msg': '未找到原图路径'})
        if not repro_abs or not os.path.isfile(repro_abs):
            return JsonResponse({'error_num': 1, 'msg': '未找到最新R层复现图'})

        existing_t_text = _build_t_layer_structured_text(t_layer)
        doc_ctx_text, card_ctx_text = _collect_ci_refine_context_text(
            username,
            manifest,
            context_docs=context_docs if isinstance(context_docs, list) else None,
            context_card_ids=context_card_ids if isinstance(context_card_ids, list) else None,
        )
        user_prompt = (
            "你要做的是：在“现有整体纪要”基础上做严格迭代，不得另起炉灶。\n"
            "必须保持结构不变（所有标题段落都保留），内容可纠错补漏、增强关联，篇幅变动尽量不超过50%。\n"
            "风格要求：抓具体细节、可识别、可理解、可提升；避免空话套话；从细节升维到宏观时必须有证据链。\n"
            "重点：对照原图与最新R层复现图，优先用更清晰文字纠正误读并增强关系理解。\n\n"
            "【现有整体纪要】\n"
            f"{existing_t_text}\n\n"
            f"【当前单图区块信息】\n标题：{section.get('title') or ''}\n主内容：{section.get('main_content') or ''}\n"
            f"【勾选文档上下文】\n{doc_ctx_text or '（无）'}\n\n"
            f"【勾选卡片上下文】\n{card_ctx_text or '（无）'}\n\n"
            "请仅输出迭代后的完整整体纪要文本，且必须使用以下固定标题：\n"
            "【📝 总体理解】\n【🎯 核心主题】\n【🔗 多图关系】\n【📄 图文关联】\n【🌐 场景意义】\n"
            "【💡 认知建议-盲区】\n【💡 认知建议-内耗区】\n【💡 认知建议-最近发展区】\n【💡 认知建议-下一步建议】\n"
            "【🧩 本体萃取-升维语义萃取】\n【🧩 本体萃取-部落知识萃取】"
        )
        refined = _call_gemini_refine_with_images(
            system_text='你是图片认知纪要迭代专家，只返回结果正文，不要解释。',
            user_text=user_prompt,
            original_abs=original_abs,
            repro_abs=repro_abs,
        )
        next_t_layer = _parse_t_layer_structured_text(refined, t_layer)

        audit_dir = os.path.join(paths['root'], 'ci_audit')
        os.makedirs(audit_dir, exist_ok=True)
        history_path = os.path.join(audit_dir, _REFINE_T_HISTORY_FILE)
        history_payload = {'entries': []}
        if os.path.isfile(history_path):
            try:
                history_payload = _safe_json_load(history_path)
            except Exception:
                history_payload = {'entries': []}
        entries = history_payload.get('entries') if isinstance(history_payload, dict) else []
        if not isinstance(entries, list):
            entries = []
        entries.append({
            'ts': _datetime.datetime.now().isoformat(),
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'before': t_layer,
            'after': next_t_layer,
        })
        _safe_json_dump(history_path, {'entries': entries})
        _safe_json_dump(paths['t_layer'], next_t_layer)
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            't_layer': next_t_layer,
            'history_file_path': history_path,
            'refined_text': refined,
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'更新整体纪要失败: {e}'})


@csrf_exempt
def ci_single_refine_t_layer_rollback(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        paths = prepare_analysis_workspace(username, analysis_id)
        history_path = os.path.join(paths['root'], 'ci_audit', _REFINE_T_HISTORY_FILE)
        if not os.path.isfile(history_path):
            return JsonResponse({'error_num': 1, 'msg': '无可回退记录'})
        payload = _safe_json_load(history_path)
        entries = payload.get('entries') if isinstance(payload, dict) else []
        if not isinstance(entries, list) or not entries:
            return JsonResponse({'error_num': 1, 'msg': '无可回退记录'})
        target_index = -1
        for idx in range(len(entries) - 1, -1, -1):
            item = entries[idx] if isinstance(entries[idx], dict) else {}
            if str(item.get('analysis_id') or '') == analysis_id and str(item.get('unit_id') or '') == unit_id:
                target_index = idx
                break
        if target_index < 0:
            return JsonResponse({'error_num': 1, 'msg': '未找到当前单图的可回退记录'})
        entry = entries.pop(target_index)
        before = entry.get('before') if isinstance(entry.get('before'), dict) else {}
        _safe_json_dump(paths['t_layer'], before)
        _safe_json_dump(history_path, {'entries': entries})
        return JsonResponse({'error_num': 0, 'msg': 'success', 't_layer': before})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'回退整体纪要失败: {e}'})


@csrf_exempt
def ci_single_refine_image_understanding_preview(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        context_docs = data.get('context_docs')
        context_card_ids = data.get('context_card_ids')
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})
        paths, manifest, _r_layer, _r_item, _overlay_item, repro_abs = _load_ci_context(username, analysis_id, unit_id)
        m_layer = _safe_json_load(paths['m_layer']) if os.path.isfile(paths['m_layer']) else {}
        t_layer = _safe_json_load(paths['t_layer']) if os.path.isfile(paths['t_layer']) else {}
        section = _find_unit_section(m_layer, unit_id)
        if not section:
            return JsonResponse({'error_num': 1, 'msg': '未找到 unit 对应图片理解内容'})
        source_file = str(section.get('source_file') or '').strip()
        seq = int(section.get('seq') or 1)
        imgid = max(0, seq - 1)
        original_abs = ''
        for unit in (manifest.get('input_units') or []):
            if str((unit or {}).get('unit_id') or '').strip() != unit_id:
                continue
            asset_rel = str((unit or {}).get('asset_path') or '').strip()
            candidate = os.path.normpath(os.path.join(paths['root'], asset_rel))
            if os.path.isfile(candidate):
                original_abs = candidate
            break
        if not original_abs or not os.path.isfile(original_abs):
            return JsonResponse({'error_num': 1, 'msg': '未找到原图路径'})
        if not repro_abs or not os.path.isfile(repro_abs):
            return JsonResponse({'error_num': 1, 'msg': '未找到最新R层复现图'})

        from llm_langchain import parse_input  # noqa: PLC0415
        existing_three_text = parse_input.get_pdf_image_sum(user_name=username, doc_name=source_file, seq=imgid) or ''
        existing_three_text = str(existing_three_text or '').strip()
        if not existing_three_text:
            return JsonResponse({'error_num': 1, 'msg': '当前图片暂无可迭代的三层理解文本'})
        t_layer_text = _build_t_layer_structured_text(t_layer)
        doc_ctx_text, card_ctx_text = _collect_ci_refine_context_text(
            username,
            manifest,
            context_docs=context_docs if isinstance(context_docs, list) else None,
            context_card_ids=context_card_ids if isinstance(context_card_ids, list) else None,
        )
        user_prompt = (
            "任务：更新完善“原图片三层理解”文本，严格基于现有内容迭代。\n"
            "硬性要求：结构不变，不可另起炉灶；纠错补漏增强；篇幅增加尽量不超过50%；避免空话。\n"
            "重点：对照原图+最新R层复现图，利用更清晰文字纠正误识别并增强关联理解。\n\n"
            f"【现有三层理解文本】\n{existing_three_text}\n\n"
            f"【该图单图整体纪要(T层)】\n{t_layer_text}\n\n"
            f"【勾选文档上下文】\n{doc_ctx_text or '（无）'}\n\n"
            f"【勾选卡片上下文】\n{card_ctx_text or '（无）'}\n\n"
            "请只输出迭代后的完整三层理解文本，不要解释。"
        )
        preview_text = _call_gemini_refine_with_images(
            system_text='你是图片三层理解迭代专家，只返回结果正文。',
            user_text=user_prompt,
            original_abs=original_abs,
            repro_abs=repro_abs,
        )
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'preview_text': preview_text,
            'existing_text': existing_three_text,
            'source_file': source_file,
            'imgid': imgid,
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'更新三层理解预览失败: {e}'})


@csrf_exempt
def ci_single_refine_image_understanding_apply(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        source_file = (data.get('source_file') or '').strip()
        imgid = int(data.get('imgid') or 0)
        refined_text = str(data.get('refined_text') or '').strip()
        if not username or not source_file or not refined_text:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / source_file / refined_text'})
        from llm_langchain import parse_input  # noqa: PLC0415
        content = parse_input.update_pdf_image_sum(
            user_name=username,
            doc_name=source_file,
            seq=imgid,
            merge_content='',
            imgtext=refined_text,
        )
        return JsonResponse({'error_num': 0, 'msg': 'success', 'content': content})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'确认更新三层理解失败: {e}'})


@csrf_exempt
def ci_single_refine_t_layer_from_d_lite_preview(request):
    """基于已保存的轻量 D 区识字汇总，预览迭代整体纪要（仅原草图，无 R 层）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        context_docs = data.get('context_docs')
        context_card_ids = data.get('context_card_ids')
        refine_model = _normalize_d_lite_refine_model(data.get('refine_model') or data.get('preview_model'))
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        paths, manifest, _r_layer, _r_item, _overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
        try:
            bundle = _load_ci_lite_recognition_bundle(paths, unit_id)
        except ValueError:
            return JsonResponse({'error_num': 1, 'msg': '未找到轻量识字结果，请先运行「全自动-直接执行&平衡效率和质量」'})
        d_text = _aggregate_ci_lite_regions_plain_text(bundle)
        if not d_text.strip():
            return JsonResponse({'error_num': 1, 'msg': '轻量识字汇总为空'})

        t_layer = _safe_json_load(paths['t_layer']) if os.path.isfile(paths['t_layer']) else {}
        m_layer = _safe_json_load(paths['m_layer']) if os.path.isfile(paths['m_layer']) else {}
        section = _find_unit_section(m_layer, unit_id)
        if not section:
            return JsonResponse({'error_num': 1, 'msg': '未找到 unit 对应 M层 section'})

        original_abs = ''
        for unit in (manifest.get('input_units') or []):
            if str((unit or {}).get('unit_id') or '').strip() != unit_id:
                continue
            asset_rel = str((unit or {}).get('asset_path') or '').strip()
            candidate = os.path.normpath(os.path.join(paths['root'], asset_rel))
            if os.path.isfile(candidate):
                original_abs = candidate
            break
        if not original_abs:
            return JsonResponse({'error_num': 1, 'msg': '未找到原图路径'})

        existing_t_text = _build_t_layer_structured_text(t_layer)
        doc_ctx_text, card_ctx_text = _collect_ci_refine_context_text(
            username,
            manifest,
            context_docs=context_docs if isinstance(context_docs, list) else None,
            context_card_ids=context_card_ids if isinstance(context_card_ids, list) else None,
        )
        user_prompt = (
            "你要做的是：在「现有整体纪要」基础上做迭代校正；主要依据为下方「各D版面轻量识字汇总」（来自 Qwen 轻量 Pipeline，含自检），并结合原草图核对。\n"
            "不得另起炉灶；必须保持下列固定标题结构不变（所有标题段落都保留）。\n"
            "可纠错补漏、理顺图文关系、补齐与版面识字一致的理解；风格具体可验证，避免空话。\n"
            "若有区分「表单预置印刷信息」与「用户手写记录」，请在纪要中分别交代两类内容；识字汇总里带（印刷）（手写）等标注时请一并吸收进叙述，避免混为一谈或遗漏用户真实书写细节。\n"
            "轻量识字可能偶有个别位置不通顺，可能是识别有误差：写入纪要时可对明显不通顺处做**理解性矫正**（理顺语义、与草图及上下文一致），但须贴近原意，不可凭空编造事实。\n"
            "篇幅：可在现有基础上适度扩充（稍多于常规50-80%上限亦可，细节/手写文字量多时允许再放宽些），要精炼但必须完整、不遗漏每个要点；专有名词与具体措辞尽量原样保留。\n\n"
            f"【各D版面轻量识字汇总】\n{d_text}\n\n"
            "【现有整体纪要】\n"
            f"{existing_t_text}\n\n"
            f"【当前单图区块信息】\n标题：{section.get('title') or ''}\n主内容：{section.get('main_content') or ''}\n"
            f"【勾选文档上下文】\n{doc_ctx_text or '（无）'}\n\n"
            f"【勾选卡片上下文】\n{card_ctx_text or '（无）'}\n\n"
            "请仅输出迭代后的完整整体纪要文本，且必须使用以下固定标题：\n"
            "【📝 总体理解】\n【🎯 核心主题】\n【🔗 多图关系】\n【📄 图文关联】\n【🌐 场景意义】\n"
            "【💡 认知建议-盲区】\n【💡 认知建议-内耗区】\n【💡 认知建议-最近发展区】\n【💡 认知建议-下一步建议】\n"
            "【🧩 本体萃取-升维语义萃取】\n【🧩 本体萃取-部落知识萃取】"
        )
        user_prompt = _append_d_lite_refine_qwen_prompt_tail(user_prompt, refine_model)
        refined = _call_refine_original_sketch_only(
            refine_model,
            system_text='你是图片认知纪要迭代专家，只返回结果正文，不要解释。',
            user_text=user_prompt,
            original_abs=original_abs,
        )
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'preview_text': refined,
            'existing_text': existing_t_text,
            'refine_source': 'd_lite_bundle',
            'refine_model': refine_model,
            'refine_model_name': _resolve_d_lite_refine_model_name(refine_model),
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'预览(T层·轻量D)失败: {e}'})


@csrf_exempt
def ci_single_refine_t_layer_from_d_lite_apply(request):
    """确认写入：将预览定稿的整体纪要保存到 t_layer（历史可追溯）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        refined_text = str(data.get('refined_text') or '').strip()
        if not username or not analysis_id or not unit_id or not refined_text:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id / refined_text'})

        paths, _manifest, _r_layer, _r_item, _overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
        t_layer = _safe_json_load(paths['t_layer']) if os.path.isfile(paths['t_layer']) else {}
        next_t_layer = _parse_t_layer_structured_text(refined_text, t_layer)

        audit_dir = os.path.join(paths['root'], 'ci_audit')
        os.makedirs(audit_dir, exist_ok=True)
        history_path = os.path.join(audit_dir, _REFINE_T_HISTORY_FILE)
        history_payload = {'entries': []}
        if os.path.isfile(history_path):
            try:
                history_payload = _safe_json_load(history_path)
            except Exception:
                history_payload = {'entries': []}
        entries = history_payload.get('entries') if isinstance(history_payload, dict) else []
        if not isinstance(entries, list):
            entries = []
        entries.append({
            'ts': _datetime.datetime.now().isoformat(),
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'before': t_layer,
            'after': next_t_layer,
            'source': 'from_d_lite_recognition',
        })
        _safe_json_dump(history_path, {'entries': entries})
        _safe_json_dump(paths['t_layer'], next_t_layer)
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            't_layer': next_t_layer,
            'history_file_path': history_path,
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'写入整体纪要(T层·轻量D)失败: {e}'})


@csrf_exempt
def ci_single_refine_image_understanding_preview_from_d_lite(request):
    """基于轻量 D 区识字汇总预览迭代三层理解（仅原草图；确认写入仍走 refine_image_understanding_apply）。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        analysis_id = (data.get('analysis_id') or '').strip()
        unit_id = (data.get('unit_id') or '').strip()
        context_docs = data.get('context_docs')
        context_card_ids = data.get('context_card_ids')
        refine_model = _normalize_d_lite_refine_model(data.get('refine_model') or data.get('preview_model'))
        save_preview_cache = bool(data.get('save_preview_cache'))
        if not username or not analysis_id or not unit_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username / analysis_id / unit_id'})

        paths, manifest, _r_layer, _r_item, _overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
        try:
            bundle = _load_ci_lite_recognition_bundle(paths, unit_id)
        except ValueError:
            return JsonResponse({'error_num': 1, 'msg': '未找到轻量识字结果，请先运行「全自动-直接执行&平衡效率和质量」'})
        d_text = _aggregate_ci_lite_regions_plain_text(bundle)
        if not d_text.strip():
            return JsonResponse({'error_num': 1, 'msg': '轻量识字汇总为空'})

        m_layer = _safe_json_load(paths['m_layer']) if os.path.isfile(paths['m_layer']) else {}
        t_layer = _safe_json_load(paths['t_layer']) if os.path.isfile(paths['t_layer']) else {}
        section = _find_unit_section(m_layer, unit_id)
        if not section:
            return JsonResponse({'error_num': 1, 'msg': '未找到 unit 对应图片理解内容'})
        source_file = str(section.get('source_file') or '').strip()
        seq = int(section.get('seq') or 1)
        imgid = max(0, seq - 1)
        original_abs = ''
        for unit in (manifest.get('input_units') or []):
            if str((unit or {}).get('unit_id') or '').strip() != unit_id:
                continue
            asset_rel = str((unit or {}).get('asset_path') or '').strip()
            candidate = os.path.normpath(os.path.join(paths['root'], asset_rel))
            if os.path.isfile(candidate):
                original_abs = candidate
            break
        if not original_abs or not os.path.isfile(original_abs):
            return JsonResponse({'error_num': 1, 'msg': '未找到原图路径'})

        from llm_langchain import parse_input  # noqa: PLC0415
        existing_three_text = parse_input.get_pdf_image_sum(user_name=username, doc_name=source_file, seq=imgid) or ''
        existing_three_text = str(existing_three_text or '').strip()
        if not existing_three_text:
            return JsonResponse({'error_num': 1, 'msg': '当前图片暂无可迭代的三层理解文本'})

        t_layer_text = _build_t_layer_structured_text(t_layer)
        doc_ctx_text, card_ctx_text = _collect_ci_refine_context_text(
            username,
            manifest,
            context_docs=context_docs if isinstance(context_docs, list) else None,
            context_card_ids=context_card_ids if isinstance(context_card_ids, list) else None,
        )
        user_prompt = (
            "任务：更新完善「原图片三层理解」文本，严格基于现有内容迭代。\n"
            "依据：下方「各D版面轻量识字汇总」（Qwen 轻量 Pipeline），并结合原草图核对；不要依赖 R 层复现图。\n"
            "硬性要求：结构不变，不可另起炉灶；纠错补漏增强；篇幅可适当增加（略多于50%亦可，细节与引用较多时允许再略放宽），但要精炼、完整、避免空话。\n"
            "若有区分「表单预置印刷信息」与「用户手写记录」，请在三层理解中分别体现；识字汇总中的（印刷）（手写）等标注请转化为清晰叙述，并尽量完整保留用户书写的具体字句与细节，勿笼统概括后丢失原文信息。\n"
            "识字可能存在个别位置不通顺，可能是有轻微误差：迭代三层理解时可在忠于图像与语境的前提下对明显不通顺处做**合理理解与用语矫正**，使叙述可读、一致；勿捏造图中不存在的信息。\n\n"
            f"【各D版面轻量识字汇总】\n{d_text}\n\n"
            f"【现有三层理解文本】\n{existing_three_text}\n\n"
            f"【该图单图整体纪要(T层)】\n{t_layer_text}\n\n"
            f"【勾选文档上下文】\n{doc_ctx_text or '（无）'}\n\n"
            f"【勾选卡片上下文】\n{card_ctx_text or '（无）'}\n\n"
            "请只输出迭代后的完整三层理解文本，不要解释。"
        )
        user_prompt = _append_d_lite_refine_qwen_prompt_tail(user_prompt, refine_model)
        preview_text = _call_refine_original_sketch_only(
            refine_model,
            system_text='你是图片三层理解迭代专家，只返回结果正文。',
            user_text=user_prompt,
            original_abs=original_abs,
        )
        out = {
            'error_num': 0,
            'msg': 'success',
            'preview_text': preview_text,
            'existing_text': existing_three_text,
            'source_file': source_file,
            'imgid': imgid,
            'refine_source': 'd_lite_bundle',
            'refine_model': refine_model,
            'refine_model_name': _resolve_d_lite_refine_model_name(refine_model),
        }
        if save_preview_cache:
            rel = _save_d_lite_iu_preview_cache(
                paths,
                unit_id,
                analysis_id,
                {
                    'preview_text': preview_text,
                    'existing_text': existing_three_text,
                    'source_file': source_file,
                    'imgid': imgid,
                    'refine_model': refine_model,
                    'refine_model_name': _resolve_d_lite_refine_model_name(refine_model),
                },
            )
            out['cache_rel_path'] = rel
            out['saved_at'] = _datetime.datetime.now().isoformat(timespec='seconds')
        return JsonResponse(out)
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'预览三层理解(轻量D)失败: {e}'})


@csrf_exempt
def ci_grade_understanding(request):
    """图片批改理解：先 Gemini 抽取，再 Claude 分析。"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        text_info = str(data.get('text') or '').strip()
        image_data_urls = _coerce_images_to_data_urls(
            data.get('images_base64') if data.get('images_base64') is not None else data.get('image_base64')
        )
        if not image_data_urls:
            return JsonResponse({'error_num': 1, 'msg': '缺少 images_base64 或 image_base64'})
        if not text_info:
            return JsonResponse({'error_num': 1, 'msg': '缺少 text'})

        gemini_cfg = {
            'model': 'gemini-3.1-pro-preview',
            'base_url': _public_config.endpoint('NKCN_REVIEW_GATEWAY_V1_URL', 'http://localhost:9999/v1'),
            'api_key': _REFINE_GEMINI_KEY,
        }
        gemini_prompt = (
            "你是小学/初中作业图片识别助手。\n"
            "任务：只做识别抽取，不做教学点评。\n"
            "输入包含单图或连续多图（2-3页）以及外部文本（含PageID、Qxx、班均正确率等）。\n"
            "请按页输出：\n"
            "1) 每页题目清单（印刷字提取，题号+题干）。\n"
            "2) 每题学生作答内容（手写识别，尽量完整准确，不漏项）。\n"
            "3) 若无法辨认，标注“疑难片段”并给最可能候选。\n"
            "重要：题旁或答案上的红笔批改痕迹（对勾/半对/叉/红线）是无效信息，全部忽略，不得当作答案内容。\n"
            "请输出严格 JSON，格式：\n"
            "{\n"
            '  "pages":[{"page_id":"...", "questions":[{"q_no":"Qxx","printed_question":"...","student_answer":"...","uncertain_spans":["..."]}]}],\n'
            '  "global_notes":"..." \n'
            "}\n\n"
            f"【外部文本】\n{text_info}"
        )
        gemini_text, gemini_attempt_used = _chat_completion_with_retry(
            gemini_cfg,
            messages=[
                {'role': 'system', 'content': '你是严谨的版面识别与手写抄录助手。'},
                {'role': 'user', 'content': _build_multimodal_content(gemini_prompt, image_data_urls)},
            ],
            temperature=0.1,
            max_tokens=5000,
            retries=2,
        )

        gemini_second_prompt = (
            "你是中小学作业批改理解助手。\n"
            "输入：图片、外部文本（含PageID/Qxx/班均正确率）、以及 Gemini 识别结果。\n"
            "注意：图中红笔批改痕迹（对勾/半对/叉/红线）均是无效信息，不能用于判断学生答案内容。\n"
            "请输出三段，且严格控制长度：\n"
            "① 150字以内：复述这页/几页题目所属大致年级、人教版方向，题干、学生答案大意、题间关系与考察点。\n"
            "② 250字以内：先逐题点评正确性（若不对或部分有误，要指出正确方向）/完整性/答题习惯，再整体分析思考习惯、书写习惯（是否工整）、表达方式、知识与方法优缺点。\n"
            "③ 100-150字：给出贴合年级认知阶段的“三区”建议（盲区/内耗区需有依据，就近发展区优先改进点必须明确）。\n"
            "用语严谨、自然、温和，不要超纲，但一定要具体，切忌“继续强化一步步写清楚计算过程”这类0帮助的废话，一定要举具体例子说明。\n"
            "输出格式：\n"
            "【一】...\n【二】...\n【三】...\n\n"
            f"【外部文本】\n{text_info}\n\n"
            f"【Gemini识别结果】\n{gemini_text}"
        )
        claude_text, claude_attempt_used = _chat_completion_with_retry(
            gemini_cfg,
            messages=[
                {'role': 'system', 'content': '你是严谨、温和、面向基础教育认知发展阶段的学业分析助手。'},
                {'role': 'user', 'content': _build_multimodal_content(gemini_second_prompt, image_data_urls)},
            ],
            temperature=0.2,
            max_tokens=5000,
            retries=2,
        )
        claude_parts = _extract_claude_sections(claude_text)
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'gemini_model': gemini_cfg['model'],
            'claude_model': gemini_cfg['model'],
            'gemini_attempt_used': gemini_attempt_used,
            'claude_attempt_used': claude_attempt_used,
            'gemini_extraction_text': gemini_text,
            'claude_analysis_text': claude_text,
            'claude_overview_brief': claude_parts.get('part1') or '',
            'claude_per_question_and_overall': claude_parts.get('part2') or '',
            'claude_zone_feedback': claude_parts.get('part3') or '',
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'图片批改理解失败: {e}'})


# ════════════════════════════════════════════════════════════════
# 旧架构兼容 API（保留旧路由，行为不变）
# ════════════════════════════════════════════════════════════════



@csrf_exempt
def start_continuous_image_analysis(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})

    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        selected_files = data.get('selected_files', [])
        mode = (data.get('mode') or 'group').strip()
        force_rebuild = bool(data.get('force_rebuild', False))
        model_id = data.get('model_id')

        if not username:
            return JsonResponse({'error_num': 1, 'msg': '缺少username'})
        if not isinstance(selected_files, list) or not selected_files:
            return JsonResponse({'error_num': 1, 'msg': 'selected_files不能为空'})

        group_id = build_group_id(username, mode, selected_files)
        task_id = f'ci_task_{uuid.uuid4().hex[:20]}'

        # 已有完成结果时，直接返回可查看状态（支持服务重启后快速回看）
        group_root = os.path.join(
            '.', 'received_dir', 'user_raw_file', username, 'continuous_image_dmt', group_id
        )
        manifest_path = os.path.join(group_root, 'manifest.json')
        d_layer_path = os.path.join(group_root, 'd_layer.json')
        m_layer_path = os.path.join(group_root, 'm_layer.json')
        t_layer_path = os.path.join(group_root, 't_layer.json')

        if not force_rebuild and os.path.exists(manifest_path) and os.path.exists(d_layer_path) \
                and os.path.exists(m_layer_path) and os.path.exists(t_layer_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                if manifest.get('status') == 'completed':
                    global_var.tasks[task_id] = {
                        'current_item': 1,
                        'total_items': 1,
                        'current_section': '完成',
                        'completed': True,
                        'error': '',
                    }
                    return JsonResponse({
                        'error_num': 0,
                        'task_id': task_id,
                        'group_id': group_id,
                        'msg': 'existing_result',
                    })
            except Exception:
                pass

        global_var.tasks[task_id] = {
            'current_item': 0,
            'total_items': 0,
            'current_section': '准备中',
            'completed': False,
            'error': '',
        }

        thread = threading.Thread(
            target=run_continuous_image_analysis,
            kwargs={
                'task_id': task_id,
                'username': username,
                'mode': mode,
                'selected_files': selected_files,
                'group_id': group_id,
                'force_rebuild': force_rebuild,
                'model_id': model_id,
            },
            daemon=True
        )
        thread.start()

        return JsonResponse({
            'error_num': 0,
            'task_id': task_id,
            'group_id': group_id,
            'msg': 'success',
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'启动失败: {e}'})


@csrf_exempt
def continuous_image_analysis_progress(request, task_id):
    task = global_var.tasks.get(task_id)
    if not task:
        return JsonResponse({
            'error_num': 1,
            'msg': '任务不存在',
            'current_item': 0,
            'total_items': 0,
            'current_section': '失败',
            'completed': True,
            'error': '任务不存在',
        })

    return JsonResponse({
        'error_num': 0,
        'current_item': task.get('current_item', 0),
        'total_items': task.get('total_items', 0),
        'current_section': task.get('current_section', '准备中'),
        'completed': task.get('completed', False),
        'error': task.get('error', ''),
    })


@csrf_exempt
def get_continuous_image_analysis_result(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})

    try:
        data = json.loads(request.body)
        group_id = (data.get('group_id') or '').strip()
        username = (data.get('username') or '').strip() or None

        if not group_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少group_id'})

        result = get_continuous_image_result(group_id, username=username)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': f'读取结果失败: {e}'})


@csrf_exempt
def serve_layout_visual(request):
    """居中转发版面可视化文件（图片 / PDF）给前端预览。

    Query params:
        path     服务器上的绝对路径
        username （可选）用于权限校验（暂不强制）
    """
    path = (request.GET.get('path') or '').strip()
    username = (request.GET.get('username') or '').strip()
    group_id = (request.GET.get('group_id') or '').strip()
    if not path:
        raise Http404('缺少 path 参数')

    # 安全性：仅允许访问常见图片 / PDF
    allowed_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.gif', '.pdf'}
    ext = os.path.splitext(path)[1].lower()
    if ext not in allowed_exts:
        raise Http404('不支持的文件类型')

    # 支持相对路径（如 layout_visual/xxx.png）和绝对路径
    if os.path.isabs(path):
        abs_path = os.path.normpath(path)
    else:
        rel_path = os.path.normpath(path).replace('\\', os.sep)
        abs_path = ''
        if username and group_id:
            candidate = os.path.normpath(os.path.join(
                '.', 'received_dir', 'user_raw_file', username, 'continuous_image_dmt', group_id, rel_path
            ))
            if os.path.isfile(candidate):
                abs_path = candidate
        if not abs_path and username:
            candidate = os.path.normpath(os.path.join(
                '.', 'received_dir', 'user_raw_file', username, rel_path
            ))
            if os.path.isfile(candidate):
                abs_path = candidate

    if not abs_path or not os.path.isfile(abs_path):
        raise Http404(f'文件不存在: {path}')

    mime_type, _ = mimetypes.guess_type(abs_path)
    mime_type = mime_type or 'application/octet-stream'

    try:
        f = open(abs_path, 'rb')  # noqa: WPS515
        response = FileResponse(f, content_type=mime_type)
        # 内嵌预览，不下载
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(abs_path)}"'
        response['X-Frame-Options'] = 'SAMEORIGIN'
        return response
    except OSError as exc:
        raise Http404(f'文件读取失败: {exc}') from exc
