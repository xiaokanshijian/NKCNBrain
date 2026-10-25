"""Prompt builders for homework grading passes.

Keep long prompt text aligned with yq/连续图片批改/src/prompts.py unless an nkcn
adapter requires explicit grade/stage or workspace differences.
"""

import json
from typing import Any, Dict, List, Optional

from app_chat.homework_grading.curriculum import (
    load_curriculum_entries,
    load_curriculum_labels,
)
from app_chat.homework_grading.semantic_config import (
    COGNITIVE_ZONES,
    EDUCATIONAL_GOALS,
    get_seed_labels,
)
from app_chat.homework_grading.question_type import (
    is_chinese_pronunciation_selection_question,
)
from app_chat.homework_grading.subject_prompt_rules import (
    CHINESE_PRONUNCIATION_SELECTION_GRADE_RULES,
    CHINESE_SENTENCE_CONTRACTION_PAGE_RULES,
    ENGLISH_PAGE15_VISUAL_TRANSCRIPTION_LOCK,
    ENGLISH_PARENTHESIZED_CHOICE_SLOT_GRADE_RULES,
    MATH_OPERATION_LAW_FULL_NAME_GRADE_RULES,
    pass1_detect_subject_suffix,
    pass1_grade_subject_suffix,
    pass1_review_subject_suffix,
)
from app_chat.homework_grading.special_cases import (
    ACTION_ENGLISH_VISUAL_TRANSCRIPTION_LOCK,
    document_special_case_enabled,
)


# ── Pass1 共性：印刷/手写区分 + 涂改痕迹处理 ─────────────────────────────────
PASS1_PRINT_HANDWRITING_RULES = '''
【印刷体 vs 手写体（必须区分）】
1. 印刷体：题干、题号、选项、表格头、页眉页脚、分值说明等，通常字形规整、墨色一致。
2. 手写体：学生作答、演算、填空、圈选标记等，笔迹风格与印刷体明显不同。
3. 印刷与手写贴得很近、甚至部分重叠时，**以笔迹风格与墨色区分**，不要把印刷题干/印刷数字误当成学生答案或手写演算。
4. 严禁出现「学生抄错印刷数字」类误判，若其实是把印刷体当成了手写体，应重新识别；仍无法区分时 verdict 设为 uncertain。

【涂改 / 删除线 / 涂抹（以最终保留为准）】
1. 学生写错后用横线划掉、涂黑、反复涂抹的内容，视为**已作废**，不得计入最终答案。
2. student_answer 只转写**最终保留、未被划掉**的有效作答；不要把删除线内的内容写进 student_answer。
3. 判分时只依据最终保留内容；不得因已划掉的内容判错（例如划掉了「×36」保留了「a-b/18」，应按后者理解）。
4. 若涂改严重、无法判断学生最终意图，verdict 设为 uncertain，并在 error_type 中说明「涂改后意图不明」。'''

PASS1_DETECT_PRINT_HANDWRITING_RULES = '''
【版面检测时的印刷/手写区分】
1. position 必须框选**该小题全部学生手写作答**（见下方「position 完整性」），不要把印刷题干、印刷选项、印刷表格主体框进作答区。
2. 印刷题干与手写答案贴得很近时，以笔迹风格区分；**完整包住手写区优先于框得窄小**。
3. stem_excerpt 只摘**该小题自身**印刷题干前 20 字左右，不要把学生手写演算或已划掉内容写进 stem_excerpt。
4. 若某题只有印刷题干、未见明确手写作答，仍输出该题 id，position 框选该小题手写作答应出现的位置（可为空作答区）。

【大题与小题归属（小题间距较远时必须做）】
1. 同一道大题（如「5. ……」）下含 (1)(2)(3) 或 5-1、5-2 等小题时，**每个小题单独一条** questions 记录。
2. parent_group_id：所属大题号（如 "5"）；无父题的独立小题填 ""。
3. parent_stem_excerpt：该大题**共用印刷题干/条件/图表说明**前约 40 字（如应用题共同背景）；让小题离大题题干较远时，后续批改仍能理解题意。
4. stem_excerpt：仅该**小题自身**印刷题干（如「(2) 篱笆的长度是多少米」），不要与大题共用题干混淆。
5. 后面的小题即使离大题印刷题干很远，也**必须**填写 parent_group_id 与 parent_stem_excerpt，禁止把小题当成无上下文的孤立题。

【position 完整性（极易出错，务必遵守）】
1. position 必须**完整包住该小题全部手写作答**，包括：演算过程、最终算式/表达式、单位、以及「答：……」完整语句。
2. **严禁**只框第一行算式而漏掉下方「答：……」——算式与答句应**同框**为一个 position（取包住全部相关手写内容的最小外接矩形）。
3. 多行作答、分步计算、竖式，均视为同一小题的一个 position；纵向可适度放宽直至包住最末一行手写内容。
4. 可在手写内容四周留少量边距（约页高 1–3%），但**不得**为求窄而截断下方「答：」行。
5. 不要把印刷大题共用题干框进 position；但若「答：」句为手写，必须框入。'''


PASS1_SYSTEM_BASE = '''你是一位中小学作业批改老师。仅凭自身学科常识判断对错，无需参考答案。

任务：对输入的单页作业扫描图，识别页面上所有题目，判断每道题学生作答的对错，输出**纯 JSON 对象**（不加 Markdown 代码围栏，不加任何前缀或后缀）。

verdict 取值严格限定为以下五种：
- correct   ——完全正确
- wrong     ——明显错误
- partial   ——部分正确（多空题中部分填对）
- unanswered——学生未作答（空白）
- uncertain ——无法判断（字迹不清或题意模糊）

position 使用归一化坐标，相对图像宽高均映射到 0–1000，格式 [x_min, y_min, x_max, y_max]，定位**学生作答区域**（不是整道题的区域）。

子题号格式：主题号-子题号（如 3-1）。识别不到题号则按出现顺序编 auto-1、auto-2……

correct_answer 不确定时填 null，同时将 verdict 设为 uncertain。

输出 JSON schema（严格遵守，字段名不可改动）：
{
  "page": <整数，页码>,
  "subject": "<math|chinese|english>",
  "boundary": {
    "continues_from_prev": false,
    "description_prev": null,
    "continues_to_next": false,
    "description_next": null
  },
  "questions": [
    {
      "id": "3-1",
      "stem_excerpt": "题干前 20 字，便于人工核对",
      "parent_group_id": "3",
      "parent_stem_excerpt": "大题共用印刷题干前约40字，无则填\"\"",
      "student_answer": "学生作答原文（手写转写）",
      "correct_answer": "参考答案或 null",
      "verdict": "correct|wrong|partial|unanswered|uncertain",
      "error_type": "可空字符串，描述错误类型",
      "knowledge_point": "可空字符串，对应知识点",
      "position": [x_min, y_min, x_max, y_max],
      "cross_page": false,
      "cross_page_note": null,
      "is_application_major_problem": false,
      "final_unit_requirement": "required|forbidden|optional",
      "recurrence_hint": "new|recurring|na"
    }
  ]
}

【recurrence_hint 字段说明】（用于后续 L5 时序筛分）
- `recurring`：本题错误与「前序练习概要」中列出的高频错误 KP 一致，且错因/知识点与之前同类。
- `new`：本题首次出现该 KP 错误，或错因明显不同于既往同类。
- `na`：verdict 为 correct / 没有前序时序上下文 / 无法判断与前序的关系。
未注入「前序练习概要」时，所有题目一律填 `na`。**严禁因前序错误就主观判定本题错误**——
recurrence_hint 仅用于刻画错误的时序关系，不得改变 verdict 的客观判断。

【跨页题目识别要求】
大多数页面的题目是完整的，无需特殊处理。但请注意以下情形：

1. 若本页顶部明显是某道题或某段材料的延续（例如：阅读短文从中间开始、题目编号明显不是本页的第一题、选项列表缺少前文题干），
   请设置 boundary.continues_from_prev = true，
   并在 boundary.description_prev 中用一句话描述缺失的内容。
   对受影响的题目设置 cross_page = true，verdict 设为 "uncertain"，
   在 cross_page_note 中简述无法判断的原因。

2. 若本页底部明显有题目或材料被截断（例如：题干句子不完整、选项未列完、页面底部出现"（接下页）"字样），
   请设置 boundary.continues_to_next = true，
   并在 boundary.description_next 中用一句话描述被截断的内容。
   对受影响的题目同样设置 cross_page = true，verdict 设为 "uncertain"。

3. 若本页内容完整，则 boundary.continues_from_prev 和
   boundary.continues_to_next 均设为 false，description 字段设为 null。
   此时无需设置任何题目的 cross_page 字段（默认 false，可省略）。

4. 不要为了使用这个机制而强行标记跨页——只在你确实看到截断证据时才标记。
''' + PASS1_PRINT_HANDWRITING_RULES + '''

严格输出 JSON 对象，不含任何 Markdown 围栏或额外文字。'''


# ── Pass1 两阶段：阶段 A 仅版面检测（坐标 + 题号 + 跨页标记）────────────────
PASS1_DETECT_SYSTEM_BASE = '''你是一位中小学作业版面分析助手。请对输入的单页作业扫描图，识别页面上所有独立题目，并定位每道题**学生作答区域**的归一化坐标。

本阶段**只做版面检测，不做批改、不转写学生答案、不判断对错**。

position 使用归一化坐标，相对图像宽高均映射到 0–1000，格式 [x_min, y_min, x_max, y_max]，定位**学生作答区域**（不是整道题的区域）。

子题号格式：主题号-子题号（如 3-1）。识别不到题号则按出现顺序编 auto-1、auto-2……

输出 JSON schema（严格遵守，字段名不可改动）：
{
  "page": <整数，页码>,
  "subject": "<math|chinese|english>",
  "page_header": "<页眉/篇目标题，可空字符串>",
  "boundary": {
    "continues_from_prev": false,
    "description_prev": null,
    "continues_to_next": false,
    "description_next": null
  },
  "questions": [
    {
      "id": "3-1",
      "parent_group_id": "3",
      "parent_stem_excerpt": "大题共用印刷题干前约40字，无则填\"\"",
      "stem_excerpt": "该小题印刷题干前 20 字",
      "position": [x_min, y_min, x_max, y_max],
      "answer_slots": [],
      "cross_page": false,
      "cross_page_note": null,
      "layout_confidence": 75,
      "is_application_major_problem": false,
      "final_unit_requirement": "required|forbidden|optional"
    }
  ]
}

answer_slots 是可选版面扩展字段：仅当后续科目规则明确要求时输出；其它题目省略该字段，不要填占位内容。

【layout_confidence 字段说明】
- 整数 0–100，表示本题**版面识别划分**的综合置信度（百分制）。
- 须综合考虑：position 坐标是否可信、是否跨页/页首页尾截断、手写作答是否潦草或涂改严重、题型是否特殊（连线/画线/操作题等）。
- **校准原则（务必遵守，禁止整体偏高）**：
  · 仅当版面框选非常清晰、题界明确、无跨页疑虑、字迹工整清晰时，才可给 90 以上。
  · 跨页题、页首/页尾题、涂改多、书写排版一般、连线/特殊题型、坐标存疑：通常 75–90。
  · 严重潦草或书写排版及涂改很乱，框选明显可能不准：60–75。
  · 同一页各题 layout_confidence **须有差异**，不要全部 85/90/95。
- 不同题目的 layout_confidence 应有合理差异，不要全部给高分。

【is_application_major_problem 字段说明】
- 布尔值，判断该题是否属于数学应用题大题（非填空题）下的题目；其它科目或不确定时填 false。
- 应用题大题是指题干给出真实情境、数量关系、图表条件或一段共同背景，需要学生列式/推理解决的问题；其 (1)(2)(3) 等小题也继承 true。
- 只要题型是填空式作答，即使有生活情境或图表条件，也填 false；包括看图填空、表格填空、公式填空、括号内填空（如“m=( )”“( )元”）。
- 口算、脱式计算、化简、选择、判断、单纯单位换算或纯表达式练习，填 false。

【final_unit_requirement 字段说明】
- 每题必填；非数学题填 optional。为兼容历史字段，它描述单位在不同作答区域中的评分要求，不替代 is_application_major_problem，也不取消应用题最终答话要求。
- required：最终答案必须带与题意兼容的单位；例如普通求长度、面积、时间、钱数、物品数量的应用题，且不是下面的代入求值型小问。
- forbidden：重点识别应用题中“前一小问先列含字母的式子，后一小问给出当 x=... 时再代入求值”的小问。它只要求计算过程末值写纯数；最终“答：……”中的数量仍必须带与题意兼容的单位、量词或“倍”等关系词。例如过程写“=300”，答话写“平均每月生产300个”。
- optional：单位不是评分点、题目只要求列式/表达意义、填空处已印单位，或不能确定是否要求单位。
- 同一道应用大题的不同小问可以不同：列式小问通常 optional/required；“当字母=数时”的代入求值小问填 forbidden，但只约束计算过程末值。不得因为题目属于应用题就把所有小问都填 required。

【跨页题目识别要求】
1. 若本页顶部/底部存在题目或材料截断，按 PASS1 跨页规则设置 boundary 与 cross_page。
2. 对 cross_page = true 的题目，仅标记位置与截断说明，本阶段不判断对错。
3. 不要为了使用跨页机制而强行标记——只在你确实看到截断证据时才标记。
''' + PASS1_DETECT_PRINT_HANDWRITING_RULES + '''

严格输出 JSON 对象，不含任何 Markdown 围栏或额外文字。'''


# ── Pass1 两阶段：阶段 B 仅识别 + 批改（题号/坐标已给定，不得改动）──────────
PASS1_GRADE_SYSTEM_BASE = '''你是一位中小学作业批改老师。仅凭自身学科常识判断对错，无需参考答案。

本阶段会同时提供：
1. 单页作业扫描图；
2. 已由上一阶段给出的题目清单（含 id、parent_group_id、parent_stem_excerpt、stem_excerpt、position、answer_slots、cross_page、final_unit_requirement 等）。

你的任务：**仅**对清单中的每道题完成手写转写与对错判定。**不得修改、增删题目，不得改动 id / parent_group_id / parent_stem_excerpt / position / answer_slots / cross_page / cross_page_note / stem_excerpt / is_application_major_problem / final_unit_requirement。**

批改时请综合理解：**parent_stem_excerpt（大题共用条件）+ stem_excerpt（小题题干）+ 图像中手写作答**。小题离大题印刷题干较远时，必须依据 parent_stem_excerpt 理解题意，不得忽略大题背景。

verdict 取值严格限定为以下五种：
- correct   ——完全正确
- wrong     ——明显错误
- partial   ——部分正确（多空题中部分填对）
- unanswered——学生未作答（空白）
- uncertain ——无法判断（字迹不清或题意模糊）

correct_answer 不确定时填 null，同时将 verdict 设为 uncertain。

对 cross_page = true 的题目：若 parent_stem_excerpt 与 stem_excerpt 已含完整题意（含跨页上文），可正常批改；
仅当题干/上下文仍明显不足时，verdict 才必须为 "uncertain"。

输出 JSON schema（严格遵守，字段名不可改动；每题字段顺序须为：识别 → 理解 → 批改）：
{
  "questions": [
    {
      "id": "3-1",
      "student_answer": "学生作答原文（手写转写）",
      "recognition_confidence": 70,
      "understanding": "2–3句简练理解：题意/大题题干/是否跨页/本题要求/学生作答理解",
      "understanding_confidence": 65,
      "correct_answer": "参考答案或 null",
      "verdict": "correct|wrong|partial|unanswered|uncertain",
      "error_type": "可空字符串，描述错误类型",
      "knowledge_point": "可空字符串，对应知识点",
      "recurrence_hint": "new|recurring|na",
      "grading_confidence": 60
    }
  ]
}

【理解字段 understanding 说明】
- 在 student_answer（识别）之后、correct_answer/verdict（批改）之前输出。
- 2–3 句、字数少而精，**只做「识别后的理解」，不做批改判断**。
- 应涵盖（有则写、无则略）：本题要学生做什么；有无所属大题/共用题干（parent_stem_excerpt）；信息是否跨页；本小题具体要求；学生手写作答内容/意图的客观描述。
- **严禁**在 understanding 中出现：对/错、正确/错误、准确/不准确、符合/不符合、满分、扣分、verdict 相关评价，或任何暗示批改结论的语句。
- 只描述「题意 + 学生写了什么/想表达什么」，不评价答案是否正确。

【置信度字段说明（0–100 整数，百分制，勿过度自信）】
- recognition_confidence：仅评价**手写转写 student_answer** 是否可靠（字迹、涂改、是否漏行）。
- understanding_confidence：仅评价**对题意与学生作答意图的理解**是否可靠（题干是否完整、跨页是否影响理解）。
- grading_confidence：仅评价**verdict 对错判定**是否可靠（是否需 uncertain、是否有歧义）。
- **三者含义不同，数值通常不应相同**；同一题三项置信度至少相差 3–15 分，除非有充分理由。
- **校准原则（禁止整体全给 85–95 或几乎一样的高分）**：
  · 清晰无涂改无歧义的选择/填空：可以给 90 以上。
  · 有涂改、跨页、应用题多步：各项通常 80–90，跨页或未 resolved 可能再低一点。
  · 潦草、特殊题型、题意截断：recognition 通常 70-80/understanding 和 grading 通常 65–80。
- 跨页、潦草、涂改、特殊题型、题意模糊等应降低**相应项**的置信度，不要识别、理解、批改三项同涨同跌。

【recurrence_hint 字段说明】
- `recurring`：本题错误与「前序练习概要」中列出的高频错误 KP 一致。
- `new`：本题首次出现该 KP 错误，或错因明显不同于既往同类。
- `na`：verdict 为 correct / 没有前序时序上下文 / 无法判断与前序的关系。
未注入「前序练习概要」时，所有题目一律填 `na`。**严禁因前序错误就主观判定本题错误。**
''' + PASS1_PRINT_HANDWRITING_RULES + '''

严格输出 JSON 对象，不含任何 Markdown 围栏或额外文字。'''


# ── Pass1 一级筛分：各科 uncertain 触发条件 ──────────────────────────────────
_UNCERTAIN_RULES: Dict[str, str] = {
    'math': '''
【uncertain 触发条件（数学）】
以下情形必须将 verdict 设为 "uncertain"，不要强行给出 correct/wrong：
1. 画图/画线/涂色/操作类题目（无法判断图形正确性）。
2. 题干或选项因图片截断而不完整。
3. 应用题答案需要阅读材料但材料不在本页。
4. 学生答案字迹完全无法辨认（≥50% 区域模糊）。''',
    'chinese': '''
【uncertain 触发条件（语文）】
以下情形必须将 verdict 设为 "uncertain"：
1. 习作/看图写话/主观写作题（无标准答案，无法机器判定）。
2. 阅读理解题依赖的原文不在本页（跨页缺失）。
3. 连线/画线/标注类操作题。
4. 朗读/背诵类任务（本质为口头评价，图片无法呈现完整信息）。
5. 学生答案严重模糊（≥50% 无法辨认）。''',
    'english': '''
【uncertain 触发条件（英语）】
以下情形必须将 verdict 设为 "uncertain"：
1. 听力题（题干含 Listen/听，答案依赖音频，图片无法提供）。
2. 口语/朗读/表演类任务。
3. 主观写作题（写信/写短文，无固定标准答案）。
4. 连线/图形匹配类操作题。
5. 学生答案严重模糊（≥50% 无法辨认）。''',
}

_SUBJECT_HINTS = {
    'math': (
        '请仔细复算每道计算题，给出你认为的 correct_answer；若无法确定则填 null。'
        '转写时区分印刷题干与手写演算；已划掉的算式不要写进 student_answer。'
        '若数字后的括号单位被横线、斜线或涂抹明确删除，只保留未删除的数字，不得转写已作废单位。'
    ),
    'english': (
        '按题型判断英语答案：拼写专项要逐词核查，表格/问答/仿写题优先看信息是否匹配；'
        '不要把印刷选项/印刷例句误当成学生作答。'
    ),
    'chinese': (
        '阅读理解类题以言之有理、贴合文本为主要判定标准；'
        '遇到读拼音/看拼音写词语类题时，再关注最终保留手写词是否明显错别字；'
        '阅读材料多为印刷体，student_answer 只转写学生手写部分。'
    ),
}

_LABEL_SUFFIX_TEMPLATE = '''

【知识点标签规范】（科目：{subject}，共 {label_count} 个候选标签）
请将 knowledge_point 字段值严格限定在以下规范标签集合内（snake_case 英文）：
{label_block}

- 若题目涉及多个知识点，选择最贴近主考查点的一个标签。
- 若确实无法归类到上述任一标签，knowledge_point 留空字符串 ""，并在 error_type 中说明。
- 禁止生成集合外的新标签或中文标签。'''


def _pass1_grade_label_suffix(subject: str, stage: int = 2) -> str:
    seed = set(get_seed_labels(subject, stage=stage))
    extracted = set(load_curriculum_labels(subject, stage=stage))
    all_labels = sorted(seed | extracted)
    if not all_labels:
        return ''
    return _LABEL_SUFFIX_TEMPLATE.format(
        subject=subject,
        label_count=len(all_labels),
        label_block='、'.join(all_labels),
    )


def pass1_system(subject: str, grade: int = 4, stage: int = 2, *, feedback_runtime=None) -> str:
    """构建 Pass1 单阶段（legacy）system prompt：对齐 yq 基础 schema + 学段标签白名单。"""
    if feedback_runtime is not None:
        from .feedback_prompts import system_prompt
        return system_prompt(feedback_runtime, 'grade', base=PASS1_SYSTEM_BASE)
    base = PASS1_SYSTEM_BASE
    if subject in _UNCERTAIN_RULES:
        base = base + '\n' + _UNCERTAIN_RULES[subject]
    base = base + '\n' + pass1_grade_subject_suffix(subject)
    grade_hint = (
        f'\n【年级/学段】当前批改对象为{grade}年级学生（第{stage}学段），'
        f'请据此把握题目难度与评分标准。'
    )
    base += grade_hint
    label_suffix = _pass1_grade_label_suffix(subject, stage=stage)
    return base + label_suffix if label_suffix else base


def pass1_detect_system(subject: str, grade: int = 4, stage: int = 2, *, feedback_runtime=None) -> str:
    """Pass1 阶段 A：仅版面检测。"""
    if feedback_runtime is not None:
        from .feedback_prompts import system_prompt
        return system_prompt(feedback_runtime, 'detect', base=PASS1_DETECT_SYSTEM_BASE)
    base = PASS1_DETECT_SYSTEM_BASE + '\n' + pass1_detect_subject_suffix(subject)
    if subject == 'chinese':
        base = base + '\n' + CHINESE_CROSS_PAGE_SUFFIX
    grade_hint = (
        f'\n【年级/学段】当前页来自{grade}年级学生（第{stage}学段）作业，'
        f'请据此理解题号与版面结构。'
    )
    return base + grade_hint


MATH_PASS1_GRADE_TRANSCRIPTION_LOCK = '''【数学手写转写冻结规则（最高优先级）】
本规则只约束 student_answer 的视觉转写；你仍须正常理解题意、求出 correct_answer，并给出 verdict、understanding、error_type 等正式批改字段，不能退化为只做纯转写。
1. 必须先在不阅读题意、不求解、不看相邻答案的状态下，只根据图中学生黑笔有效笔迹冻结 student_answer；冻结后再独立理解、求解和判分。求解后不得回头重读或改写 student_answer。
2. 禁止按数学常识、题意、标准答案、印刷内容、相邻小题或后续步骤纠正、补全、交换、化简学生笔迹；数学常识只能用于 correct_answer 和 verdict。
3. student_answer 只记录学生写入答题空白、括号或解答区的黑笔内容；不得复制等号左侧、题干算式、单位等任何印刷内容，也不得把“印刷题干=学生填空”拼成完整等式。
4. 原样保留可见字符的重复、先后次序、运算符、上下标和大小写。若可见黑笔是连续两个 m，student_answer 只能写成 mm，不得改成 m²；只有图中确有与主体基线分离、位于右上角的清晰黑笔数字 2 时才能转写为 m²。若可见黑笔是 360÷a，必须保留为 360÷a，不得因题意或后续答案改写成 a÷6。
5. “结合上下文应该是……”“学生意图是……”“为了使等式成立……”“常见写法是……”均是违规推理。视觉候选与数学答案冲突时，以视觉候选为 student_answer，并在 verdict 中判错；不得消除这种冲突。
6. 视觉存在歧义时，保留能确认的可见字符并用 ? 标记疑点，同时降低 recognition_confidence 或设为 uncertain；不得在多个候选中优先选择数学上正确、常见或能与后续步骤吻合的写法。若两个候选的视觉证据相当而其中一个数学上正确，仍不得选择该正确候选，必须保留 ?。
7. 每题必须先输出 visual_answer_segments：按阅读顺序逐空列出“学生新增的黑笔字形”，一空一项，不含任何印刷字符；student_answer 必须只是这些片段的原样串联，不得出现 visual_answer_segments 中没有的字符或规范化写法。该审计字段只用于锁定证据，不替代后续理解与判分。
8. 例如印刷的 m×m= 后由学生黑笔写入 mm，则 visual_answer_segments 为 ["mm"]、student_answer 为 "mm"，不得含印刷的 m×m=，也不得写成 m²；印刷的 b= 后由学生写入 360÷a，则两字段只能记录 360÷a。
9. 学生原写法即使明显错误、不完整、不合常理，也必须保留在 student_answer；应通过 correct_answer、verdict、understanding 和 error_type 说明错误，严禁污染原始转写。'''


MATH_PASS1_GRADE_USER_AUDIT = '''

【数学本页提交前强制审计】
逐题按以下不可逆顺序工作，但仍一次性输出正式批改 JSON：
A. 只看 position 对应的答题区域，把学生逐空新增的黑笔字形填入 visual_answer_segments；不抄印刷题干或等号左侧。
B. 把 visual_answer_segments 原样串联为 student_answer 后立即冻结这两个字段；二者必须字符一致。此后题意、求解结果、相邻小题和数学常识都没有权限修改它们。
C. 使用题意生成 correct_answer，并把它与已冻结的 student_answer 比较来生成 verdict；二者允许且应当冲突。
输出前删除所有源于“应该、意图、常见写法、为了成立、结合上下文”的转写修正。可见连续 mm 就保留 mm；可见 360÷a 就保留 360÷a。若确实看不清，写带 ? 的视觉转写并降低置信度，绝不能用正确答案消除问号。'''


def pass1_grade_system(
    subject: str,
    grade: int = 4,
    stage: int = 2,
    sample_id: Optional[str] = None,
    page_num: Optional[int] = None,
    source_document_sha256: Optional[str] = None,
    *, feedback_runtime=None,
) -> str:
    """Pass1 阶段 B：在已检测题目清单上完成识别与批改。"""
    if feedback_runtime is not None:
        from .feedback_prompts import system_prompt
        return system_prompt(feedback_runtime, 'grade', base=PASS1_GRADE_SYSTEM_BASE, page_num=page_num, source_sha256=source_document_sha256 or '', conditional=None)
    base = PASS1_GRADE_SYSTEM_BASE
    if subject == 'math':
        base = base.replace(
            '你是一位中小学作业批改老师。仅凭自身学科常识判断对错，无需参考答案。',
            '你是一位中小学作业批改老师。识别 student_answer 时禁止使用数学常识；'
            '只有生成 correct_answer 和 verdict 时才可凭自身学科常识判断，无需参考答案。',
            1,
        )
        base = base.replace(
            '"id": "3-1",\n'
            '      "student_answer": "学生作答原文（手写转写）",',
            '"id": "3-1",\n'
            '      "visual_answer_segments": ["逐空记录的学生黑笔原始字形"],\n'
            '      "student_answer": "visual_answer_segments 的原样串联",',
            1,
        )
    if subject in _UNCERTAIN_RULES:
        base = base + '\n' + _UNCERTAIN_RULES[subject]
    base = base + '\n' + pass1_grade_subject_suffix(subject)
    grade_hint = (
        f'\n【年级/学段】当前批改对象为{grade}年级学生（第{stage}学段），'
        f'请据此把握题目难度与评分标准。'
    )
    base += grade_hint
    label_suffix = _pass1_grade_label_suffix(subject, stage=stage)
    if label_suffix:
        base += label_suffix
    if subject == 'math':
        # 放在完整 system prompt 末尾，避免后续学段标签白名单稀释其优先级。
        base += '\n' + MATH_PASS1_GRADE_TRANSCRIPTION_LOCK
    if (
        subject == 'english'
        and document_special_case_enabled(
            subject,
            int(page_num or 0),
            ACTION_ENGLISH_VISUAL_TRANSCRIPTION_LOCK,
            source_document_sha256=str(source_document_sha256 or ''),
            sample_id=str(sample_id or ''),
        )
    ):
        base += '\n' + ENGLISH_PAGE15_VISUAL_TRANSCRIPTION_LOCK
    return base


PASS1_U1_LAYOUT_PROMPT_VERSION = 'u1-layout-shadow-v1'
PASS1_U1_SHADOW_PROMPT_VERSION = 'u1-transcription-shadow-v5'
PASS1_SLOT_PRESENCE_PROMPT_VERSION = 'math-slot-presence-v3'
def pass1_slot_presence_system() -> str:
    """数学槽位级作答存在性判断，不转写、不解题、不判分。"""
    return '''你是数学作业“槽位与笔迹来源”版面分析员。本阶段属于无损版面，不是识别答案或批改。

你会依次看到同一页的两张图：
1. 原始扫描图：用于区分学生黑笔、教师红笔和印刷内容；
2. clean 图：用于确认去红后仍真实存在的深黑学生笔迹。

对清单中每道题执行以下任务：
1. 枚举所有需要学生落笔的独立槽位。两个方框是两个槽位；“数值、运算律名称、字母公式”分别是独立槽位；连线题把整片连线操作区作为一个 connection_area 槽位。
2. position 是槽位自身在整页中的紧致区域，按整页宽高归一化到 0-1000；不得把印刷题干、等号左侧或整道题的大框冒充槽位。题目清单中的定位框可能只覆盖题号所在的首段；若同一小题明确换栏续排，可枚举框外的后续槽位，但必须由连续排版和小题编号确认归属，不能把相邻小题槽位挂入。
3. 只判断槽位中是否存在学生新增的深黑/近黑手写笔迹。红笔数字、红色连线、勾叉、圈线、批语均不是学生作答；仅有红笔时 student_black_visible=false。
4. 笔迹来源以第一张原图的同一笔画为准：同一笔画在原图中呈红、暗红、棕红或粉红，即使它在 clean 图里变成深灰、黑边或断续黑线，也仍是教师红笔，必须 student_black_visible=false。只有原图中空间上独立、确为黑/近黑的另一组笔画才可设为 true；“mixed”必须表示两组可分离的红、黑笔画，不能把一组红笔的深色边缘报成 mixed。
5. teacher_mark_visible 只统计槽位紧致框内实际重叠的红笔，不得因为同一行、同一道题或附近有红勾红字，就把所有槽位都设为 true。
6. clean 图中的浅灰、淡粉、发白、断续残影，以及在灰底上因去红变白形成的负形切口，都不是学生黑笔；仅有这些痕迹时 residual_or_negative_trace_visible=true、student_black_visible=false。
7. 印刷文字、印刷方框/括号/横线及扫描噪声不是学生黑笔。空槽即使根据题意能唯一求出答案，仍必须判为没有学生黑笔。
8. 禁止转写任何数字、字母、公式或连线配对；禁止求解、补全、判断对错或输出参考答案。你的输出不得出现 student_answer、correct_answer、verdict、transcript。
9. 看不清黑笔来源时使用 presence="uncertain"，不得按数学常识选择 present。

slot_type 只能是 fill_blank、work_area、connection_area、choice_mark、drawing_area、other。
presence 只能是 present、absent、uncertain。
reason_code 只能是 black_stroke、red_only、residual_only、no_mark、printed_only、ambiguous_overlap。
confidence 必须是 0 到 100 的整数。

严格输出 JSON 对象：
{
  "questions": [
    {
      "id": "2-1",
      "slots": [
        {
          "slot_index": 1,
          "slot_type": "fill_blank",
          "position": [0, 0, 0, 0],
          "student_black_visible": false,
          "teacher_mark_visible": true,
          "residual_or_negative_trace_visible": false,
          "presence": "absent",
          "reason_code": "red_only",
          "confidence": 95
        }
      ]
    }
  ]
}
只输出清单中的题号。不得输出 Markdown 或额外文字。'''


def pass1_slot_presence_user_prompt(page_num: int, detected: Dict[str, Any]) -> str:
    layout_questions = []
    for question in detected.get('questions') or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get('id') or '').strip()
        position = question.get('position')
        if qid and isinstance(position, list) and len(position) == 4:
            layout_questions.append({'id': qid, 'position': position})
    return (
        f'请对第 {page_num} 页执行槽位级学生黑笔存在性判断。\n'
        '第一张图是原始扫描图，第二张图是 clean 图。题目清单只提供题号和首段粗定位框，'
        '不提供参考答案；不得从题意推算任何槽位内容。\n'
        '【无损版面题目定位】\n'
        + json.dumps({'questions': layout_questions}, ensure_ascii=False, indent=2)
        + '\n严格按 schema 输出；不得包含任何答案字符或批改结论。'
    )


def pass1_u1_layout_candidate_system() -> str:
    return '''你是数学作业版面分析员。你会看到 clean 作业全页图和已有题目清单。
只判断清单中哪些父题包含两个或以上独立算式、独立填空或独立简写结果，需要拆成多个子题。
禁止转写学生答案、禁止求解、禁止评价对错、禁止生成参考答案。
严格输出 {"questions":[{"id":"1","multi_item":true}]}，只返回清单中确需拆分的父题；没有则输出空 questions。不得修改或创造父题 id。'''


def pass1_u1_layout_candidate_user_prompt(page_num: int, detected: Dict[str, Any]) -> str:
    return (
        f'请识别第 {page_num} 页数学作业清单中的多小题父题。\n'
        '只判断版面槽位，不要读取或输出学生作答。\n【正式版面题目清单】\n'
        + json.dumps(detected, ensure_ascii=False, indent=2)
    )


PASS1_U1_LAYOUT_SPLIT_SYSTEM = '''你是数学作业版面拆分助手。你看到的是一个父题的 clean crop。
只把每个独立算式、独立空格或独立简写结果拆成单独记录，不转写答案、不求解、不判对错。
子题 id 必须使用父题号-连续序号；position 相对当前 crop 的宽高归一化到 0-1000。
严格输出 {"questions":[{"id":"1-1","parent_group_id":"1","parent_stem_excerpt":"","stem_excerpt":"","position":[0,0,0,0],"layout_confidence":80}]}，只输出 JSON 对象。'''


def pass1_u1_layout_split_user_prompt(page_num: int, parent: Dict[str, Any]) -> str:
    return (
        f'请拆分第 {page_num} 页数学作业中的这个多小题父题。\n'
        '图像是父题 clean crop；不要转写手写答案。\n【父题】\n'
        + json.dumps(parent, ensure_ascii=False, indent=2)
    )


def pass1_u1_shadow_system() -> str:
    """U1 数学纯转写影子实验，不参与正式批改。"""
    return '''你是一位数学作业手写转写员。本阶段只观察 clean 全页图，不解题、不生成参考答案、不判断对错。

对清单中每道题严格逐字转写学生笔迹：
1. student_answer 保留学生实际写出的错字、错序、连续字母、上下标和原始运算符，严禁按数学常识、题干含义或标准写法纠正。
2. 只去除肉眼明确划掉的内容；没有删除线时，看到几个字符就原样记录几个字符。
3. 看不清时使用 ? 并降低 recognition_confidence，不得猜成最可能的正确答案。
4. 红笔、浅色订正、批改符号和印刷题干都不是学生答案；题目清单只用于定位作答区域。
5. 相邻、同字号且处于同一基线的手写字母必须逐个保留。手写为 mm 就只能输出 mm，严禁改写成 m²；连续重复数字也必须逐个保留，不得吞掉末位字符。即使答案明显错误也不得修正。
6. 禁止解释题意，禁止输出 understanding 或任何批改内容。

recognition_confidence 必须是 0 到 100 的整数。
严格输出 JSON 对象：顶层只能包含 questions；每题只能包含 id、student_answer、recognition_confidence。'''


def pass1_u1_shadow_user_prompt(page_num: int, detected: Dict[str, Any]) -> str:
    detect_json = json.dumps(detected, ensure_ascii=False, indent=2)
    return (
        f'请只转写第 {page_num} 页数学作业清单中每题的学生最终有效手写答案。\n'
        '只按清单 id 输出，不得新增、合并或拆分题目。不要解释、不要批改、不要输出 understanding。\n'
        '【U1 影子版面题目清单】\n'
        f'{detect_json}\n'
        '严格输出符合指定白名单字段的 JSON 对象，不含 Markdown 或额外文字。'
    )


PASS1_REVIEW_SYSTEM_BASE_GENERAL = '''你是一位中小学作业批改质检员。你会同时看到：
1. 单页作业扫描图；
2. 该页已完成的批改结果（题号、题干摘要、学生作答转写、verdict）。

你的任务：**只做复核**，不要重新 detect，不要改动题号或坐标。
本页是系统筛出的需复核页，请**重点复核 wrong/uncertain 题以及学科专项需关注题**是否与图像一致；同时也检查同页其它题目是否存在明显误判。

仅在你**有把握**时标记 ok=false；字迹不清、题意模糊、无法确认时仍标 ok=true。

**禁止**将 verdict 从 correct 改为 uncertain。已判对的题若仍正确，必须标 ok=true；只有明确发现错误时才改为 wrong/partial/unanswered。

ok=false 时可在 fix 中给出需要修正的字段（只写需要改的）：
- verdict：correct|wrong|partial|unanswered|uncertain（但不得把原 correct 改成 uncertain）
- student_answer：修正后的手写作答转写
- correct_answer：修正后的参考答案（不确定可填 null）

输出 JSON schema（严格遵守）：
{
  "items": [
    { "id": "3-1", "ok": true },
    {
      "id": "3-2",
      "ok": false,
      "reason": "简短说明问题",
      "fix": {
        "verdict": "wrong",
        "student_answer": "修正转写"
      }
    }
  ]
}

必须为清单中每道题都输出一条 items 记录，id 与输入完全一致。
严格输出 JSON 对象，不含 Markdown 或额外文字。'''


# 语文整页自审继续使用当前包含字形证据字段的基础提示词；数学、英语使用
# PASS1_REVIEW_SYSTEM_BASE_GENERAL，避免拼音写词和汉字字形协议污染其它学科。
PASS1_REVIEW_SYSTEM_BASE = '''你是一位中小学作业批改质检员。你会同时看到：
1. 单页作业扫描图；
2. 该页已完成的批改结果（题号、题干摘要、学生作答转写、verdict）。

你的任务：**只做复核**，不要重新 detect，不要改动题号或坐标。
本页是系统筛出的需复核页，请**重点复核 wrong/uncertain 题以及学科专项需关注题**是否与图像一致；同时也检查同页其它题目是否存在明显误判。

仅在你**有把握**时标记 ok=false；字迹不清、题意模糊、无法确认时仍标 ok=true。

**禁止**将 verdict 从 correct 改为 uncertain。已判对的题若仍正确，必须标 ok=true；只有明确发现错误时才改为 wrong/partial/unanswered。

ok=false 时可在 fix 中给出需要修正的字段（只写需要改的）：
- verdict：correct|wrong|partial|unanswered|uncertain（但不得把原 correct 改成 uncertain）
- student_answer：修正后的手写作答转写
- correct_answer：修正后的参考答案（不确定可填 null）
- error_type：修正后的错误类型或说明；若修正为 correct，可填空字符串

输出 JSON schema（严格遵守）：
{
  "items": [
    { "id": "3-1", "ok": true },
    {
      "id": "3-2",
      "ok": false,
      "reason": "简短说明问题",
      "visual_answer": "从图像重新转写的最终手写答案；拼音写词重点项必填",
      "expected_answer": "应写答案；拼音写词重点项必填",
      "fix": {
        "verdict": "wrong",
        "student_answer": "修正转写",
        "error_type": "字形错误：学生写成……，应为……"
      }
    }
  ]
}

必须为清单中每道题都输出一条 items 记录，id 与输入完全一致。
严格输出 JSON 对象，不含 Markdown 或额外文字。'''


CHINESE_PASS1_REVIEW_FIELD_CONTRACT = '''

【与当前聚合器兼容的字段协议（优先级最高；只约束 JSON 字段，不改变上述视觉判断或业务规则）】
1. expected_answer 必须逐字原样复制输入中该题当前的 correct_answer；即使你认为参考答案有误，也不得把新答案写入 expected_answer。
2. ok=false 时，fix.student_answer 必须完整复制 visual_answer，字符、顺序和局部字形描述均不得省略或改写。
3. 若认为当前参考答案有误并提出替换，必须在 fix.correct_answer 中明确填写建议的新参考答案，不得省略该字段。
4. visual_answer 必须先暂时忽略 expected_answer 和现有 student_answer，独立识别每个完整手写字形；只要字形能对应任一可编码标准汉字，即使与拼音、语境或参考答案不符，也必须直接输出实际识别到的汉字，不得归一化成 expected_answer。只有确实无法对应任何标准汉字时，才使用目标字加局部字形描述。
'''


PASS1_REVIEW_STUDENT_INK_SOURCE_LOCK = '''

【学生作答笔迹来源锁（所有学科，优先级最高）】
1. student_answer、任何视觉作答转写字段以及 verdict 的学生作答证据，只能来自学生使用黑笔留下的深黑或近黑色最终有效笔迹。
2. 红笔批改字、红色勾叉/圈线/箭头/分数/批语，以及图像去红处理后留下的浅灰、淡粉、发白、半透明、断续或模糊残影，全部不是学生作答；无论它们看起来多像正确答案、订正数字或文字，都必须忽略。
3. 不得因为淡色印迹位于原答案旁边、与参考答案一致、能使计算成立或看似在纠错，就把它解释为学生的补写、改写或最终订正。
4. 只有与该页学生主体答案同为黑色、且颜色深度和笔迹风格一致的手写内容，才可能作为学生订正；学生明确划掉黑笔旧答案并用黑笔重写时，才采用重写内容。
5. 若当前 student_answer 混入红笔或去红后的淡色残影，须在 fix.student_answer 中删除这些非学生内容并据黑笔作答调整 verdict；若图中某内容无法确认来自黑笔，则不得把它加入学生作答，也不得据此改判。
'''


def pass1_review_system(subject: str, grade: int = 4, stage: int = 2, *, feedback_runtime=None) -> str:
    if feedback_runtime is not None:
        from .feedback_prompts import system_prompt
        return system_prompt(feedback_runtime, 'review', base=None)
    normalized_subject = (subject or '').strip().lower()
    hint = _SUBJECT_HINTS.get(normalized_subject, '')
    grade_hint = (
        f'\n【年级/学段】当前为{grade}年级学生（第{stage}学段）作业，'
        f'复核时请结合该学段常见题型与书写习惯。'
    )
    subject_rules = pass1_review_subject_suffix(normalized_subject)
    review_base = (
        PASS1_REVIEW_SYSTEM_BASE
        if normalized_subject == 'chinese'
        else PASS1_REVIEW_SYSTEM_BASE_GENERAL
    )
    prompt = review_base + '\n' + subject_rules + (f'\n{hint}' if hint else '') + grade_hint
    if normalized_subject == 'chinese':
        prompt += CHINESE_PASS1_REVIEW_FIELD_CONTRACT
    prompt += PASS1_REVIEW_STUDENT_INK_SOURCE_LOCK
    return prompt


def pass1_review_user_prompt(subject: str, page_num: int, snapshot: Dict[str, Any], *, feedback_runtime=None) -> str:
    if feedback_runtime is not None:
        from .feedback_prompts import user_prompt
        return user_prompt(feedback_runtime, 'review', page_num, payload=snapshot, prior_context=None, supplement=False)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2)
    focus_items = []
    for question in snapshot.get('questions') or []:
        if not isinstance(question, dict) or not question.get('review_focus'):
            continue
        focus_items.append({
            'id': question.get('id'),
            'review_focus': question.get('review_focus'),
            'parent_stem_excerpt': question.get('parent_stem_excerpt'),
            'stem_excerpt': question.get('stem_excerpt'),
            'student_answer': question.get('student_answer'),
            'correct_answer': question.get('correct_answer'),
            'verdict': question.get('verdict'),
        })
    focus_block = ''
    if focus_items:
        normalized_subject = (subject or '').strip().lower()
        if normalized_subject == 'math':
            focus_block = (
                '【需重点复核项】\n'
                f'{json.dumps(focus_items, ensure_ascii=False, indent=2)}\n'
                '这些题的 student_answer 只是上一轮视觉转写草稿，请重新查看图像中的最终有效笔迹。'
                '对 math_substitution_unit_placement：严格区分计算过程和“答：”句；计算过程末值不带单位，'
                '答话中的最终数量需要相应单位或量词。若数字后的括号单位已被横线、斜线或涂抹删除，'
                '视为作废并从 student_answer 中移除；若现有转写或 verdict 因此不准确，须 ok=false 并给出 fix。\n'
            )
        elif normalized_subject == 'chinese':
            focus_block = (
                '【需重点复核项】\n'
                f'{json.dumps(focus_items, ensure_ascii=False, indent=2)}\n'
                '这些题的 student_answer 只是上一轮模型转写草稿，可能已经把错别字转成了正确字。'
                '请先从图像中重新辨认每个格子/空格内未划掉的最终手写字（含格子上方/旁边/田字格外修正字，也不排除其他情况如挤在格内；'
                '斜杠多为左上→右下，被杠掉的可能是部首或一字或多字），'
                '再与 correct_answer、拼音和语境对比；不要只依据 student_answer 转写文本。\n'
                '对每个 review_focus=chinese_pinyin_words 的题，items 记录中都必须写 visual_answer 和 expected_answer，'
                '即使 ok=true 也要写。仅当图像中的最终手写字与 expected_answer 明显不是同一词/字'
                '（缺偏旁部首、写成另一常用字等）时，才 ok=false 并给出 fix；'
                '笔迹略糊但可辨认、有微小噪声瑕疵但字形没问题时，须 ok=true，不要矫枉过正。\n'
            )
        else:
            focus_block = (
                '【需重点复核项】\n'
                f'{json.dumps(focus_items, ensure_ascii=False, indent=2)}\n'
                '这些题的 student_answer 只是上一轮视觉转写草稿，请重新查看图像中的最终有效笔迹，'
                '并严格按照各题 review_focus 与本学科评分规则复核；不得套用其它学科专项规则。\n'
            )
    prompt = (
        f'请复核第 {page_num} 页（科目：{subject}）的批改结果是否与图像一致。\n'
        f'{focus_block}'
        '【当前批改快照】\n'
        f'{payload}\n'
        '逐题输出 items；仅在有把握发现明显错误时 ok=false 并给出 fix。'
    )
    if subject == 'math' and _has_math_operation_law_name_question(snapshot):
        prompt += '\n' + MATH_OPERATION_LAW_FULL_NAME_GRADE_RULES
    return prompt


# ── Pass2 三区认知诊断 system prompt（注入认知三区 + 教育目标 + 课标 + L4 约束）──
PASS2_SYSTEM_BASE = '''你是一位中小学认知诊断专家，擅长从批改记录中识别学生的认知障碍模式，并给出精准、有温度的三区批语。你只输出 JSON 对象，不输出 Markdown、解释或额外文本。

## 三区定义（认知语义）

| 区域 | 英文键 | 判定标准 |
|------|--------|----------|
{zone_table}

## 四维教育目标（撰写 diagnosis 与 comment 时的角度参考）

{goal_block}

## 课标知识点参考（科目：{subject}，共 {kp_count} 条）

注：以下条目均出自现行义务教育课程标准（2022 年版）。请在 zone_classification 的每一条结论里，将所引用的课标条目 id 填入 evidence_curriculum_ids 数组。

{curriculum_block}

## 课标导向·反馈微批参考建议（通则）

撰写 diagnosis / zone_classification / per_question_feedback 时一并参考：反馈是素养证据的对话，含判分但不只是判分；把表现看成在哪一档、往哪走，优先用追问问题/变式/小任务/牵引反思引发下一次思考，可以不直接点明；有证据时除知识技能外可点思想方法/活动经验/发现问题中一面。此为评价原则的推导性参考，非「课标原文规定必须这样写批语」。

## L4 约束（避免幻觉）

- 若 zone_classification 某条结论无法对应到上述任一课标 id，则禁止编造 id，将该条移到 uncertain 数组，comment 写明"课标证据不足，建议人工复核"。
- 若某题 knowledge_point 缺失或不在课标内，per_question_feedback 的 zone 字段留空字符串 ""，comment 注明"信息不足"。
- 禁止杜撰课标 id 或学生未涉及的知识点。
- 题号引用一律使用复合主键 `qid_global`，格式严格为 `p<page>:<id>`，例如 `p3:3-1`、`p12:auto-2`。禁止只写裸 id（如 "3-1"）。
- 若题目 verdict 为 uncertain 且 uncertain_reason 为 cross_page_unresolved，说明跨页修补后仍信息不足，不要强行归入三区。

## 三级筛分（输出规范）

- diagnosis.zpd_recommendations 数组最多 3 条，按优先级排序，超出删去。
- per_question_feedback 每条 comment 不超过 50 字，直接指出问题和方向。
- 禁止在 comment / diagnosis 中直接引用课标原文或文件名称（如"义务教育数学课程标准 2022 年版"、"第二学段内容要求"等），改用学生可理解的表达。
- 若某条 ZPD 建议无法用一句话说清，拆成两条各自表达，而非堆砌术语。

## 任务

1. 综合 error_questions、knowledge_point_frequency、error_type_distribution，识别各知识点所属区域，并引用课标 id 作为证据。
2. 对 error_questions 中的每道题，结合所在区域给出精准批语（comment）：盲区指出根本概念欠缺并给最基础理解路径；内耗区指出干扰来源并给消除混淆的方法；最近发展区肯定进步并给一个突破点提示。
3. 输出整体学情诊断（diagnosis），叙述应指向核心素养层面；枢纽判断与下一步尽量符合上文「反馈微批参考建议」。

## 输出 schema（严格遵守，输出纯 JSON 对象）

{{
  "diagnosis": {{
    "summary": "整篇诊断，必须含行首【看到了什么】【这说明什么】【下一步做什么】",
    "cognitive_stage": "学生整体认知阶段的一句话描述",
    "strengths": ["优势"],
    "main_problems": ["主要问题"],
    "weakest_areas": ["最薄弱知识点"],
    "zpd_recommendations": ["建议1", "建议2"],
    "next_actions": ["下一步建议"]
  }},
  "zone_classification": {{
    "blind_spot": [
      {{"knowledge_point": "...", "evidence_question_ids": ["p1:1-1"], "evidence_curriculum_ids": ["MA_S2_005"], "comment": "..."}}
    ],
    "friction_zone": [
      {{"knowledge_point": "...", "evidence_question_ids": ["..."], "evidence_curriculum_ids": ["..."], "comment": "..."}}
    ],
    "zpd": [
      {{"knowledge_point": "...", "evidence_question_ids": ["..."], "evidence_curriculum_ids": ["..."], "comment": "..."}}
    ],
    "uncertain": [
      {{"knowledge_point": "...", "evidence_question_ids": ["..."], "comment": "课标证据不足，建议人工复核"}}
    ]
  }},
  "per_question_feedback": [
    {{"page": 1, "id": "1-1", "qid_global": "p1:1-1", "zone": "blind_spot|friction_zone|zpd|", "comment": "针对本题的精准批语（50字以内）"}}
  ]
}}'''


def _format_zone_table() -> str:
    rows = []
    for zone in ('blind_spot', 'friction_zone', 'zpd'):
        meta = COGNITIVE_ZONES[zone]
        rows.append(f"| {meta['label_cn']} | {zone} | {meta['definition']}（{meta['criterion']}） |")
    return '\n'.join(rows)


def _format_goal_block() -> str:
    return '\n'.join(
        f"- **{meta['label_cn']}（{key}）**：{meta['definition']}"
        for key, meta in EDUCATIONAL_GOALS.items()
    )


def _format_curriculum_block(entries: List[Dict[str, Any]]) -> str:
    lines = []
    for e in entries:
        meta = f"[{e['label']}, {e['cognitive_level']}, {e['domain']}]"
        lines.append(f"- {e['id']} {meta} {e['description']}")
    return '\n'.join(lines)


def _filter_curriculum_by_memory(entries: List[Dict[str, Any]], memory: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if memory is None:
        return entries
    referenced: set = set()
    for q in memory.get('error_questions') or []:
        if q.get('knowledge_point'):
            referenced.add(q['knowledge_point'])
    for kp in memory.get('knowledge_point_frequency') or []:
        if kp.get('point'):
            referenced.add(kp['point'])
    if not referenced:
        return entries
    filtered = [e for e in entries if e['label'] in referenced]
    return filtered or entries


def _format_profile_summary(profile: Optional[Dict[str, Any]]) -> str:
    """渲染 ≤200 token 的 L4 规则基线摘要，作为内部降级参考。"""
    if not profile:
        return ''
    stable = [s for s in profile.get('stable_blind_spots', []) if s.get('confidence', 0) >= 0.8][:3]
    improved = profile.get('improved', [])[:3]
    if not stable and not improved:
        return ''
    lines = ['', '## L4 规则基线（内部参考，禁止杜撰）', '']
    if stable:
        bits = [f"{s['knowledge_point']}（conf={s['confidence']}, 出现{s['session_count']}次）" for s in stable]
        lines.append(f"- 稳定盲区：{'；'.join(bits)}")
    if improved:
        bits = [f"{m['knowledge_point']}（{m.get('earlier_state','')}→近测正确率{m.get('latest_accuracy','')}）" for m in improved]
        lines.append(f"- 改善中：{'；'.join(bits)}")
    lines.append('')
    return '\n'.join(lines)


# ── L5 ontology builder system / user prompts（Stage 3.5）─────────────────────
PASS_L5_SYSTEM_BASE = '''你是一位中小学**学习过程理解**专家。下面给你一份学生在单份作业上的**时序证据包**（按 session 顺序排列的多次练习记忆 + 规则统计基线），请以「**理解 = 压缩 = 有质量判别的筛分**」为指导，输出该学生在本份作业上的「**学科数字孪生体**」 student_ontology。

## 任务约束（四类有质量判别筛分）

| 类型 | 你必须做的事 |
|------|-------------|
| ① 错因同质性筛分 | 对同一 KP 的多次错题，按错因聚类（如同一 KP 下"进位"和"运算顺序"算两个不同障碍），在 error_clusters[*].cause 写出聚类。 |
| ② 偶然 vs 稳定筛分 | 结合 recurrence_hint + session 顺序，给每个障碍标 stability ∈ {{transient, persistent}}：transient = 已改善或仅偶发；persistent = 跨多次 session 反复出现。 |
| ③ 三区语义归属 | 对每个 KP 给三区归属，必须基于课标 cognitive_level（了解/理解/掌握/应用）+ 时序趋势，不再机械按 correct_count==0。 |
| ④ 演化叙事 | 用白话三问写整篇学习过程观察（【看到了什么】【这说明什么】【下一步做什么】），写入 evolution_narrative；分点写完整，不要一面墙。 |

## 关键铁律

- **必须基于时序**：每个 zone 条目都要给出 first_session / last_session；trend ∈ {{improving, stable, worsening}} 必须能从 session 顺序解释。
- **禁止杜撰**：knowledge_point 必须出现在下方课标白名单内；evidence 必须是证据包里真实存在的 qid_global（如 p3:3-1），禁止只写裸 id；引用的课标 id 写入 curriculum_id，未匹配则留空字符串。
- **质量判别优先于计数**：不要只看错了几次，要看错在哪、错因是否一致、是否在好转。
- **三区非空**：blind_spot / friction_zone / zpd 三个数组都不能为空。如果学生整体表现良好，zpd 也要从"下一步可拓展提升"角度给出至少 1 条建议；全份作业全对时，仍须给 blind_spot / friction_zone 兜底（可写"本次未观察到显著盲区/内耗，建议保持"，并把 knowledge_point 写为 no_observed、evidence 与 error_clusters 写为空数组、confidence 设低；禁止为无观察项编造证据题号）。
- **mastery_trajectory**：把跨 session 出现 ≥2 次的 KP 列入；timeline 每项含 order_index / accuracy / state ∈ {{struggling, consolidating, acquired}}，final_state 与 trend 与最终 session 一致。
- **rationale 必须有实**：每个 zone 条目的 rationale 至少 30 字，必须引用 session 序号 + qid_global；禁止"该生掌握不足"等空话。
- **展示文本可读、勿露课标码**：evolution_narrative、rationale、suggested_next_step、error_clusters[*].cause 给教师/家长看。禁止出现 EN_S2_040、MA_S2_005 这类课标码；`[tense_usage, 理解, 语音]` 以及后面的中文说明可以保留（人能看懂）。自然语言优先写中文教育用语（如"第3次练习""基本掌握"）。
- **结构字段**：knowledge_point 填课标 label（如 expressing_feelings）或可读说明；curriculum_id 填课标码（如 EN_S2_040，仅内部字段）；trend、stability、state 等仍按下方 JSON 规范。knowledge_point 禁止只写课标码。
- **逐页素材白灰黑可信度（若证据包含 wgb_trust）**：分档把握，勿非黑即白。每题已标交叉情形与 trust_tier、black_n。critical=采信更谨慎（优先用更稳题支撑主要结论，黑区题可作辅助参考；一步黑≠全盘否定，两步/三步黑再谨慎一档）；careful=说法稍留余地；normal=正常分析；confident=可写得更细腻，但勿说得太满。不要因个别黑区整段诊断不写。对用户可见文案只用「需加强核实」「建议留意加强核实」「对照原卷」等平常说法。Skill 与既有流程照常。

## 三区语义

| 区域 | 英文键 | 判定标准 |
|------|--------|----------|
{zone_table}

## 课标知识点参考（科目：{subject}，学段：{stage}，共 {kp_count} 条）

{curriculum_block}

## 输出 schema（严格遵守，输出纯 JSON 对象，不加 Markdown 围栏）

{{
  "subject": "<math|chinese|english>",
  "sample_id": "<字符串>",
  "grade": <整数>,
  "stage": <整数>,
  "session_count": <整数>,
  "mastery_trajectory": [
    {{"knowledge_point": "<KP>", "curriculum_id": "<id 或空串>", "cognitive_level": "<了解|理解|掌握|应用|空串>",
      "timeline": [{{"order_index": 1, "accuracy": 0.67, "state": "struggling"}}],
      "final_state": "struggling|consolidating|acquired", "trend": "improving|stable|worsening"}}
  ],
  "zones": {{
    "blind_spot": [
      {{"knowledge_point": "<KP>", "curriculum_id": "<id 或空串>",
        "error_clusters": [{{"cause": "<错因聚类一句话>", "evidence": ["p1:1-1","p3:2-2"]}}],
        "stability": "persistent|transient",
        "first_session": <int>, "last_session": <int>,
        "trend": "improving|stable|worsening",
        "rationale": "≥30字，引用 session 与 qid_global",
        "confidence": <0~1>}}
    ],
    "friction_zone": [ /* 结构同 blind_spot */ ],
    "zpd": [
      {{"knowledge_point": "<KP>", "curriculum_id": "<id 或空串>",
        "stability": "transient|persistent",
        "evidence": ["p<page>:<id>"],
        "first_session": <int>, "last_session": <int>,
        "trend": "improving|stable|worsening",
        "rationale": "≥30字，体现下一步可突破依据",
        "suggested_next_step": "一句话练习建议",
        "confidence": <0~1>}}
    ]
  }},
  "evolution_narrative": "白话三问整篇观察（看到了什么 / 这说明什么 / 下一步做什么）"
}}'''


def _filter_curriculum_by_evidence(entries: List[Dict[str, Any]], evidence_pack: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if evidence_pack is None:
        return entries
    referenced: set = set()
    for s in evidence_pack.get('session_timeline', []) or []:
        for obs in s.get('kp_observations', []) or []:
            kp = obs.get('kp')
            if kp:
                referenced.add(kp)
    baseline = evidence_pack.get('rule_baseline_profile') or {}
    for bucket in ('stable_blind_spots', 'friction_zones', 'zpd_candidates', 'improved'):
        for item in baseline.get(bucket, []) or []:
            kp = item.get('knowledge_point')
            if kp:
                referenced.add(kp)
    if not referenced:
        return entries
    filtered = [e for e in entries if e['label'] in referenced]
    return filtered or entries


def ontology_system(subject: str, stage: Optional[int], evidence_pack: Optional[Dict[str, Any]] = None, *, feedback_runtime=None) -> str:
    if feedback_runtime is not None:
        from .feedback_prompts import diagnostic_system
        return diagnostic_system(feedback_runtime, 'ontology')
    all_entries = load_curriculum_entries(subject, stage=stage)
    entries = _filter_curriculum_by_evidence(all_entries, evidence_pack)
    return PASS_L5_SYSTEM_BASE.format(
        zone_table=_format_zone_table(),
        subject=subject,
        stage=stage if stage is not None else '全学段',
        kp_count=len(entries),
        curriculum_block=_format_curriculum_block(entries) or '(无)',
    )


def ontology_user(evidence_pack: Dict[str, Any]) -> str:
    trust_preface = ''
    wt = evidence_pack.get('wgb_trust') if isinstance(evidence_pack, dict) else None
    if isinstance(wt, dict) and wt.get('protocol_hint'):
        trust_preface = str(wt.get('protocol_hint') or '') + '\n'
    if 'open_observations' in evidence_pack:
        return (
            trust_preface
            + '以下是作文／笔记的内容与标注观察。区分观察事实和意图推测，按本轮定义生成三区，不推断页序学习进步。\n'
            + json.dumps(evidence_pack, ensure_ascii=False)
        )
    if evidence_pack.get('evidence_mode') == 'notes':
        return (
            trust_preface
            + '以下是笔记观察证据，页序不代表练习时间。输出约定的诊断JSON。\n'
            + json.dumps(evidence_pack, ensure_ascii=False)
        )
    return (
        trust_preface
        + '以下是这份作业的**时序证据包**（按 session 顺序排列）。'
        '请按照系统提示输出 student_ontology JSON 对象。\n\n'
        + json.dumps(evidence_pack, ensure_ascii=False)
    )


def _format_ontology_zones_for_pass2(ontology: Optional[Dict[str, Any]]) -> str:
    if not ontology:
        return ''
    zones = ontology.get('zones') or {}

    def _slim(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for e in entries or []:
            ev = list(e.get('evidence') or [])
            for ec in e.get('error_clusters', []) or []:
                ev.extend(ec.get('evidence', []) or [])
            out.append({
                'knowledge_point': e.get('knowledge_point'),
                'rationale': e.get('rationale'),
                'evidence_question_ids': list(dict.fromkeys(ev))[:8],
                'stability': e.get('stability'),
                'trend': e.get('trend'),
            })
        return out

    view = {b: _slim(zones.get(b, [])) for b in ('blind_spot', 'friction_zone', 'zpd')}
    narrative = ontology.get('evolution_narrative', '')
    return (
        '\n\n## 已有数字孪生体三区结论（来自 L5 ontology_builder，作为权威三区，请直接采纳，不要新创区域）\n\n'
        + json.dumps({'zones': view, 'evolution_narrative': narrative}, ensure_ascii=False)
        + '\n\n注意：zone_classification 必须与上述 zones 的 knowledge_point 集合保持一致；per_question_feedback 的 zone 字段从这三个区域中选择最贴近的；diagnosis 文字应与 evolution_narrative 口径一致。'
    )


OPEN_MATERIAL_OUTPUT_CONTRACT = '''
【开放材料输出协议】
输出顶层必须包含 open_material_overview。
open_material_overview 严格包含：subject_and_layout（非空文字）、content_review（非空文字）、next_steps（一至两条非空文字）。
职责拆分：overview=线（事实链+克制判断≤3短点）；diagnosis.summary=面（一句枢纽+三问支撑）；禁止两块互相复述整段。
若本轮已注入外部方法：三个字段合起来可读出白话三问，但不要提前写完整育人落点与三区处方；
要用中文写出方法概念痕迹；禁止英文/拼音方法名与表格章节出处，禁止注水冗长。
不得写成与未启用方法时几乎同构的目录复述或零散补丁。
逐单元批语必须覆盖输入中的每个书写单元，包括 verdict=correct 的单元；题号、页码必须沿用输入。不得输出百分制分数。'''


def _with_open_material_output_contract(system: str, feedback_runtime) -> str:
    from .feedback_material_kinds import is_open_material
    if is_open_material((feedback_runtime.context or {}).get('material_type')):
        return system + OPEN_MATERIAL_OUTPUT_CONTRACT
    return system


def pass2_system(subject: str, memory: Optional[Dict[str, Any]] = None, profile: Optional[Dict[str, Any]] = None, ontology: Optional[Dict[str, Any]] = None, *, feedback_runtime=None) -> str:
    """构建 Pass2 system prompt：注入认知三区 + 教育目标 + 课标（按 memory 过滤） + ontology 三区。"""
    if feedback_runtime is not None:
        from .feedback_prompts import diagnostic_system
        return _with_open_material_output_contract(
            diagnostic_system(feedback_runtime, 'pass2_full', memory=memory, ontology=ontology),
            feedback_runtime,
        )
    stage = ontology.get('stage') if isinstance(ontology, dict) else None
    all_entries = load_curriculum_entries(subject, stage=stage)
    entries = _filter_curriculum_by_memory(all_entries, memory)
    base = PASS2_SYSTEM_BASE.format(
        zone_table=_format_zone_table(),
        goal_block=_format_goal_block(),
        subject=subject,
        kp_count=len(entries),
        curriculum_block=_format_curriculum_block(entries) or '(无)',
    )
    return base + _format_profile_summary(profile) + _format_ontology_zones_for_pass2(ontology)


PASS2_FEEDBACK_SYSTEM_BASE = '''你是一位中小学批改老师。下面已经给出该学生在本份作业上的「三区结论」（来自 学科数字孪生体 student_ontology），请仅依据这些结论，对每道**错题/部分错/未作答/不确定**的题目写一条**精准、有温度**的批语。

## 关键约束

- **以三区结论为准**：每条 `per_question_feedback` 必须从给定 zones 中选择最贴近的区域（blind_spot / friction_zone / zpd），不要新创区域，也不要把"已正确"的题目纳入。
- **若某题对应的知识点未出现在任一区域**：`zone` 留空字符串 `""`，`comment` 写"信息不足，建议人工复核"。
- **comment ≤50 字**：直接指出问题或方向，不要套话；并可合理吸收课标反馈通则。
- **禁止引用课标原文/文件名**（如"义务教育数学课程标准 2022 年版"）。
- **题号一律使用 `qid_global`**，格式 `p<page>:<id>`。
- **批语应与三区 rationale 口径一致**：盲区→指出根本概念欠缺；内耗区→指出干扰来源；最近发展区→肯定进步并给一个突破点提示。
- **若错题带有 wgb_trust_tier**：critical 批语略留余地（两步/三步黑可提一句「建议对照原卷加强核实」；一步黑不必句句提醒）；careful 稍留余地；confident/normal 按常规写。可见文案勿用生僻自造词。

## 输出 schema（严格遵守，输出纯 JSON 对象，不加 Markdown 围栏）

{
  "per_question_feedback": [
    {
      "page": 1,
      "id": "1-1",
      "qid_global": "p1:1-1",
      "zone": "blind_spot|friction_zone|zpd|",
      "comment": "针对本题的精准批语（带三区视角，50字以内）"
    }
  ]
}'''


def pass2_feedback_system(subject: str, *, feedback_runtime=None) -> str:
    from .page_feedback import PAGE_FEEDBACK_PROTOCOL
    if feedback_runtime is not None:
        from .feedback_prompts import diagnostic_system
        system = diagnostic_system(feedback_runtime, 'pass2')
        return _with_open_material_output_contract(system, feedback_runtime) + '\n' + PAGE_FEEDBACK_PROTOCOL
    return PASS2_FEEDBACK_SYSTEM_BASE + '\n' + PAGE_FEEDBACK_PROTOCOL


def pass2_feedback_user(memory: Dict[str, Any], ontology: Dict[str, Any], *, feedback_runtime=None) -> str:
    """构建 yq v2.5 Pass2 轻量批语 user prompt：只给 ontology 三区和错题。"""
    from .feedback_material_kinds import is_open_material
    open_material = bool(
        feedback_runtime is not None
        and is_open_material((feedback_runtime.context or {}).get('material_type'))
    )
    zones = ontology.get('zones') or {}

    def _slim_zone(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for entry in entries or []:
            evidence = list(entry.get('evidence') or [])
            evidence.extend(entry.get('content_context_evidence') or [])
            for cluster in entry.get('error_clusters') or []:
                evidence.extend(cluster.get('evidence') or [])
            out.append({
                'knowledge_point': entry.get('knowledge_point'),
                'rationale': entry.get('rationale'),
                'evidence_question_ids': list(dict.fromkeys(evidence))[:8],
                'stability': entry.get('stability'),
                'trend': entry.get('trend'),
                'evidence_basis': entry.get('evidence_basis', 'content'),
                **({'content_context_evidence': list(entry['content_context_evidence'])} if entry.get('content_context_evidence') else {}),
            })
        return out

    zone_view = {
        bucket: _slim_zone(zones.get(bucket, []))
        for bucket in ('blind_spot', 'friction_zone', 'zpd')
    }
    fields = (
        'page', 'id', 'qid_global', 'verdict', 'stem_excerpt',
        'student_answer', 'correct_answer', 'error_type', 'knowledge_point',
    )
    if open_material:
        fields = fields + ('understanding', 'note_role', 'annotation_links', 'assessment_status',
                           'diagnostic_eligible', 'page_origin', 'cross_page', 'cross_page_resolved',
                           'material_check', 'assessment_reason', 'printed_text_marked',
                           'handwritten_text_marked', 'marking_warnings', 'observation_eligible')
    slim_errors: List[Dict[str, Any]] = []
    from .material_markings import open_units
    feedback_units = open_units(memory, feedback_runtime.context['material_type']) if open_material else memory.get('error_questions') or []
    for question in feedback_units:
        slim_errors.append({
            key: question[key]
            for key in fields
            if key in question
        })
    # 附上逐题白灰黑可信度，批语措辞分层
    from .wgb_trust import attach_trust_to_questions
    wgb_trust = ontology.get('wgb_trust') if isinstance(ontology, dict) else None
    slim_errors = attach_trust_to_questions(slim_errors, wgb_trust)

    payload = {
        'subject': memory.get('subject'),
        'sample_id': memory.get('sample_id'),
        'zones': zone_view,
        'error_questions': slim_errors,
        'evolution_narrative': ontology.get('evolution_narrative', ''),
        'page_understanding': memory.get('page_understanding', []),
    }
    if isinstance(wgb_trust, dict) and wgb_trust.get('tier_counts'):
        payload['wgb_trust_summary'] = {
            'tier_counts': wgb_trust.get('tier_counts'),
            'cross_counts': wgb_trust.get('cross_counts'),
            'need_verify_count': len(wgb_trust.get('need_verify') or []),
            'unit_word': wgb_trust.get('unit_word'),
            'protocol_hint': wgb_trust.get('protocol_hint'),
        }
    if open_material:
        intro = (
            '以下是该学生在本份作文/笔记上的三区结论与全部书写单元（含正确单元）。\n'
            '请整合 understanding 与 correct_answer 中的形成性评价，按系统提示输出纯 JSON：'
            '顶层包含 `open_material_overview` 和 `per_question_feedback`，每个单元都必须有批语。\n\n'
        )
    else:
        intro = (
            '以下是该学生在本份作业上的三区结论与所有错题列表。\n'
            '请按系统提示输出纯 JSON：仅含 `per_question_feedback` 字段。\n\n'
        )
    from .page_feedback import PAGE_FEEDBACK_PROTOCOL
    return intro.replace('仅含 `per_question_feedback` 字段', '包含 `per_question_feedback` 字段') + (
        PAGE_FEEDBACK_PROTOCOL + '\n' if payload['page_understanding'] else ''
    ) + json.dumps(payload, ensure_ascii=False)

MATH_VERIFICATION_SUFFIX = '''
【验算要求】
1. 对每道计算题，请先识别学生作答内容，再自行独立计算出正确答案。
2. 将你的计算结果与学生答案逐位对比，确认是否一致。
3. 若不一致，在 error_type 中具体说明错误环节（如"进位遗漏"、"退位错误"、"乘法口诀记错"等）。
4. 对应用题，请先理解题意、列出算式，再计算结果；correct_answer 填写最终数值。
5. 学生答案为代数表达式时，必须独立化简/规范化后再判断，并把与题意匹配的标准形式写入 correct_answer；不得把学生式子原样复制为 correct_answer 后直接判对。
6. 求最终数量、差、和、结果或填写最终答案时，仍有可完成运算或可合并同类项通常不得判 correct；例如 50a-30a 应化简为 20a，思路正确但未化简时判 partial，error_type 填 final_form_required。若题目仅要求列式或“用含有字母的式子表示”，则不强制展开或改变能准确表达数量关系的结构。
7. 你的计算过程请在思考中完成，最终输出仅包含 JSON，不输出任何 Markdown 或其他内容。'''

CHINESE_CROSS_PAGE_SUFFIX = '''
【语文阅读题特别提示】
若本页包含阅读理解题，请判断：
- 阅读材料（短文/诗歌/段落）是否完整出现在本页？
  若短文开头或结尾明显缺失，请设置 boundary.continues_from_prev 或 continues_to_next。
- 阅读小题是否有前续题目缺失（如题号从第2题开始、第1题不见）？
  若有，设置 continues_from_prev，对缺少前文的小题设 cross_page = true, verdict = "uncertain"。
仅标记你确实观察到截断证据的情形，不要过度标记。'''

CROSS_PAGE_SYSTEM = '''你是一位中小学作业批改老师。现在给你的是连续的若干页作业图片，
这些页面之间存在跨页题目（题干或阅读材料被页面切断）。

请将这几页图片视为一个连续的整体来阅读和理解，重点关注：
1. 跨页的阅读材料：将前后页的短文/材料合并为完整文本来理解。
2. 跨页的题目：根据完整题干和完整的学生作答给出判断。
3. 仅输出需要新增或修正的题目。对于已经可以在单页上完整判断的题目，
   不必重复输出（避免意外覆盖正确判断）。

输出 JSON，格式与原有 pass1_json schema 完全一致，顶层为：
{
  "cross_page_group": [<页码列表>],
  "corrections": [
    {
      "page": <int>,
      "id": "<题目id>",
      "verdict": "correct|wrong|partial|unanswered|uncertain",
      "correct_answer": "<答案或null>",
      "error_type": "<可空>",
      "knowledge_point": "<可空>",
      "cross_page": true,
      "cross_page_resolved": true
    }
  ]
}

不确定时保持 verdict 为 "uncertain"，不要强行给出答案。
严格输出 JSON 对象，不含任何 Markdown 围栏或额外文字。'''


def pass1_user_prompt(subject: str, page_num: int, prior_context: Optional[str] = None, *, feedback_runtime=None) -> str:
    if feedback_runtime is not None:
        from .feedback_prompts import user_prompt
        return user_prompt(feedback_runtime, 'grade', page_num, payload=None, prior_context=prior_context, supplement=False)
    hint = _SUBJECT_HINTS.get(subject, '')
    prompt = (
        f'请批改以下第 {page_num} 页作业（科目：{subject}）。\n'
        f'{hint}\n'
        '转写 student_answer 时只保留最终有效手写内容（忽略删除线/涂改），不要把印刷题干当成学生答案。\n'
        '严格输出符合 schema 的 JSON 对象，不要包含任何其他文字。'
    )
    if subject == 'math':
        prompt += MATH_VERIFICATION_SUFFIX
    elif subject == 'chinese':
        prompt += CHINESE_CROSS_PAGE_SUFFIX
    if prior_context:
        prompt = prior_context.rstrip() + '\n\n' + prompt
    return prompt


def pass1_detect_user_prompt(subject: str, page_num: int, *, feedback_runtime=None) -> str:
    if feedback_runtime is not None:
        from .feedback_prompts import user_prompt
        return user_prompt(feedback_runtime, 'detect', page_num, payload=None, prior_context=None, supplement=False)
    prompt = (
        f'请分析以下第 {page_num} 页作业扫描图（科目：{subject}），'
        f'识别全部题目并给出每道题学生手写作答区域的 position。\n'
        '本阶段只做版面检测：严格区分印刷题干与手写作答，position 须完整包住每小题全部手写内容（含「答：……」）。\n'
        '大题下多小题且间距较远时，务必填写 parent_group_id 与 parent_stem_excerpt。\n'
        '不要转写答案、不要判断对错。\n'
        '每题须输出 layout_confidence（0–100 综合版面置信度，勿过度自信）。\n'
        '每题须输出 is_application_major_problem；数学应用题大题（非填空题）及其小题填 true，'
        '看图填空/表格填空/公式或括号填空等填空式题目即使有情境也填 false，其它题填 false。\n'
        '每题须输出 final_unit_requirement（required|forbidden|optional）；数学应用题中前问列含字母式子、'
        '后问“当字母=数时”代入求值的小问填 forbidden；该值只要求计算过程末值不带单位，最终答话仍需单位/量词；非数学题填 optional。\n'
        '严格输出符合 schema 的 JSON 对象，不要包含任何其他文字。'
    )
    if subject == 'chinese':
        prompt += (
            '\n若本页出现“给加点字选择正确的读音”题，必须按 system 规则为该题输出'
            '逐字 answer_slots（含两个 candidate_regions 与黑笔 mark_position），'
            '但不得在版面阶段判断 selected_answer。'
        )
    return prompt


def _has_chinese_sentence_contraction_question(detected: Dict[str, Any]) -> bool:
    """Return whether this detected page contains a Chinese sentence-contraction item."""
    for question in detected.get('questions') or []:
        if not isinstance(question, dict):
            continue
        text = ''.join(
            str(question.get(field) or '')
            for field in ('parent_stem_excerpt', 'stem_excerpt')
        )
        normalized = ''.join(text.split())
        if '缩句' in normalized:
            return True
        if '缩写' in normalized and any(
            marker in normalized
            for marker in ('句子', '一句', '原句', '最恰当的一项')
        ):
            return True
    return False


def _has_chinese_pronunciation_answer_slots(detected: Dict[str, Any]) -> bool:
    for question in detected.get('questions') or []:
        if not isinstance(question, dict):
            continue
        if (
            is_chinese_pronunciation_selection_question(question)
            and isinstance(question.get('answer_slots'), list)
            and question.get('answer_slots')
        ):
            return True
    return False


def _has_english_parenthesized_choice_slots(detected: Dict[str, Any]) -> bool:
    for question in detected.get('questions') or []:
        if not isinstance(question, dict):
            continue
        slots = question.get('answer_slots')
        if not isinstance(slots, list):
            continue
        if any(
            isinstance(slot, dict)
            and str(slot.get('slot_type') or '').strip() == 'parenthesized_choice'
            for slot in slots
        ):
            return True
    return False


def _has_math_operation_law_name_question(detected: Dict[str, Any]) -> bool:
    """Detect pages that ask students to name a concrete arithmetic law."""
    for question in detected.get('questions') or []:
        if not isinstance(question, dict):
            continue
        text = ''.join(
            str(question.get(field) or '')
            for field in ('parent_stem_excerpt', 'stem_excerpt')
        )
        normalized = ''.join(text.split())
        if not normalized:
            continue
        arithmetic_context = (
            '乘法' in normalized
            or '加法' in normalized
            or normalized.count('×') >= 2
            or normalized.count('+') >= 2
        )
        if not arithmetic_context:
            continue
        if '运算律' in normalized and any(
            marker in normalized
            for marker in ('运用', '什么', '哪种', '名称', '是')
        ):
            return True
        if any(
            marker in normalized
            for marker in ('这里运用了', '这里运用的', '可以运用', '所用的律')
        ):
            return True
    return False


def pass1_grade_user_prompt(
    subject: str,
    page_num: int,
    detected: Dict[str, Any],
    prior_context: Optional[str] = None,
    *, feedback_runtime=None, source_document_sha256="",
) -> str:
    if feedback_runtime is not None:
        from .feedback_prompts import user_prompt
        return user_prompt(feedback_runtime, 'grade', page_num, payload=detected, prior_context=prior_context, supplement=False, source_sha256=source_document_sha256)
    hint = _SUBJECT_HINTS.get(subject, '')
    detect_json = json.dumps(detected, ensure_ascii=False, indent=2)
    prompt = (
        f'请批改以下第 {page_num} 页作业（科目：{subject}）。\n'
        f'题目清单已由上一阶段给出，请逐题补全 student_answer / correct_answer / verdict 等字段，'
        f'**不要修改 id、parent_group_id、parent_stem_excerpt、position、cross_page、cross_page_note、stem_excerpt、is_application_major_problem、final_unit_requirement、answer_slots**。\n'
        f'{hint}\n'
        '每题须按顺序输出：student_answer（识别）→ recognition_confidence → understanding（仅题意与作答理解，不涉及对错）→ understanding_confidence → correct_answer/verdict 等（批改）→ grading_confidence。\n'
        '批改时务必结合 parent_stem_excerpt（大题条件）理解小题；转写 student_answer 时须覆盖该题全部手写作答（含「答：……」），不要只转写算式一行。\n'
        '【已检测题目清单】\n'
        f'{detect_json}\n'
        '严格输出符合 schema 的 JSON 对象（仅 questions 数组即可），不要包含任何其他文字。'
    )
    if subject == 'math':
        prompt += MATH_VERIFICATION_SUFFIX
        # 用户消息末尾再做一次逐页硬审计；正式输出字段与批改职责保持不变。
        prompt += MATH_PASS1_GRADE_USER_AUDIT
        if _has_math_operation_law_name_question(detected):
            prompt += '\n' + MATH_OPERATION_LAW_FULL_NAME_GRADE_RULES
    if subject == 'chinese' and _has_chinese_sentence_contraction_question(detected):
        prompt += '\n' + CHINESE_SENTENCE_CONTRACTION_PAGE_RULES
    if subject == 'chinese' and _has_chinese_pronunciation_answer_slots(detected):
        prompt += '\n' + CHINESE_PRONUNCIATION_SELECTION_GRADE_RULES
    if subject == 'english' and _has_english_parenthesized_choice_slots(detected):
        prompt += '\n' + ENGLISH_PARENTHESIZED_CHOICE_SLOT_GRADE_RULES
    if prior_context:
        prompt = prior_context.rstrip() + '\n\n' + prompt
    return prompt


def pass1_detect_supplement_user_prompt(subject: str, page_num: int, detected: Dict[str, Any], *, feedback_runtime=None) -> str:
    if feedback_runtime is not None:
        from .feedback_prompts import user_prompt
        return user_prompt(feedback_runtime, 'detect', page_num, payload=detected, prior_context=None, supplement=True)
    detect_json = json.dumps(detected, ensure_ascii=False, indent=2)
    return (
        f'请分析以下第 {page_num} 页作业扫描图（科目：{subject}）。\n'
        '【已有版面检测结果（最终结论，除 layout_confidence 外均不得修改）】\n'
        f'{detect_json}\n'
        '你的任务：**仅**为 questions 中每题补充 layout_confidence（0–100 综合版面置信度）。\n'
        '校准：勿整体给 85–95；跨页/页首尾/潦草/特殊题型应明显低于清晰书写无涂改无歧义的题；同页各题须有差异。\n'
        '不得修改 id、parent_group_id、parent_stem_excerpt、stem_excerpt、position、cross_page、cross_page_note 等任何已有字段。\n'
        '严格输出 JSON 对象，questions 数组每项至少含 id 与 layout_confidence，不要包含任何其他文字。'
    )


def pass1_grade_supplement_user_prompt(
    subject: str,
    page_num: int,
    detected: Dict[str, Any],
    graded: Dict[str, Any],
    prior_context: Optional[str] = None,
    *, feedback_runtime=None,
) -> str:
    if feedback_runtime is not None:
        from .feedback_prompts import user_prompt
        return user_prompt(feedback_runtime, 'grade', page_num, payload={'detected': detected, 'graded': graded}, prior_context=prior_context, supplement=True)
    hint = _SUBJECT_HINTS.get(subject, '')
    detect_json = json.dumps(detected, ensure_ascii=False, indent=2)
    grade_json = json.dumps(graded, ensure_ascii=False, indent=2)
    prompt = (
        f'请批改以下第 {page_num} 页作业（科目：{subject}）。\n'
        f'{hint}\n'
        '【已检测题目清单（版面信息，含跨页上下文）】\n'
        f'{detect_json}\n\n'
        '【已有识别与批改结果（最终结论，不得修改）】\n'
        f'{grade_json}\n\n'
        '你的任务：在**不改变** student_answer、correct_answer、verdict、error_type、knowledge_point、recurrence_hint 的前提下，'
        '为每题按顺序补充 recognition_confidence → understanding → understanding_confidence → grading_confidence。\n'
        'understanding 只做识别后的题意/作答理解（2–3句）：此题要学生做什么、大题题干、是否跨页、本题要求、学生写了什么等；'
        '**禁止**写对错、准确与否、是否符合标准等批改性表述。\n'
        '三项置信度须分别评估、数值通常不应相同；勿整体 85–95，按字迹/跨页/歧义合理拉开差距。\n'
        '跨页题须结合 detect 中 parent_stem_excerpt / cross_page 信息理解题意（仍不判对错）。\n'
        '严格输出 JSON 对象（仅 questions 数组即可），每项至少含 id 与上述四个新增字段，不要包含任何其他文字。'
    )
    if subject == 'math':
        prompt += '\n（本任务只补理解与置信度，勿重算或改动 verdict。）'
    if prior_context:
        prompt = prior_context.rstrip() + '\n\n' + prompt
    return prompt


def build_prior_context(order_index: int, total: int, top_recurring_kps: List[str]) -> str:
    """渲染 ≤120 token 的前序 session 摘要块（改编自 yq prompts.build_prior_context §3.2）。

    top_recurring_kps：前几个 session 聚合后 error_count≥2 且 error_rate≥0.4 的 Top-3 KP。
    空列表表示首个 session 或尚无高频错点（调用方应传 order_index>1 时才调用本函数）。
    """
    kps = '、'.join(top_recurring_kps[:3]) if top_recurring_kps else '（暂无明显高频错点）'
    return (
        '【前序练习概要（时序上下文，仅供参考，不要照搬判定）】\n'
        f'本份作业是该生连续完成的第 {order_index} 次练习（共 {total} 次）。\n'
        f'此前各次练习中反复出错的知识点：{kps}。\n'
        '注意：若本页出现这些知识点，请如实判定对错，并在 error_type 中说明\n'
        '是否与既往同类错误一致；recurrence_hint 字段填 new/recurring/na。\n'
        '**严禁因之前错就主观判这次也错——必须基于本页学生作答客观判定。**'
    )


def cross_page_user_prompt(
    group: List[int],
    context_notes: List[str],
    pending_questions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    notes_text = '\n'.join(
        f'  第 {page_num} 页：{note}'
        for page_num, note in zip(group, context_notes)
    )
    prompt = (
        f'以下是连续的第 {group[0]}–{group[-1]} 页作业图片（共 {len(group)} 页）。\n'
        f'已知的跨页信息：\n{notes_text}\n\n'
    )
    if pending_questions:
        lines = []
        for item in pending_questions:
            lines.append(
                f"- 第 {item.get('page')} 页 id={item.get('id')!r} "
                f"verdict={item.get('verdict')!r} cross_page={item.get('cross_page')}\n"
                f"  题干摘录：{item.get('stem_excerpt')}\n"
                f"  学生作答：{item.get('student_answer')}\n"
                f"  当前 error_type：{item.get('error_type') or '（空）'}"
            )
        prompt += (
            '【待修补题目清单】以下题目因跨页上下文不足被标为 uncertain，'
            '请结合多页图片合并材料后给出批改结论（须在 corrections 中逐题输出）：\n'
            + '\n'.join(lines)
            + '\n\n'
        )
    prompt += '请识别跨页题目的完整内容并给出批改结论，仅输出 corrections JSON。'
    return prompt
