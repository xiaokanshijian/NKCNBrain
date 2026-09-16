"""冻结消费者所需的全部依据，兼容P01指纹和快照输入。"""
import json
from dataclasses import dataclass

from .feedback_context import FrozenFeedbackContext, canonical_json
from .feedback_fingerprint import compute_config_fingerprint


@dataclass(frozen=True)
class FrozenFeedbackRuntime:
    _json: str

    def __post_init__(self):
        data = self.to_dict()
        context = FrozenFeedbackContext.from_json(canonical_json(data['context']))
        digest = compute_config_fingerprint(context, **data['dependencies'])
        from .feedback_skill_matching import compose_skills
        selected, _ = compose_skills(data['context'], data['dependencies']['skills'])
        if [(s['id'], s['version']) for s in selected] != [(s['id'], s['version']) for s in data['dependencies']['skills']]:
            raise ValueError('冻结专项范围或执行顺序不匹配')
        if data['dependencies']['curriculum'] is not None:
            from .feedback_curriculum import curriculum_entries
            curriculum_entries(self)
        if data.get('config_fingerprint') != digest:
            raise ValueError('冻结运行依据指纹不一致')

    def to_dict(self):
        return json.loads(self._json)

    @property
    def context(self):
        return self.to_dict()['context']

    @property
    def dependencies(self):
        return self.to_dict()['dependencies']

    @property
    def fingerprint(self):
        return self.to_dict()['config_fingerprint']

    def audit(self):
        return {'config_fingerprint': self.fingerprint, 'skill_bindings': self.context['skill_bindings'],
                'curriculum_binding': self.context['curriculum_binding'],
                'skill_selection': self.to_dict().get('selection', {})}

    def has_specialized(self, subject=None):
        subject = subject or self.context['subject_code']
        return any(s['id'] == f'{subject}-primary4-question' for s in self.dependencies['skills'])


def freeze_feedback_runtime(context, *, selection=None, **dependencies):
    data = context.to_dict() if isinstance(context, FrozenFeedbackContext) else context
    fingerprint = compute_config_fingerprint(data, **dependencies)
    return FrozenFeedbackRuntime(canonical_json({'context': data, 'dependencies': dependencies,
                                                'config_fingerprint': fingerprint, 'selection': selection or {}}))


def prepare_feedback_runtime(metadata, *, model_config, preprocessing, retrieval, references,
                             curriculum_selection='auto'):
    """独立调用入口；调用者明确提供配置/参考资料，不读取真实文件或模型。"""
    from .feedback_curriculum import freeze_builtin_curriculum
    from .feedback_skill_matching import bind_skills
    if curriculum_selection not in ('auto', None):
        raise ValueError('本阶段仅支持自动匹配课标或明确不绑定，暂不支持选择资源版本')
    curriculum = None if curriculum_selection is None else freeze_builtin_curriculum(metadata)
    binding = None if curriculum is None else {k: curriculum[k] for k in ('resource_id', 'version', 'stage_key')}
    context, skills, selection = bind_skills(metadata, curriculum_binding=binding)
    return freeze_feedback_runtime(context, selection=selection, skills=skills, curriculum=curriculum,
                                   references=references, model_config=model_config,
                                   preprocessing=preprocessing, retrieval=retrieval)


def runtime_attributes(runtime):
    c=runtime.context
    binding=c.get('curriculum_binding')
    stage=None
    if binding and binding['stage_key'] in ('S1','S2','S3'):
        stage=int(binding['stage_key'][1:])
    return c['subject_code'],c.get('grade_global'),stage


def frozen_environment(runtime, key, default=None):
    """消费者开关从冻结配置读取；缺省使用代码默认值，不回读进程环境。"""
    import os
    if runtime is None:
        return os.environ.get(key, default)
    value = runtime.dependencies['preprocessing'].get('environment', {}).get(key, default)
    if value is not None and not isinstance(value, str):
        raise ValueError('冻结消费者环境选项须为字符串：' + key)
    return value


def stamp_feedback(value, runtime, phase=None):
    if runtime is not None and isinstance(value,dict):
        value['feedback_context']=runtime.context
        value['feedback_execution']=runtime.audit()
        if phase: value['feedback_execution']['consumer']=phase
    return value
