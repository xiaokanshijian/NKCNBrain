"""
DMT版面分析系统的提示词配置文件
包含所有用于AI分析的提示词模板
"""

# D版面分析提示词(无预置内容)
D_HANDWRITTEN_PROMPT = """请你从以下维度对该版面进行解读：
1. content_text: 理解该版面本身的具体内容，重点区分印刷内容和手写内容，手写内容涵盖小组同学和TA（助教）的手写笔迹，小组同学通常使用铅笔或黑色签字笔，TA（助教）通常使用红色笔。注意，如果手写内容涉及TA评分，则TA评分不会低于3分。如果辨认不清或识别出的内容有错别字、不通顺、不合理，需要结合上下文信息补全或修正。不超过300字。
2. otcl_analysis: 判断该版面存在哪些OTCL（目标/任务/主线/日志）特征，并提取对应特征的内容。不超过50字。
3. format_evaluation: 评估手写内容的书写规范和版面饱满度。不超过30字。
4. confidence: 手写内容的识别置信度，类型是小数，范围0到1，0表示完全不确定，1表示非常确定。
5. abnormality_eval: 以客观、中立的态度，评估你对该版面的解读是否存在异常，异常包括但不限于：OTCL特征提取不合理、解读逻辑不通顺、手写内容无法理解、版面字体不清晰等。给出异常程度（低/中/高）和异常原因。不超过50字。
请你以JSON格式输出，不要输出```json```代码段：
"""

# D版面分析提示词(有预置内容)
D_PRINTED_PROMPT = """请你从以下维度对该版面进行解读：
1. otcl_analysis: 判断该版面存在哪些OTCL（目标/任务/主线/日志）特征，并提取对应特征的内容。不超过50字。
2. abnormality_eval: 以客观、中立的态度，评估你对该版面的解读是否存在异常，异常包括但不限于：OTCL特征提取不合理、版面字体不清晰、印刷内容不完整等。给出异常程度（低/中/高）和异常原因。不超过50字。
请你以JSON格式输出，不要输出```json```代码段："""

# D版面分析提示词(提取组号)
D_GROUP_PROMPT = """请你提取该版面中的组号信息，通常位于小组二维码的正中央，格式为“G组号”，例如“G1”。
请你以如下JSON格式输出，不要输出```json```代码段：
{
    "group_number": "G组号"
}
"""

# D版面分析提示词
D_ANALYSIS_PROMPT = """请你从以下维度对该版面进行解读：
1. content_text: 理解该版面本身的具体内容，重点区分印刷内容和手写内容，手写内容涵盖小组同学和TA（助教）的手写笔迹，小组同学通常使用铅笔或黑色签字笔，TA（助教）通常使用红色笔。注意，如果手写内容涉及TA评分，则TA评分不会低于3分。如果辨认不清或识别出的内容有错别字、不通顺、不合理，需要结合上下文信息补全或修正。不超过300字。
2. otcl_analysis: 判断该版面存在哪些OTCL（目标/任务/主线/日志）特征，并提取对应特征的内容。不超过50字。
3. abnormality_eval: 以客观、中立的态度，评估你对该版面的解读是否存在异常，异常包括但不限于：OTCL特征提取不合理、解读逻辑不通顺、手写内容无法理解、版面字体不清晰等。给出异常程度（低/中/高）和异常原因。不超过50字。
如果该版面存在手写内容，请额外包含以下维度：
4. format_evaluation: 评估手写内容的书写规范和版面饱满度。不超过30字。
5. confidence: 手写内容的识别置信度，类型是小数，范围0到1，0表示完全不确定，1表示非常确定。
请你以JSON格式输出，不要输出```json```代码段：
"""

# M版面分析提示词
# 从裂变视角，分析该版面所包含的各个D版面在什么位置、起什么作用、对M有何贡献以及与其他D在位置/内容上的相互关系。不超过300字。
M_ANALYSIS_PROMPT = """请你从以下维度对该版面进行解读：
1. context_analysis: 从裂变视角，分析该版面所包含的各个D版面在什么位置、起什么作用、对M有何贡献以及与其他D在位置/内容上的相互关系。不超过300字。
2. deficiency_detection: 从聚变视角，基于该版面所包含的各个D版面信息，挖掘该小组在知识问题/技能错误/能力习惯缺陷三个维度存在的不足。不超过300字。
请你以JSON格式输出，不要输出```json```代码段。
"""

# T版面分析提示词（不含T0版面）
# 从裂变视角，分析该版面所包含的各个M版面或D版面在什么位置、起什么作用、对T有何贡献以及与其他M在位置/内容上的相互关系。不超过300字。
T_ANALYSIS_PROMPT = """请你从以下维度对该版面进行解读：
1. context_analysis: 从裂变视角，分析该版面所包含的各个M版面或D版面在什么位置、起什么作用、对T有何贡献以及与其他M在位置/内容上的相互关系。不超过300字。
2. deficiency_detection: 从聚变视角，基于该版面所包含的各个M版面或D版面信息，挖掘该小组在知识问题/技能错误/能力习惯缺陷三个维度存在的不足。不超过300字。
请你以JSON格式输出，不要输出```json```代码段。
"""

# T0版面分析提示词
T0_ANALYSIS_PROMPT = """请对这张图片进行专业多层次分析解读，包含以下要点：
1. 版面结构：从裂变视角，分析该图片所包含的各个版面在什么位置、起什么作用、对该图片有何贡献以及与其他版面在位置/内容上的相互关系。注意，版面所属的层次并不代表它在图片上的实际位置，而是代表一种认知上的逻辑关系，以下是各层版面的含义，供你理解：
    - 底层（Down，D）版面：最小的认知单元，比如一道题目、一个知识点。能够提取核心认知颗粒，作为认知活动的基本构件；
    - 中间层（Middle，M）版面：一种中间层次的认知组织形态，反映多个D版面的逻辑关联，例如一节课程或一个知识模块的整体结构；
    - 顶层（Top，T）版面：顶层结构，由多个D类和M类版面聚合而成，体现全局认知组织，比如一门课程的整体知识体系或大型协作任务的全局结构。
2. 多层内容依次解读：
    - 底图层：图片本身的整体感知性理解。
    - 印刷层：教材/试题等印刷，具体印了哪些文字；
    - 涂鸦层：批注符号、圈点、下划线等标记（涂鸦勾画等其实是思考过程的体现，也很重要，不可以忽视这层！），若有涂鸦痕迹，则指出具体涂鸦了什么；
    - 手写层：尽可能囊括**所有**手写内容，务必涉及具体写了什么，如果辨认不清或识别出的内容有错别字、不通顺、不合理，请结合上下文信息补全或修正。
3. 层间关联：分析各层次间的对应关系，特别关注手写、涂鸦、印刷内容的对应及关联关系。
4. 三维缺陷：从聚变视角，基于该图片所包含的各个版面信息以及上述分析，挖掘该小组在知识问题/技能错误/能力习惯缺陷三个维度存在的不足。
5. 另外注意事项：
    - 给你的DMT分析上下文材料非常详尽完整，你需要尽可能多地保留不同维度的信息，只是缩减精炼篇幅，而例如手写内容识别甚至可以全都留下，让这些分析结果尽可能在之后更多地用上，这很重要，请你格外注意！
    - 给你的上下文参考材料里或许存在类似“M1”或“D1”这样的版面编号，你的回答中一定不要出现这些编号，最好用对应的“M级区域描述”或“D级区域描述”来指代相应的区域！
    - 对于图片的标题（一般在版面最上方居中的位置，且黑色加粗），你一定要在最开头就把它识别出来并进行陈述！如果识别不出来或者不清楚，请你参考上下文信息。（如果有组号，你也要在最开头提及，格式为“G组号”，例如“G1”）
    - 对于手写识别置信度低于0.9或异常程度标注不低的版面信息，你在列举手写内容时应当明确指出，在三维缺陷时不应参考或引用这部分内容。
    - 涂鸦和手写层虽然都是书写，也有关联性，但你描述时需要分开（格式上分开，内容上要找关联），涂鸦层比较随意，偏向思考过程；手写层比较正式，偏向作答过程。如果没有涂鸦笔迹，也需要简单说明一下。
    - 你需要说明这张图片最可能是针对哪些对象的，如什么阶段（小学初中高中大学等）、什么年级等等。

请直接给出自然、完整的图片描述，整体大要求是需要保留更多篇幅的图片主体具体内容以及具体理解分析（实实在在的），辅以一些偏虚的说明和描述，你可以形象地理解为70%立足、20%面向、
10%放眼，这样的篇幅安排是合理的、有实际操作和分析价值的。使用简体中文，控制在不超过2000字为佳。
"""

# 基础提示词模板
BASE_PROMPTS = {
    'D': "这是{content}上的D（Down）版面，属于DMT(Down-Middle-Top)结构的底层版面。",
    'M': "这是{content}上的M（Middle）版面，属于DMT(Down-Middle-Top)结构的中间层版面。\n",
    'T': "这是{content}上的T（Top）版面，属于DMT(Down-Middle-Top)结构的顶层版面。\n",
    'T0': "这是{content}，它包含以下版面：\n"
}

# 重试提示词后缀
RETRY_SUFFIX = "\n请确保返回有效的JSON格式，不要包含任何```json```标记或额外的文本。"

# 版面类型提示词
PANEL_TYPE_PROMPTS = {
    'preset_content': "该版面的预置（印刷）内容是{preset_content}\n", # 用于D版面分析
    'handwritten_area': "该版面属于填写区\n", # 用于D版面分析
    'contains_d_panels': "该版面包含上述这些D版面\n", # 用于M版面分析
    'contains_m_panels': "该版面包含上述这些M版面或D版面\n", # 用于T版面分析（不含T0版面）
    'contains_t_panels': "该版面包含上述这些T版面和D版面\n", # 用于T0版面分析
}

# 多图输入时各图片描述模板(用于T/M版面分析)
IMAGE_DESCRIPTION_TEMPLATES = {
    'D_panel': "这张图片是“{panel_id}”版面，属于D（Down）版面\n具体内容：{content_text}\nOTCL分析：{otcl_analysis}\n",
    'D_panel_with_evaluation': "这张图片是“{panel_id}”版面，属于D（Down）版面\n具体内容：{content_text}\nOTCL分析：{otcl_analysis}\n书写规范性：{format_evaluation}\n识别置信度：{confidence}\n",
    'M_panel': "这张图片是“{panel_id}”版面，属于M（Middle）版面\n裂变分析：{context_analysis}\n聚变分析：{deficiency_detection}\n",
    "T_panel": "这张图片是“{panel_id}”版面，属于T（Top）版面，它所包含的版面信息如下：{contained_panels_info}\n"
}

def get_base_prompt(panel_type, content):
    """
    获取基础提示词
    
    Args:
        panel_type: 版面类型 ('D', 'M', 'T')
        content: 预置内容
        
    Returns:
        str: 格式化后的基础提示词
    """
    return BASE_PROMPTS[panel_type].format(content=content)

def get_retry_prompt(original_prompt):
    """
    获取重试提示词
    
    Args:
        original_prompt: 原始提示词
        
    Returns:
        str: 添加了重试后缀的提示词
    """
    return original_prompt + RETRY_SUFFIX

def get_panel_type_prompt(prompt_type, **kwargs):
    """
    获取版面类型提示词
    
    Args:
        prompt_type: 提示词类型
        **kwargs: 格式化参数
        
    Returns:
        str: 格式化后的提示词
    """
    template = PANEL_TYPE_PROMPTS.get(prompt_type, "")
    return template.format(**kwargs)

def get_image_description(template_type, **kwargs):
    """
    获取图片描述模板
    
    Args:
        template_type: 模板类型
        **kwargs: 格式化参数
        
    Returns:
        str: 格式化后的图片描述
    """
    template = IMAGE_DESCRIPTION_TEMPLATES.get(template_type, "")
    return template.format(**kwargs)

# 提示词配置字典，方便批量获取
PROMPTS_CONFIG = {
    'D': {
        'handwritten': D_HANDWRITTEN_PROMPT,
        'printed': D_PRINTED_PROMPT,
        'group': D_GROUP_PROMPT,
        'analysis': D_ANALYSIS_PROMPT
    },
    'M': {
        'analysis': M_ANALYSIS_PROMPT
    },
    'T': {
        'analysis': T_ANALYSIS_PROMPT
    },
    'T0': {
        'analysis': T0_ANALYSIS_PROMPT
    }
}

def get_prompt(panel_type, prompt_type):
    """
    获取指定的提示词
    
    Args:
        panel_type: 版面类型 ('D', 'M', 'T')
        prompt_type: 提示词类型
        
    Returns:
        str: 对应的提示词
    """
    return PROMPTS_CONFIG.get(panel_type, {}).get(prompt_type, "")
