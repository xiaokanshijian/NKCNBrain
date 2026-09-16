"""Detect and crop real Tianzige cells for Chinese glyph arbitration.

The detector deliberately fails closed.  It only returns cells backed by
visible horizontal and vertical grid lines; it never divides a question box
by the expected answer length or interpolates a missing separator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import cv2
import numpy as np

from app_chat.homework_grading.utils import normalize_position


_ASPECT_MIN = 0.65
_ASPECT_MAX = 1.35
_SIZE_CV_MAX = 0.20


def _read_gray(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f'cannot read image: {path}')
    return image


def _groups(indexes: np.ndarray, *, gap: int = 1) -> List[Tuple[int, int]]:
    result: List[List[int]] = []
    for raw in indexes.tolist():
        value = int(raw)
        if not result or value > result[-1][-1] + gap:
            result.append([value])
        else:
            result[-1].append(value)
    return [(values[0], values[-1]) for values in result]


def _coefficient_of_variation(values: Sequence[float]) -> float:
    if not values:
        return 1.0
    mean = float(np.mean(values))
    if mean <= 0:
        return 1.0
    return float(np.std(values) / mean)


def _horizontal_group_intervals(
    horizontal: np.ndarray,
    top_y: int,
    bottom_y: int,
    row_height: int,
) -> List[Tuple[int, int]]:
    top_edge = horizontal[max(0, top_y - 3):min(horizontal.shape[0], top_y + 4)]
    bottom_edge = horizontal[max(0, bottom_y - 3):min(horizontal.shape[0], bottom_y + 4)]
    coverage = np.any(top_edge > 0, axis=0) | np.any(bottom_edge > 0, axis=0)
    return [
        (left, right)
        for left, right in _groups(np.where(coverage)[0], gap=5)
        if right - left + 1 >= row_height * _ASPECT_MIN
    ]


def _best_real_group_cells(
    boundaries: Sequence[Tuple[int, float]],
    left: int,
    right: int,
    row_height: int,
) -> List[List[int]]:
    tolerance = max(5, int(round(row_height * 0.12)))
    candidates = [
        boundary for boundary in boundaries
        if left - tolerance <= boundary[0] <= right + tolerance
    ]
    if len(candidates) < 2:
        return []
    # The horizontal group endpoints are observed edges, so the selected path
    # must start and end at their nearest real vertical boundaries. Interior
    # false strokes may be skipped, but missing endpoints cannot be invented.
    start = min(range(len(candidates)), key=lambda index: abs(candidates[index][0] - left))
    end = min(range(len(candidates)), key=lambda index: abs(candidates[index][0] - right))
    if start >= end:
        return []
    candidates = candidates[start:end + 1]
    paths: List[List[int]] = []

    def walk(index: int, path: List[int]) -> None:
        if index == len(candidates) - 1:
            paths.append(path + [index])
            return
        x = candidates[index][0]
        for following in range(index + 1, len(candidates)):
            aspect = (candidates[following][0] - x) / max(1.0, float(row_height))
            if aspect > _ASPECT_MAX:
                break
            if aspect >= _ASPECT_MIN:
                walk(following, path + [index])

    walk(0, [])
    best_cells: List[List[int]] = []
    best_score = float('inf')
    for path in paths:
        widths = [
            candidates[path[index + 1]][0] - candidates[path[index]][0]
            for index in range(len(path) - 1)
        ]
        if not widths:
            continue
        width_cv = _coefficient_of_variation(widths)
        if width_cv > _SIZE_CV_MAX:
            continue
        geometry_error = float(np.mean([
            abs(width / max(1.0, float(row_height)) - 1.0)
            for width in widths
        ]))
        confidence = float(np.mean([candidates[index][1] for index in path]))
        score = geometry_error + width_cv - confidence * 0.05
        if score < best_score:
            best_score = score
            best_cells = [
                [candidates[path[index]][0], 0, candidates[path[index + 1]][0], row_height]
                for index in range(len(path) - 1)
            ]
    return best_cells


def detect_tianzige_cells(
    image_path: str,
    position: Any,
    expected_slots: int,
) -> Dict[str, Any]:
    """Return real grid-backed cells in absolute pixel coordinates."""
    audit: Dict[str, Any] = {
        'detector_version': 'tianzige_lines_v1',
        'status': 'roi_unavailable',
        'failure_reason': '',
        'cells': [],
    }
    normalized = normalize_position(position)
    if not normalized:
        audit['failure_reason'] = 'position_missing'
        return audit
    if expected_slots <= 0 or expected_slots > 40:
        audit['failure_reason'] = 'invalid_expected_slot_count'
        return audit

    try:
        image = _read_gray(image_path)
    except (OSError, ValueError) as exc:
        audit['failure_reason'] = f'image_unavailable:{exc}'
        return audit

    height, width = image.shape[:2]
    x1, y1, x2, y2 = normalized
    box = [
        int(round(x1 / 1000.0 * width)),
        int(round(y1 / 1000.0 * height)),
        int(round(x2 / 1000.0 * width)),
        int(round(y2 / 1000.0 * height)),
    ]
    box_width = max(1, box[2] - box[0])
    box_height = max(1, box[3] - box[1])
    pad = max(8, int(round(box_height * 0.25)))
    crop_box = [
        max(0, box[0] - pad),
        max(0, box[1] - pad),
        min(width, box[2] + pad),
        min(height, box[3] + pad),
    ]
    crop = image[crop_box[1]:crop_box[3], crop_box[0]:crop_box[2]]
    audit['question_box'] = box
    audit['search_box'] = crop_box
    if crop.size == 0:
        audit['failure_reason'] = 'empty_search_crop'
        return audit

    block_size = max(15, min(31, (min(crop.shape[:2]) // 8) * 2 + 1))
    binary = cv2.adaptiveThreshold(
        crop,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        block_size,
        12,
    )
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (max(25, int(round(box_height * 0.35))), 1),
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (1, max(25, int(round(box_height * 0.25)))),
    )
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)

    horizontal_projection = np.count_nonzero(horizontal, axis=1)
    min_horizontal_support = max(20, int(round(box_width * 0.06)))
    y_bands = _groups(np.where(horizontal_projection >= min_horizontal_support)[0], gap=2)
    y_lines = [int(round((top + bottom) / 2.0)) for top, bottom in y_bands]
    if len(y_lines) < 2:
        audit['failure_reason'] = 'horizontal_grid_lines_missing'
        return audit

    row_candidates: List[Tuple[int, int]] = []
    for top_index, top_y in enumerate(y_lines[:-1]):
        for bottom_y in y_lines[top_index + 1:]:
            row_height = bottom_y - top_y
            if row_height < box_height * 0.45 or row_height > box_height * 1.25:
                continue
            row_candidates.append((top_y, bottom_y))

    if not row_candidates:
        audit['failure_reason'] = 'grid_row_pair_missing'
        return audit
    top_y, bottom_y = max(row_candidates, key=lambda item: item[1] - item[0])
    row_height = bottom_y - top_y
    section = vertical[max(0, top_y - 3):min(vertical.shape[0], bottom_y + 4)]
    projection = np.count_nonzero(section, axis=0)
    min_vertical_support = max(20, int(round(row_height * 0.15)))
    bands = _groups(np.where(projection >= min_vertical_support)[0], gap=2)
    boundaries: List[Tuple[int, float]] = []
    for local_left, local_right in bands:
        center = int(round((local_left + local_right) / 2.0))
        top_band = binary[max(0, top_y - 4):min(binary.shape[0], top_y + 5), local_left:local_right + 1]
        bottom_band = binary[max(0, bottom_y - 4):min(binary.shape[0], bottom_y + 5), local_left:local_right + 1]
        score = float(np.max(projection[local_left:local_right + 1]) / max(1, row_height))
        if np.any(top_band) and np.any(bottom_band) and score >= 0.50:
            boundaries.append((center, min(1.0, score)))
    # Horizontal edges define the observed groups. Each group must be tiled
    # from its real left endpoint to its real right endpoint using detected
    # vertical boundaries. False handwriting strokes may be skipped, while a
    # missing group endpoint or divider makes that group fail closed.
    audit['vertical_boundaries'] = [
        {'x': int(position + crop_box[0]), 'score': round(float(score), 4)}
        for position, score in boundaries
    ]
    group_intervals = _horizontal_group_intervals(horizontal, top_y, bottom_y, row_height)
    audit['horizontal_groups'] = [
        [int(left + crop_box[0]), int(right + crop_box[0])]
        for left, right in group_intervals
    ]
    cells_local: List[List[int]] = []
    group_counts: List[int] = []
    for left, right in group_intervals:
        group_cells = _best_real_group_cells(boundaries, left, right, row_height)
        group_counts.append(len(group_cells))
        for cell in group_cells:
            cell[1] = top_y
            cell[3] = bottom_y
        cells_local.extend(group_cells)
    audit['detected_group_counts'] = group_counts
    boundary_scores = [score for _position, score in boundaries]

    if len(cells_local) != expected_slots:
        audit['failure_reason'] = 'detected_slot_count_mismatch'
        audit['detected_slot_count'] = len(cells_local)
        audit['expected_slot_count'] = expected_slots
        return audit
    widths = [cell[2] - cell[0] for cell in cells_local]
    heights = [cell[3] - cell[1] for cell in cells_local]
    width_cv = _coefficient_of_variation(widths)
    height_cv = _coefficient_of_variation(heights)
    audit['width_cv'] = round(width_cv, 4)
    audit['height_cv'] = round(height_cv, 4)
    if width_cv > _SIZE_CV_MAX or height_cv > _SIZE_CV_MAX:
        audit['failure_reason'] = 'inconsistent_cell_sizes'
        return audit

    cells = [
        [
            cell[0] + crop_box[0],
            cell[1] + crop_box[1],
            cell[2] + crop_box[0],
            cell[3] + crop_box[1],
        ]
        for cell in cells_local
    ]
    median_width = float(np.median([cell[2] - cell[0] for cell in cells]))
    group_break_slots = [
        index + 1
        for index in range(len(cells) - 1)
        if cells[index + 1][0] - cells[index][2] > median_width * 0.30
    ]
    audit.update({
        'status': 'available',
        'failure_reason': '',
        'expected_slot_count': expected_slots,
        'detected_slot_count': len(cells),
        'cells': cells,
        'group_break_slots': group_break_slots,
        'row_box': [
            min(cell[0] for cell in cells),
            min(cell[1] for cell in cells),
            max(cell[2] for cell in cells),
            max(cell[3] for cell in cells),
        ],
        'confidence': round(float(np.mean(boundary_scores)) if boundary_scores else 0.0, 4),
    })
    return audit


def _write_png(path: str, image: np.ndarray) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode('.png', image)
    if not ok:
        raise ValueError(f'cannot encode image: {path}')
    encoded.tofile(path)


def crop_tianzige_targets(
    image_path: str,
    roi: Dict[str, Any],
    target_slots: Sequence[int],
    output_prefix: str,
) -> Dict[str, Any]:
    """Persist only target-cell crops; no row image is generated."""
    if roi.get('status') != 'available':
        raise ValueError('tianzige ROI is unavailable')
    image_data = np.fromfile(image_path, dtype=np.uint8)
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'cannot read image: {image_path}')
    height, width = image.shape[:2]
    cells = [list(map(int, cell)) for cell in roi.get('cells') or []]
    if not cells:
        raise ValueError('tianzige ROI has no cells')

    target_paths: List[Dict[str, Any]] = []
    for slot in target_slots:
        if slot <= 0 or slot > len(cells):
            raise ValueError(f'invalid target slot: {slot}')
        left, top, right, bottom = cells[slot - 1]
        cell_width = right - left
        cell_height = bottom - top
        pad_x = int(round(cell_width * 0.12))
        pad_y = int(round(cell_height * 0.12))
        if slot > 1:
            previous = cells[slot - 2]
            previous_midline = int(round((previous[0] + previous[2]) / 2.0))
            pad_x = min(pad_x, max(0, left - previous_midline))
        if slot < len(cells):
            following = cells[slot]
            following_midline = int(round((following[0] + following[2]) / 2.0))
            pad_x = min(pad_x, max(0, following_midline - right))
        target_box = [
            max(0, left - pad_x),
            max(0, top - pad_y),
            min(width, right + pad_x),
            min(height, bottom + pad_y),
        ]
        target = image[target_box[1]:target_box[3], target_box[0]:target_box[2]]
        target = cv2.resize(target, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_LANCZOS4)
        target_path = f'{output_prefix}.slot{slot}.png'
        _write_png(target_path, target)
        target_paths.append({'slot': int(slot), 'path': target_path, 'box': target_box})
    return {'targets': target_paths}


def crop_tianzige_evidence(
    image_path: str,
    roi: Dict[str, Any],
    target_slots: Sequence[int],
    output_prefix: str,
) -> Dict[str, Any]:
    """Persist target-cell and row crops for auditable model requests."""
    if roi.get('status') != 'available':
        raise ValueError('tianzige ROI is unavailable')
    image_data = np.fromfile(image_path, dtype=np.uint8)
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'cannot read image: {image_path}')
    height, width = image.shape[:2]
    cells = [list(map(int, cell)) for cell in roi.get('cells') or []]
    if not cells:
        raise ValueError('tianzige ROI has no cells')

    median_height = float(np.median([cell[3] - cell[1] for cell in cells]))
    row_left, row_top, row_right, row_bottom = map(int, roi['row_box'])
    row_pad_y = int(round(median_height * 0.10))
    row_box = [
        max(0, row_left),
        max(0, row_top - row_pad_y),
        min(width, row_right),
        min(height, row_bottom + row_pad_y),
    ]
    row = image[row_box[1]:row_box[3], row_box[0]:row_box[2]]
    row = cv2.resize(row, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_LANCZOS4)
    row_path = f'{output_prefix}.row.png'
    _write_png(row_path, row)

    target_paths: List[Dict[str, Any]] = []
    for slot in target_slots:
        if slot <= 0 or slot > len(cells):
            raise ValueError(f'invalid target slot: {slot}')
        left, top, right, bottom = cells[slot - 1]
        cell_width = right - left
        cell_height = bottom - top
        pad_x = int(round(cell_width * 0.12))
        pad_y = int(round(cell_height * 0.12))
        if slot > 1:
            previous = cells[slot - 2]
            previous_midline = int(round((previous[0] + previous[2]) / 2.0))
            pad_x = min(pad_x, max(0, left - previous_midline))
        if slot < len(cells):
            following = cells[slot]
            following_midline = int(round((following[0] + following[2]) / 2.0))
            pad_x = min(pad_x, max(0, following_midline - right))
        target_box = [
            max(0, left - pad_x),
            max(0, top - pad_y),
            min(width, right + pad_x),
            min(height, bottom + pad_y),
        ]
        target = image[target_box[1]:target_box[3], target_box[0]:target_box[2]]
        target = cv2.resize(target, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_LANCZOS4)
        target_path = f'{output_prefix}.slot{slot}.png'
        _write_png(target_path, target)
        target_paths.append({'slot': int(slot), 'path': target_path, 'box': target_box})
    return {'row_path': row_path, 'row_box': row_box, 'targets': target_paths}
