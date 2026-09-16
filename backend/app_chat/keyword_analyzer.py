"""
关键词四色和DMT属性判定工具
复用卡片分析逻辑，但针对关键词进行适配
"""
import json
import os

from openai import OpenAI

from app_chat.card_analyzer import analyze_dmt_level, analyze_four_color_type, analyze_knowledge_type_with_llm
from app_chat.keyword_utils import (
    KIMI_CLASSIFY_EXTRA_BODY,
    KIMI_CLASSIFY_MODEL,
    KIMI_CLASSIFY_TEMPERATURE,
    LLM_COLOR_DMT_TWO_LETTER_RULE,
    debug_log_kimi_response,
    extract_kimi_message_text,
    parse_llm_color_dmt_response,
)


def analyze_keyword_four_color_dmt_with_llm(keyword, card_content, scene_name=None,
                                            sub_scene_name=None, scene_summary="", notebook_description=""):
    """
    🔥 使用LLM（Kimi K2，即kimi-k2-turbo-preview）分析单个关键词的四色/DMT属性

    用于卡片生成时，同步分析新生成的关键词的四色/DMT属性。

    Args:
        keyword: 关键词字符串
        card_content: 包含该关键词的卡片内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景摘要（可选）
        notebook_description: 本子描述（可选）

    Returns:
        (four_color_type, dmt_level) 元组
        four_color_type: 'R', 'B', 'P', 'G' 或 ''
        dmt_level: 'D', 'M', 'T' 或 ''
    """
    if not keyword or not keyword.strip() or not card_content:
        return '', ''

    keyword = keyword.strip()

    try:
        # 🔥 获取场景相关的四色示例
        from app_chat.scene_context_helper import get_scene_four_color_examples
        scene_examples = get_scene_four_color_examples(scene_name) if scene_name else None

        # 构建基础prompt - 针对关键词分析（优化版）
        base_system_prompt = """你是一个专业的卡片分类专家，擅长分析关键词在文本中的语言特征和语境类型。

你需要根据关键词在卡片内容中的使用情况，判断该关键词的四色语境类型和DMT层次。

**四色语境类型判断标准（按优先级严格判断）**：

**红色（R）- 行业领域语言**（优先判断）：
- 特征：专业、严谨、权威，目标指向品质提高，具有明确的行业规范或学术标准
- 核心标识：
  * 明确的专业术语、学科概念（如"教学设计"、"课程标准"、"认知心理学"）
  * 行业规范、标准流程、官方文件（如"课标对标"、"教学大纲"）
  * 权威性表达、正式表述、学术语言
- ⚠️ 判断要点：必须是明确的、可识别的专业术语或行业规范，不能是泛化的方法论描述

**蓝色（B）- 技术工具语言**（第二优先级）：
- 特征：目标明确指向效率提高，具有可操作性的工具、方法、手段
- 核心标识：
  * 具体的技术工具、软件、平台（如"RAG搜索"、"AI辅助"、"算法对比"）
  * 可操作的方法、流程、步骤（如"分-连-用三步法"、"结构化分解"）
  * 效率提升手段、优化方法、改进工具
- ⚠️ 判断要点：必须具有明确的技术特征或工具属性，而非抽象思维

**绿色（G）- 自然语言**（第三优先级，需要明确识别）：
- 特征：基于紫色思维语言并产生了一定的简单而深刻的自然表达，既要有简单易懂的自然语言特征，也要有一定的深刻性（有所体现即可，不必太过苛刻，但要有）
- 核心标识：
  * 去专业化表达、本质化描述，但带有思维深度（如"学习自主性"、"真实情境"）
  * 自然语言特征明显，但不仅仅停留在表面，有一定的本质洞察
  * 简单易懂的同时，具有可向下击穿性（能够产生方法和知识）
- ⚠️ 判断要点：
  * 必须同时具备简单易懂的自然语言特征和一定的深刻性（两者缺一不可）
  * 是基于紫色思维语言的自然化表达，不是纯技术性描述
  * 深刻性不必过于苛刻，但必须有所体现（约10-15%左右应为绿色）

**紫色（P）- 场景思维语言**（最后判断）：
- 特征：逻辑思维性，系统性推演、方法论框架、认知结构
- 核心标识：
  * 思维框架、认知框架、方法论体系（如"认知阶梯"、"思维路径"、"认知锚点"）
  * 系统性推演、逻辑结构、思维张力
  * DMT框架相关、思维模式、认知结构
- ⚠️ 判断要点：只有当前三种类型都不符合时，才判定为紫色。紫色是场景思维语言，是深刻、系统、全面、统领等的思维框架性关键词的类型。

**DMT层次判断标准（严格按抽象程度判断）**：

**T层（Top）- 顶层**（严格但不过度，约10-15%左右）：
- 特征：偏思维性的（D偏知识，M偏方法），T的粒度是较大的，但也不是所有思维性内容都可以作为T
- 核心标识：
  * 具有可向下击穿性（能够产生方法和知识）的思维框架
  * 偏思维性而非纯知识性或方法性，能够指导并衍生出具体的M层方法和D层知识
  * 宏观系统、思维框架、认知框架、方法论体系
  * 统领性概念、顶层设计、系统性思维
- ⚠️ 判断要点：
  * 必须是偏思维性的（而非偏知识或偏方法）
  * 必须具有可向下击穿性：能够产生方法和知识，而不是孤立的抽象概念
  * 粒度较大，但必须具有指导性和衍生性
  * 约10-15%左右应为T层（过高过低都不可取）
  * 例如："单元学习任务单总体框架设计方法论"（可以向下击穿为具体方法和知识）、"认知框架"（可以指导具体认知方法）

**M层（Middle）- 中层**（约25-35%）：
- 特征：中等抽象程度、连接过渡、分类组织
- 核心标识：
  * 关系分析、转换转化、分类组织、比较分析
  * 连接性概念、过渡性方法、整合性思维
  * 结构化思维、组织化方法
- ⚠️ 判断要点：
  * 具有明确的组织、分类、连接特征
  * 能够连接多个概念或方法
  * 具有结构化的特征，但不是顶层框架

**D层（Down）- 底层**（最多，约50-60%）：
- 特征：具象、具体、细节、操作层面、可直接执行
- 核心标识：
  * 具体步骤、操作方法、实例示例、代码命令
  * 细节描述、操作指南、实践方法
  * 可直接执行的、可操作的、具体化的内容
- ⚠️ 判断要点：
  * 必须具有明确的操作性、可执行性
  * 是具体的方法、步骤、操作，而非抽象概念
  * 是实践层面的内容，可以直接应用

**判定原则（重要）**：
1. **四色类型判断顺序**：先判断是否为红色（专业术语）→ 再判断是否为蓝色（技术工具）→ 再判断是否为绿色（自然语言）→ 最后判定为紫色（思维框架语言）
2. **避免过度判定为紫色**：只有当前三种类型都不符合时，才判定为紫色。许多思维性关键词可能实际上是红色（专业术语）或蓝色（技术工具），以及有些可能是超脱紫色的绿色。
3. **DMT层次严格判定**：
   - T层：必须是具有统领性、框架性的内容，比例控制在10-20%
   - M层：具有连接、组织特征的内容，比例控制在25-35%
   - D层：具体的、可操作的内容，比例控制在50-60%
4. **关键词本身特征优先**：判断时优先考虑关键词本身的词汇特征和语义，再结合卡片内容中的使用语境。"""

        # 🔥 如果提供了场景信息，添加场景上下文
        scene_context = ""
        if scene_name:
            scene_context += f"\n\n**当前场景信息**：\n"
            scene_context += f"- 场景名称：{scene_name}\n"
            if sub_scene_name:
                scene_context += f"- 子场景名称：{sub_scene_name}\n"
            if scene_summary:
                # 截断场景摘要（不超过300字）
                summary_short = scene_summary[:300] + "..." if len(scene_summary) > 300 else scene_summary
                scene_context += f"- 场景内涵摘要：{summary_short}\n"
            if notebook_description:
                scene_context += f"- 本子描述：{notebook_description}\n"

            if scene_examples:
                scene_context += f"\n**在当前场景下的四色示例**：\n"
                scene_context += f"- 红色（R）示例：{scene_examples.get('R', '专业术语、行业规范')}\n"
                scene_context += f"- 蓝色（B）示例：{scene_examples.get('B', '技术工具、方法手段')}\n"
                scene_context += f"- 紫色（P）示例：{scene_examples.get('P', '逻辑框架、认知框架')}\n"
                scene_context += f"- 绿色（G）示例：{scene_examples.get('G', '自然语言、简单深刻')}\n"

            scene_context += "\n请结合当前场景的特点来判断关键词的四色类型和DMT层次。"

        system_prompt = base_system_prompt + scene_context + """

**重要判定规则（必须严格遵守）**：

1. **四色类型判定顺序**：
   - 首先判断是否为红色（R）：关键词是否为明确的专业术语、行业规范、学科概念？如果是，直接判定为R。
   - 其次判断是否为蓝色（B）：关键词是否为技术工具、可操作方法、效率提升手段？如果是，直接判定为B。
   - 再次判断是否为绿色（G）：关键词是否具有简单而深刻的本质化表达或自然语言特征？如果是，直接判定为G。
   - 最后判定为紫色（P）：只有当前三种类型都不符合时，才判定为P。紫色是具有统领性、原子性、思维框架性等的类型，和绿色一样都不是大多数关键词的类型。

2. **DMT层次判定严格性**：
   - T层（顶层）：偏思维性的，具有可向下击穿性（能够产生方法和知识），粒度较大。约10-15%左右应为T层（过高过低都不可取）。
   - M层（中层）：偏方法的，具有连接、组织、分类特征，中等抽象程度。约25-35%的内容应该是M层。
   - D层（底层）：偏知识的，具体的、可操作的、细节层面的内容。约50-60%的内容应该是D层。

3. **避免误判**：
   - 不要把专业术语误判为紫色思维语言
   - 不要把技术工具误判为紫色思维语言
   - 不要把具体操作方法误判为T层（T必须是偏思维性且有可向下击穿性）
   - 不要把思维框架误判为D层
   - 不要把简单的自然语言误判为绿色（绿色必须有深刻性）
   - 不要把基本满足简单而深刻要求的绿色低判为紫色
   - 不要把没有可向下击穿性的抽象概念误判为T层

请仔细分析关键词在卡片内容中的使用情况，严格按照上述规则判断其四色类型和DMT层次。只返回两个字母，第一个字母表示四色类型（R、B、P、G），第二个字母表示DMT层次（D、M、T）。如果无法明确判断，返回空字符串。

你的回答格式：直接返回两个字母（如"RD"表示红色+底层），不要有其他说明文字。

""" + LLM_COLOR_DMT_TWO_LETTER_RULE

        user_prompt = f"""请分析以下关键词在卡片内容中的四色语境类型和DMT层次：

**关键词**：{keyword}

**卡片内容**：
{card_content[:4000]}

**分析要求**：
1. 首先分析关键词本身的语义特征：它是专业术语、技术工具、思维框架还是自然表达？
2. 然后分析关键词在卡片内容中的使用语境：它在内容中如何被使用？起到什么作用？
3. 严格按照判定顺序(这是认知的递进顺序)进行判断：R > B > G > P（四色类型），D > M > T（T层和G层、P层都要适中，各自均约10-20%左右）
4. 避免误判：
   - 不要把专业术语误判为紫色
   - 不要把操作方法误判为T层（T必须是偏思维性且有可向下击穿性）
   - 不要把简单的自然语言误判为绿色（绿色必须有深刻性，是基于紫色的自然化表达），也不要把基本满足简单而深刻的绿色低判为紫色
   - 紫色绿色和T层应各占约10-15%左右，不要过度判定也不要过于保守

请判断该关键词的四色类型和DMT层次（格式：两个字母，如"RD"表示红色+底层）：

""" + LLM_COLOR_DMT_TWO_LETTER_RULE

        def parse_result(result_text):
            return parse_llm_color_dmt_response(result_text)

        def keyword_rule_fallback():
            combined = f'{keyword}\n{card_content[:2000]}'
            fc = analyze_four_color_type(combined)
            dmt = analyze_dmt_level(combined)
            if fc or dmt:
                print(
                    f"[analyze_keyword_four_color_dmt_with_llm] 关键词'{keyword}' 规则降级: "
                    f"四色={fc}, DMT={dmt}"
                )
            return fc, dmt

        # 🔥 第一次尝试：使用kimi-k2-turbo-preview，15秒超时
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        def call_kimi_first():
            API_KEY = os.environ.get("KIMI_API_KEY", "")
            client = OpenAI(
                api_key=API_KEY,
                base_url="https://api.moonshot.cn/v1",
                timeout=15.0
            )
            response = client.chat.completions.create(
                model=KIMI_CLASSIFY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=KIMI_CLASSIFY_TEMPERATURE,
                max_tokens=20,
                extra_body=KIMI_CLASSIFY_EXTRA_BODY,
            )
            return response

        def handle_kimi_response(response, attempt_tag):
            raw_text = extract_kimi_message_text(response.choices[0].message)
            four_color_type, dmt_level = parse_result(raw_text)
            if four_color_type and dmt_level:
                print(
                    f"[analyze_keyword_four_color_dmt_with_llm] 关键词'{keyword}' {attempt_tag}LLM判定: "
                    f"四色={four_color_type}, DMT={dmt_level}"
                )
                return four_color_type, dmt_level, True
            debug_log_kimi_response(
                f'analyze_keyword_four_color_dmt/{keyword}/{attempt_tag}',
                response,
                raw_text=raw_text,
                parsed=f'{four_color_type},{dmt_level}',
            )
            print(
                f"[analyze_keyword_four_color_dmt_with_llm] 关键词'{keyword}' {attempt_tag}LLM返回无效结果: "
                f"raw={raw_text!r} parsed=({four_color_type!r},{dmt_level!r})"
            )
            return four_color_type, dmt_level, False

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(call_kimi_first)
                response = future.result(timeout=15)
                four_color_type, dmt_level, ok = handle_kimi_response(response, '')
                if ok:
                    return four_color_type, dmt_level
                fallback = keyword_rule_fallback()
                if fallback[0] and fallback[1]:
                    return fallback
                if four_color_type or dmt_level:
                    return four_color_type, dmt_level
                raise Exception("无效结果，需要重试")
        except (FuturesTimeoutError, Exception) as e:
            print(f"[analyze_keyword_four_color_dmt_with_llm] 首次调用失败或超时: {e}，使用K2重试...")

        # 🔥 第二次尝试
        try:
            client = OpenAI(
                api_key=os.environ.get("KIMI_API_KEY", ""),
                base_url="https://api.moonshot.cn/v1",
                timeout=15.0
            )
            response = client.chat.completions.create(
                model=KIMI_CLASSIFY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=KIMI_CLASSIFY_TEMPERATURE,
                max_tokens=20,
                extra_body=KIMI_CLASSIFY_EXTRA_BODY,
            )
            four_color_type, dmt_level, ok = handle_kimi_response(response, '重试')
            if ok:
                return four_color_type, dmt_level
            fallback = keyword_rule_fallback()
            if fallback[0] and fallback[1]:
                return fallback
            if four_color_type or dmt_level:
                return four_color_type, dmt_level
        except Exception as e2:
            print(f"[analyze_keyword_four_color_dmt_with_llm] K2重试也失败: {e2}")

        return keyword_rule_fallback()

    except Exception as e:
        print(f"[analyze_keyword_four_color_dmt_with_llm] 关键词'{keyword}' LLM判定失败: {e}")
        import traceback
        traceback.print_exc()
        combined = f'{keyword.strip()}\n{(card_content or "")[:2000]}'
        fc = analyze_four_color_type(combined)
        dmt = analyze_dmt_level(combined)
        return fc, dmt


def analyze_keyword_knowledge_type_with_llm(keyword, card_content, scene_name=None,
                                            sub_scene_name=None, scene_summary="",
                                            notebook_description=""):
    """使用 LLM 分析单个关键词的三类知识属性，返回 trad/org/trib 或空字符串。"""
    if not keyword or not keyword.strip() or not card_content:
        return ''
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        def _call():
            return analyze_knowledge_type_with_llm(
                card_content,
                scene_name=scene_name,
                sub_scene_name=sub_scene_name,
                scene_summary=scene_summary,
                notebook_description=notebook_description,
                keyword=keyword.strip(),
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            return future.result(timeout=15) or ''
    except Exception as e:
        print(f"[analyze_keyword_knowledge_type_with_llm] 关键词'{keyword}' 判定失败: {e}")
        return ''


def analyze_keyword_full_attributes_with_llm(keyword, card_content, scene_name=None,
                                             sub_scene_name=None, scene_summary="",
                                             notebook_description=""):
    """
    并行分析关键词的四色/DMT 与三类知识属性。
    返回 (four_color_type, dmt_level, knowledge_type)
    """
    from concurrent.futures import ThreadPoolExecutor

    four_color_type = dmt_level = knowledge_type = ''
    with ThreadPoolExecutor(max_workers=2) as executor:
        fc_dmt_future = executor.submit(
            analyze_keyword_four_color_dmt_with_llm,
            keyword, card_content, scene_name, sub_scene_name, scene_summary, notebook_description,
        )
        kt_future = executor.submit(
            analyze_keyword_knowledge_type_with_llm,
            keyword, card_content, scene_name, sub_scene_name, scene_summary, notebook_description,
        )
        try:
            four_color_type, dmt_level = fc_dmt_future.result(timeout=20)
        except Exception as e:
            print(f"[analyze_keyword_full_attributes_with_llm] 四色/DMT失败 keyword={keyword}: {e}")
        try:
            knowledge_type = kt_future.result(timeout=20) or ''
        except Exception as e:
            print(f"[analyze_keyword_full_attributes_with_llm] 三类知识失败 keyword={keyword}: {e}")
    return four_color_type, dmt_level, knowledge_type


def analyze_keyword_four_color_dmt(keyword, cards_with_keyword=None, scene_name=None,
                                    sub_scene_name=None, scene_summary="", notebook_description=""):
    """
    分析关键词的四色/DMT属性

    策略：
    1. 收集所有包含该关键词的卡片内容
    2. 使用卡片内容分析关键词的四色/DMT类型
    3. 如果有多张卡片，取最常见的类型（投票机制）

    Args:
        keyword: 关键词字符串
        cards_with_keyword: 包含该关键词的卡片列表（可选，如果提供则直接使用）
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景摘要（可选）
        notebook_description: 本子描述（可选）

    Returns:
        (four_color_type, dmt_level) 元组
        four_color_type: 'R', 'B', 'P', 'G' 或 ''
        dmt_level: 'D', 'M', 'T' 或 ''
    """
    if not keyword or not keyword.strip():
        return '', ''

    keyword = keyword.strip()

    # 如果没有提供卡片列表，返回空（需要从外部调用时提供）
    if not cards_with_keyword or len(cards_with_keyword) == 0:
        print(f"[analyze_keyword_four_color_dmt] 关键词'{keyword}'没有关联卡片，返回空值")
        return '', ''

    # 收集所有卡片的内容
    combined_content = []
    four_color_votes = {'R': 0, 'B': 0, 'P': 0, 'G': 0}
    dmt_votes = {'D': 0, 'M': 0, 'T': 0}

    # 分析每张卡片，统计投票
    for card in cards_with_keyword:
        card_content = card.get('content', '') if isinstance(card, dict) else getattr(card, 'content', '')
        if card_content:
            combined_content.append(card_content)

            # 使用关键词匹配方法快速分析（不调用LLM，避免太慢）
            four_color = analyze_four_color_type(card_content)
            dmt = analyze_dmt_level(card_content)

            if four_color and four_color in four_color_votes:
                four_color_votes[four_color] += 1
            if dmt and dmt in dmt_votes:
                dmt_votes[dmt] += 1

    # 如果只有1-2张卡片，直接使用卡片分析结果
    if len(cards_with_keyword) <= 2:
        if combined_content:
            combined_text = '\n\n'.join(combined_content)
            # 使用关键词匹配方法
            four_color_type = analyze_four_color_type(combined_text)
            dmt_level = analyze_dmt_level(combined_text)
            return four_color_type, dmt_level

    # 多张卡片时，使用投票机制
    # 四色类型：取票数最多的，如果最高票数相同，优先顺序：P > G > R > B
    max_four_color_votes = max(four_color_votes.values())
    if max_four_color_votes > 0:
        # 找出所有得票最高的类型
        top_four_colors = [k for k, v in four_color_votes.items() if v == max_four_color_votes]
        # 按优先级排序
        priority_order = ['P', 'G', 'R', 'B']
        four_color_type = sorted(top_four_colors, key=lambda x: priority_order.index(x) if x in priority_order else 999)[0]
    else:
        four_color_type = ''

    # DMT层次：取票数最多的，如果最高票数相同，优先顺序：T > M > D
    max_dmt_votes = max(dmt_votes.values())
    if max_dmt_votes > 0:
        top_dmt_levels = [k for k, v in dmt_votes.items() if v == max_dmt_votes]
        priority_order = ['T', 'M', 'D']
        dmt_level = sorted(top_dmt_levels, key=lambda x: priority_order.index(x) if x in priority_order else 999)[0]
    else:
        dmt_level = ''

    print(f"[analyze_keyword_four_color_dmt] 关键词'{keyword}'分析完成: 四色={four_color_type}, DMT={dmt_level}")
    return four_color_type, dmt_level


def update_notebook_keyword_four_color_dmt(username, scene_name, book_name, keyword,
                                           four_color_type, dmt_level, knowledge_type=''):
    """
    更新笔记本中关键词的四色/DMT信息

    Args:
        username: 用户名（可能是"用户名_本子名"格式）
        scene_name: 场景名（可选，用于查找笔记本）
        book_name: 本子名（可选，如果不提供则从username解析）
        keyword: 关键词
        four_color_type: 四色类型
        dmt_level: DMT层次
    """
    try:
        from zym.models import UserNotebook, scene

        # 解析username格式
        realName = username.split('_')[0] if '_' in username else username

        # 如果没有提供book_name，尝试从username解析
        if not book_name:
            if '_' in username:
                # username格式可能是 "用户名_本子名"
                book_name = username[len(realName) + 1:]

        # 如果仍然没有book_name，尝试通过scene_name查找
        if not book_name and scene_name:
            try:
                scene_obj = scene.objects.get(sceneDescription=scene_name)
                notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                if notebook:
                    book_name = notebook.bookName
            except:
                pass

        if not book_name:
            print(f"[update_notebook_keyword_four_color_dmt] 无法确定book_name，跳过更新")
            return

        # 查找笔记本
        try:
            notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
        except UserNotebook.DoesNotExist:
            print(f"[update_notebook_keyword_four_color_dmt] 找不到笔记本 username={realName}, bookName={book_name}")
            return

        # 读取现有的关键词四色/DMT信息
        keyword_data = {}
        if notebook.keywordFourColorDMT:
            try:
                keyword_data = json.loads(notebook.keywordFourColorDMT)
            except:
                keyword_data = {}

        # 更新该关键词的信息
        entry = keyword_data.get(keyword, {}) if isinstance(keyword_data.get(keyword), dict) else {}
        entry['four_color_type'] = four_color_type
        entry['dmt_level'] = dmt_level
        if knowledge_type:
            entry['knowledge_type'] = knowledge_type
        keyword_data[keyword] = entry

        # 保存回数据库
        notebook.keywordFourColorDMT = json.dumps(keyword_data, ensure_ascii=False)
        notebook.save()

        print(f"[update_notebook_keyword_four_color_dmt] 成功更新关键词'{keyword}'的四色/DMT信息到笔记本")

    except Exception as e:
        print(f"[update_notebook_keyword_four_color_dmt] 更新关键词四色/DMT信息失败: {e}")
        import traceback
        traceback.print_exc()


def analyze_and_update_keywords_for_notebook(username, scene_name=None):
    """
    分析笔记本中所有关键词的四色/DMT属性并更新到数据库

    策略：
    1. 获取该笔记本的所有卡片
    2. 提取所有关键词
    3. 对每个关键词，找到包含它的所有卡片
    4. 分析关键词的四色/DMT属性
    5. 保存到UserNotebook的keywordFourColorDMT字段

    Args:
        username: 用户名（可能是"用户名_本子名"格式）
        scene_name: 场景名（可选）
    """
    try:
        from app_chat.models import Card
        from zym.models import UserNotebook, scene
        import re

        # 解析username
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None

        # 如果没有book_name，尝试通过scene_name查找
        if not book_name and scene_name:
            try:
                scene_obj = scene.objects.get(sceneDescription=scene_name)
                notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                if notebook:
                    book_name = notebook.bookName
            except:
                pass

        if not book_name:
            print(f"[analyze_and_update_keywords_for_notebook] 无法确定book_name，跳过分析")
            return

        # 获取该笔记本的所有卡片
        cards = Card.objects.filter(username=username).values('cid', 'content', 'keyWords')
        cards_list = list(cards)

        if not cards_list:
            print(f"[analyze_and_update_keywords_for_notebook] 笔记本中没有卡片，跳过分析")
            return

        # 提取所有关键词
        all_keywords = set()
        for card in cards_list:
            if card.get('keyWords'):
                keywords = re.split(r'[,，]', card['keyWords'])
                for kw in keywords:
                    kw_clean = kw.strip()
                    if kw_clean:
                        all_keywords.add(kw_clean)

        print(f"[analyze_and_update_keywords_for_notebook] 发现 {len(all_keywords)} 个唯一关键词")

        # 🔥 获取场景摘要和本子描述（用于LLM分析）
        scene_summary = ""
        notebook_description = ""
        sub_scene_name = None
        try:
            from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
            if scene_name:
                scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, sub_scene_name)
                scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
                notebook_description = get_notebook_description(username, scene_name)
        except Exception as e:
            print(f"[analyze_and_update_keywords_for_notebook] 获取场景信息失败: {e}")

        # 对每个关键词进行分析（使用LLM方法）
        for keyword in all_keywords:
            # 找到包含该关键词的所有卡片
            cards_with_keyword = []
            for card in cards_list:
                if card.get('keyWords'):
                    keywords = re.split(r'[,，]', card['keyWords'])
                    keywords_clean = [kw.strip() for kw in keywords]
                    if keyword in keywords_clean:
                        cards_with_keyword.append(card)

            if not cards_with_keyword:
                continue

            # 🔥 使用LLM分析关键词的四色/DMT属性
            # 使用第一张包含该关键词的卡片内容进行分析
            first_card = cards_with_keyword[0]
            card_content = first_card.get('content', '')

            # 如果第一张卡片内容为空，尝试合并所有卡片内容
            if not card_content and len(cards_with_keyword) > 1:
                card_contents = [card.get('content', '') for card in cards_with_keyword if card.get('content')]
                if card_contents:
                    card_content = '\n\n'.join(card_contents[:3])  # 最多合并3张卡片的内容

            if not card_content:
                continue

            # 从卡片内容标题中提取子场景信息（如果存在）
            try:
                import re as re_module
                content_title = first_card.get('contentTitle', '')
                if content_title:
                    sub_scene_match = re_module.search(r'^S(\d+)[:：]', content_title)
                    if sub_scene_match:
                        # 子场景编号已提取，但这里我们主要用场景名即可
                        pass
            except:
                pass

            try:
                # 使用LLM分析关键词
                four_color_type, dmt_level = analyze_keyword_four_color_dmt_with_llm(
                    keyword=keyword,
                    card_content=card_content[:4000],  # 限制长度，避免过长
                    scene_name=scene_name,
                    sub_scene_name=sub_scene_name,
                    scene_summary=scene_summary,
                    notebook_description=notebook_description
                )

                # 更新到数据库
                if four_color_type or dmt_level:
                    update_notebook_keyword_four_color_dmt(
                        username=username,
                        scene_name=scene_name,
                        book_name=book_name,
                        keyword=keyword,
                        four_color_type=four_color_type,
                        dmt_level=dmt_level
                    )
                    print(f"[analyze_and_update_keywords_for_notebook] 关键词'{keyword}' LLM分析完成: 四色={four_color_type}, DMT={dmt_level}")
            except Exception as e:
                print(f"[analyze_and_update_keywords_for_notebook] 分析关键词'{keyword}'失败: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"[analyze_and_update_keywords_for_notebook] 完成关键词分析")
        
    except Exception as e:
        print(f"[analyze_and_update_keywords_for_notebook] 分析关键词失败: {e}")
        import traceback
        traceback.print_exc()

