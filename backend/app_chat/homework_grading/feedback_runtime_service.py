"""正常启动冻结实际配置；从P01既有四快照恢复，不复制连接凭据。"""
import hashlib
import json
import os
from pathlib import Path

from .feedback_runtime import prepare_feedback_runtime, freeze_feedback_runtime
from .feedback_snapshot_reader import read_feedback_snapshot, SNAPSHOT_FILES

ENVIRONMENT_KEYS = (
    'HOMEWORK_PASS1_TWO_STAGE', 'HOMEWORK_PASS1_MAX_ATTEMPTS',
    'HOMEWORK_PASS1_PAGE_MAX_ATTEMPTS', 'HOMEWORK_PASS1_PARALLELISM',
    'HOMEWORK_PASS1_5_ENABLED', 'HOMEWORK_PASS1_5_MATH_THINKING',
    'HOMEWORK_PASS1_SELF_REVIEW', 'HOMEWORK_PASS1_REVIEW_SCOPE',
    'HOMEWORK_PASS1_REVIEW_STOP_ON_QUOTA', 'HOMEWORK_PASS1_REVIEW_REUSE_EXISTING',
    'HOMEWORK_PASS1_REVIEW_PARALLELISM', 'HOMEWORK_PASS1_FOCUSED_CHINESE_VISUAL_REVIEW',
    'HOMEWORK_PASS1_GLYPH_ARBITRATION_MODE', 'HOMEWORK_PASS1_FOCUSED_REVIEW_MAX',
    'HOMEWORK_PASS1_FOCUSED_REVIEW_MARGIN_PX', 'HOMEWORK_PASS1_FOCUSED_REVIEW_EXTRA_PAD_RATIO',
    'HOMEWORK_PASS1_FOCUSED_REVIEW_SCALE', 'HOMEWORK_PASS1_REVIEW_INLINE_MAX_MB',
    'HOMEWORK_PASS1_REVIEW_INLINE_TARGET_MB', 'HOMEWORK_PASS1_SLOT_PRESENCE',
    'HOMEWORK_PASS1_U1_SHADOW', 'HOMEWORK_FIXED_ENGLISH_CHOICE_SLOTS',
    'HOMEWORK_FIXED_SAMPLE_CROSSOUT_REPAIR', 'HOMEWORK_RED_INK_RESIDUAL_MASK',
    'HOMEWORK_GRADING_BLACK_INK_IMAGE', 'HOMEWORK_PASS1_REVIEW_BLACK_INK_IMAGE',
    'NKCN_HOMEWORK_RED_BLUE_EARLY_STAGE_FEEDBACK_ENABLED',
    'NKCN_HOMEWORK_GEMINI_TIMEOUT', 'NKCN_HOMEWORK_RED_BLUE_TIMEOUT',
)


def execution_configuration(preprocess_mode):
    from .llm_clients import (homework_qwen_model, homework_deepseek_model,
                              homework_review_gemini_model, HOMEWORK_RED_BLUE_MODEL,
                              HOMEWORK_RED_BLUE_REASONING_EFFORT)
    from .preprocess import normalize_preprocess_mode
    mode = normalize_preprocess_mode(preprocess_mode)
    if not mode:
        raise ValueError('预处理模式无效')
    # 参数常量由实际消费者定义；记录代码哈希使策略变化不会复用旧页面。
    sources = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
               for path in sorted(Path(__file__).parent.glob('*.py'))
               if not path.name.endswith('_test.py') and not path.name.startswith('test_')}
    models = {'roles': {
        'qwen': {'model': homework_qwen_model(), 'extra_body': {'enable_thinking': False}},
        'deepseek': {'model': homework_deepseek_model()},
        'review': {'model': homework_review_gemini_model()},
        'quality': {'model': HOMEWORK_RED_BLUE_MODEL, 'reasoning_effort': HOMEWORK_RED_BLUE_REASONING_EFFORT},
    }, 'consumer_parameters_version': 'p03-v1', 'consumer_code_hashes': sources,
        'qwen_call_policy': {'version': 1, 'allowed_extra_bodies': [
            {'enable_thinking': False}, {'enable_thinking': True, 'thinking_budget': 4096}],
            'allowed_temperatures': [None, 0.0, 0.1]}}
    preprocessing = {'version': 'p03-v1', 'mode': mode,
                     'environment': {key: os.environ[key] for key in ENVIRONMENT_KEYS if key in os.environ}}
    from .fixed_sample_crossout import load_fixed_sample_crossout_manifest
    from .special_cases import load_document_special_case_manifest
    preprocessing['fixed_crossout'] = load_fixed_sample_crossout_manifest()
    preprocessing['fixed_document_identities'] = load_document_special_case_manifest()
    retrieval = {'version': 'p03-existing-curriculum-v1', 'mode': 'frozen_scope',
                 'external_retrieval_status': 'not_executed'}
    from .curriculum import _load_label_mapping
    retrieval['display_names'] = {subject: _load_label_mapping(subject)
                                 for subject in ('math', 'chinese', 'english')}
    return {'model_config': models, 'preprocessing': preprocessing, 'retrieval': retrieval}


def build_request_runtime(metadata, data, *, preprocess_mode='auto'):
    reference_text = data.get('reference_text', '')
    if not isinstance(reference_text, str):
        raise ValueError('reference_text必须为文字')
    external = bool(data.get('context_docs') or data.get('context_card_ids'))
    references = {'status': 'provided_text_documents_not_read' if external else
                  'provided_text' if reference_text else 'not_provided',
                  'reference_text': reference_text, 'documents': []}
    configuration = execution_configuration(preprocess_mode)
    configuration['retrieval']['curriculum_selection'] = data.get('curriculum_selection', 'auto')
    return prepare_feedback_runtime(metadata, references=references,
        curriculum_selection=data.get('curriculum_selection', 'auto'),
        **configuration)


def restore_feedback_runtime(root):
    root = Path(root)
    state = read_feedback_snapshot(root)
    if state['snapshot_status'] != 'complete':
        raise ValueError('运行快照无法完整恢复，请保留原结果并发起完整新跑')
    # 再次校验本次读取的字节，避免读取检查后文件被替换。
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    contents = {}
    for kind, filename in SNAPSHOT_FILES.items():
        raw = (root / filename).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['feedback_snapshot']['files'][filename]:
            raise ValueError('恢复期间运行快照发生变化')
        value = json.loads(raw)
        contents[kind] = value if kind == 'context' else value['data']
    context = contents.pop('context')
    runtime = freeze_feedback_runtime(context, **contents, **manifest['feedback_execution'])
    if runtime.fingerprint != state['config_fingerprint']:
        raise ValueError('恢复的运行依据与原指纹不同')
    return runtime
