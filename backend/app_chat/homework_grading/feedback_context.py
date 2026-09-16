"""统一上下文的值对象；不读取运行配置或匹配课程。"""
import copy
import json
from dataclasses import dataclass

CONTEXT_SCHEMA = 'feedback-context-v2'
LEVEL_NAMES = {'primary': '小学', 'junior': '初中', 'senior': '高中', 'vocational': '职业教育',
               'university': '大学', 'postgraduate': '研究生', 'adult': '成人教育',
               'other': '其他', 'unknown': '未知学段'}


def canonical_json(value):
    """不改变正文字符串、数组顺序；拒绝非JSON数值及非文字对象键。"""
    def check(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError('JSON对象键必须是文字')
            for child in item.values():
                check(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check(child)
    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate_context(data):
    if not isinstance(data, dict) or data.get('schema_version') != CONTEXT_SCHEMA:
        raise ValueError('不支持的材料上下文格式')
    required_strings = ('parser_version', 'alias_version', 'subject_code', 'subject_key',
                        'education_level', 'material_type', 'grade_status')
    if any(not isinstance(data.get(key), str) or not data[key] for key in required_strings):
        raise ValueError('材料上下文缺少必要属性')
    if data['education_level'] not in LEVEL_NAMES:
        raise ValueError('教育阶段值无效')
    if data['grade_status'] not in ('resolved', 'unknown', 'unconfirmed', 'conflict'):
        raise ValueError('年级确认状态无效')
    for key in ('subject_name', 'material_name', 'grade_label', 'term', 'textbook', 'school_system'):
        if data.get(key) is not None and not isinstance(data[key], str):
            raise ValueError('材料名称与说明必须为文字或空值')
    for key in ('grade_in_level', 'grade_global'):
        value = data.get(key)
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError('年级必须为正整数或空值')
    if data['education_level'] not in ('primary', 'junior', 'senior') and data.get('grade_global') is not None:
        raise ValueError('非K12上下文不能强行设置全局年级')
    if data['grade_status'] != 'resolved' and (data.get('grade_global') is not None or data.get('grade_in_level') is not None):
        raise ValueError('未确认年级不能作为已解析范围')
    if data['grade_status'] == 'resolved':
        local = data.get('grade_in_level')
        if type(local) is not int:
            raise ValueError('已解析年级缺少阶段内年级')
        bounds = {'primary': (0, 6), 'junior': (6, 3), 'senior': (9, 3)}
        if data['education_level'] in bounds:
            offset, size = bounds[data['education_level']]
            if not 1 <= local <= size or data.get('grade_global') != offset + local:
                raise ValueError('上下文的学段、阶段内年级和全局年级不一致')
            if data.get('school_system') not in (None, '', '6-3-3'):
                raise ValueError('未确认学制不能使用六三三年级映射')
    for key in ('metadata_source', 'declared_metadata'):
        if not isinstance(data.get(key), dict):
            raise ValueError('材料来源信息必须为对象')
    if 'selected_raw' in data['declared_metadata'] and not isinstance(data['declared_metadata']['selected_raw'], dict):
        raise ValueError('材料原始声明必须为对象')
    if not isinstance(data.get('issues'), list) or not isinstance(data.get('locked_unknown_fields'), list):
        raise ValueError('材料问题及锁定字段必须为数组')
    bindings = data.get('skill_bindings')
    if not isinstance(bindings, list):
        raise ValueError('规则绑定必须为数组')
    for binding in bindings:
        if not isinstance(binding, dict) or not all(isinstance(binding.get(k), str) and binding[k] for k in ('id', 'version')):
            raise ValueError('规则绑定必须明确ID及版本')
    binding = data.get('curriculum_binding')
    if binding is not None and (not isinstance(binding, dict) or not all(
            isinstance(binding.get(key), str) and binding[key] for key in ('resource_id', 'version', 'stage_key'))):
        raise ValueError('课程绑定必须明确资源、版本和阶段')
    canonical_json(data)


@dataclass(frozen=True)
class FrozenFeedbackContext:
    """内部仅持有不可变JSON文本；每次读出均产生独立嵌套对象。"""
    _json: str

    def __post_init__(self):
        validate_context(json.loads(self._json))

    def to_dict(self):
        return json.loads(self._json)

    def to_json(self):
        return self._json

    @classmethod
    def from_json(cls, text):
        data = json.loads(text)
        validate_context(data)
        return cls(canonical_json(data))


def freeze_feedback_context(metadata, *, skill_bindings=None, curriculum_binding=None):
    if not isinstance(metadata, dict):
        raise ValueError('材料上下文必须为对象')
    data = copy.deepcopy(metadata)
    data.update(schema_version=CONTEXT_SCHEMA,
                education_level_name=LEVEL_NAMES.get(data.get('education_level'), '未知学段'),
                skill_bindings=copy.deepcopy([] if skill_bindings is None else skill_bindings),
                curriculum_binding=copy.deepcopy(curriculum_binding))
    validate_context(data)
    return FrozenFeedbackContext(canonical_json(data))


def legacy_homework_attributes(context):
    data = context.to_dict() if isinstance(context, FrozenFeedbackContext) else context
    validate_context(data)
    is_k12 = data['education_level'] in ('primary', 'junior', 'senior') and data['material_type'] in ('homework', 'exam')
    return {'is_k12_homework': is_k12, 'is_homework_pdf': is_k12,
            'homework_subject': data['subject_code'], 'homework_stage': data['education_level'],
            'homework_grade': data.get('grade_global')}
