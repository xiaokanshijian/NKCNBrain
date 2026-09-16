"""查询与启动共享的确定性准入；不调用模型、不读写业务缓存。"""
from .feedback_context import freeze_feedback_context, legacy_homework_attributes
from .feedback_material_kinds import (
    is_grading_eligible_material,
    is_question_material,
)
from .feedback_metadata import resolve_feedback_metadata


def resolve_feedback_request(filename, overrides=None, requested_action='auto', *,
                             reliable_observations=None, legacy_attrs=None):
    if requested_action not in ('auto', 'grading', 'understanding'):
        raise ValueError('requested_action必须为grading、understanding或auto')
    metadata = resolve_feedback_metadata(filename, overrides, reliable_observations)
    parsed = metadata['declared_metadata']['filename']
    is_pdf = parsed['basename'].lower().endswith('.pdf')
    material = metadata['material_type']
    # 作业/试卷/未知 + 开放式作文/笔记可进批改；日记/日志等其它类型仍排除
    eligible = is_pdf and is_grading_eligible_material(material)
    warnings = list(dict.fromkeys(issue['message'] for issue in metadata['issues']))
    if not is_pdf:
        warnings.append('批改当前仅支持单份PDF')
    elif not eligible:
        warnings.append('本阶段仅支持作业、试卷、作文与笔记；其它材料类型的反馈将在后续阶段提供')
    legacy_attrs = legacy_attrs if isinstance(legacy_attrs, dict) else {}
    legacy_recommends = legacy_attrs.get('is_homework_pdf') is True or legacy_attrs.get('is_k12_homework') is True
    # 仅作业/试卷算「题目型声明」——auto 路由逻辑与既有行为一致
    declared_question_material = is_question_material(material)
    if requested_action == 'understanding':
        route = 'continuous_image'
    elif requested_action == 'grading':
        route = 'homework_grading' if eligible else 'unsupported'
    else:
        # auto：题目型或旧版作业标记 → 批改；作文/笔记需显式点批改入口（工具条），避免改变双击理解默认行为
        route = 'homework_grading' if eligible and (declared_question_material or legacy_recommends) else 'continuous_image'
    context = freeze_feedback_context(metadata).to_dict()
    return {'feedback_eligible': eligible, 'parse_status': parsed['parse_status'],
            'feedback_context': context, 'declared_metadata': metadata['declared_metadata'],
            'warnings': warnings, 'route': route,
            'recommended_action': 'grading' if route == 'homework_grading' else 'understanding',
            'requested_action': requested_action,
            'legacy_observation': dict(legacy_attrs), **legacy_homework_attributes(context)}
