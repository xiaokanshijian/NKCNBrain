from __future__ import annotations

import datetime
import os
import shutil
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import cv2
import fitz
import numpy as np

from app_chat.homework_grading.utils import page_filename, safe_json_dump, safe_json_load


DPI = 300
RED_LOWER1 = np.array([0, 15, 80], dtype=np.uint8)
RED_UPPER1 = np.array([15, 255, 255], dtype=np.uint8)
RED_LOWER2 = np.array([150, 15, 80], dtype=np.uint8)
RED_UPPER2 = np.array([180, 255, 255], dtype=np.uint8)
RED_RESIDUAL_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
RED_RESIDUAL_LIGHT_VALUE_MIN = 185
RED_RESIDUAL_MASK_ENV = 'HOMEWORK_RED_INK_RESIDUAL_MASK'
REVIEW_LIGHT_RESIDUAL_VALUE_MIN = 230
WORKFLOW_BLACK_INK_IMAGE_ENV = 'HOMEWORK_GRADING_BLACK_INK_IMAGE'
LEGACY_REVIEW_BLACK_INK_IMAGE_ENV = 'HOMEWORK_PASS1_REVIEW_BLACK_INK_IMAGE'

PREPROCESS_SCHEMA_VERSION = 'homework-preprocess-v2'
PREPROCESS_MODE_AUTO = 'auto'
PREPROCESS_MODE_SCAN = 'scan'
PREPROCESS_MODE_PHOTO = 'photo'
PREPROCESS_MODE_OFF = 'off'
PREPROCESS_MODES = {
    PREPROCESS_MODE_AUTO,
    PREPROCESS_MODE_SCAN,
    PREPROCESS_MODE_PHOTO,
    PREPROCESS_MODE_OFF,
}
PREPROCESS_MODE_LABELS = {
    PREPROCESS_MODE_AUTO: '自动识别',
    PREPROCESS_MODE_SCAN: '扫描件模式',
    PREPROCESS_MODE_PHOTO: '拍照增强',
    PREPROCESS_MODE_OFF: '关闭预处理',
}

CLASSIFIER_MAX_SIDE = 900
CLASSIFIER_TILE_COUNT = 8
CLASSIFIER_WHITE_VALUE_MIN = 230
CLASSIFIER_SCAN_WHITE_FRACTION_MIN = 0.70
CLASSIFIER_SCAN_PAPER_P85_MIN = 248.0
CLASSIFIER_SCAN_FIELD_RANGE_MAX = 8.0
CLASSIFIER_SCAN_SATURATION_P90_MAX = 5.0
CLASSIFIER_BLANK_INK_FRACTION_MAX = 0.005

LEGACY_MASK_FRACTION_MAX = 0.08
LEGACY_MASK_COMPONENT_MAX = 0.03

PHOTO_PAPER_WORK_SIZE = 1000
PHOTO_PAPER_RADIUS_FRACTION = 1 / 40
PHOTO_RED_BETA = 0.45
PHOTO_RED_FLOOR = 14.0
PHOTO_RED_CHROMA_BLUR = 1.2
PHOTO_RED_GROW = 1
PHOTO_BLACK_POINT = 0.42
PHOTO_WHITE_POINT = 0.86
PHOTO_GAMMA = 1.15
PHOTO_SHARPEN = 0.6


def normalize_preprocess_mode(
    value: Optional[str],
    *,
    default: str = PREPROCESS_MODE_AUTO,
) -> str:
    text = str(value or '').strip().lower()
    if not text:
        return default if default in PREPROCESS_MODES or default == '' else PREPROCESS_MODE_AUTO
    return text if text in PREPROCESS_MODES else ''


def preprocess_mode_from_manifest(manifest: Optional[Dict[str, Any]]) -> str:
    """Return the persisted request mode; old manifests represent legacy scan mode."""
    preprocess = (manifest or {}).get('preprocess')
    if isinstance(preprocess, dict):
        mode = normalize_preprocess_mode(preprocess.get('requested_mode'), default='')
        if mode:
            return mode
    return PREPROCESS_MODE_SCAN


def preprocess_mode_matches_manifest(
    manifest: Optional[Dict[str, Any]],
    requested_mode: str,
) -> bool:
    normalized = normalize_preprocess_mode(requested_mode, default='')
    return bool(normalized and preprocess_mode_from_manifest(manifest) == normalized)


def _red_residual_mask_enabled(feedback_runtime=None) -> bool:
    from .feedback_runtime import frozen_environment
    raw = frozen_environment(feedback_runtime, RED_RESIDUAL_MASK_ENV, '1').strip().lower()
    return raw not in {'0', 'false', 'no', 'off'}


def _workflow_black_ink_image_enabled(feedback_runtime=None) -> bool:
    from .feedback_runtime import frozen_environment
    raw = frozen_environment(feedback_runtime, WORKFLOW_BLACK_INK_IMAGE_ENV)
    if raw is None:
        raw = frozen_environment(feedback_runtime, LEGACY_REVIEW_BLACK_INK_IMAGE_ENV, '1')
    raw = raw.strip().lower()
    return raw not in {'0', 'false', 'no', 'off'}


def build_teacher_mark_mask(
    img_bgr: np.ndarray,
    *,
    remove_pale_residuals: Optional[bool] = None,
    feedback_runtime=None,
) -> np.ndarray:
    """Locate red teacher marks and their light anti-aliased residuals.

    This is the established scan-mode implementation. Auto mode only selects
    it for neutral, uniformly white scanner output, preserving historical
    clean-image hashes for the fixed regression documents.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    red_mask = (
        cv2.inRange(hsv, RED_LOWER1, RED_UPPER1)
        | cv2.inRange(hsv, RED_LOWER2, RED_UPPER2)
    )
    if remove_pale_residuals is None:
        remove_pale_residuals = _red_residual_mask_enabled(feedback_runtime)
    if not remove_pale_residuals:
        return red_mask

    red_neighborhood = cv2.dilate(red_mask, RED_RESIDUAL_KERNEL, iterations=1)
    light_pixels = hsv[:, :, 2] >= RED_RESIDUAL_LIGHT_VALUE_MIN
    pale_residual_mask = np.where(
        (red_neighborhood > 0) & light_pixels,
        255,
        0,
    ).astype(np.uint8)
    return cv2.bitwise_or(red_mask, pale_residual_mask)


def remove_red_ink(
    img_bgr: np.ndarray,
    *,
    remove_pale_residuals: Optional[bool] = None,
    return_mask: bool = False,
    feedback_runtime=None,
):
    mask = build_teacher_mark_mask(
        img_bgr,
        remove_pale_residuals=remove_pale_residuals,
        feedback_runtime=feedback_runtime,
    )
    out = img_bgr.copy()
    out[mask > 0] = (255, 255, 255)
    if return_mask:
        return out, mask
    return out


def build_student_ink_workflow_image(
    cleaned_bgr: np.ndarray,
    *,
    mask_light_residuals: Optional[bool] = None,
    feedback_runtime=None,
) -> np.ndarray:
    """Build the established high-contrast image for scanner-produced pages."""
    if mask_light_residuals is None:
        mask_light_residuals = _workflow_black_ink_image_enabled(feedback_runtime)
    out = cleaned_bgr.copy()
    if not mask_light_residuals:
        return out
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV)
    out[hsv[:, :, 2] >= REVIEW_LIGHT_RESIDUAL_VALUE_MIN] = (255, 255, 255)
    return out


def _resize_for_metrics(img_bgr: np.ndarray, max_side: int = CLASSIFIER_MAX_SIDE) -> np.ndarray:
    height, width = img_bgr.shape[:2]
    scale = min(1.0, float(max_side) / max(height, width))
    if scale >= 1.0:
        return img_bgr
    return cv2.resize(
        img_bgr,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA,
    )


def analyze_page_capture(img_bgr: np.ndarray) -> Dict[str, Any]:
    """Compute cheap, layout-independent page metrics for scan/photo routing."""
    small = _resize_for_metrics(img_bgr)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    tile_p85: List[float] = []
    for tile_y in range(CLASSIFIER_TILE_COUNT):
        for tile_x in range(CLASSIFIER_TILE_COUNT):
            y0 = tile_y * height // CLASSIFIER_TILE_COUNT
            y1 = (tile_y + 1) * height // CLASSIFIER_TILE_COUNT
            x0 = tile_x * width // CLASSIFIER_TILE_COUNT
            x1 = (tile_x + 1) * width // CLASSIFIER_TILE_COUNT
            tile = gray[y0:y1, x0:x1]
            if tile.size:
                tile_p85.append(float(np.percentile(tile, 85)))
    tile_values = np.asarray(tile_p85 or [0.0], dtype=np.float32)
    white_fraction = float((hsv[:, :, 2] >= CLASSIFIER_WHITE_VALUE_MIN).mean())
    ink_fraction = float((gray < 220).mean())
    metrics = {
        'white_fraction': round(white_fraction, 4),
        'paper_p85': round(float(np.median(tile_values)), 2),
        'paper_field_range': round(
            float(np.percentile(tile_values, 90) - np.percentile(tile_values, 10)),
            2,
        ),
        'saturation_p90': round(float(np.percentile(hsv[:, :, 1], 90)), 2),
        'ink_fraction': round(ink_fraction, 4),
    }

    if ink_fraction <= CLASSIFIER_BLANK_INK_FRACTION_MAX:
        classification = 'blank'
        scan_votes = 4
    else:
        scan_votes = sum((
            white_fraction >= CLASSIFIER_SCAN_WHITE_FRACTION_MIN,
            metrics['paper_p85'] >= CLASSIFIER_SCAN_PAPER_P85_MIN,
            metrics['paper_field_range'] <= CLASSIFIER_SCAN_FIELD_RANGE_MAX,
            metrics['saturation_p90'] <= CLASSIFIER_SCAN_SATURATION_P90_MAX,
        ))
        if scan_votes >= 3:
            classification = PREPROCESS_MODE_SCAN
        elif scan_votes <= 1:
            classification = PREPROCESS_MODE_PHOTO
        else:
            classification = 'uncertain'

    metrics['scan_votes'] = int(scan_votes)
    metrics['classification'] = classification
    metrics['classification_confidence'] = (
        'high' if scan_votes in (0, 4) else 'medium' if scan_votes in (1, 3) else 'low'
    )
    return metrics


def _largest_component_fraction(mask: np.ndarray) -> float:
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if component_count <= 1:
        return 0.0
    return float(stats[1:, cv2.CC_STAT_AREA].max()) / float(mask.size)


def _legacy_mask_metrics(img_bgr: np.ndarray, feedback_runtime=None) -> Tuple[np.ndarray, Dict[str, float]]:
    mask = build_teacher_mark_mask(img_bgr, feedback_runtime=feedback_runtime)
    metrics = {
        'mask_fraction': round(float((mask > 0).mean()), 4),
        'largest_component_fraction': round(_largest_component_fraction(mask), 4),
    }
    return mask, metrics


def estimate_photo_paper(
    img_bgr: np.ndarray,
    *,
    work: int = PHOTO_PAPER_WORK_SIZE,
    radius_fraction: float = PHOTO_PAPER_RADIUS_FRACTION,
) -> np.ndarray:
    """Estimate local paper colour at low resolution and return a uint8 field."""
    height, width = img_bgr.shape[:2]
    scale = min(1.0, float(work) / max(height, width))
    small = cv2.resize(
        img_bgr,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA,
    )
    radius = max(6, int(round(max(small.shape[:2]) * radius_fraction)))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (2 * radius + 1, 2 * radius + 1),
    )
    background = cv2.morphologyEx(small, cv2.MORPH_CLOSE, kernel)
    background = cv2.GaussianBlur(background, (0, 0), radius * 0.6)
    background = cv2.resize(background, (width, height), interpolation=cv2.INTER_LINEAR)
    return np.maximum(background, 1).astype(np.uint8)


def photo_red_confidence(
    img_bgr: np.ndarray,
    paper_bgr: np.ndarray,
    *,
    beta: float = PHOTO_RED_BETA,
    floor: float = PHOTO_RED_FLOOR,
    chroma_blur: float = PHOTO_RED_CHROMA_BLUR,
    grow: int = PHOTO_RED_GROW,
) -> np.ndarray:
    """Estimate red ink from channel absorption relative to the local paper."""
    smoothed = cv2.GaussianBlur(img_bgr, (0, 0), chroma_blur)
    paper_f = paper_bgr.astype(np.float32)
    smooth_f = smoothed.astype(np.float32)
    absorbed_blue = paper_f[:, :, 0] - smooth_f[:, :, 0]
    absorbed_green = paper_f[:, :, 1] - smooth_f[:, :, 1]
    absorbed_red = paper_f[:, :, 2] - smooth_f[:, :, 2]
    absorbed_other = np.minimum(absorbed_green, absorbed_blue)
    confidence = (absorbed_other - absorbed_red) / np.maximum(beta * absorbed_other, 1e-6)
    confidence = np.clip(confidence, 0.0, 1.0)
    confidence[absorbed_other < floor] = 0.0
    if grow > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (2 * grow + 1, 2 * grow + 1),
        )
        confidence = cv2.dilate(confidence, kernel)
    return cv2.GaussianBlur(confidence, (0, 0), 0.6)


def build_photo_candidate(
    img_bgr: np.ndarray,
    *,
    black_point: float = PHOTO_BLACK_POINT,
    white_point: float = PHOTO_WHITE_POINT,
    gamma: float = PHOTO_GAMMA,
    sharpen: float = PHOTO_SHARPEN,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build a colour-preserving, scanner-like page without changing geometry."""
    paper = estimate_photo_paper(img_bgr)
    red_confidence = photo_red_confidence(img_bgr, paper)
    paper_red = paper[:, :, 2].astype(np.float32)
    observed_red = img_bgr[:, :, 2].astype(np.float32)
    ink_amount = (paper_red - observed_red) * (1.0 - red_confidence)
    reflectance = np.clip(
        1.0 - ink_amount / np.maximum(paper_red, 1.0),
        0.0,
        1.0,
    )
    tone = np.clip(
        (reflectance - black_point) / max(white_point - black_point, 1e-6),
        0.0,
        1.0,
    ) ** gamma
    if sharpen > 0:
        blurred = cv2.GaussianBlur(tone, (0, 0), 1.0)
        tone = np.clip(tone + sharpen * (tone - blurred), 0.0, 1.0)
    gray = (tone * 255.0 + 0.5).astype(np.uint8)

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1].astype(np.float32) * (1.0 - red_confidence)
    hsv[:, :, 1] = np.clip(saturation, 0, 255).astype(np.uint8)
    hsv[:, :, 2] = gray
    candidate = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return candidate, red_confidence, paper


def evaluate_photo_candidate(
    raw_bgr: np.ndarray,
    candidate_bgr: np.ndarray,
    red_confidence: np.ndarray,
    paper_bgr: np.ndarray,
) -> Dict[str, Any]:
    """Fail closed when photo enhancement removes non-red visual evidence."""
    raw_small = _resize_for_metrics(raw_bgr, max_side=1000)
    candidate_small = cv2.resize(
        candidate_bgr,
        (raw_small.shape[1], raw_small.shape[0]),
        interpolation=cv2.INTER_AREA,
    )
    confidence_small = cv2.resize(
        red_confidence,
        (raw_small.shape[1], raw_small.shape[0]),
        interpolation=cv2.INTER_AREA,
    )
    paper_small = cv2.resize(
        paper_bgr,
        (raw_small.shape[1], raw_small.shape[0]),
        interpolation=cv2.INTER_AREA,
    )
    raw_gray = cv2.cvtColor(raw_small, cv2.COLOR_BGR2GRAY)
    candidate_gray = cv2.cvtColor(candidate_small, cv2.COLOR_BGR2GRAY)
    paper_gray = cv2.cvtColor(paper_small, cv2.COLOR_BGR2GRAY)

    ink_strength = (
        paper_gray.astype(np.int16) - raw_gray.astype(np.int16)
    )
    # Below roughly 25 levels the signal is dominated by paper texture,
    # shadows and reverse-side show-through in the photographed fixtures.
    non_red_ink = (ink_strength >= 25) & (confidence_small < 0.25)
    ink_count = int(non_red_ink.sum())
    ink_retention = (
        float((candidate_gray[non_red_ink] <= 245).mean())
        if ink_count
        else 1.0
    )

    raw_x = cv2.Sobel(raw_gray, cv2.CV_32F, 1, 0, ksize=3)
    raw_y = cv2.Sobel(raw_gray, cv2.CV_32F, 0, 1, ksize=3)
    candidate_x = cv2.Sobel(candidate_gray, cv2.CV_32F, 1, 0, ksize=3)
    candidate_y = cv2.Sobel(candidate_gray, cv2.CV_32F, 0, 1, ksize=3)
    raw_gradient = cv2.magnitude(raw_x, raw_y)
    candidate_gradient = cv2.magnitude(candidate_x, candidate_y)
    gradient_threshold = max(12.0, float(np.percentile(raw_gradient, 80)))
    evidence_edges = (raw_gradient >= gradient_threshold) & (confidence_small < 0.25)
    edge_count = int(evidence_edges.sum())
    edge_retention = (
        float(
            (
                candidate_gradient[evidence_edges]
                >= np.maximum(6.0, raw_gradient[evidence_edges] * 0.20)
            ).mean()
        )
        if edge_count
        else 1.0
    )

    erased_non_red = non_red_ink & (candidate_gray >= 250)
    erased_component_fraction = _largest_component_fraction(erased_non_red)
    before_metrics = analyze_page_capture(raw_bgr)
    after_metrics = analyze_page_capture(candidate_bgr)
    before_range = float(before_metrics['paper_field_range'])
    after_range = float(after_metrics['paper_field_range'])
    background_ok = (
        before_range <= CLASSIFIER_SCAN_FIELD_RANGE_MAX
        or after_range <= max(12.0, before_range * 0.70)
    )
    ink_ok = ink_retention >= 0.82
    edge_ok = edge_retention >= 0.78
    erased_ok = erased_component_fraction <= 0.02
    reasons: List[str] = []
    if not background_ok:
        reasons.append('背景均匀度没有改善')
    if not ink_ok:
        reasons.append('非红笔迹保留不足')
    if not edge_ok:
        reasons.append('文字和图形边缘保留不足')
    if not erased_ok:
        reasons.append('出现大面积非红证据擦除')

    return {
        'passed': bool(background_ok and ink_ok and edge_ok and erased_ok),
        'background_ok': background_ok,
        'ink_retention': round(ink_retention, 4),
        'edge_retention': round(edge_retention, 4),
        'largest_erased_component_fraction': round(erased_component_fraction, 4),
        'before_paper_field_range': round(before_range, 2),
        'after_paper_field_range': round(after_range, 2),
        'red_confidence_fraction': round(float((red_confidence > 0.5).mean()), 4),
        'reasons': reasons,
    }


def preprocess_page_image(
    img_bgr: np.ndarray,
    requested_mode: str = PREPROCESS_MODE_AUTO,
    *, feedback_runtime=None,
) -> Tuple[np.ndarray, Dict[str, Any], Optional[np.ndarray]]:
    """Select and apply one preprocessing strategy to an already rendered page."""
    normalized_mode = normalize_preprocess_mode(requested_mode, default='')
    if not normalized_mode:
        raise ValueError('preprocess_mode 必须是 auto、scan、photo 或 off')

    capture = analyze_page_capture(img_bgr)
    classification = str(capture['classification'])
    effective_mode = normalized_mode
    if normalized_mode == PREPROCESS_MODE_AUTO:
        if classification == PREPROCESS_MODE_SCAN:
            effective_mode = PREPROCESS_MODE_SCAN
        elif classification == PREPROCESS_MODE_PHOTO:
            effective_mode = PREPROCESS_MODE_PHOTO
        else:
            effective_mode = PREPROCESS_MODE_OFF

    record: Dict[str, Any] = {
        'requested_mode': normalized_mode,
        'classification': classification,
        'classification_confidence': capture['classification_confidence'],
        'capture_metrics': capture,
        'effective_mode': effective_mode,
        'fallback_used': False,
        'fallback_reason': '',
    }
    photo_candidate: Optional[np.ndarray] = None

    if effective_mode == PREPROCESS_MODE_SCAN:
        teacher_mask, mask_metrics = _legacy_mask_metrics(img_bgr, feedback_runtime)
        record['legacy_mask'] = mask_metrics
        if (
            normalized_mode == PREPROCESS_MODE_AUTO
            and mask_metrics['mask_fraction'] > LEGACY_MASK_FRACTION_MAX
            and mask_metrics['largest_component_fraction'] > LEGACY_MASK_COMPONENT_MAX
        ):
            effective_mode = PREPROCESS_MODE_PHOTO
            record['effective_mode'] = effective_mode
            record['auto_reroute_reason'] = '扫描件去红掩膜异常，改用拍照增强'
        else:
            red_cleaned = img_bgr.copy()
            red_cleaned[teacher_mask > 0] = (255, 255, 255)
            return build_student_ink_workflow_image(red_cleaned, feedback_runtime=feedback_runtime), record, None

    if effective_mode == PREPROCESS_MODE_PHOTO:
        photo_candidate, red_confidence, paper = build_photo_candidate(img_bgr)
        quality = evaluate_photo_candidate(
            img_bgr,
            photo_candidate,
            red_confidence,
            paper,
        )
        record['photo_quality_gate'] = quality
        if quality['passed']:
            return photo_candidate, record, photo_candidate
        record['effective_mode'] = PREPROCESS_MODE_OFF
        record['fallback_used'] = True
        record['fallback_reason'] = '；'.join(quality['reasons']) or '拍照增强质量门禁未通过'
        return img_bgr.copy(), record, photo_candidate

    return img_bgr.copy(), record, None


def _write_png(path: str, img_bgr: np.ndarray) -> None:
    ok, buffer = cv2.imencode('.png', img_bgr)
    if not ok:
        raise RuntimeError(f'无法编码页面图: {path}')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buffer.tofile(path)


def load_preprocess_metadata(metadata_path: str) -> Dict[str, Any]:
    if not metadata_path or not os.path.isfile(metadata_path):
        return {}
    try:
        value = safe_json_load(metadata_path)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def preprocess_manifest_entry(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    value = metadata if isinstance(metadata, dict) else {}
    return {
        'schema_version': value.get('schema_version') or PREPROCESS_SCHEMA_VERSION,
        'requested_mode': value.get('requested_mode') or PREPROCESS_MODE_SCAN,
        'requested_mode_label': PREPROCESS_MODE_LABELS.get(
            value.get('requested_mode') or PREPROCESS_MODE_SCAN,
            '扫描件模式',
        ),
        'document_classification': value.get('document_classification') or 'unknown',
        'summary': value.get('summary') if isinstance(value.get('summary'), dict) else {},
        'updated_at': value.get('updated_at') or '',
    }


def _metadata_summary(page_records: List[Dict[str, Any]]) -> Tuple[str, Dict[str, int]]:
    effective_counts = {
        PREPROCESS_MODE_SCAN: 0,
        PREPROCESS_MODE_PHOTO: 0,
        PREPROCESS_MODE_OFF: 0,
    }
    classified_counts = {
        PREPROCESS_MODE_SCAN: 0,
        PREPROCESS_MODE_PHOTO: 0,
        'uncertain': 0,
        'blank': 0,
    }
    fallback_count = 0
    for record in page_records:
        effective = record.get('effective_mode')
        if effective in effective_counts:
            effective_counts[effective] += 1
        classified = record.get('classification')
        if classified in classified_counts:
            classified_counts[classified] += 1
        if record.get('fallback_used'):
            fallback_count += 1

    non_blank_scan = classified_counts[PREPROCESS_MODE_SCAN]
    non_blank_photo = classified_counts[PREPROCESS_MODE_PHOTO]
    non_blank_uncertain = classified_counts['uncertain']
    if non_blank_scan and not non_blank_photo and not non_blank_uncertain:
        document_classification = PREPROCESS_MODE_SCAN
    elif non_blank_photo and not non_blank_scan and not non_blank_uncertain:
        document_classification = PREPROCESS_MODE_PHOTO
    elif non_blank_scan or non_blank_photo or non_blank_uncertain:
        document_classification = 'mixed'
    else:
        document_classification = 'blank'
    summary = {
        'page_count': len(page_records),
        'scan_page_count': effective_counts[PREPROCESS_MODE_SCAN],
        'photo_page_count': effective_counts[PREPROCESS_MODE_PHOTO],
        'off_page_count': effective_counts[PREPROCESS_MODE_OFF],
        'fallback_page_count': fallback_count,
        'blank_page_count': classified_counts['blank'],
        'uncertain_page_count': classified_counts['uncertain'],
    }
    return document_classification, summary


def preprocess_pdf(
    pdf_path: str,
    raw_dir: str,
    clean_dir: str,
    subject: str,
    sample_id: str,
    page_numbers: Optional[Iterable[int]] = None,
    *,
    preprocess_mode: str = PREPROCESS_MODE_AUTO,
    metadata_path: Optional[str] = None,
    candidate_dir: Optional[str] = None,
    feedback_runtime=None,
) -> List[Dict[str, Any]]:
    """Render PDF pages and create the effective clean image for each page.

    ``off`` still renders the PDF but copies the rendered page byte-for-byte to
    ``clean``. Partial reruns update only their page records in the audit file.
    """
    if feedback_runtime is not None:
        preprocess_mode = feedback_runtime.dependencies['preprocessing']['mode']
    normalized_mode = normalize_preprocess_mode(preprocess_mode, default='')
    if not normalized_mode:
        raise ValueError('preprocess_mode 必须是 auto、scan、photo 或 off')

    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(clean_dir, exist_ok=True)
    selected_pages: Optional[Set[int]] = None
    if page_numbers is not None:
        selected_pages = {int(page) for page in page_numbers if int(page) > 0}

    existing_metadata = load_preprocess_metadata(metadata_path or '')
    if selected_pages is not None and existing_metadata:
        existing_mode = normalize_preprocess_mode(
            existing_metadata.get('requested_mode'),
            default=PREPROCESS_MODE_SCAN,
        )
        if existing_mode != normalized_mode:
            raise ValueError('切换预处理模式必须完整迭代整份作业')

    records_by_page: Dict[int, Dict[str, Any]] = {}
    if selected_pages is not None:
        for item in existing_metadata.get('pages') or []:
            if not isinstance(item, dict):
                continue
            try:
                page_num = int(item.get('page'))
            except (TypeError, ValueError):
                continue
            if page_num > 0:
                records_by_page[page_num] = item

    pages: List[Dict[str, Any]] = []
    zoom = DPI / 72
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(pdf_path) as document:
        total_pages = len(document)
        for page_index, page in enumerate(document, start=1):
            if selected_pages is not None and page_index not in selected_pages:
                continue
            name = page_filename(subject, sample_id, page_index)
            raw_path = os.path.join(raw_dir, name)
            clean_path = os.path.join(clean_dir, name)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pixmap.save(raw_path)

            img = cv2.imdecode(np.fromfile(raw_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise RuntimeError(f'无法读取PDF渲染页: {raw_path}')
            cleaned, record, photo_candidate = preprocess_page_image(
                img,
                requested_mode=normalized_mode,
                feedback_runtime=feedback_runtime,
            )
            record.update({
                'page': page_index,
                'filename': name,
            })

            if record['effective_mode'] == PREPROCESS_MODE_OFF:
                shutil.copyfile(raw_path, clean_path)
            else:
                _write_png(clean_path, cleaned)

            if photo_candidate is not None and candidate_dir:
                photo_dir = os.path.join(candidate_dir, PREPROCESS_MODE_PHOTO)
                candidate_path = os.path.join(photo_dir, name)
                _write_png(candidate_path, photo_candidate)
                record['photo_candidate_path'] = os.path.join(
                    'preprocess_candidates',
                    PREPROCESS_MODE_PHOTO,
                    name,
                ).replace('\\', '/')

            records_by_page[page_index] = record
            pages.append({
                'page': page_index,
                'page_count': total_pages,
                'raw_abs_path': raw_path,
                'clean_abs_path': clean_path,
                'filename': name,
                'preprocess': record,
            })

    ordered_records = [records_by_page[key] for key in sorted(records_by_page)]
    document_classification, summary = _metadata_summary(ordered_records)
    now = datetime.datetime.now().isoformat()
    metadata = {
        'schema_version': PREPROCESS_SCHEMA_VERSION,
        'requested_mode': normalized_mode,
        'requested_mode_label': PREPROCESS_MODE_LABELS[normalized_mode],
        'document_classification': document_classification,
        'summary': summary,
        'created_at': existing_metadata.get('created_at') or now,
        'updated_at': now,
        'pages': ordered_records,
    }
    if metadata_path:
        safe_json_dump(metadata_path, metadata)
    return pages
