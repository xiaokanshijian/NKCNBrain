"""
文档四色和DMT属性判定工具
三级回滚机制：GPT -> Kimi -> 关键词匹配
一个文档做一次分析，保存在document的meta属性中
"""
from app_chat.card_analyzer import analyze_four_color_type, analyze_dmt_level
from app_chat import gpt4_api, kimi_api


def analyze_document_four_color_type_with_gpt(full_content, scene_name=None, sub_scene_name=None, scene_summary="", notebook_description=""):
    """
    使用GPT（低温度）分析文档的四色主辅色类型
    返回：主色（'R'/'B'/'P'/'G'），辅色（'R'/'B'/'P'/'G'）或空字符串

    Args:
        full_content: 文档完整内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not full_content:
        return '', ''

    try:
        # 截取前8000字符作为分析样本（避免内容过长）
        content_sample = full_content[:8000]

        # 🔥 获取场景相关的四色示例
        from app_chat.scene_context_helper import get_scene_four_color_examples
        scene_examples = get_scene_four_color_examples(scene_name) if scene_name else None

        # 构建基础prompt
        base_system_prompt = """你是一个专业的文档分类专家，擅长分析文档的语言特征和语境类型。

你需要根据文档内容判断其四色语境类型的主色和辅色，判断标准如下：

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

        system_prompt = base_system_prompt + scene_context + "\n\n请仔细分析文档内容，判断主色和辅色（按占比从高到低）。\n只返回格式：主色字母,辅色字母（例如：R,B 或 P,G 或 B, 表示只有主色无辅色）\n如果无法明确判断，返回空字符串。\n\n你的回答格式：直接返回\"主色,辅色\"或\"主色,\"，不要有其他说明文字。"

        user_prompt = f"""请分析以下文档内容的四色语境类型，判断主色和辅色：

文档内容：
{content_sample}

请判断主色和辅色（格式：主色,辅色）："""

        # 🔥 使用gpt4_api中的函数调用GPT
        # 临时修改global_var.config以确保使用低温度和小的max_tokens
        from llm_langchain import global_var
        original_temp = global_var.config.get("temperature", 0.7)
        original_max_tokens = global_var.config.get("max_tokens", 4096)

        try:
            # 临时设置低温度和小的max_tokens
            global_var.config["temperature"] = 0.1
            global_var.config["max_tokens"] = 10

            # 调用gpt4_api中的函数
            result_text = gpt4_api.make_gpt4o_text_requests(user_prompt, system_prompt)
            result = result_text.strip().upper()
        finally:
            # 恢复原始配置
            global_var.config["temperature"] = original_temp
            global_var.config["max_tokens"] = original_max_tokens

        # 解析结果：主色,辅色 或 主色,
        if ',' in result:
            parts = result.split(',')
            main_color = parts[0].strip()
            secondary_color = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ''

            # 验证主色
            if main_color in ['R', 'B', 'P', 'G']:
                # 验证辅色
                if secondary_color in ['R', 'B', 'P', 'G']:
                    print(f"[document_analyzer] GPT判定四色类型: 主色={main_color}, 辅色={secondary_color}")
                    return main_color, secondary_color
                elif not secondary_color:
                    print(f"[document_analyzer] GPT判定四色类型: 主色={main_color}, 无辅色")
                    return main_color, ''

        print(f"[document_analyzer] GPT返回无效结果: {result}")
        return '', ''

    except Exception as e:
        print(f"[document_analyzer] GPT判定四色类型失败: {e}")
        return '', ''


def analyze_document_four_color_type_with_kimi(full_content, scene_name=None, sub_scene_name=None, scene_summary="", notebook_description=""):
    """
    使用Kimi分析文档的四色主辅色类型
    返回：主色（'R'/'B'/'P'/'G'），辅色（'R'/'B'/'P'/'G'）或空字符串

    Args:
        full_content: 文档完整内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not full_content:
        return '', ''

    try:
        # 截取前8000字符作为分析样本
        content_sample = full_content[:8000]

        # 🔥 获取场景相关的四色示例
        from app_chat.scene_context_helper import get_scene_four_color_examples
        scene_examples = get_scene_four_color_examples(scene_name) if scene_name else None

        # 构建基础prompt
        base_system_prompt = """你是一个专业的文档分类专家，擅长分析文档的语言特征和语境类型。

你需要根据文档内容判断其四色语境类型的主色和辅色，判断标准如下：

**红色（R）- 行业领域语言**：专业、严谨、权威，目标指向品质提高
**蓝色（B）- 技术工具语言**：目标指向效率提高
**紫色（P）- 场景思维语言**：逻辑思维性，系统性推演、方法论框架
**绿色（G）- 自然语言**：简单深刻，陪伴、滋润、敬畏，不虚伪、不浮华、不僵化"""

        # 🔥 如果提供了场景信息，添加场景特定的示例
        scene_context = ""
        if scene_name:
            scene_context += f"\n\n**当前场景信息**：\n"
            scene_context += f"- 场景名称：{scene_name}\n"
            if sub_scene_name:
                scene_context += f"- 子场景名称：{sub_scene_name}\n"
            if scene_summary:
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

        system_prompt = base_system_prompt + scene_context + "\n\n请仔细分析文档内容，判断主色和辅色（按占比从高到低）。\n只返回格式：主色字母,辅色字母（例如：R,B 或 P,G 或 B, 表示只有主色无辅色）\n如果无法明确判断，返回空字符串。\n\n你的回答格式：直接返回\"主色,辅色\"或\"主色,\"，不要有其他说明文字。"

        user_prompt = f"""请分析以下文档内容的四色语境类型，判断主色和辅色：

文档内容：
{content_sample}

请判断主色和辅色（格式：主色,辅色）："""

        # 🔥 使用kimi_api中的函数调用Kimi
        # 合并system和user prompt
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # 临时修改global_var.kimiConfig以确保使用小的max_tokens
        from llm_langchain import global_var
        original_max_tokens = global_var.kimiConfig.get("max_tokens", 4096)

        try:
            # 临时设置小的max_tokens
            global_var.kimiConfig["max_tokens"] = 10

            # 调用kimi_api中的函数（is_completion=False表示对话模式，temperature=0.1低温度）
            response = kimi_api.make_requests(full_prompt, None, False, 0.1)
            result = response.choices[0].message.content.strip().upper()
        finally:
            # 恢复原始配置
            global_var.kimiConfig["max_tokens"] = original_max_tokens

        # 解析结果：主色,辅色 或 主色,
        if ',' in result:
            parts = result.split(',')
            main_color = parts[0].strip()
            secondary_color = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ''

            # 验证主色
            if main_color in ['R', 'B', 'P', 'G']:
                # 验证辅色
                if secondary_color in ['R', 'B', 'P', 'G']:
                    print(f"[document_analyzer] Kimi判定四色类型: 主色={main_color}, 辅色={secondary_color}")
                    return main_color, secondary_color
                elif not secondary_color:
                    print(f"[document_analyzer] Kimi判定四色类型: 主色={main_color}, 无辅色")
                    return main_color, ''

        print(f"[document_analyzer] Kimi返回无效结果: {result}")
        return '', ''

    except Exception as e:
        print(f"[document_analyzer] Kimi判定四色类型失败: {e}")
        return '', ''


def analyze_document_four_color_type(full_content, scene_name=None, sub_scene_name=None, scene_summary="", notebook_description=""):
    """
    三级回滚机制分析文档的四色主辅色类型
    1. GPT（低温度）
    2. Kimi
    3. 关键词匹配（仅判断主色）

    返回：主色（'R'/'B'/'P'/'G'），辅色（'R'/'B'/'P'/'G'）或空字符串

    Args:
        full_content: 文档完整内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not full_content:
        return '', ''

    # 第一级：尝试GPT
    main_color, secondary_color = analyze_document_four_color_type_with_gpt(
        full_content, scene_name, sub_scene_name, scene_summary, notebook_description
    )
    if main_color:
        return main_color, secondary_color

    # 第二级：尝试Kimi
    main_color, secondary_color = analyze_document_four_color_type_with_kimi(
        full_content, scene_name, sub_scene_name, scene_summary, notebook_description
    )
    if main_color:
        return main_color, secondary_color

    # 第三级：关键词匹配（仅判断主色，无辅色）
    main_color = analyze_four_color_type(full_content)
    if main_color:
        print(f"[document_analyzer] 关键词匹配判定四色类型: {main_color}")
        return main_color, ''

    return '', ''


def analyze_document_dmt_level_with_gpt(full_content, scene_name=None, sub_scene_name=None, scene_summary="", notebook_description=""):
    """
    使用GPT（低温度）分析文档的DMT层次
    返回：'D'（Down）、'M'（Middle）、'T'（Top）或空字符串

    Args:
        full_content: 文档完整内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not full_content:
        return ''

    try:
        # 截取前8000字符作为分析样本
        content_sample = full_content[:8000]

        # 构建基础prompt
        base_system_prompt = """你是一个专业的文档分类专家，擅长分析文档的抽象层次。

你需要根据文档内容判断其DMT层次，判断标准如下：

**D层（Down）- 底层**：
- 特征：具象、具体、细节、操作层面
- 核心标识：具体步骤、操作方法、实例示例、代码命令、细节描述

**M层（Middle）- 中层**：
- 特征：中性、中等抽象程度、连接、过渡
- 核心标识：关系联系、转换转化、分类组织、比较分析

**T层（Top）- 顶层**：
- 特征：抽象、宏观、本质、全局、统领性、思维框架性
- 核心标识：本质核心、理念思想、理论哲学、战略策略、宏观系统、思维框架、认知框架、方法论体系
- ⚠️ 注意：T层应该是最少的（约10-20%），具有明显统领性、思维框架性的内容才判定为T

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

        system_prompt = base_system_prompt + scene_context + "\n\n请仔细分析文档内容的抽象程度，严格判断。只返回一个字母：D、M、T 中的任意一个。如果无法明确判断，返回空字符串。\n\n你的回答格式：直接返回单个字母，不要有其他说明文字。"

        user_prompt = f"""请分析以下文档内容的DMT层次：

文档内容：
{content_sample}

请判断DMT层次："""

        # 🔥 使用gpt4_api中的函数调用GPT
        # 临时修改global_var.config以确保使用低温度和小的max_tokens
        from llm_langchain import global_var
        original_temp = global_var.config.get("temperature", 0.7)
        original_max_tokens = global_var.config.get("max_tokens", 4096)

        try:
            # 临时设置低温度和小的max_tokens
            global_var.config["temperature"] = 0.1
            global_var.config["max_tokens"] = 10

            # 调用gpt4_api中的函数
            result_text = gpt4_api.make_gpt4o_text_requests(user_prompt, system_prompt)
            result = result_text.strip().upper()
        finally:
            # 恢复原始配置
            global_var.config["temperature"] = original_temp
            global_var.config["max_tokens"] = original_max_tokens

        # 验证结果是否为有效的DMT层次
        if result in ['D', 'M', 'T']:
            print(f"[document_analyzer] GPT判定DMT层次: {result}")
            return result
        else:
            print(f"[document_analyzer] GPT返回无效结果: {result}")
            return ''

    except Exception as e:
        print(f"[document_analyzer] GPT判定DMT层次失败: {e}")
        return ''


def analyze_document_dmt_level_with_kimi(full_content, scene_name=None, sub_scene_name=None, scene_summary="", notebook_description=""):
    """
    使用Kimi分析文档的DMT层次
    返回：'D'（Down）、'M'（Middle）、'T'（Top）或空字符串

    Args:
        full_content: 文档完整内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not full_content:
        return ''

    try:
        # 截取前8000字符作为分析样本
        content_sample = full_content[:8000]

        # 构建基础prompt
        base_system_prompt = """你是一个专业的文档分类专家，擅长分析文档的抽象层次。

你需要根据文档内容判断其DMT层次，判断标准如下：

**D层（Down）- 底层**：
- 特征：具象、具体、细节、操作层面
- 核心标识：具体步骤、操作方法、实例示例、代码命令、细节描述

**M层（Middle）- 中层**：
- 特征：中性、中等抽象程度、连接、过渡
- 核心标识：关系联系、转换转化、分类组织、比较分析

**T层（Top）- 顶层**：
- 特征：抽象、宏观、本质、全局、统领性、思维框架性
- 核心标识：本质核心、理念思想、理论哲学、战略策略、宏观系统、思维框架、认知框架、方法论体系
- ⚠️ 注意：T层应该是最少的（约10-20%），具有明显统领性、思维框架性的内容才判定为T

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
                summary_short = scene_summary[:300] + "..." if len(scene_summary) > 300 else scene_summary
                scene_context += f"- 场景内涵摘要：{summary_short}\n"
            if notebook_description:
                scene_context += f"- 本子描述：{notebook_description}\n"
            scene_context += "\n请结合当前场景的特点来判断DMT层次。"

        system_prompt = base_system_prompt + scene_context + "\n\n请仔细分析文档内容的抽象程度，严格判断。只返回一个字母：D、M、T 中的任意一个。如果无法明确判断，返回空字符串。\n\n你的回答格式：直接返回单个字母，不要有其他说明文字。"

        user_prompt = f"""请分析以下文档内容的DMT层次，只返回单个字母（D、M、T）或空字符串：

文档内容：
{content_sample}

请判断DMT层次："""

        # 🔥 使用kimi_api中的函数调用Kimi
        # 合并system和user prompt
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # 临时修改global_var.kimiConfig以确保使用小的max_tokens
        from llm_langchain import global_var
        original_max_tokens = global_var.kimiConfig.get("max_tokens", 4096)

        try:
            # 临时设置小的max_tokens
            global_var.kimiConfig["max_tokens"] = 10

            # 调用kimi_api中的函数（is_completion=False表示对话模式，temperature=0.1低温度）
            response = kimi_api.make_requests(full_prompt, None, False, 0.1)
            result = response.choices[0].message.content.strip().upper()
        finally:
            # 恢复原始配置
            global_var.kimiConfig["max_tokens"] = original_max_tokens

        # 验证结果是否为有效的DMT层次
        if result in ['D', 'M', 'T']:
            print(f"[document_analyzer] Kimi判定DMT层次: {result}")
            return result
        else:
            print(f"[document_analyzer] Kimi返回无效结果: {result}")
            return ''

    except Exception as e:
        print(f"[document_analyzer] Kimi判定DMT层次失败: {e}")
        return ''


def analyze_document_dmt_level(full_content, scene_name=None, sub_scene_name=None, scene_summary="", notebook_description=""):
    """
    三级回滚机制分析文档的DMT层次
    1. GPT（低温度）
    2. Kimi
    3. 关键词匹配

    返回：'D'（Down）、'M'（Middle）、'T'（Top）或空字符串

    Args:
        full_content: 文档完整内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not full_content:
        return ''

    # 第一级：尝试GPT
    result = analyze_document_dmt_level_with_gpt(
        full_content, scene_name, sub_scene_name, scene_summary, notebook_description
    )
    if result:
        return result

    # 第二级：尝试Kimi
    result = analyze_document_dmt_level_with_kimi(
        full_content, scene_name, sub_scene_name, scene_summary, notebook_description
    )
    if result:
        return result

    # 第三级：关键词匹配
    result = analyze_dmt_level(full_content)
    if result:
        print(f"[document_analyzer] 关键词匹配判定DMT层次: {result}")
        return result

    return ''


def analyze_document_attributes(full_content, scene_name=None, sub_scene_name=None, scene_summary="", notebook_description=""):
    """
    综合分析文档的四色主辅色和DMT层次
    返回：{
        'main_four_color': 'R'/'B'/'P'/'G' 或 '',
        'secondary_four_color': 'R'/'B'/'P'/'G' 或 '',
        'dmt_level': 'D'/'M'/'T' 或 ''
    }

    Args:
        full_content: 文档完整内容
        scene_name: 场景名（可选）
        sub_scene_name: 子场景名（可选）
        scene_summary: 场景内涵摘要（可选）
        notebook_description: 本子描述（可选）
    """
    if not full_content:
        return {
            'main_four_color': '',
            'secondary_four_color': '',
            'dmt_level': ''
        }

    # 分析四色主辅色
    main_color, secondary_color = analyze_document_four_color_type(
        full_content, scene_name, sub_scene_name, scene_summary, notebook_description
    )

    # 分析DMT层次
    dmt_level = analyze_document_dmt_level(
        full_content, scene_name, sub_scene_name, scene_summary, notebook_description
    )
    
    return {
        'main_four_color': main_color,
        'secondary_four_color': secondary_color,
        'dmt_level': dmt_level
    }
