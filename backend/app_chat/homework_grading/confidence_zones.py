"""白/灰/黑区置信度阈值与颜色（后端渲染与前端展示共用逻辑）。

按学科三套阈值：语文为基准；数学略放宽白区；英语略收紧白区。
每一科也是三套阈值分别用于：无损版面(layout)、无损理解(understanding)、三区批改(grading)。
黑区阈值三科共用（与语文基准一致）。
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Tuple

ConfidenceMode = Literal['layout', 'understanding', 'grading']
SubjectCode = Literal['math', 'chinese', 'english']

# 语文基准（保持不变）
_CHINESE = {
    'layout': {'white': 89, 'black': 75},
    'understanding': {'white': 90, 'black': 82},
    'grading': {'white': 92, 'black': 83},
}
# 数学：白区门槛略降（相对语文 -2→-3 版面），批改/理解略收紧以恢复「英>语>数」
_MATH = {
    'layout': {'white': 86, 'black': 75},
    'understanding': {'white': 89, 'black': 82},
    'grading': {'white': 91, 'black': 83},
}
# 英语：白区门槛略升，避免白区过高，保留「英 > 语 > 数」
_ENGLISH = {
    'layout': {'white': 91, 'black': 75},
    'understanding': {'white': 92, 'black': 82},
    'grading': {'white': 94, 'black': 83},
}

SUBJECT_THRESHOLDS: Dict[SubjectCode, Dict[ConfidenceMode, Dict[str, int]]] = {
    'chinese': _CHINESE,
    'math': _MATH,
    'english': _ENGLISH,
}

# 兼容旧引用（= 语文基准）
LAYOUT_WHITE_THRESHOLD = _CHINESE['layout']['white']
LAYOUT_BLACK_THRESHOLD = _CHINESE['layout']['black']
UNDERSTANDING_WHITE_THRESHOLD = _CHINESE['understanding']['white']
UNDERSTANDING_BLACK_THRESHOLD = _CHINESE['understanding']['black']
GRADING_WHITE_THRESHOLD = _CHINESE['grading']['white']
GRADING_BLACK_THRESHOLD = _CHINESE['grading']['black']

ZONE_LABELS = {'white': '白区', 'gray': '灰区', 'black': '黑区'}

GRAY_SHADE_KEYS = ('gray_deep', 'gray_mid', 'gray_light')
GRAY_SHADE_LABELS = {
    'gray_deep': '深灰',
    'gray_mid': '中灰',
    'gray_light': '浅灰',
}

SHADE_ORDER = ('white', 'gray_deep', 'gray_mid', 'gray_light', 'black')
SHADE_DISPLAY = {
    'white': '白区',
    'gray_deep': '深灰',
    'gray_mid': '中灰',
    'gray_light': '浅灰',
    'black': '黑区',
}

# 灰区三档固定色（白/黑区不变）。BGR 与 RGB 相同。
# 框：无损版面/理解 PNG 边框 + 半透明填充
GRAY_BOX_BGR_BY_SHADE: Dict[str, Tuple[int, int, int]] = {
    'gray_deep': (92, 92, 92),
    'gray_mid': (128, 128, 128),
    'gray_light': (168, 168, 168),
}
# 圆：三区批改置信度小圆（实心）
GRAY_DOT_BGR_BY_SHADE: Dict[str, Tuple[int, int, int]] = {
    'gray_deep': (108, 108, 108),
    'gray_mid': (148, 148, 148),
    'gray_light': (188, 188, 188),
}
GRAY_BOX_RGB_BY_SHADE = {k: v[0] for k, v in GRAY_BOX_BGR_BY_SHADE.items()}
GRAY_DOT_RGB_BY_SHADE = {k: v[0] for k, v in GRAY_DOT_BGR_BY_SHADE.items()}

SUBJECT_LABELS = {
    'math': '数学',
    'chinese': '语文',
    'english': '英语',
}


def normalize_subject(subject: Any) -> SubjectCode:
    code = str(subject or '').strip().lower()
    if code in SUBJECT_THRESHOLDS:
        return code  # type: ignore[return-value]
    return 'chinese'


def get_thresholds(mode: ConfidenceMode = 'grading', subject: Any = 'chinese') -> Tuple[int, int]:
    subj = normalize_subject(subject)
    cfg = SUBJECT_THRESHOLDS[subj].get(mode) or SUBJECT_THRESHOLDS['chinese']['grading']
    return int(cfg['white']), int(cfg['black'])


def clamp_confidence(value: Any) -> Optional[int]:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, n))


def combined_recognition_understanding_confidence(question: Dict[str, Any]) -> Optional[int]:
    rec = clamp_confidence(question.get('recognition_confidence'))
    und = clamp_confidence(question.get('understanding_confidence'))
    if rec is None and und is None:
        return None
    if rec is None:
        return und
    if und is None:
        return rec
    return round((rec + und) / 2)


def confidence_zone(value: Any, mode: ConfidenceMode = 'grading', subject: Any = 'chinese') -> str:
    n = clamp_confidence(value)
    if n is None:
        return 'gray'
    white_th, black_th = get_thresholds(mode, subject=subject)
    if n >= white_th:
        return 'white'
    if n < black_th:
        return 'black'
    return 'gray'


def zone_label(zone: str) -> str:
    return ZONE_LABELS.get(zone, '灰区')


def zone_display(value: Any, mode: ConfidenceMode = 'grading', subject: Any = 'chinese') -> str:
    n = clamp_confidence(value)
    z = confidence_zone(n, mode=mode, subject=subject)
    if n is None:
        return '灰区（无置信度）'
    return f'{zone_label(z)}（{n}）'


def _gray_t(value: int, white_th: int, black_th: int) -> float:
    t = (value - black_th) / max(white_th - black_th - 1, 1)
    return max(0.0, min(1.0, t))


def gray_shade(value: Any, mode: ConfidenceMode = 'grading', subject: Any = 'chinese') -> str:
    n = clamp_confidence(value)
    if n is None:
        return 'gray_mid'
    zone = confidence_zone(n, mode=mode, subject=subject)
    if zone == 'white':
        return 'white'
    if zone == 'black':
        return 'black'
    white_th, black_th = get_thresholds(mode, subject=subject)
    t = _gray_t(n, white_th, black_th)
    if t < 1 / 3:
        return 'gray_deep'
    if t < 2 / 3:
        return 'gray_mid'
    return 'gray_light'


def gray_shade_confidence_range(mode: ConfidenceMode, shade: str, subject: Any = 'chinese') -> str:
    if shade not in GRAY_SHADE_KEYS:
        return '—'
    white_th, black_th = get_thresholds(mode, subject=subject)
    vals = [
        v for v in range(black_th, white_th)
        if gray_shade(v, mode=mode, subject=subject) == shade
    ]
    if not vals:
        return '—'
    if len(vals) == 1:
        return str(vals[0])
    return f'{min(vals)}–{max(vals)}'


def count_shade_distribution(
    values: list[int],
    mode: ConfidenceMode,
    subject: Any = 'chinese',
) -> Dict[str, int]:
    counts = {key: 0 for key in SHADE_ORDER}
    for value in values:
        counts[gray_shade(value, mode=mode, subject=subject)] += 1
    return counts


def shade_distribution_pct(
    values: list[int],
    mode: ConfidenceMode,
    subject: Any = 'chinese',
) -> Dict[str, float]:
    if not values:
        return {key: 0.0 for key in SHADE_ORDER}
    counts = count_shade_distribution(values, mode, subject=subject)
    n = len(values)
    return {key: counts[key] / n * 100.0 for key in SHADE_ORDER}


def shade_distribution_pct_mixed(
    records: list[tuple[int, str]],
    mode: ConfidenceMode,
) -> Dict[str, float]:
    if not records:
        return {key: 0.0 for key in SHADE_ORDER}
    counts = {key: 0 for key in SHADE_ORDER}
    for value, subject in records:
        counts[gray_shade(value, mode=mode, subject=subject)] += 1
    n = len(records)
    return {key: counts[key] / n * 100.0 for key in SHADE_ORDER}


def _gray_shade_from_value(value: int, white_th: int, black_th: int) -> str:
    t = _gray_t(value, white_th, black_th)
    if t < 1 / 3:
        return 'gray_deep'
    if t < 2 / 3:
        return 'gray_mid'
    return 'gray_light'


def _gray_box_bgr(value: int, white_th: int, black_th: int) -> Tuple[int, int, int]:
    shade = _gray_shade_from_value(value, white_th, black_th)
    return GRAY_BOX_BGR_BY_SHADE[shade]


def _gray_dot_bgr(value: int, white_th: int, black_th: int) -> Tuple[int, int, int]:
    shade = _gray_shade_from_value(value, white_th, black_th)
    return GRAY_DOT_BGR_BY_SHADE[shade]


def confidence_box_bgr(
    value: Any,
    mode: ConfidenceMode,
    subject: Any = 'chinese',
) -> Tuple[int, int, int]:
    n = clamp_confidence(value)
    if n is None:
        return (120, 120, 120)
    white_th, black_th = get_thresholds(mode, subject=subject)
    zone = confidence_zone(n, mode=mode, subject=subject)
    if zone == 'white':
        return (0, 200, 0)
    if zone == 'black':
        return (55, 55, 65)
    return _gray_box_bgr(n, white_th, black_th)


def confidence_dot_bgr(
    value: Any,
    mode: ConfidenceMode = 'grading',
    subject: Any = 'chinese',
) -> Tuple[int, int, int]:
    n = clamp_confidence(value)
    if n is None:
        return (190, 190, 190)
    white_th, black_th = get_thresholds(mode, subject=subject)
    zone = confidence_zone(n, mode=mode, subject=subject)
    if zone == 'white':
        return (245, 245, 245)
    if zone == 'black':
        return (45, 45, 55)
    return _gray_dot_bgr(n, white_th, black_th)


def gray_box_rgb(value: int, mode: ConfidenceMode, subject: Any = 'chinese') -> int:
    white_th, black_th = get_thresholds(mode, subject=subject)
    shade = _gray_shade_from_value(value, white_th, black_th)
    return GRAY_BOX_RGB_BY_SHADE[shade]


def gray_dot_rgb(value: int, mode: ConfidenceMode = 'grading', subject: Any = 'chinese') -> int:
    white_th, black_th = get_thresholds(mode, subject=subject)
    shade = _gray_shade_from_value(value, white_th, black_th)
    return GRAY_DOT_RGB_BY_SHADE[shade]
