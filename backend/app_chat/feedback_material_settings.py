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
from .homework_grading.feedback_request import resolve_feedback_request
from .homework_grading.utils import safe_json_dump, safe_json_load, windows_io_path


def settings_path(workspace, filename):
    root = Path(settings.BASE_DIR) / 'received_dir' / 'user_raw_file' / workspace
    assert_workspace_path(workspace, root / filename)
    return root / '.feedback_material' / (hashlib.sha256(filename.encode('utf-8')).hexdigest()[:24] + '.json')


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
        try:
            material = safe_json_load(path)
            saved = True
        except FileNotFoundError:
            material, saved = {}, False
        if data.get('save') is True:
            material = data.get('material')
            if not isinstance(material, dict):
                raise ValueError('材料设置必须为对象')
            material = {key: material[key] for key in ('feedback_overrides', 'curriculum_selection', 'reference_text') if key in material}
            if material.get('curriculum_selection', 'auto') not in ('auto', None):
                raise ValueError('暂不支持指定课标资源')
            if not isinstance(material.get('reference_text', ''), str):
                raise ValueError('参考文字格式无效')
        parsed = resolve_feedback_request(files[0], material.get('feedback_overrides'), 'grading')
        if data.get('save') is True:
            temp = str(path) + '.' + uuid.uuid4().hex[:8] + '.tmp'
            try:
                safe_json_dump(temp, material)
                os.replace(windows_io_path(temp), windows_io_path(path))
            finally:
                if os.path.isfile(windows_io_path(temp)):
                    os.remove(windows_io_path(temp))
            saved = True
        return JsonResponse({'error_num': 0, **parsed, 'material': material, 'material_saved': saved})
    except (ValueError, OSError, TypeError) as exc:
        return JsonResponse({'error_num': 1, 'msg': f'材料设置失败：{exc}'})
