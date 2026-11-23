# -*- coding: utf-8 -*-
"""把本子语义关键词空间收成批改可用的专业语境，并写出报告开头的期望水准。

用户看到的是课标、考点、题型和素养量规能接得住的说法。
不把四色、DMT、象限等内部说法写进批语或报告。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

_JARGON_RE = re.compile(
    r"四色|DMT|象限|共识区|温度计|螺旋|主体本体|机知|人知|红O|蓝O|紫O|绿O"
)


def strip_internal_jargon(text: str) -> str:
    cleaned = _JARGON_RE.sub("", str(text or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def load_semantic_professional_brief(username: str, *, max_chars: int = 1600) -> str:
    """读取已梳理好的本子关键词空间，只留专业问题、专业词和要问清的点。"""
    name = str(username or "").strip()
    if not name:
        return ""
    path = os.path.normpath(
        os.path.join(".", "received_dir", "user_raw_file", name, "cardCondense", "bookTopKeywords.json")
    )
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    lines: List[str] = []
    core = strip_internal_jargon(str(data.get("core_issue") or ""))
    if core:
        lines.append("本子要抓住的专业问题：" + core[:420])
    words = [str(w).strip() for w in (data.get("top10") or []) if str(w).strip()][:10]
    if words:
        lines.append("批改要落到的专业内容：" + "、".join(words))
    subs = []
    for item in data.get("sub_issues") or []:
        text = strip_internal_jargon(str(item or ""))
        if text:
            subs.append(text[:90])
        if len(subs) >= 6:
            break
    if subs:
        lines.append("具体要问清的：" + "；".join(subs))
    reasons = data.get("reasons") if isinstance(data.get("reasons"), dict) else {}
    reason_bits = []
    for key in ("top1", "top3", "top5"):
        bit = strip_internal_jargon(str((reasons or {}).get(key) or ""))
        if bit:
            reason_bits.append(bit[:160])
    if reason_bits:
        lines.append("这些内容在本子里怎么用：" + " ".join(reason_bits)[:480])
    return strip_internal_jargon("\n".join(lines))[:max_chars]


def competency_context_block(subject_label: str = "") -> str:
    """按义务教育课标的要求批改，并吸收量规把大词落到行为的办法。分项是我们自己的。"""
    subject = str(subject_label or "").strip()
    return (
        "【批改语境，必须遵守】\n"
        "用语是报告的一部分。句子通顺，含义确定。先写清对谁说：学是对学生说，教是对教师说，"
        "育是对教师说如何促成变化。家长需要知道的配合另写一句，不把课堂步骤再讲一遍。\n"
        "先写当前这一步要人完成什么。这一步是承上启下的那一层，用几十字说清，再说它下面能核对的知识和卷面，"
        "再说它上面的方向、期望和牵引。不要先罗列知识点或题号再贴素养名称，也不要先写素养名称再往下找题。\n"
        "每段稍长的话，先用几十字把这一步说准确，再分点。几十字说不清，就不要展开。\n"
        "写考查内容时，先写知识、情境、这一步要做什么。有图就写图上是什么关系，没有图不要编。题号只放在括号里。"
        "拿掉括号以后，句子仍然要能看懂。不要只报题号，也不要改成另一串内容的堆砌。\n"
        "不要自造说法，不要把一组题概括成题干和课标里都没有的名词。只用题干里已有的说法、该学科课标和教材的正式名称、"
        "以及下面19项和36项的原名。\n"
        "不要使用这些说法：对上了、碰得到、站稳、已稳、已走通、走得最稳、达到档、断点、"
        "这次看见的、往上接到、只选一种学法、铰在、铺满、说不清、一变就断、站不住、对得上、多条件覆盖。\n"
        "档位只写「达到」「基本达到」「尚未达到」，不要写成「达到档」。\n"
        "知识和卷面要写准确，这是这一步下面可以核对的部分，不是整篇报告的开头。题目作对，是这一步完成的结果。\n"
        "做错、空着、部分做对要分开。空着算未掌握，不要写成已经会。多数人做对而该生做错或空着，要写出来。"
        "同一类内容里有的做对、有的做错或空着，对照着写，不要合成一句。前序只在证据里有时才写，不要编以前的失分。\n"
        "能力名称大约七到八成使用下面的正式名称，两到三成写课标中的对应关系、教与学和三个档位。"
        "正式能力只写本次作答能够对应的项目，名称用这19个原名：问题解决能力、学习动力与自我调节能力、自主学习能力、"
        "实践与劳动能力、团队协作能力、创新设计能力、科学理解能力、系统思考能力、反思改进能力、"
        "信息处理能力、证据分析与判断能力、数理思考能力、审美与艺术创造能力、社会责任与公共参与能力、"
        "表达沟通能力、文化理解与交流能力、探究研究能力、数据分析能力、健康与运动能力。"
        "每项下面只写36个可观察行为中本次能够对应的，原名不要改：设定目标、制定学习计划、自我修订、反馈、"
        "情绪识别、创造模型、联系生活实际、收集证据、发现问题、分析问题、提出问题、构建解释、"
        "团队目标和角色、团队效能、规则、劳动认知、艺术鉴赏、选择相关原始资料、综合多种原始资料、"
        "艺术创作、设计方案、估算结论、原型设计与试验、物质与结构认知、证据选择、建立与运用模型、"
        "评估方案、系统性思考反思迁移、数据、数据整理分析与应用、表达媒介、主题与中心思想、"
        "用词选择与积极沟通、信息性与解释性文本创作、口头表达与朗读背诵、反思能力。"
        "没有依据的项目不要补写，不要把19项或36项全部列出，不要写成排名。"
        "能够对应的能力写 1 到 5 的素养分，保留一位小数，不要按做对题数换算。"
        "依据写清是哪一种考查内容、哪一步，题号放在括号里。几道题若是同一内容，写它们的联系，不要另起一个名称。\n"
        "只写本次作答能够支持的内容。下面六条是判断口径，不要把这些简称写进报告：\n"
        "1. 知识是否正确：考查内容和关键步骤是否正确。\n"
        "2. 能力是否明确：这个考查内容对应课标中的哪一种能力，使用正式名称。\n"
        "3. 能否迁移：换成相近的问法或生活情境后，是否仍然正确。\n"
        "4. 学习方式：依据中能看出学生是在听讲、独立思考、动手实践，还是只在核对答案。\n"
        "5. 内容联系：这几道题是否考查同一内容，或与笔记本中的其他内容有联系。\n"
        "6. 人的变化：只写这次卷面能够对应的价值观、品格或关键能力，落到具体题目，不打分，不给全班排名。\n"
        "语文用义务教育2022的文化自信、语言运用、思维能力、审美创造，四项是一个整体，以语言运用为基础。"
        "实践对应识字与写字、阅读与鉴赏、表达与交流、梳理与探究中本次实际出现的。"
        "思维写直觉思维、形象思维、逻辑思维、辩证思维中本次能够对应的，不要四种都写。\n"
        "数学用三个会用：会用数学的眼光观察现实世界、会用数学的思维思考现实世界、会用数学的语言表达现实世界。"
        "眼光主要是数感、量感、符号意识、几何直观、空间观念、创新意识；"
        "思维主要是运算能力、推理意识或推理能力；"
        "表达主要是数据意识或数据观念、模型意识或模型观念、应用意识。"
        "本次题目实际用到几种就写几种，每种都要落到具体题目和步骤。不能判断为高中内容时，不要写成数学抽象、逻辑推理。\n"
        "英语用语言能力、文化意识、思维品质、学习能力。"
        "语言能力看感知、体验、积累和运用，以及能否进行有意义的沟通；"
        "学习能力看是否会运用学习策略、寻找学习渠道，而不是只增加词汇量。\n"
        "其他学科用该学科课标的核心素养名称，不要编。\n"
        "人的核心素养有两套国家文本，都是育人目标，不是贴在学生身上的标签。\n"
        "义务教育课程方案的培养目标是有理想、有本领、有担当。"
        "三科课标把核心素养定义为：学生通过课程学习逐步形成的正确价值观、必备品格和关键能力，是课程育人价值的集中体现。\n"
        "《中国学生发展核心素养》是三个方面、六大素养：文化基础下的人文底蕴、科学精神；自主发展下的学会学习、健康生活；社会参与下的责任担当、实践创新。"
        "知引在这三方面下另写了一长串细分，那是知引自己的拆法，不要把那张清单当成国家的十八个基本要点。\n"
        "这些大词禁止直接当作评价结论。要写成这次卷面看得到的表现，并说明它对应哪一个目标。"
        "数学里看课标写明的内涵：好奇心和想象、实事求是的科学态度、讲道理且有条理的思维品质、理性精神、应用意识与实践能力，以及四基、四能和正确的情感、态度、价值观。"
        "语文里看总目标：正确的世界观、人生观、价值观，社会责任意识，有理有据、负责任地表达，实事求是、崇尚真知。"
        "英语里看文化意识中的家国情怀、品格和社会责任感，以及学习能力中的终身学习。"
        "卷面看不出这些，就写这次作业还看不出人的变化。不要写成独立作答、做完过程、对结果负责、做事有条理。\n"
        "符号意识、应用意识、运算能力这些是学科核心素养的表现，写在学科素养里。它们不是知引19项能力的代名，不要因为出现了课标里的一个词，就改写成另一项19项能力。\n"
        "三个档位要写成可以核对的行为，不能只更换形容词。"
        "尚未达到：考查内容或关键步骤尚未正确，先补正这一步，暂不要求迁移。"
        "基本达到：主要步骤基本正确，但不能说明它对应哪一种能力，或只写出了结果。"
        "达到：步骤完整，能说出对应的能力，换成相近情境后仍然正确。\n"
        "学、教、育分成三条，对谁说要分开。学只写依据中能够看出的一种，是对学生说的：语文是自主、合作、探究；"
        "数学是听讲、独立思考、动手实践、自主探索、合作交流；"
        "英语是在体验中学习、在实践中运用、在迁移中创新。不要同时安排多种学习方式。\n"
        "教是对教师说的，分别写清为什么教、教什么、教到什么程度、怎么教。教师是组织者、引导者和合作者。"
        "先讲清这一步和它的适用范围，再让学生在新的同类内容里使用。评价与教、学说的是同一件事。\n"
        "育是对教师说的，写立德树人在这一步里露出来的正确价值观、必备品格或关键能力，用上面课标里的内涵，扣住具体作答。"
        "学习方法、做题步骤、做事有条理，写在学或教里，不能拿来充当育。"
        "家长若需要一句，只写家里能配合的那一件事，不重复教里的课堂步骤。"
        "布置了但没有作答的题计入未掌握，并按卷面分辨是不会，还是畏难、嫌字多不愿写；没有卷面差异就不要写态度。学、教、育里的育，以及后文凡写到育人的地方，都按这个要求写。\n"
        "阅读只在本次确有阅读（课文、语篇、整本书、阅读题）时写：阅读、思考和运用写在一起，不写打卡，不写读了多少本。"
        "能够判断为小学时，写阅读是否展开；能够判断为初中时，写阅读是否深入。不能判断学段时不写。纯计算题不要写成阅读。\n"
        "最近发展只选择一种与本次作答相符的做法：让学生说出步骤，或与某同学对照同一步骤，或在一个小任务中使用一次。"
        "本次确有阅读时，才写读完一段再回来做题。不要并列多种做法。\n"
        f"这份材料的学科：{subject or '按材料判断'}。\n"
        "禁止写出四色、DMT、象限、共识区、温度计、螺旋、主体本体。\n"
    )


def semantic_grading_guidance(username: str) -> str:
    """附在批改阶段提示后：约束批语和单人整篇诊断，不改 JSON 字段。"""
    brief = load_semantic_professional_brief(username)
    return (
        "\n"
        + competency_context_block("")
        + ("【本子专业内容】\n" + brief + "\n" if brief else "")
        + "整篇 diagnosis.summary 在【看到了什么】之前，先写「本次期望水准」，必须换行分点，禁止写成一整段："
        "先用几十字写当前这一步要完成什么；"
        "再写一条素养链（这一步 → 课标里的学科素养及这次哪一处作答看得出来 → 人的变化看得出或还看不出），不要把第一截写成知识点或题号清单；"
        "三条分别以「学：」「教：」「育：」开头，学对学生说，教和育对教师说；"
        "三条分别以「达到：」「基本达到：」「尚未达到：」开头，每档都写这一步做到什么程度，不能三档只更换形容词；"
        "再写一句本次更希望该生达到哪一档。\n"
        "【看到了什么】【这说明什么】【下一步做什么】仍各占一行开头，每问下面用短句分点，不要大段。"
        "下一步要按该生眼下情况说是保持还是再进一步，必要时点一种贴题的学法，不要空说认真细心。\n"
        "每条题目批语保持简短，但要点明具体考点：落到哪一档、差在哪一步。不要改 JSON 字段名。\n"
    )


def _focus_items(report: Dict[str, Any], *, limit: int = 3) -> List[str]:
    found: List[str] = []
    for brief in report.get("question_briefs") or []:
        if not isinstance(brief, dict):
            continue
        text = str(brief.get("stem") or brief.get("parent_stem") or brief.get("knowledge_point") or "").strip()
        text = re.sub(r"\s+", " ", text)[:48]
        if text and text not in found:
            found.append(text)
        if len(found) >= limit:
            break
    return found


def _verdict_kind(verdict: Any) -> str:
    value = str(verdict or "").strip().lower()
    if value in ("wrong", "incorrect", "false", "错误"):
        return "wrong"
    if value in ("unanswered", "blank", "empty", "未作答"):
        return "blank"
    if value in ("partial", "部分正确"):
        return "partial"
    if value in ("uncertain", "灰", "gray", "grey", ""):
        return ""
    return "ok"


def paper_situation(student_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """全班逐题内容和作答分布。供期望水准和个人、班级报告共用，避免各写各的。"""
    questions: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for report in student_reports or []:
        name = str(report.get("display_name") or "").strip()
        for brief in report.get("question_briefs") or []:
            if not isinstance(brief, dict):
                continue
            qid = str(brief.get("qid") or "").strip() or "未编号"
            slot = questions.get(qid)
            if slot is None:
                stem = _clip_sentence(str(brief.get("stem") or ""), 100)
                parent = _clip_sentence(str(brief.get("parent_stem") or ""), 60)
                content = stem or parent
                if parent and stem and parent not in stem:
                    content = _clip_sentence(parent + "。" + stem, 140)
                slot = {
                    "id": qid,
                    "content": content,
                    "figure": _clip_sentence(str(brief.get("figure") or ""), 80),
                    "ok": [],
                    "wrong": [],
                    "blank": [],
                    "partial": [],
                }
                questions[qid] = slot
                order.append(qid)
            kind = _verdict_kind(brief.get("verdict"))
            if kind and name and name not in slot[kind]:
                slot[kind].append(name)
    rows: List[Dict[str, Any]] = []
    for qid in order[:30]:
        slot = questions[qid]
        rows.append({
            "id": slot["id"],
            "content": slot["content"],
            "figure": slot["figure"],
            "ok_count": len(slot["ok"]),
            "wrong": slot["wrong"],
            "blank": slot["blank"],
            "partial": slot["partial"],
        })
    by_student: Dict[str, List[str]] = {}
    for report in student_reports or []:
        sid = str(report.get("student_index"))
        notes: List[str] = []
        groups: Dict[str, List[str]] = {}
        for brief in report.get("question_briefs") or []:
            if not isinstance(brief, dict):
                continue
            qid = str(brief.get("qid") or "").strip() or "未编号"
            slot = questions.get(qid) or {}
            kind = _verdict_kind(brief.get("verdict"))
            content = str(slot.get("content") or brief.get("stem") or "")[:48]
            answer = _clip_sentence(str(brief.get("student_answer") or ""), 40)
            label = str(brief.get("knowledge_point") or "").strip()[:16]
            if label:
                groups.setdefault(label, []).append(kind or "other")
            ok_n = len(slot.get("ok") or [])
            bad_n = len(slot.get("wrong") or []) + len(slot.get("blank") or [])
            if kind in ("wrong", "blank") and ok_n >= 2 and ok_n > bad_n:
                how = "空着" if kind == "blank" else "做错"
                wrote = f"，写下的是「{answer}」" if answer and kind == "wrong" else ""
                notes.append(f"多数人做对，该生{how}：{content}{wrote}（题{qid}）")
            elif kind == "wrong" and answer:
                notes.append(f"该生写下「{answer}」，与题目要求不符：{content}（题{qid}）")
        for label, kinds in groups.items():
            if "ok" in kinds and ("wrong" in kinds or "blank" in kinds):
                notes.append(
                    f"已有标签「{label}」下，该生有的做对、有的做错或空着。标签只供对照，写的时候用题干里的说法。"
                )
        seen: List[str] = []
        for note in notes:
            if note not in seen:
                seen.append(note)
        by_student[sid] = seen[:6]
    return {"questions": rows, "by_student": by_student}


def _clip_sentence(text: str, limit: int = 240) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(raw) <= limit:
        return raw
    cut = raw[:limit]
    for mark in ("。", "；", "，"):
        pos = cut.rfind(mark)
        if pos >= limit // 2:
            return cut[:pos + 1]
    return cut.rstrip() + "…"


def _prior_line(report: Dict[str, Any]) -> str:
    for point in report.get("points") or []:
        text = str(point or "").strip()
        if text.startswith("前序"):
            return _clip_sentence(text)
    return "本次是可以参照的当前次序，还没有更早的批改可以对照。"


def _peer_line(report: Dict[str, Any]) -> str:
    peers = report.get("peer_horizontal") if isinstance(report.get("peer_horizontal"), list) else []
    for line in peers:
        text = strip_internal_jargon(str(line or ""))
        if text:
            return text[:180]
    return "先完成该生自己的这一关键步骤。班里若有同学同一考查点已经正确，可以对照这一步骤，而不是只核对答案。"


def _literacy_pair(subject_label: str) -> tuple:
    """期望水准兜底句里用的课标名称。数学、语文、英语各用本学科课标，不互相借用。"""
    subject = subject_label or ""
    if "数学" in subject:
        return (
            "会用数学的眼光观察现实世界（如符号意识）、会用数学的思维思考现实世界（如运算能力）或会用数学的语言表达现实世界（如应用意识）",
            "实事求是的科学态度、讲道理且有条理的思维品质",
        )
    if "语文" in subject:
        return (
            "语言运用，以及这次看得到的思维能力或审美创造",
            "有理有据、负责任地表达，实事求是、崇尚真知",
        )
    if "英语" in subject or "英文" in subject:
        return (
            "语言能力，以及这次看得到的思维品质或学习能力",
            "品格与社会责任感",
        )
    return (
        "该学科课标里的学科核心素养",
        "课标所说的价值观、品格或关键能力",
    )


def fallback_student_expectation(
    report: Dict[str, Any],
    *,
    subject_label: str,
    material_label: str,
    filename: str,
) -> str:
    name = str(report.get("display_name") or f"学生{report.get('student_index')}")
    material = material_label or filename or "这份作业"
    focuses = _focus_items(report) or ["这份作业里的具体题目"]
    focus = "、".join(f"「{x}」" for x in focuses)
    subject = subject_label or "本学科"
    literacy, character = _literacy_pair(subject)
    return strip_internal_jargon(
        f"这一步：先把{focus}里要完成的那一层自己做对，并能说出它对应的学科素养。教和育写在班级期望里，这里不重复。\n"
        f"- 学：{name}先独立把这一步里还没做对的那一处说出来。对学生说。\n"
        f"- 家长：只在家里听该生把这一步说一遍，不另讲课堂步骤。\n"
        f"- 达到：这一步的关键关系正确，并能说出它对应{literacy}里的哪一种。\n"
        f"- 基本达到：主要步骤基本正确，但还不能说明它对应哪一种能力。\n"
        f"- 尚未达到：这一步下面的考查内容或关键步骤尚未正确。先补正这一步。\n"
        f"对照该生前面的情况：{_prior_line(report)}\n"
        f"和班里同学一起看：{_peer_line(report)}"
    )


def fallback_class_expectation(
    *,
    class_map: Dict[str, Any],
    student_reports: List[Dict[str, Any]],
    subject_label: str,
    material_label: str,
    filename: str,
) -> str:
    material = material_label or filename or "这次作业"
    subject = subject_label or "本学科"
    class_id = class_map.get("class_id") or "本班"
    hw = class_map.get("homework_index") or ""
    focuses: List[str] = []
    for report in student_reports:
        for item in _focus_items(report, limit=2):
            if item not in focuses:
                focuses.append(item)
        if len(focuses) >= 4:
            break
    focus = "、".join(f"「{x}」" for x in focuses) if focuses else "这次作业里的具体题目"
    literacy, character = _literacy_pair(subject)
    who = "、".join(
        str(r.get("display_name") or "")
        for r in student_reports[:5]
        if str(r.get("display_name") or "").strip()
    )
    return strip_internal_jargon(
        f"## 本次期望水准\n"
        f"这一步：{class_id}第{hw}次{subject}「{material}」要先完成{focus}里承上启下的那一层，再核对它下面的知识，再接到{literacy}。全班同一方向，每人不必同一档。\n"
        f"- 素养链：这一步是把{focus}里的关系写对并说出来 → 学科素养对应{literacy}，要能在上述作答里看出来 → 人的变化写这次看得到的{character}；看不出就写还看不出。\n"
        f"- 学：对学生说，先独立把这一步说清楚；这一步正确之后，再与同学对照同一步骤。\n"
        f"- 教：对教师说，先讲清这一步和它的适用范围，再留一道问法相近的内容。\n"
        f"- 育：对教师说，这一步里看得到的{character}写在这里。做题步骤不写在这里。看不出就写还看不出。\n"
        f"- 家长：只在家里听孩子把这一步说一遍，不重复课堂步骤。\n"
        f"- 达到：这一步完整，能说出它对应的能力，换成相近问法后仍然正确。\n"
        f"- 基本达到：主要步骤基本正确，但不能说明它对应哪一种能力，或只写出了结果。\n"
        f"- 尚未达到：这一步下面的考查内容或关键步骤尚未正确。先补正这一步。\n"
        f"班里{who or '各学生'}不要求处于同一档。个人报告沿用这一步，不把上面的教和育再写一遍。"
    )


def _levels_ok(text: str) -> bool:
    raw = str(text or "")
    return "达到" in raw and ("基本达到" in raw or "尚未达到" in raw)


def compose_expectation_pack(
    *,
    username: str,
    subject_label: str,
    material_label: str,
    filename: str,
    class_map: Dict[str, Any],
    student_reports: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """为班级报告和每个学生报告准备开头的期望水准。模型失败时用材料里的考查点兜底。"""
    brief = load_semantic_professional_brief(username)
    fallback_class = fallback_class_expectation(
        class_map=class_map,
        student_reports=student_reports,
        subject_label=subject_label,
        material_label=material_label,
        filename=filename,
    )
    by_student: Dict[str, str] = {}
    for report in student_reports:
        sid = str(report.get("student_index"))
        by_student[sid] = fallback_student_expectation(
            report,
            subject_label=subject_label,
            material_label=material_label,
            filename=filename,
        )
    rubric = ""
    try:
        from .class_multi_grading import load_rubric_guidance

        rubric = load_rubric_guidance(max_chars=2500)
    except Exception:
        rubric = ""
    situation = paper_situation(student_reports)
    payload = {
        "class_id": class_map.get("class_id"),
        "homework_index": class_map.get("homework_index"),
        "subject": subject_label,
        "material": material_label or filename,
        "paper": situation.get("questions") or [],
        "students": [
            {
                "student_index": r.get("student_index"),
                "name": r.get("display_name"),
                "prior": _prior_line(r),
                "peer": _peer_line(r),
                "notable": (situation.get("by_student") or {}).get(str(r.get("student_index"))) or [],
                "wrong_count": r.get("wrong_count"),
                "uncertain_count": r.get("uncertain_count"),
            }
            for r in student_reports
        ],
    }
    prompt = f"""请为这次班级作业写「期望水准」。班级这一段给教师看，学生那一段给学生和家长看。

{competency_context_block(subject_label)}

先读 paper：每题有 content（题干里的考查内容）、figure（有图才有）、ok_count、wrong、blank、partial。
已有标签若与 content 不一致，以 content 为准，不要用标签造一个新名称。
先从全班都要完成的那一层写起，不要从题号清单写起，也不要先贴素养名称。

要写两块，全部用「- 」分点。每块先有一句「这一步：」，几十个字，说清当前要完成什么。
1. class_markdown：以「## 本次期望水准」开头，然后是「这一步：」。这是全班共用的那一层，只在这里写完整。必须还有：
   素养链：、学：、教：、育：、家长：、达到：、基本达到：、尚未达到：。
   素养链用「 → 」连成三截。第一截就是这一步，不要改成哪些题完成了。第二截写课标里的学科素养正式名称，并写它在哪一种作答里看得出来：数学写三个会用里这次用到的；语文写语言运用等；英语写语言能力等。第三截写人的变化；看不出就写还看不出。
   学是对学生说的。教和育是对教师说的。家长只写家里能配合的一件事，不重复教。
   三档都写这一步做到什么程度，不能只更换形容词。写明不同学生不必处于同一档。
2. students：每位学生一段。沿用班级的「这一步」，不要重写教、育和三档定义。只写：
   这一步：该生停在这一层的哪里；学：对该生说的一种做法；家长：一句；以及该生更接近达到、基本达到还是尚未达到，依据写 notable 里的卷面，题号放括号。
   禁止把班级那几条原样复制给每个人。

一句里有两件以上的事，就在该条下面再用「- 」分开。不要写「达到档」，不要写单独成行的 ---。
不要自造题干和课标里没有的概括名词。禁止「要细心」「加强练习」这种没有考查内容的句子。
只输出 JSON：
{{"class_markdown":"## 本次期望水准\\n...","students":[{{"student_index":1,"markdown":"..."}}]}}

【本子专业内容】
{brief or "（本子尚未梳理出专业内容，只依据课标和这份材料的题目来写）"}

【素养量规摘录，只作把概括写成可观察行为的方法，不要把它当成这次的题目】
能力名使用上面的19项和36项，本次体现几种就写几种。每项写 1 到 5 的素养分，依据写考查内容，不要按做对题数换算。
{rubric[:1200]}

【卷面与全班分布】
{json.dumps(payload, ensure_ascii=False)[:14000]}
"""
    try:
        from .class_multi_grading import _call_class_multi_llm

        text, model_tag = _call_class_multi_llm(
            prompt,
            system="你写的是作业期望水准。班级段给教师，学生段给学生和家长。只用中文，输出合法 JSON。",
            max_tokens=5200,
        )
        if text.startswith("（班级报告生成暂降级") or str(model_tag).startswith("failed:"):
            raise RuntimeError(model_tag)
        matched = re.search(r"\{[\s\S]*\}", text)
        data = json.loads(matched.group(0) if matched else text)
        class_md = strip_internal_jargon(str(data.get("class_markdown") or ""))
        if _levels_ok(class_md):
            if "本次期望水准" not in class_md:
                class_md = "## 本次期望水准\n" + class_md
            fallback_class = class_md
        for item in data.get("students") or []:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("student_index"))
            md = strip_internal_jargon(str(item.get("markdown") or ""))
            if sid in by_student and _levels_ok(md):
                by_student[sid] = md
    except Exception as exc:
        print(f"[semantic_feedback] expectation fallback: {exc}", flush=True)
    return {"class_markdown": fallback_class, "by_student": by_student}
