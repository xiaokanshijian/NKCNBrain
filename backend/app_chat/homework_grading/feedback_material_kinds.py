"""材料品类常量。开放式品类与题目型品类分流，避免改动作业/试卷既有行为。"""

# 题目型（既有批改主路径，行为必须保持不变）
QUESTION_MATERIALS = frozenset({'homework', 'exam'})

# 开放式（作文/笔记：可无离散题目、可连续多页）
OPEN_MATERIALS = frozenset({'notes', 'composition'})

# 可进批改通道（含 unknown：未注明时仍可准入，由后置观察提示）
GRADING_ELIGIBLE_MATERIALS = QUESTION_MATERIALS | OPEN_MATERIALS | frozenset({'unknown'})

# 作文/笔记跨页组上限（作业/试卷仍用 cross_page.MAX_PAGES_PER_GROUP=3）
OPEN_MAX_PAGES_PER_GROUP = 8


def is_question_material(material_type: str) -> bool:
    return (material_type or '') in QUESTION_MATERIALS


def is_open_material(material_type: str) -> bool:
    return (material_type or '') in OPEN_MATERIALS


def is_grading_eligible_material(material_type: str) -> bool:
    return (material_type or '') in GRADING_ELIGIBLE_MATERIALS


def default_preprocess_mode(material_type: str) -> str:
    """开放材料首先保留原色；题目卷继续沿用自动预处理。"""
    return 'off' if is_open_material(material_type) else 'auto'


def cross_page_max_pages(material_type: str) -> int:
    from .cross_page import MAX_PAGES_PER_GROUP
    if is_open_material(material_type):
        return OPEN_MAX_PAGES_PER_GROUP
    return MAX_PAGES_PER_GROUP
