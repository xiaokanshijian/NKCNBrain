"""本子内每份PDF的已保存材料设置；保存不启动任务。"""
import hashlib
import json
import os
from pathlib import Path
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .ci_access import ci_access, assert_workspace_path
from .feedback_material_identity import source_digest, record_digest
from .homework_grading.feedback_request import resolve_feedback_request
from .homework_grading.utils import safe_json_dump, safe_json_load, windows_io_path


MATERIAL_KEYS = ('feedback_overrides', 'curriculum_selection', 'reference_text')


def legacy_settings_path(workspace, filename):
    root = Path(settings.BASE_DIR) / 'received_dir' / 'user_raw_file' / workspace
    assert_workspace_path(workspace, root / filename)
    return root / '.feedback_material' / (hashlib.sha256(filename.encode('utf-8')).hexdigest()[:24] + '.json')


def settings_path(workspace, filename):
    old = legacy_settings_path(workspace, filename)
    digest = source_digest(workspace, filename)
    return old.parent / ('sha256-' + digest + '.json') if digest else old


def validate_material_settings(material):
    if not isinstance(material, dict):
        raise ValueError('材料设置必须为对象')
    material = {key: material[key] for key in MATERIAL_KEYS if key in material}
    overrides = material.get('feedback_overrides', {})
    if not isinstance(overrides, dict):
        raise ValueError('材料属性设置必须为对象')
    if material.get('curriculum_selection', 'auto') not in ('auto', None):
        raise ValueError('暂不支持指定课标资源')
    if not isinstance(material.get('reference_text', ''), str):
        raise ValueError('附加信息格式无效')
    return material


def load_saved_material_settings(workspace, filename):
    """读取一份 PDF 的当前设置；不存在与不可信旧档均视为未保存，不阻断重新填写保存。"""
    path = settings_path(workspace, filename)
    digest = source_digest(workspace, filename)
    try:
        if path.name.startswith('sha256-') and path.is_file():
            value = safe_json_load(path)
            if value.get('source_document_sha256') != digest:
                # 同名换内容或指纹对不上：旧档作废，当作未保存
                print(
                    f'[material_settings] 忽略指纹不一致的旧设置 file={filename}',
                    flush=True,
                )
                return {}, False
            return validate_material_settings(value['material']), True
        from .ci.index_manager import CIIndexManager
        records = CIIndexManager.load(workspace) if digest else []
        aliases = {filename}
        trusted = set()
        for record in records:
            if record.get('analysis_type') == 'homework_grading' and record_digest(workspace, record) == digest:
                trusted.update(record.get('files', []))
        aliases.update(trusted)
        candidates = []
        unverified = False
        for alias in aliases:
            old = legacy_settings_path(workspace, alias)
            if old.is_file():
                value = safe_json_load(old)
                if digest and alias in trusted:
                    candidates.append(validate_material_settings(value))
                else:
                    unverified = True
        if unverified or (candidates and any(v != candidates[0] for v in candidates)):
            # 旧档无法核对/冲突：不硬拦对话框，当作未保存，让用户重新保存
            print(
                f'[material_settings] 忽略不可信旧设置 file={filename} '
                f'unverified={unverified} candidates={len(candidates)}',
                flush=True,
            )
            return {}, False
        return (candidates[0], True) if candidates else ({}, False)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ValueError(f'已保存材料设置无法读取：{exc}') from exc


def merge_saved_material_settings(workspace, filename, request_data):
    """保存值作默认值，请求显式值优先；属性覆盖按字段合并。"""
    if not isinstance(request_data, dict):
        raise ValueError('请求参数必须为对象')
    saved, exists = load_saved_material_settings(workspace, filename)
    if not exists:
        return dict(request_data), False
    merged = dict(request_data)
    for key in ('curriculum_selection', 'reference_text'):
        if key not in merged and key in saved:
            merged[key] = saved[key]
    saved_overrides = saved.get('feedback_overrides') or {}
    if 'feedback_overrides' in merged:
        explicit_overrides = merged['feedback_overrides']
        if not isinstance(explicit_overrides, dict):
            raise ValueError('材料属性设置必须为对象')
        merged['feedback_overrides'] = {**saved_overrides, **explicit_overrides}
    elif saved_overrides:
        merged['feedback_overrides'] = dict(saved_overrides)
    return merged, True


@csrf_exempt
@ci_access
def material_settings(request):
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持POST'})
    try:
        data = json.loads(request.body)
        files = data.get('files', [])
        if len(files) != 1 or not files[0].lower().endswith('.pdf'):
            raise ValueError('材料设置仅支持单份PDF')
        path = settings_path(request.ci_workspace, files[0])
        if data.get('save') is True:
            material, saved = validate_material_settings(data.get('material')), False
        else:
            material, saved = load_saved_material_settings(request.ci_workspace, files[0])
        parsed = resolve_feedback_request(files[0], material.get('feedback_overrides'), 'grading')
        if data.get('save') is True:
            temp = str(path) + '.' + uuid.uuid4().hex[:8] + '.tmp'
            try:
                digest = source_digest(request.ci_workspace, files[0])
                if digest and path.name != 'sha256-' + digest + '.json':
                    raise ValueError('保存期间材料内容发生变化，请重新打开材料设置')
                if not digest:
                    raise ValueError('材料文件不存在，不能保存内容设置')
                safe_json_dump(temp, {'schema_version': 'feedback-material-v2',
                    'source_document_sha256': digest, 'filename_aliases': [files[0]], 'material': material})
                os.replace(windows_io_path(temp), windows_io_path(path))
            finally:
                if os.path.isfile(windows_io_path(temp)):
                    os.remove(windows_io_path(temp))
            saved = True
        return JsonResponse({'error_num': 0, **parsed, 'material': material, 'material_saved': saved})
    except (ValueError, OSError, TypeError) as exc:
        return JsonResponse({'error_num': 1, 'msg': f'材料设置失败：{exc}'})
