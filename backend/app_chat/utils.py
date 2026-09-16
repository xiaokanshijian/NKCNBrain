import random

import pandas as pd
import io
import openpyxl
import base64
import re
import urllib.parse

import os
from PyPDF2 import PdfFileReader, PdfFileWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import requests


def clean_json_content(content):
    """清理内容中的特殊字符，避免JSON解析错误"""
    if not content:
        return content

    # 替换可能导致JSON解析错误的字符
    # 但保留基本的中文和英文内容
    import re
    # 移除控制字符（除了换行、回车、制表符）
    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', content)

    return content


def limit_content_to_400_chars(content):
    """将内容限制在400字以内，保留前150字、后150字和中间随机100字"""
    if not content:
        return content

    # 如果内容少于400字，直接返回
    if len(content) <= 400:
        return content

    # 取前150字
    prefix = content[:150]

    # 取后150字
    suffix = content[-150:]

    # 计算中间部分
    middle_start = 150
    middle_end = len(content) - 150

    # 如果中间部分少于100字，取全部
    if middle_end - middle_start <= 100:
        middle = content[middle_start:middle_end]
    else:
        # 从中间部分随机取100字
        import random
        random_start = random.randint(middle_start, middle_end - 100)
        middle = content[random_start:random_start + 100]

    return prefix + "..." + middle + "..." + suffix


# 计算已有内容的总字/单词数
def get_total_words_count(content_list):
    """
    计算内容列表中的总字/单词数
    """
    total_count = 0
    for content in content_list:
        total_count += count_words(content)
    return total_count


def count_words(text):
    """
    计算文本中的字/单词数量
    对于中文，每个汉字算一个
    对于英文，每个空格分隔的单词算一个
    """
    # 分离中文和英文
    chinese_chars = 0
    english_words = 0

    # 处理英文部分 - 找出所有英文单词并计数
    import re
    english_pattern = re.compile(r'[a-zA-Z]+')
    english_words = len(english_pattern.findall(text))

    # 处理中文部分 - 每个汉字算一个
    chinese_pattern = re.compile(r'[\u4e00-\u9fa5]')
    chinese_chars = len(chinese_pattern.findall(text))

    # 返回总数
    return chinese_chars + english_words


def count_words_another(text):
    """
    另一种逻辑，计算文本的字数，统计中文字符数和英文单词数
    """
    if not text:
        return 0

    cleaned_text = text

    # 🔥 如果是目录卡，移除参考文献部分（## 参考文献 之后的内容不计算字数）
    # 查找"## 参考文献"的位置
    ref_pattern = r'##\s*参考文献'
    ref_match = re.search(ref_pattern, cleaned_text, re.IGNORECASE)
    if ref_match:
        # 移除参考文献部分（包括"## 参考文献"本身）
        cleaned_text = cleaned_text[:ref_match.start()]

    # # 统计中文字符
    # chinese_count = len(re.findall(r'[\u4e00-\u9fa5]', text))

    # 移除所有修改标签（如<第1次修改内容>、</第1次修改内容>、<第2次修改内容>等）
    cleaned_text = re.sub(r'<第\d+次修改内容>', '', cleaned_text)
    cleaned_text = re.sub(r'</第\d+次修改内容>', '', cleaned_text)

    # 🔥 移除章首/章尾/节首/节尾内容（这些内容不计入卡片字数）
    # 通过在生成/组装时使用特殊标记【章首】、【章尾】、【节首】、【节尾】来标记
    # 标记后的内容是一段话（200-250字，单段落，无换行），格式为：【标记】内容\n\n
    # 移除标记、内容和后面的换行
    cleaned_text = re.sub(r'【章首】[^\n]+\n\n', '', cleaned_text)
    cleaned_text = re.sub(r'【章尾】[^\n]+\n\n', '', cleaned_text)
    cleaned_text = re.sub(r'【节首】[^\n]+\n\n', '', cleaned_text)
    cleaned_text = re.sub(r'【节尾】[^\n]+\n\n', '', cleaned_text)

    # 统计中文字符（在移除标签后统计，这样标签中的字符不会被计算）
    chinese_count = len(re.findall(r'[\u4e00-\u9fa5]', cleaned_text))

    # 清理markdown符号
    # cleaned_text = text
    # 只移除代码块标记
    cleaned_text = re.sub(r'```', '', cleaned_text)
    # 只移除行内代码标记
    cleaned_text = re.sub(r'`', '', cleaned_text)
    # 只移除加粗标记
    cleaned_text = re.sub(r'\*\*', '', cleaned_text)
    # 只移除斜体标记
    cleaned_text = re.sub(r'\*', '', cleaned_text)
    # 保留链接文本，移除URL
    cleaned_text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', cleaned_text)
    # 只移除标题标记
    cleaned_text = re.sub(r'#{1,6}\s', '', cleaned_text)
    # 移除列表符号
    cleaned_text = re.sub(r'-\s+', ' ', cleaned_text)
    # 移除引用符号
    cleaned_text = re.sub(r'>\s+', ' ', cleaned_text)
    # 将标点符号替换为空格（保留中文字符）
    cleaned_text = re.sub(r'[^\w\s\u4e00-\u9fa5]|_', ' ', cleaned_text)
    # 合并多个空格
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    # 去除首尾空格
    cleaned_text = cleaned_text.strip()

    # # 统计英文单词（按空格分隔）
    # english_words = [word for word in cleaned_text.split()
    #                  if re.search(r'[a-zA-Z]', word) and len(word) > 0]
    # english_count = len(english_words)

    # 🔥 统计英文单词和数字（连续的数字只算一个词）
    # 将连续的数字序列替换为一个占位符，然后统计
    cleaned_for_count = re.sub(r'\b\d+\b', ' NUM ', cleaned_text)
    cleaned_for_count = re.sub(r'\s+', ' ', cleaned_for_count).strip()

    # 统计包含字母的单词和数字序列
    words_for_count = cleaned_for_count.split()
    english_count = 0
    for word in words_for_count:
        if word == 'NUM':
            # 数字序列，算一个词
            english_count += 1
        elif re.search(r'[a-zA-Z]', word):
            # 包含字母的单词
            english_count += 1

    # 返回总字数
    return chinese_count + english_count


def calculate_overlap_ratio(text1, text2, n=2):
    """
    使用n-gram来计算两个文本的相似度
    n-gram是连续n个字符的序列
    """
    # 如果任一文本为空，则相似度为0
    if not text1 or not text2:
        return 0

    # 生成n-gram
    def get_ngrams(text, n):
        return [text[i:i + n] for i in range(len(text) - n + 1)]

    ngrams1 = set(get_ngrams(text1, n))
    ngrams2 = set(get_ngrams(text2, n))

    # 计算Jaccard相似度
    intersection = len(ngrams1.intersection(ngrams2))
    union = len(ngrams1.union(ngrams2))

    return intersection / union if union > 0 else 0


# 创建一个单独的函数来处理问号和叹号的检测
def detect_special_markers(message):
    """
    检测用户消息中的特殊标记：
    - 三个问号 (???)
    - 两个问号 (??) 及可选的加号
    - 叹号 (!) 及可选的加号

    返回:
        dict: 包含检测结果的字典，包括：
            - has_triple_question_marks: 布尔值
            - has_double_question_marks: 布尔值
            - double_question_match: 匹配对象或None
            - plus_count: 双问号后的加号数量(0-3)
            - exclamation_match: 匹配对象或None
            - exclamation_plus_count: 叹号后的加号数量(0-3)
    """
    result = {
        'has_triple_question_marks': False,
        'has_double_question_marks': False,
        'double_question_match': None,
        'plus_count': 0,
        'exclamation_match': None,
        'exclamation_plus_count': 0
    }

    # 检测三个问号
    result['has_triple_question_marks'] = bool(
        re.search(r'(?<!\?)\?\?\?(?!\?)', message) or
        re.search(r'(?<!？)？？？(?!？)', message)
    )

    # 检测两个问号及可选的加号
    double_question_mark_match = re.search(r'(?<!\?)\?\?\+{0,3}(?!\?)|(?<!？)？？\+{0,3}(?!？)', message)
    result['has_double_question_marks'] = double_question_mark_match is not None
    result['double_question_match'] = double_question_mark_match

    # 如果找到双问号，计算加号数量
    if double_question_mark_match:
        match_string = double_question_mark_match.group(0)
        result['plus_count'] = match_string.count('+')

    # 检查叹号及可选的加号 - 在最后6个字符中搜索
    # exclamation_match = re.search(r'[!！]\+{0,3}', message[-6:] if len(message) >= 6 else message)
    # result['exclamation_match'] = exclamation_match

    # 如果找到叹号，计算加号数量
    # if exclamation_match:
    #     match_string = exclamation_match.group(0)
    #     result['exclamation_plus_count'] = match_string.count('+')

    return result


def get_base64_size(base64_str):
    # 计算base64字符串对应的字节大小
    # base64编码后的字符串长度 * 0.75 约等于原始数据的字节数
    return len(base64_str) * 0.75


def add_cardImage(info_list, image_url):
    info_list.extend([
        {
            "type": "text",
            "text": "此图片与给你的[重要素材文本]可能有较大关联，请你注意理解并用于回答用户提出的问题。"
                    "如果你参考了此图片, 请指出对一些关键点的理解分析，可以采用多层次注意分析法理解："
                    "识别图片的版面结构及区域关系、突出的自然特征、分析关联素材文本、可能存在的印刷、涂鸦层"
                    "和手写笔迹等内容，最后通过它们之间的关联理解提高准确度、加深认识"
        },
        {
            "type": "image_url",
            "image_url": {
                "url": image_url
            }
        }
    ])


def extract_card_ids(title):
    """
    从卡片标题中提取卡片ID
    例如："卡片11965批判结果" -> ["11965"]
          "卡片2740,2686自定义功能结果" -> ["2740", "2686"]
    """
    if not title:
        return []

    # 使用正则表达式匹配"卡片"后面的数字（可能有多组，以逗号分隔）
    match = re.search(r'卡片(\d+(?:,\d+)*)', title)
    if not match:
        return []

    # 提取所有ID并转换为列表
    ids_str = match.group(1)
    return [id_str.strip() for id_str in ids_str.split(',')]


def calculate_weighted_score_recursion(card, all_cards_dict, score_cache=None, visited=None, depth=0, max_depth=10):
    """
    递归计算卡片的加权得分，使用缓存避免重复计算

    参数:
    - card: 当前处理的卡片
    - all_cards_dict: 所有卡片的字典，键为cid
    - score_cache: 已计算过的卡片得分缓存，避免重复计算
    - visited: 已访问过的卡片cid集合，用于检测循环引用
    - depth: 当前递归深度
    - max_depth: 最大递归深度，防止无限递归

    返回:
    - 计算出的加权得分
    - 用于计算的来源卡片数量
    """
    if score_cache is None:
        score_cache = {}

    if visited is None:
        visited = set()

    # 检查是否已经计算过这个卡片的得分
    if card['cid'] in score_cache:
        # 使用缓存的结果，避免重复计算
        return score_cache[card['cid']]

    # 防止循环引用和过深递归，以及不在0-5的异常数据跳过(主要是为-1的，即打分失败的默认值)
    if card['cid'] in visited or depth > max_depth or card['scoreSFT'] <= 0:
        return card['scoreSFT'], 0

    visited.add(card['cid'])

    # 权重设计：使用衰减函数，p为自身权重，从0.6开始
    # q, m, n, x, y... 依次减小
    p = 0.6  # 自身评分权重，占60%
    decay_factor = 0.5  # 每一级来源的权重衰减因子

    # 提取来源卡片ID
    source_ids = extract_card_ids(card['title'])

    if not source_ids:
        # 没有来源卡片，仅使用自身评分
        score_cache[card['cid']] = (card['scoreSFT'], 0)
        return card['scoreSFT'], 0

    # 计算来源卡片的总权重和加权得分
    total_source_weight = 0
    weighted_sum = 0
    total_sources = 0

    for level, source_id in enumerate(source_ids, 1):
        if source_id.isdigit() and int(source_id) in all_cards_dict:
            source_card = all_cards_dict[int(source_id)]

            # 递归计算来源卡片的得分，使用visited.copy()确保不同路径的访问历史互不干扰，只有真正的循环引用才会被截断
            source_score, source_count = calculate_weighted_score_recursion(
                source_card, all_cards_dict, score_cache, visited.copy(), depth + 1, max_depth
            )

            # 计算当前来源卡片的权重 (q, m, n, ...) = p * decay_factor^level
            source_weight = p * (decay_factor / len(source_ids))

            if source_score > 0:
                weighted_sum += source_score * source_weight
                total_source_weight += source_weight
                total_sources += 1 + source_count  # 当前来源 + 其子来源
            else:
                continue

    # 计算总得分 = 自身得分 * p + 来源加权得分 * (1-p)
    self_weight = p
    source_total_weight = 1 - p  # 所有来源卡片总共占40%
    final_score = 0

    # 归一化来源权重
    if total_source_weight > 0:
        normalized_weighted_sum = weighted_sum * (source_total_weight / total_source_weight)
        final_score = card['scoreSFT'] * self_weight + normalized_weighted_sum
    else:
        normalized_weighted_sum = 0
        final_score = card['scoreSFT']

    # 缓存计算结果
    score_cache[card['cid']] = (final_score, total_sources)

    return final_score, total_sources


def remove_thinking_and_checking_blocks(text):
    """
    移除文本中的thinking和checking块，只保留最终结果部分。
    能够处理各种格式，包括嵌套在thinking/checking块中的代码块。
    具体方法：
    1. 逐行分析文本
    2. 使用堆栈跟踪当前所在的块类型
    3. 识别并跳过checking块thinking和
    4. 正确处理嵌套的代码块（如'''python）
    5. 只保留不在思考或检查块内的行

    参数:
        text (str): 包含thinking/checking块的输入文本

    返回:
        str: 只保留最终结果部分的文本
    """
    lines = text.split('\n')
    result = []

    in_thinking_block = False
    in_checking_block = False
    code_block_stack = []

    for line in lines:
        trimmed_line = line.strip()

        # 检查thinking块的开始
        if trimmed_line == '```thinking':
            in_thinking_block = True
            code_block_stack.append('thinking')
            continue

        # 检查checking块的开始
        if trimmed_line == '```checking':
            in_checking_block = True
            code_block_stack.append('checking')
            continue

        # 检查嵌套代码块的开始
        if (in_thinking_block or in_checking_block) and \
                trimmed_line.startswith('```') and \
                trimmed_line != '```' and \
                'thinking' not in trimmed_line and \
                'checking' not in trimmed_line:
            # 这是一个像```python这样的嵌套代码块
            code_block_stack.append('code')
            continue

        # 检查任何块的结束
        if trimmed_line == '```' and code_block_stack:
            block_type = code_block_stack.pop()
            if block_type == 'thinking':
                in_thinking_block = False
            if block_type == 'checking':
                in_checking_block = False
            continue

        # 如果不在thinking或checking块内，添加到结果中
        if not in_thinking_block and not in_checking_block:
            result.append(line)  # 保留原始空格

    return '\n'.join(result).strip()


def remove_thinking_and_checking_blocks_plus(text):
    """
    🔥 增强版：移除文本中所有包含"think"或"check"的代码块，以及<think>标签，只保留最终结果部分。
    能够处理各种格式，包括：
    - ```thinking
    - ```checking
    - ```check again
    - ```think about it
    - 任何以```开头，后面包含"think"或"check"的块（不区分大小写）
    - <think>xxx</think>

    具体方法：
    1. 先移除<think>标签及其内容
    2. 逐行分析文本
    3. 使用堆栈跟踪当前所在的块类型
    4. 识别并跳过所有包含"think"或"check"的代码块
    5. 正确处理嵌套的代码块（如```python）
    6. 只保留不在思考或检查块内的行

    参数:
        text (str): 包含thinking/checking块的输入文本

    返回:
        str: 只保留最终结果部分的文本
    """
    # 🔥 首先移除<think>标签及其内容（包括换行符）
    import re
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)

    lines = text.split('\n')
    result = []

    in_thinking_checking_block = False
    code_block_stack = []

    for line in lines:
        trimmed_line = line.strip()

        # 检查是否是以```开头的代码块
        if trimmed_line.startswith('```'):
            # 提取代码块标识（去掉```）
            block_identifier = trimmed_line[3:].strip().lower()

            # 检查是否包含"think"或"check"（不区分大小写）
            if block_identifier and ('think' in block_identifier or 'check' in block_identifier):
                # 这是一个thinking/checking相关的块，开始跳过
                in_thinking_checking_block = True
                code_block_stack.append('think_check')
                continue
            elif in_thinking_checking_block:
                # 在thinking/checking块内的嵌套代码块（如```python），继续跳过
                code_block_stack.append('code')
                continue
            elif trimmed_line == '```':
                # 单独的```，可能是结束标记
                if code_block_stack:
                    block_type = code_block_stack.pop()
                    if block_type == 'think_check':
                        in_thinking_checking_block = False
                # 如果不在thinking/checking块内，保留这行
                if not in_thinking_checking_block:
                    result.append(line)
                continue
            else:
                # 普通的代码块（如```python），不在thinking/checking块内，保留
                result.append(line)
                continue

        # 检查代码块结束（单独的```）
        if trimmed_line == '```' and code_block_stack:
            block_type = code_block_stack.pop()
            if block_type == 'think_check':
                in_thinking_checking_block = False
            continue

        # 如果不在thinking/checking块内，添加到结果中
        if not in_thinking_checking_block:
            result.append(line)  # 保留原始空格

    return '\n'.join(result).strip()


def extract_thinking_checking_blocks(text):
    """
    提取文本中的所有thinking和checking块

    参数:
        text (str): 包含thinking和checking块的文本

    返回:
        list: 包含所有thinking和checking块的列表
    """
    lines = text.split('\n')
    blocks = []
    current_block = []
    in_block = False
    in_thinking_block = False
    in_checking_block = False
    code_block_stack = []

    for i, line in enumerate(lines):
        trimmed_line = line.strip()

        # 检查thinking块的开始
        if trimmed_line == '```thinking':
            in_block = True
            in_thinking_block = True
            code_block_stack.append('thinking')
            current_block = [line]
            continue

        # 检查checking块的开始
        if trimmed_line == '```checking':
            in_block = True
            in_checking_block = True
            code_block_stack.append('checking')
            current_block = [line]
            continue

        # 如果在块内，收集行
        if in_block:
            current_block.append(line)

            # 检查嵌套代码块的开始
            if (in_thinking_block or in_checking_block) and \
                    trimmed_line.startswith('```') and \
                    trimmed_line != '```' and \
                    'thinking' not in trimmed_line and \
                    'checking' not in trimmed_line:
                code_block_stack.append('code')
                continue

            # 检查块的结束
            if trimmed_line == '```' and code_block_stack:
                block_type = code_block_stack.pop()
                if block_type == 'thinking':
                    in_thinking_block = False
                    if not code_block_stack:  # 如果stack为空，表示整个thinking块结束
                        in_block = False
                        blocks.append('\n'.join(current_block))
                        current_block = []
                elif block_type == 'checking':
                    in_checking_block = False
                    if not code_block_stack:  # 如果stack为空，表示整个checking块结束
                        in_block = False
                        blocks.append('\n'.join(current_block))
                        current_block = []

    return blocks


def restore_thinking_checking_blocks(original_text, processed_text, merged_new_content):
    """
    将从原文中移除的thinking和checking块加回到合并后的新内容之前

    参数:
        original_text (str): 原始文本，可能包含thinking和checking块
        processed_text (str): 移除thinking和checking块后的文本
        merged_new_content (str): 经过处理后的最终结果

    返回:
        str: 将thinking和checking块加回后的最终结果
    """
    # 如果原始文本和处理后的文本相同，说明没有thinking和checking块，直接返回合并后的内容
    if original_text == processed_text:
        return merged_new_content

    # 提取原始文本中的所有thinking和checking块
    thinking_checking_blocks = extract_thinking_checking_blocks(original_text)

    # 将提取的块加到合并后的新内容之前
    if thinking_checking_blocks:
        result = '\n'.join(thinking_checking_blocks + ['', merged_new_content])
    else:
        result = merged_new_content

    return result


def is_valid_answer(answer):
    # 定义无效回答的模式
    invalid_patterns = [
        "此模型您已暂时关闭使用",
        "出错，参考文档内容偏多，或服务器繁忙！",
        "API调用出错",
        "API调用超时",
        "服务器繁忙"
    ]
    # 检查当前回答是否包含任何无效模式
    is_valid = True
    for pattern in invalid_patterns:
        if pattern in answer:
            is_valid = False
            break
    return is_valid


def get_first_valid_answer(model_name: str, chat_content: dict, window_id="left"):
    # 定义无效回答的模式
    invalid_patterns = [
        "此模型您已暂时关闭使用",
        "出错，参考文档内容偏多，或服务器繁忙！",
        "API调用出错",
        "API调用超时",
        "服务器繁忙"
    ]
    # 若主窗口回答没问题，直接返回
    if window_id == "left" and chat_content[model_name] is not None:
        content = chat_content[model_name]
        is_valid = True
        for pattern in invalid_patterns:
            if pattern in content:
                is_valid = False
                break
        if is_valid:
            return content
    # 否则遍历所有回答，返回第一个有效回答
    for answer in chat_content.values():
        if answer is None or answer == "":
            continue
        # 检查当前回答是否包含任何无效模式
        is_valid = True
        for pattern in invalid_patterns:
            if pattern in answer:
                is_valid = False
                break
        # 如果是有效回答，返回它
        if is_valid:
            return answer

    # 如果没有找到有效回答，返回None或其他默认值
    return None


def sample_content(content, max_chars=400):
    """
    从内容中随机采样，确保结果不超过指定字数，且保持句子完整
    :param content: 原始内容
    :param max_chars: 最大字符数
    :return: 采样后的内容
    """
    # 按句子分割内容（考虑中文句号、英文句号、问号、感叹号）
    sentences = re.split(r'([。.!?！？\n])', content)

    # 重新组合句子（保留分割符）
    complete_sentences = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            complete_sentences.append(sentences[i] + sentences[i + 1])
        else:
            complete_sentences.append(sentences[i])

    # 如果最后一个元素不是完整的句子，添加它
    if len(sentences) % 2 == 1:
        complete_sentences.append(sentences[-1])

    # 随机打乱句子顺序
    random.shuffle(complete_sentences)

    # 选择句子直到接近但不超过500字
    sampled_content = []
    current_length = 0

    for sentence in complete_sentences:
        # 如果添加当前句子后总长度仍在限制内，就添加它
        if current_length + len(sentence) <= max_chars:
            sampled_content.append(sentence)
            current_length += len(sentence)
        else:
            break

    # 如果没有选到任何句子（所有句子都太长），至少返回一个完整句子
    if not sampled_content and complete_sentences:
        return complete_sentences[0][:max_chars]

    return ''.join(sampled_content)


# 用于语音合成文本分段的工具函数
def split_text_by_size(text, max_bytes=1000):  # 预留一些余量，不用满1024
    segments = []
    current_segment = ""
    current_bytes = 0

    # 按句子分割文本
    sentences = re.split('([。！？])', text)

    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        if i + 1 < len(sentences):
            sentence += sentences[i + 1]  # 加回标点符号

        # 计算当前句子的字节数
        sentence_bytes = len(sentence.encode('utf-8'))

        if current_bytes + sentence_bytes > max_bytes:
            if current_segment:
                segments.append(current_segment)
            current_segment = sentence
            current_bytes = sentence_bytes
        else:
            current_segment += sentence
            current_bytes += sentence_bytes

    if current_segment:
        segments.append(current_segment)

    return segments


def get_time_period(hour):
    """确定时间段特征"""
    if 5 <= hour < 8:
        return "morning_dawn"
    elif 8 <= hour < 11:
        return "morning_prime"
    elif 11 <= hour < 13:
        return "noon"
    elif 13 <= hour < 15:
        return "afternoon_rest"
    elif 15 <= hour < 17:
        return "afternoon_work"
    elif 17 <= hour < 19:
        return "evening"
    elif 19 <= hour < 23:
        return "night"
    else:
        return "late_night"


def is_rest_time(hour):
    """判断是否是特殊休息时段"""
    return (13 <= hour < 15) or (hour >= 23 or hour < 5)


def read_xlsx_to_binary(file_path):
    try:
        wb = openpyxl.load_workbook(file_path)
        binary_data = io.BytesIO()
        wb.save(filename=binary_data)
        binary_data.seek(0)
        return binary_data
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def read_prompt_from_file(file_path):
    prompt_dict = {}
    params_dict = {}
    for sheet_name in ['LUI1', 'LUI2', 'LUI3', 'LUI4']:
        print(sheet_name)
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        # 第2列是key，第3列是value
        data_dict = dict(zip(df.iloc[:, 1], df.iloc[:, 2]))
        param_dict = dict(zip(df.iloc[:, 1], df.iloc[:, 3]))
        print(param_dict)
        params_dict[sheet_name] = param_dict
        prompt_dict[sheet_name] = data_dict
    return prompt_dict, params_dict


def read_prompt_from_bytes(binary_data, backend_file_path='./backData/prompt.xlsx'):
    # 必须先写再读
    with open(backend_file_path, 'wb') as file:
        file.write(binary_data)
    return read_prompt_from_file(backend_file_path)


def prompt_to_ghp(prompt_params):
    prompt = prompt_params[0]
    params = prompt_params[1]
    # print('get user prompt:', prompt)
    res = {
        "LUI1": {},
        "LUI2": {},
        "LUI3": {},
        "LUI4": {}
    }
    params_out = {}
    res["LUI1"]["summary"] = prompt["LUI1"]["summary"]
    res["LUI1"]["topic"] = prompt["LUI1"]["topic"]
    res["LUI2"]["qa"] = prompt["LUI2"]["qa"]
    res["LUI2"]["qa_question"] = prompt["LUI2"]["qa_question"]
    res["LUI2"]["img_topic"] = prompt["LUI2"]["img_topic"]
    res["LUI2"]["topic_question"] = prompt["LUI2"]["topic_question"]
    res["LUI3"]["multi_summarize"] = prompt["LUI3"]["multi_summarize"]
    res["LUI3"]["multi_suggestions"] = prompt["LUI3"]["multi_suggestions"]
    res["LUI3"]["multi_study_guide"] = prompt["LUI3"]["multi_study_guide"]
    res["LUI3"]["single_understand"] = prompt["LUI3"]["single_understand"]
    res["LUI3"]["single_critique"] = prompt["LUI3"]["single_critique"]
    res["LUI3"]["single_outline"] = prompt["LUI3"]["single_outline"]
    res["LUI3"]["user_define"] = prompt["LUI3"]["user_define"]
    res["LUI4"]["rate"] = prompt["LUI4"]["rate"]
    print(type(params["LUI1"]["topic"]))
    params_out["topic"] = int(params["LUI1"]["topic"])
    params_out["image"] = int(params["LUI1"]["image"])
    params_out["img_topic"] = int(params["LUI2"]["img_topic"])
    params_out["topic_question"] = int(params["LUI2"]["topic_question"])
    params_out["qa_question"] = int(params["LUI2"]["qa_question"])
    # print('new prompt:', res)
    return res, params_out


def encode_to_base64(chinese_text):
    """
    将汉字字符串转换为Base64编码。

    参数:
    chinese_text (str): 需要编码的汉字字符串。

    返回:
    str: Base64编码后的字符串。
    """
    # 将汉字字符串转换为字节串
    byte_text = chinese_text.encode('utf-8')
    # 对字节串进行Base64编码
    base64_encoded = base64.b64encode(byte_text)
    # 将Base64编码的字节串解码为字符串
    return base64_encoded.decode('utf-8')


def decode_from_base64(base64_text):
    """
    将Base64编码的字符串解码回汉字字符串。

    参数:
    base64_text (str): Base64编码的字符串。

    返回:
    str: 解码后的汉字字符串。
    """
    # 将Base64编码的字符串转换为字节串
    byte_base64 = base64_text.encode('utf-8')
    # 对Base64编码的字节串进行解码
    base64_decoded = base64.b64decode(byte_base64)
    # 将解码后的字节串解码为汉字字符串
    return base64_decoded.decode('utf-8')


def encode_string_to_binary(input_string):
    # 初始化一个空字符串用于存储结果
    binary_result = ''
    # 遍历字符串中的每个字符
    for char in input_string:
        # 将每个字符转换为ASCII码，然后转换为八位二进制数
        ascii_code = ord(char)
        binary_str = format(ascii_code, '08b')
        # 将转换后的二进制数添加到结果字符串中
        binary_result += binary_str
    return binary_result


def decode_binary_to_ascii(binary_str):
    # 确保输入的二进制字符串长度是8的倍数
    if len(binary_str) % 8 != 0:
        raise ValueError("输入的二进制字符串长度不是8的倍数")
    # 初始化一个空字符串用于存储结果
    decoded_string = ''
    # 每次取8位二进制数进行解码
    for i in range(0, len(binary_str), 8):
        # 截取8位二进制数
        binary_chunk = binary_str[i:i+8]
        # 将二进制字符串转换为整数
        binary_int = int(binary_chunk, 2)
        # 将整数转换回字符，并添加到结果字符串中
        decoded_string += chr(binary_int)
    return decoded_string


def encode_string_to_hex(input_string):
    # 初始化一个空字符串用于存储结果
    hex_result = ''
    # 遍历字符串中的每个字符
    for char in input_string:
        # 将每个字符转换为ASCII码，然后转换为16进制数
        ascii_code = ord(char)
        hex_str = format(ascii_code, '02x')  # 使用'02x'格式化为两位的16进制数
        # 将转换后的16进制数添加到结果字符串中
        hex_result += hex_str
    return hex_result


def decode_hex_to_string(hex_str):
    # 确保16进制字符串的长度是偶数
    if len(hex_str) % 2 != 0:
        raise ValueError("16进制字符串的长度不是偶数")
    # 初始化一个空字符串用于存储结果
    decoded_string = ''
    # 每次取两位16进制数进行解码
    for i in range(0, len(hex_str), 2):
        # 截取两位16进制数
        hex_chunk = hex_str[i:i+2]
        # 将16进制字符串转换为整数
        binary_int = int(hex_chunk, 16)
        # 将整数转换回字符，并添加到结果字符串中
        decoded_string += chr(binary_int)
    return decoded_string


def encode_chinese_to_binary(str):
    return encode_string_to_binary((encode_to_base64(str)))


def decode_chinese_from_binary(binary):
    return decode_from_base64(decode_binary_to_ascii(binary))


def encode_chinese_to_hex(str):
    return encode_string_to_hex((encode_to_base64(str)))


def decode_chinese_from_hex(hex):
    return decode_from_base64(decode_hex_to_string(hex))


def remove_spaces_and_blank_lines(text):
    # 按行分割字符串，然后剔除空行和空字符串
    lines = text.splitlines()
    # 使用列表推导式过滤掉空行和只包含空格的行
    filtered_lines = [line for line in lines if line.strip()]
    # 使用join方法将过滤后的行重新组合为一个字符串
    return '\n'.join(filtered_lines)


def resolve_prompt_storage_key(writer_username, origin_real_name=None):
    """
    场景 prompt/params 在 global_var.store_memory 中的键。
    组本场景下多人共用本子 userId（writer_username），协作者各自的真实登录名在 origin_real_name；
    写入与读取必须使用同一规则，避免后切换子场景的人覆盖他人内存中的 prompt。
    """
    w = (writer_username or "").strip()
    o = (origin_real_name or "").strip()
    if not o:
        return w
    if o == w:
        return w
    return o


if __name__ == '__main__':
    # file_path = r'C:\Users\hp\Desktop\prompt2.xlsx'
    # binary_data = read_xlsx_to_binary(file_path)
    # res = read_prompt_from_bytes(binary_data)
    # print(res)
    # res2 = prompt_to_ghp(res)
    # print(res2)
    # 如果是本地测试要改read_prompt_from_bytes，一个是改成../backData，另一个是getBuffer()

    chinese_name = '学位论文修改'
    # print('中文字符串：', chinese_name)
    # bs64 = encode_to_base64(chinese_name)
    # print('字符串转base64编码：', bs64)
    # binary = encode_string_to_binary(bs64)
    # print('base64转二进制数字编码：', binary)
    # ascii = decode_binary_to_ascii(binary)
    # print('二进制转base64编码：', ascii)
    # cn = decode_from_base64(ascii)
    # print('base64编码转字符串：', cn)

    # 转为二进制
    binary = encode_chinese_to_binary(chinese_name)
    chinese = decode_chinese_from_binary(binary)
    print(binary, chinese)
    # 转为十六进制
    hex = encode_chinese_to_hex(chinese_name)
    print(len(hex))
    chinese = decode_chinese_from_hex(hex)
    print(hex, chinese)


def translate_text(text, source_lang='en', target_lang='zh'):
    # 这里应该是调用翻译服务的代码
    # 例如使用 Google Translate API
    # 以下代码仅为示例，需要替换为实际的 API 调用代码
    # ...
    return "翻译后的文本"


def create_new_pdf(original_path, translated_text, output_path):
    reader = PdfFileReader(original_path)
    writer = PdfFileWriter()

    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]
        text = page.extract_text()
        # 翻译文本
        translated_text = translate_text(text)

    # 保存新的 PDF 文件
    with open(output_path, 'wb') as f:
        writer.write(f)


def getDataUsingPyPdf2(filename):
    pdf = PdfFileReader(open(filename, "rb"))
    content = ""
    num = pdf.getNumPages()
    for i in range(0, num):
        extractedText = pdf.getPage(i).extractText()
        content += extractedText + "\n"
    return content



