"""作文/笔记仅在三区批改阶段的后处理；不改变版面/理解阶段产物生成逻辑。"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Set

from .feedback_material_kinds import is_open_material
from .utils import is_final_pass1_page_json, parse_page_num, safe_json_dump, safe_json_load

_EXCELLENCE_MARKERS = (
    '非常好', '十分出色', '非常出色', '优秀', '佳作', '典范', '几乎完美',
    '高水平', '精彩', '完成度很高', '完成度极高', '可作范文',
)


def _looks_excellent(question: Dict[str, Any]) -> bool:
    text = ' '.join(
        str(question.get(key) or '')
        for key in ('understanding', 'correct_answer', 'error_detail', 'error_type')
    )
    return any(marker in text for marker in _EXCELLENCE_MARKERS)


def refine_open_material_for_grading(
    pass1_dir: str,
    *,
    feedback_runtime=None,
    page_nums: Optional[Set[int]] = None,
) -> Dict[str, int]:
    """三区批改汇总前：作文/笔记少判全对，为后续批语保留形成性口径。

    不改动作业/试卷；不重跑无损版面/无损理解模型。
    """
    material = ''
    if feedback_runtime is not None:
        material = str((feedback_runtime.context or {}).get('material_type') or '')
    if not is_open_material(material) or not os.path.isdir(pass1_dir):
        return {'pages': 0, 'demoted': 0}

    demoted = 0
    pages = 0
    for name in os.listdir(pass1_dir):
        if not is_final_pass1_page_json(name):
            continue
        page_num = parse_page_num(name)
        if page_nums is not None and page_num not in page_nums:
            continue
        path = os.path.join(pass1_dir, name)
        try:
            data = safe_json_load(path)
        except Exception:
            continue
        questions = data.get('questions')
        if not isinstance(questions, list):
            continue
        changed = False
        pages += 1
        for question in questions:
            if not isinstance(question, dict):
                continue
            verdict = str(question.get('verdict') or '').strip()
            if verdict != 'correct':
                continue
            if _looks_excellent(question):
                continue
            question['verdict'] = 'partial'
            if not str(question.get('error_type') or '').strip():
                question['error_type'] = '形成性提升空间'
            demoted += 1
            changed = True
        if changed:
            safe_json_dump(path, data)
    return {'pages': pages, 'demoted': demoted}
