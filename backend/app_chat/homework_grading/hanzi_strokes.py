"""Offline stroke-count lookup for common standardized Chinese characters."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)

COMPLEX_GLYPH_STROKE_THRESHOLD = 13
HIGH_COMPLEXITY_STROKE_THRESHOLD = 16

_DATA_PATH = os.path.join(
    os.path.dirname(__file__),
    'data',
    'hanzi_stroke_counts_tgh_17_0.json',
)


@lru_cache(maxsize=1)
def _load_stroke_counts() -> Dict[str, int]:
    try:
        with open(_DATA_PATH, 'r', encoding='utf-8') as file:
            payload = json.load(file)
        raw_counts = payload.get('counts') if isinstance(payload, dict) else None
        if not isinstance(raw_counts, dict):
            raise ValueError('missing counts object')
        counts: Dict[str, int] = {}
        for char, raw_count in raw_counts.items():
            if not isinstance(char, str) or len(char) != 1:
                continue
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                continue
            if count > 0:
                counts[char] = count
        return counts
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning('汉字笔画数据加载失败，复杂字 focused 覆盖将保持关闭: %s', exc)
        return {}


def get_hanzi_stroke_count(char: Any) -> Optional[int]:
    text = str(char or '')
    if len(text) != 1:
        return None
    return _load_stroke_counts().get(text)


def classify_hanzi_complexity(char: Any) -> Dict[str, Any]:
    count = get_hanzi_stroke_count(char)
    if count is None:
        level = 'unknown'
    elif count >= HIGH_COMPLEXITY_STROKE_THRESHOLD:
        level = 'high'
    elif count >= COMPLEX_GLYPH_STROKE_THRESHOLD:
        level = 'complex'
    else:
        level = 'normal'
    return {
        'stroke_count': count,
        'complexity_level': level,
    }
