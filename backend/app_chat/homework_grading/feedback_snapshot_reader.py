"""只读运行快照。历史缺失与损坏明确区分，不回查最新资源。"""
import hashlib
import json
import re
from pathlib import Path

from app_chat.homework_grading.feedback_context import validate_context
from app_chat.homework_grading.feedback_fingerprint import compute_config_fingerprint

SNAPSHOT_SCHEMA = 'feedback-snapshot-v1'
SNAPSHOT_FILES = {'context': 'feedback_context.json', 'skills': 'skill_snapshot.json',
                  'curriculum': 'curriculum_snapshot.json', 'references': 'reference_snapshot.json'}
_HASH = re.compile(r'[0-9a-f]{64}')


def is_sha256(value):
    return isinstance(value, str) and bool(_HASH.fullmatch(value))


def _state(status, message=None, context=None, fingerprint=None):
    return {'feedback_context': context, 'config_fingerprint': fingerprint,
            'snapshot_status': status, 'snapshot_warnings': [message] if message else []}


def read_feedback_snapshot(root, manifest=None):
    root = Path(root)
    try:
        if manifest is None:
            path = root / 'manifest.json'
            manifest = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        if not isinstance(manifest, dict):
            return _state('invalid', '运行记录格式损坏，无法核实材料配置')
        marker = manifest.get('feedback_snapshot')
        if marker is None and not any((root / name).exists() for name in SNAPSHOT_FILES.values()):
            return _state('legacy_missing', '历史版本未保存材料配置快照，仅展示当时结果')
        if not isinstance(marker, dict):
            return _state('invalid', '材料配置快照缺少完整性记录')
        if marker.get('schema_version') != SNAPSHOT_SCHEMA:
            return _state('unsupported', '材料配置快照版本暂不支持，请保留原版本')
        if marker.get('status') != 'complete':
            return _state('invalid', '材料配置快照尚未完整保存')
        hashes = marker.get('files')
        if not isinstance(hashes, dict) or set(hashes) != set(SNAPSHOT_FILES.values()):
            return _state('invalid', '材料配置快照校验清单不完整')
        if not is_sha256(manifest.get('source_document_sha256')) or not is_sha256(manifest.get('config_fingerprint')):
            return _state('invalid', '材料配置快照缺少有效源文件标识或配置指纹')
        data = {}
        for kind, name in SNAPSHOT_FILES.items():
            path = root / name
            if not path.is_file():
                return _state('missing', '材料配置快照文件缺失，不能作为已完成配置复用')
            if path.is_symlink() or path.resolve().parent != root.resolve():
                return _state('invalid', '材料配置快照路径无效')
            payload = path.read_bytes()
            if not is_sha256(hashes.get(name)) or hashlib.sha256(payload).hexdigest() != hashes[name]:
                return _state('invalid', '材料配置快照校验不一致，请保留原结果核对')
            value = json.loads(payload)
            if kind == 'context':
                validate_context(value)
                data[kind] = value
            else:
                if not isinstance(value, dict) or value.get('schema_version') != SNAPSHOT_SCHEMA:
                    return _state('unsupported', '材料依据快照格式暂不支持')
                if value.get('kind') != kind or 'data' not in value:
                    return _state('invalid', '材料依据快照内容格式无效')
                content = value['data']
                if ((kind == 'skills' and not isinstance(content, list)) or
                        (kind == 'curriculum' and content is not None and not isinstance(content, dict)) or
                        (kind == 'references' and not isinstance(content, dict))):
                    return _state('invalid', '材料依据快照内容类型无效')
                data[kind] = content
        execution = manifest.get('feedback_execution')
        if not isinstance(execution, dict) or set(execution) != {'model_config', 'preprocessing', 'retrieval'}:
            return _state('invalid', '材料配置快照缺少实际执行配置')
        actual_fingerprint = compute_config_fingerprint(data['context'], skills=data['skills'],
            curriculum=data['curriculum'], references=data['references'], **execution)
        if actual_fingerprint != manifest['config_fingerprint']:
            return _state('invalid', '材料依据与配置指纹不一致，不能复用本配置')
        return _state('complete', context=data['context'], fingerprint=actual_fingerprint)
    except (ValueError, TypeError, OSError, UnicodeError):
        return _state('invalid', '材料配置快照无法读取或格式损坏，原批改结果仍保留')


def feedback_version_summary(root, manifest=None):
    result = read_feedback_snapshot(root, manifest)
    context = result['feedback_context']
    if context is not None:
        # 仅返回列表展示所需上下文；不携带声明原件、参考正文或完整规则。
        keys = ('schema_version', 'parser_version', 'alias_version', 'subject_code', 'subject_name',
                'subject_key', 'education_level', 'education_level_name', 'grade_in_level', 'grade_global',
                'grade_label', 'grade_status', 'material_type', 'material_name', 'term', 'textbook')
        summary = {key: context.get(key) for key in keys}
        summary['skill_bindings'] = [{key: item[key] for key in ('id', 'version')} for item in context['skill_bindings']]
        binding = context.get('curriculum_binding')
        summary['curriculum_binding'] = None if binding is None else {key: binding.get(key) for key in (
            'resource_id', 'version', 'stage_key', 'selection_source', 'coverage_status')}
        result['feedback_context'] = summary
    return result
