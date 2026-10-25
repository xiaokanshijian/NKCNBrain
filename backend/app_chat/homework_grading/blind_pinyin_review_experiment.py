"""B-mode-only blind visual transcription experiment for Chinese pinyin words.

This module is deliberately isolated from ``grader_pass1_review``.  It never
loads a question's previous transcription, reference answer, verdict, or
review report into a model request, and it never writes back to Pass1.

Usage (from ``djangoProject``)::

    python -m app_chat.homework_grading.blind_pinyin_review_experiment --prepare-only
    python -m app_chat.homework_grading.blind_pinyin_review_experiment --run

The spaced executable name above is illustrative only; use the repository's
configured virtual environment path in practice.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from app_chat.homework_grading.llm_clients import (
    _call_homework_gemini_json,
    homework_review_gemini_model,
)
from app_chat.homework_grading.utils import (
    image_to_data_uri_for_gemini_review,
    normalize_position,
    safe_json_dump,
)


EXPERIMENT_MODE = 'blind_plain_v1'
EXPERIMENT_SEED = 20260717
DEFAULT_REPEATS = 3
DEFAULT_WORKERS = 3
MAX_FORMAT_RETRIES = 5
ROI_SCALE = 2
VALID_STATUSES = frozenset({'recognized', 'nonstandard', 'unclear', 'blank'})
_QUOTA_MARKERS = ('quota', 'rate limit', '429', 'resource exhausted', 'insufficient_quota')

_MODULE_DIR = Path(__file__).resolve().parent
_DJANGO_ROOT = _MODULE_DIR.parent.parent
DEFAULT_CASES_PATH = _MODULE_DIR / 'data' / 'experiments' / 'blind_pinyin_review_cases_20260717.json'
DEFAULT_SAMPLES_ROOT = (
    _DJANGO_ROOT / 'received_dir' / 'user_raw_file' / 'abc_TestGrading' / 'continuous_image_dmt'
)
DEFAULT_OUTPUT_DIR = _DJANGO_ROOT / 'analysis_output' / 'blind_pinyin_review_20260717'

BLIND_TRANSCRIPTION_SYSTEM_PROMPT = '''你是一名视觉转写员。仅依据本轮提供的一张作业截图，按从左到右、从上到下的顺序转写学生最终保留的手写汉字。

不要判断对错，不要推测题目应填写什么，也不要根据拼音、语境或常见词把看见的笔迹归一化。被清楚划掉的内容不属于最终作答；只有同色同笔迹且明显替代被划掉内容的格外修正字，才属于最终作答。

请只输出 JSON 对象：
{"slots":[{"index":1,"status":"recognized","recognized_char":""}]}

每个字槽一条记录。status 只能是 recognized、nonstandard、unclear、blank。只有能稳定识别为单个标准汉字时，status 才能是 recognized，recognized_char 必须恰好填写该一个汉字。其余三种状态的 recognized_char 必须是空字符串。不要输出 Markdown 或额外说明。'''
BLIND_TRANSCRIPTION_USER_TEXT = '请仅按截图输出 JSON。'


class BlindResponseFormatError(ValueError):
    """Returned content is not the deliberately small B-mode schema."""


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


def _is_cjk_char(value: str) -> bool:
    if len(value) != 1:
        return False
    code = ord(value)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2EBEF
    )


def _strip_json_fence(raw: str) -> str:
    text = str(raw or '').strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith('```'):
            lines = lines[:-1]
        text = '\n'.join(lines).strip()
    return text


def _loads_json_object(raw: str) -> Dict[str, Any]:
    text = _strip_json_fence(raw)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}')
        if start < 0 or end <= start:
            raise BlindResponseFormatError('response is not a JSON object')
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise BlindResponseFormatError('response JSON cannot be parsed') from exc
    if not isinstance(value, dict):
        raise BlindResponseFormatError('response root is not an object')
    return value


def normalize_blind_response(raw: str) -> Dict[str, Any]:
    """Validate the B-mode schema without consulting a case label."""
    payload = _loads_json_object(raw)
    source_slots = payload.get('slots')
    if not isinstance(source_slots, list) or not source_slots:
        raise BlindResponseFormatError('slots must be a non-empty list')
    if len(source_slots) > 40:
        raise BlindResponseFormatError('slots exceeds B-mode safety limit')

    normalized: List[Dict[str, Any]] = []
    for source in source_slots:
        if not isinstance(source, dict):
            raise BlindResponseFormatError('slot is not an object')
        try:
            index = int(source.get('index'))
        except (TypeError, ValueError) as exc:
            raise BlindResponseFormatError('slot index is invalid') from exc
        status = str(source.get('status') or '').strip()
        recognized_char = str(source.get('recognized_char') or '').strip()
        if status not in VALID_STATUSES:
            raise BlindResponseFormatError('slot status is invalid')
        if status == 'recognized':
            if not _is_cjk_char(recognized_char):
                raise BlindResponseFormatError('recognized slot must contain exactly one CJK character')
        elif recognized_char:
            raise BlindResponseFormatError('non-recognized slot must have an empty recognized_char')
        normalized.append({
            'index': index,
            'status': status,
            'recognized_char': recognized_char,
        })

    indexes = [slot['index'] for slot in normalized]
    if indexes != list(range(1, len(normalized) + 1)):
        raise BlindResponseFormatError('slot indexes must be contiguous and visually ordered from 1')
    return {'slots': normalized}


def build_blind_messages(image_data_uri: str) -> List[Dict[str, Any]]:
    """Build the only request shape allowed by this experiment.

    This function intentionally accepts no question, answer, page, or case
    object.  That makes business-text leakage structurally impossible unless a
    caller changes this module's public contract.
    """
    if not str(image_data_uri).startswith('data:image/'):
        raise ValueError('B-mode image must be an inline image data URI')
    return [
        {'role': 'system', 'content': BLIND_TRANSCRIPTION_SYSTEM_PROMPT},
        {
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': image_data_uri}},
                {'type': 'text', 'text': BLIND_TRANSCRIPTION_USER_TEXT},
            ],
        },
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
                if part.get('type') == 'image_url':
                    image_count += 1
    serialized_text = json.dumps(text_blocks, ensure_ascii=False)
    forbidden_field_names = (
        'student_answer', 'correct_answer', 'verdict', 'error_type',
        'target_slot', 'target_char', 'focused', 'confirmation',
    )
    forbidden_present = [name for name in forbidden_field_names if name in serialized_text]
    return {
        'experiment_mode': EXPERIMENT_MODE,
        'roles': [str(message.get('role') or '') for message in messages if isinstance(message, dict)],
        'image_count': image_count,
        'image_sha256': image_sha256,
        'text_blocks': text_blocks,
        'forbidden_field_names_present': forbidden_present,
        'business_text_leakage_free': image_count == 1 and not forbidden_present,
    }


def _crop_image(source_path: Path, position: Any, destination: Path) -> Dict[str, Any]:
    normalized = normalize_position(position)
    if not normalized:
        raise ValueError(f'invalid question_roi: {position!r}')
    try:
        from PIL import Image  # noqa: PLC0415
    except Exception as exc:
        raise RuntimeError('Pillow is required to prepare B-mode ROI images') from exc

    with Image.open(source_path) as source:
        source.load()
        width, height = source.size
        x1, y1, x2, y2 = normalized
        box = (
            int(round(x1 / 1000.0 * width)),
            int(round(y1 / 1000.0 * height)),
            int(round(x2 / 1000.0 * width)),
            int(round(y2 / 1000.0 * height)),
        )
        left, top, right, bottom = box
        if right - left < 16 or bottom - top < 16:
            raise ValueError(f'question_roi is too small: {position!r}')
        crop = source.crop(box).convert('RGB')
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        crop = crop.resize((crop.width * ROI_SCALE, crop.height * ROI_SCALE), resample)
        destination.parent.mkdir(parents=True, exist_ok=True)
        crop.save(destination, format='PNG')
        cropped_size = crop.size
        crop.close()
    return {
        'source_size': [width, height],
        'source_box_pixels': list(box),
        'crop_size': list(cropped_size),
        'scale': ROI_SCALE,
    }


def _create_contact_sheet(prepared_cases: List[Dict[str, Any]], output_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415
    except Exception as exc:
        raise RuntimeError('Pillow is required to create the ROI contact sheet') from exc

    thumb_width, thumb_height, label_height = 520, 300, 28
    columns = 2
    rows = (len(prepared_cases) + columns - 1) // columns
    sheet = Image.new('RGB', (columns * thumb_width, rows * (thumb_height + label_height)), 'white')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, case in enumerate(prepared_cases):
        row, column = divmod(index, columns)
        origin = (column * thumb_width, row * (thumb_height + label_height))
        with Image.open(case['crop_path']) as image:
            image.thumbnail((thumb_width - 8, thumb_height - 8))
            x = origin[0] + (thumb_width - image.width) // 2
            y = origin[1] + (thumb_height - image.height) // 2
            sheet.paste(image.convert('RGB'), (x, y))
        draw.rectangle((origin[0], origin[1] + thumb_height, origin[0] + thumb_width, origin[1] + thumb_height + label_height), fill='white')
        draw.text((origin[0] + 4, origin[1] + thumb_height + 7), case['case_id'], fill='black', font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format='PNG')
    sheet.close()


def prepare_cases(cases_path: Path, samples_root: Path, output_dir: Path) -> Dict[str, Any]:
    """Create immutable ROI copies and an audit manifest without model calls."""
    manifest = _read_json(cases_path)
    if manifest.get('experiment_mode') != EXPERIMENT_MODE:
        raise ValueError('case manifest is not for blind_plain_v1')
    cases = manifest.get('cases')
    if not isinstance(cases, list) or len(cases) != 10:
        raise ValueError('B-mode experiment requires exactly 10 fixed cases')

    prepared_cases: List[Dict[str, Any]] = []
    seen_ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError('case must be an object')
        case_id = str(case.get('case_id') or '').strip()
        if not case_id or case_id in seen_ids:
            raise ValueError('case_id must be unique')
        seen_ids.add(case_id)
        homework_id = str(case.get('homework_id') or '').strip()
        image_relpath = str(case.get('image_relpath') or '').strip().replace('/', os.sep)
        if not homework_id or not image_relpath:
            raise ValueError(f'{case_id} lacks a source image reference')
        source_path = (samples_root / homework_id / image_relpath).resolve()
        expected_root = (samples_root / homework_id).resolve()
        if expected_root not in source_path.parents or not source_path.is_file():
            raise ValueError(f'{case_id} source image is missing or outside its homework root')
        crop_path = output_dir / 'crops' / f'{case_id}.png'
        crop_meta = _crop_image(source_path, case.get('question_roi'), crop_path)
        prepared_cases.append({
            'case_id': case_id,
            'crop_path': str(crop_path),
            'crop_sha256': _sha256_file(crop_path),
            'source_image_sha256': _sha256_file(source_path),
            'source_image_path': str(source_path),
            'question_roi': normalize_position(case.get('question_roi')),
            **crop_meta,
        })

    _create_contact_sheet(prepared_cases, output_dir / 'roi_contact_sheet.png')
    prepared = {
        'experiment_mode': EXPERIMENT_MODE,
        'prepared_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'cases_manifest_sha256': _sha256_file(cases_path),
        'roi_scale': ROI_SCALE,
        'case_count': len(prepared_cases),
        'cases': prepared_cases,
        'contact_sheet': str(output_dir / 'roi_contact_sheet.png'),
    }
    safe_json_dump(str(output_dir / 'prepared_cases.json'), prepared)
    return prepared


def _content_from_response(response: Any) -> str:
    choices = getattr(response, 'choices', None) or []
    if not choices:
        raise RuntimeError('Gemini returned no choices')
    message = getattr(choices[0], 'message', None)
    content = getattr(message, 'content', '') if message is not None else ''
    if not content:
        raise RuntimeError('Gemini returned empty content')
    return str(content)


def call_blind_model(messages: List[Dict[str, Any]]) -> str:
    response = _call_homework_gemini_json(messages, temperature=0.1, max_tokens=2000)
    return _content_from_response(response)


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _QUOTA_MARKERS)


class RetryBudget:
    def __init__(self, maximum: int):
        self.maximum = maximum
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.used >= self.maximum:
                return False
            self.used += 1
            return True


def _result_path(output_dir: Path, case_id: str, repeat: int) -> Path:
    return output_dir / 'responses' / f'{case_id}__repeat{repeat}.json'


def _load_existing_result(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        result = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if result.get('experiment_mode') == EXPERIMENT_MODE and result.get('status') in ('completed', 'failed', 'quota_limited'):
        return result
    return None


def _run_one_task(
    task: Dict[str, Any],
    output_dir: Path,
    retry_budget: RetryBudget,
    quota_stop: threading.Event,
    call_func: Callable[[List[Dict[str, Any]]], str],
) -> Dict[str, Any]:
    result_path = _result_path(output_dir, task['case_id'], task['repeat'])
    existing = _load_existing_result(result_path)
    if existing is not None:
        return existing
    if quota_stop.is_set():
        result = {
            'experiment_mode': EXPERIMENT_MODE,
            'case_id': task['case_id'],
            'repeat': task['repeat'],
            'status': 'quota_limited',
            'attempts': 0,
            'skipped_before_call': True,
        }
        safe_json_dump(str(result_path), result)
        return result

    image_data_uri = image_to_data_uri_for_gemini_review(task['crop_path'])
    messages = build_blind_messages(image_data_uri)
    audit = request_audit(messages, task['crop_sha256'])
    attempts: List[Dict[str, Any]] = []
    for attempt_number in range(1, 3):
        if attempt_number == 2 and not retry_budget.take():
            break
        started_at = time.monotonic()
        raw: Optional[str] = None
        try:
            raw = call_func(messages)
            normalized = normalize_blind_response(raw)
        except BlindResponseFormatError as exc:
            attempts.append({
                'attempt': attempt_number,
                'kind': 'format_error',
                'error': str(exc),
                # Keep malformed output for the experiment audit. It is not
                # reused as a prompt or as an evaluation label.
                'raw_response': raw,
                'elapsed_seconds': round(time.monotonic() - started_at, 3),
            })
            if attempt_number == 1:
                continue
            result = {
                'experiment_mode': EXPERIMENT_MODE,
                'case_id': task['case_id'],
                'repeat': task['repeat'],
                'status': 'failed',
                'attempts': attempts,
                'request_audit': audit,
            }
            safe_json_dump(str(result_path), result)
            return result
        except Exception as exc:  # External model failures are audit data, not a retry mode.
            quota_limited = _is_quota_error(exc)
            attempts.append({
                'attempt': attempt_number,
                'kind': 'quota_error' if quota_limited else 'call_error',
                'error': str(exc),
                'elapsed_seconds': round(time.monotonic() - started_at, 3),
            })
            if quota_limited:
                quota_stop.set()
                status = 'quota_limited'
            else:
                status = 'failed'
            result = {
                'experiment_mode': EXPERIMENT_MODE,
                'case_id': task['case_id'],
                'repeat': task['repeat'],
                'status': status,
                'attempts': attempts,
                'request_audit': audit,
            }
            safe_json_dump(str(result_path), result)
            return result
        else:
            attempts.append({
                'attempt': attempt_number,
                'kind': 'completed',
                'elapsed_seconds': round(time.monotonic() - started_at, 3),
            })
            result = {
                'experiment_mode': EXPERIMENT_MODE,
                'case_id': task['case_id'],
                'repeat': task['repeat'],
                'status': 'completed',
                'attempts': attempts,
                'raw_response': raw,
                'normalized_response': normalized,
                'request_audit': audit,
            }
            safe_json_dump(str(result_path), result)
            return result

    result = {
        'experiment_mode': EXPERIMENT_MODE,
        'case_id': task['case_id'],
        'repeat': task['repeat'],
        'status': 'failed',
        'attempts': attempts,
        'request_audit': audit,
        'error': 'format_retry_budget_exhausted',
    }
    safe_json_dump(str(result_path), result)
    return result


def run_blind_calls(
    prepared: Dict[str, Any],
    output_dir: Path,
    repeats: int = DEFAULT_REPEATS,
    workers: int = DEFAULT_WORKERS,
    seed: int = EXPERIMENT_SEED,
    call_func: Callable[[List[Dict[str, Any]]], str] = call_blind_model,
) -> List[Dict[str, Any]]:
    if repeats != DEFAULT_REPEATS:
        raise ValueError(f'B-mode repeat count is fixed at {DEFAULT_REPEATS}')
    if workers < 1 or workers > DEFAULT_WORKERS:
        raise ValueError(f'B-mode workers must be between 1 and {DEFAULT_WORKERS}')
    tasks = [
        {
            'case_id': case['case_id'],
            'repeat': repeat,
            'crop_path': case['crop_path'],
            'crop_sha256': case['crop_sha256'],
        }
        for case in prepared['cases']
        for repeat in range(1, repeats + 1)
    ]
    random.Random(seed).shuffle(tasks)
    retry_budget = RetryBudget(MAX_FORMAT_RETRIES)
    quota_stop = threading.Event()
    results: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_run_one_task, task, output_dir, retry_budget, quota_stop, call_func)
            for task in tasks
        ]
        for future in futures:
            results.append(future.result())
    results.sort(key=lambda item: (str(item.get('case_id') or ''), int(item.get('repeat') or 0)))
    safe_json_dump(str(output_dir / 'run_summary.json'), {
        'experiment_mode': EXPERIMENT_MODE,
        'seed': seed,
        'requested_primary_calls': len(tasks),
        'max_extra_format_retries': MAX_FORMAT_RETRIES,
        'format_retries_used': retry_budget.used,
        'physical_request_count': sum(len(item.get('attempts') or []) for item in results),
        'quota_limited': quota_stop.is_set(),
        'results': results,
    })
    return results


def _slot_text(result: Dict[str, Any]) -> str:
    slots = ((result.get('normalized_response') or {}).get('slots') or [])
    return ''.join(slot.get('recognized_char') or '' for slot in slots)


def _completed_rows(results: Iterable[Dict[str, Any]], case_id: str) -> List[Dict[str, Any]]:
    return [
        result for result in results
        if result.get('case_id') == case_id and result.get('status') == 'completed'
    ]


def evaluate_results(cases_path: Path, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Evaluate saved B-mode observations; labels are never used for calls."""
    manifest = _read_json(cases_path)
    cases = manifest['cases']
    per_case: List[Dict[str, Any]] = []
    standard_case_passes: List[bool] = []
    correct_false_positives = 0
    correct_total = 0
    nonstandard_pass = False
    for case in cases:
        label = case.get('evaluation') or {}
        case_id = str(case['case_id'])
        rows = _completed_rows(results, case_id)
        kind = str(label.get('kind') or '')
        entry: Dict[str, Any] = {
            'case_id': case_id,
            'kind': kind,
            'completed_runs': len(rows),
            'observed_texts': [_slot_text(row) for row in rows],
        }
        if kind == 'standard_wrong':
            actual_text = str(label.get('actual_text') or '')
            hits = sum(_slot_text(row) == actual_text for row in rows)
            entry.update({'actual_text_hits': hits, 'passed': hits >= 2})
            standard_case_passes.append(hits >= 2)
        elif kind == 'correct':
            expected_text = str(label.get('expected_text') or '')
            false_positives = sum(_slot_text(row) != expected_text for row in rows)
            entry.update({'false_positive_runs': false_positives, 'passed': false_positives < 2})
            correct_false_positives += false_positives
            correct_total += DEFAULT_REPEATS
        elif kind == 'nonstandard':
            target_index = int(label.get('target_index') or 1)
            target_expected_char = str(label.get('target_expected_char') or '')
            hits = 0
            for row in rows:
                slots = ((row.get('normalized_response') or {}).get('slots') or [])
                slot = next((item for item in slots if item.get('index') == target_index), {})
                if slot.get('status') in ('nonstandard', 'unclear') and not slot.get('recognized_char'):
                    hits += 1
                if slot.get('recognized_char') == target_expected_char:
                    entry.setdefault('normalized_to_target_runs', 0)
                    entry['normalized_to_target_runs'] += 1
            entry.update({'nonstandard_or_unclear_hits': hits, 'passed': hits >= 2})
            nonstandard_pass = hits >= 2
        else:
            raise ValueError(f'unknown evaluation kind for {case_id}: {kind}')
        per_case.append(entry)

    valid_json_count = sum(1 for result in results if result.get('status') == 'completed')
    leakage_free = all(
        bool((result.get('request_audit') or {}).get('business_text_leakage_free'))
        for result in results
        if result.get('request_audit')
    )
    passed = bool(
        len(standard_case_passes) == 2
        and all(standard_case_passes)
        and correct_total == 21
        and correct_false_positives <= 1
        and nonstandard_pass
        and valid_json_count >= 29
        and leakage_free
    )
    return {
        'experiment_mode': EXPERIMENT_MODE,
        'valid_json_count': valid_json_count,
        'expected_primary_calls': 30,
        'correct_false_positive_runs': correct_false_positives,
        'correct_total_runs': correct_total,
        'business_text_leakage_free': leakage_free,
        'passed': passed,
        'per_case': per_case,
    }


def write_output_report(output_dir: Path, evaluation: Dict[str, Any]) -> None:
    lines = [
        '# B 模式盲视觉转写实验结果',
        '',
        f'- 模式：`{EXPERIMENT_MODE}`（未实现或调用 A/C 模式）',
        f'- 结论：`{"通过" if evaluation.get("passed") else "未通过"}`',
        f'- 有效 JSON：{evaluation.get("valid_json_count")}/30',
        f'- 正确题假阳性：{evaluation.get("correct_false_positive_runs")}/21',
        f'- 业务文本泄漏审计：{"通过" if evaluation.get("business_text_leakage_free") else "失败"}',
        '',
        '| 题例 | 类型 | 完成次数 | 观测 | 结果 |',
        '| --- | --- | ---: | --- | --- |',
    ]
    for entry in evaluation.get('per_case') or []:
        observed = '<br>'.join(str(item) for item in entry.get('observed_texts') or []) or '-'
        lines.append(
            f'| {entry.get("case_id")} | {entry.get("kind")} | {entry.get("completed_runs")} | {observed} | '
            f'{"通过" if entry.get("passed") else "未通过"} |'
        )
    (output_dir / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def run_experiment(
    cases_path: Path,
    samples_root: Path,
    output_dir: Path,
    *,
    prepare_only: bool = False,
    workers: int = DEFAULT_WORKERS,
) -> Dict[str, Any]:
    prepared = prepare_cases(cases_path, samples_root, output_dir)
    if prepare_only:
        return {'prepared': prepared, 'ran_model': False}
    results = run_blind_calls(prepared, output_dir, workers=workers)
    evaluation = evaluate_results(cases_path, results)
    safe_json_dump(str(output_dir / 'evaluation.json'), evaluation)
    write_output_report(output_dir, evaluation)
    return {'prepared': prepared, 'ran_model': True, 'evaluation': evaluation}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='B-mode-only blind visual transcription experiment for pinyin words')
    parser.add_argument('--cases', default=str(DEFAULT_CASES_PATH), help='Fixed B-mode case manifest JSON')
    parser.add_argument('--samples-root', default=str(DEFAULT_SAMPLES_ROOT), help='Root containing homework_* sample folders')
    parser.add_argument('--output-dir', default=str(DEFAULT_OUTPUT_DIR), help='Ignored experiment output directory')
    parser.add_argument('--prepare-only', action='store_true', help='Export ROI images and contact sheet without any model call')
    parser.add_argument('--run', action='store_true', help='Run the fixed B-mode calls after ROI preparation')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help='B-mode worker count (1-3)')
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.prepare_only and args.run:
        raise SystemExit('--prepare-only and --run cannot be used together')
    if not args.prepare_only and not args.run:
        raise SystemExit('choose --prepare-only or --run; no other experiment mode is available')
    result = run_experiment(
        Path(args.cases).resolve(),
        Path(args.samples_root).resolve(),
        Path(args.output_dir).resolve(),
        prepare_only=bool(args.prepare_only),
        workers=int(args.workers),
    )
    prepared = result['prepared']
    print(f'prepared {prepared["case_count"]} B-mode ROI images')
    print(f'contact sheet: {prepared["contact_sheet"]}')
    if result.get('ran_model'):
        evaluation = result['evaluation']
        print(f'B-mode evaluation: {"passed" if evaluation.get("passed") else "not passed"}')
        print(f'valid JSON: {evaluation.get("valid_json_count")}/30')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
