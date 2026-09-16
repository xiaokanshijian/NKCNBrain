from django.utils import timezone

from app_chat.global_state import GLOBAL_STATE
from app_chat.config.config_manager import config_manager

from app_chat.utils import get_base64_size, add_cardImage, resolve_prompt_storage_key

from llm_langchain import global_var
from llm_langchain import normal_qa_new
from llm_langchain import util

import os
import re


def calculate_rot_score_algorithmic(text, rag_docs_text="", history_text="", cards_text=""):
    """
    确定性算法计算腐烂度评分（权重60%）
    注意：腐烂度评分越低越好！
    返回0-5分，0分最好（无腐烂），5分最差（严重腐烂）
    """
    score = 0.0  # 初始无腐烂

    # 计算总上下文长度
    total_context_length = len(rag_docs_text) + len(history_text) + len(cards_text)
    print(
        f"[腐烂度-上下文分析] 问答文本:{len(text)}字, RAG:{len(rag_docs_text)}字, 历史:{len(history_text)}字, 卡片:{len(cards_text)}字, 总计:{total_context_length}字")

    # 0. 基础分：根据总上下文长度给一个基础分（避免总是0分）
    # 0-2000字: 0分
    # 2000-5000字: 0-0.3分
    # 5000-10000字: 0.3-0.8分
    if total_context_length > 2000:
        if total_context_length <= 5000:
            base_score = 0.3 * (total_context_length - 2000) / 3000
        elif total_context_length <= 10000:
            base_score = 0.3 + 0.5 * (total_context_length - 5000) / 5000
        else:
            base_score = 0.8
        score += base_score
        print(f"[腐烂度-基础分] 上下文{total_context_length}字，基础分{base_score:.2f}分")

    # 1. 长度因子：上下文长度 > 10000字时开始计分（降低阈值）
    # 10000-15000字: +0.0-0.5分
    # 15000-20000字: +0.5-1.0分
    # 20000字以上: +1.0-2.5分（最高2.5分）
    if total_context_length > 10000:
        if total_context_length <= 15000:
            excess_length = total_context_length - 10000
            length_score = 0.5 * (excess_length / 5000)
        elif total_context_length <= 20000:
            excess_length = total_context_length - 15000
            length_score = 0.5 + 0.5 * (excess_length / 5000)
        else:
            excess_length = total_context_length - 20000
            length_score = 1.0 + min(1.5, 1.5 * (excess_length / 10000))

        score += length_score
        print(f"[腐烂度-长度因子] 总上下文{total_context_length}字，增加{length_score:.2f}分")

    # 2. 重复因子：基于随机抽取文本段的相似度检测
    all_text = text + rag_docs_text + history_text + cards_text

    import re
    # 按标点符号分句（用于后续模糊因子）
    sentences = re.split(r'[。！？；\n.!?;]+', all_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    # 从上下文中随机抽取2段内容进行相似度比较
    if len(all_text) > 200:  # 至少200字才进行抽取
        import random

        # 确定抽取长度（100字或100单词）
        words = all_text.split()
        is_english = len(words) > len(all_text) / 10

        if is_english:
            # 英文：100单词
            sample_size = min(100, len(words) // 4)  # 最多取总词数的1/4
        else:
            # 中文：100字
            sample_size = min(100, len(all_text) // 4)  # 最多取总字数的1/4

        # 随机抽取第一段
        if is_english:
            max_start1 = max(0, len(words) - sample_size - 1)
            if max_start1 > 0:
                start1 = random.randint(0, max_start1)
                segment1_words = words[start1:start1 + sample_size]
                segment1 = ' '.join(segment1_words)
            else:
                segment1 = ' '.join(words[:sample_size])
        else:
            max_start1 = max(0, len(all_text) - sample_size - 1)
            if max_start1 > 0:
                start1 = random.randint(0, max_start1)
                segment1 = all_text[start1:start1 + sample_size]
            else:
                segment1 = all_text[:sample_size]

        # 随机抽取第二段（确保不重叠）
        if is_english:
            if max_start1 > sample_size:
                # 确保第二段不与第一段重叠
                possible_starts = list(range(0, start1 - sample_size)) + list(
                    range(start1 + sample_size, max_start1 + 1))
                if possible_starts:
                    start2 = random.choice(possible_starts)
                    segment2_words = words[start2:start2 + sample_size]
                    segment2 = ' '.join(segment2_words)
                else:
                    segment2 = segment1  # 文本太短，无法避免重叠
            else:
                segment2 = segment1  # 文本太短
        else:
            if max_start1 > sample_size:
                possible_starts = list(range(0, start1 - sample_size)) + list(
                    range(start1 + sample_size, max_start1 + 1))
                if possible_starts:
                    start2 = random.choice(possible_starts)
                    segment2 = all_text[start2:start2 + sample_size]
                else:
                    segment2 = segment1
            else:
                segment2 = segment1

        # 计算两段文本的相似度（改进方法：词级别Jaccard + 词频相似度）
        if segment1 != segment2:
            import jieba
            from collections import Counter

            # 方法1: 词级别的Jaccard相似度
            if is_english:
                words1 = set(w.lower() for w in segment1.split() if w.strip())
                words2 = set(w.lower() for w in segment2.split() if w.strip())
            else:
                # 中文分词
                try:
                    words1 = set(jieba.cut(segment1))
                    words2 = set(jieba.cut(segment2))
                    # 移除单字符和空白
                    words1 = {w for w in words1 if len(w.strip()) > 1}
                    words2 = {w for w in words2 if len(w.strip()) > 1}
                except:
                    # 降级到字符级别
                    words1 = set(segment1.lower())
                    words2 = set(segment2.lower())

            intersection = len(words1 & words2)
            union = len(words1 | words2)
            jaccard_sim = intersection / union if union > 0 else 0

            # 方法2: 基于词频的余弦相似度
            if is_english:
                words_list1 = [w.lower() for w in segment1.split() if w.strip()]
                words_list2 = [w.lower() for w in segment2.split() if w.strip()]
            else:
                try:
                    words_list1 = list(jieba.cut(segment1))
                    words_list2 = list(jieba.cut(segment2))
                    words_list1 = [w for w in words_list1 if len(w.strip()) > 1]
                    words_list2 = [w for w in words_list2 if len(w.strip()) > 1]
                except:
                    words_list1 = list(segment1.lower())
                    words_list2 = list(segment2.lower())

            # 计算词频
            freq1 = Counter(words_list1)
            freq2 = Counter(words_list2)

            # 计算共同词的频率相似度
            common_words = set(freq1.keys()) & set(freq2.keys())
            if common_words and words_list1 and words_list2:
                freq_similarity = sum(min(freq1[w], freq2[w]) for w in common_words) / max(len(words_list1),
                                                                                           len(words_list2))
            else:
                freq_similarity = 0

            # 综合相似度：Jaccard 70% + 频率相似度 30%
            similarity = jaccard_sim * 0.7 + freq_similarity * 0.3

            print(f"[腐烂度-重复因子] Jaccard={jaccard_sim:.2%}, 频率相似度={freq_similarity:.2%}, 综合={similarity:.2%}")

            # 基于相似度评分（U型曲线，居中最优）
            # 最优相似度: 30-60% (内容相关但不重复)
            #
            # 相似度过低（逻辑跳跃）- 增强惩罚：
            # < 10%: +0.8分 (极度跳跃，内容完全无关)
            # 10-15%: +0.5-0.8分 (严重跳跃)
            # 15-20%: +0.3-0.5分
            # 20-30%: +0.1-0.3分
            #
            # 最优区间：
            # 30-60%: 0分 (内容连贯且不重复)
            #
            # 相似度过高（重复冗余）：
            # 60-70%: +0-0.5分
            # 70-85%: +0.5-1.2分
            # > 85%: +1.2-2.0分 (严重重复)

            repeat_score = 0.0

            # 相似度过低（增强惩罚力度）
            if similarity < 0.30:
                if similarity < 0.10:
                    repeat_score = 0.8  # 极度跳跃
                elif similarity < 0.15:
                    repeat_score = 0.5 + 0.3 * (0.15 - similarity) / 0.05
                elif similarity < 0.20:
                    repeat_score = 0.3 + 0.2 * (0.20 - similarity) / 0.05
                else:
                    repeat_score = 0.1 + 0.2 * (0.30 - similarity) / 0.10
                print(f"[腐烂度-重复因子] 随机抽样相似度{similarity:.2%}（过低，逻辑跳跃），增加{repeat_score:.2f}分")

            # 相似度过高（影响较大）
            elif similarity > 0.60:
                if similarity < 0.70:
                    repeat_score = 0.5 * (similarity - 0.60) / 0.10
                elif similarity < 0.85:
                    repeat_score = 0.5 + 0.7 * (similarity - 0.70) / 0.15
                else:
                    repeat_score = 1.2 + min(0.8, 0.8 * (similarity - 0.85) / 0.15)
                print(f"[腐烂度-重复因子] 随机抽样相似度{similarity:.2%}（过高，内容重复），增加{repeat_score:.2f}分")

            # 最优区间
            else:
                print(f"[腐烂度-重复因子] 随机抽样相似度{similarity:.2%}（最优区间），不加分")

            score += repeat_score
        else:
            print(f"[腐烂度-重复因子] 文本过短，两段重叠，跳过检测")
    else:
        print(f"[腐烂度-重复因子] 文本长度不足({len(all_text)}字)，跳过重复检测")

    # 3. 模糊因子：使用渐进式评分（更敏感）
    vague_words = ['可能', '也许', '大概', '似乎', '好像', '一些', '某些', '或许', '大约', '左右',
                   '基本', '大致', '差不多', '应该', '可以说', '在一定程度上', '某种意义上']
    vague_count = sum(all_text.count(word) for word in vague_words)

    # 基于句子数量计算模糊词密度
    if len(sentences) > 0:
        vague_density = vague_count / len(sentences)  # 平均每句话的模糊词数量

        # 渐进式评分：
        # < 0.3: 0分 (清晰表达，平均每句不到0.3个模糊词)
        # 0.3-0.5: 0-0.2分
        # 0.5-1.0: 0.2-0.5分
        # > 1.0: 0.5-1.0分 (过于模糊，最高1.0分)
        if vague_density >= 0.3:
            if vague_density < 0.5:
                vague_score = 0.2 * (vague_density - 0.3) / 0.2
            elif vague_density < 1.0:
                vague_score = 0.2 + 0.3 * (vague_density - 0.5) / 0.5
            else:
                vague_score = 0.5 + min(0.5, 0.5 * (vague_density - 1.0) / 0.5)

            score += vague_score
            print(f"[腐烂度-模糊因子] 模糊词密度{vague_density:.2f}个/句，增加{vague_score:.2f}分")
    else:
        print(f"[腐烂度-模糊因子] 无有效句子，跳过模糊检测")

    # 确保评分在0-5范围内
    score = max(0.0, min(5.0, score))
    print(f"[腐烂度-确定性算法] 最终得分: {score:.2f}/5.0 (长度+重复+模糊)")

    return round(score, 1)



system_prompt_claude = """<人性化思考协议>
<多模态感知>
以人类般的多维感知能力处理信息、感知情境、解决问题：
1. 视觉场景模拟建立感知
- 构建清晰的心理图像
- 想象具体视觉细节
- 分析空间关系布局
- 识别能可视化的模式和结构

2. 听觉场景模拟建立感知
- 模拟声音和语调变化
- 感知语言节奏韵律
- 注意声音的情感特征

3. 触觉场景模拟建立感知
- 模拟解决问题的环境具象并密切感受
- 想象物理交互变化过程
- 感知动作和空间关系

4. 情感感知
- 识别情绪基调
- 揣摩发问动机
- 分析心理影响
- 把握情感连接

5. 整体感知整合
- 以当事人视角，以好奇心驱动探究
- 整合多感官信息
- 建立丰富的心理表征
- 形成多维度理解网络

<思维发展阶段>
按照阶段使用不同思维推进思考：
1. 自然意识流状态
- 保持思维自由开放地流动
- 允许梦境般的幻想状态
- 注意自发的联想
- 记录初始整体印象

2. 多模态感知激活
- 运用多模态感知
- 构建丰富场景
- 整合感知信息，形成丰富表征

3. 直觉系统运作
- 此阶段开始不允许再停留于类似做梦的幻想状态
- 捕捉首要印象
- 识别潜在模式
- 产生创意火花，形成初步方向

4. 推理系统主导
- 严密的逻辑分析
- 随时验证和评估
- 以树分支、图连接的方式推理思考
- 不断提出新的假设并记得验证
- 从错误的假设或树图思考路径中吸取经验

5. 深度整合
- 综合多维观点
- 对不同思考提炼核心见解、建立深层联系
- 思维活跃，不断构建完善论证

<核心思考步骤细节>
1. 初始解析
- 重述问题中关键信息以达到理解
- 考虑背景知识体系
- 分析询问动机
- 识别已知未知

2. 深入分析
- 分解核心要素
- 识别出隐含的需求
- 考虑不同级别的限制条件
- 设想理想结果

3. 多角度探索
- 考虑多种解释
- 对一个问题或概念可能有多种认知，应该揣摩人类更可能的意愿，排除歧义
- 激活灵感，不断探索更优方案

4. 推理验证
- 持续检验假设
- 寻找证据支持
- 考虑反例
- 验证逻辑一致

5. 知识整合
- 组织相关信息
- 建立关系网络
- 提炼核心，总结关键发现

<质量控制>
1. 系统化验证
- 对较复杂问题，多次重复且独立地验证每个步骤
- 以发现漏洞为目标
- 问题最终解决后，完整检查思考过程
- 核对所有已知条件
- 确保逻辑严谨
- 考虑边界情况

2. 错误防范
- 面对任何问题，在任何阶段，都不要过于自信，即使看起来可能很简单明确
- 避免过早下结论
- 考虑替代方案

3. 评估标准
- 分析完整性
- 逻辑严密性
- 证据充分性
- 实际可用性

<表达特征>
1. 自然语言风格
- 流畅的意识流表达
- 生动的场景构建和多感知描述
- 自然舒展地表达展现完整思维过程

2. 思维深度
- 逐层深入分析
- 展示认知发展
- 揭示思维转折，凸显关键洞察

<重要规则>
- 思维过程必须全面且深入
- 保持自然的思维流动
- 善用模拟多模态情境感知理解
- 遵循自然意识→感知→直觉→推理→深度思考验证的过程
- 输出的所有思考过程必须在三反引号代码块中，标记为"thinking"
- 如果涉及逻辑推理，思考结束要完整检查，标记为"checking"，此时应特别注意，一定不可遗漏任何已知条件，以找漏洞为目标，此时应该更倾向于说明矛盾点，符合点一笔带过即可；同时注意是否失误地排除了正确答案
- 如果找出漏洞，需重新"thinking"解决问题，应着重对之前产生漏洞的相关思考吸取教训，且再次"checking"时，应该更加仔细且多次
- 如果思考和检查超过2轮就请停下来，承认自己无法解决并告知人类原因
- 避免在思考和检查过程输出中使用三反引号，这会导致格式解析出错
- 将思考过程总结为一个思考成果报告，直接解决人类的问题并作适当解释
- 以人类使用或请求的语言来回应
</人性化思考框架>
"""


def get_possible_cardImgs_base64_byIds(username, CardIndexList):
    # 初始化一个空列表用于存储图片的base64编码
    base64_images = []

    # 遍历每个卡片ID
    for i, id_str in enumerate(CardIndexList):
        # 检查三种可能的图片扩展名
        for file_extension in ['.jpg', '.jpeg', '.png']:
            image_dir = f'./received_dir/user_raw_file/{username}/cardImage'
            file_name = f'{id_str}{file_extension}'

            # 确保目录存在
            os.makedirs(image_dir, exist_ok=True)
            file_path = os.path.join(image_dir, file_name)

            # 检查文件是否存在
            if os.path.exists(file_path):
                # 如果文件存在，将其编码为base64
                base64_image = util.encode_image(file_path)
                base64_images.append(base64_image)
                # 找到图片后就不需要继续检查其他扩展名
                break

    return base64_images


def compose_message_with_summary(data, username, message):
    # 不懂为啥不能在此导入...
    from app_chat.models import BgCard
    from app_chat.bgcGenerate import summarize_scene
    sumContent = ""
    
    try:
        mysql_card = BgCard.objects.get(username=username, status="3")
        sumContent = mysql_card.content
    except BgCard.DoesNotExist:
        realName = data["realName"]
        userbookName = data["userbookName"]
        sceneName = data["sceneName"]
        bgc = summarize_scene(realName, sceneName)
        current_datetime = timezone.now()
        bg_card = BgCard(
                username=realName,
                name=sceneName+"场景背景摘要",
                detail=sceneName+"场景背景摘要",
                # content=bgc,
                datetime=current_datetime,
                status="2"
            )
        bg_card.save()
        sumContent = bgc
    message = "背景知识摘要：\n" + sumContent + "\n用户的请求或提问：\n" + message
    return message


def construct_data(data):
    from app_chat.views import chat_history_used, chat_history
    print('[INFO] 正在构造数据...')
    
    username = data["username"]
    originRealName = data.get("originRealName", "")
    if originRealName != "":
        name2RealUse = originRealName
    else:
        name2RealUse = username

    prompt_mem_key = resolve_prompt_storage_key(username, originRealName)
    # 可选显式覆盖（前端一般不传；自动化勿再覆盖到 rag 组键）
    _prompt_override = (data.get("promptStorageKey") or data.get("prompt_mem_key") or "").strip()
    if _prompt_override:
        prompt_mem_key = _prompt_override
    
    seed = int(data['seed'])
    message = data["message"]
    model_id = data["model_id"]
    summary = data["summary"]
    fileNameList = data["filenamelist"]
    leftSelectList = data["leftSelectList"]
    rightSelectList = data["rightSelectList"]
    isHistoryUsed = data["isHistoryUsed"]
    isSummaryUsed = data["isSummaryUsed"]
    rounds = int(data["rounds"])
    model_states = data["modelStates"]
    
    print('[DEBUG:construct_data] 构造数据:', data)

    history = False
    if isHistoryUsed == "true" \
        and not GLOBAL_STATE.conversation_manager.is_empty():
        history = True
    # if isHistoryUsed == "true" and chat_history_used != {}:
    #     history = True
    if isSummaryUsed == "true":
        message = compose_message_with_summary(data, username, message)
    
    # 根据模型id，获取模型名称
    model_name = config_manager.get_model_name_by_id(model_id)

    ## 处理文件列表和选择列表
    file_list = fileNameList.split(',') if fileNameList else []
    print('[app_chat chat_send]:', leftSelectList, rightSelectList)
    left_select_list = [int(item) for item in leftSelectList.split(',')] if leftSelectList else []
    right_select_list = [int(item) for item in rightSelectList.split(',')] if rightSelectList else []
    print('file_list and selection info:')
    print(file_list, left_select_list, right_select_list)

    # NK2026 梯子图场景：勾选「××组梯子图填写」或附带 target_file 时注入 Gxx.md
    try:
        from app_chat.group_twin_gxx import (
            prepend_nk2026_chuchengjia_context_if_needed,
            prepend_nk2026_gxx_context_if_needed,
        )

        _scene_name = data.get("sceneName") or data.get("scene_name") or ""
        _tf = (data.get("target_file") or data.get("targetFile") or "").strip()
        message = prepend_nk2026_gxx_context_if_needed(
            username, _scene_name, file_list, message, target_file=_tf or None
        )
        message = prepend_nk2026_chuchengjia_context_if_needed(
            username, _scene_name, message
        )
    except Exception as _gxx_e:
        print(f"[construct_data NK2026 Gxx/正本清源 注入] {_gxx_e}")

    if seed == 2:
        # # swap topic and topic-question prompt
        # topic_question_prompt = global_var.store_memory[username]["prompt"]["LUI2"]["topic_question"]
        # global_var.store_memory[username]["prompt"]["LUI2"]["topic_question"] = \
        #     global_var.store_memory[username]["prompt"]["LUI2"]["qa"]
        # global_var.store_memory[username]["prompt"]["LUI2"]["qa"] = topic_question_prompt
        # swap topic and topic-question prompt（须与场景 prompt 存储键一致，避免组本协作者互相覆盖）
        topic_question_prompt = global_var.store_memory[prompt_mem_key]["prompt"]["LUI2"]["topic_question"]
        global_var.store_memory[prompt_mem_key]["prompt"]["LUI2"]["topic_question"] = \
            global_var.store_memory[prompt_mem_key]["prompt"]["LUI2"]["qa"]
        global_var.store_memory[prompt_mem_key]["prompt"]["LUI2"]["qa"] = topic_question_prompt

    # 如果多轮对话超过n轮，移除最早的一轮
    # if len(chat_history_used[name2RealUse]) > rounds:
    #     chat_history_used[name2RealUse].pop(0)
    # if len(chat_history[name2RealUse]) > rounds:
    #     chat_history[name2RealUse].pop(0)

    # 定义需要检查大小的模型ID列表
    SIZE_CHECK_MODELS = ["1006", "1011"]
    
    info_list = []
    MAX_SIZE = 5 * 1024 * 1024  # 5MB in bytes
    current_total_size = 0
    
    if 'choosedCardIdList' in data and data['choosedCardIdList']:
        # 如果勾选了卡片问答，存在choosedCardIdList，拆分choosedCardIdList字符串为列表
        CardIndexList = data['choosedCardIdList'].split(',')
        base64_images = get_possible_cardImgs_base64_byIds(username, CardIndexList)
        
        for base64_image in base64_images:
            # 仅在特定模型下检查图片大小
            if model_id in SIZE_CHECK_MODELS:
                image_size = get_base64_size(base64_image)
                # 检查添加新图片后是否会超过限制
                if current_total_size + image_size > MAX_SIZE:
                    print(f"Skipping image size {image_size} as it would exceed the 5MB limit")
                    continue
                # 更新已使用的总大小
                current_total_size += image_size
            
            # 因为gemini好像不接受jpg，所以默认试试png
            image_url = f"data:image/png;base64,{base64_image}"
            add_cardImage(info_list, image_url)

    # 构造response数据
    response = {}
    response['seed'] = seed
    
    # 从模型管理器中获取模型超参数，并将其转换为字典格式
    response["nowParams"] = config_manager.get_model_config(model_name).get_hyper_para().to_dict()
    
    print('[Debug:construct_data] cur_modelID = ',  model_id)

    # 添加RAG搜索用时（如果有文档）
    from app_chat.views import chat_with_files_params, last_segments
    rag_docs_text = ""
    rag_sample_docs = []
    if name2RealUse in chat_with_files_params and 'rag_search_time' in chat_with_files_params[name2RealUse]:
        response['rag_search_time'] = chat_with_files_params[name2RealUse]['rag_search_time']
        print(f"[DEBUG] construct_data - 从chat_with_files_params获取RAG时间: {response['rag_search_time']}s")

        # 获取RAG文档内容用于腐烂度计算
        if name2RealUse in last_segments and last_segments[name2RealUse]:
            rag_docs_list = last_segments[name2RealUse]

            # 处理最外层可能的嵌套（有时是[[Document, ...]]格式）
            if len(rag_docs_list) > 0 and isinstance(rag_docs_list[0], list):
                rag_docs_list = rag_docs_list[0]

            print(f"[DEBUG]xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx construct_data - RAG文档列表长度: {len(rag_docs_list)}")

            # 处理嵌套列表结构，确保每个元素都是字符串
            rag_docs_text_list = []
            for item in rag_docs_list:
                if isinstance(item, list):
                    # 如果是列表，递归处理
                    for sub_item in item:
                        if isinstance(sub_item, str):
                            rag_docs_text_list.append(sub_item)
                        elif hasattr(sub_item, 'page_content'):
                            # 如果是Document对象，提取page_content
                            rag_docs_text_list.append(sub_item.page_content)
                elif isinstance(item, str):
                    # 如果是字符串，直接添加
                    rag_docs_text_list.append(item)
                elif hasattr(item, 'page_content'):
                    # 如果是Document对象，提取page_content
                    rag_docs_text_list.append(item.page_content)

            rag_docs_text = "\n".join(rag_docs_text_list)
            print(f"[DEBUG] construct_data - RAG文档总字数: {len(rag_docs_text)}")

            # 提取第1个、最后1个、中间随机1个文档用于小模型评估
            # 首先扁平化rag_docs_list，确保所有元素都是字符串
            flat_rag_docs = []
            for item in rag_docs_list:
                if isinstance(item, list):
                    # 处理嵌套列表
                    for sub_item in item:
                        if isinstance(sub_item, str):
                            flat_rag_docs.append(sub_item)
                        elif hasattr(sub_item, 'page_content'):
                            flat_rag_docs.append(sub_item.page_content)
                elif isinstance(item, str):
                    flat_rag_docs.append(item)
                elif hasattr(item, 'page_content'):
                    # 如果是Document对象，提取page_content
                    flat_rag_docs.append(item.page_content)

            print(f"[DEBUG] construct_data - 扁平化后文档数量: {len(flat_rag_docs)}")

            if len(flat_rag_docs) >= 3:
                import random
                middle_idx = random.randint(1, len(flat_rag_docs) - 2)
                rag_sample_docs_raw = [
                    flat_rag_docs[0],
                    flat_rag_docs[middle_idx],
                    flat_rag_docs[-1]
                ]
            else:
                rag_sample_docs_raw = flat_rag_docs

            # 每段文档限制为100字（用于小模型评估）
            rag_sample_docs = []
            for doc in rag_sample_docs_raw:
                # 检测是否主要是英文（空格分词后单词数量接近字符数的1/5）
                words = doc.split()
                is_english = len(words) > len(doc) / 10

                if is_english:
                    # 英文：取前60个单词（优化：减少长度）
                    if len(words) > 60:
                        doc = ' '.join(words[:60]) + '...'
                else:
                    # 中文：取前60个字符（优化：减少长度）
                    if len(doc) > 60:
                        doc = doc[:60] + '...'

                rag_sample_docs.append(doc)

            # 将样本文档拼接
            rag_sample_text = "\n---\n".join(rag_sample_docs)
            response['rag_sample_text'] = rag_sample_text
            print(f"[DEBUG] construct_data - RAG样本文档字数: {len(rag_sample_text)} (每段限制60字/词)")

            # 获取文档置信度评分（从文档metadata中）
            doc_confidence_scores = []
            user_docs = global_var.get_user_split(name2RealUse, file_list[0] if file_list else None)
            if user_docs:
                for doc in user_docs:
                    if 'confidence_score' in doc.metadata:
                        doc_confidence_scores.append(doc.metadata['confidence_score'])

            if doc_confidence_scores:
                avg_doc_confidence = sum(doc_confidence_scores) / len(doc_confidence_scores)
                response['doc_confidence_score'] = round(avg_doc_confidence, 1)
                print(f"[DEBUG] construct_data - 文档平均置信度: {response['doc_confidence_score']}")
            else:
                response['doc_confidence_score'] = 0
                print(f"[DEBUG] construct_data - 文档置信度未评估或为0")
    else:
        response['rag_search_time'] = 0
        response['rag_sample_text'] = ""
        print(
            f"[DEBUG] construct_data - RAG时间设为0, name2RealUse在chat_with_files_params中: {name2RealUse in chat_with_files_params}")
        if name2RealUse in chat_with_files_params:
            print(f"[DEBUG] construct_data - chat_with_files_params[{name2RealUse}]的键: {list(chat_with_files_params[name2RealUse].keys())}")

    # 计算腐烂度（确定性算法部分，权重60%）
    history_text = ""
    cards_text = ""
    if history:
        # 获取当前用户和模型的历史记录
        try:
            question_list = GLOBAL_STATE.conversation_manager.get_question_list(username, model_name)
            response_list = GLOBAL_STATE.conversation_manager.get_response_list(username, model_name)

            # 合并问题和回答
            history_messages = []
            for i in range(min(len(question_list), len(response_list))):
                history_messages.append(f"Q: {question_list[i]}")
                history_messages.append(f"A: {response_list[i]}")

            history_text = "\n".join(history_messages)

            # 提取最近3轮历史记录样本用于小模型评估
            if len(history_messages) > 0:
                # 取最近3轮对话（每轮包含Q和A，所以是6条消息）
                recent_count = min(6, len(history_messages))
                history_sample_messages = history_messages[-recent_count:]

                # 精简历史记录：问题取最后50字，回答取前100字
                processed_messages = []
                for msg in history_sample_messages:
                    if msg.startswith("Q: "):
                        question = msg[3:]  # 去掉"Q: "前缀

                        # 如果问题超过50字，优先找最后一个问号并向前提取最多50字
                        if len(question) > 50:
                            last_question_mark = question.rfind('?')
                            if last_question_mark == -1:
                                last_question_mark = question.rfind('？')

                            if last_question_mark != -1:
                                # 找到问号，从问号位置向前提取最多50字
                                start_pos = max(0, last_question_mark - 49)
                                question = question[start_pos:last_question_mark + 1]
                                if start_pos > 0:
                                    question = "..." + question
                            else:
                                # 没有问号，直接取最后50字
                                question = "..." + question[-50:]

                        processed_messages.append(f"Q: {question}")

                    elif msg.startswith("A: "):
                        answer = msg[3:]  # 去掉"A: "前缀

                        # 如果回答超过100字，只保留前100字
                        if len(answer) > 100:
                            answer = answer[:100] + "..."

                        processed_messages.append(f"A: {answer}")

                history_sample_text = "\n".join(processed_messages)
                response['history_sample_text'] = history_sample_text
                print(f"[DEBUG] construct_data - 历史对话样本字数: {len(history_sample_text)} (已精简)")
            else:
                response['history_sample_text'] = ""
        except Exception as e:
            print(f"[WARNING] 获取历史记录失败: {e}")
            history_text = ""
            response['history_sample_text'] = ""
    else:
        response['history_sample_text'] = ""

    # 计算上下文腐烂度（确定性算法）
    rot_score_algorithmic = calculate_rot_score_algorithmic(message, rag_docs_text, history_text, cards_text)
    response['rot_score_algorithmic'] = rot_score_algorithmic

    response['msg'] = 'success'
    response['error_num'] = 0

    system_prompt = """You are an advanced AI assistant providing accurate and professional responses across 
                technical, research, content creation, and general knowledge domains. 
    
                KEY PRINCIPLES:
                - Ensure accuracy and completeness
                - Provide structured explanations with examples
                - Consider multiple solutions and trade-offs
                - Use clear language and systematic approach
                - Validate practical applicability
    
                DEFAULTS:
                - Respond in Chinese unless otherwise specified
                - Tailor to user context and requirements
                - Include step-by-step explanations when needed"""
    system_prompt_claudeUse = system_prompt_claude + "\n" + system_prompt
    
    print('[Debug:construct_data] 系统提示:', message)
    
    if history:
        question = normal_qa_new.get_model_specific_histories2(username, message, model_name, rounds)
        print("[Debug:construct_data] 生成的历史提问:", question)
    else:
        question = message
        print("[Debug:construct_data] 生成的提问:", question)
    
    # 返回构造的数据
    # TODO：改造为一个类，包含所有的属性和方法，避免应用、追踪困难
    # 这里，message是用户的提问，question是用message和历史对话生成的提问
    return {
        "info_list": info_list,
        "rounds": rounds,
        "system_prompt": system_prompt,
        "system_prompt_claudeUse": system_prompt_claudeUse,
        "question": question,
        "response_data": response,
        "file_list": file_list,
        "left_select_list": left_select_list,
        "right_select_list": right_select_list,
        "history": history,
        "message": message,
        "model_states": model_states,
        "user_name": name2RealUse,
        "writer": username,
        "prompt_storage_key": prompt_mem_key,
    }
