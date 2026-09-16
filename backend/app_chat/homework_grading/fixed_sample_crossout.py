"""Fail-closed image repairs for explicitly approved crossout samples.

The original ``clean/`` image remains immutable.  A repaired sibling is used
only by model stages that interpret student answers; layout detection and
rendering continue to use the original evidence image.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

import cv2
import numpy as np

from app_chat.homework_grading.utils import safe_json_dump, windows_io_path


FIXED_SAMPLE_CROSSOUT_ENV = 'HOMEWORK_FIXED_SAMPLE_CROSSOUT_REPAIR'
MODEL_IMAGE_PATH_KEY = 'model_abs_path'
_MANIFEST_PATH = os.path.join(
    os.path.dirname(__file__),
    'data',
    'experiments',
    'fixed_crossout_sample_repairs_20260724.json',
)


def fixed_sample_crossout_enabled(subject: str, feedback_runtime=None) -> bool:
    from .feedback_runtime import frozen_environment
    if feedback_runtime is not None and not feedback_runtime.has_specialized(subject):
        return False
    if str(subject or '').strip().lower() not in {'math', 'chinese'}:
        return False
    raw = frozen_environment(feedback_runtime, FIXED_SAMPLE_CROSSOUT_ENV, '1').strip().lower()
    return raw not in {'0', 'false', 'no', 'off'}


def load_fixed_sample_crossout_manifest() -> Dict[str, Any]:
    with open(_MANIFEST_PATH, 'r', encoding='utf-8') as file:
        payload = json.load(file)
    if not isinstance(payload, dict) or not isinstance(payload.get('cases'), list):
        raise ValueError('固定删除线样例清单格式无效')
    return payload


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(windows_io_path(path), 'rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_bgr(path: str) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(windows_io_path(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f'无法读取固定样例clean图: {path}')
    return image


def _validate_box(
    value: Any,
    width: int,
    height: int,
    label: str,
) -> Tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f'{label} 不是四元素坐标')
    x1, y1, x2, y2 = (int(item) for item in value)
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError(f'{label} 越过图像边界: {[x1, y1, x2, y2]}')
    return x1, y1, x2, y2


def _validate_point(
    value: Any,
    width: int,
    height: int,
    label: str,
) -> Tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f'{label} 不是二元素坐标')
    x, y = (int(item) for item in value)
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(f'{label} 越过图像边界: {[x, y]}')
    return x, y


def _mark_allowed(
    allowed: np.ndarray,
    box: Tuple[int, int, int, int],
) -> None:
    x1, y1, x2, y2 = box
    allowed[y1:y2, x1:x2] = True


def apply_fixed_sample_operations(
    image: np.ndarray,
    case: Dict[str, Any],
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Apply one already-approved case and return strict pixel audit data."""
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('固定删除线样例仅支持三通道BGR图')
    height, width = image.shape[:2]
    original = image.copy()
    repaired = image.copy()
    allowed = np.zeros((height, width), dtype=bool)
    operation_audits: List[Dict[str, Any]] = []

    for index, operation in enumerate(case.get('operations') or []):
        if not isinstance(operation, dict):
            raise ValueError(f'第{index + 1}个固定样例操作格式无效')
        operation_type = str(operation.get('type') or '').strip()
        audit: Dict[str, Any] = {
            'type': operation_type,
            'question_id': str(operation.get('question_id') or ''),
            'sample_part': str(operation.get('sample_part') or ''),
        }
        if operation_type == 'whiteout':
            box = _validate_box(
                operation.get('bbox_xyxy'),
                width,
                height,
                f'operations[{index}].bbox_xyxy',
            )
            x1, y1, x2, y2 = box
            repaired[y1:y2, x1:x2] = 255
            _mark_allowed(allowed, box)
            audit['bbox_xyxy'] = list(box)
        elif operation_type == 'whiteout_line':
            start = _validate_point(
                operation.get('start_xy'),
                width,
                height,
                f'operations[{index}].start_xy',
            )
            end = _validate_point(
                operation.get('end_xy'),
                width,
                height,
                f'operations[{index}].end_xy',
            )
            thickness = int(operation.get('thickness') or 0)
            if thickness <= 0:
                raise ValueError(
                    f'operations[{index}].thickness 必须为正整数'
                )
            cv2.line(repaired, start, end, (255, 255, 255), thickness)
            allowed_line = np.zeros((height, width), dtype=np.uint8)
            cv2.line(allowed_line, start, end, 255, thickness)
            allowed |= allowed_line > 0
            audit.update({
                'start_xy': list(start),
                'end_xy': list(end),
                'thickness': thickness,
            })
        elif operation_type == 'move_ink':
            source_box = _validate_box(
                operation.get('source_bbox_xyxy'),
                width,
                height,
                f'operations[{index}].source_bbox_xyxy',
            )
            clear_box = _validate_box(
                operation.get('source_clear_bbox_xyxy'),
                width,
                height,
                f'operations[{index}].source_clear_bbox_xyxy',
            )
            destination_box = _validate_box(
                operation.get('destination_bbox_xyxy'),
                width,
                height,
                f'operations[{index}].destination_bbox_xyxy',
            )
            sx1, sy1, sx2, sy2 = source_box
            cx1, cy1, cx2, cy2 = clear_box
            dx1, dy1, dx2, dy2 = destination_box
            source_patch = original[sy1:sy2, sx1:sx2].copy()
            if source_patch.shape[:2] != (dy2 - dy1, dx2 - dx1):
                raise ValueError('固定样例替换字符的源框与目标框尺寸不一致')
            threshold = int(operation.get('ink_threshold_gray_lt') or 250)
            ink_mask = cv2.cvtColor(source_patch, cv2.COLOR_BGR2GRAY) < threshold
            ink_count = int(np.count_nonzero(ink_mask))
            expected_ink_count = int(operation.get('expected_ink_pixel_count') or 0)
            if expected_ink_count and ink_count != expected_ink_count:
                raise RuntimeError(
                    f'固定样例替换字符像素数不匹配: {ink_count} != {expected_ink_count}'
                )
            repaired[cy1:cy2, cx1:cx2] = 255
            destination = repaired[dy1:dy2, dx1:dx2]
            destination[ink_mask] = source_patch[ink_mask]
            repaired[dy1:dy2, dx1:dx2] = destination
            _mark_allowed(allowed, clear_box)
            _mark_allowed(allowed, destination_box)
            audit.update({
                'source_bbox_xyxy': list(source_box),
                'source_clear_bbox_xyxy': list(clear_box),
                'destination_bbox_xyxy': list(destination_box),
                'ink_threshold_gray_lt': threshold,
                'ink_pixel_count': ink_count,
                'copied_ink_pixel_identical': bool(
                    np.array_equal(
                        repaired[dy1:dy2, dx1:dx2][ink_mask],
                        source_patch[ink_mask],
                    )
                ),
            })
        else:
            raise ValueError(f'未知固定样例图像操作: {operation_type}')
        operation_audits.append(audit)

    diff = np.any(original != repaired, axis=2)
    changed_pixel_count = int(np.count_nonzero(diff))
    outside_count = int(np.count_nonzero(diff & ~allowed))
    expected_changed = int(case.get('expected_changed_pixel_count') or 0)
    if outside_count:
        raise RuntimeError(f'固定样例修复越过白名单区域: {outside_count} pixels')
    if expected_changed and changed_pixel_count != expected_changed:
        raise RuntimeError(
            f'固定样例改动像素数不匹配: {changed_pixel_count} != {expected_changed}'
        )
    return repaired, {
        'changed_pixel_count': changed_pixel_count,
        'changed_outside_approved_regions': outside_count,
        'all_changes_inside_approved_regions': outside_count == 0,
        'operations': operation_audits,
    }


def _matching_case(
    manifest: Dict[str, Any],
    subject: str,
    page_num: int,
    source_sha256: str,
) -> Optional[Dict[str, Any]]:
    for case in manifest.get('cases') or []:
        if not isinstance(case, dict):
            continue
        if str(case.get('subject') or '') != str(subject or ''):
            continue
        if int(case.get('page') or 0) != int(page_num or 0):
            continue
        if str(case.get('source_sha256') or '').lower() != source_sha256.lower():
            continue
        return case
    return None


def repair_fixed_sample_image(
    image_path: str,
    output_dir: str,
    subject: str,
    page_num: int,
    *,
    manifest: Optional[Dict[str, Any]] = None,
    feedback_runtime=None,
    source_document_sha256: str = '',
) -> Tuple[str, Dict[str, Any]]:
    """Return an approved repaired model image, or the unchanged clean path."""
    source_sha256 = _sha256_file(image_path)
    audit: Dict[str, Any] = {
        'enabled': fixed_sample_crossout_enabled(subject, feedback_runtime),
        'applied': False,
        'subject': subject,
        'page': int(page_num),
        'source_image': image_path,
        'source_sha256': source_sha256,
    }
    if not audit['enabled']:
        audit['reason'] = 'feature_disabled'
        return image_path, audit

    if feedback_runtime is not None:
        config = feedback_runtime.dependencies['preprocessing']
        identities = config.get('fixed_document_identities', {}).get('cases', [])
        approved = [case for case in identities if case.get('subject') == subject
                    and case.get('source_document_sha256') == source_document_sha256
                    and len(source_document_sha256) == 64]
        if not approved:
            audit['reason'] = 'source_document_not_approved'
            return image_path, audit
        payload = config.get('fixed_crossout', {})
        audit.update(source_document_sha256=source_document_sha256,
                     config_fingerprint=feedback_runtime.fingerprint)
    else:
        payload = manifest or load_fixed_sample_crossout_manifest()
    case = _matching_case(payload, subject, page_num, source_sha256)
    if not case:
        audit['reason'] = 'source_not_approved'
        return image_path, audit

    image = _read_bgr(image_path)
    height, width = image.shape[:2]
    expected_size = [int(value) for value in (case.get('image_size_wh') or [])]
    if expected_size != [width, height]:
        raise RuntimeError(
            f'固定样例图像尺寸不匹配: {[width, height]} != {expected_size}'
        )
    repaired, pixel_audit = apply_fixed_sample_operations(image, case)
    ok, buffer = cv2.imencode('.png', repaired)
    if not ok:
        raise RuntimeError('无法编码固定样例模型判读图')
    encoded = buffer.tobytes()
    output_sha256 = _sha256_bytes(encoded)
    expected_output_sha256 = str(case.get('expected_output_sha256') or '').lower()
    if not expected_output_sha256 or output_sha256 != expected_output_sha256:
        raise RuntimeError(
            '固定样例输出哈希不匹配: '
            f'{output_sha256} != {expected_output_sha256 or "missing"}'
        )

    os.makedirs(windows_io_path(output_dir), exist_ok=True)
    stem = os.path.splitext(os.path.basename(image_path))[0]
    output_path = os.path.join(output_dir, f'{stem}.fixed_crossout.png')
    temp_path = output_path + '.tmp'
    with open(windows_io_path(temp_path), 'wb') as file:
        file.write(encoded)
    os.replace(windows_io_path(temp_path), windows_io_path(output_path))

    audit.update(pixel_audit)
    audit.update({
        'applied': True,
        'reason': 'approved_fixed_sample',
        'case_id': str(case.get('case_id') or ''),
        'manifest_version': str(payload.get('version') or ''),
        'model_image': output_path,
        'model_image_sha256': output_sha256,
        'expected_output_sha256': expected_output_sha256,
        'original_clean_preserved': _sha256_file(image_path) == source_sha256,
    })
    safe_json_dump(output_path + '.audit.json', audit)
    return output_path, audit


def prepare_fixed_sample_crossout_images(
    pages: Iterable[Dict[str, Any]],
    base_dir: str,
    subject: str,
    *, feedback_runtime=None, source_document_sha256: str = '',
) -> Dict[str, Any]:
    """Attach repaired model-image paths to matching page dictionaries."""
    page_list = list(pages)
    manifest = (feedback_runtime.dependencies['preprocessing'].get('fixed_crossout', {})
                if feedback_runtime is not None else load_fixed_sample_crossout_manifest())
    candidate_pages = {
        int(case.get('page') or 0)
        for case in manifest.get('cases') or []
        if str(case.get('subject') or '') == str(subject or '')
    }
    output_dir = os.path.join(base_dir, 'layout_evidence', 'fixed_sample_crossout')
    results: List[Dict[str, Any]] = []
    for page in page_list:
        page.pop(MODEL_IMAGE_PATH_KEY, None)
        page_num = int(page.get('page') or 0)
        clean_path = str(page.get('clean_abs_path') or '')
        if page_num not in candidate_pages or not clean_path or not os.path.isfile(windows_io_path(clean_path)):
            continue
        model_path, audit = repair_fixed_sample_image(
            clean_path,
            output_dir,
            subject,
            page_num,
            manifest=manifest,
            feedback_runtime=feedback_runtime,
            source_document_sha256=source_document_sha256,
        )
        if audit.get('applied'):
            page[MODEL_IMAGE_PATH_KEY] = model_path
        results.append(audit)

    summary = {
        'enabled': fixed_sample_crossout_enabled(subject, feedback_runtime),
        'mode': 'fixed_sample_allowlist',
        'manifest_version': str(manifest.get('version') or ''),
        'candidate_page_numbers': sorted(candidate_pages),
        'examined_page_count': len(results),
        'applied_page_count': sum(1 for item in results if item.get('applied')),
        'applied_case_ids': [
            item.get('case_id') for item in results if item.get('applied')
        ],
        'pages': results,
    }
    if results:
        os.makedirs(windows_io_path(output_dir), exist_ok=True)
        safe_json_dump(os.path.join(output_dir, 'summary.json'), summary)
    return summary
