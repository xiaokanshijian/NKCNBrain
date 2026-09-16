"""作业批改三维语义注册表（认知 / 课程标准 / 教育目标）。

改编自 yq 连续图片批改 v2.0 `src/semantic_config.py`（nkcn 自有副本，不依赖 yq）。

消费方：
- llm.py：Pass1 注入课标标签白名单；Pass2 注入认知三区定义 + 教育目标。
- hallucination_filter.py：校验 knowledge_point 字段。
- memory.py：error_type → importance 分级。
- profile.py：稳定盲区/内耗区纳入条件。
"""

from __future__ import annotations

import re as _re_ic

# ── 认知语义：三区 + 不确定 ────────────────────────────────────────────────
COGNITIVE_ZONES = {
    'blind_spot': {
        'label_cn': '盲区',
        'definition': '学生在整份作业中从未答对、且无近似尝试的知识点。表明该知识点在认知中不存在或完全错误。',
        'criterion': 'correct_count == 0 且 attempt_rate > 0',
        'json_value': 'blind_spot',
    },
    'friction_zone': {
        'label_cn': '内耗区',
        'definition': '学生已知该知识点（偶有答对），但仍反复犯同类错误（出错率>40%）。表明存在稳定的错误图式。',
        'criterion': 'wrong_count / total_count > 0.4 且 correct_count >= 1',
        'json_value': 'friction_zone',
    },
    'zpd': {
        'label_cn': '最近发展区',
        'definition': '学生在当前批改周期内有进步迹象，或该知识点出错原因为粗心/格式而非概念性错误。稍加引导可突破。',
        'criterion': 'error_type 主要为 format_error 或 careless，或近两页正确率上升',
        'json_value': 'zpd',
    },
    'uncertain': {
        'label_cn': '不确定',
        'definition': '模型识别置信度不足，不做三区判断。记录原因，待人工复核。',
        'criterion': '图像模糊、字迹无法辨认、跨页题目未完整',
        'json_value': 'uncertain',
    },
}


# ── error_type → importance 三档分级（HIGH/MID/LOW）────────────────────────
# 命中优先级：按列表顺序逐条 search()，首条命中即返回；未命中默认 MID。
ERROR_TYPE_IMPORTANCE_RULES: list[tuple[object, str]] = [
    # HIGH：概念性 / 知识性根本错误
    (_re_ic.compile(r'概念|公式|术语|法则|定义|含义|理解|混淆|不会|不懂'), 'HIGH'),
    (_re_ic.compile(r'concept|formula|definition|misconception', _re_ic.IGNORECASE), 'HIGH'),
    # LOW：粗心 / 格式 / 抄写
    (_re_ic.compile(r'粗心|笔误|抄错|漏写|多写|看错|格式|书写|大小写|标点'), 'LOW'),
    (_re_ic.compile(r'careless|typo|format|spelling', _re_ic.IGNORECASE), 'LOW'),
    # 其余落到 MID（计算错误、步骤错误、推理错误等）
]


def importance_of(error_type: str | None) -> str:
    """将自由文本 error_type 映射为 HIGH / MID / LOW。

    None / 空字符串 → MID（视为未标注，而非可忽略）。
    """
    if not error_type:
        return 'MID'
    for pat, level in ERROR_TYPE_IMPORTANCE_RULES:
        if pat.search(error_type):
            return level
    return 'MID'


_IMPORTANCE_RANK = {'LOW': 0, 'MID': 1, 'HIGH': 2}


def max_importance(levels: list[str]) -> str:
    """从一组 importance 中取最严重者（用于知识点级聚合）。"""
    if not levels:
        return 'MID'
    return max(levels, key=lambda x: _IMPORTANCE_RANK.get(x, 1))


# ── 课程标准语义：三科种子标签（subject → stage → domain → labels）─────────
# 学段映射（2022 义教课标，"六三"学制）：
#   stage 1 = 第一学段（1-2 年级）
#   stage 2 = 第二学段（3-4 年级）
#   stage 3 = 第三学段（5-6 年级）
# 英语按"级别"组织：stage 1/2 → 一级；stage 3 → 二级起步。
# 种子标签是 LLM 课标抽取的"优先复用锚点"，无需穷举；课标 PDF 提取会自动补全长尾。

_MATH_LABELS_BY_STAGE: dict[int, dict[str, list[str]]] = {
    1: {
        '数与代数': [
            'number_within_20', 'number_within_100', 'simple_add_sub',
            'add_sub_within_100', 'number_composition',
        ],
        '图形与几何': [
            'shape_recognition', 'position_direction', 'clock_reading',
        ],
        '统计与概率': [
            'simple_classify',
        ],
        '综合与实践': [
            'money_basic',
        ],
    },
    2: {
        '数与代数': [
            'big_number', 'mixed_operations', 'operation_law', 'algebra_expression',
            'fraction_basic', 'decimal_meaning', 'decimal_operations',
        ],
        '图形与几何': [
            'angle_measure', 'triangle_classify', 'quadrilateral_area',
        ],
        '统计与概率': [
            'bar_chart', 'line_chart',
        ],
        '综合与实践': [
            'number_pattern', 'word_problem',
        ],
    },
    3: {
        '数与代数': [
            'fraction_operations', 'decimal_multiply_divide', 'percentage',
            'ratio_proportion', 'simple_equation', 'negative_number',
        ],
        '图形与几何': [
            'circle_area', 'volume', 'surface_area', 'axial_symmetry',
        ],
        '统计与概率': [
            'average_median', 'possibility',
        ],
        '综合与实践': [
            'real_world_modeling',
        ],
    },
}

_CHINESE_LABELS_BY_STAGE: dict[int, dict[str, list[str]]] = {
    1: {
        '识字与写字': [
            'pinyin_full', 'basic_strokes', 'literacy_500',
        ],
        '阅读': [
            'simple_sentence', 'read_aloud',
        ],
        '习作': [
            'writing_warmup',
        ],
        '语文园地': [
            'punctuation_basic',
        ],
    },
    2: {
        '识字与写字': [
            'character_writing', 'stroke_order', 'similar_characters',
        ],
        '阅读': [
            'word_meaning', 'paragraph_summary', 'expression_style',
        ],
        '习作': [
            'sentence_rewrite', 'sentence_expand', 'imitation_writing',
        ],
        '语文园地': [
            'polyphonic_char', 'idiom', 'punctuation',
        ],
    },
    3: {
        '识字与写字': [
            'advanced_characters', 'calligraphy_basic',
        ],
        '阅读': [
            'paragraph_structure', 'rhetorical_devices', 'reading_inference',
            'classical_chinese_intro',
        ],
        '习作': [
            'essay_writing', 'narrative_writing',
        ],
        '语文园地': [
            'literary_quotation', 'discourse_logic',
        ],
    },
}

_ENGLISH_LABELS_BY_STAGE: dict[int, dict[str, list[str]]] = {
    # 1-2 年级英语在多数版本中尚未系统开课；占位最小集合，保留接口对称性
    1: {
        '语音': ['letter_recognition'],
        '词汇': ['greeting_vocab'],
    },
    2: {
        '语音': [
            'phonics', 'spelling_rule',
        ],
        '词汇': [
            'topic_vocabulary', 'occupation_vocab',
        ],
        '语法': [
            'be_verb', 'present_continuous', 'simple_present',
        ],
        '语篇': [
            'dialogue_comprehension', 'reading_comprehension',
        ],
        '写作': [
            'word_spelling', 'sentence_writing',
        ],
    },
    3: {
        '语音': [
            'stress_intonation',
        ],
        '词汇': [
            'extended_topic_vocab',
        ],
        '语法': [
            'past_tense', 'future_tense', 'comparatives',
        ],
        '语篇': [
            'reading_strategies', 'narrative_text',
        ],
        '写作': [
            'paragraph_writing',
        ],
    },
}

CURRICULUM_LABELS: dict[str, dict[int, dict[str, list[str]]]] = {
    'math': _MATH_LABELS_BY_STAGE,
    'chinese': _CHINESE_LABELS_BY_STAGE,
    'english': _ENGLISH_LABELS_BY_STAGE,
}

STAGE_TO_GRADE_BAND = {1: '1-2', 2: '3-4', 3: '5-6'}


# ── 教育目标语义 ───────────────────────────────────────────────────────────
EDUCATIONAL_GOALS = {
    'knowledge': {
        'label_cn': '知识传授',
        'definition': '学生是否掌握了该知识点的基本概念和运算规则',
        'impact_on_feedback': '判断 verdict，输出知识点错误的直接说明',
    },
    'competence': {
        'label_cn': '能力发展',
        'definition': '学生是否能够将知识迁移运用（如用字母表示数→列方程）',
        'impact_on_feedback': '识别 ZPD，给出下一步能力发展建议',
    },
    'core_literacy': {
        'label_cn': '核心素养',
        'definition': '数学课标：数感、运算能力、空间观念；语文：语言建构与运用；英语：语言交际能力',
        'impact_on_feedback': 'Pass2 报告的整体学情诊断应指向核心素养层面',
    },
    'process': {
        'label_cn': '认知过程',
        'definition': '关注学生解题过程是否完整、思路是否清晰，而非仅关注结果',
        'impact_on_feedback': 'partial 和 wrong 题目的批语应尽量还原学生的错误思路',
    },
}


# ── 便捷查询接口 ───────────────────────────────────────────────────────────
def _iter_stage_maps(subject: str, stage: int | None):
    """Yield {domain: [labels]} maps for the given subject (filtered by stage if set).

    stage=None 时合并所有学段（向后兼容旧调用）。未知 subject 返回空迭代器。
    """
    if subject not in CURRICULUM_LABELS:
        return
    by_stage = CURRICULUM_LABELS[subject]
    if stage is None:
        for s in sorted(by_stage.keys()):
            yield by_stage[s]
    else:
        if stage not in by_stage:
            return
        yield by_stage[stage]


def get_seed_labels(subject: str, stage: int | None = None) -> list[str]:
    """扁平化某科目的所有种子标签（去重保序）。未知科目返回空列表。

    stage=None（默认）时合并所有学段，向后兼容无 stage 参数的旧调用。
    """
    seen, out = set(), []
    for stage_map in _iter_stage_maps(subject, stage):
        for labels in stage_map.values():
            for label in labels:
                if label not in seen:
                    seen.add(label)
                    out.append(label)
    return out


def get_domain_for_label(subject: str, label: str, stage: int | None = None) -> str | None:
    """反查某 label 所属的课标领域；不存在返回 None。"""
    for stage_map in _iter_stage_maps(subject, stage):
        for domain, labels in stage_map.items():
            if label in labels:
                return domain
    return None


def get_label_domain_map(subject: str, stage: int | None = None) -> dict[str, str]:
    """构造 label → domain 的映射字典（last-wins 处理跨学段同名 label）。"""
    out: dict[str, str] = {}
    for stage_map in _iter_stage_maps(subject, stage):
        for domain, labels in stage_map.items():
            for label in labels:
                out[label] = domain
    return out
