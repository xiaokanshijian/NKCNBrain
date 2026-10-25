"""显式阶段依赖；未知模块保守影响全链路，完整哈希仍独立保留审计。"""
import copy
import hashlib
import json
from pathlib import Path

SCHEMA = 'grading-stage-dependencies-v1'
ORDER = ('layout', 'understanding', 'grading', 'render', 'quality')
MODULES = {
    'layout': set('''__init__ artifact_transaction curriculum feedback_context feedback_curriculum
        feedback_fingerprint feedback_material_kinds feedback_metadata feedback_model feedback_prompts
        feedback_runtime feedback_runtime_service feedback_skill_matching feedback_skills feedback_capabilities managed_feedback_rules
        execution_control execution_checkpoints stage_dependencies llm llm_clients model_output
        preprocess grader_pass1 prompts subject_prompt_rules sessions service staged_pipeline
        fixed_sample_crossout special_cases slot_presence u1_shadow same_page_detect_backfill
        parent_stem_backfill cross_page_detect_backfill note_page_links tianzige_roi utils
        question_type material_markings note_evidence fixed_english_choice_slots
        feedback_request feedback_snapshot feedback_snapshot_reader feedback_start_service
        feedback_start_transaction feedback_rerun_plan feedback_workspaces homework_versions'''.split()),
    'understanding': set('''fixed_english_page15_guard fixed_math_sample_guards pass1_confidence_fields_backfill
        memory page_feedback semantic_config feedback_verification'''.split()),
    'grading': set('''grader_pass1_review grader_pass1_5 cross_page evidence_contract
        verifiers rubric_verifiers rubric_rules answer_statement_verifier
        profile ontology_builder grader_pass2 hallucination_filter semantic_checks
        confidence_zones partial_feedback validation_issues hanzi_strokes'''.split()),
    'render': {'render'},
    'quality': {'red_blue_review', 'delivery_basis', 'feedback_quality_retry'},
    'display': set('''feedback_result_basis feedback_observation feedback_task_recovery grading_rag
        pass3 pass3_service count_homework_questions analyze_confidence_distribution
        export_focused_review_crops complex_glyph_description_experiment
        qwen_complex_glyph_description_experiment blind_pinyin_review_experiment
        rerun_gemini_review_pipeline open_material_grading'''.split()),
}
# 完成/产物验证决定可交付性，但不改变上游识别结果。
MODULES['grading'].update({'completion', 'feedback_artifacts'})
MODULES['understanding'].add('notebook_skills')
SHARED_FILES = ('../ci/file_io.py', '../ci_access.py')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def stage_name(phase):
    if phase in ORDER:
        return phase
    return {'startup': 'layout', 'preprocess': 'layout', 'detect': 'layout', 'sessions': 'layout',
            'grade': 'understanding', 'grade_page_from_detect': 'understanding',
            'cross_page': 'grading', 'review': 'grading', 'verification': 'grading',
            'memory': 'grading', 'ontology': 'grading', 'report': 'grading',
            'hallucination': 'grading', 'output_validation': 'render'}.get(phase, 'layout')


def code_basis(hashes, stage):
    limit = ORDER.index(stage_name(stage))
    selected = {}
    for name, value in hashes.items():
        stem = name[:-3] if name.endswith('.py') else name
        owner = next((phase for phase, names in MODULES.items() if stem in names), 'layout')
        if owner != 'display' and ORDER.index(owner) <= limit:
            selected[name] = value
    return digest(selected)


def configuration(runtime, stage):
    deps = copy.deepcopy(runtime.dependencies)
    phase = stage_name(stage)
    limit = ORDER.index(phase)
    model = deps['model_config']
    model.pop('consumer_code_hashes', None)
    roles = {'qwen'}
    if limit >= 2:
        roles.update(('deepseek', 'review'))
    if limit >= 4:
        roles.add('quality')
    model['roles'] = {key: value for key, value in model.get('roles', {}).items() if key in roles}
    env = deps['preprocessing'].get('environment', {})
    for key in list(env):
        if (('RED_BLUE' in key and limit < 4) or ('REVIEW' in key or 'GEMINI' in key) and limit < 2
                or 'PASS2' in key and limit < 2):
            del env[key]
    # 消费者阶段只包含实际可注入的规则正文；上下文中的全规则哈希仅作审计。
    phases = {'detect', 'sessions'}
    if limit >= 1:
        phases.add('grade')
    if limit >= 2:
        phases.update(('cross_page', 'review', 'memory', 'profile', 'ontology', 'pass2', 'filter'))
    if limit >= 4:
        phases.add('quality')
    for skill in deps.get('skills', []):
        skill.pop('content_hash', None)
        content = skill['content']
        content.pop('instructions', None)
        rules = [r for r in content['manifest']['rules'] if set(r['stages']) & phases]
        content['manifest']['rules'] = rules
        content['resources']['texts'] = {r['text_key']: content['resources']['texts'][r['text_key']] for r in rules}
    context = copy.deepcopy(runtime.context)
    context.pop('skill_bindings', None)
    context.pop('declared_metadata', None)
    return digest({'context': context, 'dependencies': deps})


def enabled(runtime):
    return runtime is not None and runtime.dependencies['model_config'].get('dependency_schema') == SCHEMA


def basis(runtime, hashes, stage):
    return {'schema': SCHEMA, 'stage': stage_name(stage),
            'configuration': configuration(runtime, stage), 'code': code_basis(hashes, stage)}


def assert_registry_complete():
    files = {p.stem for p in Path(__file__).parent.glob('*.py')
             if not p.name.endswith('_test.py') and not p.name.startswith('test_')}
    registered = set().union(*MODULES.values())
    missing = files - registered
    if missing:
        raise ValueError('执行依赖尚未显式登记：' + ', '.join(sorted(missing)))


def artifact_compatible(value, runtime):
    saved = value.get('feedback_execution', {})
    if saved.get('config_fingerprint') == runtime.fingerprint:
        return True
    if not enabled(runtime):
        return False
    previous = saved.get('stage_basis') or {}
    if previous.get('schema') != SCHEMA or previous.get('stage') not in ORDER:
        return False
    from .execution_control import current_execution, code_identity
    actual = current_execution().identity if current_execution() else code_identity()
    return previous == basis(runtime, actual['actual_code_hashes'], previous['stage'])


def reusable_upstream(original, candidate):
    """规则、材料及参考资料变化仍完整新跑；仅执行配置变化可按阶段复用。"""
    if not enabled(original) or not enabled(candidate) or original.context != candidate.context:
        return False
    before, after = original.dependencies, candidate.dependencies
    if any(before[key] != after[key] for key in ('skills', 'curriculum', 'references', 'retrieval')):
        return False
    return configuration(original, 'layout') == configuration(candidate, 'layout')
