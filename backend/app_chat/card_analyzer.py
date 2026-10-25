"""
卡片四色和DMT属性判定工具
使用关键词方法进行初步判定
当关键词判定为空时，调用kimi LLM进行精准判定
"""
import nkcn_public_config as _public_config
from openai import OpenAI
import concurrent.futures
import time

from app_chat.card_value_filter import (
    STRICT_VALUE_SYSTEM_PROMPT,
    build_value_scene_context,
)
from app_chat.keyword_utils import (
    KIMI_CLASSIFY_EXTRA_BODY,
    KIMI_CLASSIFY_MODEL,
    KIMI_CLASSIFY_TEMPERATURE,
    LLM_SINGLE_LETTER_OUTPUT_RULE,
    debug_log_kimi_response,
    extract_kimi_message_text,
    parse_knowledge_type,
    parse_llm_single_color,
    parse_llm_single_dmt,
)


def analyze_four_color_type(content):
    """
    通过关键词判定卡片的四色语境类型
    返回：'R'（红）、'B'（蓝）、'P'（紫）、'G'（绿）或空字符串
    """
    if not content:
        return ''

    content_lower = content.lower()

    # 红色（行业领域语言）：专业、严谨、权威，目标指向品质提高
    # 核心特征：各领域的专业术语、行业规范、权威标准
    # 注意：如果是计算机领域，计算机相关内容应该是红色（行业语言），而非蓝色
    red_keywords = [
        # 行业专业相关（各类场景通用）
        '行业标准', '行业规范', '行业领域', '行业术语', '行业专业',
        '专业术语', '专业规范', '专业标准', '专业权威', '专业性',
        '权威性', '严谨性', '品质提高', '品质提升', '品质保证',
        # 学术领域（论文、研究相关）
        '学术规范', '学术标准', '学术术语', '学术研究', '学术论文',
        '学位论文', '期刊论文', '参考文献', '文献引用', '学术写作',
        '研究规范', '研究标准', '学术权威',
        # 教育领域
        '课程标准', '教学规范', '教育标准', '教学术语', '教育规范',
        '教学标准', '教育政策', '教学制度', '教育法规',
        # 计算机领域（如果是计算机领域，相关内容算红色）
        '编程规范', '代码规范', '编程标准', '软件开发规范', '软件工程标准',
        '计算机术语', '编程术语', '技术标准', '技术规范',
        # 军队/政治领域
        '军事术语', '军事规范', '政治工作规范', '军队标准',
        # 业务场景相关（业务相关的组合词，避免单独的"业务"）
        '业务流程', '业务逻辑', '业务场景', '业务需求', '业务规范',
        '业务标准', '业务管理', '业务运营', '业务执行',
        # 组织管理相关（组合词，避免单独的"管理"）
        '企业管理', '组织管理', '部门职能', '岗位职责', '角色定位',
        '管理制度', '管理规范', '管理标准', '管理流程',
        # 合规法规相关
        '合规性', '法规标准', '政策规范', '制度标准', '规范要求',
        '标准规范', '规范流程', '标准体系',
        # 学术相关（组合词，强调规范性）
        '论文评审', '论文格式', '论文润色', '论文修改', '论文编辑',
        '学术评审', '学位论文', '期刊论文',
        # 教育相关（组合词，强调规范性）
        '课程教学', '教学课程', '课程标准', '教学标准', '教育标准',
        # 数据和绩效相关（组合词，强调专业性）
        '数据统计', '数据报表', '绩效指标', 'kpi指标', '绩效评估'
    ]

    # 蓝色（技术工具语言）：目标指向效率提高
    # 核心特征：各类场景通用的技术工具、方法、手段、效率提升方式（不局限于计算机）
    # 注意：如果是计算机领域，计算机相关内容应该是红色，蓝色是更通用的工具方法
    blue_keywords = [
        # 效率提升相关（明确指向效率）
        '效率提升', '效率提高', '效率优化', '提升效率', '提高效率', '效率改进',
        '效率工具', '效率方法', '效率手段', '效率改进', '效率优化工具',
        # 通用工具方法（各类场景通用）
        '工具方法', '优化工具', '辅助工具', '实用工具', '处理工具',
        '优化方法', '改进方法', '提升方法', '优化策略', '改进策略',
        # 技术手段（不局限于计算机）
        '技术手段', '实现手段', '操作方法', '执行方法', '应用方法',
        '分析工具', '评估工具', '测量工具', '检测工具', '辅助工具',
        # 自动化相关（各类场景通用）
        '自动化工具', '自动化方法', '自动化流程', '自动化处理',
        # 数据处理（作为工具方法，而非行业术语）
        '数据处理', '数据分析', '数据整理', '数据统计', '数据优化',
        # 流程优化（作为工具方法）
        '流程优化', '流程改进', '流程提升', '流程精简',
        # 方案和策略（作为工具方法）
        '实施方案', '执行方案', '应用方案', '操作方案', '解决方案',
        '实施策略', '执行策略', '应用策略', '操作策略',
        # 通用工具词（但避免太宽泛，需要与其他词组合才有意义）
        # 注意：单独的"方法"、"技术"等词太宽泛，这里保留是为了作为组合词的一部分
        # 实际匹配时主要通过组合词来判断
        '工具方法', '技术手段', '分析方法', '处理方法', '优化方法',
        '实现方法', '应用方法', '改进方法', '提升方法', '群组设计'
    ]

    # 紫色（场景思维语言）：逻辑思维性，除乘加·DMT，都江堰化，COT/SOT/TOT/GOT
    # 核心特征：系统性推演、方法论框架、逻辑思维、熵减、深刻思维张力
    # 🔥 严格控制，只保留最核心的特征词，避免过度匹配（目标：占总数的15-20%）
    purple_keywords = [
        # DMT相关（除乘加·DMT）- 最核心特征
        'dmt', '除乘加', 'down middle top', 'dmt层次', 'dmt框架', 'dmt体系',
        # 都江堰化相关（堤坝洪流·自治筛分）- 最核心特征
        '都江堰', '都江堰化', '堤坝洪流', '自治筛分', '筛分机制', '自治机制',
        # COT/SOT/TOT/GOT相关 - 最核心特征
        'cot', 'sot', 'tot', 'got', 'chain of thought', 'skeleton of thought',
        'tree of thought', 'graph of thought', '思维链', '思维骨架', '思维树', '思维图',
        # 熵减相关 - 最核心特征
        '熵减', '信息熵减', '熵减过程', '信息梳理', '有序框架',
        # 系统性推演和方法论框架
        '推演框架', '推演体系', '推演方法', '推演逻辑',
        '方法框架', '方法体系', '方法范式',
        '逻辑推演', '逻辑框架', '逻辑体系', '逻辑范式',
        '思维张力', '深刻思维', '思维深度', '认知张力',
        # 抽象框架相关
        '抽象思维', '抽象模型', '抽象框架', '抽象体系', '抽象范式',
        '场景设计', '场景分析', '场景规划', '场景构建', '场景应用', '场景化',
        '情境分析', '情境设计', '情境构建', '情境化',
        # 方法论框架（但需要更具体）
        '推演框架', '逻辑框架', '认知框架',
        # 思维张力 - 核心特征
        '思维张力', '认知张力'
    ]

    # 绿色（自然语言）：简单深刻，陪伴、滋润、敬畏，不虚伪、不浮华、不僵化
    # 核心特征：去专业化、强本质化、促传播化，普适本质，简单而深刻，非辩证，大众语言
    # 🔥 精简，移除过于通用的词（如"洞察"、"智慧"），保留真正核心的特征词
    green_keywords = [
        # 直接特征词（来自定义，非常核心）
        '陪伴', '滋润', '敬畏', '不虚伪', '不浮华', '不僵化',
        '简单而深刻', '简单深刻', '深刻简单',
        # 去专业化、本质化相关（核心特征）
        '去专业化', '去专业', '去除专业', '去掉专业',
        '强本质化', '本质化', '提炼本质', '普适本质', '本质提炼',
        '促传播化', '传播化', '大众传播', '普适性', '通用性',
        # 自然语言相关
        '自然语言', '自然表达', '自然沟通', '自然交流',
        '大众语言', '通俗语言', '平易近人', '深入浅出',
        # 情感共鸣相关（陪伴、滋润的本质）
        '情感共鸣', '心灵共鸣', '精神共鸣', '共鸣感',
        '人文关怀', '人文精神', '人文情怀', '人性温暖',
        # 非辩证、直接表达
        '非辩证', '直接表达', '直接呈现', '直观感受',
        # 涌现和共生相关
        '涌现', '生命力', '共生', '共生成长', '共生关系',
        '自然规律', '自然法则', '自然之道', '大道至简',
        # 体悟相关（更具体，避免泛化）
        '体悟', '感悟', '领悟'  # 移除"洞察"、"智慧"等过于通用的词
    ]

    # 统计各色关键词出现次数
    red_count = sum(1 for kw in red_keywords if kw in content_lower)
    blue_count = sum(1 for kw in blue_keywords if kw in content_lower)
    purple_count = sum(1 for kw in purple_keywords if kw in content_lower)
    green_count = sum(1 for kw in green_keywords if kw in content_lower)

    # 如果都没有匹配，默认返回空字符串
    max_count = max(red_count, blue_count, purple_count, green_count)
    if max_count == 0:
        return ''

    # 🔥 目标分布：红蓝60-70%（红30-35%，蓝30-35%），紫绿30-40%（紫15-20%，绿15-20%）
    # 如果匹配数太少（< 1），不判定
    if max_count < 1:
        return ''

    # 🔥 如果某个颜色匹配数明显高于其他（>=2且是第二高的2倍以上），直接判定
    counts = [(red_count, 'R'), (blue_count, 'B'), (purple_count, 'P'), (green_count, 'G')]
    counts_sorted = sorted(counts, key=lambda x: x[0], reverse=True)

    top_count, top_color = counts_sorted[0]
    second_count, _ = counts_sorted[1] if len(counts_sorted) > 1 else (0, None)

    # 如果最高匹配数 >= 2 且是第二高的2倍以上，直接判定
    if top_count >= 2 and top_count >= second_count * 2:
        return top_color

    # 🔥 如果多个颜色匹配数相同，按优先级判定：红 > 蓝 > 紫 > 绿
    # （红色和蓝色应该更多，但不要过度偏向）
    if red_count == max_count:
        return 'R'
    elif blue_count == max_count:
        return 'B'
    elif purple_count == max_count:
        return 'P'
    elif green_count == max_count:
        return 'G'

    return ''  # 理论上不会到这里


def analyze_four_color_type_with_llm(content, scene_name=None, sub_scene_name=None, scene_summary="",
                                     notebook_description=""):
    """
    当关键词判定为空时，调用kimi LLM进行精准判定卡片的四色语境类型
    返回：'R'（红）、'B'（蓝）、'P'（紫）、'G'（绿）或空字符串

    Args:
        content: 卡片内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not content:
        return ''

    try:
        # 🔥 获取场景相关的四色示例
        from app_chat.scene_context_helper import get_scene_four_color_examples
        scene_examples = get_scene_four_color_examples(scene_name) if scene_name else None

        # 构建基础prompt
        base_system_prompt = """你是一个专业的卡片分类专家，擅长分析文本的语言特征和语境类型。

你需要根据文本内容判断其四色语境类型，判断标准如下：

**红色（R）- 行业领域语言**：
- 特征：专业、严谨、权威，目标指向品质提高
- 核心标识：各领域的专业术语、行业规范、权威标准、学术规范

**蓝色（B）- 技术工具语言**：
- 特征：目标指向效率提高
- 核心标识：通用的技术工具、方法、手段、效率提升方式

**紫色（P）- 场景思维语言**：
- 特征：逻辑思维性，系统性推演、方法论框架
- 核心标识：DMT框架、都江堰化、COT/SOT/TOT/GOT、熵减、推演框架、思维张力

**绿色（G）- 自然语言**：
- 特征：简单深刻，陪伴、滋润、敬畏，不虚伪、不浮华、不僵化
- 核心标识：去专业化、强本质化、促传播化、普适本质、自然语言"""

        # 🔥 如果提供了场景信息，添加场景特定的示例
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
                scene_context += f"- 绿色（G）示例：{scene_examples.get('G', '自然语言、情感共鸣')}\n"
                scene_context += "\n请结合当前场景的特点和示例来判断四色类型。"

        system_prompt = base_system_prompt + scene_context + "\n\n请仔细分析文本内容，只返回一个字母：R、B、P、G 中的任意一个。如果无法明确判断，返回空字符串。\n\n你的回答格式：直接返回单个字母，不要有其他说明文字。"

        user_prompt = f"""请分析以下文本的四色语境类型，只返回单个字母（R、B、P、G）或空字符串：

文本内容：
{content[:4000]}

请判断四色类型："""

        # 调用kimi API
        API_KEY = _public_config.secret('KIMI_API_KEY')
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://api.moonshot.cn/v1",
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

        raw_text = extract_kimi_message_text(response.choices[0].message)
        result = raw_text.strip().upper()
        parsed = parse_llm_single_color(result)
        if parsed:
            print(f"[card_analyzer] kimi LLM判定四色类型: {parsed}")
            return parsed
        debug_log_kimi_response('card_analyzer/four_color', response, raw_text=raw_text, parsed=parsed)
        print(f"[card_analyzer] kimi LLM返回无效结果，降级关键词匹配")
        return analyze_four_color_type(content)

    except Exception as e:
        print(f"[card_analyzer] kimi LLM判定四色类型失败: {e}")
        return ''


def analyze_dmt_level_with_llm(content, scene_name=None, sub_scene_name=None, scene_summary="",
                               notebook_description=""):
    """
    当关键词判定为空时，调用kimi LLM进行精准判定卡片的DMT层次
    返回：'D'（Down）、'M'（Middle）、'T'（Top）或空字符串

    Args:
        content: 卡片内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not content:
        return ''

    try:
        # 构建基础prompt
        base_system_prompt = """你是一个专业的卡片分类专家，擅长分析文本的抽象层次。

你需要根据文本内容判断其DMT层次，判断标准如下：

**D层（Down）- 底层**：
- 特征：具象、具体、细节、操作层面
- 核心标识：具体步骤、操作方法、实例示例、代码命令、细节描述

**M层（Middle）- 中层**：
- 特征：中性、中等抽象程度、连接、过渡
- 核心标识：关系联系、转换转化、分类组织、比较分析

**T层（Top）- 顶层**：
- 特征：抽象、宏观、本质、全局、统领性、思维框架性
- 核心标识：本质核心、理念思想、理论哲学、战略策略、宏观系统、思维框架、认知框架、方法论体系
- ⚠️ 注意：T层应该是最少的（约10-20%），具有明显统领性、思维框架性的内容才判定为T。

**判定原则**：
- D层（Down）应该最多（50-60%）：具体步骤、操作方法、实例示例、细节描述等
- M层（Middle）居中（25-35%）：关系分析、分类整理、转换方法、对比评估等
- T层（Top）应该最少（10-20%）：具有明显统领性、思维框架性的内容"""

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
            scene_context += "\n请结合当前场景的特点来判断DMT层次。"

        system_prompt = base_system_prompt + scene_context + "\n\n请仔细分析文本内容的抽象程度，严格判断。只返回一个字母：D、M、T 中的任意一个。如果无法明确判断，返回空字符串。\n\n你的回答格式：直接返回单个字母，不要有其他说明文字。"

        user_prompt = f"""请分析以下文本的DMT层次，只返回单个字母（D、M、T）或空字符串：

文本内容：
{content[:4000]}

请判断DMT层次："""

        # 调用kimi API
        API_KEY = _public_config.secret('KIMI_API_KEY')
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://api.moonshot.cn/v1",
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

        raw_text = extract_kimi_message_text(response.choices[0].message)
        result = raw_text.strip().upper()
        parsed = parse_llm_single_dmt(result)
        if parsed:
            print(f"[card_analyzer] kimi LLM判定DMT层次: {parsed}")
            return parsed
        debug_log_kimi_response('card_analyzer/dmt', response, raw_text=raw_text, parsed=parsed)
        print(f"[card_analyzer] kimi LLM返回无效结果，降级关键词匹配")
        return analyze_dmt_level(content)

    except Exception as e:
        print(f"[card_analyzer] kimi LLM判定DMT层次失败: {e}")
        return ''


def analyze_knowledge_type_with_llm(content, scene_name=None, sub_scene_name=None, scene_summary="",
                                    notebook_description="", keyword=None):
    """
    调用 LLM 判定三类知识类型：trad（传统显性）/ org（组织半显性）/ trib（部落隐性）。
    keyword 非空时针对该关键词在内容中的知识类型；否则针对整段文本/卡片。
    """
    if not content and not keyword:
        return ''

    focus = f'关键词「{keyword}」' if keyword else '文本'
    try:
        base_system_prompt = """你是知识类型分类专家。请判断内容属于三类知识中的哪一类：

**trad（传统知识）**：低维显性知识，可枚举、可配置的结构性一般知识（字段指标、时间规则、权限规则、标准术语等）。

**org（组织知识）**：中维半显性知识，治理/决策流程、责任分工、协作流程、分级响应、敏感表达规范等「谁来处理、怎么运转」的规则体系。

**trib（部落知识）**：高维隐性知识，长期实践积累的经验、直觉、诀窍（复合信号判断、成因链追溯、干预有效性预测、群体问题识别等），难以完全显性化。

注意：三类知识与 DMT（语义粒度层次）是不同维度，不要混淆。
只返回 trad、org、trib 三者之一；无法判断则返回空。"""

        scene_context = ""
        if scene_name:
            scene_context += f"\n\n**当前场景**：{scene_name}\n"
            if sub_scene_name:
                scene_context += f"**子场景**：{sub_scene_name}\n"
            if scene_summary:
                summary_short = scene_summary[:300] + "..." if len(scene_summary) > 300 else scene_summary
                scene_context += f"**场景摘要**：{summary_short}\n"
            if notebook_description:
                scene_context += f"**本子描述**：{notebook_description}\n"

        system_prompt = base_system_prompt + scene_context + "\n\n只返回 trad、org 或 trib，无其他文字。"
        if keyword:
            user_prompt = f"""请判断以下{focus}在卡片内容中体现的知识类型（trad/org/trib）：

**关键词**：{keyword}

**卡片内容**：
{content[:4000]}"""
        else:
            user_prompt = f"""请判断以下文本的知识类型（trad/org/trib）：

{content[:4000]}"""

        API_KEY = _public_config.secret('KIMI_API_KEY')
        client = OpenAI(api_key=API_KEY, base_url="https://api.moonshot.cn/v1")
        response = client.chat.completions.create(
            model=KIMI_CLASSIFY_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=KIMI_CLASSIFY_TEMPERATURE,
            max_tokens=20,
            extra_body=KIMI_CLASSIFY_EXTRA_BODY,
        )
        raw_text = extract_kimi_message_text(response.choices[0].message)
        parsed = parse_knowledge_type(raw_text.strip())
        if parsed:
            print(f"[card_analyzer] kimi LLM判定三类知识: {parsed}" + (f" keyword={keyword}" if keyword else ''))
            return parsed
        debug_log_kimi_response('card_analyzer/knowledge_type', response, raw_text=raw_text, parsed=parsed)
    except Exception as e:
        print(f"[card_analyzer] kimi LLM判定三类知识失败: {e}" + (f" keyword={keyword}" if keyword else ''))
    return ''


def analyze_dmt_level(content):
    """
    通过关键词判定卡片的DMT层次
    返回：'D'（Down）、'M'（Middle）、'T'（Top）或空字符串
    """
    if not content:
        return ''

    content_lower = content.lower()

    # Down层（具象、具体、细节、操作）
    down_keywords = [
        '具体', '详细', '步骤', '操作', '方法', '做法', '实施',
        '示例', '例子', '案例', '实例', '例子', '样本', '数据',
        '代码', '命令', '参数', '配置', '设置', '选项', '值',
        '如何', '怎样', '怎么', '什么', '哪些', '哪个', '哪里',
        '细节', '细部', '局部', '微观', '小', '细', '具体',
        '执行', '运行', '使用', '应用', '调用', '创建', '删除'
    ]

    # Middle层（中性、中等、连接、过渡）
    middle_keywords = [
        '中等', '适中', '平衡', '协调', '整合', '融合', '结合',
        '关系', '联系', '关联', '相关', '对应', '匹配', '映射',
        '转换', '转化', '变化', '演进', '发展', '进步', '提升',
        '桥梁', '纽带', '中介', '中间', '过渡', '衔接', '连接',
        '分类', '分组', '组织', '结构', '层次', '层级', '级别',
        '比较', '对比', '分析', '评估', '判断', '选择', '决策'
    ]

    # Top层（抽象、宏观、本质、全局）
    top_keywords = [
        '本质', '核心', '根本', '基础', '根源', '源头', '起源',
        '理念', '观念', '思想', '理论', '哲学', '原理', '原则',
        '宏观', '全局', '整体', '系统', '体系', '框架', '架构',
        '战略', '策略', '规划', '设计', '愿景', '目标', '方向',
        '意义', '价值', '目的', '宗旨', '使命', '追求', '理想',
        '抽象', '概括', '总结', '归纳', '升华', '提升', '超越',
        '洞察', '洞见', '智慧', '深刻', '透彻', '全面', '整体'
    ]

    # 统计各层关键词出现次数
    down_count = sum(1 for kw in down_keywords if kw in content_lower)
    middle_count = sum(1 for kw in middle_keywords if kw in content_lower)
    top_count = sum(1 for kw in top_keywords if kw in content_lower)

    # 如果都没有匹配，默认返回空字符串
    max_count = max(down_count, middle_count, top_count)
    if max_count == 0:
        return ''

    # 🔥 调整判定逻辑：D最多（50-60%），M居中（25-35%），T最少（10-20%）
    # 1. T层判定要更严格：只有当top_count明显高于其他时才判定为T
    if top_count >= 3 and top_count >= down_count * 2 and top_count >= middle_count * 2:
        return 'T'

    # 2. M层判定：middle_count明显高于down_count时判定为M
    if middle_count >= 2 and middle_count >= down_count * 1.5:
        return 'M'

    # 3. 默认判定为D（因为D应该是最多的，原子性、具体操作层面的内容占大多数）
    # 只有当down_count明显低于其他时，才考虑M或T
    if down_count >= 1:
        return 'D'

    # 4. 如果down_count为0，根据middle和top判断
    if middle_count > 0 and middle_count >= top_count:
        return 'M'
    elif top_count > 0:
        return 'T'

    return 'D'  # 默认返回D


def analyze_four_color_type_for_new_card(content, scene_name=None, sub_scene_name=None, scene_summary="",
                                         notebook_description=""):
    """
    🔥 新卡片四色分析：先Kimi（10s超时），失败则降级到关键词匹配
    返回：'R'（红）、'B'（蓝）、'P'（紫）、'G'（绿）或空字符串

    Args:
        content: 卡片内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not content:
        return ''

    # 🔥 先尝试Kimi分析（5s超时）
    def kimi_analysis():
        try:
            return analyze_four_color_type_with_llm(
                content,
                scene_name=scene_name,
                sub_scene_name=sub_scene_name,
                scene_summary=scene_summary,
                notebook_description=notebook_description
            )
        except Exception as e:
            print(f"[analyze_four_color_type_for_new_card] Kimi分析异常: {e}")
            return ''

    try:
        # 使用线程池执行Kimi分析，设置5s超时
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(kimi_analysis)
            try:
                result = future.result(timeout=10.0)
                if result and result in ['R', 'B', 'P', 'G']:
                    print(f"[analyze_four_color_type_for_new_card] Kimi分析成功: {result}")
                    return result
            except concurrent.futures.TimeoutError:
                print(f"[analyze_four_color_type_for_new_card] Kimi分析超时（>10s），降级到关键词匹配")
                future.cancel()  # 取消任务
            except Exception as e:
                print(f"[analyze_four_color_type_for_new_card] Kimi分析失败: {e}，降级到关键词匹配")
    except Exception as e:
        print(f"[analyze_four_color_type_for_new_card] Kimi分析异常: {e}，降级到关键词匹配")

    # 🔥 Kimi失败或超时，降级到关键词匹配
    print(f"[analyze_four_color_type_for_new_card] 使用关键词匹配进行降级分析")
    return analyze_four_color_type(content)


def analyze_dmt_level_for_new_card(content, scene_name=None, sub_scene_name=None, scene_summary="",
                                   notebook_description=""):
    """
    🔥 新卡片DMT分析：先Kimi（10s超时），失败则降级到关键词匹配
    返回：'D'（Down）、'M'（Middle）、'T'（Top）或空字符串

    Args:
        content: 卡片内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not content:
        return ''

    # 🔥 先尝试Kimi分析（5s超时）
    def kimi_analysis():
        try:
            return analyze_dmt_level_with_llm(
                content,
                scene_name=scene_name,
                sub_scene_name=sub_scene_name,
                scene_summary=scene_summary,
                notebook_description=notebook_description
            )
        except Exception as e:
            print(f"[analyze_dmt_level_for_new_card] Kimi分析异常: {e}")
            return ''

    try:
        # 使用线程池执行Kimi分析，设置5s超时
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(kimi_analysis)
            try:
                result = future.result(timeout=10.0)
                if result and result in ['D', 'M', 'T']:
                    print(f"[analyze_dmt_level_for_new_card] Kimi分析成功: {result}")
                    return result
            except concurrent.futures.TimeoutError:
                print(f"[analyze_dmt_level_for_new_card] Kimi分析超时（>10s），降级到关键词匹配")
                future.cancel()  # 取消任务
            except Exception as e:
                print(f"[analyze_dmt_level_for_new_card] Kimi分析失败: {e}，降级到关键词匹配")
    except Exception as e:
        print(f"[analyze_dmt_level_for_new_card] Kimi分析异常: {e}，降级到关键词匹配")

    # 🔥 Kimi失败或超时，降级到关键词匹配
    print(f"[analyze_dmt_level_for_new_card] 使用关键词匹配进行降级分析")
    return analyze_dmt_level(content)


def check_card_has_value_for_analysis(card, all_cards_data=None, total_cards_count=None):
    """
    🔥 前置存在性评判：判断卡片是否有打上四色/DMT属性的价值

    有价值的卡片包括：
    1. 确定性类型（代码直接判断）：
       - 神经元卡
       - 进化卡
       - 被勾选次数多的卡
       - 包含文档总示意图的文档摘要卡
       - 文档交叉梳理建议卡
       - 提问得分较高的问答卡
    2. LLM判别类型：
       - 内容质量贴合场景的子场景且字数篇幅颗粒度适中或较小的问答卡

    返回：True表示有价值，False表示低价值

    Args:
        card: 卡片对象或字典，需要包含：
            - content: 卡片内容
            - contentTitle: 卡片标题（格式：S1:标题）
            - is_neuron: 是否为神经元卡
            - is_evolved: 是否为进化卡
            - selection_count: 被勾选次数
            - cid: 卡片ID
        all_cards_data: 所有卡片数据列表（可选，用于计算被勾选次数等）
        total_cards_count: 总卡片数量（可选，用于LLM判断比例）
    """
    if not card:
        return False

    # 获取卡片属性
    content = card.get('content', '') if isinstance(card, dict) else getattr(card, 'content', '')
    content_title = card.get('contentTitle', '') if isinstance(card, dict) else getattr(card, 'contentTitle', '')
    is_neuron = card.get('is_neuron', False) if isinstance(card, dict) else getattr(card, 'is_neuron', False)
    is_evolved = card.get('is_evolved', False) if isinstance(card, dict) else getattr(card, 'is_evolved', False)

    # 1. 确定性判断：神经元卡、进化卡
    if is_neuron or is_evolved:
        print(f"[check_card_has_value_for_analysis] 卡片是神经元卡或进化卡，判定为有价值")
        return True

    # 2. 确定性判断：被勾选次数多的卡
    selection_count = card.get('selection_count', 0) if isinstance(card, dict) else getattr(card, 'selection_count', 0)
    if all_cards_data and isinstance(all_cards_data, list) and len(all_cards_data) > 0:
        # 计算所有卡片被勾选次数的平均值
        all_selection_counts = [c.get('selection_count', 0) if isinstance(c, dict) else getattr(c, 'selection_count', 0) for c in all_cards_data]
        if all_selection_counts:
            avg_selection_count = sum(all_selection_counts) / len(all_selection_counts)
            # 只有当平均值大于0且当前卡片被勾选次数超过平均值的1.5倍时，才判定为有价值
            if avg_selection_count > 0 and selection_count > avg_selection_count * 1.5:
                print(f"[check_card_has_value_for_analysis] 卡片被勾选次数较多（{selection_count}），判定为有价值")
                return True

    # 3. 确定性判断：文档摘要卡（单文档【文件摘要】或多增量【综合摘要】）
    if content:
        s = content.strip()
        is_single_summary = s.startswith('【文件摘要】') and (
            '【章节摘要】' in s or '二、金句萃取与重要细节标注' in s
        )
        is_multi_summary = s.startswith('【综合摘要】')
        if is_single_summary or is_multi_summary:
            print(f"[check_card_has_value_for_analysis] 卡片是文档摘要卡，判定为有价值")
            return True

    # 4. 确定性判断：文档交叉梳理建议卡
    if content and content.strip().startswith('【文档全面交叉梳理建议卡片】'):
        print(f"[check_card_has_value_for_analysis] 卡片是文档交叉梳理建议卡，判定为有价值")
        return True

    # 5. 确定性判断：提问得分较高的问答卡
    # from app_chat.card_filter import extract_questions_from_card, calculate_question_score
    # questions = extract_questions_from_card(card if isinstance(card, dict) else {'content': content})
    # if questions:
    #     question_scores = [calculate_question_score(q) for q in questions]
    #     if question_scores:
    #         avg_score = sum(question_scores) / len(question_scores)
    #         max_score = max(question_scores)
    #         if avg_score >= 3.0 or max_score >= 3.5:
    #             print(f"[check_card_has_value_for_analysis] 卡片包含高价值问题（平均分={avg_score:.2f}, 最高分={max_score:.2f}），判定为有价值")
    #             return True

    # 6. LLM判别：内容质量贴合场景的子场景且字数篇幅颗粒度适中或较小的问答卡
    # 提取子场景信息
    sub_scene_name = None
    if content_title:
        import re
        subscene_match = re.search(r'^S(\d+)[:：]', content_title)
        if subscene_match:
            # 这里需要获取场景信息来判断
            # 先返回False，后续在分析时会通过LLM判断
            pass

    # 对于其他类型的卡片，需要通过LLM进一步判断
    # 这部分会在analyze_card_with_new_standard中处理
    return None  # None表示需要LLM进一步判断


def analyze_card_value_with_llm(card, scene_name=None, sub_scene_name=None, scene_summary="",
                                notebook_description="", total_cards_count=None,
                                all_cards_data=None):
    """
    🔥 使用LLM判断卡片是否有打上四色/DMT属性的价值
    专门针对内容质量贴合场景的子场景且字数篇幅颗粒度适中或较小的问答卡

    返回：True表示有价值，False表示低价值

    Args:
        card: 卡片对象或字典
        scene_name: 场景名
        sub_scene_name: 子场景名
        scene_summary: 场景摘要
        notebook_description: 本子描述
        total_cards_count: 总卡片数量
    """
    # return False

    if not card:
        return False

    content = card.get('content', '') if isinstance(card, dict) else getattr(card, 'content', '')
    content_title = card.get('contentTitle', '') if isinstance(card, dict) else getattr(card, 'contentTitle', '')

    if not content:
        return False

    cid = card.get('cid') if isinstance(card, dict) else getattr(card, 'cid', None)

    try:
        word_count = len(content)
        scene_context = build_value_scene_context(
            scene_name, sub_scene_name, scene_summary, notebook_description,
            total_cards_count, all_cards_data, exclude_cid=cid
        )
        system_prompt = STRICT_VALUE_SYSTEM_PROMPT + scene_context

        # 截断内容（限制在4000字符内）
        content_preview = content[:4000]
        if len(content) > 4000:
            content_preview += "..."

        user_prompt = f"""请判断以下卡片是否有打上四色/DMT属性的价值（本子内高价值卡宜约10-15%；严格判断，只有真正高水准的才判 YES）：

卡片标题：{content_title}
卡片字数：{word_count}字

卡片内容：
{content_preview}

请判断："""

        # 调用kimi API
        API_KEY = _public_config.secret('KIMI_API_KEY')
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://api.moonshot.cn/v1",
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

        raw_text = extract_kimi_message_text(response.choices[0].message)
        result = raw_text.strip().upper()

        if result.startswith('YES') or result == 'Y':
            print(f"[analyze_card_value_with_llm] LLM判定卡片有价值")
            return True
        if result.startswith('NO') or result == 'N':
            print(f"[analyze_card_value_with_llm] LLM判定卡片低价值")
            return False
        debug_log_kimi_response('analyze_card_value_with_llm', response, raw_text=raw_text)
        print(f"[analyze_card_value_with_llm] LLM返回模糊({result!r})，从严默认低价值")
        return False

    except Exception as e:
        print(f"[analyze_card_value_with_llm] LLM判断卡片价值失败: {e}，默认低价值")
        return False


def _run_four_color_dmt_llm_parallel(content, scene_name, sub_scene_name, scene_summary, notebook_description):
    """并发执行四色/DMT LLM 分析，10s 超时。"""
    def four_color_analysis():
        try:
            return analyze_four_color_type_with_llm(
                content, scene_name, sub_scene_name, scene_summary, notebook_description
            )
        except Exception as e:
            print(f"[analyze_card_with_new_standard] 四色分析异常: {e}")
            return ''

    def dmt_analysis():
        try:
            return analyze_dmt_level_with_llm(
                content, scene_name, sub_scene_name, scene_summary, notebook_description
            )
        except Exception as e:
            print(f"[analyze_card_with_new_standard] DMT分析异常: {e}")
            return ''

    four_color_type = dmt_level = ''
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            four_color_future = executor.submit(four_color_analysis)
            dmt_future = executor.submit(dmt_analysis)
            try:
                four_color_type = four_color_future.result(timeout=10.0)
                dmt_level = dmt_future.result(timeout=10.0)
            except concurrent.futures.TimeoutError:
                print(f"[analyze_card_with_new_standard] 分析超时（>10s）")
                four_color_future.cancel()
                dmt_future.cancel()
    except Exception as e:
        print(f"[analyze_card_with_new_standard] 并发分析异常: {e}")
    return four_color_type, dmt_level


def analyze_card_with_new_standard(card, scene_name=None, sub_scene_name=None,
                                   scene_summary="", notebook_description="",
                                   all_cards_data=None, total_cards_count=None,
                                   force_analyze=False):
    """
    🔥 按照新标准分析卡片：包含前置存在性评判的四色/DMT分析

    流程：
    1. 前置存在性评判：规则预判（神经元/进化/高勾选/特定摘要卡等）→ 未命中时 LLM 判高价值 YES/NO
    2. 高价值：并发调用 LLM 判定四色与 DMT（各 10s 超时）
    3. 低价值：四色/DMT 直接置空，不再走关键词/规则降级，也不再补调 LLM

    force_analyze 参数已弃用：传入 True 仅打警告，不会跳过价值筛分。

    返回：(four_color_type, dmt_level, is_analyzed_by_new_standard)

    Args:
        card: 卡片对象或字典，需要包含 content, contentTitle, is_neuron, is_evolved, selection_count, cid 等字段
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景摘要（可选）
        notebook_description: 本子描述（可选）
        all_cards_data: 所有卡片数据列表（可选，用于判断被勾选次数等）
        total_cards_count: 总卡片数量（可选）
    """
    four_color_type = ''
    dmt_level = ''
    is_analyzed_by_new_standard = False

    # 获取卡片内容
    content = card.get('content', '') if isinstance(card, dict) else getattr(card, 'content', '')
    if not content:
        return '', '', True  # 空内容，直接标记为已分析

    # 如果没有场景信息，尝试从card获取
    if not scene_name:
        username = card.get('username', '') if isinstance(card, dict) else getattr(card, 'username', '')
        content_title = card.get('contentTitle', '') if isinstance(card, dict) else getattr(card, 'contentTitle', '')
        if username:
            from app_chat.scene_context_helper import get_scene_info_from_username
            scene_name, sub_scene_name, scene_summary, notebook_description = get_scene_info_from_username(
                username, content_title
            )

    if force_analyze:
        print(f"[analyze_card_with_new_standard] 警告: force_analyze 已弃用，仍走价值筛分")

    has_value = check_card_has_value_for_analysis(card, all_cards_data, total_cards_count)
    if has_value is None:
        has_value = analyze_card_value_with_llm(
            card, scene_name, sub_scene_name, scene_summary,
            notebook_description, total_cards_count, all_cards_data=all_cards_data
        )

    if has_value:
        print(f"[analyze_card_with_new_standard] 卡片判定为有价值，开始进行四色/DMT分析（使用LLM）")
        four_color_type, dmt_level = _run_four_color_dmt_llm_parallel(
            content, scene_name, sub_scene_name, scene_summary, notebook_description
        )
        is_analyzed_by_new_standard = True
    else:
        print(f"[analyze_card_with_new_standard] 卡片判定为低价值，四色/DMT置空")
        is_analyzed_by_new_standard = True

    return four_color_type, dmt_level, is_analyzed_by_new_standard
