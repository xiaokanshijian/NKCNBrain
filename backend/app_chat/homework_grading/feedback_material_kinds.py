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


def cross_page_max_pages(material_type: str) -> int:
    from .cross_page import MAX_PAGES_PER_GROUP
    if is_open_material(material_type):
        return OPEN_MAX_PAGES_PER_GROUP
    return MAX_PAGES_PER_GROUP


OPEN_MATERIAL_PROMPT = """
【开放式材料·作文/笔记｜覆盖本提示中的题目卷规则】本轮材料类型为作文或笔记（非传统作业/试卷题目卷）。
1. 允许没有离散小题：可将整页或跨页连续书写视为一个（或少数几个）开放任务单元，不要为凑题号而硬切碎。
2. 版面(detect)：优先定位书写区、段落、标题、批注区；跨页连续书写可标记 boundary.continues_* 与 cross_page=true，这只表示书写延续，不是“信息不足”。
3. 理解：忠实转写可见笔迹与结构；不要臆造标准答案题干。
4. 批改/反馈（最高优先级，覆盖下方任何「跨页必须 uncertain」「无唯一标准答案必须 uncertain」「习作/主观写作必须 uncertain」规则）：
   - 做理解性、开放式形成性评价（要点、表达、结构、就近发展区建议）。
   - correct_answer 可写简要评价要点或期望表现，允许没有唯一标准答案；不得因此把 verdict 设为 uncertain。
   - 跨页连续作文/笔记：只要本页可见书写足够做形成性评价，就必须给出 correct / partial / wrong，禁止仅因跨页、题号为 auto-*、题干不完整、无客观标准答案而设为 uncertain。
   - 仅当本页有效笔迹大面积不可辨（约≥50%）或完全空白无法评价时，才可用 uncertain / unanswered。
5. 若页面上确实出现传统习题，可按题目处理；本段规则只作用于作文/笔记材料，不得改变作业/试卷材料的处理方式。
""".strip()


# 仅注入 Pass2/三区批语链路，不注入版面/理解阶段
OPEN_PASS2_FEEDBACK_PROMPT = """
【开放式材料·作文/笔记·三区批语专项】本轮为作文或笔记，批语规则覆盖下方“已正确不写批语”“comment≤50字”等题目卷约束：
1. 必须对每一个书写单元输出批语，包括 verdict=correct 的单元；禁止因“已正确”而省略。
2. 优先整合抽取 understanding 与 correct_answer（尤其其中的形成性评价要点），写成精准、有价值的三区批语，禁止空泛套话。
3. 除非文本整体达到优秀/出色水平，教学口径上不要轻易按“完全正确、无需改进”收束；批语中须给出质量分（如 78/100）并点明 1 个亮点与 1 个可改进点。
4. comment 建议 80–160 字，可含分数；zone 仍从 blind_spot/friction_zone/zpd 中选最贴近者，优秀提升类多用 zpd。
5. 本规则只作用于作文/笔记，不得改变作业/试卷批语行为。
""".strip()
