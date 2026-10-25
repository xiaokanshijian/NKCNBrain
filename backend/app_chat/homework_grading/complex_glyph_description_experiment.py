"""C-mode shadow probe for visual evidence of one nonstandard Chinese glyph.

This module is deliberately separate from the B-mode experiment and the formal
Pass1 review.  A model request can contain only one prepared ROI, a neutral
visual-description instruction, and its JSON schema.  It never receives a
question id, page number, prior transcription, reference answer, verdict, or
the offline evaluation label.

Usage (from ``djangoProject``)::

    python -m app_chat.homework_grading.complex_glyph_description_experiment --prepare-only
    python -m app_chat.homework_grading.complex_glyph_description_experiment --run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app_chat.homework_grading.blind_pinyin_review_experiment import (
    DEFAULT_SAMPLES_ROOT,
    ROI_SCALE,
    _content_from_response,
    _crop_image,
    _is_cjk_char,
    _is_quota_error,
    _loads_json_object,
)
from app_chat.homework_grading.llm_clients import (
    _call_homework_gemini_json,
)
from app_chat.homework_grading.utils import image_to_data_uri_for_gemini_review, safe_json_dump


EXPERIMENT_MODE = 'glyph_description_v1'
DEFAULT_REPEATS = 3
MAX_FORMAT_RETRIES = 2
VALID_STATUSES = frozenset({'recognized', 'nonstandard', 'unclear', 'blank'})
_MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_CASE_PATH = _MODULE_DIR / 'data' / 'experiments' / 'complex_glyph_description_case_20260717.json'
DEFAULT_OUTPUT_DIR = _MODULE_DIR.parent.parent / 'analysis_output' / 'complex_glyph_description_20260717'

C_DESCRIPTION_SYSTEM_PROMPT = '''你是一名视觉记录员。仅依据本轮提供的一张作业截图，按视觉顺序记录学生最终保留的每个手写汉字字槽。

不要判断对错，不要推测题目应填写什么，不要根据拼音、语境或常见词归一化笔迹，也不要猜测这个字想写成哪个规范汉字。被清楚划掉的内容不属于最终作答；只有同色同笔迹且明显替代被划掉内容的格外修正字，才属于最终作答。

请只输出 JSON 对象：
{"slots":[{"index":1,"status":"recognized","recognized_char":"","visual_description":""}]}

每个字槽一条记录。status 只能是 recognized、nonstandard、unclear、blank。若能稳定识别为单个标准汉字，使用 recognized，并只在 recognized_char 填该一个字；visual_description 留空。若字形不能对应标准汉字、但异常局部清楚可见，使用 nonstandard，recognized_char 留空，visual_description 用简短的客观视觉描述记录局部位置、笔画或部件形状，不得命名它本应是哪一个字。unclear 与 blank 的两个文本字段都留空。不要输出 Markdown 或额外说明。'''
C_DESCRIPTION_USER_TEXT = '请仅按截图输出 JSON。'


class CDescriptionFormatError(ValueError):
    """Returned content is not the intentionally small C-mode schema."""


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open('r', encoding='utf-8') as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f'JSON root must be an object: {path}')
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_c_description_response(raw: str) -> Dict[str, Any]:
    """Validate only C's visual record, without consulting the offline label."""
    try:
        payload = _loads_json_object(raw)
    except ValueError as exc:
        raise CDescriptionFormatError(str(exc)) from exc
    source_slots = payload.get('slots')
    if not isinstance(source_slots, list) or not source_slots or len(source_slots) > 12:
        raise CDescriptionFormatError('slots must be a non-empty list of at most 12 entries')

    slots: List[Dict[str, Any]] = []
    for source in source_slots:
        if not isinstance(source, dict):
            raise CDescriptionFormatError('slot is not an object')
        try:
            index = int(source.get('index'))
        except (TypeError, ValueError) as exc:
            raise CDescriptionFormatError('slot index is invalid') from exc
        status = str(source.get('status') or '').strip()
        recognized_char = str(source.get('recognized_char') or '').strip()
        visual_description = str(source.get('visual_description') or '').strip()
        if status not in VALID_STATUSES:
            raise CDescriptionFormatError('slot status is invalid')
        if status == 'recognized':
            if not _is_cjk_char(recognized_char) or visual_description:
                raise CDescriptionFormatError('recognized slot must have one CJK char and no description')
        elif status == 'nonstandard':
            if recognized_char or not visual_description or len(visual_description) > 120:
                raise CDescriptionFormatError('nonstandard slot must have only a concise description')
        elif recognized_char or visual_description:
            raise CDescriptionFormatError('unclear/blank slot must have empty text fields')
        slots.append({
            'index': index,
            'status': status,
            'recognized_char': recognized_char,
            'visual_description': visual_description,
        })
    if [item['index'] for item in slots] != list(range(1, len(slots) + 1)):
        raise CDescriptionFormatError('slot indexes must be contiguous and visually ordered from 1')
    return {'slots': slots}


def build_c_description_messages(image_data_uri: str) -> List[Dict[str, Any]]:
    """Build C's visual-only request shape; no business object is accepted."""
    if not str(image_data_uri).startswith('data:image/'):
        raise ValueError('C-mode image must be an inline image data URI')
    return [
        {'role': 'system', 'content': C_DESCRIPTION_SYSTEM_PROMPT},
        {'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': image_data_uri}},
            {'type': 'text', 'text': C_DESCRIPTION_USER_TEXT},
        ]},
    ]


def request_audit(messages: List[Dict[str, Any]], image_sha256: str) -> Dict[str, Any]:
    text_blocks: List[str] = []
    image_count = 0
    for message in messages:
        content = message.get('content') if isinstance(message, dict) else None
        if isinstance(content, str):
            text_blocks.append(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get('type') == 'text':
                    text_blocks.append(str(part.get('text') or ''))
                elif part.get('type') == 'image_url':
                    image_count += 1
    serialized = json.dumps(text_blocks, ensure_ascii=False)
    forbidden = (
        'student_answer', 'correct_answer', 'verdict', 'error_type',
        'target_slot', 'target_char', 'focused', 'confirmation',
    )
    hits = [item for item in forbidden if item in serialized]
    return {
        'experiment_mode': EXPERIMENT_MODE,
        'roles': [str(item.get('role') or '') for item in messages],
        'image_count': image_count,
        'image_sha256': image_sha256,
        'text_blocks': text_blocks,
        'forbidden_field_names_present': hits,
        'business_text_leakage_free': image_count == 1 and not hits,
    }


def prepare_case(case_path: Path = DEFAULT_CASE_PATH, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Dict[str, Any]:
    manifest = _read_json(case_path)
    if manifest.get('experiment_mode') != EXPERIMENT_MODE:
        raise ValueError('case manifest experiment_mode mismatch')
    case = manifest.get('case')
    if not isinstance(case, dict):
        raise ValueError('C-mode manifest must have one case object')
    source = DEFAULT_SAMPLES_ROOT / str(case.get('homework_id') or '') / str(case.get('image_relpath') or '')
    if not source.is_file():
        raise FileNotFoundError(f'case image does not exist: {source}')
    crop_path = output_dir / 'crop.png'
    crop = _crop_image(source, case.get('question_roi'), crop_path)
    prepared = {
        'experiment_mode': EXPERIMENT_MODE,
        'case_id': str(case.get('case_id') or ''),
        'crop_path': str(crop_path),
        'crop_sha256': _sha256_file(crop_path),
        'crop_size': crop['crop_size'],
        'source_sha256': _sha256_file(source),
    }
    safe_json_dump(str(output_dir / 'prepared_case.json'), prepared)
    return prepared


def call_c_description_model(messages: List[Dict[str, Any]]) -> str:
    response = _call_homework_gemini_json(
        messages,
        temperature=0.1,
        max_tokens=2000,
    )
    return _content_from_response(response)


def _result_path(output_dir: Path, repeat: int) -> Path:
    return output_dir / 'requests' / f'repeat_{repeat:02d}.json'


def _load_result(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    value = _read_json(path)
    return value if value.get('experiment_mode') == EXPERIMENT_MODE else None


def _run_one(
    prepared: Dict[str, Any],
    output_dir: Path,
    repeat: int,
    retry_state: Dict[str, int],
    call_func: Callable[[List[Dict[str, Any]]], str],
) -> Dict[str, Any]:
    result_path = _result_path(output_dir, repeat)
    existing = _load_result(result_path)
    if existing is not None:
        return existing
    messages = build_c_description_messages(image_to_data_uri_for_gemini_review(prepared['crop_path']))
    audit = request_audit(messages, prepared['crop_sha256'])
    attempts: List[Dict[str, Any]] = []
    for attempt_number in range(1, 3):
        if attempt_number == 2:
            if retry_state['used'] >= MAX_FORMAT_RETRIES:
                break
            retry_state['used'] += 1
        started = time.monotonic()
        raw: Optional[str] = None
        try:
            raw = call_func(messages)
            normalized = normalize_c_description_response(raw)
        except CDescriptionFormatError as exc:
            attempts.append({
                'attempt': attempt_number,
                'kind': 'format_error',
                'error': str(exc),
                'raw_response': raw,
                'elapsed_seconds': round(time.monotonic() - started, 3),
            })
            continue
        except Exception as exc:
            result = {
                'experiment_mode': EXPERIMENT_MODE,
                'repeat': repeat,
                'status': 'quota_limited' if _is_quota_error(exc) else 'failed',
                'attempts': attempts + [{'attempt': attempt_number, 'kind': 'call_error', 'error': str(exc)}],
                'request_audit': audit,
            }
            safe_json_dump(str(result_path), result)
            return result
        result = {
            'experiment_mode': EXPERIMENT_MODE,
            'repeat': repeat,
            'status': 'completed',
            'attempts': attempts + [{'attempt': attempt_number, 'kind': 'completed', 'elapsed_seconds': round(time.monotonic() - started, 3)}],
            'raw_response': raw,
            'normalized_response': normalized,
            'request_audit': audit,
        }
        safe_json_dump(str(result_path), result)
        return result
    result = {
        'experiment_mode': EXPERIMENT_MODE,
        'repeat': repeat,
        'status': 'failed',
        'attempts': attempts,
        'request_audit': audit,
        'error': 'format_retry_budget_exhausted',
    }
    safe_json_dump(str(result_path), result)
    return result


def evaluate(case_path: Path, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Read the offline label only after all model calls have completed."""
    label = _read_json(case_path)['case']['evaluation']
    target_index = int(label['target_index'])
    target_char = str(label['target_expected_char'])
    completed = [item for item in results if item.get('status') == 'completed']
    nonstandard_records: List[str] = []
    normalized_to_target = 0
    for result in completed:
        slots = result['normalized_response']['slots']
        slot = next((item for item in slots if item['index'] == target_index), None)
        if slot is None:
            continue
        if slot['status'] == 'nonstandard':
            nonstandard_records.append(slot['visual_description'])
        if slot['status'] == 'recognized' and slot['recognized_char'] == target_char:
            normalized_to_target += 1
    audits = [item.get('request_audit') or {} for item in results]
    return {
        'experiment_mode': EXPERIMENT_MODE,
        'completed_runs': len(completed),
        'nonstandard_description_runs': len(nonstandard_records),
        'descriptions': nonstandard_records,
        'normalized_to_target_runs': normalized_to_target,
        'business_text_leakage_free': len(audits) == DEFAULT_REPEATS and all(
            audit.get('business_text_leakage_free') for audit in audits
        ),
        'passed': len(nonstandard_records) >= 2 and normalized_to_target == 0,
    }


def write_report(output_dir: Path, evaluation: Dict[str, Any], physical_calls: int, retries: int) -> None:
    lines = [
        '# C 模式非标准字形局部描述探针',
        '',
        f"- 模式：`{EXPERIMENT_MODE}`（仅影子运行）",
        f"- 结论：`{'通过' if evaluation['passed'] else '未通过'}`",
        f"- 实际调用：{physical_calls}（3 次主调用，格式重试 {retries} 次）",
        f"- 完成调用：{evaluation['completed_runs']}/3",
        f"- 非标准局部描述：{evaluation['nonstandard_description_runs']}/3",
        f"- 被规范化为离线目标字：{evaluation['normalized_to_target_runs']}/3",
        f"- 业务文本泄漏审计：{'通过' if evaluation['business_text_leakage_free'] else '失败'}",
        '',
        '## 描述原文',
        '',
    ]
    if evaluation.get('backend'):
        lines[3:3] = [
            f"- 后端：`{evaluation['backend']}`",
            f"- 模型：`{evaluation.get('model') or ''}`",
        ]
    lines.extend(f'- {description}' for description in evaluation['descriptions'])
    safe_json_dump(str(output_dir / 'evaluation.json'), evaluation)
    (output_dir / 'report.md').parent.mkdir(parents=True, exist_ok=True)
    (output_dir / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='C-mode nonstandard glyph description shadow probe')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if args.prepare_only == args.run:
        raise SystemExit('choose exactly one of --prepare-only or --run')
    prepared = prepare_case()
    if args.prepare_only:
        print(f"prepared C-mode ROI: {prepared['crop_path']}")
        return 0

    retry_state = {'used': 0}
    results: List[Dict[str, Any]] = []
    for repeat in range(1, DEFAULT_REPEATS + 1):
        result = _run_one(prepared, DEFAULT_OUTPUT_DIR, repeat, retry_state, call_c_description_model)
        results.append(result)
        if result.get('status') == 'quota_limited':
            break
    summary = {
        'experiment_mode': EXPERIMENT_MODE,
        'physical_request_count': sum(len(item.get('attempts') or []) for item in results),
        'format_retries_used': retry_state['used'],
        'results': results,
    }
    safe_json_dump(str(DEFAULT_OUTPUT_DIR / 'run_summary.json'), summary)
    evaluation = evaluate(DEFAULT_CASE_PATH, results)
    write_report(DEFAULT_OUTPUT_DIR, evaluation, summary['physical_request_count'], retry_state['used'])
    print(f"C-mode evaluation: {'passed' if evaluation['passed'] else 'not passed'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
