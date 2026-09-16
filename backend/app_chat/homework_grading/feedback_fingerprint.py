"""运行指纹纯函数；调用者必须提供本轮冻结依据，禁止读取最新配置。"""
import copy
import hashlib

from app_chat.homework_grading.feedback_context import FrozenFeedbackContext, canonical_json, validate_context
from app_chat.homework_grading.feedback_metadata import custom_key

FINGERPRINT_SCHEMA = 'feedback-fingerprint-v1'
CONTEXT_KEYS = ('schema_version', 'parser_version', 'alias_version', 'subject_code', 'subject_key',
                'education_level', 'grade_in_level', 'grade_global', 'grade_status', 'material_type',
                'material_key', 'term', 'textbook', 'school_system')
_AUDIT_KEYS = {'created_at', 'updated_at', 'timestamp', 'progress', 'display_name'}
_CREDENTIAL_KEYS = {'api_key', 'apikey', 'password', 'authorization', 'access_token', 'refresh_token', 'secret', 'token'}


def _validate_execution_config(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.casefold() in _CREDENTIAL_KEYS:
                raise ValueError('执行快照仅接受模型标识及参数，不接受凭据')
            _validate_execution_config(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_execution_config(item)


def content_sha256(content):
    return hashlib.sha256(canonical_json(content).encode('utf-8')).hexdigest()


def _required_text(data, key):
    if not isinstance(data.get(key), str) or not data[key]:
        raise ValueError(f'运行依据缺少有效字段：{key}')
    return data[key]


def _resource(resource, identity_keys):
    if not isinstance(resource, dict) or 'content' not in resource or resource['content'] is None:
        raise ValueError('运行依据必须保存实际内容，不能只传资源ID或路径')
    result = {key: _required_text(resource, key) for key in identity_keys}
    digest = content_sha256(resource['content'])
    if 'content_hash' in resource and resource['content_hash'] != digest:
        raise ValueError('运行依据内容哈希不一致')
    result['content_hash'] = digest
    for key in ('scope', 'coverage_status'):
        if key in resource:
            result[key] = copy.deepcopy(resource[key])
    return result


def fingerprint_payload(context, *, skills, curriculum, references, model_config, preprocessing, retrieval):
    data = context.to_dict() if isinstance(context, FrozenFeedbackContext) else copy.deepcopy(context)
    validate_context(data)
    if not isinstance(skills, list):
        raise ValueError('规则快照必须为数组')
    skill_data = [_resource(skill, ('id', 'version')) for skill in skills]
    expected = [(item['id'], item['version']) for item in data['skill_bindings']]
    actual = [(item['id'], item['version']) for item in skill_data]
    if actual != expected or len(set(actual)) != len(actual):
        raise ValueError('规则快照与上下文绑定或执行顺序不一致')
    for binding, item in zip(data['skill_bindings'], skill_data):
        if 'content_hash' in binding and binding['content_hash'] != item['content_hash']:
            raise ValueError('规则绑定内容哈希不一致')
    binding = data['curriculum_binding']
    curriculum_data = None
    if curriculum is not None:
        curriculum_data = _resource(curriculum, ('resource_id', 'version', 'stage_key'))
    if (binding is None) != (curriculum is None):
        raise ValueError('课程快照与上下文绑定不一致')
    if binding is not None:
        if any(binding[key] != curriculum_data[key] for key in ('resource_id', 'version', 'stage_key')):
            raise ValueError('课程快照与绑定版本或阶段不一致')
        if 'content_hash' in binding and binding['content_hash'] != curriculum_data['content_hash']:
            raise ValueError('课程绑定内容哈希不一致')
        for key in ('scope', 'coverage_status'):
            if key in binding:
                curriculum_data['binding_' + key] = copy.deepcopy(binding[key])
    if not isinstance(references, dict):
        raise ValueError('参考资料快照必须为对象')
    _required_text(references, 'status')
    if not isinstance(references.get('reference_text'), str) or not isinstance(references.get('documents'), list):
        raise ValueError('参考资料须明确正文、读取状态和文档数组')
    documents = []
    for document in references['documents']:
        if not isinstance(document, dict) or not isinstance(document.get('content'), str):
            raise ValueError('参考文档须保留实际读取文本，读取失败时使用空文本及明确状态')
        documents.append({key: _required_text(document, key) for key in ('id', 'role', 'status')})
        documents[-1].update(content_hash=content_sha256(document['content']), version=document.get('version'))
    config = {}
    for name, value in [('model_config', model_config), ('preprocessing', preprocessing), ('retrieval', retrieval)]:
        if not isinstance(value, dict) or not value:
            raise ValueError('必须明确传入模型、预处理及检索配置')
        _validate_execution_config(value)
        config[name] = {key: copy.deepcopy(item) for key, item in value.items() if key not in _AUDIT_KEYS}
        if not config[name]:
            raise ValueError('运行配置不能只有展示或审计字段')
    semantic = {key: data.get(key) for key in CONTEXT_KEYS}
    if data['material_type'] == 'other':
        name = data.get('material_name')
        if not isinstance(name, str) or not name:
            raise ValueError('自定义品类必须保留名称')
        semantic['material_key'] = custom_key(name)
    if data['education_level'] == 'other':
        raw = data.get('declared_metadata', {}).get('selected_raw', {}).get('education_level')
        semantic['education_level_key'] = custom_key(raw) if raw else 'other'
    result = {'schema_version': FINGERPRINT_SCHEMA, 'context': semantic, 'skills': skill_data,
              'curriculum': curriculum_data,
              'references': {'status': references['status'], 'reference_text': references['reference_text'], 'documents': documents},
              **config}
    canonical_json(result)
    return result


def compute_config_fingerprint(context, **dependencies):
    return content_sha256(fingerprint_payload(context, **dependencies))
