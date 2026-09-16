"""重跑默认继承原依据；显式变更依据时禁止阶段或篇目复用。"""
from .feedback_fingerprint import CONTEXT_KEYS
from .feedback_request import resolve_feedback_request
from .feedback_runtime import freeze_feedback_runtime, prepare_feedback_runtime
from .feedback_runtime_service import restore_feedback_runtime, execution_configuration, build_request_runtime
from .preprocess import normalize_preprocess_mode


def request_bool(data, key):
    value = data.get(key, False)
    if value in (True, 1, '1', 'true'):
        return True
    if value in (False, None, 0, '0', 'false', ''):
        return False
    raise ValueError(key + '必须为布尔值')


def choose_rerun_runtime(root, filename, data):
    stage = data.get('rerun_stage', 'all')
    if stage not in ('all', 'layout', 'understanding', 'grading'):
        raise ValueError('重跑阶段无效')
    resume = request_bool(data, 'resume')
    has_sessions = 'session_ids' in data
    if resume and has_sessions:
        raise ValueError('续跑时不能同时选择篇目')
    if has_sessions:
        ids = data['session_ids']
        if (not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x.strip() for x in ids)
                or len(ids) != len(set(ids))):
            raise ValueError('篇目列表不能为空或包含重复标识')
    full = request_bool(data, 'full_recompute')
    if full and (stage != 'all' or has_sessions or resume):
        raise ValueError('完整新跑不能同时使用阶段、篇目或续跑参数')
    try:
        original = restore_feedback_runtime(root)
    except (ValueError, OSError, KeyError, TypeError):
        if not full:
            raise ValueError('历史快照缺失、损坏或不受支持；请设置材料信息并明确发起完整新跑')
        parsed = resolve_feedback_request(filename, data.get('feedback_overrides'), 'grading')
        if parsed['route'] != 'homework_grading':
            raise ValueError('该材料类型暂不支持题目批改')
        runtime = build_request_runtime(parsed['feedback_context'], data,
                                        preprocess_mode=data.get('preprocess_mode', 'auto'))
        return runtime, {'stage': stage, 'resume': False, 'clone': False, 'changed': True,
                         'warnings': ['原历史快照不能恢复，本轮完整重算，不复用原页面结果']}

    context = original.context
    if 'feedback_overrides' in data:
        if not isinstance(data['feedback_overrides'], dict):
            raise ValueError('材料覆盖必须为对象')
        raw = dict(context['declared_metadata'].get('selected_raw', {}))
        raw.update(data['feedback_overrides'])
        parsed = resolve_feedback_request(filename, raw, 'grading')
        if parsed['route'] != 'homework_grading':
            raise ValueError('该材料类型暂不支持题目批改')
        candidate = parsed['feedback_context']
    else:
        candidate = context
    metadata_changed = any(candidate.get(key) != context.get(key) for key in CONTEXT_KEYS)
    if context['education_level'] == candidate['education_level'] == 'other':
        metadata_changed |= (candidate['declared_metadata']['selected_raw'].get('education_level')
                             != context['declared_metadata']['selected_raw'].get('education_level'))
    refresh = request_bool(data, 'refresh_configuration')
    deps = original.dependencies
    mode = normalize_preprocess_mode(data.get('preprocess_mode'),
                                     default=deps['preprocessing']['mode'])
    if not mode:
        raise ValueError('预处理模式无效')
    if refresh:
        deps.update(execution_configuration(mode))
    deps['preprocessing']['mode'] = mode
    if 'reference_text' in data:
        if not isinstance(data['reference_text'], str):
            raise ValueError('参考文本必须为文字')
        deps['references'] = {'reference_text': data['reference_text'], 'documents': [],
                              'status': 'provided_text' if data['reference_text'] else 'not_provided'}
    selection = data.get('curriculum_selection',
                         original.dependencies['retrieval'].get('curriculum_selection', 'auto'))
    if selection not in ('auto', None):
        raise ValueError('当前仅支持自动课标或明确不绑定')
    if metadata_changed or refresh or 'curriculum_selection' in data:
        deps['retrieval']['curriculum_selection'] = selection
        runtime = prepare_feedback_runtime(candidate, curriculum_selection=selection,
            **{key: deps[key] for key in ('model_config', 'preprocessing', 'retrieval', 'references')})
    else:
        runtime = freeze_feedback_runtime(context, **deps)
    changed = runtime.fingerprint != original.fingerprint
    if changed and (stage != 'all' or has_sessions or resume):
        raise ValueError('材料或运行依据已变化，必须完整重跑整份材料，不能混用篇目或续跑参数')
    return runtime, {'stage': stage, 'resume': resume, 'changed': changed,
                     'clone': not changed and not full and (stage != 'all' or has_sessions or resume),
                     'warnings': []}


def prepare_rerun_workspace(destination, original, workspace, analysis_id, runtime, plan, data):
    from pathlib import Path
    from .homework_versions import prepare_homework_session_rerun, invalidate_homework_stage_for_rerun
    from .red_blue_review import load_red_blue_review, load_iteration_context, build_iteration_context, save_iteration_context
    from .grader_pass1 import pass1_two_stage_enabled
    stage = plan['stage']
    if stage in ('layout', 'understanding') and not pass1_two_stage_enabled(feedback_runtime=runtime):
        raise ValueError('本轮关闭了分阶段识别，不能只迭代版面或理解')
    original = Path(original)
    destination = Path(destination)
    original_paths = {'base': str(original / 'homework_grading'),
                      'pass2_report': str(original / 'homework_grading/pass2_report')}
    use_feedback = request_bool(data, 'use_red_blue_feedback')
    review = load_red_blue_review(original_paths)
    if use_feedback and not plan['resume'] and review.get('status') != 'ready':
        raise ValueError('当前红蓝卡标不可用，请关闭参考开关或先重新评分')
    meta = {}
    if 'session_ids' in data or plan['resume']:
        meta = prepare_homework_session_rerun(workspace, analysis_id, stage,
            session_ids=data.get('session_ids'), resume=plan['resume'],
            workspace_root=destination)
    elif plan['clone']:
        invalidate_homework_stage_for_rerun(workspace, analysis_id, stage, workspace_root=destination)
    context = (load_iteration_context(original_paths) if plan['resume'] else
               build_iteration_context(review, use_feedback, original.name, stage,
                   session_ids=meta.get('effective_session_ids', []), feedback_runtime=runtime))
    save_iteration_context({'base': str(destination / 'homework_grading')}, context)
    return {**meta, 'scope_page_nums': set(meta['scope_page_nums']) if 'scope_page_nums' in meta else None,
            'force_preprocess_scope': bool(meta) and stage == 'all',
            'red_blue_feedback_used': bool(context.get('enabled'))}
