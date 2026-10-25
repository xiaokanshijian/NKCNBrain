"""只缓存已验证模型JSON；完整请求、冻结依据和实际代码决定可复用性。"""
import copy
import hashlib
import json
from pathlib import Path

from .execution_control import current_execution
from .utils import safe_json_dump, safe_json_load


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def checkpoint_key(messages, stage):
    execution = current_execution()
    if execution is None or execution.base is None or execution.runtime is None:
        return None
    from .stage_dependencies import enabled, basis
    if enabled(execution.runtime):
        return digest({'schema': 2, 'messages': messages, 'stage': stage,
                       'basis': basis(execution.runtime, execution.identity['actual_code_hashes'], execution.stage)})
    return digest({'schema': 1, 'messages': messages, 'stage': stage,
                   'configuration': execution.runtime.fingerprint,
                   'code': execution.identity['actual_code_fingerprint']})


def load_checkpoint(key, validate):
    execution = current_execution()
    if key is None or not execution.reuse:
        return None
    path = execution.base / 'checkpoints' / (key + '.json')
    if not path.is_file():
        return None
    try:
        record = safe_json_load(path)
        if not isinstance(record, dict) or not isinstance(record.get('result'), dict):
            return None
        payload = record['result']
        if record['key'] != key or record['sha256'] != digest(payload):
            return None
        if payload.get('content_validation', {}).get('status') == 'needs_review':
            return None
        return validate(copy.deepcopy(payload))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_checkpoint(key, value):
    execution = current_execution()
    if key is not None and value.get('content_validation', {}).get('status') != 'needs_review':
        safe_json_dump(execution.base / 'checkpoints' / (key + '.json'),
                       {'key': key, 'sha256': digest(value), 'result': value})


def _receipt_runtime(paths):
    execution = current_execution()
    if execution is not None and execution.runtime is not None:
        return execution.runtime
    from .feedback_runtime_service import restore_feedback_runtime
    return restore_feedback_runtime(Path(paths['base']).parent)


def stage_receipt(paths, stage, fingerprint, code=None, schema=2):
    from .execution_control import code_identity
    base = Path(paths['base'])
    files = list((base / 'clean').glob('*.png')) + list((base / 'pass1_json').glob('*.detect.json'))
    if stage in ('understanding', 'grading', 'render', 'quality'):
        files += list((base / 'pass1_json').glob('*.grade.json'))
    if stage in ('grading', 'render', 'quality'):
        files += list((base / 'pass1_json').glob('*.json')) + list((base / 'pass2_report').glob('*_report.json'))
        files += [base / 'student_ontology.json']
    if (schema == 2 and stage == 'grading') or (schema == 3 and stage in ('render', 'quality')):
        files += list((base / 'annotated').glob('*.png')) + list((base / 'annotated_understanding').glob('*.png'))
        files += list((base / 'annotated_layout').glob('*.png')) if schema == 3 else []
    if schema == 3 and stage == 'quality':
        files += [base / 'pass2_report/red_blue_review.json']
    code = code or (current_execution().identity if current_execution() else code_identity())
    scoped = None
    if schema == 3:
        from .stage_dependencies import basis, configuration, SCHEMA
        runtime = _receipt_runtime(paths)
        scoped = (basis(runtime, code['actual_code_hashes'], stage) if 'actual_code_hashes' in code else
                  {'schema': SCHEMA, 'stage': stage, 'configuration': configuration(runtime, stage),
                   'code': code['actual_code_fingerprint']})
    return {**({'schema': schema} if schema >= 2 else {}),
            **({'basis': scoped} if scoped else {}),
            'configuration': scoped['configuration'] if scoped else fingerprint,
            'code': scoped['code'] if scoped else code['actual_code_fingerprint'],
            'files': {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(set(files)) if p.is_file()}}


def receipt_matches(paths, manifest, stage, code=None):
    try:
        receipts = manifest.get('stage_receipts')
        previous = receipts.get(stage) if isinstance(receipts, dict) else None
        return bool(isinstance(previous, dict) and previous.get('files') and previous ==
                    stage_receipt(paths, stage, manifest.get('config_fingerprint'), code, previous.get('schema', 1)))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def record_stage_receipt(paths, manifest, stage):
    from .stage_dependencies import enabled
    try:
        schema = 3 if enabled(_receipt_runtime(paths)) else 2
    except (OSError, ValueError, KeyError, TypeError):
        schema = 2
    manifest.setdefault('stage_receipts', {})[stage] = stage_receipt(
        paths, stage, manifest.get('config_fingerprint'), schema=schema)
