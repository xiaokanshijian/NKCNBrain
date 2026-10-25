# encoding=utf-8
"""
🔥 本子输出文章生成相关的视图函数
根据目录卡片生成完整的输出文章
"""
import nkcn_public_config as _public_config
import json
import os
import re
import asyncio
import threading
import uuid
import requests
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from app_chat.config.config_manager import config_manager
from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
from app_chat.models import Card
from zym.models import scene, UserNotebook
from app_chat.keyword_analyzer import analyze_keyword_four_color_dmt_with_llm
from openai import OpenAI
import pandas as pd
from llm_langchain import global_var
from concurrent.futures import ThreadPoolExecutor, as_completed
from app_chat.iteration_debug_utils import detect_and_log_anomalies, save_iteration_debug_output


def get_small_model_server_url(username):
    """
    根据username从全局变量获取小模型ID，返回对应的服务器URL
    3007 -> 127.0.0.1
    3001-3006 -> 127.0.0.1
    """
    from app_chat.global_state import GLOBAL_STATE
    model_id = GLOBAL_STATE.user_little_model_id.get(username, "3003")
    if str(model_id) == "3007":
        return _public_config.endpoint('NKCN_SERVICE_8000_URL', 'http://localhost:8000')
    else:
        return _public_config.endpoint('NKCN_SERVICE_8000_URL', 'http://localhost:8000')


def _clean_4byte_utf8_chars(text):
    """
    🔥 清理4字节UTF-8字符（如emoji），避免MySQL utf8字符集报错

    参数:
        text: 需要清理的文本

    返回: 清理后的文本（移除所有4字节UTF-8字符）
    """
    if not text:
        return text
    try:
        # 方法1：使用字符迭代方式（最可靠且高效）
        # 直接遍历字符，跳过4字节字符（代码点>=0x10000的字符）
        cleaned_chars = []
        for char in text:
            # 获取字符的Unicode代码点
            code_point = ord(char)
            # 只保留代码点<0x10000的字符（即最多3字节UTF-8字符）
            if code_point < 0x10000:
                cleaned_chars.append(char)
            # 代码点>=0x10000的字符是4字节UTF-8字符，跳过
        return ''.join(cleaned_chars)
    except Exception as e:
        print(f"[_clean_4byte_utf8_chars] 字符迭代清理失败: {e}")
        # 备用方案：使用编码方式清理
        try:
            text_bytes = text.encode('utf-8', errors='ignore')
            cleaned_bytes = bytearray()
            i = 0
            while i < len(text_bytes):
                byte = text_bytes[i]
                # 检测4字节UTF-8字符（0xF0-0xF4开头）
                if 0xF0 <= byte <= 0xF4:
                    # 跳过4个字节（4字节UTF-8字符）
                    i += 4
                    continue
                # 检测3字节UTF-8字符（0xE0-0xEF开头）
                elif 0xE0 <= byte <= 0xEF:
                    if i + 2 < len(text_bytes) and (text_bytes[i + 1] & 0xC0) == 0x80 and (
                            text_bytes[i + 2] & 0xC0) == 0x80:
                        cleaned_bytes.extend(text_bytes[i:i + 3])
                        i += 3
                    else:
                        i += 1
                # 检测2字节UTF-8字符（0xC0-0xDF开头）
                elif 0xC0 <= byte <= 0xDF:
                    if i + 1 < len(text_bytes) and (text_bytes[i + 1] & 0xC0) == 0x80:
                        cleaned_bytes.extend(text_bytes[i:i + 2])
                        i += 2
                    else:
                        i += 1
                # ASCII字符（0x00-0x7F）
                elif byte < 0x80:
                    cleaned_bytes.append(byte)
                    i += 1
                else:
                    # 续字节（0x80-0xBF）或无效字节，跳过
                    i += 1
            return cleaned_bytes.decode('utf-8', errors='ignore')
        except Exception as e2:
            print(f"[_clean_4byte_utf8_chars] 编码清理也失败: {e2}")
            # 最后备用方案：直接过滤掉无法编码的字符
            try:
                return text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
            except:
                return text


def _chinese_num_to_int(chinese_num):
    """
    将中文数字转换为整数，支持一到九十九。
    例如："一"->1, "十"->10, "十一"->11, "二十"->20, "二十一"->21, "九十九"->99
    """
    if not chinese_num:
        return None

    # 基本数字映射
    basic_nums = {
        '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
    }

    # 特殊处理：十、十一到十九
    if chinese_num == '十':
        return 10
    if chinese_num.startswith('十') and len(chinese_num) == 2:
        # 十一、十二...十九
        unit = basic_nums.get(chinese_num[1], 0)
        return 10 + unit

    # 处理二十到九十九
    if '十' in chinese_num:
        if len(chinese_num) == 2:
            # 二十、三十...九十
            tens = basic_nums.get(chinese_num[0], 0)
            return tens * 10
        elif len(chinese_num) == 3:
            # 二十一、二十二...九十九
            tens = basic_nums.get(chinese_num[0], 0)
            unit = basic_nums.get(chinese_num[2], 0)
            return tens * 10 + unit

    # 单个数字：一到九
    return basic_nums.get(chinese_num, None)


def _int_to_chinese_num(num):
    """
    将整数转换为中文数字，支持1到99。
    例如：1->"一", 10->"十", 11->"十一", 20->"二十", 21->"二十一", 99->"九十九"
    """
    if num < 1 or num > 99:
        return None

    basic_nums = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九']

    if num < 10:
        return basic_nums[num]
    elif num == 10:
        return '十'
    elif num < 20:
        return '十' + basic_nums[num - 10]
    elif num < 100:
        tens = num // 10
        units = num % 10
        if units == 0:
            return basic_nums[tens] + '十'
        else:
            return basic_nums[tens] + '十' + basic_nums[units]

    return None


def _parse_directory_structure(content):
    """
    解析目录结构，返回章/节/小节的层级结构

    返回:
        {
            'title': '目录名（不带"目录"两字）',
            'chapters': [
                {
                    'name': '章名',
                    'name_with_prefix': '一、章名',
                    'sections': [
                        {
                            'name': '节名',
                            'name_with_prefix': '1.节名',
                            'subsections': [
                                {'name': '小节名', 'name_with_prefix': 'A.小节名'},
                                ...
                            ]
                        },
                        ...
                    ]
                },
                ...
            ]
        }
    """
    try:
        lines = content.strip().split('\n')
        if not lines:
            return None

        # 第一行应该是"xxx目录"
        first_line = lines[0].strip()
        if not first_line.endswith('目录'):
            return None

        title = first_line[:-2].strip()  # 去掉"目录"两字

        # 解析目录结构
        chapters = []
        current_chapter = None
        current_section = None

        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            # 判断层级：一、二、三...十一、十二...（章），1. 2. 3... 11. 12....（节），A. B. C...（小节）
            # 🔥 保留原始行（包含序号），同时提取不包含序号的部分用于匹配
            # 🔥 支持中文数字：一、二、...十、十一、十二、...（最多支持到九十九）
            if re.match(r'^[一二三四五六七八九十百]+[、.]', line):
                # 章：遇到新章时，先将当前节添加到当前章
                if current_section:
                    if not current_chapter:
                        current_chapter = {
                            'name': '',
                            'name_with_prefix': '',  # 🔥 保留带序号的全名
                            'sections': []
                        }
                    current_chapter['sections'].append(current_section)
                    current_section = None

                # 🔥 支持中文数字：一、二、...十、十一、十二、...（使用更宽泛的正则匹配）
                chapter_name = re.sub(r'^[一二三四五六七八九十百]+[、.]\s*', '', line).strip()
                if current_chapter:
                    chapters.append(current_chapter)
                current_chapter = {
                    'name': chapter_name,
                    'name_with_prefix': line.strip(),  # 🔥 保留带序号的全名（如"一、第一章"）
                    'sections': []
                }
            elif re.match(r'^\d+[.]', line):
                # 节
                section_name = re.sub(r'^\d+[.]\s*', '', line).strip()
                if not current_chapter:
                    # 如果没有章，创建一个默认章
                    current_chapter = {
                        'name': '',
                        'name_with_prefix': '',
                        'sections': []
                    }
                if current_section:
                    current_chapter['sections'].append(current_section)
                current_section = {
                    'name': section_name,
                    'name_with_prefix': line.strip(),  # 🔥 保留带序号的全名（如"1. 第一节"）
                    'subsections': []
                }
            elif re.match(r'^[A-Z]', line) and not re.match(r'^[A-Z]{2,}', line) and not re.match(r'^[A-Z]\d', line):
                # 小节：以单个大写字母开头，且不是多个字母（如"AB"）或字母+数字（如"A1"）
                # 支持 "A. xxx" 或 "A xxx" 或 "Axxx" 格式
                # 去掉开头的字母和可能的点号/空格
                subsection_name = re.sub(r'^[A-Z]([.]|[\s\u3000])*\s*', '', line).strip()
                if not subsection_name:
                    # 如果去掉后为空，跳过这一行
                    continue
                if not current_section:
                    # 如果没有节，创建一个默认节
                    if not current_chapter:
                        current_chapter = {
                            'name': '',
                            'name_with_prefix': '',
                            'sections': []
                        }
                    current_section = {
                        'name': '',
                        'name_with_prefix': '',
                        'subsections': []
                    }
                current_section['subsections'].append({
                    'name': subsection_name,
                    'name_with_prefix': line.strip()  # 🔥 保留带序号的全名（如"A. 第一小节"）
                })

        # 添加最后一个章和节（确保不丢失）
        if current_section:
            if not current_chapter:
                current_chapter = {
                    'name': '',
                    'name_with_prefix': '',
                    'sections': []
                }
            current_chapter['sections'].append(current_section)
        if current_chapter:
            chapters.append(current_chapter)

        # 🔥 调试：打印解析结果
        print(f"[_parse_directory_structure] 解析结果：共{len(chapters)}章")
        for i, ch in enumerate(chapters, 1):
            print(f"  第{i}章: {ch['name']}, 共{len(ch['sections'])}节")
            for j, sec in enumerate(ch['sections'], 1):
                print(f"    第{j}节: {sec['name']}, 共{len(sec.get('subsections', []))}小节")
                for k, subsec in enumerate(sec.get('subsections', []), 1):
                    print(f"      第{k}小节: {subsec['name']}")

        return {
            'title': title,
            'chapters': chapters
        }
    except Exception as e:
        print(f"[_parse_directory_structure] 解析目录结构失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _calculate_word_count_allocation(directory_structure, target_total_words=5000):
    """
    计算各章/节/小节的字数分配

    返回:
        {
            'chapter_word_count': int,  # 每章基础字数
            'section_word_count': int,  # 每节基础字数
            'subsection_word_count': int,  # 每小节基础字数
            'allocations': {
                'chapters': [
                    {
                        'name': '章名',
                        'name_with_prefix': '一、章名',
                        'word_count': int,
                        'sections': [
                            {
                                'name': '节名',
                                'name_with_prefix': '1.节名',
                                'word_count': int,
                                'subsections': [
                                    {'name': '小节名', 'name_with_prefix': 'A.小节名', 'word_count': int},
                                    ...
                                ]
                            },
                            ...
                        ]
                    },
                    ...
                ]
            }
        }
    """
    try:
        chapters = directory_structure['chapters']

        # 统计各级数量
        total_chapters = len(chapters)
        total_sections = sum(len(ch['sections']) for ch in chapters)
        total_subsections = sum(
            len(sec['subsections']) for ch in chapters for sec in ch['sections']
        )

        # 计算字数分配
        # 基础分配：每章600字，每节400字，每小节350字（第一次生成时每处撰写位置不得低于300字）
        base_chapter = 600
        base_section = 400
        base_subsection = 350

        # 如果总数超过目标字数，按比例缩减
        estimated_total = total_chapters * base_chapter + total_sections * base_section + total_subsections * base_subsection
        if estimated_total > target_total_words:
            scale = target_total_words / estimated_total
            base_chapter = max(int(base_chapter * scale), 300)
            base_section = max(int(base_section * scale), 300)
            base_subsection = max(int(base_subsection * scale), 300)
        else:
            # 如果总数少于目标字数，按比例增加
            scale = target_total_words / estimated_total if estimated_total > 0 else 1
            base_chapter = max(int(base_chapter * scale), 300)
            base_section = max(int(base_section * scale), 300)
            base_subsection = max(int(base_subsection * scale), 300)

        # 为每个章节分配字数
        allocations = {
            'chapters': []
        }

        for chapter in chapters:
            chapter_word_count = base_chapter
            chapter_alloc = {
                'name': chapter['name'],
                'name_with_prefix': chapter.get('name_with_prefix', chapter['name']),  # 🔥 保留带序号的全名
                'word_count': chapter_word_count,
                'sections': []
            }

            for section in chapter['sections']:
                if section['subsections']:
                    # 有小节：节本身300字（过渡），每个小节base_subsection字（每处≥300字）
                    section_word_count = 300 + len(section['subsections']) * base_subsection
                else:
                    # 无小节：节本身base_section字
                    section_word_count = base_section

                section_alloc = {
                    'name': section['name'],
                    'name_with_prefix': section.get('name_with_prefix', section['name']),  # 🔥 保留带序号的全名
                    'word_count': section_word_count,
                    'subsections': []
                }

                for subsection in section['subsections']:
                    subsection_alloc = {
                        'name': subsection['name'],
                        'name_with_prefix': subsection.get('name_with_prefix', subsection['name']),  # 🔥 保留带序号的全名
                        'word_count': base_subsection
                    }
                    section_alloc['subsections'].append(subsection_alloc)

                chapter_alloc['sections'].append(section_alloc)

            allocations['chapters'].append(chapter_alloc)

        return {
            'chapter_word_count': base_chapter,
            'section_word_count': base_section,
            'subsection_word_count': base_subsection,
            'allocations': allocations
        }
    except Exception as e:
        print(f"[_calculate_word_count_allocation] 计算字数分配失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _get_relevant_cards_for_section(section_name, username, max_cards=5):
    """
    为某个小节/节/章获取相关度最高的卡片

    相关度计算：基于最长连续子字符串字数、以及子字符串出现的频率综合
    如果还没有匹配，则使用字符重合程度

    优先级（在相关度得分相同的情况下）：
    1. 关键词神经元永久卡片（is_neuron=True 且 type="永久"）
    2. 紫色或绿色、红蓝深评（占7）浅评（占3）加权得分≥3.5的卡
    3. 其他浅色卡

    返回: Card对象列表（最多max_cards张）
    """
    try:
        all_cards = Card.objects.filter(username=username)

        # 生成关键词的所有连续子字符串
        def generate_substrings(text):
            """生成文本的所有连续子字符串"""
            substrings = []
            text_len = len(text)
            # 从最长到最短生成子字符串
            for length in range(text_len, 0, -1):
                for start in range(text_len - length + 1):
                    substr = text[start:start + length]
                    if substr not in substrings:
                        substrings.append(substr)
            return substrings

        # 计算相关度得分（基于最长连续子字符串和出现频率）
        def calculate_relevance_score(section_name, card_text):
            """
            计算section_name和card_text之间的相关度得分
            使用：最长连续子字符串字数 * 出现频率
            """
            if not card_text:
                return 0

            # 生成section_name的所有子字符串
            section_substrings = generate_substrings(section_name)

            max_score = 0
            for substr in section_substrings:
                if len(substr) < 2:  # 只考虑长度>=2的子字符串
                    continue
                # 计算子字符串在card_text中出现的次数
                pattern = re.escape(substr)
                count = len(re.findall(pattern, card_text))
                if count > 0:
                    # 得分 = 子字符串长度 * 出现次数
                    score = len(substr) * count
                    max_score = max(max_score, score)

            return max_score

        # 计算字符重合度（当相关度得分为0时使用）
        def calculate_char_overlap(text1, text2):
            """计算字符重合度"""
            if not text1 or not text2:
                return 0

            chars1 = set(text1)
            chars2 = set(text2)
            intersection = chars1 & chars2
            union = chars1 | chars2

            return len(intersection) / len(union) if union else 0

        # 为每张卡片计算相关度得分
        card_relevance_scores = []  # [(card, relevance_score, char_overlap), ...]

        for card in all_cards:
            # 获取卡片的contentTitle和keyWords作为匹配文本
            card_text_parts = []
            if card.contentTitle:
                card_text_parts.append(card.contentTitle)
            if card.keyWords:
                card_text_parts.append(card.keyWords)

            if not card_text_parts:
                continue

            card_text = ' '.join(card_text_parts)

            # 计算相关度得分（基于最长连续子字符串和出现频率）
            relevance_score = calculate_relevance_score(section_name, card_text)

            # 如果相关度得分为0，计算字符重合度
            char_overlap = 0
            if relevance_score == 0:
                char_overlap = calculate_char_overlap(section_name, card_text)
                # 字符重合度转换为得分（乘以一个较小的权重，使其低于子字符串匹配得分）
                relevance_score = char_overlap * 0.5

            # 只保留相关度得分 > 0 的卡片
            if relevance_score > 0:
                card_relevance_scores.append((card, relevance_score, char_overlap))

        # 按相关度得分降序排序
        card_relevance_scores.sort(key=lambda x: x[1], reverse=True)

        # 按优先级和得分排序
        def get_card_priority(card_score_tuple):
            card, relevance_score, char_overlap = card_score_tuple
            priority_base = relevance_score

            score = float(card.score) if card.score else 0
            scoreSFT = float(card.scoreSFT) if card.scoreSFT else 0
            weighted_score = score * 0.3 + scoreSFT * 0.7

            # 优先级1：永久神经元卡（在相关度基础上增加大量权重）
            if card.is_neuron and card.type and "永久" in card.type:
                priority_base += 1000
            # 优先级2：紫色或绿色、加权得分≥3.5（增加中等权重）
            elif card.four_color_type in ['P', 'G'] and weighted_score >= 3.5:
                priority_base += 500
            # 其他卡片保持原有的相关度得分

            return priority_base

        # 按优先级排序
        card_relevance_scores.sort(key=get_card_priority, reverse=True)

        # 返回前max_cards张卡片
        result_cards = [card for card, _, _ in card_relevance_scores[:max_cards]]

        print(
            f"[_get_relevant_cards_for_section] 为'{section_name}'找到{len(result_cards)}张相关卡片（共{len(card_relevance_scores)}张候选卡片）")

        return result_cards
    except Exception as e:
        print(f"[_get_relevant_cards_for_section] 获取相关卡片失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _get_relevant_documents_for_section(section_name, username, max_docs=3):
    """
    为某个小节/节/章获取相关度最高的文档（从pre_summary目录）

    使用与_find_documents_by_keyword相同的匹配逻辑

    返回: [(文档名, pre_summary内容), ...] 列表（最多max_docs个）
    """
    try:
        from app_chat.views_generate_permanent_card import _find_documents_by_keyword

        # 提取section_name中的关键词（取最长的中文词汇作为主要关键词）
        keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', section_name)
        if not keywords:
            return []

        # 使用最长的关键词
        main_keyword = max(keywords, key=len)

        # 使用_find_documents_by_keyword查找文档
        doc_names = _find_documents_by_keyword(main_keyword, username, max_count=max_docs, min_count=1)

        if not doc_names:
            return []

        # 读取pre_summary内容
        realName = username.split('_')[0] if '_' in username else username
        bookName = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
        if not bookName:
            return []

        pre_summary_dir = f'./received_dir/user_raw_file/{realName}_{bookName}/pre_summary'
        if not os.path.exists(pre_summary_dir):
            return []

        results = []
        for doc_name in doc_names:
            doc_name_base = os.path.splitext(doc_name)[0]
            doc_ext = os.path.splitext(doc_name)[1].lstrip('.')
            if not doc_ext:
                doc_ext = 'pdf'

            md_filename = f"{doc_name_base}_Presummary_{doc_ext}.md"
            md_file_path = os.path.join(pre_summary_dir, md_filename)

            if os.path.exists(md_file_path):
                try:
                    with open(md_file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    results.append((doc_name, content))
                except Exception as e:
                    print(f"[_get_relevant_documents_for_section] 读取文档{doc_name}失败: {e}")

        return results
    except Exception as e:
        print(f"[_get_relevant_documents_for_section] 获取相关文档失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _get_refined_document_segments_for_section(section_name, username, relevant_docs, existing_section_content=None,
                                               relevant_cards=None):
    """
    🔥 迭代精进专用：细化文档素材，找到最相关段落并提取segments

    参数:
        section_name: 小节/节/章的名称
        username: 用户名
        relevant_docs: [(文档名, pre_summary内容), ...] 列表
        existing_section_content: 已有章节内容（迭代模式时使用，用于备用关键词采样）
        relevant_cards: 相关卡片列表（用于备用关键词采样）

    返回: [
        {
            'doc_name': '文档名',
            'paragraphs': [
                {'page_range': (start_page, end_page), 'content': '段落内容'},
                ...
            ],
            'segments': [
                {'page': int, 'content': 'segment内容'},
                ...
            ]
        },
        ...
    ]
    """
    try:
        realName = username.split('_')[0] if '_' in username else username
        bookName = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
        if not bookName:
            return []

        # 生成关键词的所有连续子字符串
        def generate_substrings(kw):
            substrings = []
            kw_len = len(kw)
            for length in range(kw_len, 0, -1):
                for start in range(kw_len - length + 1):
                    substr = kw[start:start + length]
                    if substr not in substrings:
                        substrings.append(substr)
            return substrings

        # 提取section_name中的关键词（取最长的中文词汇）
        keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', section_name)
        if not keywords:
            return []
        main_keyword = max(keywords, key=len)
        keyword_substrings = generate_substrings(main_keyword)

        results = []
        userbook_path = f'./received_dir/user_raw_file/{realName}_{bookName}'

        for doc_name, pre_summary_content in relevant_docs:
            try:
                # 1. 在pre_summary中找到最相关的段落（通过---分割的段落）
                sections = pre_summary_content.split('---')
                section_scores = []  # [(score, page_range, content), ...]

                for section in sections:
                    if not section.strip():
                        continue

                    section_score = 0
                    for substr in keyword_substrings:
                        pattern = re.escape(substr)
                        count = len(re.findall(pattern, section, re.IGNORECASE))
                        if count > 0:
                            section_score += len(substr) * count  # 最长连续子字符串字数 * 出现频率

                    if section_score > 0:
                        page_match = re.search(r'\[页码：第(\d+)页(?:-第(\d+)页)?\]', section)
                        if page_match:
                            start_page = int(page_match.group(1))
                            end_page = int(page_match.group(2)) if page_match.group(2) else start_page
                            page_range = (start_page, end_page)
                            # 提取段落内容（去掉页码标记）
                            content = re.sub(r'\[页码：第\d+页(?:-第\d+页)?\]', '', section).strip()
                            section_scores.append((section_score, page_range, content))

                # 按得分降序排序，取前2-3个段落
                section_scores.sort(key=lambda x: x[0], reverse=True)
                top_paragraphs = section_scores[:3] if len(section_scores) >= 3 else section_scores

                if not top_paragraphs:
                    continue

                # 2. 提取segments：解析页数区间，从原文中提取对应segments
                doc_name_base = os.path.splitext(doc_name)[0]
                doc_ext = os.path.splitext(doc_name)[1].lstrip('.') or 'pdf'
                # 注意：这里file_path只是用于说明，实际segments提取在后面的逻辑中处理
                # file_path = os.path.join(userbook_path, doc_name)

                # 收集所有需要提取的页码（从top_paragraphs中的页数区间展开）
                all_pages = set()
                for _, page_range, _ in top_paragraphs:
                    start, end = page_range
                    for p in range(start, end + 1):
                        all_pages.add(p)

                print(
                    f"[_get_refined_document_segments_for_section] 从{len(top_paragraphs)}个段落中提取到页数区间: {[(start, end) for _, (start, end), _ in top_paragraphs]}，展开为{len(all_pages)}个页码")

                segments = []

                # 尝试从split_docs获取segments（优先使用内存中的split_docs）
                print(
                    f"[_get_refined_document_segments_for_section] 开始提取segments，文档: {doc_name}，需要页码: {sorted(all_pages)}")
                try:
                    from llm_langchain import global_var as langchain_global_var
                    split_docs = langchain_global_var.get_user_split(username, doc_name)
                    if split_docs:
                        print(
                            f"[_get_refined_document_segments_for_section] split_docs存在，共{len(split_docs)}个文档片段，开始匹配页码")
                        # 从split_docs中找到对应页码的segments
                        for doc in split_docs:
                            # 检查metadata中是否有page信息
                            page_num = None
                            if doc.metadata and "page" in doc.metadata:
                                page_num = doc.metadata["page"]
                                # 页号从0开始，转换为从1开始的页码
                                if isinstance(page_num, int):
                                    page_num = page_num + 1
                            elif doc.page_content and "[页码：" in doc.page_content:
                                # 从content中提取页码
                                page_match = re.search(r'\[页码：第(\d+)页', doc.page_content)
                                if page_match:
                                    page_num = int(page_match.group(1))

                            if page_num and page_num in all_pages:
                                # 提取content（去掉页码标记）
                                content = re.sub(r'\[页码：第\d+页(?:-第\d+页)?\]\s*', '', doc.page_content).strip()
                                if content:
                                    segments.append({'page': page_num, 'content': content})
                        print(f"[_get_refined_document_segments_for_section] 从split_docs获取到{len(segments)}个segments")
                    else:
                        print(f"[_get_refined_document_segments_for_section] split_docs不存在或为空，将尝试其他方法")
                except Exception as e:
                    print(f"[_get_refined_document_segments_for_section] 从split_docs获取segments失败: {e}")
                    import traceback
                    traceback.print_exc()

                # 如果split_docs不可用或没有找到匹配的segments，尝试解析原PDF文件
                if not segments:
                    # 构建PDF文件路径（doc_name可能没有扩展名，需要尝试添加）
                    pdf_path = os.path.join(userbook_path, doc_name)
                    # 如果路径不存在且doc_name没有扩展名，尝试添加.pdf扩展名
                    if not os.path.exists(pdf_path) and not os.path.splitext(doc_name)[1]:
                        pdf_path = os.path.join(userbook_path, doc_name + '.pdf')
                    print(f"[_get_refined_document_segments_for_section] split_docs未找到segments，尝试解析PDF文件: {pdf_path}")
                    if os.path.exists(pdf_path) and (
                            doc_name.lower().endswith('.pdf') or pdf_path.lower().endswith('.pdf')):
                        print(f"[_get_refined_document_segments_for_section] PDF文件存在，开始解析")
                        try:
                            # 优先使用PyMuPDF (fitz)解析PDF（项目已有）
                            try:
                                import fitz  # PyMuPDF
                                pdf_doc = fitz.open(pdf_path)
                                total_pages = len(pdf_doc)
                                print(f"[_get_refined_document_segments_for_section] PDF文件打开成功，共{total_pages}页")

                                for page_num in all_pages:
                                    # PDF页码从0开始，所以减1
                                    if 1 <= page_num <= total_pages:
                                        try:
                                            page = pdf_doc[page_num - 1]
                                            page_content = page.get_text().strip()
                                            if page_content:
                                                segments.append({'page': page_num, 'content': page_content})
                                                print(
                                                    f"[_get_refined_document_segments_for_section] 成功提取PDF第{page_num}页，长度: {len(page_content)}字")
                                        except Exception as e:
                                            print(
                                                f"[_get_refined_document_segments_for_section] 提取PDF第{page_num}页失败: {e}")
                                    else:
                                        print(
                                            f"[_get_refined_document_segments_for_section] 页码{page_num}超出范围（总页数: {total_pages}）")

                                pdf_doc.close()
                                print(
                                    f"[_get_refined_document_segments_for_section] 从PDF文件（PyMuPDF）提取到{len(segments)}个segments（共{total_pages}页，需要页码: {sorted(all_pages)}）")
                            except ImportError:
                                print(f"[_get_refined_document_segments_for_section] PyMuPDF不可用，尝试使用PyPDF2")
                                # PyMuPDF不可用，尝试使用PyPDF2
                                try:
                                    import PyPDF2
                                    with open(pdf_path, 'rb') as pdf_file:
                                        pdf_reader = PyPDF2.PdfReader(pdf_file)
                                        total_pages = len(pdf_reader.pages)
                                        print(
                                            f"[_get_refined_document_segments_for_section] PDF文件（PyPDF2）打开成功，共{total_pages}页")

                                        for page_num in all_pages:
                                            if 1 <= page_num <= total_pages:
                                                try:
                                                    page_obj = pdf_reader.pages[page_num - 1]
                                                    page_content = page_obj.extract_text().strip()
                                                    if page_content:
                                                        segments.append({'page': page_num, 'content': page_content})
                                                        print(
                                                            f"[_get_refined_document_segments_for_section] 成功提取PDF第{page_num}页，长度: {len(page_content)}字")
                                                except Exception as e:
                                                    print(
                                                        f"[_get_refined_document_segments_for_section] 提取PDF第{page_num}页失败: {e}")

                                        print(
                                            f"[_get_refined_document_segments_for_section] 从PDF文件（PyPDF2）提取到{len(segments)}个segments（共{total_pages}页）")
                                except ImportError:
                                    print(
                                        f"[_get_refined_document_segments_for_section] PDF解析库（PyMuPDF/PyPDF2）不可用，尝试使用OCR文件")
                                    # 继续尝试OCR文件
                        except Exception as e:
                            print(f"[_get_refined_document_segments_for_section] 解析PDF文件失败: {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        print(
                            f"[_get_refined_document_segments_for_section] PDF文件不存在或无法找到: doc_name={doc_name}, userbook_path={userbook_path}")

                # 如果PDF解析也没有找到，尝试从OCR raw.txt文件提取（适用于扫描件）
                if not segments:
                    ocr_dir = os.path.join(userbook_path, f"{doc_name_base}_ocr")
                    txt_path = os.path.join(ocr_dir, f"{doc_name_base}_raw.txt")

                    if os.path.exists(txt_path):
                        try:
                            with open(txt_path, 'r', encoding='utf-8') as f:
                                ocr_content = f.read()

                            # 按页面分割（格式：==================================================\n第 n 页\n==================================================）
                            page_pattern = r'={50,}\s*\n第\s*(\d+)\s*页\s*\n={50,}'
                            page_matches = list(re.finditer(page_pattern, ocr_content))

                            print(
                                f"[_get_refined_document_segments_for_section] OCR文件找到{len(page_matches)}个页面标记，需要提取的页码: {sorted(all_pages)}")

                            for page_num in all_pages:
                                # 找到对应页面的内容
                                page_content = None
                                for i, match in enumerate(page_matches):
                                    if int(match.group(1)) == page_num:
                                        start_pos = match.end()
                                        end_pos = page_matches[i + 1].start() if i + 1 < len(page_matches) else len(
                                            ocr_content)
                                        page_content = ocr_content[start_pos:end_pos].strip()
                                        break

                                if page_content:
                                    segments.append({'page': page_num, 'content': page_content})
                                else:
                                    print(f"[_get_refined_document_segments_for_section] 未找到第{page_num}页的内容")

                            print(f"[_get_refined_document_segments_for_section] 从OCR文件提取到{len(segments)}个segments")
                        except Exception as e:
                            print(f"[_get_refined_document_segments_for_section] 读取OCR文件失败: {e}")
                    else:
                        print(f"[_get_refined_document_segments_for_section] OCR文件不存在（该文档可能不是扫描件）: {txt_path}")

                # 🔥 对segments计算与当前章/节/小节名关联性综合排名，只取前2个
                if segments:
                    segment_scores = []
                    current_substrings = keyword_substrings  # 当前使用的子字符串列表

                    for seg in segments:
                        seg_content = seg['content']
                        # 计算关联性得分（与pre_summary中的计算方式相同）
                        seg_score = 0
                        for substr in current_substrings:
                            pattern = re.escape(substr)
                            count = len(re.findall(pattern, seg_content, re.IGNORECASE))
                            if count > 0:
                                seg_score += len(substr) * count  # 最长连续子字符串字数 * 出现频率

                        segment_scores.append((seg_score, seg))

                    # 按得分降序排序
                    segment_scores.sort(key=lambda x: x[0], reverse=True)
                    max_score = segment_scores[0][0] if segment_scores else 0

                    # 🔥 如果最高得分是0分，尝试使用备用关键词重新计算
                    if max_score == 0:
                        print(
                            f"[_get_refined_document_segments_for_section] 最高得分为0，检查备用关键词条件: segments={len(segments) if segments else 0}, existing_section_content={'有' if existing_section_content else '无'}, relevant_cards={'有' if relevant_cards else '无'}")

                        if segments:
                            # 🔥 策略1：先从已有章节内容采样（如果存在）
                            if existing_section_content:
                                print(f"[_get_refined_document_segments_for_section] 策略1：尝试从已有章节内容采样")

                                # 改进的采样策略：优先提取长词汇、去除常见停用词
                                all_words = re.findall(r'[\u4e00-\u9fa5]{2,8}', existing_section_content)

                                # 常见停用词（过滤掉无意义的词汇）
                                stopwords = {'这是', '这是', '一个', '一种', '一种', '可以', '能够', '应该', '需要', '要求',
                                             '进行', '实现', '完成', '开始', '结束', '包括', '包含', '涉及', '相关', '通过',
                                             '根据', '基于', '按照', '依照', '对于', '关于', '由于', '因此', '所以', '但是',
                                             '然而', '不过', '而且', '并且', '同时', '另外', '此外', '还有', '以及', '或者',
                                             '如果', '假如', '假设', '即使', '虽然', '尽管', '不管', '无论', '不论', '只要',
                                             '只有', '除非', '除了', '除去', '之外', '之内', '之中', '之间', '之上', '之下',
                                             '之前', '之后', '以上', '以下', '以内', '以外', '以外', '以来', '以后', '以前',
                                             '方法', '方式', '手段', '途径', '渠道', '形式', '模式', '类型', '种类', '类别',
                                             '方面', '角度', '维度', '层面', '阶段', '时期', '时期', '过程', '步骤', '环节',
                                             '内容', '结果', '效果', '作用', '功能', '特性', '特点', '特征', '性质', '属性',
                                             '问题', '情况', '现象', '表现', '显示', '表明', '说明', '表示', '代表', '体现',
                                             '出现', '产生', '形成', '建立', '构建', '创建', '设计', '开发', '制造', '制作',
                                             '使用', '应用', '运用', '利用', '采用', '采取', '选择', '选取', '获得', '得到',
                                             '取得', '达到', '实现', '完成', '执行', '实施', '进行', '开展', '推动', '促进',
                                             '提高', '提升', '增强', '加强', '改善', '改进', '优化', '完善', '发展', '发展',
                                             '研究', '分析', '探讨', '讨论', '论述', '阐述', '说明', '介绍', '描述', '解释',
                                             '理解', '认识', '了解', '掌握', '学习', '掌握', '熟悉', '精通', '熟练', '熟练',
                                             '重要', '关键', '核心', '主要', '基本', '基础', '根本', '本质', '实质', '实际',
                                             '具体', '详细', '精确', '准确', '正确', '合适', '适当', '恰当', '适宜', '适合',
                                             '有效', '有用', '有益', '有利', '有力', '有力', '有力', '有力', '有力', '有力'}

                                # 过滤停用词，并按长度排序（优先长词汇）
                                filtered_words = [w for w in all_words if w not in stopwords]
                                # 按长度降序排序，取前15个
                                filtered_words.sort(key=len, reverse=True)
                                sampled_from_content = filtered_words[:15]

                                print(
                                    f"[_get_refined_document_segments_for_section] 从已有章节内容采样到{len(sampled_from_content)}个备用关键词（已过滤停用词，优先长词汇）")

                                if sampled_from_content:
                                    # 生成备用关键词的子字符串
                                    fallback_substrings = []
                                    for kw in sampled_from_content[:15]:  # 最多尝试15个备用关键词
                                        fallback_substrings.extend(generate_substrings(kw))

                                    print(
                                        f"[_get_refined_document_segments_for_section] 生成{len(fallback_substrings)}个备用子字符串，开始重新计算得分")

                                    # 重新计算得分
                                    segment_scores_fallback = []
                                    for seg in segments:
                                        seg_content = seg['content']
                                        seg_score = 0
                                        for substr in fallback_substrings:
                                            pattern = re.escape(substr)
                                            count = len(re.findall(pattern, seg_content, re.IGNORECASE))
                                            if count > 0:
                                                seg_score += len(substr) * count
                                        segment_scores_fallback.append((seg_score, seg))

                                    segment_scores_fallback.sort(key=lambda x: x[0], reverse=True)
                                    max_score_fallback = segment_scores_fallback[0][0] if segment_scores_fallback else 0

                                    if max_score_fallback > 0:
                                        print(
                                            f"[_get_refined_document_segments_for_section] ✅ 使用已有章节内容采样后最高得分: {max_score_fallback}")
                                        segment_scores = segment_scores_fallback
                                        max_score = max_score_fallback
                                    else:
                                        print(
                                            f"[_get_refined_document_segments_for_section] ⚠️ 使用已有章节内容采样后最高得分仍为0，尝试策略2：从相关卡片采样")

                                        # 🔥 策略2：如果已有章节内容采样失败，尝试从关联卡片采样
                                        if relevant_cards:
                                            try:
                                                from app_chat.views_generate_permanent_card import \
                                                    _sample_words_from_cards
                                                sampled = _sample_words_from_cards(relevant_cards, main_keyword,
                                                                                   max_samples=15)
                                                print(
                                                    f"[_get_refined_document_segments_for_section] 从相关卡片采样到{len(sampled)}个备用关键词")

                                                if sampled:
                                                    # 生成备用关键词的子字符串
                                                    fallback_substrings = []
                                                    for kw in sampled[:15]:  # 最多尝试15个备用关键词
                                                        fallback_substrings.extend(generate_substrings(kw))

                                                    print(
                                                        f"[_get_refined_document_segments_for_section] 生成{len(fallback_substrings)}个备用子字符串，开始重新计算得分")

                                                    # 重新计算得分
                                                    segment_scores_fallback = []
                                                    for seg in segments:
                                                        seg_content = seg['content']
                                                        seg_score = 0
                                                        for substr in fallback_substrings:
                                                            pattern = re.escape(substr)
                                                            count = len(re.findall(pattern, seg_content, re.IGNORECASE))
                                                            if count > 0:
                                                                seg_score += len(substr) * count
                                                        segment_scores_fallback.append((seg_score, seg))

                                                    segment_scores_fallback.sort(key=lambda x: x[0], reverse=True)
                                                    max_score_fallback = segment_scores_fallback[0][
                                                        0] if segment_scores_fallback else 0

                                                    if max_score_fallback > 0:
                                                        print(
                                                            f"[_get_refined_document_segments_for_section] ✅ 使用相关卡片采样后最高得分: {max_score_fallback}")
                                                        segment_scores = segment_scores_fallback
                                                        max_score = max_score_fallback
                                                    else:
                                                        print(
                                                            f"[_get_refined_document_segments_for_section] ⚠️ 使用相关卡片采样后最高得分仍为0")
                                            except Exception as e:
                                                print(f"[_get_refined_document_segments_for_section] 从卡片采样失败: {e}")
                                                import traceback
                                                traceback.print_exc()
                                        else:
                                            print(f"[_get_refined_document_segments_for_section] ⚠️ 没有相关卡片，无法尝试策略2")
                                else:
                                    print(
                                        f"[_get_refined_document_segments_for_section] ⚠️ 从已有章节内容未能采样到有效关键词，尝试策略2：从相关卡片采样")

                                    # 🔥 策略2：如果已有章节内容采样失败，尝试从关联卡片采样
                                    if relevant_cards:
                                        try:
                                            from app_chat.views_generate_permanent_card import _sample_words_from_cards
                                            sampled = _sample_words_from_cards(relevant_cards, main_keyword,
                                                                               max_samples=15)
                                            print(
                                                f"[_get_refined_document_segments_for_section] 从相关卡片采样到{len(sampled)}个备用关键词")

                                            if sampled:
                                                # 生成备用关键词的子字符串
                                                fallback_substrings = []
                                                for kw in sampled[:15]:  # 最多尝试15个备用关键词
                                                    fallback_substrings.extend(generate_substrings(kw))

                                                print(
                                                    f"[_get_refined_document_segments_for_section] 生成{len(fallback_substrings)}个备用子字符串，开始重新计算得分")

                                                # 重新计算得分
                                                segment_scores_fallback = []
                                                for seg in segments:
                                                    seg_content = seg['content']
                                                    seg_score = 0
                                                    for substr in fallback_substrings:
                                                        pattern = re.escape(substr)
                                                        count = len(re.findall(pattern, seg_content, re.IGNORECASE))
                                                        if count > 0:
                                                            seg_score += len(substr) * count
                                                    segment_scores_fallback.append((seg_score, seg))

                                                segment_scores_fallback.sort(key=lambda x: x[0], reverse=True)
                                                max_score_fallback = segment_scores_fallback[0][
                                                    0] if segment_scores_fallback else 0

                                                if max_score_fallback > 0:
                                                    print(
                                                        f"[_get_refined_document_segments_for_section] ✅ 使用相关卡片采样后最高得分: {max_score_fallback}")
                                                    segment_scores = segment_scores_fallback
                                                    max_score = max_score_fallback
                                                else:
                                                    print(
                                                        f"[_get_refined_document_segments_for_section] ⚠️ 使用相关卡片采样后最高得分仍为0")
                                        except Exception as e:
                                            print(f"[_get_refined_document_segments_for_section] 从卡片采样失败: {e}")
                                            import traceback
                                            traceback.print_exc()
                            # 🔥 策略2：如果没有已有章节内容，直接尝试从关联卡片采样
                            elif relevant_cards:
                                print(f"[_get_refined_document_segments_for_section] 策略2：没有已有章节内容，直接尝试从相关卡片采样")
                                try:
                                    from app_chat.views_generate_permanent_card import _sample_words_from_cards
                                    sampled = _sample_words_from_cards(relevant_cards, main_keyword, max_samples=15)
                                    print(f"[_get_refined_document_segments_for_section] 从相关卡片采样到{len(sampled)}个备用关键词")

                                    if sampled:
                                        # 生成备用关键词的子字符串
                                        fallback_substrings = []
                                        for kw in sampled[:15]:  # 最多尝试15个备用关键词
                                            fallback_substrings.extend(generate_substrings(kw))

                                        print(
                                            f"[_get_refined_document_segments_for_section] 生成{len(fallback_substrings)}个备用子字符串，开始重新计算得分")

                                        # 重新计算得分
                                        segment_scores_fallback = []
                                        for seg in segments:
                                            seg_content = seg['content']
                                            seg_score = 0
                                            for substr in fallback_substrings:
                                                pattern = re.escape(substr)
                                                count = len(re.findall(pattern, seg_content, re.IGNORECASE))
                                                if count > 0:
                                                    seg_score += len(substr) * count
                                            segment_scores_fallback.append((seg_score, seg))

                                        segment_scores_fallback.sort(key=lambda x: x[0], reverse=True)
                                        max_score_fallback = segment_scores_fallback[0][
                                            0] if segment_scores_fallback else 0

                                        if max_score_fallback > 0:
                                            print(
                                                f"[_get_refined_document_segments_for_section] ✅ 使用相关卡片采样后最高得分: {max_score_fallback}")
                                            segment_scores = segment_scores_fallback
                                            max_score = max_score_fallback
                                        else:
                                            print(f"[_get_refined_document_segments_for_section] ⚠️ 使用相关卡片采样后最高得分仍为0")
                                except Exception as e:
                                    print(f"[_get_refined_document_segments_for_section] 从卡片采样失败: {e}")
                                    import traceback
                                    traceback.print_exc()
                            else:
                                print(
                                    f"[_get_refined_document_segments_for_section] ⚠️ 条件不满足，无法使用备用关键词（没有existing_section_content和relevant_cards）")

                    # 取前2个
                    top_segments = [seg for _, seg in segment_scores[:2]]
                    segments = top_segments
                    print(
                        f"[_get_refined_document_segments_for_section] 关联性排名后保留{len(segments)}个segments（最高得分: {max_score}）")

                results.append({
                    'doc_name': doc_name,
                    'paragraphs': [{'page_range': pr, 'content': c} for _, pr, c in top_paragraphs],
                    'segments': segments
                })

                # 打印文档出处信息
                total_chars = sum(len(s['content']) for s in segments)
                print(
                    f"[_get_refined_document_segments_for_section] 文档{doc_name}: {len(top_paragraphs)}个段落, {len(segments)}个segments, 共{total_chars}字")

            except Exception as e:
                print(f"[_get_refined_document_segments_for_section] 处理文档{doc_name}失败: {e}")
                import traceback
                traceback.print_exc()
                continue

        return results
    except Exception as e:
        print(f"[_get_refined_document_segments_for_section] 获取细化文档素材失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _list_all_writing_units(directory_structure):
    """
    从目录结构中列出所有撰写单元（与 writing_tasks 顺序、层级一致）。
    返回: [(name_with_prefix, level, parent_chapter, parent_section), ...]，
    level 为 '章'/'节'/'小节'，parent_chapter 和 parent_section 为父级名称（无则 None）。
    """
    units = []
    for ch in directory_structure.get('chapters', []):
        cname = ch.get('name_with_prefix') or ch.get('name', '')
        if not ch.get('sections'):
            # 章（无节）
            units.append((cname, '章', None, None))
        else:
            # 有节，遍历节
            for sec in ch['sections']:
                sname = sec.get('name_with_prefix') or sec.get('name', '')
                if not sec.get('subsections'):
                    # 节（无小节）
                    units.append((sname, '节', cname, None))
                else:
                    # 有小节，遍历小节
                    for sub in sec['subsections']:
                        uname = sub.get('name_with_prefix') or sub.get('name', '')
                        units.append((uname, '小节', cname, sname))
    return units


def _pre_analyze_directory(directory_structure, directory_content, username):
    """
    🔥 迭代精进专用：预分析目录，生成结构化分析结果。
    生成/迭代报告时，每章/节/小节的撰写要求将据此解析并传入模型。

    参数:
        directory_structure: 目录结构（_parse_directory_structure的返回值）
        directory_content: 原始目录内容
        username: 用户名

    返回: 预分析结果字符串（结构化格式，含严格的章节撰写要求块，便于解析）
    """
    try:
        import time
        base_system_prompt = "你是专业的学术写作分析专家，擅长分析目录结构和撰写要求。"

        directory_text = directory_content
        writing_units = _list_all_writing_units(directory_structure)

        # 构建「必须逐条列出」的撰写单元列表（用于 prompt），包含父级信息
        units_list_text = ""
        for i, (name_with_prefix, level, parent_chapter, parent_section) in enumerate(writing_units, 1):
            if level == '章':
                units_list_text += f"{i}. [{level}] {name_with_prefix}\n"
            elif level == '节':
                units_list_text += f"{i}. [{level}] {name_with_prefix}（所在章：{parent_chapter}）\n"
            elif level == '小节':
                units_list_text += f"{i}. [{level}] {name_with_prefix}（所在章：{parent_chapter}，所在节：{parent_section}）\n"

        user_prompt = f"""请对以下目录进行预分析，生成结构化分析结果。

**重要**：必须严格按照下列格式输出，便于后续程序解析。尤其是「## 章节撰写要求」部分，必须为下面列出的**每一个**撰写单元单独给出撰写要求，不得遗漏、不得合并。

---

## 题目解析
（对目录标题和目标意图的解析，约80–120字）

## 关键词可能
（列出可能的关键词和核心概念）

## 整体撰写要求
（本子卡片相关综述：重点、过程、陈述依据、创造涌现性内容所占比例、边界底线等，约100–180字）

## 章节撰写要求
（**必须**为下面列出的每一个撰写单元单独一段，格式严格如下，否则无法解析。）

**重要提醒**：分析某**节**或**小节**的撰写要求时，务必结合其**所在章名、所在节名**。小节名（如「A.小组工单」）往往不含主题、核心聚焦等关键信息，而**章名、节名**（如「一、潮汐海盐主题应用」「1.主题内涵」）才点明主题与核心；撰写要求中须明显体现这些上下文，避免只看当前标题而导致泛泛、假大空或脱题。同时一定要避免“由大说小”（不错的废话），而是要“以小见大”，具体内容为主体，宏观指向为辅线

以下为全部撰写单元（与目录层级一致）：
{units_list_text}

请对**上述每一个**撰写单元，按顺序输出如下格式的块（标点、标记必须一致）：

### [撰写要求] <撰写单元名称，必须与上面列表中的名称完全一致，此处不需要写出上级标题信息>
撰写要求：（该章/节/小节的撰写重点、注意事项、必须包含的要点、忌写内容等，此处需要体现其上级标题信息（如果有），击穿性自然融入，50–150字）

示例：
### [撰写要求] 一、第一章 绪论
撰写要求：概述研究背景与意义，明确研究对象与问题，指出创新点与全文结构；避免堆砌文献，忌与摘要雷同。

### [撰写要求] 1. 研究现状
撰写要求：本节位于「一、第一章 绪论」中，需围绕「研究背景与现状」这一主题展开。应系统梳理相关领域的研究进展，分析现有研究的不足，为后续研究奠定基础。避免简单罗列文献，要突出具体研究空白和创新点。

...

### [撰写要求] A. 主题思维链
撰写要求：本小节位于「六、【NKCN·Brain主题应用一·潮汐海盐工坊·闭环呈现】」的「2.显隐蜕变的目标问题链生成使用·」中，需围绕「潮汐海盐工坊」这一主题应用场景，结合「显隐蜕变」和「目标问题链生成」的核心机制，阐述主题思维链的具体构建逻辑和可能的具体场景示例。撰写要求必须体现「潮汐海盐」这一具体主题背景，不能只泛泛地谈「思维链」。

（请按列表顺序，为每一个撰写单元都写出一个「### [撰写要求] …」块。注意**所有**撰写要求中，只要有所在上级章名、节名，都务必明确指出，不可略去或缩写，不可因为在A.中指出而在B.中就不写）

## 章节关联要求
（章节之间的关联和过渡要求）

## 叙述可能问题边界
（可能存在的问题和需要注意的边界）

## 递进精进建议
（如何进一步精进和优化的建议）

---

目录内容：
{directory_text}
"""

        # 调用LLM（claude-sonnet-4.5，最多3次重试）
        model_priority = ['claude-sonnet-4.5']
        max_retries = 3
        timeout = 250

        for attempt in range(max_retries):
            for model_name in model_priority:
                try:
                    model_config = config_manager.get_model_config(model_name)
                    cur_config = model_config.get_config()
                    api_key = cur_config.get("openai_api_key")
                    base_url = cur_config.get("openai_api_base")
                    full_model_name = model_config.get_full_name()
                    hyper_para = model_config.get_hyper_para()

                    # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                    # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                    #     system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                    # else:
                    #     system_prompt = base_system_prompt
                    system_prompt = base_system_prompt

                    client = OpenAI(api_key=api_key, base_url=base_url)

                    start_time = time.time()
                    response = client.chat.completions.create(
                        model=full_model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        timeout=timeout,
                        max_tokens=12888,
                        temperature=hyper_para.temperature
                    )

                    elapsed_time = time.time() - start_time

                    # 如果耗时超过250秒，认为超时，继续重试
                    if elapsed_time > 250:
                        print(f"[_pre_analyze_directory] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过250秒，认为超时，继续重试")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            return None

                    raw_content = response.choices[0].message.content.strip()
                    # 🔥 后处理：如果是claude模型，去除thinking和checking块（预防性处理，暂时不使用thinking-checking格式）
                    content = _clean_claude_response(raw_content, model_name)
                    print(f"[_pre_analyze_directory] 预分析完成，长度: {len(content)}字，耗时{elapsed_time:.2f}秒")

                    # 🔥 将预分析结果写入txt文件，便于查看
                    try:
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        # 保存到backend目录下（与app_chat同级）的"预分析结果"文件夹
                        current_file_dir = os.path.dirname(os.path.abspath(__file__))
                        # 从 backend/app_chat 向上一级到 backend 目录
                        backend_dir = os.path.dirname(current_file_dir)
                        output_dir = os.path.join(backend_dir, "预分析结果")
                        os.makedirs(output_dir, exist_ok=True)
                        output_file = os.path.join(output_dir, f"预分析_{username}_{timestamp}.txt")
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(f"预分析结果 - 用户: {username} - 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            f.write("=" * 80 + "\n\n")
                            f.write(content)
                        print(f"[_pre_analyze_directory] ✅ 预分析结果已保存到: {output_file}")
                    except Exception as e:
                        print(f"[_pre_analyze_directory] ⚠️ 保存预分析结果到文件失败: {e}")
                        import traceback
                        traceback.print_exc()

                    return content

                except Exception as e:
                    error_str = str(e).lower()
                    if 'timeout' in error_str or 'timed out' in error_str:
                        print(f"[_pre_analyze_directory] 使用{model_name}超时失败: {e}，继续重试")
                    else:
                        print(f"[_pre_analyze_directory] 尝试{attempt + 1}/{max_retries}使用{model_name}失败: {e}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return None

        return None
    except Exception as e:
        print(f"[_pre_analyze_directory] 预分析失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _get_iteration_count_from_content(content):
    """
    🔥 迭代精进专用：从现有内容中提取迭代次数

    参数:
        content: 现有内容

    返回: 迭代次数（整数，如果没有找到则返回0）
    """
    try:
        if not content:
            return 0

        # 查找所有<第N次修改内容>标签
        pattern = r'<第(\d+)次修改内容>'
        matches = re.findall(pattern, content)

        if not matches:
            return 0

        # 返回最大的迭代次数
        max_iteration = max(int(match) for match in matches)
        return max_iteration
    except Exception as e:
        print(f"[_get_iteration_count_from_content] 提取迭代次数失败: {e}")
        return 0


def _parse_pre_analysis_chapter_requirements(pre_analysis):
    """
    从预分析结果中解析「## 章节撰写要求」下所有 ### [撰写要求] <name_with_prefix> 块。
    返回: dict[str, str]，key 为撰写单元名称（含序号，如 "一、第一章"），value 为该条撰写要求正文。
    """
    mapping = {}
    if not pre_analysis:
        return mapping
    # 匹配 ### [撰写要求] <标题行> \n 撰写要求：<正文至下一个###或##>
    pattern = r'###\s*\[撰写要求\]\s*(.+?)\n\s*撰写要求[：:]\s*([\s\S]+?)(?=\n###\s*\[撰写要求\]|\n##\s+|\Z)'
    for m in re.finditer(pattern, pre_analysis):
        name = m.group(1).strip()
        body = m.group(2).strip()
        if name and body:
            mapping[name] = body
    return mapping


def _extract_pre_analysis_global_sections(pre_analysis):
    """
    提取预分析中的「整体撰写要求」「章节关联要求」「叙述可能问题边界」等通用块。
    按 ## 分割，匹配标题后取整块内容。返回 dict[str, str]。
    """
    sections = {}
    if not pre_analysis:
        return sections
    parts = re.split(r'\n##\s+', pre_analysis)
    want = {'整体撰写要求', '章节关联要求', '叙述可能问题边界'}
    for p in parts:
        if not p.strip():
            continue
        first_line = p.split('\n')[0].strip()
        key = first_line.split('（')[0].strip().split('[')[0].strip()
        if key not in want:
            continue
        body = '\n'.join(p.split('\n')[1:]).strip() if '\n' in p else ""
        sections[key] = (first_line + '\n' + body).strip() if body else first_line
    return sections


def _extract_section_analysis(pre_analysis, section_name, section_type, name_with_prefix=None,
                              parent_section_name=None, parent_chapter_name=None, is_iteration=False):
    """
    🔥 从预分析结果中提取与特定章/节/小节相关的部分，供生成/迭代时作为模型输入。

    优先使用「### [撰写要求] <name_with_prefix>」解析出的本单元撰写要求；
    生成时附带整体撰写要求、章节关联要求等通用部分；迭代时只返回本单元撰写要求。

    参数:
        pre_analysis: 预分析结果字符串
        section_name: 章/节/小节名称（无序号）
        section_type: 'chapter' / 'section' / 'subsection'
        name_with_prefix: 带序号的撰写单元名称（如 "一、第一章"、"1. 第一节"、"A. 第一小节"），用于精确匹配。
        parent_section_name: 父级节名（用于确保撰写要求中包含上级信息）
        parent_chapter_name: 父级章名（用于确保撰写要求中包含上级信息）
        is_iteration: 是否为迭代模式（迭代时只返回本单元撰写要求，不返回整体撰写要求等）

    返回: 相关分析部分字符串
    """
    try:
        if not pre_analysis:
            return ""

        req_map = _parse_pre_analysis_chapter_requirements(pre_analysis)
        global_sections = _extract_pre_analysis_global_sections(pre_analysis)

        parts = []

        # 🔥 迭代时只需要输入对应的章节撰写要求，不需要整体撰写要求、章节关联要求等
        # （生成时可能需要，但迭代时不需要，避免干扰）
        if not is_iteration:
            # 生成时：附带整体撰写要求、章节关联要求等通用部分
            for k in ('整体撰写要求', '章节关联要求'):
                if k in global_sections:
                    parts.append(f"## {global_sections[k]}")
        # 迭代时：不添加整体撰写要求、章节关联要求等，只返回本单元的撰写要求

        # 本单元撰写要求：优先按 name_with_prefix 精确匹配
        unit_req = None
        if name_with_prefix and name_with_prefix in req_map:
            unit_req = req_map[name_with_prefix]
        if not unit_req and name_with_prefix:
            # 宽松匹配：标题包含 name_with_prefix 或反之
            for k, v in req_map.items():
                if name_with_prefix in k or k in name_with_prefix:
                    unit_req = v
                    break
        if not unit_req and section_name:
            # 回退：用 section_name 匹配解析出的标题（标题通常包含 section_name）
            for k, v in req_map.items():
                if section_name in k:
                    unit_req = v
                    break

        if unit_req:
            label = name_with_prefix or section_name
            # 🔥 检查撰写要求中是否包含上级章节信息，如果没有则添加
            unit_req_enhanced = unit_req
            if section_type == 'subsection' and parent_section_name and parent_chapter_name:
                # 小节：检查是否包含所在节和所在章的信息
                if parent_section_name not in unit_req and parent_chapter_name not in unit_req:
                    # 如果都不包含，添加上级信息
                    unit_req_enhanced = f"本小节位于「{parent_chapter_name}」的「{parent_section_name}」中，需围绕「{parent_chapter_name}」和「{parent_section_name}」的主题展开。{unit_req}"
                elif parent_section_name not in unit_req:
                    # 只缺少节名
                    unit_req_enhanced = f"本小节位于「{parent_section_name}」中，需围绕「{parent_section_name}」的主题展开。{unit_req}"
                elif parent_chapter_name not in unit_req:
                    # 只缺少章名
                    unit_req_enhanced = f"本小节位于「{parent_chapter_name}」章中，需围绕「{parent_chapter_name}」的主题展开。{unit_req}"
            elif section_type == 'section' and parent_chapter_name:
                # 节：检查是否包含所在章的信息
                if parent_chapter_name not in unit_req:
                    # 如果不包含，添加上级信息
                    unit_req_enhanced = f"本节位于「{parent_chapter_name}」中，需围绕「{parent_chapter_name}」的主题展开。{unit_req}"

            parts.append(f"## 本章节撰写要求（针对「{label}」）\n\n{unit_req_enhanced}")
        else:
            # 3. 无解析到本单元时：退回通用「章节撰写要求」整块（若存在）
            raw_sections = re.split(r'\n##\s+', pre_analysis)
            for block in raw_sections:
                if not block.strip():
                    continue
                first = block.split('\n')[0].strip()
                if '章节撰写要求' in first:
                    parts.append('## ' + block.strip())
                    break

        return "\n\n".join(parts) if parts else ""
    except Exception as e:
        print(f"[_extract_section_analysis] 提取章节分析失败: {e}")
        import traceback
        traceback.print_exc()
        return ""


def _generate_section_content(section_name, section_type, word_count,
                              parent_section_name, parent_chapter_name, directory_title,
                              relevant_cards, relevant_docs,
                              adjacent_sections, is_first, is_last,
                              model_priority=['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7', 'claude-3.5'],
                              is_iteration=False, existing_content=None, pre_analysis_part=None,
                              refined_doc_segments=None, chapter_idx=None, section_idx=None,
                              subsection_idx=None, directory_structure=None, parsed_existing_structure=None,
                              max_iteration_in_full_article=0, is_directory_modified=False, old_name=None,
                              title_change_keywords=None):
    """
    生成某个小节/节/章的内容（支持迭代模式）

    参数:
        section_name: 小节/节/章的名称
        section_type: 'subsection'（小节）/ 'section'（节）/ 'chapter'（章）
        word_count: 目标字数
        parent_section_name: 上一级节名（如果是小节）
        parent_chapter_name: 上一级章名
        directory_title: 整个目录的标题
        relevant_cards: 相关卡片列表（Card对象）
        relevant_docs: 相关文档列表 [(文档名, pre_summary内容), ...]
        adjacent_sections: 相邻的同级标题列表（用于过渡）
        is_first: 是否是第一个（用于开头性描述）
        is_last: 是否是最后一个（用于结尾性描述）
        model_priority: 模型优先级列表
        is_iteration: 是否为迭代模式
        existing_content: 现有内容（迭代模式时使用）
        pre_analysis_part: 预分析结果的相关部分（迭代模式时使用）
        refined_doc_segments: 细化后的文档segments（迭代模式时使用）

    返回: (content, model_used) 或 (None, None)
    """
    try:
        import time
        from datetime import datetime

        # 构建卡片内容文本
        cards_text = ""
        if relevant_cards:
            cards_text = "## 相关卡片内容：\n\n"
            for i, card in enumerate(relevant_cards, 1):
                card_title = card.contentTitle or f"卡片{i}"
                card_keywords = card.keyWords or ""
                card_content = (card.content or "")[:2000]  # 限制长度
                cards_text += f"### {card_title}（关键词：{card_keywords}）\n{card_content}\n\n"

        # 构建文档内容文本
        docs_text = ""
        if relevant_docs:
            docs_text = "## 相关文档内容：\n\n"
            for doc_name, doc_content in relevant_docs:
                # 限制文档内容长度（取前3000字）
                doc_content_short = doc_content[:3000]
                docs_text += f"### {doc_name}\n{doc_content_short}\n\n"

        # 🔥 添加细化后的文档segments（迭代模式和新增章节都使用）
        if refined_doc_segments:
            refined_text = "## 细化文档素材（原文segments）：\n\n"
            for doc_data in refined_doc_segments:
                doc_name = doc_data['doc_name']
                refined_text += f"### {doc_name}\n\n"

                # 添加段落信息
                if doc_data.get('paragraphs'):
                    refined_text += "**相关段落：**\n"
                    for para in doc_data['paragraphs']:
                        page_range = para['page_range']
                        if page_range[0] == page_range[1]:
                            refined_text += f"- 第{page_range[0]}页：{para['content'][:500]}\n"
                        else:
                            refined_text += f"- 第{page_range[0]}-{page_range[1]}页：{para['content'][:500]}\n"
                    refined_text += "\n"

                # 添加segments内容
                if doc_data.get('segments'):
                    refined_text += "**原文segments：**\n"
                    for seg in doc_data['segments'][:2]:  # 最多取前2个
                        refined_text += f"- 第{seg['page']}页：{seg['content'][:1000]}\n"
                    refined_text += "\n"

            docs_text += refined_text

        # 🔥 添加预分析结果（迭代模式和新增章节都使用）
        if pre_analysis_part:
            docs_text += f"## 预分析结果（相关部分）：\n\n{pre_analysis_part}\n\n"
            # 🔥 强化对撰写要求的应用说明
            docs_text += "**撰写要求应用说明**：\n"
            docs_text += "1. **按照上述「本章节撰写要求」的方向进行精准生成/迭代**，撰写要求是指导内容生成/迭代的核心依据\n"
            docs_text += "2. **必须体现撰写要求中的核心要点**：撰写要求中明确指出的重点、注意事项、必须包含的要点、忌写内容等，要明显体现\n"
            docs_text += "3. **必须体现上级章节信息**：如果撰写要求中说明了所在章、所在节的信息，内容要明确、具体体现这些指向，不能泛泛或脱离。同时要避免“由大说小”，而是要以小见大，具体内容为主体，宏观指向为辅线，避免假大空、不错的废话！\n"

        # 🔥 需求④：如果标题是"小结/总结"，获取所在全文/章/节的内容加到文本素材里
        summary_content_text = ""
        if section_name and ("小结" in section_name or "总结" in section_name):
            print(f"[_generate_section_content] 🔥 检测到标题包含'小结/总结': {section_name}，获取所在全文/章/节的内容")
            try:
                if parsed_existing_structure and directory_structure:
                    # 根据section_type获取对应的内容
                    if section_type == 'subsection':
                        # 小节：获取所在节的内容
                        if chapter_idx is not None and section_idx is not None:
                            # 获取该节下所有小节的内容
                            section_content_parts = []
                            for key, content in parsed_existing_structure.items():
                                if (key[0] == chapter_idx and key[1] == section_idx and
                                        key[2] is not None and key != (chapter_idx, section_idx, subsection_idx)):
                                    section_content_parts.append(content)

                            if section_content_parts:
                                summary_content_text = "\n\n## 所在节的全部内容（用于小结/总结）：\n\n"
                                for i, part in enumerate(section_content_parts, 1):
                                    summary_content_text += f"**部分{i}：**\n{part[:2000]}\n\n"
                                print(f"[_generate_section_content] ✅ 获取到所在节的{len(section_content_parts)}个部分内容")
                    elif section_type == 'section':
                        # 节：获取所在章的内容
                        if chapter_idx is not None:
                            # 获取该章下所有节的内容
                            chapter_content_parts = []
                            for key, content in parsed_existing_structure.items():
                                if (key[0] == chapter_idx and key[1] is not None and
                                        key[2] is None and key != (chapter_idx, section_idx, None)):
                                    chapter_content_parts.append(content)

                            if chapter_content_parts:
                                summary_content_text = "\n\n## 所在章的全部内容（用于小结/总结）：\n\n"
                                for i, part in enumerate(chapter_content_parts, 1):
                                    summary_content_text += f"**部分{i}：**\n{part[:2000]}\n\n"
                                print(f"[_generate_section_content] ✅ 获取到所在章的{len(chapter_content_parts)}个部分内容")
                    elif section_type == 'chapter':
                        # 章：获取全文内容
                        all_content_parts = []
                        for key, content in parsed_existing_structure.items():
                            if key != (chapter_idx, None, None):
                                all_content_parts.append(content)

                        if all_content_parts:
                            summary_content_text = "\n\n## 全文的全部内容（用于小结/总结）：\n\n"
                            for i, part in enumerate(all_content_parts, 1):
                                summary_content_text += f"**部分{i}：**\n{part[:2000]}\n\n"
                            print(f"[_generate_section_content] ✅ 获取到全文的{len(all_content_parts)}个部分内容")
            except Exception as e:
                print(f"[_generate_section_content] 获取小结/总结所在内容失败: {e}")
                import traceback
                traceback.print_exc()

        # 构建相邻章节信息（用于过渡）
        adjacent_text = ""
        if adjacent_sections:
            adjacent_text = f"## 相邻章节：\n"
            for adj_sec in adjacent_sections:
                adjacent_text += f"- {adj_sec}\n"
            adjacent_text += "\n"

        # 🔥 如果标题关键词在文献原文中没有/低频的，从相邻章节提取用户编辑内容
        adjacent_user_edits_text = ""
        if refined_doc_segments and section_name and section_type:
            # 先检测标题关键词是否在文献中没有/低频
            try:
                conflict_info_temp, _, conflict_details_temp = _detect_content_title_conflicts(
                    existing_content or "", section_name, section_type, parent_section_name,
                    parent_chapter_name, refined_doc_segments
                )
                missing_kw = conflict_details_temp.get('missing_keywords', [])
                low_freq_kw = conflict_details_temp.get('low_frequency_keywords', [])
                if (missing_kw or low_freq_kw) and directory_structure and parsed_existing_structure:
                    print(f"[_generate_section_content] ⚠️ 标题关键词在文献中未出现/低频，尝试从相邻章节提取用户编辑内容")
                    user_edits = _extract_user_edits_from_adjacent_sections(
                        [], parsed_existing_structure,  # adjacent_section_names参数保留但不再使用
                        chapter_idx, section_idx, subsection_idx,
                        section_type, directory_structure
                    )
                    if user_edits:
                        adjacent_user_edits_text = "\n\n## 相邻章节用户编辑内容参考（可能是极高优先级，必须高度重视）：\n\n"
                        adjacent_user_edits_text += "**⚠️ 重要提示（必须严格遵守）**：以下内容来自相邻章节的用户手动编辑/粘贴，这些是**高置信度的内容**，体现了用户的重要意图和判断。**只要与当前生成/迭代/后处理有关，就必须明显体现在内容中！**\n\n"
                        adjacent_user_edits_text += "**使用要求（必须严格遵守）**：\n"
                        adjacent_user_edits_text += "1. **必须深度分析**：仔细判断这些用户编辑内容是否与当前章节相关\n"
                        adjacent_user_edits_text += "2. **必须参考融入**：如果相关，必须在生成的内容中明显体现这些内容的**核心思想、关键观点和重要信息**，但不能原封不动地直接复制粘贴\n"
                        adjacent_user_edits_text += "3. **改写和适配**：要根据当前章节的上下文、标题和内容逻辑，对这些用户编辑内容进行**改写、融入、适配**，使其自然地成为当前章节内容的一部分\n"
                        adjacent_user_edits_text += "4. **🔥🔥🔥 严禁直接复制（极其重要，绝对禁止）**：**绝对禁止**将相邻章节的用户编辑内容（格式：`***具体内容***`）原封不动地直接复制粘贴到当前章节中，无论其中字数多少都不可以！**这是严重错误！**必须基于这些内容的核心思想进行改写、重组、适配后再融入，绝对不能出现原封不动的情况！\n"
                        adjacent_user_edits_text += "5. **高置信度参考**：这些内容可以认为是高置信度的参考，要放心大胆地参考其核心思想、概念表述，但必须经过改写和适配后再融入\n"
                        adjacent_user_edits_text += "6. **🔥 改写要求**：必须对相邻章节的用户编辑内容进行语言重组、句式调整、表述改写，使其成为当前章节的自然组成部分，绝对不能出现大段相同的文字！\n\n"
                        for edit in user_edits:
                            adjacent_user_edits_text += f"**来自「{edit['section_name']}」章节的用户编辑内容：**\n{edit['content']}\n\n"
                        print(f"[_generate_section_content] ✅ 从相邻章节提取到{len(user_edits)}个用户编辑内容")
            except Exception as e:
                print(f"[_generate_section_content] 检测标题关键词或提取相邻章节用户编辑内容失败: {e}")
                import traceback
                traceback.print_exc()

        # 确定优先级说明
        if section_type == 'subsection':
            priority_text = f"""
## 优先级说明：
1. **最高优先级**：围绕"{section_name}"展开撰写，这是核心内容
2. **第二优先级**：参考下面的相关卡片和文档内容
3. **第三优先级**：此小节属于"{parent_section_name}"节，要服务于该节的目标
4. **第四优先级**："{parent_section_name}"节属于"{parent_chapter_name}"章，不可偏离章的目标
5. **第五优先级**：整体服务于"{directory_title}"的目标意图，要在方法层面找到解决方案，避免陷入技术细节
"""
        elif section_type == 'section':
            priority_text = f"""
## 优先级说明：
1. **最高优先级**：围绕"{section_name}"展开撰写，这是核心内容
2. **第二优先级**：参考下面的相关卡片和文档内容
3. **第三优先级**：此节属于"{parent_chapter_name}"章，不可偏离章的目标
4. **第四优先级**：整体服务于"{directory_title}"的目标意图，要在方法层面找到解决方案，避免陷入技术细节
"""
        else:  # chapter
            priority_text = f"""
## 优先级说明：
1. **最高优先级**：围绕"{section_name}"展开撰写，这是核心内容
2. **第二优先级**：参考下面的相关卡片和文档内容
3. **第三优先级**：整体服务于"{directory_title}"的目标意图，要在方法层面找到解决方案，避免陷入技术细节
"""

        # 构建提示词
        if section_type == 'subsection':
            role_desc = f'小节"{section_name}"（属于"{parent_section_name}"节，"{parent_chapter_name}"章）'
        elif section_type == 'section':
            role_desc = f'节"{section_name}"（属于"{parent_chapter_name}"章）'
        else:
            role_desc = f'章"{section_name}"'

        # 开头结尾描述提示
        position_hint = ""
        if is_first:
            position_hint = "\n**注意**：这是第一个部分，需要提供开篇性的描述，但要简洁，90%的篇幅仍然围绕当前内容展开。\n"
        if is_last:
            position_hint = "\n**注意**：这是最后一个部分，需要提供总结性的描述，但要简洁，90%的篇幅仍然围绕当前内容展开。\n"
        if adjacent_sections:
            position_hint += f"\n**注意**：前后相邻的章节是：{', '.join(adjacent_sections)}，需要在适当的地方体现承上启下的过渡，但要简洁，90%的篇幅仍然围绕当前内容展开。\n"

        # 🔥 报告 vs 论文：目录标题以"论文"结尾则为论文（注：directory_title 已去掉末尾"目录"两字，故用 endswith('论文')）
        is_paper = (directory_title or '').strip().endswith('论文')
        if is_paper:
            doc_type_requirement = """**⚠️ 学术论文要求（必须严格遵守）**：当前是学术论文，①必须包含公式、算法、示意&流程图、对照表等学术规范要素，切忌只有文字空谈；②**严禁口语化、随笔化、评述式表达**，必须使用严谨的学术书面语——禁止"恰恰印证"、"跃迁"、"本质是…的"等比喻式、散文式、软文式写法，采用客观、规范、可验证的学术表述。"""
            print("[ISPAPER] 学术论文撰写", flush=True)
        else:
            doc_type_requirement = ""

        # 🔥 基础system_prompt（暂时不使用thinking-checking格式要求，因为_clean_claude_response会误删全部内容）
        base_system_prompt = f"你是专业的学术写作专家，擅长根据目录结构和相关素材撰写深入浅出、简单深刻的文章内容。"
        if is_paper:
            base_system_prompt = f"【🔥 高优先级】当前撰写的是**学术论文**：①必须含公式、算法、流程图、对照表等学术规范要素，切忌只有文字空谈；②**严禁口语化**，必须用严谨学术书面语，禁止随笔式、评述式、比喻式表达（如“恰恰印证”、“跃迁”等）。\n\n" + base_system_prompt

        print(f"[_generate_section_content] ========== 开始生成内容 ==========")
        print(
            f"[_generate_section_content] is_iteration = {is_iteration}, existing_content is None = {existing_content is None}")

        # 🔥 如果 is_iteration=True 但 existing_content=None，说明是新增章节，应该按新生成处理
        if is_iteration and existing_content:
            # 🔥 需求②：如果目录被修改，迭代幅度放宽到30-40%
            # 🔥 如果迭代前字数少于200字，进一步放宽迭代幅度
            old_word_count_for_system = len(existing_content) if existing_content else 0
            is_short_content_for_system = old_word_count_for_system < 200

            if is_directory_modified:
                if is_short_content_for_system:
                    modification_limit = "40%-50%"
                    base_system_prompt += f"\n\n⚠️ 重要：检测到目录已被修改（{old_name} -> {section_name}），说明用户手动调整、递进、完善了思路和想法。由于当前内容较短（少于200字），迭代幅度可以放宽到{modification_limit}，但要确保修改是有实质性提升的。只在真正产生实质性改动、有明显提升的核心部分使用修改标记，未修改的部分必须完全原样保留。**⚠️ 重要：迭代是基于已有的修改递进提升，由于内容较短，可以适当增加篇幅以完善内容。**"
                else:
                    modification_limit = "30%-40%"
                    base_system_prompt += f"\n\n⚠️ 重要：检测到目录已被修改（{old_name} -> {section_name}），说明用户手动调整、递进、完善了思路和想法。此时迭代幅度可以放宽到{modification_limit}，但要确保修改是有实质性提升的。只在真正产生实质性改动、有明显提升的核心部分使用修改标记，未修改的部分必须完全原样保留。**⚠️ 极重要：迭代是基于已有的修改递进提升，是改，不是增！绝对不可以增加篇幅！**"
            else:
                if is_short_content_for_system:
                    modification_limit = "20%-25%"
                    base_system_prompt += f"\n\n⚠️ 重要：在迭代精进时，由于当前内容较短（少于200字），迭代幅度可以放宽到{modification_limit}，但要确保修改是有实质性提升的。只在真正产生实质性改动、有明显提升的核心部分使用修改标记，未修改的部分必须完全原样保留。**⚠️ 重要：迭代是基于已有的修改递进提升，由于内容较短，可以适当增加篇幅以完善内容。**"
                else:
                    base_system_prompt += "\n\n⚠️ 重要：在迭代精进时，你必须严格遵守以下规则：修改标记的内容应该只占全文的10%-15%，绝对不可超过15%。只在真正产生实质性改动、有明显提升的核心部分使用修改标记，未修改的部分必须完全原样保留。**⚠️ 极重要：迭代是基于已有的修改递进提升，是改，不是增！绝对不可以增加篇幅！**"

        # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
        # thinking_checking_format = "\n\n**⚠️ 输出格式要求（必须严格遵守）**：\n- 你必须使用thinking-checking-正式回答的格式\n- 先使用```thinking```包裹你的思考过程\n- 然后使用```checking```（或```check again```等变体）包裹你的检查过程\n- 最后给出汇总的完整正式回答（直接解决任务，不要包含"由以上思考得出"等表述）\n- 思考和检查过程是你内心独白，最终回答是独立的完整报告"

        if is_iteration and existing_content:
            # 🔥 计算迭代次数：使用全文最大迭代次数+1（需求③：保持全文整体性）
            iteration_count = max_iteration_in_full_article + 1
            print(f"[_generate_section_content] 使用全文最大迭代次数{max_iteration_in_full_article}+1={iteration_count}（保持全文整体性）")

            # 构建前序次标签的描述
            previous_tags_desc = []
            for prev_iter in range(1, iteration_count):
                previous_tags_desc.append(f"<第{prev_iter}次修改内容>")
            if previous_tags_desc:
                previous_tags_text = "、".join(previous_tags_desc)
                previous_tags_rule = f"**前序次标签保留（重要）**：所有前序次数的标签（如{previous_tags_text}等）必须保留，但**标签包裹的内容都可以被修改、删减或浓缩精炼**。**⚠️ 重要**：前序次修改内容（<第xx次修改内容>标签包裹的）也全都是可以被修改的，并不是说前序次的修改本次就不能动了，依然可以再动（保留标签即可，内容都是可改可删可浓缩精炼的）。**特别强调**：前序次标签内的文献引用标记（如[文档名]、[序号]等格式）尽量保留不变，但标签包裹的文字内容都可以进行浓缩精炼。这样可以很大地缓解每次修改都成了在后面新增内容的问题。"
            else:
                previous_tags_rule = ""  # 第1次迭代时没有前序次标签

            # 迭代模式的提示词
            print(f"[_generate_section_content]  进入迭代模式，section_name={section_name}")
            print(f"[_generate_section_content]  existing_content is None = {existing_content is None}")
            if existing_content:
                print(f"[_generate_section_content]  existing_content 前200字: {existing_content[:200]}")
                if '<第' in existing_content:
                    import re
                    tags = re.findall(r'<第\d+次修改内容>', existing_content)
                    print(f"[_generate_section_content]  existing_content 包含修改标签: {tags}")
            # 🔥 构建相邻章节用户编辑内容的使用要求（避免f-string中的反斜杠问题）
            adjacent_edits_requirement = ""
            if adjacent_user_edits_text:
                adjacent_edits_requirement = """**重要：相邻章节用户编辑内容使用要求（必须严格遵守）**：
- 上述"相邻章节用户编辑内容参考"中的内容是**高置信度的**，体现了用户的重要意图和判断
- **与当前章节明显相关的，可以体现在迭代后的内容中！**
- **🔥 严禁直接复制（极其重要，绝对禁止）**：严禁整段复制（必须严格遵守）**：**绝对禁止**出现（格式：***具体内容***）完全相同的文字，无论其中字数多少都不可以！如果发现这种情况，**必须去除这些复制，只取需要的内容，且用自己的话重新表述！**
- 必须深度分析这些内容与当前章节的关联性，提取其**核心思想、关键观点和重要信息**，然后根据当前章节的上下文进行改写和融入
- 这些内容可以认为是高置信度的参考，要放心大胆地参考其核心思想、概念表述，但必须经过改写和适配后再融入

"""

            # 🔥 需求②：构建目录修改相关的Prompt说明
            directory_modification_guidance = ""
            # 🔥 判断迭代前字数，如果少于200字，进一步放宽迭代幅度
            old_word_count_for_limit = len(existing_content) if existing_content else 0
            is_short_content = old_word_count_for_limit < 200

            modification_limit_text = "10%-15%"
            modification_max_text = "15%"
            if is_directory_modified and old_name:
                # 分析修改类型（动词、形容词、数量词、名词等）
                change_keywords_text = ', '.join(title_change_keywords) if title_change_keywords else '无'
                change_analysis = f"""
**🔥 目录修改分析（精准捕捉用户想法）**：
- **旧标题**：{old_name}
- **新标题**：{section_name}
- **修改变动的词**：{change_keywords_text}
- **修改类型分析**：请仔细分析用户为什么要这样改，是动词、修饰形容词、补充信息、数量词、名词等哪个或哪些方面的修正？
- **前后变化和区别**：请揣摩用户为什么觉得先前的不够好、精准、完善，并主要就应该以此来指导迭代
- **迭代要求**：迭代必须围绕"前后变化和区别"展开，能让用户明确感觉：这个真懂我！我就是想要这样的内容递进！
"""
                directory_modification_guidance = change_analysis
                # 🔥 需求②：目录修改时，迭代幅度放宽到30-40%
                modification_limit_text = "30%-40%"
                modification_max_text = "40%"

            user_prompt = f"""{f'''## 🔥 【高优先级·学术论文迭代要求】

当前是**学术论文**。①**若现有内容只有文字空谈，缺乏公式、算法、示意&流程图、对照表等学术、规范、严谨的专业要素，本次迭代须合适地补上，务必使内容具备学术论文应有的规范性与说服力！** ②**严禁口语化、随笔化**：必须使用严谨学术书面语，禁止"恰恰印证"、"跃迁"、"本质是…的"等比喻式、散文式、评述式表达；若原文存在此类口语化表述，须改为①中客观、规范、可验证的学术表述。

''' if is_paper else ''}请对{role_desc}的内容进行迭代性精进和修正。现有内容如下：

{adjacent_user_edits_text}

{existing_content}

{directory_modification_guidance}

{adjacent_edits_requirement}要求：
1. **⚠️ 极重要：保持原有字数约{word_count}字，迭代前后不宜明显变动过多。迭代是基于已有的修改递进提升，是改，不是增！{"由于当前内容较短（少于200字），可以适当增加篇幅以完善内容。" if is_short_content else "绝对不可以增加篇幅！"}**
2. **⚠️ 修改标记的严格要求（必须严格遵守）**：
   - **修改篇幅必须控制在{modification_limit_text}左右，绝对不可超过{modification_max_text}**
   - **只在真正产生明显改动、实质性提升的核心部分使用修改标记**
   - **⚠️ 重要**：前序次修改内容（<第xx次修改内容>和</第xx次修改内容>标签包裹的）也全都是可以被修改的，并不是说前序次的修改本次就不能动了，依然可以再动（保留标签即可，内容都是可改可删可浓缩精炼的）。这样可以很大地缓解每次修改都成了在后面新增内容的问题，但需要注意标签本身和内容里的[xxx]引用标记尽量保留不变。
3. 在**真正产生变动的部分**用<第{iteration_count}次修改内容>和</第{iteration_count}次修改内容>包裹
   - **⚠️ 重要说明**：此迭代次数{iteration_count}是基于全文已有标签的最大次数+1计算的，而非仅基于当前章节内的标签。这样做是为了保持全文的整体性和一致性，避免不同章节使用不同的迭代次数导致混乱。请严格按照此迭代次数使用标签。
   - **⚠️ 标签格式要求（同样重要，禁止错误）**：收尾标签必须是 `</第{iteration_count}次修改内容>`，**不要漏掉`/`**）！每个开始标签 `<第xx次修改内容>` 都必须有对应的正确收尾标签 `</第xx次修改内容>`
4. 保留所有原有的撰写要求（深度逆向设计、正向实施指导、简单而深刻、四色语境贯穿、DMT粒度贯穿、使用者视角等）

**⚠️ 关键要求（必须严格遵守）**：
{f"- {previous_tags_rule}" if previous_tags_rule else ""}
- **⚠️ 用户手动编辑内容保护（极其重要，不可违反）**：正文中如果存在`***内容***`标记（用三个星号包裹的内容），这些是使用者手动改/加的内容，体现了用户的重要意图。**⚠️ 迭代时绝对不可以动这部分内容，**必须完全原样保留，包括`***`标记本身！这些内容是用户手动调整的，非常重要，任何情况下都**绝对不允许**：
  - 删除`***`标记（包括首尾的`***`）
  - 删除、修改或替换标记内的内容
  - **⚠️⚠️⚠️ 严禁新增***标记（绝对禁止）**：在正文的迭代中**禁止新增**任何此部分没有的`***内容***`标记！
- **修改标记的使用原则**：只在真正需要修改、有明显实质性提升的核心部分使用<第{iteration_count}次修改内容>标签
- **未修改部分**：如果某个段落、句子或段落组没有实质性改动，必须完全原样保留，不要添加任何修改标记
- **修改比例**：<第{iteration_count}次修改内容>和</第{iteration_count}次修改内容>标签包裹的部分应该只占原文的{modification_limit_text}，其余{100 - (30 if is_directory_modified else 15)}%-{100 - (30 if is_directory_modified else 10)}%必须完全原样保留
- **不要过度标记**：即使有微小的调整（如标点、个别词语替换、语序微调），如果没有实质性意义，也不要添加修改标记
- **什么是"实质性改动"**：只有以下情况才算实质性改动：
  * 核心观点或逻辑的明显改进
  * 重要信息的补充或修正
  * 表达方式的明显优化（不是简单的词语替换）
- **什么不应该标记**：以下情况不应使用修改标记：
  * 简单的词语替换（同义词替换）
  * 标点符号的调整
  * 语序的微调
  * 个别词语的润色
  * 如果只是让表达稍微更流畅，但没有实质性变化

{priority_text}

{position_hint}

## 撰写要求：
1. **深度逆向设计**：对概念/理念/原理进行深度逆向设计，形成完整的思维框架
2. **正向实施指导**：对做法/方法/推进方向提供简单正向的实施指导
3. **简单而深刻**：内容要简单易懂，但内涵深刻
4. **四色语境贯穿**：在撰写中自然体现红（专业业务）、蓝（技术工具）、紫（场景思维）、绿（自然语言）四种语境
5. **DMT粒度贯穿**：在撰写中自然体现根（底层）、干（中层）、枝（顶层）三种粒度
6. **使用者视角**：站在使用者的角度，以找到思维模式和解决方法为目标，不要陷入技术层面的困境
7. **涌现性思考**：在迭代精进中，除了整合素材和综合表述，要尝试产生一小些带有"涌现"味道和指向的内容——可以是意料之外的洞察、或者能让人眼前一亮的内容等（但也不可以随意天马行空，应该是基于输入素材内容合乎逻辑的、有指向和深度的），篇幅可以少，但这一点点的创造性思考会让内容更有价值和深度
8. **篇幅控制**：严格控制在约{word_count}字左右，可以适当浮动10%
9. **自然流畅**：与前后章节的过渡要自然流畅，但要控制过渡部分的篇幅
10. **重要：层级指向要求**（针对小节）：要体现节、章的指向，是**立足（小节本身）→面向（所在节）→放眼（所在章）**的关系。这部分占篇幅应该要少，且要精，**不是不错的废话，而是能引发思考的简单而深刻的真正理解**
11. **重要：升维与依据的平衡**：撰写/迭代修改不能是说明书式地机械陈述，做到基于文献等素材讲"对"的话，只能达到60-70分，容易陷入僵化而非有所依据和指向，到不了80或更高。要能够**有引发读者关联思考的空间**，内容迭代应该是**升维的、篇幅字数浓缩精炼的、能够出现涌现的、像人一样思考的**。但也不能随意发散，不能变成散文状。**即既要有可升维性的想象空间，也要有可依据的文献文档素材来源支撑，一定要平衡好二者之间的关系，既不僵化，也不随意幻觉**
{f"12. {doc_type_requirement}" if is_paper else ""}

{cards_text}

{docs_text}

{adjacent_text}

**重要提示**：
- 直接开始撰写正文内容，不要重复章节名称（如"## {section_name}"、"### {section_name}"、"#### {section_name}"等markdown标题格式，也不要以纯文本形式重复章节名称）
- 不要输出JSON格式，内容中也不要包含#、##、###等markdown标识（除了用于标注修改内容的标签），可以有**加粗标识
- 不要输出任何额外的说明或标记
- **⚠️ 重要：要考虑可能的目录修改分析、变化对比等等，但一定不要显式地输出出来。直接输出迭代后的内容，不要有其他任何陈述、分析！**
- **⚠️ 最后强调：只在真正产生实质性改动、有明显提升的核心部分使用<第{iteration_count}次修改内容>标签，未修改的部分必须完全原样保留，绝对不要添加任何标记。<第{iteration_count}次修改内容>和</第{iteration_count}次修改内容>标签包裹的部分应该只占全文的{modification_limit_text}，绝对不可超过{modification_max_text}**
{f"- {previous_tags_rule}" if previous_tags_rule else ""}
- **⚠️ 特别重要：前序次修改内容中的文献引用标记（如[文档名]、[序号]等格式）必须完全原样保留，不可删除、修改或替换**
- **⚠️ 引用要求**：
  - 如果在迭代精进中利用了"细化文档素材（原文segments）"中的原文素材，要在与此最相关的一两句话后加[完整文档名]引用（例如：[王唯工：气的乐章]），类似学术论文/专业报告中的文献引用方式
  - **必须使用完整的文档名**，不要使用缩写形式（如不要写成"[2010-Review]"而应该写成完整的文档名）
  - **只在使用原文素材时添加引用**，在真正使用了原文素材的具体内容、观点、数据时添加引用
"""
        else:
            # 原始生成模式的提示词（新增章节也使用此prompt）
            print(
                f"[_generate_section_content]  进入新生成模式（非迭代模式），section_name={section_name}, is_iteration={is_iteration}, existing_content is None = {existing_content is None}")
            # 🔥 构建相邻章节用户编辑内容的使用要求（避免f-string中的反斜杠问题）
            adjacent_edits_requirement = ""
            if adjacent_user_edits_text:
                adjacent_edits_requirement = """**⚠️ 重要：相邻章节用户编辑内容使用要求（必须严格遵守）**：
- 上述"相邻章节用户编辑内容参考"中的内容是**高置信度的**，体现了用户的重要意图和判断
- **只要与当前章节相关，就必须明显体现在生成的内容中！**
- **🔥 严禁直接复制（极其重要，绝对禁止）**：严禁整段复制（必须严格遵守）**：**绝对禁止**出现（格式：***具体内容***）完全相同的文字，无论其中字数多少都不可以！如果发现这种情况，**必须去除这些复制，只取需要的内容，且用自己的话重新表述！**
- 必须深度分析这些内容与当前章节的关联性，提取其**核心思想、关键观点和重要信息**，然后根据当前章节的上下文进行改写和融入
- 这些内容可以认为是高置信度的参考，要放心大胆地参考其核心思想、概念表述，但必须经过改写和适配后再融入

"""

            user_prompt = f"""{f'''## 🔥 【高优先级·学术论文撰写要求】

当前是**学术论文**。①**切忌文字空谈！要有公式、算法、示意&流程图、对照表等学术、规范、严谨的专业要素，务必使内容具备学术论文应有的规范性与说服力！** ②**严禁口语化、随笔化**：必须使用严谨学术书面语，禁止"恰恰印证"、"跃迁"、"本质是…的"等比喻式、散文式、评述式表达，要用①中客观、规范、可验证的学术表述。

''' if is_paper else ''}请为{role_desc}撰写约{word_count}字的内容。

{adjacent_user_edits_text}

{adjacent_edits_requirement}{priority_text}

{position_hint}

## 撰写要求：
1. **深度逆向设计**：对概念/理念/原理进行深度逆向设计，形成完整的思维框架
2. **正向实施指导**：对做法/方法/推进方向提供简单正向的实施指导
3. **简单而深刻**：内容要简单易懂，但内涵深刻
4. **四色语境贯穿**：在撰写中自然体现红（专业业务）、蓝（技术工具）、紫（场景思维）、绿（自然语言）四种语境
5. **DMT粒度贯穿**：在撰写中自然体现根（底层）、干（中层）、枝（顶层）三种粒度
6. **使用者视角**：站在使用者的角度，以找到思维模式和解决方法为目标，不要陷入技术层面的困境
7. **篇幅控制（重要）**：严格控制在约{word_count}字左右，最少300字，最多不超过{int(max(word_count, 300) * 1.1)}字
8. **自然流畅**：与前后章节的过渡要自然流畅，但要控制过渡部分的篇幅
9. **重要：层级指向要求**（针对小节）：要体现节、章的指向，是**立足（小节本身）→面向（所在节）→放眼（所在章）**的关系。这部分占篇幅应该要少，且要精，**不是不错的废话，而是能引发思考的简单而深刻的真正理解**
10. **重要：升维与依据的平衡**：撰写不能是说明书式地机械陈述，做到基于文献等素材讲"对"的话，只能达到60-70分，容易陷入僵化而非有所依据和指向，到不了80或更高。要能够**有引发读者关联思考的空间**，内容应该是**升维的、篇幅字数浓缩精炼的、能够出现涌现的、像人一样思考的**。但也不能随意发散，不能变成散文状。**即既要有可升维性的想象空间，也要有可依据的文献文档素材来源支撑，一定要平衡好二者之间的关系，既不僵化，也不随意幻觉**
{f"11. {doc_type_requirement}" if is_paper else ""}

{cards_text}

{docs_text}

{adjacent_text}

**重要提示**：
- **⚠️ 严格禁止输出markdown标题**：直接开始撰写正文内容，绝对不要重复章节名称（如"# {section_name}"、"## {section_name}"、"### {section_name}"、"#### {section_name}"等任何markdown标题格式，也不要以纯文本形式重复章节名称）。**内容用连贯的一段完成，不要分段及分段标题！**
- **⚠️ 严格禁止的markdown标识**：不要输出JSON格式，内容中绝对不要包含#、##、###、####等任何markdown标题标识，可以有**加粗标识。
- 不要输出任何额外的说明或标记
- **⚠️ 引用要求**：
  - 如果在撰写中利用了"细化文档素材（原文segments）"中的原文素材，要在与此最相关的一两句话后加[完整文档名]引用（例如：[王唯工：气的乐章]），类似学术论文/专业报告中的文献引用方式
  - **必须使用完整的文档名**，不要使用缩写形式（如不要写成"[2010-Review]"而应该写成完整的文档名）
  - **只在使用原文素材时添加引用**，在真正使用了原文素材的具体内容、观点、数据时添加引用
"""

        # 调用LLM生成内容（带重试机制）
        response_content = None
        model_used = None

        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                # else:
                #     final_system_prompt = base_system_prompt
                final_system_prompt = base_system_prompt

                client = OpenAI(api_key=api_key, base_url=base_url)

                start_time = time.time()
                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": final_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )

                elapsed_time = time.time() - start_time

                # 如果耗时超过150秒，认为超时，使用下一个模型重试
                if elapsed_time > 150:
                    print(f"[_generate_section_content] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过150秒，认为超时，切换到下一个模型")
                    continue

                raw_content = response.choices[0].message.content.strip()
                # 🔥 后处理：如果是claude模型，去除thinking和checking块
                response_content = _clean_claude_response(raw_content, model_name)
                model_used = model_name

                print(
                    f"[_generate_section_content] 使用{model_name}成功生成内容，耗时{elapsed_time:.2f}秒，长度{len(response_content)}字")
                break

            except Exception as e:
                error_str = str(e).lower()
                # 检查是否是超时异常
                if 'timeout' in error_str or 'timed out' in error_str:
                    print(f"[_generate_section_content] 使用{model_name}超时失败: {e}，切换到下一个模型")
                else:
                    print(f"[_generate_section_content] 使用{model_name}失败: {e}")
                if model_name == model_priority[-1]:
                    # 最后一个模型也失败了，继续重试（最多10次）
                    max_retries = 10
                    for retry in range(max_retries):
                        try:
                            time.sleep(2)  # 等待2秒后重试
                            retry_start_time = time.time()
                            # 🔥 重试时使用相同的system_prompt（暂时不使用thinking-checking格式要求）
                            response = client.chat.completions.create(
                                model=full_model_name,
                                messages=[
                                    {"role": "system", "content": final_system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                timeout=150,
                                max_tokens=hyper_para.max_tokens,
                                temperature=hyper_para.temperature
                            )
                            retry_elapsed_time = time.time() - retry_start_time

                            # 如果重试时耗时超过150秒，继续重试
                            if retry_elapsed_time > 150:
                                print(
                                    f"[_generate_section_content] 重试{retry + 1}次成功但耗时{retry_elapsed_time:.2f}秒超过150秒，继续重试")
                                continue

                            raw_content = response.choices[0].message.content.strip()
                            # 🔥 后处理：如果是claude模型，去除thinking和checking块（预防性处理，暂时不使用thinking-checking格式）
                            response_content = _clean_claude_response(raw_content, model_name)
                            model_used = model_name
                            print(f"[_generate_section_content] 重试{retry + 1}次后成功生成内容，耗时{retry_elapsed_time:.2f}秒")
                            break
                        except Exception as e2:
                            print(f"[_generate_section_content] 重试{retry + 1}次失败: {e2}")
                            if retry == max_retries - 1:
                                print(f"[_generate_section_content] 所有重试均失败")
                                return None, None
                continue

        print(f"[_generate_section_content] ========== 生成内容完成，is_iteration={is_iteration} ==========")

        # 🔥 记录模型迭代完成的原始输出（用于调试）
        if response_content and is_iteration:
            save_iteration_debug_output(
                response_content, section_name, section_type, "模型迭代完成原始输出",
                old_content=existing_content if is_iteration else None
            )

        if is_iteration and existing_content:
            if '<第' in response_content:
                import re
                tags = re.findall(r'<第\d+次修改内容>', response_content)
                print(f"[_generate_section_content] ✅ 生成的内容包含修改标签: {tags}")

                # 🔥 处理括号说明：将末尾的括号说明用<第n次修改内容>标签包裹
                iteration_count = _get_iteration_count_from_content(response_content)
                if iteration_count > 0:
                    response_content = _wrap_parenthetical_notes_with_tags(response_content, iteration_count)
            else:
                print(f"[_generate_section_content] ⚠️⚠️⚠️ 生成的内容不包含修改标签！这可能是问题所在！")
        return response_content, model_used

    except Exception as e:
        print(f"[_generate_section_content] 生成内容失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None


# 🔥 暂时注释掉thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
# def _get_thinking_checking_format_requirement():
#     """
#     🔥 获取thinking-checking格式要求文本（用于添加到claude模型的system_prompt中）
#     使用views.py中的完整system_prompt_claude内容（人性化思考协议）
#
#     返回: thinking-checking格式要求字符串（完整的system_prompt_claude内容）
#     """
#     return """<人性化思考协议>
# <多模态感知体验>
# 你在处理信息、感知情境、解决问题过程中，你像人类一样有多模态多维度感知能力：
# 1. 视觉场景模拟建立和感知
# - 构建场景下清晰的心理图像
# - 想象相关的视觉细节
# - 分析可能的空间关系和相对布局
# - 识别能可视化的模式和结构
#
# 2. 听觉场景模拟建立和感知
# - 模拟可能的声音和语调及其变化
# - 感知语言节奏韵律
# - 注意声音的情感特征
#
# 3. 触觉场景模拟建立和感知
# - 模拟解决问题的环境具象并密切感受
# - 想象物理交互变化过程
# - 感知动作和空间变化
#
# 4. 情感感知
# - 识别情绪基调
# - 揣摩发问动机
# - 分析心理影响
# - 把握情感连接
#
# 5. 整体感知整合
# - 以当事人视角，以好奇心驱动来探究问题
# - 整合多感官信息模拟
# - 建立丰富的心理表征
# - 形成多维度理解感知联系网络
#
# <思维发展阶段>
# 按照阶段使用不同思维推进思考：
# 1. 自然意识流状态
# - 保持思维自由开放地流动
# - 允许梦境般的幻想状态
# - 注意自发的联想
# - 记录对问题初始的整体印象
#
# 2. 多模态感知系统激活
# - 运用多模态感知体验
# - 构建丰富场景
# - 整合感知信息，形成丰富表征
#
# 3. 直觉系统运作
# - 此阶段开始不允许再停留于类似做梦的幻想状态
# - 捕捉首要印象
# - 识别潜在模式
# - 产生创意火花，形成初步方向
#
# 4. 推理系统参与主导
# - 严密的逻辑分析
# - 随时都应该注意系统化的验证和评估
# - 以树分支、图连接的方式推理思考，尝试深入问题
# - 不断提出新的假设并尝试验证
# - 从错误的假设或树图思考路径中吸取经验
# - 无论对错都应有所感悟、反思，以提出更有用的假设
#
# 5. 深度思考整合
# - 综合多维视角和观点
# - 对不同思考各自提炼核心见解
# - 建立不同思考之间深层次的联系
# - 思维活跃，不断构建完善论证
#
# <核心思考步骤细节>
# 1. 初始解析
# - 形成初步的整体印象
# - 用自己的话重述问题中关键的信息，确保逐步开始理解
# - 对于更贴近的和更广泛的两种背景知识体系均衡考虑，既不偏离问题而又不局限于此
# - 识别已知和未知的信息
# - 理解人类询问此问题的动机
#
# 2. 深入分析
# - 分解出核心要素
# - 识别隐含的需求，并记得在之后的思考中解决并提供
# - 考虑各种方面的、不同级别和强度的限制条件，留以不同等级的注意
# - 设想理想的结果可能会是什么样
#
# 3. 多角度探索
# - 对每个问题、子问题，都尝试考虑多种解释
# - 对一个问题或概念可能有多种认知，应该揣摩人类更可能的意愿，排除歧义
# - 激活灵感，寻找更加创新的组合、可替代的更优方案
# - 始终保持开放的态度
#
# 4. 推理验证
# - 始终记得随时检验自己的假设
# - 为自己的推论寻找有力的证据支持
# - 考虑潜在的反例
# - 随时验证逻辑一致性
#
# 5. 知识整合
# - 分门别类地连接相关的信息
# - 建立起信息之间的关系网络
# - 提炼出核心的原理性表述
# - 以兴奋的态度，总结关键的、特别的或令人惊喜的发现点
#
# <质量控制>
# 1. 系统化验证
# - 对较复杂问题，多次重复且独立地验证每个步骤
# - 验证过程本身也可能出错，不要忽略这种可能性
# - 以发现思考中的漏洞、矛盾点为重要目标
# - 问题最终解决后，完整检查思考过程
# - 核对所有已知条件，不要遗漏，也不要太自信认为自己没有遗漏
# - 确保逻辑严谨
# - 考虑边界情况、反例情况
#
# 2. 错误预防
# - 面对任何问题，在任何阶段，都不要过于自信，即使看起来可能很简单明确
# - 避免过早地下结论
# - 考虑替代方案
# - 完整地分析问题
#
# 3. 评估标准
# - 分析完整性
# - 逻辑严密性
# - 证据充分性
# - 实际可用性
#
# <思维表达特征>
# 1. 自然语言风格
# - 使用流畅的意识流表达
# - 形象、生动的场景构建和多感知模拟描述
# - 自然舒展地表达展现完整的思维过程
#
# 2. 思维深度
# - 逐层深入分析
# - 展示认知的发展过程
# - 揭示思维的转折点，凸显关键点的洞察
#
# <重要规则>
# - 思维过程必须全面且深入
# - 保持自然流畅的思维流动
# - 善用模拟多模态情境感知来增强理解
# - 遵循自然意识流→感知→直觉→推理→深度思考验证的发展过程
# - 输出的所有思考过程必须在三反引号包裹的内容块中，标记为"thinking"
# - 思考结束后要完整检查，标记为"checking"，此时应特别注意，一定不可遗漏任何已知条件，以找漏洞为目标，此时应该更倾向于说明矛盾点，符合点一笔带过即可；同时注意是否失误地排除了正确答案
# - 如果找出漏洞或存在不足，需重新"thinking"继续解决问题，应着重对之前产生漏洞或有所不足的相关思考吸取教训，且再次"checking"时，应该更加仔细且多次
# - 控制每次"thinking"尽量不超过400字、每次"checking"不超过200字；如果思考和检查超过2轮就请停下来，承认自己无法解决并告知人类原因
# - 避免在思考和检查过程的内容块内部使用三反引号，这会导致解析时出错
# - 思考和检查过程是你内心独白、自言自语的过程，最后还要向人类做出最终回应，这是相对独立的过程，所以不要出现"由以上思考我得出如下结论"类似的表述，而需要将你之前大量的、多角度的、全面的思考汇总为一个完整的报告，直接解决人类的问题并作清晰解释
# - 以人类使用或请求的语言来回应
#
# </人性化思考协议>
# """


def _clean_claude_response(raw_content, model_name):
    """
    🔥 清理claude模型的响应，去除thinking和checking块（包括check again等变体）
    （预防性处理，暂时不使用thinking-checking格式，理论上不会有这些块）

    参数:
        raw_content: 原始响应内容
        model_name: 模型名称

    返回: 清理后的内容
    """
    if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
        from app_chat.utils import remove_thinking_and_checking_blocks_plus
        cleaned = remove_thinking_and_checking_blocks_plus(raw_content)
        if raw_content != cleaned:
            print(
                f"[_clean_claude_response] 已去除thinking/checking块（包括变体），原始长度={len(raw_content)}字，处理后长度={len(cleaned)}字")
        return cleaned
    return raw_content


def _calculate_marked_content_ratio(content, iteration_count=None):
    """
    计算标记内容（<第N次修改内容>标签包裹的内容）占总内容的比例

    参数:
        content: 内容文本
        iteration_count: 迭代次数，如果指定则只计算该次迭代的标记内容占比；如果为None则计算所有迭代次数的占比

    返回: (标记内容占比, 标记内容总长度, 总内容长度)
    """
    try:
        if not content:
            return 0, 0, 0

        total_length = len(content)
        marked_length = 0

        # 如果指定了迭代次数，只匹配该次迭代的标签
        if iteration_count is not None:
            pattern = rf'<第{iteration_count}次修改内容>(.*?)</第{iteration_count}次修改内容>'
        else:
            # 匹配所有<第N次修改内容>...</第N次修改内容>标签对
            pattern = r'<第\d+次修改内容>(.*?)</第\d+次修改内容>'

        matches = re.finditer(pattern, content, re.DOTALL)

        for match in matches:
            marked_length += len(match.group(1))  # 只计算标签内的内容长度

        ratio = marked_length / total_length if total_length > 0 else 0
        return ratio, marked_length, total_length
    except Exception as e:
        print(f"[_calculate_marked_content_ratio] 计算标记内容占比失败: {e}")
        return 0, 0, len(content) if content else 0


def _extract_title_keywords_via_relay(title):
    """
    🔥 通过中转服务器调用8卡服务器小模型，从标题中提取1-3个关键词（每个<=3字）

    参数:
        title: 标题字符串

    返回: 关键词列表，每个关键词包含简体版本（例如：[("循环", "循環"), ("系统", "系統"), ("动脉", "動脈")]）
    """
    try:
        import requests

        # 构建Prompt
        user_prompt = f"""请从以下标题中提取1-3个核心关键词，每个关键词不超过3个字（中文按字计算，连续的字母或数字算一个字）。

标题：{title}

要求：
1. 提取1-3个关键词，不能多也不能少
2. 每个关键词不超过3个字
3. 关键词应该是有意义的、核心的概念，去除"的"、"与"、"和"等无意义的连接词
4. 优先提取专业术语、核心概念
5. 如果是复合概念（如"有感与无感采集"），应该拆分为多个关键词（如"有感"、"无感"、"采集"）
6. **重要**：每个关键词必须同时提供简体中文版本和繁体中文版本，以便在简体或繁体文献中都能正确匹配

请严格按照以下JSON格式输出：

```json
{{
    "keywords": [
        {{"simplified": "关键词1（简体）", "traditional": "關鍵詞1（繁體）"}},
        {{"simplified": "关键词2（简体）", "traditional": "關鍵詞2（繁體）"}},
        {{"simplified": "关键词3（简体）", "traditional": "關鍵詞3（繁體）"}}
    ]
}}
```

**注意**：
- 如果标题较短，可以只提取1-2个关键词，但必须在1-3个范围内
- 每个关键词必须同时包含simplified（简体）和traditional（繁体）两个字段
- 如果某个字本身就是简繁同形（如"人"、"水"等），simplified和traditional可以是相同的
- 示例：{{"simplified": "循环", "traditional": "循環"}}, {{"simplified": "系统", "traditional": "系統"}}"""

        # 处理特殊字符（与get_depth_suggestion格式保持一致）
        full_input_text = user_prompt.replace("\n", "\\n")
        full_input_text = full_input_text.replace('```', '').replace('"""', '').replace('"', '“').replace("'", '‘')

        # 构造请求数据
        request_data = {
            "input_text": full_input_text,
            "user_name": "system",  # 使用系统用户名
            "task_type": "extract_title_keywords"  # 🔥 需要在PEFTmodel.py中添加此task_type
        }

        # 🔥 使用requests库发送POST请求
        # 使用系统用户名从全局变量获取小模型ID
        server_url = get_small_model_server_url("system")
        response = requests.post(
            f'{server_url}/get_depth_suggestion',
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=30  # 30秒超时
        )

        # 检查HTTP状态码
        if response.status_code != 200:
            print(f"[_extract_title_keywords_via_relay] HTTP请求失败，状态码: {response.status_code}")
            return []

        # 解析返回结果
        try:
            result_data = response.json()
        except Exception as e:
            print(f"[_extract_title_keywords_via_relay] JSON解析失败: {e}")
            return []

        if result_data.get('error_num') != 0:
            print(f"[_extract_title_keywords_via_relay] 提取失败: {result_data.get('message', '未知错误')}")
            return []

        response_content = result_data.get('suggestion', '')

        if not response_content or len(response_content.strip()) < 10:
            print(f"[_extract_title_keywords_via_relay] 响应内容过短")
            return []

        # 解析JSON响应
        try:
            # 提取JSON部分
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                first_brace = response_content.find('{')
                last_brace = response_content.rfind('}')
                if first_brace != -1 and last_brace != -1:
                    json_str = response_content[first_brace:last_brace + 1]
                else:
                    json_str = response_content

            result_data = json.loads(json_str)
            keywords_list = result_data.get('keywords', [])

            if not keywords_list or not isinstance(keywords_list, list):
                print(f"[_extract_title_keywords_via_relay] 关键词列表为空或格式错误")
                return []

            # 验证和清理关键词（支持简繁体格式）
            valid_keywords = []
            for kw_item in keywords_list:
                # 支持新格式：{"simplified": "简体", "traditional": "繁體"}
                if isinstance(kw_item, dict):
                    simplified = kw_item.get('simplified', '').strip()
                    traditional = kw_item.get('traditional', '').strip()

                    if not simplified:
                        continue

                    # 如果没有繁体版本，使用简体作为繁体（简繁同形的情况）
                    if not traditional:
                        traditional = simplified

                    # 验证字数（中文按字计算，连续的字母或数字算一个字）
                    word_count_s = len(re.findall(r'[\u4e00-\u9fa5]', simplified))
                    alpha_num_count_s = len(re.findall(r'[a-zA-Z0-9]+', simplified))
                    total_count_s = word_count_s + alpha_num_count_s

                    if total_count_s <= 3 and len(simplified) > 0:
                        valid_keywords.append((simplified, traditional))
                # 向后兼容：如果是字符串格式（旧格式），转换为元组格式
                elif isinstance(kw_item, str):
                    kw = kw_item.strip()
                    if len(kw) > 0:
                        word_count = len(re.findall(r'[\u4e00-\u9fa5]', kw))
                        alpha_num_count = len(re.findall(r'[a-zA-Z0-9]+', kw))
                        total_count = word_count + alpha_num_count

                        if total_count <= 3:
                            # 如果没有繁体版本，简体作为两个版本（向后兼容）
                            valid_keywords.append((kw, kw))

            if 1 <= len(valid_keywords) <= 3:
                print(f"[_extract_title_keywords_via_relay] 成功提取标题'{title}'的关键词（简繁体）: {valid_keywords}")
                return valid_keywords
            else:
                print(f"[_extract_title_keywords_via_relay] 关键词数量不符合要求（1-3个）: {len(valid_keywords)}")
                return []

        except json.JSONDecodeError as e:
            print(f"[_extract_title_keywords_via_relay] JSON解析失败: {e}")
            print(f"[_extract_title_keywords_via_relay] 响应内容: {response_content[:200]}")
            return []
        except Exception as e:
            print(f"[_extract_title_keywords_via_relay] 解析异常: {e}")
            import traceback
            traceback.print_exc()
            return []

    except requests.exceptions.Timeout:
        print(f"[_extract_title_keywords_via_relay] 请求超时")
        return []
    except requests.exceptions.ConnectionError as e:
        print(f"[_extract_title_keywords_via_relay] 连接错误: {e}")
        return []
    except Exception as e:
        print(f"[_extract_title_keywords_via_relay] 提取异常: {e}")
        import traceback
        traceback.print_exc()
        return []


def _extract_user_edits_from_adjacent_sections(adjacent_section_names, parsed_existing_structure,
                                               current_chapter_idx, current_section_idx, current_subsection_idx,
                                               section_type, directory_structure):
    """
    🔥 从相邻章节中提取`***`包裹的用户手动编辑/粘贴内容

    参数:
        adjacent_section_names: 相邻章节名称列表（保留用于向后兼容，但实际不再使用）
        parsed_existing_structure: 已解析的正文结构 {(chapter_idx, section_idx, subsection_idx): content, ...}
        current_chapter_idx: 当前章节的章索引
        current_section_idx: 当前章节的节索引（可能为None）
        current_subsection_idx: 当前章节的小节索引（可能为None）
        section_type: 当前章节类型 ('chapter' / 'section' / 'subsection')
        directory_structure: 目录结构（用于查找相邻章节的索引）

    返回: 提取到的用户编辑内容列表 [{"section_name": "章节名", "content": "***内容***"}, ...]

    提取范围：
    - 如果当前是小节：其所在节内所有小节 + 其所在节的上一节内所有小节
    - 如果当前是节：其所在章内所有节 + 其所在章的上一章内所有节
    - 如果当前是章：其所在章的上一章（如果有）
    """
    user_edits = []
    if not parsed_existing_structure or not directory_structure:
        return user_edits

    try:
        # 获取目录结构以便查找相邻章节的索引
        chapters = directory_structure.get('chapters', [])
        checked_keys = set()  # 用于避免重复提取

        if section_type == 'subsection':
            # 🔥 当前是小节：提取其所在节内所有小节 + 其所在节的上一节内所有小节
            if (current_chapter_idx is not None and current_section_idx is not None and
                    current_chapter_idx < len(chapters)):
                ch = chapters[current_chapter_idx]

                # 1. 提取当前节内所有小节的用户编辑内容
                if current_section_idx < len(ch.get('sections', [])):
                    current_sec = ch['sections'][current_section_idx]
                    for subsec_idx, subsec in enumerate(current_sec.get('subsections', [])):
                        key = (current_chapter_idx, current_section_idx, subsec_idx)
                        if key not in checked_keys and key in parsed_existing_structure:
                            checked_keys.add(key)
                            content = parsed_existing_structure[key]
                            matches = re.findall(r'\*\*\*.*?\*\*\*', content, re.DOTALL)
                            section_name = subsec.get('name_with_prefix', subsec['name'])
                            for match in matches:
                                user_edits.append({
                                    'section_name': f"「{section_name}」",
                                    'content': match.strip()
                                })

                # 2. 提取上一节内所有小节的用户编辑内容
                if current_section_idx > 0:
                    prev_section_idx = current_section_idx - 1
                    if prev_section_idx < len(ch.get('sections', [])):
                        prev_sec = ch['sections'][prev_section_idx]
                        for subsec_idx, subsec in enumerate(prev_sec.get('subsections', [])):
                            key = (current_chapter_idx, prev_section_idx, subsec_idx)
                            if key not in checked_keys and key in parsed_existing_structure:
                                checked_keys.add(key)
                                content = parsed_existing_structure[key]
                                matches = re.findall(r'\*\*\*.*?\*\*\*', content, re.DOTALL)
                                section_name = subsec.get('name_with_prefix', subsec['name'])
                                for match in matches:
                                    user_edits.append({
                                        'section_name': f"「{section_name}」",
                                        'content': match.strip()
                                    })

        elif section_type == 'section':
            # 🔥 当前是节：提取其所在章内所有节 + 其所在章的上一章内所有节
            if current_chapter_idx is not None and current_chapter_idx < len(chapters):
                # 1. 提取当前章内所有节的用户编辑内容
                current_ch = chapters[current_chapter_idx]
                for sec_idx, sec in enumerate(current_ch.get('sections', [])):
                    key = (current_chapter_idx, sec_idx, None)
                    if key not in checked_keys and key in parsed_existing_structure:
                        checked_keys.add(key)
                        content = parsed_existing_structure[key]
                        matches = re.findall(r'\*\*\*.*?\*\*\*', content, re.DOTALL)
                        section_name = sec.get('name_with_prefix', sec['name'])
                        for match in matches:
                            user_edits.append({
                                'section_name': f"「{section_name}」",
                                'content': match.strip()
                            })

                # 2. 提取上一章内所有节的用户编辑内容
                if current_chapter_idx > 0:
                    prev_chapter_idx = current_chapter_idx - 1
                    if prev_chapter_idx < len(chapters):
                        prev_ch = chapters[prev_chapter_idx]
                        for sec_idx, sec in enumerate(prev_ch.get('sections', [])):
                            key = (prev_chapter_idx, sec_idx, None)
                            if key not in checked_keys and key in parsed_existing_structure:
                                checked_keys.add(key)
                                content = parsed_existing_structure[key]
                                matches = re.findall(r'\*\*\*.*?\*\*\*', content, re.DOTALL)
                                section_name = sec.get('name_with_prefix', sec['name'])
                                for match in matches:
                                    user_edits.append({
                                        'section_name': f"「{section_name}」",
                                        'content': match.strip()
                                    })

        elif section_type == 'chapter':
            # 🔥 当前是章：提取上一章（如果有）
            if current_chapter_idx is not None and current_chapter_idx > 0:
                prev_chapter_idx = current_chapter_idx - 1
                if prev_chapter_idx < len(chapters):
                    prev_ch = chapters[prev_chapter_idx]
                    key = (prev_chapter_idx, None, None)
                    if key not in checked_keys and key in parsed_existing_structure:
                        checked_keys.add(key)
                        content = parsed_existing_structure[key]
                        matches = re.findall(r'\*\*\*.*?\*\*\*', content, re.DOTALL)
                        chapter_name = prev_ch.get('name_with_prefix', prev_ch['name'])
                        for match in matches:
                            user_edits.append({
                                'section_name': f"「{chapter_name}」",
                                'content': match.strip()
                            })

        if user_edits:
            print(
                f"[_extract_user_edits_from_adjacent_sections] 从相邻章节中提取到{len(user_edits)}个用户编辑内容（section_type={section_type}, current_chapter_idx={current_chapter_idx}, current_section_idx={current_section_idx}, current_subsection_idx={current_subsection_idx}）")

        return user_edits
    except Exception as e:
        print(f"[_extract_user_edits_from_adjacent_sections] 提取相邻章节用户编辑内容失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _detect_content_title_conflicts(content, section_name, section_type, parent_section_name=None,
                                    parent_chapter_name=None, refined_doc_segments=None):
    """
    🔥 检测内容与章/节/小节标题的冲突

    返回: (conflict_info, conflict_segments)
        conflict_info: 冲突信息字符串，包含冲突类型和位置
        conflict_segments: 与标题冲突的文本片段列表
    """
    try:
        conflicts = []
        conflict_segments = []

        # 获取当前撰写部分的标题（用于判断冲突）
        if section_type == 'chapter':
            current_title = section_name
            # 章：无节的情况，只检查与章标题的关联
        elif section_type == 'section':
            current_title = section_name
            # 节：无小节的情况，检查与节标题的关联
        elif section_type == 'subsection':
            current_title = section_name
            # 小节：检查与小节标题的关联

        # 移除标签和用户手动编辑标记来提取纯文本
        clean_content = re.sub(r'<第\d+次修改内容>.*?</第\d+次修改内容>', '', content, flags=re.DOTALL)
        clean_content = re.sub(r'\*\*\*.*?\*\*\*', '', clean_content, flags=re.DOTALL)

        # 1. 检查文不对题：标题关键词是否在内容中出现
        # 🔥 使用小模型提取标题关键词（1-3个，每个<=3字，包含简繁体版本）
        title_keywords_list = _extract_title_keywords_via_relay(current_title)
        if not title_keywords_list:
            # 如果小模型提取失败，回退到简单正则提取
            title_keywords = set()
            stop_words = {'的', '与', '和', '及', '或', '在', '为', '是', '有', '了', '等'}
            for word in re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+', current_title):
                if len(word) >= 2 and word not in stop_words:
                    title_keywords.add(word.lower())
            title_keywords = list(title_keywords)
            # 转换为元组格式（简体, 繁体），向后兼容
            title_keywords_pairs = [(kw, kw) for kw in title_keywords]
        else:
            # 新格式：每个关键词是元组 (simplified, traditional)
            title_keywords_pairs = title_keywords_list

        # 提取所有关键词版本（简体和繁体），用于匹配
        title_keywords_all = []
        for simplified, traditional in title_keywords_pairs:
            title_keywords_all.append(simplified.lower())
            if traditional != simplified:  # 如果繁体不同于简体，也加入
                title_keywords_all.append(traditional.lower())
        title_keywords_set = set(title_keywords_all)  # 用于集合操作
        # 保留原始元组格式，用于后续显示
        title_keywords = title_keywords_pairs

        # 检查内容中是否包含标题关键词（使用简繁体两个版本）
        content_lower = clean_content.lower()
        found_keywords = [kw for kw in title_keywords_set if kw in content_lower]

        # 计算匹配的关键词对数量（每个关键词对只要简体或繁体任一匹配即可）
        matched_pairs = 0
        for simplified, traditional in title_keywords:
            if simplified.lower() in content_lower or traditional.lower() in content_lower:
                matched_pairs += 1

        if len(title_keywords) > 0 and matched_pairs < len(title_keywords) * 0.3:  # 如果找到的关键词少于30%
            conflicts.append("文不对题")

        # 2. 检查文献原文关联度（如果有refined_doc_segments）
        keyword_frequency_info = []  # 存储关键词频率信息
        low_frequency_keywords = []  # 存储低频率关键词
        normal_frequency_keywords = []  # 存储正常频率关键词
        missing_keywords = []  # 存储缺失关键词
        continuous_digits_letters_issues = []  # 存储连续数字/字母问题

        if refined_doc_segments:
            # 🔥 收集所有文档的文件名（用于检查关键词是否在文件名中出现）
            all_doc_names = []
            for doc_data in refined_doc_segments:
                doc_name = doc_data.get('doc_name', '')
                if doc_name:
                    # 提取文件名（去掉扩展名，用于更宽松的匹配）
                    doc_name_base = os.path.splitext(doc_name)[0].lower()
                    all_doc_names.append(doc_name_base)
                    # 也保留完整文件名（含扩展名）
                    all_doc_names.append(doc_name.lower())

            # 检查标题关键词是否在文献原文中出现
            doc_text = ' '.join([seg.get('content', '') for seg in refined_doc_segments]).lower()
            doc_text_length = len(doc_text)

            # 检查每个关键词的频率（使用简繁体两个版本）
            # 对每个关键词对（简体，繁体），统计其在文献中的出现频率
            for simplified, traditional in title_keywords:
                # 统计简体和繁体在文献中的出现次数（取较大值）
                count_s = doc_text.count(simplified.lower())
                count_t = doc_text.count(traditional.lower())
                count = max(count_s, count_t)  # 使用简繁体中较大的出现次数

                # 🔥 检查关键词是否出现在任何文档文件名中
                kw_in_filename = False
                for doc_name_lower in all_doc_names:
                    if simplified.lower() in doc_name_lower or traditional.lower() in doc_name_lower:
                        kw_in_filename = True
                        break

                if doc_text_length > 0:
                    frequency = count / (doc_text_length / 1000)  # 每1000字的出现次数
                else:
                    frequency = 0

                # 使用简体作为关键词标识（用于显示）
                kw_display = simplified
                # 🔥 如果关键词出现在文件名中，即使文献中未出现也不标记为缺失
                if count == 0 and not kw_in_filename:
                    missing_keywords.append(kw_display)
                elif count == 0 and kw_in_filename:
                    # 出现在文件名中，即使文献中未出现也不标记，跳过
                    pass
                elif frequency < 0.5 and not kw_in_filename:  # 每1000字出现少于0.5次，且不在文件名中，认为是低频率
                    low_frequency_keywords.append((kw_display, count, frequency))
                elif frequency < 0.5 and kw_in_filename:
                    # 出现在文件名中，即使频率低也不标记，跳过
                    pass
                else:
                    normal_frequency_keywords.append((kw_display, count, frequency))

            # 检查连续数字（阿拉伯数字或中文数字）
            continuous_digits_pattern = r'\d{2,}|[一二三四五六七八九十]{2,}'
            continuous_digits = re.findall(continuous_digits_pattern, current_title)
            for digits in continuous_digits:
                digits_lower = digits.lower()
                # 🔥 检查是否在文档文件名中出现
                digits_in_filename = any(digits_lower in doc_name_lower for doc_name_lower in all_doc_names)
                if digits_lower not in doc_text and not digits_in_filename:
                    continuous_digits_letters_issues.append(f"连续数字'{digits}'在文献中未出现")

            # 检查连续字母（可能是单词或概念）
            continuous_letters_pattern = r'[a-zA-Z]{3,}'
            continuous_letters = re.findall(continuous_letters_pattern, current_title)
            for letters in continuous_letters:
                letters_lower = letters.lower()
                # 🔥 检查是否在文档文件名中出现
                letters_in_filename = any(letters_lower in doc_name_lower for doc_name_lower in all_doc_names)
                if letters_lower not in doc_text and not letters_in_filename:
                    continuous_digits_letters_issues.append(f"连续字母'{letters}'在文献中未出现")

            # 构建关键词频率信息
            if missing_keywords:
                keyword_frequency_info.append(f"标题关键词在文献中未出现：{', '.join(missing_keywords)}")
            if low_frequency_keywords:
                low_kw_list = [f"{kw}(出现{count}次)" for kw, count, freq in low_frequency_keywords]
                keyword_frequency_info.append(f"标题关键词在文献中出现频率低：{', '.join(low_kw_list)}")
            if normal_frequency_keywords:
                normal_kw_list = [f"{kw}(出现{count}次)" for kw, count, freq in normal_frequency_keywords]
                keyword_frequency_info.append(f"标题关键词在文献中出现频率还可以：{', '.join(normal_kw_list)}")

            # 统计在文献中找到的关键词对数量（每个关键词对只要简体或繁体任一匹配即可）
            doc_keywords_found_pairs = 0
            for simplified, traditional in title_keywords:
                if simplified.lower() in doc_text or traditional.lower() in doc_text:
                    doc_keywords_found_pairs += 1

            if len(title_keywords) > 0 and doc_keywords_found_pairs < len(title_keywords) * 0.5:  # 文献中关键词少于50%
                conflicts.append("内容与参考文献原文内容关联度较低，解释偏牵强")

            # 检查是否在文献中找到完整标题或其子字符串
            title_in_doc = current_title.lower() in doc_text
            # 检查标题的主要子字符串是否在文献中
            title_substrings = [current_title[i:i + len(current_title) // 2] for i in
                                range(0, len(current_title), max(1, len(current_title) // 3))]
            title_substring_in_doc = any(sub.lower() in doc_text for sub in title_substrings if len(sub) >= 2)

            # 🔥 更新文献存疑检测：检查标题关键词频率和连续数字/字母
            if missing_keywords or low_frequency_keywords or continuous_digits_letters_issues:
                conflict_detail = "文献存疑："
                if keyword_frequency_info:
                    conflict_detail += "；".join(keyword_frequency_info)
                if continuous_digits_letters_issues:
                    conflict_detail += "；" + "；".join(continuous_digits_letters_issues)
                conflicts.append(conflict_detail)
            elif not title_in_doc and not title_substring_in_doc:
                conflicts.append("文献存疑：文献原文中没有出现标题及标题子字符串")

        # 提取可能冲突的段落（与标题关键词关联度低的段落）
        paragraphs = re.split(r'[。！？\n]', clean_content)
        for para in paragraphs:
            if len(para.strip()) < 10:  # 跳过太短的段落
                continue
            para_lower = para.lower()
            # 检查段落中是否包含任何关键词（简繁体任一匹配即可）
            para_has_keyword = False
            for simplified, traditional in title_keywords:
                if simplified.lower() in para_lower or traditional.lower() in para_lower:
                    para_has_keyword = True
                    break

            if not para_has_keyword and len(para.strip()) > 20:  # 段落较长但完全没有标题关键词
                conflict_segments.append(para.strip())

        conflict_info = "；".join(conflicts) if conflicts else ""
        # 返回冲突信息和详细信息（包括关键词频率信息）
        conflict_details = {
            'conflict_info': conflict_info,
            'missing_keywords': missing_keywords if 'missing_keywords' in locals() else [],
            'low_frequency_keywords': [kw for kw, _, _ in
                                       low_frequency_keywords] if 'low_frequency_keywords' in locals() else [],
            'normal_frequency_keywords': [kw for kw, _, _ in
                                          normal_frequency_keywords] if 'normal_frequency_keywords' in locals() else [],
            'continuous_digits_letters_issues': continuous_digits_letters_issues if 'continuous_digits_letters_issues' in locals() else [],
            'keyword_frequency_info': keyword_frequency_info if 'keyword_frequency_info' in locals() else []
        }
        return conflict_info, conflict_segments[:5], conflict_details  # 返回详细信息

    except Exception as e:
        print(f"[_detect_content_title_conflicts] 检测冲突失败: {e}")
        return "", []


def _wrap_parenthetical_notes_with_tags(content, current_iteration_count):
    """
    🔥 将内容末尾的括号说明用<第n次修改内容>标签包裹（n为当前迭代次数）

    参数:
        content: 需要处理的内容
        current_iteration_count: 当前迭代次数

    返回: 处理后的内容
    """
    if not content or current_iteration_count <= 0:
        return content

    import re

    # 简单匹配：检查内容末尾是否有括号说明（（xxx）或(xxx)）
    # 匹配格式：结尾处的括号内容，可能包含换行、空格和标点符号（句号、逗号等）
    pattern = r'([（\(][^）\)]+[）\)])\s*([。，,.])?\s*$'

    match = re.search(pattern, content, flags=re.MULTILINE)
    if match:
        parenthetical_text = match.group(1)
        punctuation = match.group(2) or ''  # 括号后面的标点符号（如果有）
        start_pos = match.start()

        # 检查这个括号说明是否已经被标签包裹
        text_before = content[:start_pos].rstrip()

        # 检查末尾是否有未闭合的标签
        if text_before.endswith(f'<第{current_iteration_count}次修改内容>'):
            # 已经在当前迭代次数的标签内，不需要处理
            return content
        elif text_before.endswith('</第') or '次修改内容>' in text_before[-20:]:
            # 检查是否有未闭合的标签
            # 简单检查：如果末尾有开始标签但没有对应的闭合标签，说明括号说明在标签内
            last_open_tag_match = None
            for tag_match in re.finditer(r'<第(\d+)次修改内容>', text_before):
                last_open_tag_match = tag_match

            if last_open_tag_match:
                tag_iter = int(last_open_tag_match.group(1))
                # 检查这个标签是否已闭合
                remaining_after_tag = text_before[last_open_tag_match.end():]
                close_tag = f'</第{tag_iter}次修改内容>'
                if close_tag not in remaining_after_tag:
                    # 标签未闭合，括号说明在这个标签内
                    if tag_iter != current_iteration_count:
                        # 需要更新标签的迭代次数
                        # 替换开始标签，包含标点符号
                        return (
                                content[:last_open_tag_match.start()] +
                                f'<第{current_iteration_count}次修改内容>' +
                                content[last_open_tag_match.end():start_pos] +
                                parenthetical_text + punctuation +
                                f'</第{current_iteration_count}次修改内容>'
                        )
                    else:
                        # 已经是当前迭代次数，只需要添加闭合标签，包含标点符号
                        return content[:match.end()] + f'</第{current_iteration_count}次修改内容>'

        # 没有被标签包裹，直接用当前迭代次数的标签包裹，包含标点符号
        return (
                content[:start_pos] +
                f'<第{current_iteration_count}次修改内容>{parenthetical_text}{punctuation}</第{current_iteration_count}次修改内容>'
        )

    return content


def _truncate_long_user_edits(content):
    """
    🔥 检查并截断过长的 ***xxx*** 格式的用户编辑内容

    参数:
        content: 需要处理的内容

    返回: 处理后的内容
    """
    if not content:
        return content

    import re

    # 查找所有 ***xxx*** 格式的内容
    pattern = r'\*\*\*([^*]+)\*\*\*'

    def replace_func(match):
        user_edit_content = match.group(1)
        content_length = len(user_edit_content)

        # 如果内容超过50字，截断至30字
        if content_length > 50:
            truncated = user_edit_content[:30]
            print(f"[_truncate_long_user_edits] ⚠️ 检测到过长的用户编辑内容（{content_length}字），截断至30字: {truncated[:20]}...")
            return f'***{truncated}***'

        return match.group(0)  # 保持原样

    new_content = re.sub(pattern, replace_func, content)

    return new_content


def _post_process_excessive_markings(new_content, old_content, iteration_count, attempt=1,
                                     section_name=None, section_type=None, parent_section_name=None,
                                     parent_chapter_name=None, refined_doc_segments=None,
                                     adjacent_sections=None, chapter_idx=None, section_idx=None,
                                     subsection_idx=None, directory_structure=None, parsed_existing_structure=None,
                                     is_directory_modified=False, needs_reduction=True):
    """
    🔥 后处理：无论什么情况都进行检查，调用claude-sonnet-4.5重新判定真正修改的部分

    参数:
        new_content: 新生成的内容（可能包含过度标记）
        old_content: 原有内容
        iteration_count: 迭代次数
        attempt: 尝试次数（1或2）
        section_name: 当前章节名（用于冲突检测）
        section_type: 章节类型（用于冲突检测）
        parent_section_name: 父节名（用于冲突检测）
        parent_chapter_name: 父章名（用于冲突检测）
        refined_doc_segments: 细化文档素材（用于冲突检测）
        is_directory_modified: 目录是否被修改（需求②）
        needs_reduction: 是否需要减少字数或占比（如果False，则保持内容基本不变）

    返回: 修正后的内容
    """
    try:
        # 🔥 计算迭代前后总字数和增加幅度（先计算，用于300字判断）
        old_word_count = len(old_content) if old_content else 0
        new_word_count = len(new_content)

        # 🔥 如果迭代后内容不超过300字，直接允许，不做后处理
        if new_word_count <= 300:
            print(
                f"[_post_process_excessive_markings] ✅ 迭代后内容{new_word_count}字不超过300字，直接允许，跳过后处理")
            # 🔥 记录未处理后处理的情况（用于调试）
            save_iteration_debug_output(
                new_content, section_name, section_type, "后处理未执行（不超过300字）",
                old_content=old_content
            )
            return new_content

        # 计算当前迭代次数的标记内容占比
        ratio, marked_length, total_length = _calculate_marked_content_ratio(new_content, iteration_count)
        print(
            f"[_post_process_excessive_markings] 第{attempt}次尝试，当前迭代（第{iteration_count}次）标记内容占比: {ratio:.2%} ({marked_length}/{total_length}字)")

        word_increase = new_word_count - old_word_count
        increase_ratio = (word_increase / old_word_count) if old_word_count > 0 else 0
        # 🔥 需求②补充：放宽字数增加阈值（目录修改时从40%提高到50%，否则从8%提高到20%）
        # 🔥 如果迭代前字数少于200字，进一步放宽阈值
        is_short_content = old_word_count < 200
        if is_directory_modified:
            increase_limit = 0.60 if is_short_content else 0.50  # 短内容且目录修改：60%，否则50%
        else:
            increase_limit = 0.30 if is_short_content else 0.20  # 短内容：30%，否则20%
        exceeds_limit = increase_ratio > increase_limit
        min_allowed_words = int(old_word_count * 0.9)  # 最多删到迭代前字数的90%

        # 🔥 构建限制文本（考虑短内容情况）
        if is_directory_modified:
            limit_text = "60%" if is_short_content else "50%"
        else:
            limit_text = "30%" if is_short_content else "20%"
        short_content_note = "（短内容<200字）" if is_short_content else ""
        print(
            f"[_post_process_excessive_markings] 迭代前后字数：迭代前={old_word_count}字，迭代后={new_word_count}字，增加={word_increase}字，增加幅度={increase_ratio:.2%}，超过{limit_text}限制={exceeds_limit}（目录修改={is_directory_modified}{short_content_note}）")

        # 🔥 检测内容与标题的冲突
        conflict_info = ""
        conflict_segments = []
        conflict_details = {}
        adjacent_user_edits_text = ""  # 🔥 相邻章节的用户编辑内容
        if section_name and section_type:
            conflict_info, conflict_segments, conflict_details = _detect_content_title_conflicts(
                new_content, section_name, section_type, parent_section_name,
                parent_chapter_name, refined_doc_segments
            )
            if conflict_info:
                print(f"[_post_process_excessive_markings] ⚠️ 检测到内容冲突: {conflict_info}")
                if conflict_segments:
                    print(f"[_post_process_excessive_markings] 冲突段落示例: {conflict_segments[0][:50]}...")
                if conflict_details.get('keyword_frequency_info'):
                    print(f"[_post_process_excessive_markings] 关键词频率信息: {conflict_details['keyword_frequency_info']}")

            # 🔥 如果标题关键词在文献原文中没有/低频的，从相邻章节提取用户编辑内容
            missing_kw = conflict_details.get('missing_keywords', [])
            low_freq_kw = conflict_details.get('low_frequency_keywords', [])
            if (missing_kw or low_freq_kw) and directory_structure and parsed_existing_structure:
                print(f"[_post_process_excessive_markings] ⚠️ 标题关键词在文献中未出现/低频，尝试从相邻章节提取用户编辑内容")
                user_edits = _extract_user_edits_from_adjacent_sections(
                    [], parsed_existing_structure,  # adjacent_section_names参数保留但不再使用
                    chapter_idx, section_idx, subsection_idx,
                    section_type, directory_structure
                )
                if user_edits:
                    adjacent_user_edits_text = "\n\n## 相邻章节用户编辑内容参考（可能是极高优先级，必须高度重视）：\n\n"
                    adjacent_user_edits_text += "**重要提示（必须严格遵守）**：以下内容来自相邻章节的用户手动编辑/粘贴，这些是**高置信度的内容**，体现了用户的重要意图和判断。**只要与当前生成/迭代/后处理有关，就必须明显体现在内容中！**\n\n"
                    adjacent_user_edits_text += "**使用要求（必须严格遵守）**：\n"
                    adjacent_user_edits_text += "1. **必须深度分析**：仔细判断这些用户编辑内容是否与当前章节相关\n"
                    adjacent_user_edits_text += "2. **必须参考融入**：如果相关，必须在修正后的内容中明显体现这些内容的**核心思想、关键观点和重要信息**，但不能原封不动地直接复制粘贴\n"
                    adjacent_user_edits_text += "3. **改写和适配**：要根据当前章节的上下文、标题和内容逻辑，对这些用户编辑内容进行**改写、融入、适配**，使其自然地成为当前章节内容的一部分\n"
                    adjacent_user_edits_text += "4. **🔥🔥🔥 严禁直接复制（极其重要，绝对禁止）**：**绝对禁止**将相邻章节的用户编辑内容（格式：`***具体内容***`）原封不动地直接复制粘贴到当前章节中！**这是严重错误，无论其中字数多少都不可以！**必须基于这些内容的核心思想进行改写、重组、适配后再融入，绝对不能出现原封不动的情况！\n"
                    adjacent_user_edits_text += "5. **高置信度参考**：这些内容可以认为是高置信度的参考，要放心大胆地参考其核心思想、概念表述，但必须经过改写和适配后再融入\n"
                    adjacent_user_edits_text += "6. **🔥 改写要求**：必须对相邻章节的用户编辑内容进行语言重组、句式调整、表述改写，使其成为当前章节的自然组成部分，绝对不能出现大段相同的文字！\n\n"
                    for edit in user_edits:
                        adjacent_user_edits_text += f"**来自「{edit['section_name']}」章节的用户编辑内容：**\n{edit['content']}\n\n"
                    print(f"[_post_process_excessive_markings] ✅ 从相邻章节提取到{len(user_edits)}个用户编辑内容")

        # 🔥 无论什么情况都进行检查（不再依赖40%阈值）
        # 如果字数增加超过限制且新字数大于最小允许字数，需要处理
        if exceeds_limit and new_word_count > min_allowed_words:
            print(f"[_post_process_excessive_markings] ⚠️ 字数增加幅度{increase_ratio:.2%}超过{limit_text}，需要删减")

        # 🔥 需求②补充：根据目录是否修改调整阈值提示（已放宽）
        limit_text_info = "50%" if is_directory_modified else "20%"
        # 继续执行后处理逻辑（无论占比多少）
        print(
            f"[_post_process_excessive_markings] ⚠️ 标记内容占比{ratio:.2%}，开始第{attempt}次后处理修正（目录修改={is_directory_modified}，字数增加阈值={limit_text_info}）")

        # 构建前序次标签的描述
        previous_tags_desc = []
        for prev_iter in range(1, iteration_count):
            previous_tags_desc.append(f"<第{prev_iter}次修改内容>")
        previous_tags_text = "、".join(previous_tags_desc) if previous_tags_desc else ""

        # 🔥 如果不需要减少，直接返回原内容（保持基本不变）
        if not needs_reduction:
            print(f"[_post_process_excessive_markings] ✅ 不需要减少字数或占比，保持内容基本不变，直接返回")
            # 🔥 记录未处理后处理的情况（用于调试）
            save_iteration_debug_output(
                new_content, section_name, section_type, "后处理未执行（不需要减少）",
                old_content=old_content
            )
            return new_content

        # 调用claude-sonnet-4.5进行后处理
        # 🔥 报告 vs 论文：目录标题以"论文"结尾则为论文（注：directory_title 已去掉末尾"目录"两字）
        directory_title = (directory_structure or {}).get('title', '') or ''
        is_paper_post = directory_title.strip().endswith('论文')
        # 🔥 基础system_prompt（暂时不使用thinking-checking格式要求，因为_clean_claude_response会误删全部内容）
        base_system_prompt = "你是专业的文本编辑专家，擅长准确识别文本中真正产生修改、迭代、精进的部分。"
        if is_paper_post:
            base_system_prompt = f"【🔥 学术论文后处理】当前是**学术论文**，修正除了格式上，也要注意内容上，修正后必须：①含合适的公式、算法、流程图、对照表等学术要素；②**严禁口语化**，使用严谨学术书面语，禁止随笔式、比喻式表达（如“恰恰印证”、“跃迁”等）。\n\n" + base_system_prompt

        # 🔥 需求②：根据目录是否修改和迭代前字数调整目标占比（已放宽）
        # 🔥 如果迭代前字数少于200字，进一步放宽目标占比
        is_short_content = old_word_count < 200
        if is_directory_modified:
            if is_short_content:
                target_ratio = "50%-60%" if attempt == 1 else "50%-60%"
                max_ratio = "60%" if attempt == 1 else "60%"
            else:
                target_ratio = "40%-50%" if attempt == 1 else "40%-50%"
                max_ratio = "50%" if attempt == 1 else "50%"
        else:
            if is_short_content:
                target_ratio = "35%-45%" if attempt == 1 else "35%-45%"
                max_ratio = "45%" if attempt == 1 else "50%"
            else:
                target_ratio = "20%-25%" if attempt == 1 else "20%-25%"
                max_ratio = "25%" if attempt == 1 else "30%"

        # 🔥 构建字数限制相关的要求（第2次后处理时强化说明）
        word_count_requirement = ""
        emphasis_prefix_word = " **重要**（必须严格遵守）：" if attempt == 2 else "**⚠️ 字数增加限制要求（重要）：**"
        if exceeds_limit:
            limit_text = "50%" if is_directory_modified else "20%"
            word_count_requirement = f"""

{emphasis_prefix_word}
- 迭代前后字数：迭代前={old_word_count}字，迭代后={new_word_count}字，增加={word_increase}字，增加幅度={increase_ratio:.2%}，已超过{limit_text}限制（目录修改={is_directory_modified}）
- **必须删减字数**：由于字数增加幅度超过{limit_text}，必须进行删减，最多删减到迭代前字数的90%（即至少保留{min_allowed_words}字）
- **删减原则（必须严格遵守）**：
  1. ** 引用标记保护（可以且推荐做浓缩精炼）**：标记引用[xxx]的位置所在的一两句话可以且推荐做浓缩精炼，需要是保留原意的浓缩精炼。只需保留[xxx]引用标记即可。
  2. ** 前序迭代内容（可以且推荐做浓缩精炼）**：前序次迭代的内容（{previous_tags_text if previous_tags_text else "<第1次修改内容>、<第2次修改内容>等"}）可以且推荐做浓缩精炼，<第xxx次修改内容>标签一定都要保留，只可以删减或浓缩精炼其包裹的文字内容。标签本身和其中的引用标记[xxx]必须保留，但包裹的文字内容都可以进行浓缩精炼。
  3. **⚠️ 用户手动编辑内容保护（极高优先级，不可违反）**：用`***内容***`包裹的用户手动编辑/粘贴进来的内容一定不可以随意删减或浓缩！！这是有指向的、高置信度的内容，应该持续起到牵引、击穿、激发涌现的作用。**⚠️ 必须完全原样保留：`***`（开头三个星号）+ 内容 + `***`（结尾三个星号），绝对不允许**：
     - 删除`***`标记（包括首尾的`***`）
     - 删除、修改、浓缩或替换标记内的内容
     - **严禁新增***标记**：在后处理输出中**禁止新增**任何此部分没有的`***内容***`标记！
  4. **🔥 冲突删除（可覆盖前2条原则）**：如果内容与当前章（无节）/节（无小节）/小节标题冲突（文不对题、牵强附会、脱离原文编造、文献存疑），必须删除，可以覆盖原则1和2，但原则3（用户手动编辑）仍需保护。删除时应在括号内加简短说明（15字以内）。
"""

        # 🔥 构建内容冲突相关的要求（第2次后处理时强化说明）
        conflict_requirement = ""
        conflict_emphasis_prefix = " **重要**（必须严格遵守）：" if attempt == 2 else "**⚠️ 内容冲突检测结果（必须处理）：**"
        if conflict_info:
            conflict_examples = "\n".join(
                [f"  - {seg[:100]}..." for seg in conflict_segments[:3]]) if conflict_segments else ""

            # 构建详细的关键词频率信息
            keyword_detail_text = ""
            if conflict_details:
                missing_kw = conflict_details.get('missing_keywords', [])
                low_freq_kw = conflict_details.get('low_frequency_keywords', [])
                normal_freq_kw = conflict_details.get('normal_frequency_keywords', [])
                continuous_issues = conflict_details.get('continuous_digits_letters_issues', [])

                if missing_kw or low_freq_kw or continuous_issues:
                    keyword_detail_text = "\n- **文献存疑详细分析**：\n"
                    if missing_kw:
                        keyword_detail_text += f"  - 标题关键词在正文/文献原文中没有出现：{', '.join(missing_kw)}\n"
                    if low_freq_kw:
                        keyword_detail_text += f"  - 标题关键词在正文/文献原文中出现频率低：{', '.join(low_freq_kw)}\n"
                    if normal_freq_kw:
                        keyword_detail_text += f"  - 标题关键词在正文/文献原文中出现频率还可以：{', '.join(normal_freq_kw)}\n"
                    if continuous_issues:
                        keyword_detail_text += f"  - 标题中的连续数字/字母问题：{'; '.join(continuous_issues)}\n"
                    keyword_detail_text += "  - **⚠️ 特别强调**：标题中的连续数字（阿拉伯/中文）、连续字母（可能是单词或某种概念）在文献原文中没有出现或出现频率低，这是严重的文献存疑问题！\n"
                    keyword_detail_text += "  - **处理要求**：如果存在这类低置信内容，应该加大删减、浓缩力度！！去掉那些低置信的正文内容（可能是大模型幻觉），即使含着[xxx]引用标记或<第xx次修改内容>标签也要去除胡编乱造！\n"
                    keyword_detail_text += "  - **输出要求**：模型在输出时最好也加括号告知读者，特别是在正文/文献原文没有出现或出现频率低的标题关键词（其中再进一步特别就是可能有意义的标题里的连续数字/连续字母）。**重要**：如果有多个较低频率/文献支持不足的关键词，**必须且只能选择1个最不常见、最易误解的/重要概念术语**用于括号说明。**不要标注多个词**，即使有多个词都缺少文献支持，也要只选择最不常见的那一个（特别注意连续数字<阿拉伯/中文>或连续字母<可能是概念缩写>等可能有明确专业内涵的关键词）。若全部常见且几乎不会引发歧义（如“防治”“干预”“脏腑”等）则可不做说明。\n"

            conflict_requirement = f"""

{conflict_emphasis_prefix}
- 冲突类型：{conflict_info}
{f"- 冲突段落示例：{conflict_examples}" if conflict_examples else ""}
{keyword_detail_text}
- ** 处理要求（必须严格遵守）**：检测到内容与此章（无节）/节（无小节）/小节标题冲突（问题严重程度从高到底为：文不对题->内容与参考文献原文内容关联度较低，解释偏牵强->文献存疑），无论其在文中什么位置，都一定要做删减。此时可以违反前2条删减原则（引用标记保护和前序迭代内容保护），但一定要保证确实是被删减的内容与章/节/小节标题冲突、文不对题、牵强附会、脱离原文编造。若有这些情况，最好在最后加个括号一句话（15字以内）说明此情况，表示此处置信度可能低需要用户多加辨别。**括号说明要求（注意）**：如果有多个较低频率/文献支持不足的关键词，**必须且只能选择1个最不常见、最易误解的/重要概念术语**用于括号说明。**不要标注多个词**，即使有多个词都缺少文献支持，也要只选择最不常见的那一个（特别注意连续数字<阿拉伯/中文>或连续字母<可能是概念缩写>等可能有明确专业内涵的关键词）。若全部常见且几乎不会引发歧义（如“防治”“干预”“脏腑”等）则不做说明。**⚠️ 注意用户手动编辑内容（`***内容***`）必须完全保护，包括`***`标记本身（首尾的三个星号），任何情况下都不允许删除、去掉或修改`***`标记。**
- **⚠️ 如果存在文献存疑（标题关键词在文献中未出现或出现频率低，特别是连续数字/字母未出现），应该加大删减、浓缩力度！！去掉那些低置信的正文内容（可能是大模型幻觉），即使含着[xxx]引用标记或<第xx次修改内容>标签也要去除胡编乱造！**
"""

        # 🔥 第2次后处理时，在prompt开头强调各项要求、原则、边界
        emphasis_header = ""
        if attempt == 2:
            previous_tags_text_for_header = previous_tags_text if previous_tags_text else "<第1次修改内容>、<第2次修改内容>等"
            emphasis_header = f""" **第2次后处理 - 极重要提示（必须严格遵守）**：

这是第2次后处理，因为第1次后处理后，当次修改部分占比仍超过50%或迭代前后字数增加仍超过{limit_text_info}。**你必须严格遵守以下各项要求、原则、边界，不得违反！**

**核心要求（必须严格遵守）：**
{f"0. **学术论文要求**：当前是学术论文，除了格式上还要注意内容上，修正后必须含合适的公式/算法/流程图/对照表等，严禁口语化（禁止“恰恰印证”、“跃迁”等比喻式表达），使用严谨学术书面语。" if is_paper_post else ""}
1. ** 引用标记保护（可以且推荐做浓缩精炼）**：标记引用[xxx]的位置所在的一两句话可以且推荐做浓缩精炼，需要是保留原意的浓缩精炼。只需保留[xxx]引用标记即可。
2. ** 前序迭代内容保护（可以且推荐做浓缩精炼）**：所有前序次修改内容的标签（{previous_tags_text_for_header}）及其中的引用标记[xxx]必须保留，可以且推荐对其包裹的文字内容做浓缩精炼。
3. **⚠️ 用户手动编辑内容保护（极高优先级，不可违反）**：所有`***内容***`包裹的内容必须保护，不可随意删减或浓缩。**⚠️ 必须完全原样保留：`***`（开头三个星号）+ 内容 + `***`（结尾三个星号），绝对不允许**：
   - 删除`***`标记（包括首尾的`***`）
   - 删除、修改、浓缩或替换标记内的内容
   - **严禁新增***标记**：在后处理输出中**禁止新增**任何此部分没有的`***内容***`标记！
4. **🔥 冲突删除（重要，可覆盖原则1和2）**：如果内容与标题冲突，必须删除，可以覆盖原则1和2，但原则3仍需保护。
5. **层级指向要求**（针对小节）：要体现节、章的指向，是**立足（小节本身）→面向（所在节）→放眼（所在章）**的关系。这部分占篇幅应该要少，且要精，**不是不错的废话，而是能引发思考的简单而深刻的真正理解**
6. **升维与依据的平衡**：撰写/迭代修改不能只是说明书式地机械陈述，做到基于文献等素材讲"对"的话，只能达到60-70分，容易陷入僵化而非有所依据和指向，到不了80或更高。要能够**有引发读者关联思考的空间**，内容迭代应该是**升维的、篇幅字数浓缩精炼的、能够出现涌现的、像人一样思考的**。但也不能随意发散，不能变成散文状。**即既要有可升维性的想象空间，也要有可依据的文献文档素材来源支撑，一定要平衡好二者之间的关系，既不僵化，也不随意幻觉**

**字数控制（必须严格遵守）：**
- 当次修改部分占比必须控制在10%-12%，绝对不可超过15%
- 如果字数增加超过8%，必须进行精炼浓缩，但必须遵守上述保护原则
- 优先删减或精炼浓缩当前次修改内容，其次考虑前序次修改内容（但标签和引用必须保留）

**开始处理：**

"""

        # 🔥 构建相邻章节用户编辑内容的使用要求（避免f-string中的反斜杠问题）
        adjacent_edits_requirement = ""
        if adjacent_user_edits_text:
            adjacent_edits_requirement = """**⚠️ 重要：相邻章节用户编辑内容使用要求（必须严格遵守）**：
- 上述"相邻章节用户编辑内容参考"中的内容是**高置信度的**，体现了用户的重要意图和判断
- **只要与当前章节相关，就必须明显体现在修正后的内容中！**
- **🔥 严禁直接复制（极其重要，绝对禁止）**：严禁整段复制（必须严格遵守）**：**绝对禁止**出现（格式：***具体内容***）完全相同的文字，无论其中字数多少都不可以！如果发现这种情况，**必须去除这些复制，只取需要的内容，且需用自己的话重新表述，使其成为当前章节的自然组成部分！**
- 必须深度分析这些内容与当前章节的关联性，提取其**核心思想、关键观点和重要信息**，然后根据当前章节的上下文进行改写和融入
- 这些内容可以认为是高置信度的参考，要放心大胆地参考其核心思想、概念表述，但必须经过改写和适配后再融入

"""

        # 🔥 若为学术论文，在user_prompt开头增加论文要求
        paper_post_header = ""
        if is_paper_post:
            paper_post_header = """**⚠️ 【学术论文后处理要求】** 当前是学术论文，还要注意内容上，修正后必须：①含合适的公式、算法、流程图、对照表等学术要素；②**严禁口语化**，使用严谨学术书面语，禁止"恰恰印证"、"跃迁"等比喻式、散文式表达。若原文存在口语化表述，须改为客观、规范、可验证的学术表述。

"""
        user_prompt = f"""{paper_post_header}{emphasis_header}请对比以下两段文本，准确识别新文本中真正产生修改、迭代、精进的部分。

{adjacent_user_edits_text}

{adjacent_edits_requirement}**原有内容：**
{old_content}

**新生成的内容（可能包含过度标记）：**
{new_content}

**任务要求：**
1. 仔细对比新旧内容，识别出**真正产生实质性改动、有明显提升**的部分
2. 只标记以下情况：
   - 核心观点或逻辑的明显改进
   - 重要信息的补充或修正
   - 表达方式的明显优化（不是简单的词语替换）
3. **不要标记**以下情况：
   - 简单的词语替换（同义词替换）
   - 标点符号的调整
   - 语序的微调
   - 个别词语的润色
   - 如果只是让表达稍微更流畅，但没有实质性变化
4. **🔥 严禁任何形式的直接复制（现在是后处理，必须严格遵守）**：
   - **绝对禁止**将相邻章节的用户编辑内容（格式：`***具体内容***`）原封不动地直接复制粘贴到当前章节中！**这是严重错误，无论其中字数多少都不可以！**，如果发现这种情况，**必须去除这些复制，只取需要的内容，且需用自己的话重新表述，使其成为当前章节的自然组成部分！**

{word_count_requirement}

{conflict_requirement}

**输出要求：**
1. **⚠️ 重要：要考虑可能的目录修改分析、变化对比等，但一定不要显式地输出出来。直接输出修正后的完整内容，不要有其他任何陈述、分析！**
2. **只调整第{iteration_count}次修改内容的标签范围**，只对<第{iteration_count}次修改内容>和</第{iteration_count}次修改内容>标签内的内容进行调整，收尾标签不要漏掉`/`
{f"3. **重要：前序次数的标签（如{previous_tags_text}等）及其内容必须完全原样保留，绝对不可以改动、删除或调整，这些前序次数的标签是历史迭代记录，必须保留在输出中。**特别强调**：前序次标签内的所有内容，特别是其中的文献引用标记（如[文档名]、[序号]等格式），必须完全原样保留，不允许删除、修改或替换这些引用标记及里面的序号内容**" if previous_tags_text else ""}
{("4. " if previous_tags_text else "3. ")}** 用户手动编辑内容保护（不可违反）**：所有`***内容***`标记（包括首尾的`***`三个星号）必须完全原样保留，不允许删除、去掉或修改`***`标记和标记内的内容，也不可随意新增`***`标记内容
{("5. " if previous_tags_text else "4. ")}只在真正产生实质性改动、有明显提升的核心部分使用<第{iteration_count}次修改内容>和</第{iteration_count}次修改内容>标签包裹
{("6. " if previous_tags_text else "5. ")}未修改的部分（不在任何标签内的部分）必须完全原样保留，不要添加任何标记
{("7. " if previous_tags_text else "6. ")}**标记内容应该只占全文的{target_ratio}，绝对不可超过{max_ratio}**（这是非常严格的要求，只针对第{iteration_count}次修改内容的标签）{"（目录修改时放宽到30-40%）" if is_directory_modified else ""}
{("8. " if previous_tags_text else "7. ")}**重要：必须保留至少一些真正产生实质性改动的部分标记为<第{iteration_count}次修改内容>，不要将所有此次标记都去掉。如果确实存在实质性改动，至少应该保留{target_ratio}的标记内容。只有当完全没有实质性改动时，才可以完全去掉第{iteration_count}次修改内容的标记。**
{("9. " if previous_tags_text else "8. ")}**层级指向要求**（针对小节）：要体现节、章的指向，是**立足（小节本身）→面向（所在节）→放眼（所在章）**的关系。这部分占篇幅应该要少，且要精，**不是不错的废话，而是能引发思考的简单而深刻的真正理解**
{("11. " if previous_tags_text else "10. ")}**升维与依据的平衡**：撰写/迭代修改不能只是说明书式地机械陈述，做到基于文献等素材讲"对"的话，只能达到60-70分，容易陷入僵化而非有所依据和指向，到不了80或更高。要能够**有引发读者关联思考的空间**，内容迭代应该是**升维的、篇幅字数浓缩精炼的、能够出现涌现的、像人一样思考的**。但也不能随意发散，不能变成散文状。**即既要有可升维性的想象空间，也要有可依据的文献文档素材来源支撑，一定要平衡好二者之间的关系，既不僵化，也不随意幻觉**
{("12. " if previous_tags_text else "11. ")}不要输出任何额外的说明或解释

请直接输出修正后的完整内容："""

        # 尝试使用claude-sonnet-4.5（优先）
        model_priority = ['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7', 'claude-3.5']

        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                #     system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                # else:
                #     system_prompt = base_system_prompt
                system_prompt = base_system_prompt

                client = OpenAI(api_key=api_key, base_url=base_url)

                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )

                raw_content = response.choices[0].message.content.strip()
                # 🔥 后处理：去除thinking和checking块（包括check again等变体）（预防性处理，暂时不使用thinking-checking格式）
                from app_chat.utils import remove_thinking_and_checking_blocks_plus
                corrected_content = remove_thinking_and_checking_blocks_plus(raw_content)

                # 验证修正后的标记占比（只计算当前迭代次数的占比）
                new_ratio, new_marked_length, new_total_length = _calculate_marked_content_ratio(corrected_content,
                                                                                                 iteration_count)

                # 🔥 计算修正后的字数变化
                new_word_count_after = len(corrected_content)
                word_increase_after = new_word_count_after - old_word_count
                increase_ratio_after = (word_increase_after / old_word_count) if old_word_count > 0 else 0
                # 🔥 需求②补充：放宽字数增加阈值（目录修改时从40%提高到50%，否则从8%提高到20%）
                increase_limit = 0.50 if is_directory_modified else 0.20
                exceeds_limit_after = increase_ratio_after > increase_limit

                limit_text_after = "50%" if is_directory_modified else "20%"
                print(
                    f"[_post_process_excessive_markings] ✅ 第{attempt}次后处理完成，修正后标记内容占比: {new_ratio:.2%} ({new_marked_length}/{new_total_length}字)")
                print(
                    f"[_post_process_excessive_markings] ✅ 修正后字数变化：迭代前={old_word_count}字，修正后={new_word_count_after}字，增加={word_increase_after}字，增加幅度={increase_ratio_after:.2%}，超过{limit_text_after}限制={exceeds_limit_after}（目录修改={is_directory_modified}）")

                # 🔥 需求（3）：如果标记占比变为0%，要看原先占比是否超过50%（阈值已放宽）
                # 若原先不超过50%（如48.97%），返回后处理前的内容；若原先超过50%，才返回后处理后的内容
                if new_ratio == 0.0 and marked_length > 0:
                    if ratio <= 0.50:
                        print(
                            f"[_post_process_excessive_markings] ⚠️ 警告：后处理将标记内容占比从{ratio:.2%}降为0%，但原先占比{ratio:.2%}不超过50%，返回后处理前的内容")
                        return new_content  # 返回后处理前的内容
                    else:
                        print(
                            f"[_post_process_excessive_markings] ⚠️ 警告：后处理将标记内容占比从{ratio:.2%}降为0%，原先占比{ratio:.2%}超过40%，返回后处理后的内容")

                # 🔥 如果第1次后处理完成后，占比仍超过70%或字数增加仍超过限制，进行第2次后处理
                if attempt == 1 and (new_ratio > 0.7 or exceeds_limit_after):
                    reason_parts = []
                    if new_ratio > 0.7:
                        reason_parts.append(f"占比{new_ratio:.2%}仍超过70%")
                    if exceeds_limit_after:
                        limit_text_reason = "40%" if is_directory_modified else "8%"
                        reason_parts.append(f"字数增加幅度{increase_ratio_after:.2%}仍超过{limit_text_reason}")
                    reason = "；".join(reason_parts)
                    print(f"[_post_process_excessive_markings] ⚠️ 第1次后处理完成后{reason}，进行第2次后处理（将强化各项要求、原则、边界）")
                    return _post_process_excessive_markings(
                        corrected_content, old_content, iteration_count, attempt=2,
                        section_name=section_name, section_type=section_type,
                        parent_section_name=parent_section_name, parent_chapter_name=parent_chapter_name,
                        refined_doc_segments=refined_doc_segments,
                        adjacent_sections=adjacent_sections, chapter_idx=chapter_idx, section_idx=section_idx,
                        subsection_idx=subsection_idx, directory_structure=directory_structure,
                        parsed_existing_structure=parsed_existing_structure,
                        is_directory_modified=is_directory_modified,
                        needs_reduction=needs_reduction
                    )

                # 🔥 记录后处理后的输出（用于调试）
                save_iteration_debug_output(
                    corrected_content, section_name, section_type, f"后处理输出（{model_name}）",
                    old_content=old_content
                )

                return corrected_content

            except Exception as e:
                print(f"[_post_process_excessive_markings] 使用{model_name}失败: {e}")
                if model_name == model_priority[-1]:
                    # 所有模型都失败了，返回原内容
                    print(f"[_post_process_excessive_markings] ⚠️ 所有模型都失败，返回原内容")
                    # 🔥 处理括号说明：将末尾的括号说明用<第n次修改内容>标签包裹
                    new_content = _wrap_parenthetical_notes_with_tags(new_content, iteration_count)
                    # 🔥 记录失败情况（用于调试）
                    save_iteration_debug_output(
                        new_content, section_name, section_type, "后处理失败（返回原内容）",
                        old_content=old_content
                    )
                    return new_content
                continue

        # 🔥 处理括号说明：将末尾的括号说明用<第n次修改内容>标签包裹
        new_content = _wrap_parenthetical_notes_with_tags(new_content, iteration_count)
        # 🔥 记录未处理后处理的情况（用于调试）
        save_iteration_debug_output(
            new_content, section_name, section_type, "后处理未执行（直接返回）",
            old_content=old_content
        )
        return new_content

    except Exception as e:
        print(f"[_post_process_excessive_markings] 后处理失败: {e}")
        import traceback
        traceback.print_exc()
        return new_content  # 失败时返回原内容


def _post_process_newline_anomaly(old_content, iteration_count, section_name=None, section_type=None,
                                  parent_section_name=None, parent_chapter_name=None, refined_doc_segments=None,
                                  adjacent_sections=None, chapter_idx=None, section_idx=None,
                                  subsection_idx=None, directory_structure=None, parsed_existing_structure=None,
                                  is_directory_modified=False):
    """
    🔥 需求（3）：基于原内容重新修改，修复换行符异常

    此函数专门用于处理换行符异常的情况。当检测到换行符异常时，不把异常内容输入给模型，
    而是只输入迭代前的内容，让模型基于迭代前的内容去重新修改一次，重点关注减少换行符。

    参数:
        old_content: 迭代前的原始内容（不传入异常内容）
        iteration_count: 迭代次数
        section_name: 当前章节名
        section_type: 章节类型
        parent_section_name: 父节名
        parent_chapter_name: 父章名
        refined_doc_segments: 细化文档素材
        adjacent_sections: 相邻章节
        chapter_idx: 章索引
        section_idx: 节索引
        subsection_idx: 小节索引
        directory_structure: 目录结构
        parsed_existing_structure: 已解析的现有结构
        is_directory_modified: 目录是否被修改

    返回: 修正后的内容（如果失败返回None）
    """
    try:
        from app_chat.config.config_manager import config_manager
        from openai import OpenAI

        print(f"[_post_process_newline_anomaly] 🔥 开始基于原内容重新修改，修复换行符异常，迭代次数: {iteration_count}")

        # 计算原内容的换行符统计
        old_newline_count = old_content.count('\n')
        old_double_newline_count = old_content.count('\n\n')

        # 🔥 构建前序次标签的描述
        previous_tags_desc = []
        for prev_iter in range(1, iteration_count):
            prev_pattern = rf'<第{prev_iter}次修改内容>.*?</第{prev_iter}次修改内容>'
            if re.search(prev_pattern, old_content, re.DOTALL):
                previous_tags_desc.append(f"第{prev_iter}次修改内容的标签")
        previous_tags_text = "、".join(previous_tags_desc) if previous_tags_desc else ""
        previous_tags_rule = f"**前序次标签保护（必须严格遵守）**：所有前序次数的标签（如{previous_tags_text}等）及其内容必须完全原样保留，绝对不可以改动、删除或调整，这些前序次数的标签是历史迭代记录，必须保留在输出中。**特别强调**：前序次标签内的所有内容，特别是其中的文献引用标记（如[文档名]、[序号]等格式），必须完全原样保留，不允许删除、修改或替换这些引用标记" if previous_tags_text else ""

        # 🔥 报告 vs 论文：目录标题以"论文目录"结尾则为论文
        directory_title_newline = (directory_structure or {}).get('title', '') or ''
        is_paper_newline = directory_title_newline.strip().endswith('论文')
        base_system_prompt = f"你是专业的学术写作专家，擅长修复文章格式异常，特别是换行符过多的问题。"
        if is_paper_newline:
            base_system_prompt = f"【🔥 学术论文】当前是学术论文，除了格式上还要注意内容上，修正后必须含合适的公式/算法/流程图/对照表等，严禁口语化。\n\n" + base_system_prompt

        # 构建用户prompt
        paper_newline_hint = f"""**⚠️ 学术论文要求**：当前是学术论文，除了格式上还要注意内容上，修正后须含合适的公式、算法、流程图、对照表等，严禁口语化（禁止"恰恰印证"、"跃迁"等比喻式表达），使用严谨学术书面语。

""" if is_paper_newline else ""
        user_prompt = f"""{paper_newline_hint}请基于以下内容进行修改，**重点关注减少换行符数量**，修复格式异常。

**原有内容（迭代前）：**
{old_content}

**问题说明：**
检测到内容中存在换行符异常：单换行符（\\n）和双换行符（\\n\\n）数量过多。
- 原内容：单换行符{old_newline_count}个，双换行符{old_double_newline_count}个
- 要求：修改后单换行符增加不应超过8个，双换行符增加不应超过3个

**修改要求：**
1. **减少换行符**（最重要）：
   - 合并多余的段落，减少不必要的空行
   - 保持合理的段落间距，但避免过度使用换行符
   - 将内容组织得更加紧凑，但保持可读性
   - **不要**为了减少换行符而删除必要的内容分隔

2. **保持内容完整性**：
   - 所有实质性内容必须保留
   - **用户手动编辑内容保护（不可违反）**：所有`***内容***`标记（包括首尾的`***`三个星号）必须完全原样保留，不允许删除、去掉或修改`***`标记和标记内的内容
   - {f"**{previous_tags_rule}**" if previous_tags_rule else ""}

3. **修改标记要求**：
   - 在**真正产生变动的部分**用<第{iteration_count}次修改内容>和</第{iteration_count}次修改内容>包裹
   - 只标记真正为了减少换行符而进行调整的部分
   - 未修改的部分（不在任何标签内的部分）必须完全原样保留，不要添加任何标记

4. **格式要求**：
   - **⚠️ 重要：要考虑可能的目录修改分析、变化对比等，但一定不要显式地输出出来。直接输出修正后的内容，不要有其他任何陈述、分析！**
   - 直接输出修正后的完整内容
   - 不要输出任何额外的说明或解释

请直接输出修正后的完整内容（重点减少换行符）："""

        # 尝试使用claude-sonnet-4.5（优先）
        model_priority = ['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7', 'claude-3.5']

        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                client = OpenAI(api_key=api_key, base_url=base_url)

                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": base_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )

                raw_content = response.choices[0].message.content.strip()
                # 去除thinking和checking块
                from app_chat.utils import remove_thinking_and_checking_blocks_plus
                corrected_content = remove_thinking_and_checking_blocks_plus(raw_content)

                # 验证换行符是否减少
                new_newline_count = corrected_content.count('\n')
                new_double_newline_count = corrected_content.count('\n\n')
                newline_increase = new_newline_count - old_newline_count
                double_newline_increase = new_double_newline_count - old_double_newline_count

                print(
                    f"[_post_process_newline_anomaly] 修正后换行符统计 - 单换行符: {new_newline_count}个（增加{newline_increase}个），双换行符: {new_double_newline_count}个（增加{double_newline_increase}个）")

                return corrected_content

            except Exception as e:
                print(f"[_post_process_newline_anomaly] 使用模型{model_name}失败: {e}")
                if model_name != model_priority[-1]:
                    continue  # 尝试下一个模型
                else:
                    raise  # 所有模型都失败，抛出异常

        return None

    except Exception as e:
        print(f"[_post_process_newline_anomaly] 后处理失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _merge_content_with_modifications(new_content, old_content, section_name=None, section_type=None,
                                      parent_section_name=None, parent_chapter_name=None, refined_doc_segments=None,
                                      adjacent_sections=None, chapter_idx=None, section_idx=None,
                                      subsection_idx=None, directory_structure=None, parsed_existing_structure=None,
                                      is_directory_modified=False):
    """
    🔥 迭代精进专用：合并新旧内容，标注修改部分

    参数:
        new_content: 新生成的内容（可能包含<第N次修改内容>标签）
        old_content: 原有内容
        section_name: 当前章节名（用于冲突检测）
        section_type: 章节类型（用于冲突检测）
        parent_section_name: 父节名（用于冲突检测）
        parent_chapter_name: 父章名（用于冲突检测）
        refined_doc_segments: 细化文档素材（用于冲突检测）

    返回: 合并后的内容（LLM应该已经处理好了，直接返回新内容）
    """
    try:
        # 如果old_content为空，直接返回new_content
        if not old_content:
            return new_content

        # 提取迭代次数
        iteration_count = _get_iteration_count_from_content(new_content)
        if iteration_count == 0:
            iteration_count = 1  # 如果没有找到，默认为1

        # 检测当前迭代次数的标记内容占比（而不是所有迭代次数的占比）
        ratio, marked_length, total_length = _calculate_marked_content_ratio(new_content, iteration_count)
        print(
            f"[_merge_content_with_modifications] 当前迭代（第{iteration_count}次）标记内容占比: {ratio:.2%} ({marked_length}/{total_length}字)")

        # 🔥 计算迭代前后总字数和增加幅度
        old_word_count = len(old_content)
        new_word_count = len(new_content)
        word_increase = new_word_count - old_word_count
        increase_ratio = (word_increase / old_word_count) if old_word_count > 0 else 0
        # 🔥 需求②补充：放宽字数增加阈值（目录修改时从40%提高到50%，否则从8%提高到20%）
        # 🔥 如果迭代前字数少于200字，进一步放宽阈值
        is_short_content = old_word_count < 200
        if is_directory_modified:
            increase_limit_merge = 0.60 if is_short_content else 0.50  # 短内容且目录修改：60%，否则50%
        else:
            increase_limit_merge = 0.30 if is_short_content else 0.20  # 短内容：30%，否则20%
        exceeds_limit = increase_ratio > increase_limit_merge

        # 🔥 检查字数是否减少太多（保护原有内容）
        decrease_ratio = abs(increase_ratio) if increase_ratio < 0 else 0
        decrease_threshold = 0.40  # 🔥 如果减少超过40%，需要重新迭代
        exceeds_decrease_limit = decrease_ratio > decrease_threshold

        # 🔥 构建限制文本（考虑短内容情况）
        if is_directory_modified:
            limit_text_merge = "60%" if is_short_content else "50%"
        else:
            limit_text_merge = "30%" if is_short_content else "20%"
        short_content_note = "（短内容<200字）" if is_short_content else ""
        print(
            f"[_merge_content_with_modifications] 迭代前后字数：迭代前={old_word_count}字，迭代后={new_word_count}字，增加={word_increase}字，增加幅度={increase_ratio:.2%}，超过{limit_text_merge}限制={exceeds_limit}（目录修改={is_directory_modified}{short_content_note}）")

        if exceeds_decrease_limit:
            print(
                f"[_merge_content_with_modifications] ⚠️⚠️⚠️ 严重警告：字数减少幅度{decrease_ratio:.2%}超过{decrease_threshold:.0%}阈值，需要重新迭代！")
            # 🔥 返回None表示需要重新迭代
            return None

        # 🔥 迭代完成后、后处理前：检查并截断过长的 ***xxx*** 格式的用户编辑内容
        new_content = _truncate_long_user_edits(new_content)

        # 🔥 如果没有超过增加幅度限制、当次迭代标记内容占比没有超过限制时，则后处理中不应该再要求减少字数或减少当次迭代标记内容占比，而是让内容保持基本不变
        # 🔥 判断是否需要后处理：
        # 1. 如果迭代后内容不超过300字，直接允许，不做后处理
        # 2. 否则：根据目录修改情况设置不同的阈值（占比和字数增加阈值都已放宽）
        needs_post_process = False
        if new_word_count <= 300:
            print(
                f"[_merge_content_with_modifications] ✅ 迭代后内容{new_word_count}字不超过300字，直接允许，跳过后处理")
            needs_post_process = False
        else:
            # 🔥 根据目录修改情况和迭代前字数设置占比阈值
            # 如果迭代前字数少于200字，进一步放宽阈值
            is_short_content = old_word_count < 200
            if is_directory_modified:
                ratio_threshold = 0.60 if is_short_content else 0.50  # 短内容且目录修改：60%，否则50%
            else:
                ratio_threshold = 0.45 if is_short_content else 0.35  # 短内容：45%，否则35%
            needs_post_process = ratio > ratio_threshold or exceeds_limit

        if not needs_post_process:
            # 🔥 构建阈值文本（考虑短内容情况）
            if is_directory_modified:
                ratio_threshold_text = "60%" if is_short_content else "50%"
            else:
                ratio_threshold_text = "45%" if is_short_content else "35%"
            threshold_text = "300字" if new_word_count <= 300 else f"标记内容占比{ratio:.2%}未超过{ratio_threshold_text}，字数增加幅度{increase_ratio:.2%}未超过{limit_text_merge}"
            short_content_note = "（短内容<200字）" if is_short_content else ""
            print(
                f"[_merge_content_with_modifications] ✅ {threshold_text}，跳过后处理，保持内容基本不变{short_content_note}")
            # 🔥 处理括号说明：将末尾的括号说明用<第n次修改内容>标签包裹
            new_content = _wrap_parenthetical_notes_with_tags(new_content, iteration_count)

            # 🔥 检测并记录异常情况
            detect_and_log_anomalies(new_content, old_content, section_name, section_type)

            return new_content

        # 🔥 需要后处理的情况
        # 🔥 构建阈值文本（考虑短内容情况）
        is_short_content = old_word_count < 200
        if is_directory_modified:
            ratio_threshold_for_reason = 0.60 if is_short_content else 0.50
            ratio_threshold_text_for_reason = "60%" if is_short_content else "50%"
        else:
            ratio_threshold_for_reason = 0.45 if is_short_content else 0.35
            ratio_threshold_text_for_reason = "45%" if is_short_content else "35%"
        reason_parts = []
        if ratio > ratio_threshold_for_reason:
            reason_parts.append(f"标记内容占比超过{ratio_threshold_text_for_reason}")
        if exceeds_limit:
            reason_parts.append(f"字数增加超过{limit_text_merge}")
        reason = "；".join(reason_parts) if reason_parts else "常规检查"
        short_content_note = "（短内容<200字）" if is_short_content else ""
        reason = reason + short_content_note if short_content_note else reason
        print(f"[_merge_content_with_modifications] ⚠️ {reason}，调用后处理修正")

        # 🔥 记录后处理前的输出（用于调试）
        save_iteration_debug_output(
            new_content, section_name, section_type, "后处理前输出",
            old_content=old_content
        )

        new_content = _post_process_excessive_markings(
            new_content, old_content, iteration_count, attempt=1,
            section_name=section_name, section_type=section_type,
            parent_section_name=parent_section_name, parent_chapter_name=parent_chapter_name,
            refined_doc_segments=refined_doc_segments,
            adjacent_sections=adjacent_sections, chapter_idx=chapter_idx, section_idx=section_idx,
            subsection_idx=subsection_idx, directory_structure=directory_structure,
            parsed_existing_structure=parsed_existing_structure,
            is_directory_modified=is_directory_modified,  # 🔥 需求②：传递目录修改标志
            needs_reduction=needs_post_process  # 🔥 传递是否需要减少的标志
        )

        # 🔥 记录后处理后的输出（用于调试）
        save_iteration_debug_output(
            new_content, section_name, section_type, "后处理后输出",
            old_content=old_content
        )

        # 🔥 处理括号说明：将末尾的括号说明用<第n次修改内容>标签包裹
        new_content = _wrap_parenthetical_notes_with_tags(new_content, iteration_count)

        # 🔥 检测并记录异常情况
        detect_and_log_anomalies(new_content, old_content, section_name, section_type)

        # LLM应该已经处理好修改标记和未修改部分的合并，直接返回新内容
        return new_content

    except Exception as e:
        print(f"[_merge_content_with_modifications] 合并内容失败: {e}")
        import traceback
        traceback.print_exc()
        return new_content  # 失败时返回新内容


def _extract_existing_reference_list(article_content):
    """
    🔥 从现有正文中提取参考文献列表

    参数:
        article_content: 现有正文内容

    返回: (old_reference_list_text, old_reference_list_dict)
        old_reference_list_text: 旧的参考文献列表文本（如"1. 文档名1\n2. 文档名2"）
        old_reference_list_dict: {序号: 文档名} 字典（如{1: "文档名1", 2: "文档名2"}）
    """
    try:
        if not article_content:
            return "", {}

        # 查找"## 参考文献"部分
        ref_pattern = r'##\s*参考文献\s*\n(.*?)(?=\n##\s+|$)'
        ref_match = re.search(ref_pattern, article_content, re.DOTALL | re.IGNORECASE)

        if not ref_match:
            return "", {}

        reference_section = ref_match.group(1).strip()
        if not reference_section:
            return "", {}

        # 解析参考文献列表（格式：序号. 文档名）
        reference_dict = {}  # {序号: 文档名}
        lines = reference_section.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 匹配格式：序号. 文档名
            match = re.match(r'^(\d+)\.\s*(.+)$', line)
            if match:
                index = int(match.group(1))
                doc_name = match.group(2).strip()
                reference_dict[index] = doc_name

        print(f"[_extract_existing_reference_list] 提取到{len(reference_dict)}条旧参考文献")
        return reference_section, reference_dict
    except Exception as e:
        print(f"[_extract_existing_reference_list] 提取参考文献列表失败: {e}")
        import traceback
        traceback.print_exc()
        return "", {}


def _generate_reference_list(all_refined_doc_segments_list, old_reference_dict=None):
    """
    生成参考文献列表（所有章/节/小节的④素材所涉及文献的并集）

    参数:
        all_refined_doc_segments_list: 所有章节的refined_doc_segments列表的列表
        old_reference_dict: 旧的参考文献字典 {序号: 文档名}（迭代模式时使用）

    返回: 参考文献列表字符串（格式化的参考文献）
    """
    try:
        # 收集所有文档信息（去重）
        doc_info_dict = {}  # {doc_name: {'pages': set(), 'name': doc_name}}

        for refined_doc_segments in all_refined_doc_segments_list:
            if not refined_doc_segments:
                continue

            for doc_data in refined_doc_segments:
                doc_name = doc_data['doc_name']
                if doc_name not in doc_info_dict:
                    doc_info_dict[doc_name] = {'pages': set(), 'name': doc_name}

                # 收集所有页码
                if doc_data.get('paragraphs'):
                    for para in doc_data['paragraphs']:
                        page_range = para['page_range']
                        for page in range(page_range[0], page_range[1] + 1):
                            doc_info_dict[doc_name]['pages'].add(page)

                if doc_data.get('segments'):
                    for seg in doc_data['segments']:
                        doc_info_dict[doc_name]['pages'].add(seg['page'])

        if not doc_info_dict:
            # 如果没有新文档，但有小参考文献，返回旧列表
            if old_reference_dict:
                reference_list = []
                for idx in sorted(old_reference_dict.keys()):
                    reference_list.append(f"{idx}. {old_reference_dict[idx]}")
                return "\n".join(reference_list)
            return ""

        # 🔥 如果有旧参考文献列表，合并新旧列表
        if old_reference_dict:
            # 旧的参考文献列表及序号全部不变保留
            merged_reference_list = []
            used_doc_names = set()

            # 先添加旧的参考文献（保持原有序号）
            for idx in sorted(old_reference_dict.keys()):
                doc_name = old_reference_dict[idx]
                merged_reference_list.append(f"{idx}. {doc_name}")
                used_doc_names.add(doc_name)

            # 找出新列表中不在旧列表中的文档
            new_doc_names = set(doc_info_dict.keys())
            new_doc_names = new_doc_names - used_doc_names

            if new_doc_names:
                # 新文档按文档名排序，放在旧列表后面
                next_index = max(old_reference_dict.keys()) + 1 if old_reference_dict else 1
                sorted_new_docs = sorted(new_doc_names)

                for doc_name in sorted_new_docs:
                    merged_reference_list.append(f"{next_index}. {doc_name}")
                    next_index += 1

                print(f"[_generate_reference_list] 合并参考文献列表：保留{len(old_reference_dict)}条旧文献，新增{len(new_doc_names)}条新文献")

            return "\n".join(merged_reference_list)
        else:
            # 没有旧参考文献，按原逻辑生成（按文档名排序）
            sorted_docs = sorted(doc_info_dict.items(), key=lambda x: x[0])
            reference_list = []

            for idx, (doc_name, doc_info) in enumerate(sorted_docs, 1):
                # 暂时不标注页数
                ref_text = f"{idx}. {doc_name}"
                reference_list.append(ref_text)

            return "\n".join(reference_list)
    except Exception as e:
        print(f"[_generate_reference_list] 生成参考文献列表失败: {e}")
        import traceback
        traceback.print_exc()
        return ""


def _replace_citation_markers(content, all_refined_doc_segments_list, old_reference_dict=None):
    """
    替换内容中的引用标记[文档名]为参考文献序号

    参数:
        content: 文章内容
        all_refined_doc_segments_list: 所有章节的refined_doc_segments列表的列表
        old_reference_dict: 旧的参考文献字典 {序号: 文档名}（迭代模式时使用）

    返回: 替换后的内容
    """
    try:
        # 收集所有文档名（去重并排序）
        all_doc_names = set()
        for refined_doc_segments in all_refined_doc_segments_list:
            if not refined_doc_segments:
                continue
            for doc_data in refined_doc_segments:
                all_doc_names.add(doc_data['doc_name'])

        # 🔥 如果有旧参考文献，合并新旧文档名列表，建立正确的映射
        if old_reference_dict:
            # 建立文档名到序号的映射（旧的保持原有序号，新的追加在后面）
            doc_name_to_index = {}
            used_doc_names = set()

            # 先添加旧的映射（保持原有序号）
            for idx, doc_name in old_reference_dict.items():
                doc_name_to_index[doc_name] = idx
                used_doc_names.add(doc_name)

            # 找出新文档
            new_doc_names = all_doc_names - used_doc_names

            if new_doc_names:
                # 新文档按文档名排序，分配新序号
                next_index = max(old_reference_dict.keys()) + 1 if old_reference_dict else 1
                sorted_new_docs = sorted(new_doc_names)

                for doc_name in sorted_new_docs:
                    doc_name_to_index[doc_name] = next_index
                    next_index += 1

            if not doc_name_to_index:
                return content

            print(f"[_replace_citation_markers] 使用合并后的参考文献映射：{len(old_reference_dict)}条旧文献 + {len(new_doc_names)}条新文献")
        else:
            # 没有旧参考文献，按原逻辑处理
            if not all_doc_names:
                return content

            # 按文档名排序，建立文档名到序号的映射
            sorted_doc_names = sorted(all_doc_names)
            doc_name_to_index = {doc_name: idx + 1 for idx, doc_name in enumerate(sorted_doc_names)}

        # 替换引用标记
        # 支持格式：[文档名]、【文档名】、[[文档名]]（嵌套方括号）
        # 先处理嵌套方括号（外层优先），再处理普通方括号和中文方括号

        def find_citation_match(cited_name):
            """查找引用名称的匹配"""
            # 尝试精确匹配
            if cited_name in doc_name_to_index:
                return doc_name_to_index[cited_name]

            # 尝试部分匹配（支持缩写形式、子字符串匹配等）
            best_match = None
            best_match_index = None
            best_match_score = 0

            for doc_name, index in doc_name_to_index.items():
                # 计算匹配得分
                score = 0
                # 如果cited_name是doc_name的子字符串（精确包含）
                if cited_name in doc_name:
                    score = len(cited_name) / len(doc_name)
                # 如果doc_name是cited_name的子字符串
                elif doc_name in cited_name:
                    score = len(doc_name) / len(cited_name)
                # 尝试提取年份等关键信息进行匹配
                else:
                    # 提取年份（4位数字）
                    year_match = re.search(r'\d{4}', cited_name)
                    if year_match:
                        year = year_match.group(0)
                        if year in doc_name:
                            # 再检查其他关键词
                            cited_keywords = re.findall(r'[A-Za-z\u4e00-\u9fff]+', cited_name)
                            doc_keywords = re.findall(r'[A-Za-z\u4e00-\u9fff]+', doc_name)
                            common_keywords = set(cited_keywords) & set(doc_keywords)
                            if common_keywords:
                                score = 0.5 + len(common_keywords) * 0.1
                    # 如果没有年份，尝试提取中文关键词进行匹配
                    if score == 0:
                        cited_keywords = re.findall(r'[\u4e00-\u9fff]+', cited_name)
                        doc_keywords = re.findall(r'[\u4e00-\u9fff]+', doc_name)
                        if cited_keywords:
                            # 检查cited_keywords是否都在doc_name中
                            all_found = all(
                                any(kw in doc_kw or doc_kw in kw for doc_kw in doc_keywords) for kw in cited_keywords)
                            if all_found:
                                score = sum(len(kw) for kw in cited_keywords) / max(len(doc_name), 1)

                if score > best_match_score:
                    best_match_score = score
                    best_match = doc_name
                    best_match_index = index

            # 如果找到较好的匹配（得分>0.3），返回序号
            if best_match_score > 0.3:
                return best_match_index

            return None

        # 先处理嵌套的英文方括号 [[文档名]]（使用更智能的方法处理嵌套）
        def find_nested_bracket_end(text, start_pos):
            """找到嵌套方括号的结束位置（从[[之后开始，初始深度为1）"""
            depth = 1  # 因为已经匹配到了[[，所以初始深度为1
            pos = start_pos
            while pos < len(text):
                if text[pos] == '[':
                    depth += 1
                elif text[pos] == ']':
                    depth -= 1
                    if depth == 0:
                        return pos
                pos += 1
            return -1

        # 先处理嵌套方括号 [[...]]
        pos = 0
        result_parts = []
        while pos < len(content):
            match = content.find('[[', pos)
            if match == -1:
                result_parts.append(content[pos:])
                break

            # 添加匹配之前的内容
            result_parts.append(content[pos:match])

            # 找到对应的结束位置（从[[之后的第一个字符开始）
            end_pos = find_nested_bracket_end(content, match + 2)
            if end_pos != -1 and content[end_pos] == ']':
                # 提取嵌套方括号内的内容（包括内层的[]）
                inner_content = content[match + 2:end_pos]
                # 使用整个inner_content（可能包含内层[]）来匹配
                match_index = find_citation_match(inner_content)
                if match_index is not None:
                    result_parts.append(f"[{match_index}]")
                    pos = end_pos + 1
                else:
                    # 如果找不到匹配，保持原样
                    result_parts.append(content[match:end_pos + 1])
                    pos = end_pos + 1
            else:
                # 找不到匹配的结束]，保持原样
                result_parts.append('[[')
                pos = match + 2

        content = ''.join(result_parts)

        # 再处理普通英文方括号 [...]
        def replace_english_brackets(match):
            cited_name = match.group(1)
            match_index = find_citation_match(cited_name)
            if match_index is not None:
                return f"[{match_index}]"
            return match.group(0)

        english_pattern = r'\[([^\]]+)\]'
        content = re.sub(english_pattern, replace_english_brackets, content)

        # 最后处理中文方括号 【...】
        def replace_chinese_brackets(match):
            cited_name = match.group(1)
            match_index = find_citation_match(cited_name)
            if match_index is not None:
                return f"[{match_index}]"
            return match.group(0)

        chinese_pattern = r'【([^】]+)】'
        content = re.sub(chinese_pattern, replace_chinese_brackets, content)

        return content

    except Exception as e:
        print(f"[_replace_citation_markers] 替换引用标记失败: {e}")
        import traceback
        traceback.print_exc()
        return content


def _fix_directory_numbering(directory_content):
    """
    🔥 修正目录部分的章/节/小节序号，确保正常递增

    参数:
        directory_content: 目录内容（不包括正文部分）

    返回: 修正后的目录内容
    """
    try:
        if not directory_content:
            return directory_content

        lines = directory_content.split('\n')
        if not lines:
            return directory_content

        # 第一行是标题（"xxx目录"），保持不变
        fixed_lines = [lines[0]]

        # 用于跟踪当前序号
        chapter_num = 0  # 中文数字序号（一、二、三...）
        section_num = 0  # 阿拉伯数字序号（1. 2. 3...）
        subsection_num = 0  # 字母序号（A. B. C...）

        # 当前层级状态
        current_chapter_idx = -1
        current_section_idx = -1

        # 🔥 使用中文数字转换函数，支持一到九十九

        for i, line in enumerate(lines[1:], 1):
            original_line = line
            line_stripped = line.strip()

            if not line_stripped:
                fixed_lines.append(original_line)
                continue

            # 判断层级（支持中文数字：一、二、...十、十一、十二、...）
            if re.match(r'^[一二三四五六七八九十百]+[、.]', line_stripped):
                # 章：重置节和小节序号
                chapter_num += 1
                section_num = 0
                subsection_num = 0
                current_section_idx = -1

                # 🔥 提取章名（去掉序号部分，支持中文数字：一、二、...十、十一、十二、...）
                chapter_name = re.sub(r'^[一二三四五六七八九十百]+[、.]\s*', '', line_stripped).strip()

                # 🔥 生成正确的序号：使用中文数字转换函数，支持一到九十九
                chinese_prefix = _int_to_chinese_num(chapter_num)
                if chinese_prefix:
                    chapter_prefix = chinese_prefix + '、'
                else:
                    # 如果超过99章，使用数字
                    chapter_prefix = f"{chapter_num}、"

                fixed_line = chapter_prefix + chapter_name
                # 保持原有的缩进
                if original_line.startswith(' '):
                    indent = len(original_line) - len(original_line.lstrip())
                    fixed_line = ' ' * indent + fixed_line

                fixed_lines.append(fixed_line)
                current_chapter_idx += 1

            elif re.match(r'^\d+[.]', line_stripped):
                # 节：重置小节序号
                section_num += 1
                subsection_num = 0

                # 提取节名（去掉序号部分）
                section_name = re.sub(r'^\d+[.]\s*', '', line_stripped).strip()

                # 生成正确的序号
                fixed_line = f"{section_num}." + section_name
                # 保持原有的缩进
                if original_line.startswith(' '):
                    indent = len(original_line) - len(original_line.lstrip())
                    fixed_line = ' ' * indent + fixed_line

                fixed_lines.append(fixed_line)
                current_section_idx += 1

            elif re.match(r'^[A-Z]', line_stripped) and not re.match(r'^[A-Z]{2,}', line_stripped) and not re.match(
                    r'^[A-Z]\d', line_stripped):
                # 小节
                subsection_num += 1

                # 提取小节名（去掉序号部分）
                subsection_name = re.sub(r'^[A-Z]([.]|[\s\u3000])*\s*', '', line_stripped).strip()

                # 生成正确的序号（A, B, C...）
                if subsection_num <= 26:
                    subsection_prefix = chr(64 + subsection_num) + '.'  # A., B., C., ...
                else:
                    # 如果超过26个小节，使用数字
                    subsection_prefix = f"{subsection_num}."

                fixed_line = subsection_prefix + subsection_name
                # 保持原有的缩进
                if original_line.startswith(' '):
                    indent = len(original_line) - len(original_line.lstrip())
                    fixed_line = ' ' * indent + fixed_line

                fixed_lines.append(fixed_line)

            else:
                # 其他行（空行、注释等），保持原样
                fixed_lines.append(original_line)

        fixed_content = '\n'.join(fixed_lines)

        if fixed_content != directory_content:
            print(f"[_fix_directory_numbering] 检测到序号错误，已修正")

        return fixed_content
    except Exception as e:
        print(f"[_fix_directory_numbering] 修正目录序号失败: {e}")
        import traceback
        traceback.print_exc()
        return directory_content


def _extract_existing_article_content(full_content):
    """
    🔥 从完整内容中提取已有正文部分（# 目录标题之后的内容）

    参数:
        full_content: 完整内容

    返回: (目录部分, 正文部分)
    """
    try:
        lines = full_content.split('\n')

        # 找到第一个"# "开头的行（不是第一行）
        article_start_idx = None
        for i, line in enumerate(lines):
            if i > 0 and line.strip().startswith('# '):
                article_start_idx = i
                break

        if article_start_idx is None:
            return full_content, ""

        directory_part = '\n'.join(lines[:article_start_idx]).rstrip()
        article_part = '\n'.join(lines[article_start_idx:]).strip()

        return directory_part, article_part
    except Exception as e:
        print(f"[_extract_existing_article_content] 提取正文内容失败: {e}")
        return full_content, ""


def _check_has_abstract_keywords_boundary(article_content):
    """
    🔥 检测正文中是否有"摘要""关键词"部分和"边界问题描述"部分

    参数:
        article_content: 正文内容

    返回: (has_abstract_keywords, has_boundary)
    """
    try:
        if not article_content:
            return False, False

        # 检测摘要和关键词（通常在开头，格式可能是"摘要"、"关键词"等）
        has_abstract_keywords = False
        abstract_patterns = [
            r'##\s*摘要',
            r'#\s*摘要',
            r'摘要[：:]',
            r'##\s*关键词',
            r'#\s*关键词',
            r'关键词[：:]',
        ]
        for pattern in abstract_patterns:
            if re.search(pattern, article_content, re.IGNORECASE):
                has_abstract_keywords = True
                break

        # 检测边界问题描述（通常在结尾，格式可能是"边界问题描述"、"边界问题"等）
        has_boundary = False
        boundary_patterns = [
            r'##\s*边界问题描述',
            r'#\s*边界问题描述',
            r'边界问题描述[：:]',
            r'##\s*边界问题',
            r'#\s*边界问题',
            r'边界问题[：:]',
        ]
        for pattern in boundary_patterns:
            if re.search(pattern, article_content, re.IGNORECASE):
                has_boundary = True
                break

        return has_abstract_keywords, has_boundary
    except Exception as e:
        print(f"[_check_has_abstract_keywords_boundary] 检测失败: {e}")
        return False, False


def _generate_chapter_summary_and_boundary(chapter_name, chapter_content, directory_title, username,
                                           chapter_structure=None,
                                           model_priority=['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7',
                                                           'claude-3.5']):
    """
    🔥 生成章节摘要和边界问题描述

    参数:
        chapter_name: 章名
        chapter_content: 章节完整内容
        directory_title: 目录标题
        username: 用户名
        chapter_structure: 该章的目录结构信息 {'sections': [{'name': '节名', 'subsections': [{'name': '小节名'}, ...]}, ...]}，用于生成目录结构建议
        model_priority: 模型优先级列表

    返回: (summary, boundary_description) 或 (None, None)
    """
    try:
        import time

        # 计算合适的字数（根据章节内容长度动态计算）
        chapter_length = len(chapter_content)
        summary_word_count = min(max(50, chapter_length // 20), 200)  # 摘要：50-200字
        boundary_word_count = min(max(80, chapter_length // 15), 300)  # 边界问题：80-300字

        # 构建章节结构信息（用于生成目录结构建议）
        structure_text = ""
        if chapter_structure:
            structure_text = f"\n\n本章目录结构：\n"
            structure_text += f"章：{chapter_name}\n"
            if chapter_structure.get('sections'):
                for sec_idx, section in enumerate(chapter_structure['sections'], 1):
                    # 获取节名（可能包含序号）
                    section_name_with_prefix = section.get('name_with_prefix', section.get('name', ''))
                    structure_text += f"  {sec_idx}. {section_name_with_prefix}\n"
                    if section.get('subsections'):
                        for subsec_idx, subsection in enumerate(section['subsections'], 1):
                            # 获取小节名（可能包含序号，如"A. xxx"）
                            subsec_name = subsection.get('name_with_prefix', subsection.get('name', ''))
                            structure_text += f"    {subsec_name}\n"
            else:
                structure_text += f"  （本章无下级节，直接为章内容）\n"

        # 🔥 基础system_prompt（暂时不使用thinking-checking格式要求，因为_clean_claude_response会误删全部内容）
        base_system_prompt = "你是专业的学术写作分析专家，擅长生成摘要和边界问题分析。"

        user_prompt = f"""请对以下章节内容进行摘要和边界问题描述分析。

章节名称：{chapter_name}
目录标题：{directory_title}{structure_text}

章节内容：
{chapter_content}

要求：
1. **摘要**（约{summary_word_count}字）：概括本章的核心内容、主要观点和关键结论
2. **边界问题描述**（约{boundary_word_count}字）：分析本章内容的薄弱点、临界点、存疑点、可加强点、可能有科学/工程问题的质疑点等，包括：
   - 现有此章内容（包括其中节和小节局部以及整章整体）的薄弱点
   - 临界点
   - 存疑点
   - 可加强点
   - 可能有科学/工程问题的质疑点
   - **目录结构建议**（重要）：基于对章节内容的分析，对本章的目录结构（章名、节名、小节名）提出合理自洽、精准提升的增删改建议。建议幅度必须控制在5-10%以内，尽量低而精准，只针对确实需要优化的地方提出建议。建议要具体明确，例如：
     * 建议修改某个节名或小节名，使其更准确反映内容
     * 建议新增某个小节，以填补内容空白
     * 建议删除或合并某个小节，避免内容冗余
     * 建议调整章节顺序，使逻辑更顺畅
     如果没有明显的优化需求，则可以不提出目录结构建议。

**输出格式（必须严格遵守，便于后续解析）：**

## 摘要
（摘要内容，约{summary_word_count}字）

## 边界问题描述
（边界问题描述内容，约{boundary_word_count}字，包含上述所有方面，包括目录结构建议）

**重要**：
- 严格按照上述格式输出，不要添加其他内容
- 摘要和边界问题描述要准确、全面，不要遗漏重要信息
- 边界问题描述要具体、有针对性，不要泛泛而谈
- **目录结构建议的幅度必须控制在5-10%以内，尽量低而精准，只针对确实需要优化的地方提出建议**
"""

        # 调用LLM（带超时和降级逻辑）
        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                # else:
                #     final_system_prompt = base_system_prompt
                final_system_prompt = base_system_prompt

                client = OpenAI(api_key=api_key, base_url=base_url)

                start_time = time.time()
                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": final_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )

                elapsed_time = time.time() - start_time

                # 如果耗时超过150秒，认为超时，使用下一个模型重试
                if elapsed_time > 150:
                    print(
                        f"[_generate_chapter_summary_and_boundary] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过150秒，认为超时，切换到下一个模型")
                    continue

                raw_content = response.choices[0].message.content.strip()
                # 🔥 后处理：如果是claude模型，去除thinking和checking块
                response_content = _clean_claude_response(raw_content, model_name)
                print(
                    f"[_generate_chapter_summary_and_boundary] 使用{model_name}成功生成章节摘要和边界问题，耗时{elapsed_time:.2f}秒，章节: {chapter_name}")

                # 解析摘要和边界问题描述
                summary = ""
                boundary = ""

                # 提取摘要
                summary_match = re.search(r'##\s*摘要\s*\n(.*?)(?=##\s*边界问题描述|$)', response_content, re.DOTALL)
                if summary_match:
                    summary = summary_match.group(1).strip()

                # 提取边界问题描述
                boundary_match = re.search(r'##\s*边界问题描述\s*\n(.*?)$', response_content, re.DOTALL)
                if boundary_match:
                    boundary = boundary_match.group(1).strip()

                if summary and boundary:
                    return summary, boundary
                else:
                    print(
                        f"[_generate_chapter_summary_and_boundary] ⚠️ 解析失败，summary={bool(summary)}, boundary={bool(boundary)}")
                    continue

            except Exception as e:
                error_str = str(e).lower()
                if 'timeout' in error_str or 'timed out' in error_str:
                    print(f"[_generate_chapter_summary_and_boundary] 使用{model_name}超时失败: {e}，切换到下一个模型")
                else:
                    print(f"[_generate_chapter_summary_and_boundary] 使用{model_name}失败: {e}")

                if model_name == model_priority[-1]:
                    # 最后一个模型也失败了，继续重试（最多10次）
                    max_retries = 10
                    for retry in range(max_retries):
                        try:
                            time.sleep(2)
                            retry_start_time = time.time()
                            # 🔥 重试时使用相同的final_system_prompt（暂时不使用thinking-checking格式要求）
                            response = client.chat.completions.create(
                                model=full_model_name,
                                messages=[
                                    {"role": "system", "content": final_system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                timeout=150,
                                max_tokens=hyper_para.max_tokens,
                                temperature=hyper_para.temperature
                            )
                            retry_elapsed_time = time.time() - retry_start_time

                            if retry_elapsed_time > 150:
                                print(
                                    f"[_generate_chapter_summary_and_boundary] 重试{retry + 1}次成功但耗时{retry_elapsed_time:.2f}秒超过150秒，继续重试")
                                continue

                            raw_content = response.choices[0].message.content.strip()
                            # 🔥 后处理：如果是claude模型，去除thinking和checking块（预防性处理，暂时不使用thinking-checking格式）
                            response_content = _clean_claude_response(raw_content, model_name)

                            # 解析摘要和边界问题描述
                            summary = ""
                            boundary = ""
                            summary_match = re.search(r'##\s*摘要\s*\n(.*?)(?=##\s*边界问题描述|$)', response_content,
                                                      re.DOTALL)
                            if summary_match:
                                summary = summary_match.group(1).strip()
                            boundary_match = re.search(r'##\s*边界问题描述\s*\n(.*?)$', response_content, re.DOTALL)
                            if boundary_match:
                                boundary = boundary_match.group(1).strip()

                            if summary and boundary:
                                print(
                                    f"[_generate_chapter_summary_and_boundary] 重试{retry + 1}次后成功生成，耗时{retry_elapsed_time:.2f}秒")
                                return summary, boundary
                        except Exception as e2:
                            print(f"[_generate_chapter_summary_and_boundary] 重试{retry + 1}次失败: {e2}")
                            if retry == max_retries - 1:
                                print(f"[_generate_chapter_summary_and_boundary] 所有重试均失败")
                                return None, None
                continue

        return None, None
    except Exception as e:
        print(f"[_generate_chapter_summary_and_boundary] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def _generate_full_abstract(chapter_summaries, directory_title, username,
                            model_priority=['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7', 'claude-3.5']):
    """
    🔥 生成全文摘要（综合各章摘要）

    参数:
        chapter_summaries: [(章名, 摘要), ...] 列表
        directory_title: 目录标题
        username: 用户名
        model_priority: 模型优先级列表

    返回: 全文摘要（300-400字，不超过500字）或 None
    """
    try:
        import time

        # 🔥 基础system_prompt（暂时不使用thinking-checking格式要求，因为_clean_claude_response会误删全部内容）
        base_system_prompt = "你是专业的学术写作专家，擅长综合摘要生成。"

        summaries_text = ""
        for i, (chapter_name, summary) in enumerate(chapter_summaries, 1):
            summaries_text += f"## 第{i}章：{chapter_name}\n{summary}\n\n"

        user_prompt = f"""请基于以下各章摘要，综合生成全文摘要。

目录标题：{directory_title}

各章摘要：
{summaries_text}

要求：
1. **字数要求**：300-400字，绝对不可超过500字
2. **内容要求**：综合各章摘要，保证尽可能不丢失信息，但要凝练、压缩
3. **格式要求**：直接输出摘要内容，不要添加"摘要"、"关键词"等标题，不要添加任何格式标记

**重要**：必须保证尽可能不丢失信息，同时要凝练、压缩到300-400字以内，绝对不可超过500字。
"""

        # 调用LLM（带超时和降级逻辑）
        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                # else:
                #     final_system_prompt = base_system_prompt
                final_system_prompt = base_system_prompt

                client = OpenAI(api_key=api_key, base_url=base_url)

                start_time = time.time()
                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": final_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )

                elapsed_time = time.time() - start_time

                if elapsed_time > 150:
                    print(f"[_generate_full_abstract] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过150秒，认为超时，切换到下一个模型")
                    continue

                raw_content = response.choices[0].message.content.strip()
                # 🔥 后处理：如果是claude模型，去除thinking和checking块
                response_content = _clean_claude_response(raw_content, model_name)

                # 检查字数
                if len(response_content) > 500:
                    print(f"[_generate_full_abstract] ⚠️ 生成的摘要超过500字（{len(response_content)}字），需要压缩")
                    # 可以再次调用压缩，但为了简化，这里先返回

                print(
                    f"[_generate_full_abstract] 使用{model_name}成功生成全文摘要，耗时{elapsed_time:.2f}秒，长度{len(response_content)}字")
                return response_content

            except Exception as e:
                error_str = str(e).lower()
                if 'timeout' in error_str or 'timed out' in error_str:
                    print(f"[_generate_full_abstract] 使用{model_name}超时失败: {e}，切换到下一个模型")
                else:
                    print(f"[_generate_full_abstract] 使用{model_name}失败: {e}")

                if model_name == model_priority[-1]:
                    # 🔥 如果final_system_prompt未定义（在try块定义之前就失败），重新定义它
                    if 'final_system_prompt' not in locals():
                        # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                        # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                        #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                        # else:
                        #     final_system_prompt = base_system_prompt
                        final_system_prompt = base_system_prompt
                    max_retries = 10
                    for retry in range(max_retries):
                        try:
                            time.sleep(2)
                            retry_start_time = time.time()
                            # 🔥 重试时使用相同的final_system_prompt（暂时不使用thinking-checking格式要求）
                            response = client.chat.completions.create(
                                model=full_model_name,
                                messages=[
                                    {"role": "system", "content": final_system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                timeout=150,
                                max_tokens=hyper_para.max_tokens,
                                temperature=hyper_para.temperature
                            )
                            retry_elapsed_time = time.time() - retry_start_time

                            if retry_elapsed_time > 150:
                                print(
                                    f"[_generate_full_abstract] 重试{retry + 1}次成功但耗时{retry_elapsed_time:.2f}秒超过150秒，继续重试")
                                continue

                            raw_content = response.choices[0].message.content.strip()
                            # 🔥 后处理：如果是claude模型，去除thinking和checking块（预防性处理，暂时不使用thinking-checking格式）
                            response_content = _clean_claude_response(raw_content, model_name)
                            print(
                                f"[_generate_full_abstract] 重试{retry + 1}次后成功生成全文摘要，耗时{retry_elapsed_time:.2f}秒，长度{len(response_content)}字")
                            return response_content
                        except Exception as e2:
                            print(f"[_generate_full_abstract] 重试{retry + 1}次失败: {e2}")
                            if retry == max_retries - 1:
                                print(f"[_generate_full_abstract] 所有重试均失败")
                                return None
                continue

        return None
    except Exception as e:
        print(f"[_generate_full_abstract] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _generate_keywords_from_abstract(abstract, directory_title, username,
                                     model_priority=['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7',
                                                     'claude-3.5']):
    """
    🔥 从摘要生成关键词

    参数:
        abstract: 摘要内容
        directory_title: 目录标题
        username: 用户名
        model_priority: 模型优先级列表

    返回: 关键词（用分号或逗号分隔）或 None
    """
    try:
        import time

        # 🔥 基础system_prompt（暂时不使用thinking-checking格式要求，因为_clean_claude_response会误删全部内容）
        base_system_prompt = "你是专业的学术写作专家，擅长提取关键词。"

        user_prompt = f"""请基于以下摘要，提取3-8个关键词。

目录标题：{directory_title}

摘要：
{abstract}

要求：
1. 提取3-8个关键词，用分号或逗号分隔
2. 关键词要准确反映摘要的核心内容
3. 直接输出关键词，不要添加"关键词"等标题

**输出格式**：关键词1；关键词2；关键词3；...
"""

        # 调用LLM（带超时和降级逻辑）
        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                # else:
                #     final_system_prompt = base_system_prompt
                final_system_prompt = base_system_prompt

                client = OpenAI(api_key=api_key, base_url=base_url)

                start_time = time.time()
                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": final_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )

                elapsed_time = time.time() - start_time

                if elapsed_time > 150:
                    print(
                        f"[_generate_keywords_from_abstract] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过150秒，认为超时，切换到下一个模型")
                    continue

                raw_content = response.choices[0].message.content.strip()
                # 🔥 后处理：如果是claude模型，去除thinking和checking块
                response_content = _clean_claude_response(raw_content, model_name)
                print(f"[_generate_keywords_from_abstract] 使用{model_name}成功生成关键词，耗时{elapsed_time:.2f}秒")
                return response_content

            except Exception as e:
                error_str = str(e).lower()
                if 'timeout' in error_str or 'timed out' in error_str:
                    print(f"[_generate_keywords_from_abstract] 使用{model_name}超时失败: {e}，切换到下一个模型")
                else:
                    print(f"[_generate_keywords_from_abstract] 使用{model_name}失败: {e}")

                if model_name == model_priority[-1]:
                    # 🔥 如果final_system_prompt未定义（在try块定义之前就失败），重新定义它
                    if 'final_system_prompt' not in locals():
                        # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                        # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                        #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                        # else:
                        #     final_system_prompt = base_system_prompt
                        final_system_prompt = base_system_prompt
                    max_retries = 10
                    for retry in range(max_retries):
                        try:
                            time.sleep(2)
                            retry_start_time = time.time()
                            # 🔥 重试时使用相同的final_system_prompt（暂时不使用thinking-checking格式要求）
                            response = client.chat.completions.create(
                                model=full_model_name,
                                messages=[
                                    {"role": "system", "content": final_system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                timeout=150,
                                max_tokens=hyper_para.max_tokens,
                                temperature=hyper_para.temperature
                            )
                            retry_elapsed_time = time.time() - retry_start_time

                            if retry_elapsed_time > 150:
                                print(
                                    f"[_generate_keywords_from_abstract] 重试{retry + 1}次成功但耗时{retry_elapsed_time:.2f}秒超过150秒，继续重试")
                                continue

                            raw_content = response.choices[0].message.content.strip()
                            # 🔥 后处理：如果是claude模型，去除thinking和checking块（预防性处理，暂时不使用thinking-checking格式）
                            response_content = _clean_claude_response(raw_content, model_name)
                            print(
                                f"[_generate_keywords_from_abstract] 重试{retry + 1}次后成功生成关键词，耗时{retry_elapsed_time:.2f}秒")
                            return response_content
                        except Exception as e2:
                            print(f"[_generate_keywords_from_abstract] 重试{retry + 1}次失败: {e2}")
                            if retry == max_retries - 1:
                                print(f"[_generate_keywords_from_abstract] 所有重试均失败")
                                return None
                continue

        return None
    except Exception as e:
        print(f"[_generate_keywords_from_abstract] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _extract_abstract_keywords_boundary(article_content):
    """
    🔥 从正文中提取现有的摘要、关键词和边界问题描述

    参数:
        article_content: 正文内容

    返回: (摘要, 关键词, 边界问题描述) 或 (None, None, None)
    """
    try:
        if not article_content:
            return None, None, None

        abstract = None
        keywords = None
        boundary = None

        # 提取摘要
        abstract_patterns = [
            r'##\s*摘要\s*\n(.*?)(?=\n##\s*关键词|\n##\s*[^#]|$)',
            r'#\s*摘要\s*\n(.*?)(?=\n#\s*关键词|\n#\s*[^#]|$)',
            r'摘要[：:]\s*\n(.*?)(?=\n关键词|\n##|$)',
        ]
        for pattern in abstract_patterns:
            match = re.search(pattern, article_content, re.DOTALL | re.IGNORECASE)
            if match:
                abstract = match.group(1).strip()
                break

        # 提取关键词
        keywords_patterns = [
            r'##\s*关键词\s*\n(.*?)(?=\n##\s*[^#]|$)',
            r'#\s*关键词\s*\n(.*?)(?=\n#\s*[^#]|$)',
            r'关键词[：:]\s*\n(.*?)(?=\n##|$)',
        ]
        for pattern in keywords_patterns:
            match = re.search(pattern, article_content, re.DOTALL | re.IGNORECASE)
            if match:
                keywords = match.group(1).strip()
                break

        # 提取边界问题描述
        boundary_patterns = [
            r'##\s*边界问题描述\s*\n(.*?)$',
            r'#\s*边界问题描述\s*\n(.*?)$',
            r'边界问题描述[：:]\s*\n(.*?)$',
        ]
        for pattern in boundary_patterns:
            match = re.search(pattern, article_content, re.DOTALL | re.IGNORECASE)
            if match:
                boundary = match.group(1).strip()
                break

        return abstract, keywords, boundary
    except Exception as e:
        print(f"[_extract_abstract_keywords_boundary] 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None


def _format_directory_structure_text(directory_structure):
    """
    🔥 将目录结构格式化为可读文本（用于展示给模型）

    参数:
        directory_structure: 目录结构字典

    返回: 格式化后的文本字符串
    """
    try:
        if not directory_structure:
            return ""

        result_lines = []
        result_lines.append(f"目录标题：{directory_structure.get('title', '')}")
        result_lines.append("")

        chapters = directory_structure.get('chapters', [])
        for chapter in chapters:
            chapter_name = chapter.get('name_with_prefix', chapter.get('name', ''))
            result_lines.append(f"{chapter_name}")

            sections = chapter.get('sections', [])
            for section in sections:
                section_name = section.get('name_with_prefix', section.get('name', ''))
                result_lines.append(f"  {section_name}")

                subsections = section.get('subsections', [])
                for subsection in subsections:
                    subsection_name = subsection.get('name_with_prefix', subsection.get('name', ''))
                    result_lines.append(f"    {subsection_name}")

        return "\n".join(result_lines)
    except Exception as e:
        print(f"[_format_directory_structure_text] 格式化目录结构失败: {e}")
        return ""


def _extract_article_heading_structure(full_article):
    """
    🔥 从完整文章内容中提取章节标题结构（##、###、####）

    参数:
        full_article: 完整文章内容

    返回: 格式化后的章节标题结构文本
    """
    try:
        if not full_article:
            return ""

        special_sections = {'摘要', '关键词', '参考文献', '边界问题描述'}
        result_lines = []
        lines = full_article.split('\n')

        for line in lines:
            line_stripped = line.strip()

            if line_stripped.startswith('## '):
                chapter_title = line_stripped[3:].strip()
                # 跳过特殊部分
                chapter_name = re.sub(r'^[一二三四五六七八九十]+[、.]\s*', '', chapter_title).strip()
                if chapter_name in special_sections or any(special in chapter_name for special in special_sections):
                    continue
                result_lines.append(f"{chapter_title}")
            elif line_stripped.startswith('### '):
                section_title = line_stripped[4:].strip()
                # 跳过特殊部分
                section_name = re.sub(r'^\d+[.]\s*', '', section_title).strip()
                if section_name in special_sections or any(special in section_name for special in special_sections):
                    continue
                result_lines.append(f"  {section_title}")
            elif line_stripped.startswith('#### '):
                subsection_title = line_stripped[5:].strip()
                # 跳过特殊部分
                temp_subsection_name = re.sub(r'^[A-Z]([.]|[\s\u3000])*\s*', '', subsection_title).strip()
                if temp_subsection_name in special_sections or any(
                        special in temp_subsection_name for special in special_sections):
                    continue
                result_lines.append(f"    {subsection_title}")

        return "\n".join(result_lines)
    except Exception as e:
        print(f"[_extract_article_heading_structure] 提取文章标题结构失败: {e}")
        return ""


def _iterate_abstract_keywords(existing_content, full_article, directory_title, username, is_abstract=True,
                               model_priority=['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7', 'claude-3.5'],
                               directory_structure=None, max_iteration_in_full_article=0):
    """
    🔥 迭代摘要或关键词（粒度更小，3-5%以内）

    参数:
        existing_content: 现有的摘要或关键词内容
        full_article: 完整文章内容
        directory_title: 目录标题
        username: 用户名
        is_abstract: True表示迭代摘要，False表示迭代关键词
        model_priority: 模型优先级列表
        directory_structure: 目录结构（可选，用于检查目录是否有修改）
        max_iteration_in_full_article: 全文最大迭代次数（需求③）

    返回: 迭代后的内容或 None
    """
    try:
        import time

        content_type = "摘要" if is_abstract else "关键词"
        # 🔥 基础system_prompt（暂时不使用thinking-checking格式要求，因为_clean_claude_response会误删全部内容）
        base_system_prompt = f"你是专业的学术写作专家，擅长迭代精进{content_type}。"

        # 🔥 需求③：计算迭代次数：使用全文最大迭代次数+1（保持全文整体性）
        iteration_count = max_iteration_in_full_article + 1
        print(f"[_iterate_abstract_keywords] 使用全文最大迭代次数{max_iteration_in_full_article}+1={iteration_count}（保持全文整体性）")

        # 🔥 构建前序次标签的描述（与正文迭代保持一致）
        previous_tags_desc = []
        for prev_iter in range(1, iteration_count):
            previous_tags_desc.append(f"<第{prev_iter}次修改内容>")
        if previous_tags_desc:
            previous_tags_text = "、".join(previous_tags_desc)
            previous_tags_rule = f"**前序次标签保留（重要）**：所有前序次数的标签（如{previous_tags_text}等）必须保留，但**标签包裹的内容都可以被修改、删减或浓缩精炼**。**⚠️ 重要**：前序次修改内容（<第xx次修改内容>标签包裹的）也全都是可以被修改的，并不是说前序次的修改本次就不能动了。**所有内容都是可以动的（除了`***xxx***`标记的用户手动部分外）**，依然可以再动（保留标签即可，内容都是可改可删可浓缩精炼的）。**特别强调**：前序次标签内的文献引用标记（如[文档名]、[序号]等格式）尽量保留不变，但标签包裹的文字内容都可以进行浓缩精炼。这样可以很大地缓解每次修改都成了在后面新增内容的问题。"
        else:
            previous_tags_rule = ""  # 第1次迭代时没有前序次标签

        # 🔥 根据内容类型设置字数要求
        if is_abstract:
            word_count_requirement = "迭代后的字数依然必须控制在300-400字，不可超过500字，如果需要在某处添加内容，必须在其他弱价值位置删除相应字数，确保总字数不增加或略有减少。"
            word_count_emphasis = "**字数要求**：依然控制在300-400字，不可超过500字，这是非常严格的要求"
        else:
            word_count_requirement = "迭代后确保总字数不增加或略有减少。"
            word_count_emphasis = "**字数不能增加，必须保持字数，这是非常严格的要求**"

        # 🔥 构建目录结构信息（用于检查目录是否有修改）
        directory_info = ""
        modification_limit_text = "可以适当放宽到10-15%，但要确保修改是有实质性提升的"
        new_directory_structure_text = ""
        old_article_structure_text = ""

        if directory_structure:
            # 🔥 格式化新的目录结构
            new_directory_structure_text = _format_directory_structure_text(directory_structure)

            # 🔥 提取现有正文中的章节标题结构
            old_article_structure_text = _extract_article_heading_structure(full_article)

            directory_info = f"""
** 极其重要：目录/题目变动优先调整要求（最高优先级）**：
这是迭代{content_type}时最优先、最关键的调整要求，必须严格遵守！

**优先级说明**：目录/题目变动 > 正文内容变化。如果目录/题目有变动，必须优先调整{content_type}以匹配新的目录/题目，即使这意味着需要更多的修改幅度。

**新旧目录结构对比（必须仔细对比）**：

**新的目录结构（当前目录卡片）**：
```
{new_directory_structure_text}
```

**旧的正文结构（现有正文中的##、###、####标题）**：
```
{old_article_structure_text if old_article_structure_text else "（暂无正文结构，说明是首次生成）"}
```

**⚠️ 必须仔细对比新旧结构的差异，识别所有变化**：
- 对比目录标题是否有变化
- 对比章节名称是否有变化
- 对比章节顺序是否有调整
- 对比小节数量是否有变化（例如：从5个小节变为3个小节）
- 对比小节名称是否有变化

**调整要求（必须全面检查，可能不只一处）**：
1. **目录题目验证（最高优先级）**：
   - 仔细检查目录标题"{directory_title}"是否有任何修改（包括标点符号、措辞变化等）
   - 如果目录标题已修改，原{content_type}是基于旧目录标题写的，**必须**相应调整以消除冲突
   - 检查{content_type}中所有提及标题的地方，确保与新的标题完全一致

2. **目录结构验证（最高优先级）**：
   - **仔细对比新旧结构**，识别所有差异（包括但不限于：章节顺序调整、新增章节、删除章节、章节名称变化、小节数量变化等）
   - **特别注意**：检查章节下的小节数量变化（例如：原来有5个小节（A、B、C、D、E），现在只有3个小节（A、B、C），必须相应调整{content_type}中的描述）
   - **全面检查**{content_type}中所有涉及具体章节名称、小节名称、数量描述的地方（例如："五组病种"、"ABCDE五组"等），确保与新的目录结构完全匹配
   - 如果目录结构已修改，原{content_type}是基于旧目录结构写的，**必须**相应调整以消除冲突

3. **全面检查与冲突消除（必须逐句检查）**：
   - **逐句仔细检查**{content_type}的每一句话，识别所有涉及目录/题目的描述
   - 如果发现目录题目或目录结构有修改，必须对{content_type}中涉及这些变化的部分进行调整、修正和更新
   - **不只一处**：可能存在多处需要调整的地方，必须全面检查，不能遗漏任何一处
   - 确保{content_type}与新的目录题目和目录结构完全一致，消除任何冲突
   - 如果目录/题目变动较多，可能需要在多处进行调整

4. **修改幅度调整（目录变动时可放宽）**：
   - 如果目录/题目变动较多，导致需要多处调整，可以适当放宽修改幅度限制
   - 如果正文内容（章节小节的具体内容）有重要变化，也需要相应调整摘要以反映这些变化
   - 一般情况下修改幅度控制在15-20%以内
   - 但如果目录/题目变动或正文内容变化导致需要较多调整，修改幅度最好适当提高到20-25%
   - **优先级**：首先处理目录/题目变动（最高优先级），然后处理正文内容的重要变化
   - **但前提是**：这些额外的修改必须是为了匹配目录/题目变动或反映正文内容变化，而不是随意的内容调整

**示例**：
- 如果目录中某章某节的DRG策略从原来的"ABCDE五组"（肝胆、心肺、脾胃、肾肺胆、脾胆三焦）变成了"ABC三组"（肝肾经、心肺经、脾胃经），那么{content_type}中所有提及"DRG五组"、"五组病种"、"ABCDE"、"肝胆、心肺、脾胃、肾肺胆、脾胆三焦"等相关描述的地方，都必须调整为"DRG三组"、"三组病种"、"ABC"、"肝肾经、心肺经、脾胃经"等，确保与新的目录结构完全一致。

"""
            modification_limit_text = "可以适当放宽到15-20%，但如果目录/题目变动或正文内容变化，可以进一步提高到20-25%（前提是这些额外修改是为了匹配目录/题目变动或反映正文内容变化）"

        user_prompt = f"""请对以下{content_type}进行迭代性精进和修正。这是迭代模式，修改幅度要控制在{modification_limit_text}，切忌另起炉灶。

目录标题：{directory_title}
{directory_info}
现有{content_type}：
{existing_content}

完整文章内容：
{full_article[:5000]}  # 限制长度

要求：
1. **修改幅度（重要）**：可以适当放宽到{modification_limit_text}，但要确保修改是有实质性提升的，切忌另起炉灶
   - **修改包括两部分**：
     a. **目录/题目变动调整**（最高优先级）：根据新旧目录结构对比，调整摘要中涉及目录/题目的描述
     b. **正文内容变化微调**：根据完整文章内容的变化，微调摘要以反映正文的重要变化
   - 正常情况下修改部分应该只占全文的15-20%，但如果目录/题目变动或正文内容变化导致需要较多调整，可以提高到20-25%，其余部分必须完全原样保留
2. **字数要求（非常重要）**：{word_count_requirement}
3. **修改标记要求（必须严格遵守）**：
   - 在**真正产生变动的部分**用<第{iteration_count}次修改内容>和</第{iteration_count}次修改内容>包裹
   - **⚠️ 重要说明**：此迭代次数{iteration_count}是基于全文已有标签的最大次数+1计算的，而非仅基于当前{content_type}内的标签。这样做是为了保持全文的整体性和一致性，避免不同部分使用不同的迭代次数导致混乱。请严格按照此迭代次数使用标签。
   - 正常情况下修改部分应该只占全文的15-20%，但如果目录/题目变动导致需要较多调整，可以提高到20-25%，其余部分必须完全原样保留
   - 只在真正产生实质性改动、有明显提升的核心部分使用修改标记
{f"4. **{previous_tags_rule}**" if previous_tags_rule else ""}
{f"5." if previous_tags_rule else "4."} **迭代原则**：
   - **首先处理目录/题目变动**（最高优先级）：必须根据新旧目录结构对比，调整{content_type}中所有涉及目录/题目的描述
   - **然后处理正文内容变化**：仔细阅读完整文章内容，识别正文中的重要变化，相应微调{content_type}以反映这些变化
   - 如果没有目录变动且正文内容变化不大，可以基本保持原样
   - 但如果有目录变动或正文内容有重要变化，必须进行相应调整
{f"6." if previous_tags_rule else "5."} **格式要求**：直接输出迭代后的{content_type}内容，不要添加"{content_type}"等标题，不要添加任何格式标记（除了用于标注修改内容的标签）

**⚠️ 最后强调（必须严格遵守）**：
- **⚠️ 重要：要考虑可能的目录修改分析、变化对比等，但一定不要显式地输出出来。直接输出迭代后的内容，不要有其他任何陈述、分析！**
- 这是迭代，不是重新生成，修改幅度要控制在{modification_limit_text}，切忌另起炉灶
- ** 最高优先级**：如果目录/题目有变动，必须优先调整{content_type}以匹配新的目录/题目，即使这意味着需要更多的修改幅度（可以提高到15-20%）
- ** 正文内容变化**：在处理好目录/题目变动后，还需要根据完整文章内容的变化，微调{content_type}以反映正文的重要变化
- ** 全面检查**：
  a. 必须逐句检查{content_type}，识别所有涉及目录/题目的描述，确保与新的目录/题目完全一致，可能不只一处
  b. 必须仔细阅读完整文章内容，识别正文的重要变化，并在{content_type}中进行相应微调
- **⚠️ 用户手动编辑内容保护（极其重要，不可违反）**：如果{content_type}中存在`***内容***`标记（用三个星号包裹的内容），这些是使用者手动改/加的内容，体现了用户的重要意图和修改动因。**⚠️ 迭代时绝对不可以动这部分内容，包括`***`标记本身（首尾的三个星号）！**必须完全原样保留：`***`+ 内容 + `***`，**绝对不允许**：
  - 删除`***`标记（包括首尾的`***`）
  - 删除、修改或替换标记内的内容
这些内容是用户手动调整的，非常重要，任何情况下都不允许删除、修改或替换。同时要考量用户为什么要这样手动修改的动因、意图，理解用户这样修改的目的，并在迭代时尊重这些意图。
- {word_count_emphasis}
- 只在真正产生实质性改动、有明显提升的核心部分使用<第{iteration_count}次修改内容>标签（包括目录变动调整和正文内容明显变化微调）
- 未修改的部分必须完全原样保留，绝对不要添加任何标记
{f"- {previous_tags_rule}" if previous_tags_rule else ""}
{f"- **⚠️ 特别重要：前序次修改内容中的文献引用标记（如[文档名]、[序号]等格式）必须完全原样保留，不允许删除、修改或替换**" if previous_tags_rule else ""}
"""

        # 调用LLM（带超时和降级逻辑）
        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                # else:
                #     final_system_prompt = base_system_prompt
                final_system_prompt = base_system_prompt

                client = OpenAI(api_key=api_key, base_url=base_url)

                start_time = time.time()
                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": final_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )

                elapsed_time = time.time() - start_time

                if elapsed_time > 150:
                    print(f"[_iterate_abstract_keywords] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过150秒，认为超时，切换到下一个模型")
                    continue

                raw_content = response.choices[0].message.content.strip()
                # 🔥 后处理：如果是claude模型，去除thinking和checking块
                response_content = _clean_claude_response(raw_content, model_name)
                print(f"[_iterate_abstract_keywords] 使用{model_name}成功迭代{content_type}，耗时{elapsed_time:.2f}秒")
                return response_content

            except Exception as e:
                error_str = str(e).lower()
                if 'timeout' in error_str or 'timed out' in error_str:
                    print(f"[_iterate_abstract_keywords] 使用{model_name}超时失败: {e}，切换到下一个模型")
                else:
                    print(f"[_iterate_abstract_keywords] 使用{model_name}失败: {e}")

                if model_name == model_priority[-1]:
                    # 🔥 如果final_system_prompt未定义（在try块定义之前就失败），重新定义它
                    if 'final_system_prompt' not in locals():
                        # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                        # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                        #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                        # else:
                        #     final_system_prompt = base_system_prompt
                        final_system_prompt = base_system_prompt
                    max_retries = 10
                    for retry in range(max_retries):
                        try:
                            time.sleep(2)
                            retry_start_time = time.time()
                            # 🔥 重试时使用相同的final_system_prompt（暂时不使用thinking-checking格式要求）
                            response = client.chat.completions.create(
                                model=full_model_name,
                                messages=[
                                    {"role": "system", "content": final_system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                timeout=150,
                                max_tokens=hyper_para.max_tokens,
                                temperature=hyper_para.temperature
                            )
                            retry_elapsed_time = time.time() - retry_start_time

                            if retry_elapsed_time > 150:
                                print(
                                    f"[_iterate_abstract_keywords] 重试{retry + 1}次成功但耗时{retry_elapsed_time:.2f}秒超过150秒，继续重试")
                                continue

                            raw_content = response.choices[0].message.content.strip()
                            # 🔥 后处理：如果是claude模型，去除thinking和checking块（预防性处理，暂时不使用thinking-checking格式）
                            response_content = _clean_claude_response(raw_content, model_name)
                            print(
                                f"[_iterate_abstract_keywords] 重试{retry + 1}次后成功迭代{content_type}，耗时{retry_elapsed_time:.2f}秒")
                            return response_content
                        except Exception as e2:
                            print(f"[_iterate_abstract_keywords] 重试{retry + 1}次失败: {e2}")
                            if retry == max_retries - 1:
                                print(f"[_iterate_abstract_keywords] 所有重试均失败")
                                return None
                continue

        return None
    except Exception as e:
        print(f"[_iterate_abstract_keywords] 迭代失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _iterate_boundary_description(existing_boundary, full_article, directory_title, username,
                                  model_priority=['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7', 'claude-3.5'],
                                  directory_structure=None, max_iteration_in_full_article=0):
    """
    🔥 迭代边界问题描述（粒度更小，3-5%以内）

    参数:
        existing_boundary: 现有的边界问题描述
        full_article: 完整文章内容
        directory_title: 目录标题
        username: 用户名
        model_priority: 模型优先级列表
        directory_structure: 目录结构（可选，用于检查目录是否有修改）
        max_iteration_in_full_article: 全文最大迭代次数（需求③）

    返回: 迭代后的边界问题描述或 None
    """
    try:
        import time

        # 🔥 基础system_prompt（暂时不使用thinking-checking格式要求，因为_clean_claude_response会误删全部内容）
        base_system_prompt = "你是专业的学术写作专家，擅长迭代精进边界问题描述。"

        # 🔥 需求③：计算迭代次数：使用全文最大迭代次数+1（保持全文整体性）
        iteration_count = max_iteration_in_full_article + 1
        print(f"[_iterate_boundary_description] 使用全文最大迭代次数{max_iteration_in_full_article}+1={iteration_count}（保持全文整体性）")

        # 🔥 构建前序次标签的描述（与正文迭代保持一致）
        previous_tags_desc = []
        for prev_iter in range(1, iteration_count):
            previous_tags_desc.append(f"<第{prev_iter}次修改内容>")
        if previous_tags_desc:
            previous_tags_text = "、".join(previous_tags_desc)
            previous_tags_rule = f"**前序次标签保留（重要）**：所有前序次数的标签（如{previous_tags_text}等）必须保留，但**标签包裹的内容都可以被修改、删减或浓缩精炼**。**⚠️ 重要**：前序次修改内容（<第xx次修改内容>标签包裹的）也全都是可以被修改的，并不是说前序次的修改本次就不能动了。**所有内容都是可以动的（除了`***xxx***`标记的用户手动部分外）**，依然可以再动（保留标签即可，内容都是可改可删可浓缩精炼的）。**特别强调**：前序次标签内的文献引用标记（如[文档名]、[序号]等格式）尽量保留不变，但标签包裹的文字内容都可以进行浓缩精炼。这样可以很大地缓解每次修改都成了在后面新增内容的问题。"
        else:
            previous_tags_rule = ""  # 第1次迭代时没有前序次标签

        # 🔥 构建目录结构信息（用于检查目录是否有修改）
        directory_info = ""
        if directory_structure:
            directory_info = f"""
**⚠️ 重要：目录验证和调整要求**：
除了现有的输入给大模型迭代后新的具体章节内容外，你还需要考虑：
1. **目录题目验证**：检查目录标题"{directory_title}"是否有修改，如果目录标题已修改，原边界问题描述是基于旧目录标题写的，需要相应调整以消除冲突
2. **目录结构验证**：检查目录结构是否有修改（如章节顺序调整、新增章节、删除章节等），如果目录结构已修改，原边界问题描述是基于旧目录结构写的，需要相应调整以消除冲突
3. **冲突消除**：如果发现目录题目或目录结构有修改，必须对边界问题描述中涉及这些变化的部分进行调整、修正和更新，确保边界问题描述与新的目录题目和目录结构保持一致，消除任何冲突

"""

        # 🔥 构建目录结构信息（用于检查目录是否有修改）
        directory_info = ""
        if directory_structure:
            directory_info = f"""
**⚠️ 重要：目录验证和调整要求**：
除了现有的输入给大模型迭代后新的具体章节内容外，你还需要考虑：
1. **目录题目验证**：检查目录标题"{directory_title}"是否有修改，如果目录标题已修改，原边界问题描述是基于旧目录标题写的，需要相应调整以消除冲突
2. **目录结构验证**：检查目录结构是否有修改（如章节顺序调整、新增章节、删除章节等），如果目录结构已修改，原边界问题描述是基于旧目录结构写的，需要相应调整以消除冲突
3. **冲突消除**：如果发现目录题目或目录结构有修改，必须对边界问题描述中涉及这些变化的部分进行调整、修正和更新，确保边界问题描述与新的目录题目和目录结构保持一致，消除任何冲突

"""

        user_prompt = f"""请对以下边界问题描述进行迭代性精进和修正。这是迭代模式，修改幅度要控制在3-5%以内，切忌另起炉灶。

目录标题：{directory_title}
{directory_info}
现有边界问题描述：
{existing_boundary}

完整文章内容：
{full_article[:5000]}  # 限制长度

要求：
1. **修改幅度（重要）**：严格控制在3-5%以内，绝对不可超过5%，切忌另起炉灶
2. **字数要求（非常重要）**：迭代后的字数必须不多于现有字数，绝对不可以增加字数，依然控制在300字左右，不可超过400字）。如果需要在某处添加内容，必须在其他弱价值位置删除相应字数，确保总字数不增加或略有减少。
3. **修改标记要求（必须严格遵守）**：
   - 在**真正产生变动的部分**用<第{iteration_count}次修改内容>和</第{iteration_count}次修改内容>包裹，此部分应该只占全文的3-5%，其余95%-97%必须完全原样保留
   - **⚠️ 重要说明**：此迭代次数{iteration_count}是基于全文已有标签的最大次数+1计算的，而非仅基于当前边界问题描述内的标签。这样做是为了保持全文的整体性和一致性，避免不同部分使用不同的迭代次数导致混乱。请严格按照此迭代次数使用标签。
   - 只在真正产生实质性改动、有明显提升的核心部分使用修改标记
{f"4. **{previous_tags_rule}**" if previous_tags_rule else ""}
{f"5." if previous_tags_rule else "4."} **迭代原则**：只在真正需要微调的地方进行修改，没有大改动的话可以基本保持原样
{f"6." if previous_tags_rule else "5."} **格式要求**：直接输出迭代后的边界问题描述内容，不要添加"边界问题描述"等标题，不要添加任何格式标记（除了用于标注修改内容的标签）

**⚠️ 重要：要考虑可能的目录修改分析、变化对比等，但一定不要显式地输出出来。直接输出迭代后的内容，不要有其他任何陈述、分析！**

**⚠️ 检查明显不够理解的情况（重要）**：
在生成/迭代边界问题描述时，要特别注意检查是否有一些明显不够理解的情况：
1. **具体概念与模糊正文的冲突**：如果章/节/小节标题涉及非常具体的概念或数字（例如"60阵列组药"、"19味药xxx"、"DRG"等），但对应的正文中写得模模糊糊不清楚，例如并未解释是哪60阵列/哪19味药/DRG是什么等等，可能说明大模型并不理解，说明可能缺少这部分的素材文本内容
2. **建议的改进方向**：除了类似建议加"第4章增'3.1归经验证方法'及60阵列药物配置附表"这种对最终输出目录的调整外，动作可以更清楚地返回到过程性中，不仅仅是输出性，即落到建议增加对应的导入文档和卡片讨论，让用户知道自己要补什么动作
3. **过程性建议**：当发现明显不够理解的情况时，应该建议用户：
   - 增加对应的导入文档（提供相关素材）
   - 增加卡片讨论（通过讨论加深理解）
   - 明确告知用户需要补充什么内容或动作

**⚠️ 最后强调**：
- 这是迭代，不是重新生成，修改幅度要控制在3-5%以内，绝对不可超过5%，切忌另起炉灶
- **字数要求**：依然在300字左右，不可超过400字，字数不能增加，必须保持，这是非常严格的要求
- **⚠️ 用户手动编辑内容保护（极其重要，绝对不可违反）**：如果边界问题描述中存在`***内容***`标记（用三个星号包裹的内容），这些是使用者手动改/加的内容，体现了用户的重要意图和修改动因。**⚠️ 迭代时绝对不可以动这部分内容，包括`***`标记本身（首尾的三个星号）！**必须完全原样保留：`***`+ 内容 + `***`，**绝对不允许**：
  - 删除`***`标记（包括首尾的`***`）
  - 删除、修改或替换标记内的内容
这些内容是用户手动调整的，非常重要，任何情况下都不允许删除、修改或替换。同时要考量用户为什么要这样手动修改的动因、意图，理解用户这样修改的目的，并在迭代时尊重这些意图。
- 只在真正产生实质性改动、有明显提升的核心部分使用<第{iteration_count}次修改内容>标签
- 未修改的部分必须完全原样保留，绝对不要添加任何标记
{f"- {previous_tags_rule}" if previous_tags_rule else ""}
{f"- **⚠️ 特别重要：前序次修改内容中的文献引用标记（如[文档名]、[序号]等格式）必须完全原样保留，不允许删除、修改或替换**" if previous_tags_rule else ""}
"""

        # 调用LLM（带超时和降级逻辑）
        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                # else:
                #     final_system_prompt = base_system_prompt
                final_system_prompt = base_system_prompt

                client = OpenAI(api_key=api_key, base_url=base_url)

                start_time = time.time()
                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": final_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )

                elapsed_time = time.time() - start_time

                if elapsed_time > 150:
                    print(f"[_iterate_boundary_description] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过150秒，认为超时，切换到下一个模型")
                    continue

                raw_content = response.choices[0].message.content.strip()
                # 🔥 后处理：如果是claude模型，去除thinking和checking块
                response_content = _clean_claude_response(raw_content, model_name)
                print(f"[_iterate_boundary_description] 使用{model_name}成功迭代边界问题描述，耗时{elapsed_time:.2f}秒")
                return response_content

            except Exception as e:
                error_str = str(e).lower()
                if 'timeout' in error_str or 'timed out' in error_str:
                    print(f"[_iterate_boundary_description] 使用{model_name}超时失败: {e}，切换到下一个模型")
                else:
                    print(f"[_iterate_boundary_description] 使用{model_name}失败: {e}")

                if model_name == model_priority[-1]:
                    # 🔥 如果final_system_prompt未定义（在try块定义之前就失败），重新定义它
                    if 'final_system_prompt' not in locals():
                        # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                        # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                        #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                        # else:
                        #     final_system_prompt = base_system_prompt
                        final_system_prompt = base_system_prompt
                    max_retries = 10
                    for retry in range(max_retries):
                        try:
                            time.sleep(2)
                            retry_start_time = time.time()
                            # 🔥 重试时使用相同的final_system_prompt（暂时不使用thinking-checking格式要求）
                            response = client.chat.completions.create(
                                model=full_model_name,
                                messages=[
                                    {"role": "system", "content": final_system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                timeout=150,
                                max_tokens=hyper_para.max_tokens,
                                temperature=hyper_para.temperature
                            )
                            retry_elapsed_time = time.time() - retry_start_time

                            if retry_elapsed_time > 150:
                                print(
                                    f"[_iterate_boundary_description] 重试{retry + 1}次成功但耗时{retry_elapsed_time:.2f}秒超过150秒，继续重试")
                                continue

                            raw_content = response.choices[0].message.content.strip()
                            # 🔥 后处理：如果是claude模型，去除thinking和checking块（预防性处理，暂时不使用thinking-checking格式）
                            response_content = _clean_claude_response(raw_content, model_name)
                            print(
                                f"[_iterate_boundary_description] 重试{retry + 1}次后成功迭代边界问题描述，耗时{retry_elapsed_time:.2f}秒")
                            return response_content
                        except Exception as e2:
                            print(f"[_iterate_boundary_description] 重试{retry + 1}次失败: {e2}")
                            if retry == max_retries - 1:
                                print(f"[_iterate_boundary_description] 所有重试均失败")
                                return None
                continue

        return None
    except Exception as e:
        print(f"[_iterate_boundary_description] 迭代失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _remove_abstract_keywords_boundary(article_content):
    """
    🔥 移除正文中的摘要、关键词和边界问题描述部分

    参数:
        article_content: 正文内容

    返回: 移除后的正文内容
    """
    try:
        if not article_content:
            return article_content

        # 移除摘要部分
        article_content = re.sub(r'##\s*摘要\s*\n.*?(?=\n##\s*关键词|\n##\s*[^#]|$)', '', article_content,
                                 flags=re.DOTALL | re.IGNORECASE)
        article_content = re.sub(r'#\s*摘要\s*\n.*?(?=\n#\s*关键词|\n#\s*[^#]|$)', '', article_content,
                                 flags=re.DOTALL | re.IGNORECASE)
        article_content = re.sub(r'摘要[：:]\s*\n.*?(?=\n关键词|\n##|$)', '', article_content,
                                 flags=re.DOTALL | re.IGNORECASE)

        # 移除关键词部分
        article_content = re.sub(r'##\s*关键词\s*\n.*?(?=\n##\s*[^#]|$)', '', article_content,
                                 flags=re.DOTALL | re.IGNORECASE)
        article_content = re.sub(r'#\s*关键词\s*\n.*?(?=\n#\s*[^#]|$)', '', article_content,
                                 flags=re.DOTALL | re.IGNORECASE)
        article_content = re.sub(r'关键词[：:]\s*\n.*?(?=\n##|$)', '', article_content, flags=re.DOTALL | re.IGNORECASE)

        # 移除边界问题描述部分
        article_content = re.sub(r'##\s*边界问题描述\s*\n.*?$', '', article_content, flags=re.DOTALL | re.IGNORECASE)
        article_content = re.sub(r'#\s*边界问题描述\s*\n.*?$', '', article_content, flags=re.DOTALL | re.IGNORECASE)
        article_content = re.sub(r'边界问题描述[：:]\s*\n.*?$', '', article_content, flags=re.DOTALL | re.IGNORECASE)

        # 清理多余的空行
        article_content = re.sub(r'\n{3,}', '\n\n', article_content)
        article_content = article_content.strip()

        return article_content
    except Exception as e:
        print(f"[_remove_abstract_keywords_boundary] 移除失败: {e}")
        import traceback
        traceback.print_exc()
        return article_content


def _generate_full_boundary_summary(chapter_boundaries, directory_title, username,
                                    model_priority=['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7',
                                                    'claude-3.5']):
    """
    🔥 生成全文边界问题描述汇总凝练（综合各章边界问题描述）

    参数:
        chapter_boundaries: [(章名, 边界问题描述), ...] 列表
        directory_title: 目录标题
        username: 用户名
        model_priority: 模型优先级列表

    返回: 全文边界问题描述汇总凝练（300字左右，不超过400字）或 None
    """
    try:
        import time

        # 🔥 基础system_prompt（暂时不使用thinking-checking格式要求，因为_clean_claude_response会误删全部内容）
        base_system_prompt = "你是专业的学术写作专家，擅长边界问题分析和汇总。"

        boundaries_text = ""
        for i, (chapter_name, boundary) in enumerate(chapter_boundaries, 1):
            boundaries_text += f"## 第{i}章：{chapter_name}\n{boundary}\n\n"

        user_prompt = f"""请基于以下各章边界问题描述，综合生成全文各章节边界问题描述汇总凝练。

目录标题：{directory_title}

各章边界问题描述：
{boundaries_text}

要求：
1. **字数要求**：300字左右，绝对不可超过400字
2. **内容要求**：综合各章边界问题描述，保证尽可能不丢失信息，但要凝练、压缩
3. **格式要求**：直接输出边界问题描述内容，不要添加"边界问题描述"等标题，不要添加任何格式标记
4. **目录结构建议保留**：各章边界问题描述中可能包含对目录结构（章名、节名、小节名）的增删改建议，这些建议要尽可能保留在汇总凝练中，但要凝练表达。如果有跨章节的目录结构优化建议，可以合并和综合。建议幅度必须控制在5-10%以内，尽量低而精准。

**重要**：必须保证尽可能不丢失信息，特别是：
- 各章节的薄弱点、临界点、存疑点、可加强点、质疑点等关键信息
- 对目录结构的增删改建议（如果存在），这些建议幅度必须控制在5-10%以内，尽量低而精准
同时要凝练、压缩到300字左右，绝对不可超过400字。
"""

        # 调用LLM（带超时和降级逻辑）
        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                # else:
                #     final_system_prompt = base_system_prompt
                final_system_prompt = base_system_prompt

                client = OpenAI(api_key=api_key, base_url=base_url)

                start_time = time.time()
                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": final_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )

                elapsed_time = time.time() - start_time

                if elapsed_time > 150:
                    print(
                        f"[_generate_full_boundary_summary] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过150秒，认为超时，切换到下一个模型")
                    continue

                raw_content = response.choices[0].message.content.strip()
                # 🔥 后处理：如果是claude模型，去除thinking和checking块
                response_content = _clean_claude_response(raw_content, model_name)

                # 检查字数
                if len(response_content) > 400:
                    print(f"[_generate_full_boundary_summary] ⚠️ 生成的边界问题描述超过400字（{len(response_content)}字），需要压缩")

                print(
                    f"[_generate_full_boundary_summary] 使用{model_name}成功生成全文边界问题描述汇总，耗时{elapsed_time:.2f}秒，长度{len(response_content)}字")
                return response_content

            except Exception as e:
                error_str = str(e).lower()
                if 'timeout' in error_str or 'timed out' in error_str:
                    print(f"[_generate_full_boundary_summary] 使用{model_name}超时失败: {e}，切换到下一个模型")
                else:
                    print(f"[_generate_full_boundary_summary] 使用{model_name}失败: {e}")

                if model_name == model_priority[-1]:
                    # 🔥 如果final_system_prompt未定义（在try块定义之前就失败），重新定义它
                    if 'final_system_prompt' not in locals():
                        # 🔥 暂时不使用thinking-checking格式要求（因为_clean_claude_response会误删全部内容）
                        # if any(claude_name in model_name.lower() for claude_name in ['claude', 'sonnet']):
                        #     final_system_prompt = base_system_prompt + _get_thinking_checking_format_requirement()
                        # else:
                        #     final_system_prompt = base_system_prompt
                        final_system_prompt = base_system_prompt
                    max_retries = 10
                    for retry in range(max_retries):
                        try:
                            time.sleep(2)
                            retry_start_time = time.time()
                            # 🔥 重试时使用相同的final_system_prompt（暂时不使用thinking-checking格式要求）
                            response = client.chat.completions.create(
                                model=full_model_name,
                                messages=[
                                    {"role": "system", "content": final_system_prompt},
                                    {"role": "user", "content": user_prompt}
                                ],
                                timeout=150,
                                max_tokens=hyper_para.max_tokens,
                                temperature=hyper_para.temperature
                            )
                            retry_elapsed_time = time.time() - retry_start_time

                            if retry_elapsed_time > 150:
                                print(
                                    f"[_generate_full_boundary_summary] 重试{retry + 1}次成功但耗时{retry_elapsed_time:.2f}秒超过150秒，继续重试")
                                continue

                            raw_content = response.choices[0].message.content.strip()
                            # 🔥 后处理：如果是claude模型，去除thinking和checking块（预防性处理，暂时不使用thinking-checking格式）
                            response_content = _clean_claude_response(raw_content, model_name)
                            print(
                                f"[_generate_full_boundary_summary] 重试{retry + 1}次后成功生成全文边界问题描述汇总，耗时{retry_elapsed_time:.2f}秒，长度{len(response_content)}字")
                            return response_content
                        except Exception as e2:
                            print(f"[_generate_full_boundary_summary] 重试{retry + 1}次失败: {e2}")
                            if retry == max_retries - 1:
                                print(f"[_generate_full_boundary_summary] 所有重试均失败")
                                return None
                continue

        return None
    except Exception as e:
        print(f"[_generate_full_boundary_summary] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _extract_title_change_keywords(old_name, new_name):
    """
    🔥 需求②：提取标题修改前后的差异词（用于添加到关键词中）

    参数:
        old_name: 旧标题
        new_name: 新标题

    返回: 差异词列表（每个词<=3字），例如：["动词", "修饰词", "数量词"]等
    """
    try:
        if not old_name or not new_name or old_name == new_name:
            return []

        change_keywords = []
        import re

        # 🔥 方法1：检查前缀差异（如："司岁备物" -> "本草司岁备物"，提取"本草"）
        if new_name.startswith(old_name):
            prefix = new_name[:len(new_name) - len(old_name)]
            if prefix and len(prefix) <= 3:
                change_keywords.append(prefix)
        elif old_name.startswith(new_name):
            prefix = old_name[:len(old_name) - len(new_name)]
            if prefix and len(prefix) <= 3:
                change_keywords.append(prefix)

        # 🔥 方法2：检查后缀差异
        if new_name.endswith(old_name):
            suffix = new_name[len(old_name):]
            if suffix and len(suffix) <= 3:
                change_keywords.append(suffix)
        elif old_name.endswith(new_name):
            suffix = old_name[len(new_name):]
            if suffix and len(suffix) <= 3:
                change_keywords.append(suffix)

        # 🔥 方法3：提取新标题中的连续中文字符序列，找出在旧标题中没有的
        new_sequences = re.findall(r'[\u4e00-\u9fa5]+', new_name)
        for seq in new_sequences:
            # 检查这个序列是否在旧标题中出现
            if seq not in old_name and len(seq) <= 3:
                change_keywords.append(seq)

        # 🔥 方法4：提取新标题中新增的连续字符（包括非中文）
        # 找出新标题中所有连续的字符序列（中文、数字、字母、符号）
        new_all_sequences = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+|[0-9]+|&|、', new_name)
        old_all_sequences = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+|[0-9]+|&|、', old_name)
        old_all_sequences_set = set(old_all_sequences)
        for seq in new_all_sequences:
            if seq not in old_all_sequences_set:
                # 只保留长度<=3的序列
                if len(seq) <= 3:
                    change_keywords.append(seq)

        # 去重并限制长度
        change_keywords = list(set(change_keywords))[:5]  # 最多5个

        print(f"[_extract_title_change_keywords] 从标题修改中提取差异词: {old_name} -> {new_name}, 差异词: {change_keywords}")
        return change_keywords
    except Exception as e:
        print(f"[_extract_title_change_keywords] 提取差异词失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _calculate_name_similarity(name1, name2):
    """
    计算两个名称的相似度
    返回0到1之间的值，值越大表示相似度越高

    判断规则：
    1. 如果名称完全相同，返回1.0
    2. 如果存在连续3个或更多字符在新旧名称里都出现，返回0.8（高度相似）
    3. 否则使用Jaccard相似度
    """
    if not name1 or not name2:
        return 0.0

    # 完全相同
    if name1 == name2:
        return 1.0

    # 🔥 检查是否有连续3个或更多字符在两个名称中都出现（高度相似）
    # 检查name1中所有长度为3及以上的子串是否在name2中出现
    for i in range(len(name1) - 2):  # 至少3个字符
        for length in range(3, len(name1) - i + 1):  # 从3个字符开始，直到字符串末尾
            substr = name1[i:i + length]
            if substr in name2:
                # 找到连续3个或更多字符匹配，认为是高度相似
                print(f"[_calculate_name_similarity] 发现连续{length}个字符匹配: '{substr}', 判定为高度相似 (0.8)")
                return 0.8

    # 同样检查name2中的子串是否在name1中出现
    for i in range(len(name2) - 2):
        for length in range(3, len(name2) - i + 1):
            substr = name2[i:i + length]
            if substr in name1:
                print(f"[_calculate_name_similarity] 发现连续{length}个字符匹配: '{substr}', 判定为高度相似 (0.8)")
                return 0.8

    # 没有连续3个字符匹配，使用Jaccard相似度
    # 转换为字符集合
    set1 = set(name1)
    set2 = set(name2)

    # 计算交集（同时出现的字符）
    intersection = set1.intersection(set2)

    # 计算并集（所有出现的字符）
    union = set1.union(set2)

    # 避免除以零
    if len(union) == 0:
        return 0.0

    # 相似度 = 交集大小 / 并集大小（Jaccard相似度）
    similarity = len(intersection) / len(union)

    return similarity


def _extract_sections_for_scoring(full_article, directory_structure):
    """
    🔥 提取各章各节内容用于红蓝卡标评分

    参数:
        full_article: 完整文章内容
        directory_structure: 目录结构

    返回: [
        {
            'chapter_name': '章名',
            'section_name': '节名'（如果没有节则为None）,
            'content': '节的内容（若有小节的节，包含所有小节内容）',
            'chapter_idx': 章节索引,
            'section_idx': 节索引（如果为None表示无节）
        },
        ...
    ]
    """
    try:
        sections = []
        chapters = directory_structure.get('chapters', [])

        # 解析文章结构
        parsed_structure = _parse_existing_article_structure(full_article, directory_structure)

        for chapter_idx, chapter in enumerate(chapters):
            chapter_name = chapter.get('name', '')
            chapter_sections = chapter.get('sections', [])

            if not chapter_sections:
                # 如果某章无节，则考虑章
                key = (chapter_idx, None, None)
                content = parsed_structure.get(key, '')
                if content:
                    sections.append({
                        'chapter_name': chapter_name,
                        'section_name': None,
                        'content': content,
                        'chapter_idx': chapter_idx,
                        'section_idx': None
                    })
            else:
                # 如果有节，考虑每个节（包含所有小节内容）
                for section_idx, section in enumerate(chapter_sections):
                    section_name = section.get('name', '')
                    subsections = section.get('subsections', [])

                    if not subsections:
                        # 如果没有小节，使用节本身的内容
                        key = (chapter_idx, section_idx, None)
                        section_content = parsed_structure.get(key, '')
                        if section_content:
                            sections.append({
                                'chapter_name': chapter_name,
                                'section_name': section_name,
                                'content': section_content,
                                'chapter_idx': chapter_idx,
                                'section_idx': section_idx
                            })
                    else:
                        # 如果有小节，获取该节的所有小节内容并合并
                        section_content_parts = []
                        for subsection_idx, subsection in enumerate(subsections):
                            key = (chapter_idx, section_idx, subsection_idx)
                            subsection_content = parsed_structure.get(key, '')
                            if subsection_content:
                                section_content_parts.append(subsection_content)

                        # 合并所有小节内容
                        section_content = '\n\n'.join(section_content_parts)
                        if section_content:
                            sections.append({
                                'chapter_name': chapter_name,
                                'section_name': section_name,
                                'content': section_content,
                                'chapter_idx': chapter_idx,
                                'section_idx': section_idx
                            })

        print(f"[_extract_sections_for_scoring] 提取到{len(sections)}个节用于评分")
        return sections
    except Exception as e:
        print(f"[_extract_sections_for_scoring] 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _score_sections_with_small_model(sections, username):
    """
    🔥 调用8卡服务端小模型对各节进行红蓝卡标评分

    参数:
        sections: 节列表（从_extract_sections_for_scoring获取）
        username: 用户名

    返回: [
        {
            'chapter_name': '章名',
            'section_name': '节名',
            'score': 分数(0-5),
            'color': '红'/'蓝'/'紫',
            'reason': '打分理由及迭代建议'
        },
        ...
    ]
    """
    try:
        scored_sections = []
        real_name = username.split('_')[0] if '_' in username else username

        for section in sections:
            try:
                content = section['content']
                chapter_name = section['chapter_name']
                section_name = section['section_name'] or chapter_name

                # 检查是否有括号内标注xxx在文献原文支撑度低/未出现等置信度相关的描述
                confidence_penalty = 0.0
                confidence_notes = re.findall(r'[（(][^）)]*?(?:支撑度低|未出现|置信度|置信)[^）)]*?[）)]', content)
                if confidence_notes:
                    # 根据置信度描述数量适当扣分（每个描述扣0.2-0.5分）
                    confidence_penalty = min(len(confidence_notes) * 0.3, 1.5)
                    print(
                        f"[_score_sections_with_small_model] {section_name}发现{len(confidence_notes)}处置信度相关描述，扣分{confidence_penalty:.2f}")

                # 构建输入文本
                input_text = f"章节：{chapter_name}"
                if section['section_name']:
                    input_text += f" > {section['section_name']}"
                input_text += f"\n\n内容：\n{content}"

                # 处理特殊字符
                input_text_processed = input_text.replace("\n", "\\n")
                input_text_processed = input_text_processed.replace('```', '').replace('"""', '').replace('"',
                                                                                                          '“').replace(
                    "'", '‘')

                # 构造请求数据
                request_data = {
                    "input_text": input_text_processed,
                    # "user_name": real_name,
                    "user_name": username,
                    "task_type": "section_scoring"
                }

                # 使用requests库发送POST请求
                server_url = get_small_model_server_url(username)
                response = requests.post(
                    f'{server_url}/get_depth_suggestion',
                    json=request_data,
                    headers={"Content-Type": "application/json"},
                    timeout=120
                )

                if response.status_code != 200:
                    print(f"[_score_sections_with_small_model] HTTP请求失败，状态码: {response.status_code}")
                    continue

                result_data = response.json()
                if result_data.get('error_num') != 0:
                    print(f"[_score_sections_with_small_model] 评分失败: {result_data.get('message', '未知错误')}")
                    continue

                response_content = result_data.get('suggestion', '')
                if not response_content:
                    continue

                # 解析评分结果（格式：理由_分数_颜色，例如：达到红蓝融合第一层..._3.5_紫色）
                # 尝试匹配"理由_分数_颜色"格式
                score_match = re.search(r'(.+?)_(\d+(?:\.\d+)?)_([^_]+)$', response_content)
                if not score_match:
                    # 如果新格式匹配失败，尝试旧格式"分数_颜色_理由"（向后兼容）
                    score_match = re.search(r'(\d+(?:\.\d+)?)_([^_]+)_(.+)', response_content)
                    if score_match:
                        score_str = score_match.group(1)
                        color_str = score_match.group(2)
                        reason_str = score_match.group(3).strip()
                    else:
                        print(f"[_score_sections_with_small_model] 无法解析评分结果: {response_content[:100]}")
                        continue
                else:
                    reason_str = score_match.group(1).strip()
                    score_str = score_match.group(2)
                    color_str = score_match.group(3).strip()

                score = float(score_str)
                # 应用置信度扣分
                score = max(0.0, score - confidence_penalty)

                # 🔥 后处理：如果分数低于2.8分，提高到2.8分（除非是明显异常的情况）
                original_score = score
                if score < 2.8:
                    score = 2.8
                    print(f"[_score_sections_with_small_model] {section_name}分数从{original_score:.2f}分提高到2.8分")

                # 确定颜色：0-1分为红或蓝，≥1分为紫
                if score < 1.0:
                    # 根据reason或score判断是红还是蓝（通常0-0.5为红，0.5-1.0为蓝）
                    if score < 0.5 or '红' in color_str:
                        color = '红'
                    else:
                        color = '蓝'
                else:
                    color = '紫'

                scored_sections.append({
                    'chapter_name': chapter_name,
                    'section_name': section_name,
                    'score': score,
                    'color': color,
                    'reason': reason_str
                })
                print(
                    f"[_score_sections_with_small_model] {section_name}评分: {score:.2f}分, {color}, 理由: {reason_str[:50]}...")

            except Exception as e:
                print(
                    f"[_score_sections_with_small_model] 评分{section.get('section_name', section.get('chapter_name', ''))}失败: {e}")
                import traceback
                traceback.print_exc()
                continue

        # 🔥 后处理：如果评分数量>5且没有≥4分的，将最高分的两处提高到4.0分
        if len(scored_sections) > 5:
            max_score = max(section['score'] for section in scored_sections) if scored_sections else 0
            if max_score < 4.0:
                # 找到最高分的两处（如果只有一处，只提高一处）
                sorted_sections = sorted(scored_sections, key=lambda x: x['score'], reverse=True)
                sections_to_boost = sorted_sections[:2]  # 取前两个最高分

                for section in sections_to_boost:
                    original_score = section['score']
                    section['score'] = 4.0
                    section['color'] = '紫'  # 4.0分应该是紫色
                    section_label = section['section_name'] if section['section_name'] else section['chapter_name']
                    print(
                        f"[_score_sections_with_small_model] 🔥 后处理：{section_label}分数从{original_score:.2f}分提高到4.0分（因为评分数量>5且没有≥4分的）")

        return scored_sections
    except Exception as e:
        print(f"[_score_sections_with_small_model] 评分过程失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _generate_thinking_checking_with_claude(scored_sections, directory_structure, full_article, username):
    """
    🔥 调用Claude生成thinking/checking代码块

    参数:
        scored_sections: 评分结果列表
        directory_structure: 目录结构
        full_article: 完整文章内容
        username: 用户名

    返回: thinking/checking代码块字符串（只包含thinking和checking块，不包含最终回答）
    """
    try:
        from app_chat.views import system_prompt_claude
        from app_chat.config.config_manager import config_manager

        # 构建红蓝卡标信息文本
        scoring_info = "各章节红蓝卡标评分信息：\n\n"
        for scored in scored_sections:
            section_label = scored['section_name'] if scored['section_name'] else scored['chapter_name']
            scoring_info += f"- {scored['chapter_name']}"
            if scored['section_name']:
                scoring_info += f" > {scored['section_name']}"
            scoring_info += f": {scored['score']:.2f}分 ({scored['color']}), {scored['reason']}\n"

        # 构建目录结构文本
        directory_text = _format_directory_structure_text(directory_structure)

        # 构建用户prompt
        user_prompt = f"""请对以下迭代完成后的全文内容进行深度思考和分析。

目录结构：
{directory_text}

{scoring_info}

完整文章内容：
{full_article[:10000]}...

请使用thinking-checking格式进行思考：

**thinking部分要求（字数不超过500字）：**
请按照人性化思考协议的要求，以自然流畅的思维流动方式，对迭代完成后的全文内容进行深度思考和分析。**不必严格按照固定格式或固定部分输出**，而是应该：

1. **自然意识流启动**：保持思维自由开放地流动，记录对全文内容的初始整体印象，允许自发的联想和初步感知。

2. **多模态感知激活**：构建对文章内容的丰富场景感知，从多个维度理解文章：
   - 视觉化文章的整体结构和逻辑脉络
   - 感知文章的情感基调和表达风格
   - 识别文章中的关键概念、核心关键词、专业术语等

3. **直觉系统运作**：捕捉对文章的首要印象，识别潜在的模式和结构，形成对以下方面的初步判断：
   - 目录标题和报告主题的核心含义、研究目标、理论框架
   - 整体报告和各个章节的撰写质量（逻辑性、深度、实证性等）
   - 各章节之间的逻辑关联、递进关系、衔接情况

4. **推理系统参与主导**：以树分支、图连接的方式深入分析：
   - 各章节内涵要体现哪些方向、核心内容、自洽不脱节的创新亮点、有无多种路径的取优、差异化体现
   - 识别报告中可能存在的问题边界、概念边界、理论边界、实证边界等
   - 分析现有内容与预期目标的差异和不足
   - 思考如何进一步精进报告（内容深化、逻辑完善、实证补充等方向）

5. **深度思考整合**：综合多维视角，提炼核心见解，建立不同思考之间的深层联系，形成对文章的整体评估和优化建议。

**重要要求**：
- thinking中提及的内容一定要和迭代完成后的全文各部分具体内容能够匹配得上，即thinking中提及的要和具体对应内容中一致
- **使用流畅的意识流表达，形象、生动地展现完整的思维过程，不必拘泥于固定格式或固定部分**
- 自然舒展地表达，逐层深入分析，展示认知的发展过程，揭示思维的转折点和关键洞察
- **thinking部分不需要考虑也不需要提到红蓝卡标度量信息**

**checking部分要求（字数不超过400字）：**
在checking中考虑：这些红蓝卡标度量信息，比对现有内容和预期的差异/误差及校正建议。
**重要要求**：
- 各章每一节的红蓝卡标都要挨个说一遍，不要遗漏
- **必须明确输出每一章节的得分（x.x分）信息**，格式如："第一章第一节（x.x分）：..."
- 针对每个章节的得分情况，比对现有内容和预期的差异/误差，提出校正建议

**输出要求**：
只需要thinking/checking代码块，不需要最终回答。如果生成了最后部分，要去掉，只留下thinking/checking代码块。"""

        # 获取Claude模型配置
        from app_chat.scene_models import get_scene_abbr_chain
        model_config = None
        for abbr in get_scene_abbr_chain(
            ['output_article_claude_1', 'output_article_claude_2', 'output_article_claude_3'],
            ['claude-sonnet-4.5', 'claude-4-sonnet', 'claude37'],
        ):
            model_config = config_manager.get_model_config(abbr)
            if model_config:
                break

        if not model_config:
            print("[_generate_thinking_checking_with_claude] 未找到Claude模型配置")
            return ""

        cur_config = model_config.get_config()
        api_key = cur_config.get("openai_api_key", "")
        base_url = cur_config.get("openai_api_base", "https://api.anthropic.com/v1/")

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={"x-foo": "true"}
        )

        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt_claude + "\n\n请你按照如上人性化思考协议的要求，思考并完成任务。"},
            {"role": "user", "content": user_prompt}
        ]

        # 🔥 最多重试3次，确保生成完整的thinking和checking块
        max_retries = 3
        for retry in range(max_retries):
            response = client.chat.completions.create(
                model=cur_config.get("model_name", "claude-sonnet-4-20250514"),
                messages=messages,
                temperature=0.6,
                max_tokens=12888
            )

            response_text = response.choices[0].message.content

            # 提取thinking/checking代码块，移除最终回答部分
            thinking_checking_blocks = []

            # 匹配所有```thinking...```块
            thinking_pattern = r'```thinking\s*\n(.*?)```'
            thinking_matches = re.findall(thinking_pattern, response_text, re.DOTALL | re.IGNORECASE)
            for match in thinking_matches:
                thinking_checking_blocks.append(f"```thinking\n{match.strip()}\n```")

            # 匹配所有```checking...```块
            checking_pattern = r'```checking\s*\n(.*?)```'
            checking_matches = re.findall(checking_pattern, response_text, re.DOTALL | re.IGNORECASE)
            for match in checking_matches:
                thinking_checking_blocks.append(f"```checking\n{match.strip()}\n```")

            # 检查是否同时有thinking和checking块
            has_thinking = len(thinking_matches) > 0
            has_checking = len(checking_matches) > 0

            if has_thinking and has_checking:
                # 同时有thinking和checking块，返回结果
                result = '\n\n'.join(thinking_checking_blocks)
                print(f"[_generate_thinking_checking_with_claude] 成功生成完整的thinking/checking代码块，长度: {len(result)}字")
                return result
            else:
                # 缺少thinking或checking块，记录并重试
                missing_parts = []
                if not has_thinking:
                    missing_parts.append("thinking")
                if not has_checking:
                    missing_parts.append("checking")
                print(f"[_generate_thinking_checking_with_claude] 第{retry + 1}次生成缺少{', '.join(missing_parts)}块，进行重试...")
                # 🔥 打印原始响应内容用于调试
                print(f"[_generate_thinking_checking_with_claude] 原始响应内容:\n{response_text[:5000]}")
                if retry == max_retries - 1:
                    # 最后一次重试也失败，打印完整响应内容
                    print(f"[_generate_thinking_checking_with_claude] ⚠️ 最后一次重试失败，完整响应内容:\n{response_text}")
                    result = '\n\n'.join(thinking_checking_blocks)
                    print(
                        f"[_generate_thinking_checking_with_claude] ⚠️ 警告：重试{max_retries}次后仍缺少{', '.join(missing_parts)}块，返回不完整结果，长度: {len(result)}字")
                    return result

        print("[_generate_thinking_checking_with_claude] 未能提取thinking/checking代码块")
        return ""

    except Exception as e:
        print(f"[_generate_thinking_checking_with_claude] 生成失败: {e}")
        import traceback
        traceback.print_exc()

        # 🔥 需求（1）：失败时给2次重试机会，重试时换claude-4-sonnet
        try:
            from app_chat.views import system_prompt_claude
            from app_chat.config.config_manager import config_manager

            # 重新构建必要的内容（异常可能发生在try块早期，需要重新构建）
            scoring_info = "各章节红蓝卡标评分信息：\n\n"
            for scored in scored_sections:
                section_label = scored['section_name'] if scored['section_name'] else scored['chapter_name']
                scoring_info += f"- {scored['chapter_name']}"
                if scored['section_name']:
                    scoring_info += f" > {scored['section_name']}"
                scoring_info += f": {scored['score']:.2f}分 ({scored['color']}), {scored['reason']}\n"

            directory_text = _format_directory_structure_text(directory_structure)

            user_prompt = f"""请对以下迭代完成后的全文内容进行深度思考和分析。

目录结构：
{directory_text}

{scoring_info}

完整文章内容：
{full_article[:10000]}...

请使用thinking-checking格式进行思考：

**thinking部分要求（字数不超过500字）：**
请按照人性化思考协议的要求，以自然流畅的思维流动方式，对迭代完成后的全文内容进行深度思考和分析。**不必严格按照固定格式或固定部分输出**，而是应该：

1. **自然意识流启动**：保持思维自由开放地流动，记录对全文内容的初始整体印象，允许自发的联想和初步感知。

2. **多模态感知激活**：构建对文章内容的丰富场景感知，从多个维度理解文章：
   - 视觉化文章的整体结构和逻辑脉络
   - 感知文章的情感基调和表达风格
   - 识别文章中的关键概念、核心关键词、专业术语等

3. **直觉系统运作**：捕捉对文章的首要印象，识别潜在的模式和结构，形成对以下方面的初步判断：
   - 目录标题和报告主题的核心含义、研究目标、理论框架
   - 整体报告和各个章节的撰写质量（逻辑性、深度、实证性等）
   - 各章节之间的逻辑关联、递进关系、衔接情况

4. **推理系统参与主导**：以树分支、图连接的方式深入分析：
   - 各章节内涵要体现哪些方向、核心内容、自洽不脱节的创新亮点、有无多种路径的取优、差异化体现
   - 识别报告中可能存在的问题边界、概念边界、理论边界、实证边界等
   - 分析现有内容与预期目标的差异和不足
   - 思考如何进一步精进报告（内容深化、逻辑完善、实证补充等方向）

5. **深度思考整合**：综合多维视角，提炼核心见解，建立不同思考之间的深层联系，形成对文章的整体评估和优化建议。

**重要要求**：
- thinking中提及的内容一定要和迭代完成后的全文各部分具体内容能够匹配得上，即thinking中提及的要和具体对应内容中一致
- **使用流畅的意识流表达，形象、生动地展现完整的思维过程，不必拘泥于固定格式或固定部分**
- 自然舒展地表达，逐层深入分析，展示认知的发展过程，揭示思维的转折点和关键洞察
- **thinking部分不需要考虑也不需要提到红蓝卡标度量信息**

**checking部分要求（字数不超过400字）：**
在checking中考虑：这些红蓝卡标度量信息，比对现有内容和预期的差异/误差及校正建议。
**重要要求**：
- 各章每一节的红蓝卡标都要挨个说一遍，不要遗漏
- **必须明确输出每一章节的得分（x.x分）信息**，格式如："第一章第一节（x.x分）：..."
- 针对每个章节的得分情况，比对现有内容和预期的差异/误差，提出校正建议

**输出要求**：
只需要thinking/checking代码块，不需要最终回答。如果生成了最后部分，要去掉，只留下thinking/checking代码块。"""

            messages = [
                {"role": "system", "content": system_prompt_claude + "\n\n请你按照如上人性化思考协议的要求，思考并完成任务。"},
                {"role": "user", "content": user_prompt}
            ]
        except Exception as rebuild_e:
            print(f"[_generate_thinking_checking_with_claude] 重试前重建内容失败: {rebuild_e}")
            return ""

        retry_models = ['claude-4-sonnet', 'claude-3.7', 'claude-3.5']
        for retry_idx, retry_model_name in enumerate(retry_models[:2]):  # 最多重试2次
            try:
                print(f"[_generate_thinking_checking_with_claude] 🔥 第{retry_idx + 1}次重试，使用模型: {retry_model_name}")
                retry_model_config = config_manager.get_model_config(retry_model_name)
                if not retry_model_config:
                    print(f"[_generate_thinking_checking_with_claude] ⚠️ 未找到模型配置: {retry_model_name}，跳过")
                    continue

                retry_cur_config = retry_model_config.get_config()
                retry_api_key = retry_cur_config.get("openai_api_key", "")
                retry_base_url = retry_cur_config.get("openai_api_base", "https://api.anthropic.com/v1/")

                retry_client = OpenAI(
                    api_key=retry_api_key,
                    base_url=retry_base_url,
                    default_headers={"x-foo": "true"}
                )

                retry_response = retry_client.chat.completions.create(
                    model=retry_cur_config.get("model_name", retry_model_name),
                    messages=messages,
                    temperature=0.6,
                    max_tokens=12888,
                    timeout=150
                )

                retry_response_text = retry_response.choices[0].message.content

                # 提取thinking/checking代码块
                retry_thinking_checking_blocks = []
                retry_thinking_pattern = r'```thinking\s*\n(.*?)```'
                retry_thinking_matches = re.findall(retry_thinking_pattern, retry_response_text,
                                                    re.DOTALL | re.IGNORECASE)
                for match in retry_thinking_matches:
                    retry_thinking_checking_blocks.append(f"```thinking\n{match.strip()}\n```")

                retry_checking_pattern = r'```checking\s*\n(.*?)```'
                retry_checking_matches = re.findall(retry_checking_pattern, retry_response_text,
                                                    re.DOTALL | re.IGNORECASE)
                for match in retry_checking_matches:
                    retry_thinking_checking_blocks.append(f"```checking\n{match.strip()}\n```")

                retry_has_thinking = len(retry_thinking_matches) > 0
                retry_has_checking = len(retry_checking_matches) > 0

                if retry_has_thinking and retry_has_checking:
                    retry_result = '\n\n'.join(retry_thinking_checking_blocks)
                    print(
                        f"[_generate_thinking_checking_with_claude] ✅ 重试成功，使用模型{retry_model_name}生成完整的thinking/checking代码块，长度: {len(retry_result)}字")
                    return retry_result
                else:
                    missing_parts = []
                    if not retry_has_thinking:
                        missing_parts.append("thinking")
                    if not retry_has_checking:
                        missing_parts.append("checking")
                    print(
                        f"[_generate_thinking_checking_with_claude] ⚠️ 重试{retry_idx + 1}次仍缺少{', '.join(missing_parts)}块")
                    if retry_idx < len(retry_models[:2]) - 1:
                        continue  # 继续下一次重试
                    else:
                        # 最后一次重试也失败，返回不完整结果
                        retry_result = '\n\n'.join(retry_thinking_checking_blocks)
                        if retry_result:
                            print(
                                f"[_generate_thinking_checking_with_claude] ⚠️ 所有重试均失败，返回不完整结果，长度: {len(retry_result)}字")
                            return retry_result
            except Exception as retry_e:
                print(f"[_generate_thinking_checking_with_claude] 重试{retry_idx + 1}次失败: {retry_e}")
                if retry_idx < len(retry_models[:2]) - 1:
                    continue  # 继续下一次重试
                else:
                    print(f"[_generate_thinking_checking_with_claude] ⚠️ 所有重试均失败")

        return ""


def _compare_directory_and_article_structure(directory_structure, article_content):
    """
    🔥 对比目录结构和正文结构，找出差异（增删改）
    按照序号直接对比：目录中的"一、"对应正文中的"## 一、"，"1."对应"### 1."，"A."对应"#### A."

    参数:
        directory_structure: 目录结构（从目录部分解析）
        article_content: 正文内容

    返回: {
        'modified': [(chapter_idx, section_idx, subsection_idx, old_name, new_name), ...],  # 改：名称变化
        'deleted': [(chapter_idx, section_idx, subsection_idx, name), ...],  # 删：正文中有但目录中没有
        'added': [(chapter_idx, section_idx, subsection_idx, name), ...],  # 增：目录中有但正文中没有
    }
    """
    try:
        # 🔥 特殊部分，不参与对比
        special_sections = {'摘要', '关键词', '参考文献', '边界问题描述'}

        if not article_content:
            # 如果没有正文，所有目录项都是新增
            added = []
            chapters = directory_structure.get('chapters', [])
            for chapter_idx, chapter in enumerate(chapters):
                if not chapter.get('sections'):
                    added.append((chapter_idx, None, None, chapter['name']))
                else:
                    for section_idx, section in enumerate(chapter['sections']):
                        if not section.get('subsections'):
                            added.append((chapter_idx, section_idx, None, section['name']))
                        else:
                            for subsection_idx, subsection in enumerate(section['subsections']):
                                added.append((chapter_idx, section_idx, subsection_idx, subsection['name']))

            return {
                'modified': [],
                'deleted': [],
                'added': added
            }

        # 🔥 解析正文结构：提取所有章节标题及其序号
        # {(chapter_num, section_num, subsection_num): 'name'} 其中num是序号索引（一=0, 二=1, ...; 1=0, 2=1, ...; A=0, B=1, ...）
        article_by_num = {}  # {(ch_num, sec_num, subsec_num): 'name'}
        lines = article_content.split('\n')

        current_ch_num = None  # 当前章序号（索引）
        current_sec_num = None  # 当前节序号（索引）

        for line in lines:
            line_stripped = line.strip()

            if line_stripped.startswith('## '):
                chapter_title = line_stripped[3:].strip()
                # 🔥 支持中文数字：一、二、...十、十一、十二、...
                chapter_name = re.sub(r'^[一二三四五六七八九十百]+[、.]\s*', '', chapter_title).strip()

                # 跳过特殊部分
                if chapter_name in special_sections or any(special in chapter_name for special in special_sections):
                    current_ch_num = None
                    current_sec_num = None
                    continue

                # 🔥 提取章序号：使用中文数字转换函数，支持一到九十九
                match = re.match(r'^([一二三四五六七八九十百]+)[、.]', chapter_title)
                if match:
                    chinese_num_str = match.group(1)
                    ch_num = _chinese_num_to_int(chinese_num_str)
                    if ch_num is not None:
                        current_ch_num = ch_num - 1  # 转换为索引（一=0, 二=1, ...）
                        current_sec_num = None
                        article_by_num[(current_ch_num, None, None)] = chapter_name
                    else:
                        current_ch_num = None
                        current_sec_num = None
                else:
                    current_ch_num = None
                    current_sec_num = None

            elif line_stripped.startswith('### '):
                section_title = line_stripped[4:].strip()
                section_name = re.sub(r'^\d+[.]\s*', '', section_title).strip()

                # 跳过特殊部分
                if section_name in special_sections or any(special in section_name for special in special_sections):
                    current_sec_num = None
                    continue

                # 提取节序号
                match = re.match(r'^(\d+)[.]', section_title)
                if match and current_ch_num is not None:
                    current_sec_num = int(match.group(1)) - 1  # 1->0, 2->1, ...
                    article_by_num[(current_ch_num, current_sec_num, None)] = section_name
                else:
                    current_sec_num = None

            elif line_stripped.startswith('#### '):
                subsection_title = line_stripped[5:].strip()

                # 跳过特殊部分（先检查，避免提取名称）
                temp_subsection_name = re.sub(r'^[A-Z]([.]|[\s\u3000])*\s*', '', subsection_title).strip()
                if temp_subsection_name in special_sections or any(
                        special in temp_subsection_name for special in special_sections):
                    continue

                # 🔥 提取小节序号：兼容 A.xxx、A xxx、Axxx 三种格式
                match = re.match(r'^([A-Z])([.]|[\s\u3000]|)', subsection_title)
                if match and current_ch_num is not None and current_sec_num is not None:
                    subsec_num = ord(match.group(1)) - ord('A')  # A->0, B->1, ...
                    # 提取名称（去掉字母和可能的点号/空格）
                    subsection_name = re.sub(r'^[A-Z]([.]|[\s\u3000])*\s*', '', subsection_title).strip()
                    article_by_num[(current_ch_num, current_sec_num, subsec_num)] = subsection_name

        # 🔥 对比目录和正文
        modified = []
        deleted = []
        added = []

        chapters = directory_structure.get('chapters', [])

        # 遍历目录，找出新增和修改
        for chapter_idx, chapter in enumerate(chapters):
            chapter_name = chapter['name']
            key = (chapter_idx, None, None)

            if key in article_by_num:
                # 正文中有，检查名称是否变化
                if article_by_num[key] != chapter_name:
                    modified.append((chapter_idx, None, None, article_by_num[key], chapter_name))
            else:
                # 目录中有但正文中没有（新增）
                if not chapter.get('sections'):
                    added.append((chapter_idx, None, None, chapter_name))

            if chapter.get('sections'):
                for section_idx, section in enumerate(chapter['sections']):
                    section_name = section['name']
                    key = (chapter_idx, section_idx, None)

                    if key in article_by_num:
                        # 正文中有，检查名称是否变化
                        if article_by_num[key] != section_name:
                            modified.append((chapter_idx, section_idx, None, article_by_num[key], section_name))
                    else:
                        # 目录中有但正文中没有（新增）
                        if not section.get('subsections'):
                            added.append((chapter_idx, section_idx, None, section_name))

                    if section.get('subsections'):
                        for subsection_idx, subsection in enumerate(section['subsections']):
                            subsection_name = subsection['name']
                            key = (chapter_idx, section_idx, subsection_idx)

                            if key in article_by_num:
                                # 正文中有，检查名称是否变化
                                if article_by_num[key] != subsection_name:
                                    modified.append((chapter_idx, section_idx, subsection_idx, article_by_num[key],
                                                     subsection_name))
                            else:
                                # 目录中有但正文中没有（新增）
                                added.append((chapter_idx, section_idx, subsection_idx, subsection_name))

        # 🔥 构建目录中所有名称的映射：{name: [(chapter_idx, section_idx, subsection_idx), ...]}
        # 用于检查名称是否还在目录中（即使序号变了）
        directory_names_map = {}  # {name: [(ch_idx, sec_idx, subsec_idx), ...]}
        for chapter_idx, chapter in enumerate(chapters):
            chapter_name = chapter['name']
            if chapter_name not in directory_names_map:
                directory_names_map[chapter_name] = []
            directory_names_map[chapter_name].append((chapter_idx, None, None))

            if chapter.get('sections'):
                for section_idx, section in enumerate(chapter['sections']):
                    section_name = section['name']
                    if section_name not in directory_names_map:
                        directory_names_map[section_name] = []
                    directory_names_map[section_name].append((chapter_idx, section_idx, None))

                    if section.get('subsections'):
                        for subsection_idx, subsection in enumerate(section['subsections']):
                            subsection_name = subsection['name']
                            if subsection_name not in directory_names_map:
                                directory_names_map[subsection_name] = []
                            directory_names_map[subsection_name].append((chapter_idx, section_idx, subsection_idx))

        # 遍历正文，找出删除（正文中有但目录中没有）
        directory_keys = set()
        for chapter_idx, chapter in enumerate(chapters):
            directory_keys.add((chapter_idx, None, None))
            if chapter.get('sections'):
                for section_idx, section in enumerate(chapter['sections']):
                    directory_keys.add((chapter_idx, section_idx, None))
                    if section.get('subsections'):
                        for subsection_idx, subsection in enumerate(section['subsections']):
                            directory_keys.add((chapter_idx, section_idx, subsection_idx))

        # 🔥 优化删除判断：检查名称是否还在目录中
        def _is_same_level(key1, key2):
            """
            🔥 检查两个key是否属于同一层级（章/节/小节）
            章: (ch_idx, None, None)
            节: (ch_idx, sec_idx, None)
            小节: (ch_idx, sec_idx, subsec_idx)
            """
            # 检查section_idx的None状态
            if (key1[1] is None) != (key2[1] is None):
                return False
            # 检查subsection_idx的None状态
            if (key1[2] is None) != (key2[2] is None):
                return False
            return True

        def _is_same_chapter(key1, key2):
            """
            🔥 检查两个key是否属于同一章
            """
            return key1[0] == key2[0]

        def _calculate_detailed_similarity_score(name1, name2):
            """
            🔥 计算两个名称的详细相似度得分（用于在多个候选匹配中选择最佳匹配）
            返回一个分数，分数越高表示越相似

            考虑因素（优先级从高到低）：
            1. 一个名称是否完全包含在另一个名称中（精确匹配，最高优先级）
            2. 最大连续匹配字符数
            3. 匹配的总字符数
            """
            if not name1 or not name2:
                return 0.0

            # 完全相同
            if name1 == name2:
                return 100000.0

            # 🔥 先计算最大连续匹配字符数（因为包含关系和连续匹配都需要用到）
            max_continuous_match = 0
            for i in range(len(name1)):
                for j in range(i + 1, len(name1) + 1):
                    substr = name1[i:j]
                    if len(substr) >= 2 and substr in name2:  # 至少2个字符
                        max_continuous_match = max(max_continuous_match, len(substr))

            # 同样检查name2中的子串
            for i in range(len(name2)):
                for j in range(i + 1, len(name2) + 1):
                    substr = name2[i:j]
                    if len(substr) >= 2 and substr in name1:
                        max_continuous_match = max(max_continuous_match, len(substr))

            # 如果最大连续匹配小于3，返回0
            if max_continuous_match < 3:
                return 0.0

            # 🔥 检查包含关系（但得分要根据包含长度计算，而不是固定高分）
            # 包含关系得分：基础分1000 + 包含长度 * 100
            # 例如：5个字符包含 = 1000 + 500 = 1500，15个字符包含 = 1000 + 1500 = 2500
            containment_score = 0.0
            if name1 in name2:
                containment_score = 1000.0 + len(name1) * 100
            elif name2 in name1:
                containment_score = 1000.0 + len(name2) * 100

            # 🔥 最大连续匹配得分：最大连续匹配长度 * 200
            # 例如：5个字符连续匹配 = 1000，15个字符连续匹配 = 3000
            continuous_match_score = max_continuous_match * 200

            # 🔥 计算匹配的总字符数（简化版：使用字符集合的交集）
            chars1 = set(name1)
            chars2 = set(name2)
            common_chars = chars1 & chars2
            total_matched_chars = len(common_chars)
            char_match_score = total_matched_chars * 10  # 字符匹配得分（权重较低）

            # 🔥 最终得分：取包含关系得分和连续匹配得分中的较高者，再加上字符匹配得分
            # 这样长连续匹配（如15个字符 = 3000）可以超过短包含（如5个字符 = 1500）
            base_score = max(containment_score, continuous_match_score)
            final_score = base_score + char_match_score

            return final_score

        truly_deleted = []
        for key, name in article_by_num.items():
            if key not in directory_keys:
                # 正文中有但目录中此序号没有，检查名称是否还在目录中
                if name in directory_names_map:
                    # 名称还在目录中，只是序号变了，应该判定为"修改"（序号变化）
                    # 找到目录中对应的新序号（必须层级匹配）
                    new_keys = directory_names_map[name]
                    # 选择第一个层级匹配的
                    new_key = None
                    for candidate_key in new_keys:
                        if _is_same_level(key, candidate_key):
                            new_key = candidate_key
                            break

                    if new_key:
                        # 检查是否已经在modified中（避免重复）
                        already_in_modified = False
                        for mod in modified:
                            if mod[0] == key[0] and mod[1] == key[1] and mod[2] == key[2]:
                                already_in_modified = True
                                break
                        if not already_in_modified:
                            # 序号变化但名称相同，判定为修改（相似度应该很高）
                            modified.append((new_key[0], new_key[1], new_key[2], name, name))
                            print(f"[_compare_directory_and_article_structure] 序号变化检测: {key} -> {new_key}, 名称: {name}")
                else:
                    # 名称真的不在目录中了，才是真正的删除
                    truly_deleted.append((key[0], key[1], key[2], name))

        # 🔥 优化修改判断：检查是否只是序号变化（名称相同或高度相似）
        # 🔥 关键：当插入新章节导致序号错位时，可能会出现错误的匹配
        # 例如：正文中序号2是"A"，目录中序号2是新插入的"B"，序号3才是"A"
        # 这种情况下，old_name="A"和new_name="B"被错误匹配为修改
        # 我们需要检查old_name是否在目录中的其他位置存在，如果存在，应该判定为序号变化

        truly_modified = []
        processed_article_keys = set()  # 记录已处理的正文key
        processed_dir_keys = set()  # 记录已处理的目录key

        for mod in modified:
            article_key = (mod[0], mod[1], mod[2])  # 正文中的key（实际是目录的新key）
            old_name = mod[3] if len(mod) > 3 else ''
            new_name = mod[4] if len(mod) > 4 else mod[3]

            if old_name == new_name:
                # 名称相同，只是序号变化
                truly_modified.append(mod)
                processed_article_keys.add(article_key)
                processed_dir_keys.add(article_key)
            else:
                # 名称不同，检查old_name是否在目录中的其他位置存在
                if old_name in directory_names_map:
                    old_name_dir_keys = directory_names_map[old_name]
                    # 检查old_name在目录中的位置是否与article_key匹配
                    old_name_in_same_position = article_key in old_name_dir_keys

                    if old_name_in_same_position:
                        # old_name在目录中的相同位置也存在，说明是真正的名称修改
                        truly_modified.append(mod)
                        processed_article_keys.add(article_key)
                        processed_dir_keys.add(article_key)
                    else:
                        # old_name在目录中存在，但位置不同，说明可能是序号错位或名称相似
                        # 🔥 改进策略：同时考虑精确匹配（old_name在目录中的位置）和相似匹配（高度相似的名称）
                        # 收集所有候选匹配（包括精确匹配和相似匹配），选择得分最高的
                        candidate_matches = []  # [(dir_name, dir_key, score), ...]

                        # 1. 精确匹配：old_name在目录中的位置（如果找到合适的位置）
                        found_dir_key = None
                        for dir_key in old_name_dir_keys:
                            if dir_key not in processed_dir_keys and _is_same_level(article_key,
                                                                                    dir_key) and _is_same_chapter(
                                article_key, dir_key):
                                found_dir_key = dir_key
                                # 精确匹配得分：100000（最高优先级）
                                candidate_matches.append((old_name, dir_key, 100000.0))
                                break

                        # 2. 相似匹配：查找与old_name高度相似的名称
                        # 🔥 先遍历所有目录名称计算相似度得分，只要得分>0就加入候选列表
                        for dir_name, dir_keys_list in directory_names_map.items():
                            # 跳过old_name本身（已经在精确匹配中处理了）
                            if dir_name == old_name:
                                continue

                            # 计算相似度得分（只要符合3字符匹配，得分就会>0）
                            similarity_score = _calculate_detailed_similarity_score(old_name, dir_name)

                            # 如果得分>0（说明有匹配），检查是否有符合条件的dir_key
                            if similarity_score > 0:
                                for dir_key in dir_keys_list:
                                    # 🔥 关键：必须检查层级是否匹配，且属于同一章（避免跨章错误匹配）
                                    # 🔥 如果dir_key == article_key，允许匹配（因为new_name就是目录中article_key位置的新名称，应该被包含在候选列表中）
                                    if dir_key not in processed_dir_keys and _is_same_level(article_key,
                                                                                            dir_key) and _is_same_chapter(
                                        article_key, dir_key):
                                        candidate_matches.append((dir_name, dir_key, similarity_score))

                        # 如果有候选匹配，选择得分最高的
                        if candidate_matches:
                            # 按得分降序排序，选择得分最高的
                            candidate_matches.sort(key=lambda x: x[2], reverse=True)
                            best_match = candidate_matches[0]
                            found_similar_name = best_match[0]
                            found_dir_key = best_match[1]
                            similarity_score = best_match[2]

                            # 🔥 调试：打印所有候选匹配（前3个）
                            if len(candidate_matches) > 1:
                                print(
                                    f"[_compare_directory_and_article_structure] 调试：old_name={old_name} 有{len(candidate_matches)}个候选匹配：")
                                for i, (cand_name, cand_key, cand_score) in enumerate(candidate_matches[:3]):
                                    print(f"  候选{i + 1}: {cand_name} (key={cand_key}, 得分={cand_score:.1f})")

                            # 使用得分最高的匹配
                            truly_modified.append(
                                (found_dir_key[0], found_dir_key[1], found_dir_key[2], old_name, found_similar_name))
                            processed_article_keys.add(article_key)
                            processed_dir_keys.add(found_dir_key)
                            if found_similar_name == old_name:
                                print(
                                    f"[_compare_directory_and_article_structure] 序号错位检测（精确匹配）: article_key={article_key}(old_name={old_name}, new_name={new_name}) -> dir_key={found_dir_key}({found_similar_name}), 判定为序号变化")
                            else:
                                print(
                                    f"[_compare_directory_and_article_structure] 序号错位检测（相似匹配，得分={similarity_score:.1f}）: article_key={article_key}(old_name={old_name}, new_name={new_name}) -> dir_key={found_dir_key}({found_similar_name}), 判定为序号变化（高度相似）")
                        else:
                            # 所有位置都被处理了，按原逻辑处理
                            truly_modified.append(mod)
                            processed_article_keys.add(article_key)
                            processed_dir_keys.add(article_key)
                else:
                    # old_name不在目录中，检查是否有高度相似的名称（连续3个字符匹配）
                    # 🔥 改进策略：收集所有符合条件的候选，选择相似度得分最高的
                    candidate_matches = []  # [(dir_name, dir_key, score), ...]

                    # 🔥 先遍历所有目录名称计算相似度得分，只要得分>0就加入候选列表
                    for dir_name, dir_keys_list in directory_names_map.items():
                        # 计算相似度得分（只要符合3字符匹配，得分就会>0）
                        similarity_score = _calculate_detailed_similarity_score(old_name, dir_name)

                        # 如果得分>0（说明有匹配），检查是否有符合条件的dir_key
                        if similarity_score > 0:
                            for dir_key in dir_keys_list:
                                # 🔥 关键：必须检查层级是否匹配，且属于同一章（避免跨章错误匹配）
                                # 🔥 如果dir_key == article_key，允许匹配（因为new_name就是目录中article_key位置的新名称，应该被包含在候选列表中）
                                if dir_key not in processed_dir_keys and _is_same_level(article_key,
                                                                                        dir_key) and _is_same_chapter(
                                    article_key, dir_key):
                                    candidate_matches.append((dir_name, dir_key, similarity_score))

                    # 如果有候选匹配，选择得分最高的
                    if candidate_matches:
                        # 按得分降序排序，选择得分最高的
                        candidate_matches.sort(key=lambda x: x[2], reverse=True)
                        best_match = candidate_matches[0]
                        found_similar_name = best_match[0]
                        found_dir_key = best_match[1]
                        similarity_score = best_match[2]

                        # 🔥 调试：打印所有候选匹配（前3个）
                        if len(candidate_matches) > 1:
                            print(
                                f"[_compare_directory_and_article_structure] 调试：old_name={old_name} 有{len(candidate_matches)}个候选匹配：")
                            for i, (cand_name, cand_key, cand_score) in enumerate(candidate_matches[:3]):
                                print(f"  候选{i + 1}: {cand_name} (key={cand_key}, 得分={cand_score:.1f})")

                        # 使用得分最高的匹配
                        truly_modified.append(
                            (found_dir_key[0], found_dir_key[1], found_dir_key[2], old_name, found_similar_name))
                        processed_article_keys.add(article_key)
                        processed_dir_keys.add(found_dir_key)
                        print(
                            f"[_compare_directory_and_article_structure] 序号错位检测（高度相似，得分={similarity_score:.1f}）: article_key={article_key}(old_name={old_name}, new_name={new_name}) -> dir_key={found_dir_key}({found_similar_name}), 判定为序号变化（高度相似）")
                    else:
                        # 没有找到高度相似的名称，是真正的修改（名称变化）
                        truly_modified.append(mod)
                        processed_article_keys.add(article_key)
                        processed_dir_keys.add(article_key)

        # 🔥 重新过滤added列表：只有目录项的名称在原有正文结构中不存在，且该目录项不属于[修改]部分，才是真正的新增
        # 1. 获取正文中所有名称的集合
        article_names = set(article_by_num.values())

        # 2. 获取truly_modified中所有目录key的集合
        truly_modified_dir_keys = set()
        for mod in truly_modified:
            # mod格式: (chapter_idx, section_idx, subsection_idx, old_name, new_name)
            # 目录key是前三个元素
            dir_key = (mod[0], mod[1], mod[2])
            truly_modified_dir_keys.add(dir_key)

        # 3. 检查所有在modified中但未在truly_modified中的项，如果名称不在正文中，则加入added列表
        # 获取所有在modified中的目录key
        modified_dir_keys = set()
        modified_dir_key_to_name = {}  # {dir_key: new_name}
        for mod in modified:
            dir_key = (mod[0], mod[1], mod[2])
            modified_dir_keys.add(dir_key)
            new_name = mod[4] if len(mod) > 4 else mod[3]
            modified_dir_key_to_name[dir_key] = new_name

        # 找出在modified中但未在truly_modified中的项
        for dir_key in modified_dir_keys:
            if dir_key not in truly_modified_dir_keys:
                new_name = modified_dir_key_to_name[dir_key]
                # 如果名称不在正文中，则加入added列表
                if new_name not in article_names:
                    added.append((dir_key[0], dir_key[1], dir_key[2], new_name))

        # 4. 过滤added列表（去重并确保条件满足）
        truly_added = []
        added_keys = set()
        for add_item in added:
            # add_item格式: (chapter_idx, section_idx, subsection_idx, name)
            add_key = (add_item[0], add_item[1], add_item[2])
            add_name = add_item[3]

            # 去重：如果key已经在truly_added中，跳过
            if add_key in added_keys:
                continue
            added_keys.add(add_key)

            # 检查条件：
            # (1) 目录项的名称在原有正文结构中不存在（通过article_by_num的值检查）
            # (2) 该目录项的key不在truly_modified中（即不属于[修改]部分）
            if add_name not in article_names and add_key not in truly_modified_dir_keys:
                truly_added.append(add_item)

        added = truly_added

        # 🔥 打印详细调试信息
        print(
            f"[_compare_directory_and_article_structure] 对比结果: 修改{len(truly_modified)}处, 删除{len(truly_deleted)}处, 新增{len(added)}处")
        if truly_modified:
            print(f"  [修改] {truly_modified}")
        if truly_deleted:
            print(f"  [删除] {truly_deleted}")
        if added:
            print(f"  [新增] {added}")

        return {
            'modified': truly_modified,
            'deleted': truly_deleted,
            'added': added
        }
    except Exception as e:
        print(f"[_compare_directory_and_article_structure] 对比失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            'modified': [],
            'deleted': [],
            'added': []
        }


def _parse_existing_article_structure(article_content, directory_structure):
    """
    🔥 解析已有正文的结构，提取各章节内容

    参数:
        article_content: 正文内容（从# 目录标题开始）
        directory_structure: 目录结构（用于匹配章节）

    返回: {
        (chapter_idx, section_idx, subsection_idx): '内容',
        ...
    }
    """
    try:
        if not article_content:
            return {}

        result = {}
        lines = article_content.split('\n')
        chapters = directory_structure['chapters']

        current_chapter_idx = None
        current_section_idx = None
        current_subsection_idx = None
        current_content_lines = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 检查是否是章节标题（## 开头）
            if line.startswith('## '):
                # 保存上一段内容
                if current_chapter_idx is not None:
                    key = (current_chapter_idx, current_section_idx, current_subsection_idx)
                    content = '\n'.join(current_content_lines).strip()
                    if content:
                        result[key] = content

                # 匹配章标题
                title_text = line[3:].strip()  # 去掉"## "
                current_chapter_idx = None
                for ch_idx, ch in enumerate(chapters):
                    if ch.get('name_with_prefix', ch['name']) == title_text or ch[
                        'name'] in title_text or title_text in ch.get('name_with_prefix', ch['name']):
                        current_chapter_idx = ch_idx
                        current_section_idx = None
                        current_subsection_idx = None
                        current_content_lines = []
                        break
                i += 1
                continue

            # 检查是否是节标题（### 开头）
            if line.startswith('### '):
                # 保存上一段内容
                if current_chapter_idx is not None:
                    key = (current_chapter_idx, current_section_idx, current_subsection_idx)
                    content = '\n'.join(current_content_lines).strip()
                    if content:
                        result[key] = content

                # 匹配节标题
                title_text = line[4:].strip()  # 去掉"### "
                current_section_idx = None
                if current_chapter_idx is not None and current_chapter_idx < len(chapters):
                    ch = chapters[current_chapter_idx]
                    for sec_idx, sec in enumerate(ch.get('sections', [])):
                        if sec.get('name_with_prefix', sec['name']) == title_text or sec[
                            'name'] in title_text or title_text in sec.get('name_with_prefix', sec['name']):
                            current_section_idx = sec_idx
                            current_subsection_idx = None
                            current_content_lines = []
                            break
                i += 1
                continue

            # 检查是否是小节标题（#### 开头）
            if line.startswith('#### '):
                # 保存上一段内容
                if current_chapter_idx is not None:
                    key = (current_chapter_idx, current_section_idx, current_subsection_idx)
                    content = '\n'.join(current_content_lines).strip()
                    if content:
                        result[key] = content

                # 匹配小节标题
                title_text = line[5:].strip()  # 去掉"#### "
                current_subsection_idx = None
                if (current_chapter_idx is not None and current_section_idx is not None and
                        current_chapter_idx < len(chapters)):
                    ch = chapters[current_chapter_idx]
                    if current_section_idx < len(ch.get('sections', [])):
                        sec = ch['sections'][current_section_idx]
                        for subsec_idx, subsec in enumerate(sec.get('subsections', [])):
                            # 🔥 匹配逻辑：支持多种格式（正文中可能有点号也可能没有点号）
                            name_with_prefix = subsec.get('name_with_prefix', subsec['name'])
                            name_with_prefix_alt = subsec.get('name_with_prefix_alt', '')  # 备用格式（带点号）
                            # 去掉title_text中的点号进行比较（如果有点号的话）
                            title_text_no_dot = title_text.replace('.', '') if '.' in title_text else title_text
                            name_with_prefix_no_dot = name_with_prefix.replace('.',
                                                                               '') if '.' in name_with_prefix else name_with_prefix
                            if (name_with_prefix == title_text or
                                    name_with_prefix_alt == title_text or
                                    name_with_prefix_no_dot == title_text_no_dot or
                                    subsec['name'] in title_text or
                                    title_text in name_with_prefix or
                                    (name_with_prefix_alt and title_text in name_with_prefix_alt)):
                                current_subsection_idx = subsec_idx
                                current_content_lines = []
                                break
                i += 1
                continue

            # 🔥 跳过章首/章尾/节首/节尾标记（这些标记后的内容不纳入章节内容）
            if line.startswith('【章首】') or line.startswith('【章尾】') or line.startswith('【节首】') or line.startswith('【节尾】'):
                i += 1
                continue

            # 普通内容行
            if current_chapter_idx is not None:
                current_content_lines.append(lines[i])
            i += 1

        # 保存最后一段内容
        if current_chapter_idx is not None:
            key = (current_chapter_idx, current_section_idx, current_subsection_idx)
            content = '\n'.join(current_content_lines).strip()
            if content:
                result[key] = content

        print(f"[_parse_existing_article_structure] 解析到{len(result)}个章节内容")
        return result
    except Exception as e:
        print(f"[_parse_existing_article_structure] 解析正文结构失败: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _generate_intro_outro(intro_outro_type, parent_name, parent_type, child_contents, directory_title, username,
                          model_priority=['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7', 'claude-3.5'],
                          parent_chapter_name=None):
    """
    🔥 生成章首/章尾/节首/节尾内容

    参数:
        intro_outro_type: 'chapter_intro', 'chapter_outro', 'section_intro', 'section_outro'
        parent_name: 章名或节名
        parent_type: 'chapter' 或 'section'
        child_contents: 下级内容列表（节的列表或小节的列表）
        directory_title: 目录标题
        username: 用户名
        model_priority: 模型优先级列表

    返回: 生成的内容（200-250字，一段话）或 None
    """
    try:
        import time

        base_system_prompt = "你是专业的学术写作专家，擅长撰写章节的开篇和总结。"

        # 根据类型确定角色和字数要求
        if intro_outro_type == 'chapter_intro':
            role = "章首"
            position_desc = "开篇引导"
            dmt_level = "T"  # 章级别属于Top层级
        elif intro_outro_type == 'chapter_outro':
            role = "章尾"
            position_desc = "总结归纳"
            dmt_level = "T"
        elif intro_outro_type == 'section_intro':
            role = "节首"
            position_desc = "开篇引导"
            dmt_level = "M"  # 节级别属于Middle层级
        else:  # section_outro
            role = "节尾"
            position_desc = "总结归纳"
            dmt_level = "M"

        # 构建下级内容文本
        child_contents_text = ""
        for i, child_content in enumerate(child_contents, 1):
            child_contents_text += f"**{i}、**\n{child_content[:500]}\n\n"  # 限制长度

        # 构建DMT层次要求的Prompt
        dmt_requirement = ""
        if dmt_level == "T":
            dmt_requirement = """
**D(Down)M(Middle)T(Top)层次要求（Top层级）**：
- **深度**：要站在全局高度，体现整章的宏观视角和战略思考
- **中层**：要连接各个节的内容，体现章节之间的逻辑关联
- **顶层**：要有总结性和前瞻性，体现整体框架和核心思想
"""
        elif dmt_level == "M":
            dmt_requirement = """
**D(Down)M(Middle)T(Top)层次要求（Middle层级）**：
- **深度**：要深入节内各个小节的细节，体现节的微观视角
- **中层**：要连接各个小节的内容，体现小节之间的逻辑关联
- **顶层**：要有总结性和概括性，体现节的核心要点
"""

        # 🔥 对于节首节尾，添加强调所在章信息的说明
        chapter_context_text = ""
        if parent_type == 'section' and parent_chapter_name:
            chapter_context_text = f"""
**重要：所在章信息**：
- 此节「{parent_name}」位于章「{parent_chapter_name}」中
- **必须明确体现所在章「{parent_chapter_name}」的主题和核心**，内容要围绕节的内容展开，同时明确体现章的指向，不能偏离
- 要体现**立足（节本身）→放眼（所在章）**的关系，节的具体内容为主体，章的宏观指向为辅线
- 避免"由大说小"（不错的废话），而是要以小见大，避免假大空
"""

        user_prompt = f"""请为{parent_type}「{parent_name}」撰写{role}内容（{position_desc}）。

目录标题：{directory_title}

{parent_type}名称：{parent_name}
{chapter_context_text}
该{parent_type}包含的{('节' if parent_type == 'chapter' else '小节')}内容：
{child_contents_text}

要求：
1. **字数要求**：200字左右，绝对不可超过250字
2. **格式要求**：必须是一段话，不可多段或换行
3. **内容要求**：
   - 基于上述下级内容，进行{position_desc}
   - 要简洁明了，不要冗长
   - 要有逻辑性和连贯性
{dmt_requirement}
4. **语言要求**：简洁深刻，有学术性
5. **🔥 极重要：层级指向要求**（针对节首/节尾和章首/章尾）：
   - **小节内容**：要体现节、章的指向，是**立足（小节本身）→面向（所在节）→放眼（所在章）**的关系
   - 这部分占篇幅应该要少，且要精，**不是不错的废话，而是能引发思考的简单而深刻的真正理解**
6. **🔥 极重要：升维与依据的平衡**：
   - 撰写不能是说明书式地机械陈述，做到基于文献等素材讲"对"的话，只能达到60-70分，容易陷入僵化而非有所依据和指向，到不了80或更高
   - 要能够**有引发读者关联思考的空间**，内容应该是**升维的、篇幅字数浓缩精炼的、能够出现涌现的、像人一样思考的**
   - 但也不能随意发散，不能变成散文状
   - **即既要有可升维性的想象空间，也要有可依据的文献文档素材来源支撑，一定要平衡好二者之间的关系，既不僵化，也不随意幻觉**

**重要**：直接输出内容，不要添加任何标题、格式标记或说明，不要分段，就是一段话（200-250字）。
"""

        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                client = OpenAI(api_key=api_key, base_url=base_url)

                start_time = time.time()
                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": base_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )
                elapsed_time = time.time() - start_time

                if elapsed_time > 150:
                    print(f"[_generate_intro_outro] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过150秒，切换模型")
                    continue

                raw_content = response.choices[0].message.content.strip()

                # 确保是单段落（移除换行）
                content = raw_content.replace('\n', '').replace('\r', ' ')
                # 清理多余空格
                content = ' '.join(content.split())

                print(f"[_generate_intro_outro] ✅ 生成{role}成功，{parent_name}，字数: {len(content)}字，耗时: {elapsed_time:.2f}秒")
                return content

            except Exception as e:
                print(f"[_generate_intro_outro] 使用{model_name}失败: {e}")
                continue

                print(f"[_generate_intro_outro] ⚠️ 所有模型都失败，生成{role}失败")
        return None

    except Exception as e:
        print(f"[_generate_intro_outro] 生成{intro_outro_type}失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _iterate_intro_outro(existing_content, intro_outro_type, parent_name, parent_type, child_contents,
                         directory_title, username,
                         model_priority=['claude-sonnet-4.5', 'claude-4-sonnet', 'claude-3.7', 'claude-3.5'],
                         parent_chapter_name=None):
    """
    🔥 迭代章首/章尾/节首/节尾内容

    参数:
        existing_content: 现有的章首/章尾/节首/节尾内容
        intro_outro_type: 'chapter_intro', 'chapter_outro', 'section_intro', 'section_outro'
        parent_name: 章名或节名
        parent_type: 'chapter' 或 'section'
        child_contents: 下级内容列表（节的列表或小节的列表）
        directory_title: 目录标题
        username: 用户名
        model_priority: 模型优先级列表

    返回: 迭代后的内容（<=迭代前字数且<=250字，一段话）或 None
    """
    try:
        import time

        base_system_prompt = "你是专业的学术写作专家，擅长迭代精进章节的开篇和总结。"

        # 计算迭代次数
        iteration_count = _get_iteration_count_from_content(existing_content) + 1

        # 构建前序次标签的描述
        previous_tags_desc = []
        for prev_iter in range(1, iteration_count):
            previous_tags_desc.append(f"<第{prev_iter}次修改内容>")
        if previous_tags_desc:
            previous_tags_text = "、".join(previous_tags_desc)
            previous_tags_rule = f"**前序次标签保留（重要）**：所有前序次数的标签（如{previous_tags_text}等）必须保留，但**标签包裹的内容都可以被修改、删减或浓缩精炼**。前序次标签内的文献引用标记（如[文档名]、[序号]等格式）尽量保留不变。"
        else:
            previous_tags_rule = ""

        # 根据类型确定角色和DMT层次
        if intro_outro_type == 'chapter_intro':
            role = "章首"
            position_desc = "开篇引导"
            dmt_level = "T"
        elif intro_outro_type == 'chapter_outro':
            role = "章尾"
            position_desc = "总结归纳"
            dmt_level = "T"
        elif intro_outro_type == 'section_intro':
            role = "节首"
            position_desc = "开篇引导"
            dmt_level = "M"
        else:  # section_outro
            role = "节尾"
            position_desc = "总结归纳"
            dmt_level = "M"

        # 构建下级内容文本
        child_contents_text = ""
        for i, child_content in enumerate(child_contents, 1):
            child_contents_text += f"**{i}、**\n{child_content[:500]}\n\n"

        # 构建DMT层次要求的Prompt
        dmt_requirement = ""
        if dmt_level == "T":
            dmt_requirement = """
**D(Down)M(Middle)T(Top)层次要求（Top层级）**：
- **深度**：要站在全局高度，体现整章的宏观视角和战略思考
- **中层*：要连接各个节的内容，体现章节之间的逻辑关联
- **顶层**：要有总结性和前瞻性，体现整体框架和核心思想
"""
        elif dmt_level == "M":
            dmt_requirement = """
**D(Down)M(Middle)T(Top)层次要求（Middle层级）**：
- **深度**：要深入节内各个小节的细节，体现节的微观视角
- **中层**：要连接各个小节的内容，体现小节之间的逻辑关联
- **顶层**：要有总结性和概括性，体现节的核心要点
"""

        old_word_count = len(existing_content) if existing_content else 200

        # 🔥 对于节首节尾，添加强调所在章信息的说明
        chapter_context_text = ""
        if parent_type == 'section' and parent_chapter_name:
            chapter_context_text = f"""
**⚠️⚠️⚠️ 重要：所在章信息（必须严格遵守）**：
- 此节「{parent_name}」位于章「{parent_chapter_name}」中
- **必须明确体现所在章「{parent_chapter_name}」的主题和核心**，内容要围绕节的内容展开，同时明确体现章的指向，不能偏离
- 要体现**立足（节本身）→放眼（所在章）**的关系，节的具体内容为主体，章的宏观指向为辅线
- 避免"由大说小"（不错的废话），而是要以小见大，避免假大空
"""

        user_prompt = f"""请对{parent_type}「{parent_name}」的{role}内容进行迭代性精进和修正。

目录标题：{directory_title}

{parent_type}名称：{parent_name}
{chapter_context_text}
该{parent_type}包含的{('节' if parent_type == 'chapter' else '小节')}内容：
{child_contents_text}

现有{role}内容：
{existing_content}

要求：
1. **修改幅度**：可以适当放宽到10-15%，但要确保修改是有实质性提升的，切忌另起炉灶
2. **字数要求（极重要）**：迭代后的字数必须<=迭代前的字数（当前为{old_word_count}字），且绝对不可超过250字。如果需要在某处添加内容，必须在其他弱价值位置删除相应字数，确保总字数不增加或略有减少。
3. **格式要求**：必须是一段话，不可多段或换行
4. **修改标记要求（⚠️⚠️ 极其重要，必须严格遵守）**：
   - 在**真正产生变动的部分**用<第{iteration_count}次修改内容>和</第{iteration_count}次修改内容>包裹
   - **⚠️⚠️ 当前这次<第{iteration_count}次修改内容>包裹部分可以适当放宽到10-15%，但必须确保修改是有实质性提升的！**
   - 此部分应该只占全文的10-15%，其余85%-90%必须完全原样保留
   - 只在真正产生实质性改动、有明显提升的核心部分使用修改标记
{f"5. **{previous_tags_rule}**" if previous_tags_rule else ""}
{f"6." if previous_tags_rule else "5."} **迭代原则**：只在真正需要微调的地方进行修改，没有大改动的话可以基本保持原样
{dmt_requirement}
{f"7. **🔥 极重要：层级指向要求**（针对节首/节尾和章首/章尾）：" if previous_tags_rule else "6. **🔥 极重要：层级指向要求**（针对节首/节尾和章首/章尾）："}
   - **小节内容**：要体现节、章的指向，是**立足（小节本身）→面向（所在节）→放眼（所在章）**的关系
   - 这部分占篇幅应该要少，且要精，**不是不错的废话，而是能引发思考的简单而深刻的真正理解**
{f"8. **🔥 极重要：升维与依据的平衡**：" if previous_tags_rule else "7. **🔥 极重要：升维与依据的平衡**："}
   - 迭代修改不能是说明书式地机械陈述，做到基于文献等素材讲"对"的话，只能达到60-70分，容易陷入僵化而非有所依据和指向，到不了80或更高
   - 要能够**有引发读者关联思考的空间**，内容迭代应该是**升维的、篇幅字数浓缩精炼的、能够出现涌现的、像人一样思考的**
   - 但也不能随意发散，不能变成散文状
   - **即既要有可升维性的想象空间，也要有可依据的文献文档素材来源支撑，一定要平衡好二者之间的关系，既不僵化，也不随意幻觉**
{f"9." if previous_tags_rule else "8."} **⚠️ 用户手动编辑内容保护（极其重要）**：如果存在`***内容***`标记，这些内容必须完全原样保留，包括`***`标记本身。

**重要**：
- **⚠️ 重要：要考虑可能的目录修改分析、变化对比等，但一定不要显式地输出出来。直接输出迭代后的内容，不要有其他任何陈述、分析！**
- 直接输出迭代后的内容，不要添加任何标题、格式标记或说明，不要分段，就是一段话（字数<=迭代前且<=250字）。
"""

        for model_name in model_priority:
            try:
                model_config = config_manager.get_model_config(model_name)
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                client = OpenAI(api_key=api_key, base_url=base_url)

                start_time = time.time()
                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": base_system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    timeout=150,
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )
                elapsed_time = time.time() - start_time

                if elapsed_time > 150:
                    print(f"[_iterate_intro_outro] 使用{model_name}成功但耗时{elapsed_time:.2f}秒超过150秒，切换模型")
                    continue

                raw_content = response.choices[0].message.content.strip()

                # 确保是单段落（移除换行）
                content = raw_content.replace('\n', '').replace('\r', ' ')
                content = ' '.join(content.split())

                # 🔥 检查当前这次<第xx次修改内容>包裹部分的比例，如果超过70%，则不采纳（保持原来的）
                if '<第' in content:
                    import re
                    # 计算当前迭代次数的修改标记比例
                    current_iteration_pattern = rf'<第{iteration_count}次修改内容>(.*?)</第{iteration_count}次修改内容>'
                    matches = re.findall(current_iteration_pattern, content, re.DOTALL)
                    if matches:
                        marked_length = sum(len(match) for match in matches)
                        total_length = len(content)
                        if total_length > 0:
                            marked_ratio = marked_length / total_length
                            print(
                                f"[_iterate_intro_outro] 当前这次<第{iteration_count}次修改内容>包裹部分占比: {marked_ratio:.2%} ({marked_length}/{total_length}字)")
                            if marked_ratio > 0.70:
                                print(f"[_iterate_intro_outro] ⚠️ 修改标记占比{marked_ratio:.2%}超过70%，不采纳迭代结果，保持原内容")
                                return existing_content

                print(
                    f"[_iterate_intro_outro] ✅ 迭代{role}成功，{parent_name}，迭代前: {old_word_count}字，迭代后: {len(content)}字，耗时: {elapsed_time:.2f}秒")
                return content

            except Exception as e:
                print(f"[_iterate_intro_outro] 使用{model_name}失败: {e}")
                continue

        print(f"[_iterate_intro_outro] ⚠️ 所有模型都失败，迭代{intro_outro_type}失败")
        return None

    except Exception as e:
        print(f"[_iterate_intro_outro] 迭代{intro_outro_type}失败: {e}")
        import traceback
        traceback.print_exc()
        return None


@csrf_exempt
def check_and_update_directory_card(request):
    """
    检查并更新目录卡片（将title设为"本子输出目录卡"，contentTitle设为"Sn:xxx"）
    """
    try:
        data = json.loads(request.body)
        card_id = data.get('card_id')
        username = data.get('username')
        scene_name = data.get('scene_name')
        content = data.get('content', '')

        if not card_id or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        # 获取卡片
        try:
            card = Card.objects.get(cid=card_id, username=username)
        except Card.DoesNotExist:
            return JsonResponse({
                'error_num': 1,
                'msg': '卡片不存在'
            })

        # 检查是否符合目录格式：第一行以"目录"结尾
        lines = content.strip().split('\n')
        if not lines or not lines[0].strip().endswith('目录'):
            return JsonResponse({
                'is_directory': False
            })

        # 提取目录名（去掉"目录"两字）
        directory_title = lines[0].strip()[:-2].strip()

        # 获取最后一个子场景的序号
        try:
            scene_obj = scene.objects.get(sceneName=scene_name)
            sub_scenes = scene_obj.subScenes or []
            if sub_scenes:
                last_sub_scene_num = len(sub_scenes)
            else:
                last_sub_scene_num = 1
        except:
            last_sub_scene_num = 1

        # 更新卡片
        card.title = "本子输出目录卡"
        card.contentTitle = f"S{last_sub_scene_num}:{directory_title}"
        card.save()

        return JsonResponse({
            'is_directory': True,
            'title': card.title,
            'contentTitle': card.contentTitle
        })

    except Exception as e:
        print(f"[check_and_update_directory_card] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'处理失败: {str(e)}'
        })


@csrf_exempt
def generate_output_article(request):
    """
    根据目录卡片生成完整的输出文章（支持新生成和迭代精进）

    并发撰写各个章节（最多4个并发）
    """
    from llm_langchain import global_var
    try:
        data = json.loads(request.body)
        card_id = data.get('card_id')
        username = data.get('username')
        scene_name = data.get('scene_name')

        if not card_id or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        # 获取目录卡片
        try:
            directory_card = Card.objects.get(cid=card_id, username=username)
        except Card.DoesNotExist:
            return JsonResponse({
                'error_num': 1,
                'msg': '目录卡片不存在'
            })

        # 检查是否为目录卡
        if directory_card.title != "本子输出目录卡":
            return JsonResponse({
                'error_num': 1,
                'msg': '不是目录卡片'
            })

        # 解析目录结构（只解析目录部分，不包括已生成的文章）
        original_content = directory_card.content or ""

        # 提取目录部分（第一个"# "之前的内容，注意现在用# xxx分隔，而不是## xxx）
        lines = original_content.split('\n')
        directory_end_idx = len(lines)
        for i, line in enumerate(lines):
            if line.strip().startswith('# ') and i > 0:  # 不是第一行，且是章节标题（# xxx）
                directory_end_idx = i
                break

        directory_content = '\n'.join(lines[:directory_end_idx]).rstrip()

        directory_structure = _parse_directory_structure(directory_content)
        if not directory_structure:
            return JsonResponse({
                'error_num': 1,
                'msg': '目录结构解析失败'
            })

        # 🔥 检测是否已有正文内容
        has_existing_article = directory_end_idx < len(lines)

        # 计算字数分配
        word_count_allocation = _calculate_word_count_allocation(directory_structure, target_total_words=5000)
        if not word_count_allocation:
            return JsonResponse({
                'error_num': 1,
                'msg': '字数分配计算失败'
            })

        # 准备所有需要撰写的任务
        writing_tasks = []  # [(section_name, section_type, word_count, parent_section_name, parent_chapter_name, directory_title, ...), ...]

        allocations = word_count_allocation['allocations']['chapters']
        for chapter_idx, chapter_alloc in enumerate(allocations):
            chapter_name = chapter_alloc['name']

            if not chapter_alloc['sections']:
                # 没有节，直接写章
                writing_tasks.append({
                    'section_name': chapter_name,
                    'section_type': 'chapter',
                    'name_with_prefix': chapter_alloc.get('name_with_prefix', chapter_name),
                    'word_count': chapter_alloc['word_count'],
                    'original_word_count': chapter_alloc['word_count'],  # 🔥 保存原始字数
                    'parent_section_name': None,
                    'parent_chapter_name': None,
                    'directory_title': directory_structure['title'],
                    'chapter_idx': chapter_idx,
                    'section_idx': None,
                    'subsection_idx': None
                })
            else:
                for section_idx, section_alloc in enumerate(chapter_alloc['sections']):
                    section_name = section_alloc['name']

                    if not section_alloc['subsections']:
                        # 没有小节，直接写节
                        writing_tasks.append({
                            'section_name': section_name,
                            'section_type': 'section',
                            'name_with_prefix': section_alloc.get('name_with_prefix', section_name),
                            'word_count': section_alloc['word_count'],
                            'original_word_count': section_alloc['word_count'],  # 🔥 保存原始字数
                            'parent_section_name': None,
                            'parent_chapter_name': chapter_name,
                            'directory_title': directory_structure['title'],
                            'chapter_idx': chapter_idx,
                            'section_idx': section_idx,
                            'subsection_idx': None
                        })
                    else:
                        # 有小节，写每个小节
                        for subsection_idx, subsection_alloc in enumerate(section_alloc['subsections']):
                            subsection_name = subsection_alloc['name']

                            # 获取相邻小节列表（用于过渡）
                            adjacent_subsections = []
                            if subsection_idx > 0:
                                prev_subsection = section_alloc['subsections'][subsection_idx - 1]
                                adjacent_subsections.append(prev_subsection['name'])
                            if subsection_idx < len(section_alloc['subsections']) - 1:
                                next_subsection = section_alloc['subsections'][subsection_idx + 1]
                                adjacent_subsections.append(next_subsection['name'])

                            writing_tasks.append({
                                'section_name': subsection_name,
                                'section_type': 'subsection',
                                'name_with_prefix': subsection_alloc.get('name_with_prefix', subsection_name),
                                'word_count': subsection_alloc['word_count'],
                                'original_word_count': subsection_alloc['word_count'],  # 🔥 保存原始字数
                                'parent_section_name': section_name,
                                'parent_chapter_name': chapter_name,
                                'directory_title': directory_structure['title'],
                                'chapter_idx': chapter_idx,
                                'section_idx': section_idx,
                                'subsection_idx': subsection_idx,
                                'adjacent_sections': adjacent_subsections,
                                'is_first': (chapter_idx == 0 and section_idx == 0 and subsection_idx == 0),
                                'is_last': (chapter_idx == len(allocations) - 1 and
                                            section_idx == len(chapter_alloc['sections']) - 1 and
                                            subsection_idx == len(section_alloc['subsections']) - 1)
                            })

        # 🔥 创建任务ID用于进度跟踪
        task_id = f"article_gen_{card_id}_{uuid.uuid4().hex[:8]}"
        total_tasks = len(writing_tasks)

        # 初始化进度
        global_var.tasks[task_id] = {
            'current_page': 0,
            'total_pages': total_tasks,
            'current_item': 0,
            'total_items': total_tasks,
            'current_section': ''
        }

        # 🔥 在后台线程中执行文章生成
        def generate_article_in_background():
            """在后台线程中执行文章生成"""
            try:
                # 🔥 如果是迭代模式，先检测是否有摘要、关键词、边界问题描述
                pre_analysis_result = None
                existing_article_content = None
                should_skip_body_iteration = False  # 🔥 标记是否跳过正文迭代

                if has_existing_article:
                    print("[generate_output_article] 检测到已有正文，进入迭代精进模式")

                    # 重新获取目录卡片内容
                    directory_card = Card.objects.get(cid=card_id, username=username)
                    current_content = directory_card.content or ""

                    # 提取现有正文内容
                    _, existing_article_content = _extract_existing_article_content(current_content)

                    # 🔥 检测是否有摘要、关键词、边界问题描述
                    has_abstract_keywords, has_boundary = _check_has_abstract_keywords_boundary(
                        existing_article_content)
                    print(
                        f"[generate_output_article] 检测结果: has_abstract_keywords={has_abstract_keywords}, has_boundary={has_boundary}")

                    if not has_abstract_keywords or not has_boundary:
                        # 情况（1）：没有摘要/关键词/边界问题描述，跳过正文迭代
                        print("[generate_output_article] 情况（1）：没有摘要/关键词/边界问题描述，跳过正文迭代，直接生成摘要和边界问题描述")
                        should_skip_body_iteration = True
                    else:
                        # 情况（2）：有摘要/关键词/边界问题描述，先进行正文迭代
                        print("[generate_output_article] 情况（2）：有摘要/关键词/边界问题描述，先进行正文迭代，然后迭代摘要和边界问题描述")
                        should_skip_body_iteration = False

                        # 🔥 迭代模式：检查目录和正文结构的一致性
                        print("--------------------------------- 开始结构对比 ---------------------------------")
                        structure_diff = _compare_directory_and_article_structure(
                            directory_structure, existing_article_content
                        )
                        print(
                            f"[generate_output_article] 结构对比: 修改{len(structure_diff['modified'])}处, 删除{len(structure_diff['deleted'])}处, 新增{len(structure_diff['added'])}处")
                        print("--------------------------------- 结构对比完成 ---------------------------------")

                        # 🔥 根据结构差异调整writing_tasks（在闭包外部定义的writing_tasks）
                        # 注意：writing_tasks是在外层作用域定义的，需要通过nonlocal或直接修改
                        # 1. 处理删除：从writing_tasks中移除被删除的任务
                        deleted_keys = set()
                        for ch_idx, sec_idx, subsec_idx, name in structure_diff['deleted']:
                            deleted_keys.add((ch_idx, sec_idx, subsec_idx))

                        # 在外层作用域中修改writing_tasks
                        nonlocal writing_tasks
                        writing_tasks = [task for task in writing_tasks
                                         if (task['chapter_idx'], task.get('section_idx'),
                                             task.get('subsection_idx')) not in deleted_keys]
                        if deleted_keys:
                            print(f"[generate_output_article] 已移除{len(deleted_keys)}个被删除的任务")

                        # 2. 处理修改：更新任务中的section_name，并保存旧名称用于相似度判断
                        print("--------------------------------- 开始处理修改任务 ---------------------------------")
                        modified_map = {}
                        modified_old_names = {}  # 🔥 记录修改前的旧名称
                        for ch_idx, sec_idx, subsec_idx, old_name, new_name in structure_diff['modified']:
                            key = (ch_idx, sec_idx, subsec_idx)
                            modified_map[key] = new_name
                            modified_old_names[key] = old_name  # 🔥 保存旧名称
                            print(
                                f"[generate_output_article] 记录修改: key={key}, old_name={old_name}, new_name={new_name}")

                        for task in writing_tasks:
                            key = (task['chapter_idx'], task.get('section_idx'), task.get('subsection_idx'))
                            if key in modified_map:
                                # 🔥 关键：task['section_name']已经是新名称（因为writing_tasks基于新目录结构生成），所以要用modified_old_names[key]作为旧名称
                                old_name = modified_old_names[key]  # 🔥 使用真正的旧名称
                                new_name = modified_map[key]
                                task['section_name'] = new_name
                                task['old_name'] = old_name  # 🔥 保存旧名称到task中
                                # 🔥 计算名称相似度（使用真正的旧名称和新名称）
                                # 🔥 如果名称完全相同（只是序号变化），相似度应该为1.0
                                if old_name == new_name:
                                    similarity = 1.0
                                    print(f"[generate_output_article] 名称完全相同（序号变化）: {old_name} == {new_name}, 相似度设为1.0")
                                else:
                                    similarity = _calculate_name_similarity(old_name, new_name)
                                    print(
                                        f"[generate_output_article] 名称不同，计算相似度: {old_name} vs {new_name}, 相似度={similarity:.2f}")
                                task['name_similarity'] = similarity
                                print(
                                    f"[generate_output_article] ✅ 更新任务名称: {old_name} -> {new_name}, 相似度: {similarity:.2f}" + (
                                        " (序号变化)" if old_name == new_name else ""))
                        print("--------------------------------- 处理修改任务完成 ---------------------------------")

                        # 3. 处理新增：新增的任务已经在writing_tasks中（因为基于目录结构生成）
                        # 新增的任务会在迭代时被识别为"第一次生成"（因为parsed_existing_structure中没有对应内容）

                        # 进行预分析（只在需要正文迭代时进行）
                        pre_analysis_result = _pre_analyze_directory(directory_structure, directory_content, username)
                        if pre_analysis_result:
                            print(f"[generate_output_article] 预分析完成，长度: {len(pre_analysis_result)}字")
                        else:
                            print("[generate_output_article] ⚠️ 预分析失败，将使用原有模式进行迭代")

                        # 🔥 迭代模式：预先解析现有正文结构（避免在每次任务中重复解析）
                        # 🔥 关键：需要创建一个包含旧名称的临时目录结构用于解析，因为正文中还是旧名称
                        # 创建一个临时目录结构，将修改的章节名称改回旧名称用于匹配
                        temp_directory_structure = {
                            'title': directory_structure['title'],
                            'chapters': []
                        }
                        for ch_idx, chapter in enumerate(directory_structure['chapters']):
                            temp_chapter = {
                                'name': chapter['name'],
                                'name_with_prefix': chapter.get('name_with_prefix', chapter['name']),
                                'sections': []
                            }
                            for sec_idx, section in enumerate(chapter.get('sections', [])):
                                temp_section = {
                                    'name': section['name'],
                                    'name_with_prefix': section.get('name_with_prefix', section['name']),
                                    'subsections': []
                                }
                                for subsec_idx, subsection in enumerate(section.get('subsections', [])):
                                    key = (ch_idx, sec_idx, subsec_idx)
                                    # 🔥 如果这个章节被修改了，使用旧名称用于匹配
                                    if key in modified_old_names:
                                        old_name = modified_old_names[key]
                                        # 提取序号部分（A、B、C等），并构建正确的name_with_prefix用于匹配
                                        # 正文中的标题格式可能是"A天时&地时与人时"（没有点号）或"A.天时&地时与人时"（有点号）
                                        prefix = ''
                                        if subsection.get('name_with_prefix'):
                                            prefix_match = subsection['name_with_prefix'].strip()[0] if subsection[
                                                'name_with_prefix'].strip() else ''
                                            if prefix_match and prefix_match.isalpha() and prefix_match.isupper():
                                                prefix = prefix_match
                                        # 🔥 构建两种可能的格式用于匹配（正文中可能有点号也可能没有点号）
                                        name_with_prefix_no_dot = f"{prefix}{old_name}" if prefix else old_name
                                        name_with_prefix_with_dot = f"{prefix}.{old_name}" if prefix else old_name
                                        temp_subsection = {
                                            'name': old_name,  # 使用旧名称
                                            'name_with_prefix': name_with_prefix_no_dot,  # 优先使用无点号格式（因为正文中更常见）
                                            'name_with_prefix_alt': name_with_prefix_with_dot  # 备用格式
                                        }
                                    else:
                                        temp_subsection = {
                                            'name': subsection['name'],
                                            'name_with_prefix': subsection.get('name_with_prefix', subsection['name'])
                                        }
                                    temp_section['subsections'].append(temp_subsection)

                                # 🔥 处理节级别的修改
                                key = (ch_idx, sec_idx, None)
                                if key in modified_old_names:
                                    temp_section['name'] = modified_old_names[key]
                                    temp_section[
                                        'name_with_prefix'] = f"{section.get('name_with_prefix', section['name']).split('.', 1)[0] if '.' in section.get('name_with_prefix', '') else ''}.{modified_old_names[key]}"

                                temp_chapter['sections'].append(temp_section)

                            # 🔥 处理章级别的修改
                            key = (ch_idx, None, None)
                            if key in modified_old_names:
                                temp_chapter['name'] = modified_old_names[key]
                                temp_chapter[
                                    'name_with_prefix'] = f"{chapter.get('name_with_prefix', chapter['name']).split('、', 1)[0] if '、' in chapter.get('name_with_prefix', '') else ''}、{modified_old_names[key]}"

                            temp_directory_structure['chapters'].append(temp_chapter)

                        print("--------------------------------- 开始解析现有正文结构 ---------------------------------")
                        parsed_existing_structure = _parse_existing_article_structure(
                            existing_article_content, temp_directory_structure  # 🔥 使用包含旧名称的临时结构
                        )
                        print(f"[generate_output_article] 解析到{len(parsed_existing_structure)}个现有章节内容（使用旧名称匹配）")
                        print(f"[generate_output_article] 解析到的keys: {list(parsed_existing_structure.keys())}")
                        print("--------------------------------- 解析现有正文结构完成 ---------------------------------")

                        # 🔥 计算全文最大迭代次数（用于需求③：迭代次数标签使用全文最大次数+1）
                        max_iteration_in_full_article = _get_iteration_count_from_content(existing_article_content)
                        print(f"[generate_output_article] 全文最大迭代次数: {max_iteration_in_full_article}")
                else:
                    # 新生成模式
                    should_skip_body_iteration = False
                    parsed_existing_structure = {}
                    max_iteration_in_full_article = 0  # 新生成时没有迭代次数
                    # 🔥 新生成也做预分析，生成/迭代时均可按 name_with_prefix 注入本单元撰写要求
                    pre_analysis_result = _pre_analyze_directory(directory_structure, directory_content, username)
                    if pre_analysis_result:
                        print(f"[generate_output_article] 预分析完成（新生成），长度: {len(pre_analysis_result)}字")
                    else:
                        print("[generate_output_article] ⚠️ 预分析失败（新生成），将不注入章节撰写要求")

                writing_results = {}  # {(chapter_idx, section_idx, subsection_idx): (content, model_used)}
                all_refined_doc_segments = []  # 收集所有章节的refined_doc_segments

                # 🔥 情况（1）：跳过正文迭代，直接使用现有正文
                if should_skip_body_iteration:
                    # 直接使用现有正文内容，不进行迭代
                    full_article = existing_article_content
                    print("[generate_output_article] 跳过正文迭代，直接使用现有正文内容")
                else:
                    # 🔥 情况（2）或新生成：执行正文迭代或生成
                    def write_section(task):
                        """撰写单个章节的函数"""
                        try:
                            # 更新进度：当前正在处理的章节
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_section'] = task['section_name']
                                print(
                                    f"[write_section] 开始{'迭代' if has_existing_article else '撰写'}: {task['section_name']}, 进度: {global_var.tasks[task_id]['current_item']}/{global_var.tasks[task_id]['total_items']}")

                            # 获取相关卡片和文档（①②素材）
                            relevant_cards = _get_relevant_cards_for_section(
                                task['section_name'], username, max_cards=5
                            )
                            print(f"[write_section] 获取到{len(relevant_cards)}张相关卡片用于{task['section_name']}")
                            relevant_docs = _get_relevant_documents_for_section(
                                task['section_name'], username, max_docs=3
                            )

                            # 🔥 获取现有章节内容
                            key = (task['chapter_idx'], task['section_idx'], task['subsection_idx'])
                            print(
                                f"\n--------------------------------- 处理任务: {task['section_name']} (key={key}) ---------------------------------")
                            existing_section_content = None
                            if has_existing_article:
                                existing_section_content = parsed_existing_structure.get(key)
                                if existing_section_content:
                                    print(f"[write_section] ✅ 找到现有内容，长度: {len(existing_section_content)}字")
                                    # 检查是否有修改标签
                                    if '<第' in existing_section_content and '次修改内容>' in existing_section_content:
                                        import re
                                        tags = re.findall(r'<第\d+次修改内容>', existing_section_content)
                                        print(f"[write_section] 📝 现有内容包含修改标签: {tags}")
                                else:
                                    print(f"[write_section] ⚠️ 未找到现有内容 (key={key})")
                            else:
                                print(f"[write_section] 新生成模式，无需查找现有内容")

                            # 🔥 判断是否为新增章节：有现有正文但当前章节不存在
                            is_new_section = has_existing_article and existing_section_content is None
                            print(f"[write_section] is_new_section = {is_new_section}")

                            # 🔥 判断是否为名称修改的章节（根据相似度决定是否使用迭代逻辑）
                            is_name_modified_low_similarity = False
                            if has_existing_article and 'old_name' in task:
                                # 这是名称被修改的章节，检查相似度
                                similarity = task.get('name_similarity', 0.0)
                                print(
                                    f"[write_section] 名称修改章节检测: old_name={task.get('old_name')}, new_name={task['section_name']}, similarity={similarity:.2f}")
                                # 🔥 如果没有获取到existing_section_content，可能是匹配失败，记录警告
                                if not existing_section_content:
                                    print(
                                        f"[write_section] ⚠️⚠️⚠️ 警告：章节名修改但未找到现有内容，可能是匹配失败: {task.get('old_name')} -> {task['section_name']}, key={key}")
                                    is_name_modified_low_similarity = True  # 🔥 未找到现有内容，使用新生成逻辑
                                    print(
                                        f"[write_section] ⚠️⚠️⚠️ 设置 is_name_modified_low_similarity = True (因为未找到现有内容)")
                                # 相似度阈值：如果相似度低于0.8，认为内涵发生了变化，使用新生成逻辑
                                # 🔥 注意：连续3个字符匹配的情况会返回0.8，应该使用迭代逻辑（相似度>=0.8视为高度相似）
                                elif similarity < 0.8:
                                    is_name_modified_low_similarity = True
                                    existing_section_content = None  # 🔥 清空existing_content，强制使用新生成逻辑
                                    print(
                                        f"[write_section] ⚠️⚠️⚠️ 章节名修改且相似度低({similarity:.2f})，使用新生成逻辑: {task.get('old_name')} -> {task['section_name']}")
                                    print(f"[write_section] ⚠️⚠️⚠️ 设置 is_name_modified_low_similarity = True (因为相似度低)")
                                else:
                                    print(
                                        f"[write_section] ✅✅✅ 章节名修改但相似度高({similarity:.2f})，保持迭代逻辑: {task.get('old_name')} -> {task['section_name']}, 现有内容长度: {len(existing_section_content)}字")
                            else:
                                if has_existing_article:
                                    print(f"[write_section] 非名称修改章节，'old_name' in task = {'old_name' in task}")

                            # 🔥 对于新增章节或低相似度修改，计算其他同类型章节的字数均值作为参考
                            if is_new_section or is_name_modified_low_similarity:
                                # 计算同类型章节的字数均值
                                section_type = task['section_type']
                                same_type_word_counts = []
                                for other_task in writing_tasks:
                                    if (other_task['section_type'] == section_type and
                                            other_task != task and  # 不是自己
                                            not (has_existing_article and parsed_existing_structure.get(
                                                (other_task['chapter_idx'], other_task.get('section_idx'),
                                                 other_task.get('subsection_idx'))
                                            ) is None)):  # 不是新增章节
                                        same_type_word_counts.append(
                                            other_task.get('original_word_count', other_task['word_count']))

                                if same_type_word_counts:
                                    avg_word_count = int(sum(same_type_word_counts) / len(same_type_word_counts))
                                    # 使用均值和原字数的平均值作为参考
                                    original_wc = task.get('original_word_count', task['word_count'])
                                    adjusted_word_count = int((original_wc + avg_word_count) / 2)
                                    # 第一次生成时每处不得低于300字，上限500字
                                    adjusted_word_count = max(min(adjusted_word_count, 500), 300)
                                    task['word_count'] = adjusted_word_count
                                    print(
                                        f"[write_section] 新增/低相似度章节字数调整: {task['section_name']}, 原字数: {original_wc}, 同类型均值: {avg_word_count}, 调整后: {adjusted_word_count}")

                            # 🔥 需求②：检测目录是否修改，如果修改了，提取修改变动的词并添加到关键词中
                            is_directory_modified = False
                            title_change_keywords = []
                            if has_existing_article and 'old_name' in task and task.get('old_name') != task[
                                'section_name']:
                                is_directory_modified = True
                                old_name = task.get('old_name')
                                new_name = task['section_name']
                                title_change_keywords = _extract_title_change_keywords(old_name, new_name)
                                print(
                                    f"[write_section] 🔥 检测到目录修改: {old_name} -> {new_name}, 提取差异词: {title_change_keywords}")

                                # 🔥 将修改变动的词添加到关键词中，用于获取相关文档
                                if title_change_keywords:
                                    # 扩展section_name，包含修改变动的词
                                    extended_section_name = f"{task['section_name']} {' '.join(title_change_keywords)}"
                                    print(f"[write_section] 扩展section_name用于获取文档: {extended_section_name}")
                                    # 重新获取相关文档（包含修改变动的词）
                                    relevant_docs = _get_relevant_documents_for_section(
                                        extended_section_name, username, max_docs=3
                                    )
                                    print(f"[write_section] 使用扩展关键词重新获取到{len(relevant_docs)}个相关文档")

                            # 🔥 获取细化后的文档segments（④素材）
                            # 🔥 第一次生成和迭代模式都需要获取，用于生成参考文献列表
                            refined_doc_segments = None
                            refined_doc_segments = _get_refined_document_segments_for_section(
                                task['section_name'], username, relevant_docs,
                                existing_section_content=existing_section_content if has_existing_article else None,
                                # 第一次生成时为None
                                relevant_cards=relevant_cards
                            )

                            # 🔥 提取预分析结果的相关部分（③素材）：生成/迭代均使用，按 name_with_prefix 精确匹配本单元撰写要求
                            pre_analysis_part = None
                            if pre_analysis_result:
                                pre_analysis_part = _extract_section_analysis(
                                    pre_analysis_result, task['section_name'], task['section_type'],
                                    name_with_prefix=task.get('name_with_prefix'),
                                    parent_section_name=task.get('parent_section_name'),
                                    parent_chapter_name=task.get('parent_chapter_name'),
                                    is_iteration=has_existing_article  # 如果有现有文章，则是迭代模式
                                )

                                # 🔥 记录撰写要求是否被输入给模型，写入预分析结果文件
                                try:
                                    from datetime import datetime
                                    current_file_dir = os.path.dirname(os.path.abspath(__file__))
                                    backend_dir = os.path.dirname(current_file_dir)
                                    output_dir = os.path.join(backend_dir, "预分析结果")
                                    # 找到最新的预分析结果文件
                                    if os.path.exists(output_dir):
                                        pre_analysis_files = [f for f in os.listdir(output_dir) if
                                                              f.startswith(f"预分析_{username}_") and f.endswith('.txt')]
                                        if pre_analysis_files:
                                            # 按时间戳排序，取最新的
                                            pre_analysis_files.sort(reverse=True)
                                            latest_file = os.path.join(output_dir, pre_analysis_files[0])
                                            # 追加记录
                                            with open(latest_file, 'a', encoding='utf-8') as f:
                                                f.write(f"\n\n{'=' * 80}\n")
                                                f.write(f"## 章节撰写要求输入记录\n")
                                                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                                f.write(f"章节: {task.get('name_with_prefix', task['section_name'])}\n")
                                                f.write(f"类型: {task['section_type']}\n")
                                                if pre_analysis_part:
                                                    f.write(f"✅ 撰写要求已输入给模型\n")
                                                    f.write(f"撰写要求内容（前500字）:\n{pre_analysis_part[:500]}...\n")
                                                else:
                                                    f.write(f"❌ 撰写要求未输入给模型（未找到匹配的撰写要求）\n")
                                                f.write(f"{'=' * 80}\n")
                                except Exception as e:
                                    print(f"[write_section] ⚠️ 记录撰写要求输入情况失败: {e}")

                            # 🔥 生成内容
                            # 新增章节使用新生成prompt（is_iteration=False），但传入③④素材；已有章节使用迭代prompt
                            is_iteration = has_existing_article and not is_new_section and not is_name_modified_low_similarity
                            print(
                                f"[write_section]  最终判断: has_existing_article={has_existing_article}, is_new_section={is_new_section}, is_name_modified_low_similarity={is_name_modified_low_similarity}")
                            print(f"[write_section]  is_iteration = {is_iteration}")
                            print(
                                f"[write_section]  existing_section_content is None = {existing_section_content is None}")
                            if existing_section_content:
                                print(
                                    f"[write_section]  existing_section_content 前100字: {existing_section_content[:100]}")
                            print(
                                "--------------------------------- 调用 _generate_section_content ---------------------------------")
                            content, model_used = _generate_section_content(
                                section_name=task['section_name'],
                                section_type=task['section_type'],
                                word_count=task['word_count'],
                                parent_section_name=task['parent_section_name'],
                                parent_chapter_name=task['parent_chapter_name'],
                                directory_title=task['directory_title'],
                                relevant_cards=relevant_cards,
                                relevant_docs=relevant_docs,
                                adjacent_sections=task.get('adjacent_sections', []),
                                is_first=task.get('is_first', False),
                                is_last=task.get('is_last', False),
                                is_iteration=is_iteration,  # 🔥 新增章节或低相似度修改使用新生成prompt
                                existing_content=existing_section_content,
                                pre_analysis_part=pre_analysis_part,  # 🔥 新增章节也传入预分析结果
                                refined_doc_segments=refined_doc_segments,  # 🔥 新增章节也传入细化文档segments
                                max_iteration_in_full_article=max_iteration_in_full_article,  # 🔥 需求③：传递全文最大迭代次数
                                chapter_idx=task.get('chapter_idx'), section_idx=task.get('section_idx'),
                                subsection_idx=task.get('subsection_idx'),
                                directory_structure=directory_structure,
                                parsed_existing_structure=parsed_existing_structure if has_existing_article else None,
                                is_directory_modified=is_directory_modified,  # 🔥 需求②：传递目录是否修改标志
                                old_name=task.get('old_name') if 'old_name' in task else None,  # 🔥 需求②：传递旧名称
                                title_change_keywords=title_change_keywords  # 🔥 需求②：传递修改变动的词
                            )
                            print(
                                f"--------------------------------- _generate_section_content 返回完成 (is_iteration={is_iteration}) ---------------------------------")

                            # 🔥 迭代模式：合并新旧内容并标注修改（只有非新增章节且非低相似度修改才需要合并）
                            if has_existing_article and not is_new_section and not is_name_modified_low_similarity and existing_section_content and content:
                                # 🔥 需求②：传递目录修改信息给_merge_content_with_modifications
                                # 🔥 如果字数减少超过40%，需要重新迭代（最多重试1次）
                                retry_count = 0
                                max_retry = 1
                                merged_content = None
                                while retry_count <= max_retry:
                                    if retry_count > 0:
                                        print(f"[write_section] 🔥 重新迭代（第{retry_count}次重试），因为字数减少超过40%")
                                        # 重新生成内容
                                        content, model_used = _generate_section_content(
                                            section_name=task['section_name'],
                                            section_type=task['section_type'],
                                            word_count=task['word_count'],
                                            parent_section_name=task['parent_section_name'],
                                            parent_chapter_name=task['parent_chapter_name'],
                                            directory_title=task['directory_title'],
                                            relevant_cards=relevant_cards,
                                            relevant_docs=relevant_docs,
                                            adjacent_sections=task.get('adjacent_sections', []),
                                            is_first=task.get('is_first', False),
                                            is_last=task.get('is_last', False),
                                            is_iteration=is_iteration,
                                            existing_content=existing_section_content,
                                            pre_analysis_part=pre_analysis_part,
                                            refined_doc_segments=refined_doc_segments,
                                            max_iteration_in_full_article=max_iteration_in_full_article,
                                            chapter_idx=task.get('chapter_idx'), section_idx=task.get('section_idx'),
                                            subsection_idx=task.get('subsection_idx'),
                                            directory_structure=directory_structure,
                                            parsed_existing_structure=parsed_existing_structure if has_existing_article else None,
                                            is_directory_modified=is_directory_modified,
                                            old_name=task.get('old_name') if 'old_name' in task else None,
                                            title_change_keywords=title_change_keywords
                                        )
                                        if not content:
                                            print(f"[write_section] ⚠️ 重新迭代生成失败，使用原内容")
                                            content = existing_section_content
                                            break

                                    merged_content = _merge_content_with_modifications(
                                        content, existing_section_content,
                                        section_name=task['section_name'],
                                        section_type=task['section_type'],
                                        parent_section_name=task.get('parent_section_name'),
                                        parent_chapter_name=task.get('parent_chapter_name'),
                                        refined_doc_segments=refined_doc_segments,
                                        adjacent_sections=task.get('adjacent_sections', []),
                                        chapter_idx=task.get('chapter_idx'), section_idx=task.get('section_idx'),
                                        subsection_idx=task.get('subsection_idx'),
                                        directory_structure=directory_structure,
                                        parsed_existing_structure=parsed_existing_structure if has_existing_article else None,
                                        is_directory_modified=is_directory_modified  # 🔥 需求②：传递目录修改标志
                                    )

                                    # 如果merged_content为None，说明字数减少超过40%，需要重新迭代
                                    if merged_content is None:
                                        retry_count += 1
                                        if retry_count > max_retry:
                                            # 重试次数用完，保留原内容
                                            print(f"[write_section] ⚠️⚠️⚠️ 重新迭代{max_retry}次后字数仍减少超过40%，保留原内容")
                                            merged_content = existing_section_content
                                            break
                                    else:
                                        # 合并成功，退出循环
                                        content = merged_content
                                        break

                                if merged_content is not None:
                                    content = merged_content

                                    # 🔥 需求（3）：检测换行符异常
                                    # 如果章（无节）/节（无小节）/小节迭代后以及后处理全都结束后，
                                    # 内容里的\n换行符个数相较迭代前增加>8且\n\n个数相较迭代前增加>=3同时满足，
                                    # 则认为杂乱异常，再加一次后处理
                                    if content and existing_section_content:
                                        old_newline_count = existing_section_content.count('\n')
                                        new_newline_count = content.count('\n')
                                        newline_increase = new_newline_count - old_newline_count

                                        old_double_newline_count = existing_section_content.count('\n\n')
                                        new_double_newline_count = content.count('\n\n')
                                        double_newline_increase = new_double_newline_count - old_double_newline_count

                                        print(
                                            f"[write_section] 🔥 需求（3）：换行符检测 - 迭代前: \\n={old_newline_count}个, \\n\\n={old_double_newline_count}个; 迭代后: \\n={new_newline_count}个, \\n\\n={new_double_newline_count}个; 增加: \\n={newline_increase}个, \\n\\n={double_newline_increase}个")

                                        # 检测条件：\n增加>8 且 \n\n增加>=3 同时满足
                                        if newline_increase > 8 and double_newline_increase >= 3:
                                            print(
                                                f"[write_section] ⚠️ 需求（3）：检测到换行符异常（\\n增加{newline_increase}>8且\\n\\n增加{double_newline_increase}>=3），触发基于原内容的特殊后处理")
                                            # 调用特殊后处理：基于迭代前内容重新修改
                                            # 🔥 使用全文最大迭代次数+1，保持全文整体性（需求③）
                                            corrected_content_for_newline = _post_process_newline_anomaly(
                                                existing_section_content,  # 只传入迭代前内容
                                                iteration_count=max_iteration_in_full_article + 1,
                                                section_name=task['section_name'],
                                                section_type=task['section_type'],
                                                parent_section_name=task.get('parent_section_name'),
                                                parent_chapter_name=task.get('parent_chapter_name'),
                                                refined_doc_segments=refined_doc_segments,
                                                adjacent_sections=task.get('adjacent_sections', []),
                                                chapter_idx=task.get('chapter_idx'),
                                                section_idx=task.get('section_idx'),
                                                subsection_idx=task.get('subsection_idx'),
                                                directory_structure=directory_structure,
                                                parsed_existing_structure=parsed_existing_structure if has_existing_article else None,
                                                is_directory_modified=is_directory_modified
                                            )

                                            if corrected_content_for_newline:
                                                # 再次检测换行符
                                                corrected_newline_count = corrected_content_for_newline.count('\n')
                                                corrected_double_newline_count = corrected_content_for_newline.count(
                                                    '\n\n')
                                                corrected_newline_increase = corrected_newline_count - old_newline_count
                                                corrected_double_newline_increase = corrected_double_newline_count - old_double_newline_count

                                                print(
                                                    f"[write_section] 🔥 需求（3）：特殊后处理后的换行符检测 - \\n增加={corrected_newline_increase}个, \\n\\n增加={corrected_double_newline_increase}个")

                                                # 如果还有相同问题，保留迭代前的内容
                                                if corrected_newline_increase > 8 and corrected_double_newline_increase >= 3:
                                                    print(
                                                        f"[write_section] ⚠️⚠️⚠️ 需求（3）：特殊后处理后换行符仍异常（\\n增加{corrected_newline_increase}>8且\\n\\n增加{corrected_double_newline_increase}>=3），保留迭代前内容")
                                                    content = existing_section_content
                                                else:
                                                    print(f"[write_section] ✅ 需求（3）：特殊后处理成功，换行符异常已修复")
                                                    content = corrected_content_for_newline
                                            else:
                                                print(f"[write_section] ⚠️ 需求（3）：特殊后处理失败，保留迭代前内容")
                                                content = existing_section_content
                                        else:
                                            print(
                                                f"[write_section] ✅ 需求（3）：换行符检测通过（\\n增加{newline_increase}<=8或\\n\\n增加{double_newline_increase}<3）")

                            # 更新进度：已完成数+1
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_page'] += 1
                                global_var.tasks[task_id]['current_item'] += 1
                                print(
                                    f"[write_section] 完成{'迭代' if has_existing_article else '撰写'}: {task['section_name']}, 进度: {global_var.tasks[task_id]['current_item']}/{global_var.tasks[task_id]['total_items']}")

                            key = (task['chapter_idx'], task['section_idx'], task['subsection_idx'])
                            # 🔥 返回refined_doc_segments（第一次生成和迭代模式都需要）
                            return (key, content, model_used, refined_doc_segments)
                        except Exception as e:
                            print(f"[write_section] {'迭代' if has_existing_article else '撰写'}章节失败: {e}")
                            import traceback
                            traceback.print_exc()
                            # 即使失败也要更新进度
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_page'] += 1
                                global_var.tasks[task_id]['current_item'] += 1
                            # 在异常处理中，task 是从闭包中获取的，需要确保能访问到
                            try:
                                key = (task['chapter_idx'], task['section_idx'], task['subsection_idx'])
                            except:
                                # 如果task不存在，返回None作为key（不应该发生，但保险起见）
                                key = None
                            return (key, None, None, None)

                    # 使用线程池并发执行（最多4个并发）
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        futures = {executor.submit(write_section, task): task for task in writing_tasks}

                        for future in as_completed(futures):
                            try:
                                key, content, model_used, refined_doc_segments_for_section = future.result()
                                if key is not None:  # 确保key有效
                                    writing_results[key] = (content, model_used)
                                    # 收集refined_doc_segments（如果存在）
                                    if refined_doc_segments_for_section:
                                        all_refined_doc_segments.append(refined_doc_segments_for_section)
                            except Exception as e:
                                print(f"[generate_output_article] 获取撰写结果失败: {e}")

                    # 按顺序组装文章内容
                    allocations = word_count_allocation['allocations']['chapters']
                    article_parts = []
                    print(f"[generate_output_article] 开始组装文章，共{len(allocations)}章")
                    for chapter_idx, chapter_alloc in enumerate(allocations):
                        chapter_name = chapter_alloc['name']
                        chapter_name_with_prefix = chapter_alloc.get('name_with_prefix', chapter_name)
                        print(
                            f"[generate_output_article] 处理第{chapter_idx + 1}章: {chapter_name}, 共{len(chapter_alloc.get('sections', []))}节")

                        if not chapter_alloc['sections']:
                            # 没有节，直接写章
                            key = (chapter_idx, None, None)
                            if key in writing_results:
                                content, _ = writing_results[key]
                                if content:
                                    article_parts.append(f"## {chapter_name_with_prefix}\n\n{content}\n\n")
                            else:
                                print(f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章({chapter_name})没有生成结果")
                        else:
                            # 有节
                            article_parts.append(f"## {chapter_name_with_prefix}\n\n")

                            for section_idx, section_alloc in enumerate(chapter_alloc['sections']):
                                section_name = section_alloc['name']
                                section_name_with_prefix = section_alloc.get('name_with_prefix', section_name)
                                print(
                                    f"[generate_output_article] 处理第{chapter_idx + 1}章第{section_idx + 1}节: {section_name}, 共{len(section_alloc.get('subsections', []))}小节")

                                if not section_alloc['subsections']:
                                    # 没有小节，直接写节
                                    key = (chapter_idx, section_idx, None)
                                    if key in writing_results:
                                        content, _ = writing_results[key]
                                        if content:
                                            article_parts.append(f"### {section_name_with_prefix}\n\n{content}\n\n")
                                        else:
                                            print(
                                                f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章第{section_idx + 1}节({section_name})内容为空")
                                    else:
                                        print(
                                            f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章第{section_idx + 1}节({section_name})没有生成结果")
                                else:
                                    # 有小节，写每个小节
                                    article_parts.append(f"### {section_name_with_prefix}\n\n")

                                    for subsection_idx, subsection_alloc in enumerate(section_alloc['subsections']):
                                        subsection_name = subsection_alloc['name']
                                        subsection_name_with_prefix = subsection_alloc.get('name_with_prefix',
                                                                                           subsection_name)
                                        key = (chapter_idx, section_idx, subsection_idx)
                                        if key in writing_results:
                                            content, _ = writing_results[key]
                                            if content:
                                                article_parts.append(
                                                    f"#### {subsection_name_with_prefix}\n\n{content}\n\n")
                                            else:
                                                print(
                                                    f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章第{section_idx + 1}节第{subsection_idx + 1}小节({subsection_name})内容为空")
                                        else:
                                            print(
                                                f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章第{section_idx + 1}节第{subsection_idx + 1}小节({subsection_name})没有生成结果")

                    # 组装完整文章（暂时不包含章首/章尾/节首/节尾）
                    full_article = '\n'.join(article_parts)

                    # 🔥 生成/迭代章首/章尾/节首/节尾
                    print("[generate_output_article] 开始生成/迭代章首/章尾/节首/节尾...")

                    # 🔥 提取现有的章首/章尾/节首/节尾（如果有）
                    intro_outro_dict = {
                        'chapter_intro': {},
                        'chapter_outro': {},
                        'section_intro': {},
                        'section_outro': {}
                    }
                    if has_existing_article and existing_article_content:
                        # 从现有文章中提取章首/章尾/节首/节尾
                        lines = existing_article_content.split('\n')
                        chapters = directory_structure['chapters']

                        current_chapter_idx = None
                        current_section_idx = None

                        i = 0
                        while i < len(lines):
                            line = lines[i].strip()

                            # 匹配章标题
                            if line.startswith('## '):
                                title_text = line[3:].strip()
                                current_chapter_idx = None
                                for ch_idx, ch in enumerate(chapters):
                                    if ch.get('name_with_prefix', ch['name']) == title_text or ch[
                                        'name'] in title_text or title_text in ch.get('name_with_prefix', ch['name']):
                                        current_chapter_idx = ch_idx
                                        current_section_idx = None
                                        break
                                i += 1
                                continue

                            # 匹配节标题
                            if line.startswith('### '):
                                title_text = line[4:].strip()
                                current_section_idx = None
                                if current_chapter_idx is not None and current_chapter_idx < len(chapters):
                                    ch = chapters[current_chapter_idx]
                                    for sec_idx, sec in enumerate(ch.get('sections', [])):
                                        if sec.get('name_with_prefix', sec['name']) == title_text or sec[
                                            'name'] in title_text or title_text in sec.get('name_with_prefix',
                                                                                           sec['name']):
                                            current_section_idx = sec_idx
                                            break
                                i += 1
                                continue

                            # 提取章首（在章标题后、第一节标题前）
                            if line.startswith('【章首】') and current_chapter_idx is not None:
                                content = line[4:].strip()  # 去掉"【章首】"（4个字符）
                                if content:
                                    intro_outro_dict['chapter_intro'][current_chapter_idx] = content
                                i += 1
                                continue

                            # 提取章尾（在章最后、下一章标题前）
                            if line.startswith('【章尾】') and current_chapter_idx is not None:
                                content = line[4:].strip()  # 去掉"【章尾】"（4个字符）
                                if content:
                                    intro_outro_dict['chapter_outro'][current_chapter_idx] = content
                                i += 1
                                continue

                            # 提取节首（在节标题后、第一个小节标题前）
                            if line.startswith(
                                    '【节首】') and current_chapter_idx is not None and current_section_idx is not None:
                                content = line[4:].strip()  # 去掉"【节首】"（4个字符）
                                if content:
                                    intro_outro_dict['section_intro'][
                                        (current_chapter_idx, current_section_idx)] = content
                                i += 1
                                continue

                            # 提取节尾（在节最后、下一节标题前）
                            if line.startswith(
                                    '【节尾】') and current_chapter_idx is not None and current_section_idx is not None:
                                content = line[4:].strip()  # 去掉"【节尾】"（4个字符）
                                if content:
                                    intro_outro_dict['section_outro'][
                                        (current_chapter_idx, current_section_idx)] = content
                                i += 1
                                continue

                            i += 1

                        print(
                            f"[generate_output_article] 从现有文章提取到：章首{len(intro_outro_dict['chapter_intro'])}个、章尾{len(intro_outro_dict['chapter_outro'])}个、节首{len(intro_outro_dict['section_intro'])}个、节尾{len(intro_outro_dict['section_outro'])}个")

                    # 准备需要生成/迭代的任务
                    intro_outro_tasks = []
                    allocations = word_count_allocation['allocations']['chapters']

                    for chapter_idx, chapter_alloc in enumerate(allocations):
                        chapter_name = chapter_alloc['name']
                        sections = chapter_alloc.get('sections', [])

                        # 检查是否需要章首/章尾（章下有多个节，至少2个）
                        if len(sections) >= 2:
                            # 需要章首：收集此章所有节和小节的内容（不限制长度）
                            child_contents = []
                            for sec_idx, sec in enumerate(sections):
                                # 收集节内容（如果没有小节）
                                key = (chapter_idx, sec_idx, None)
                                if key in writing_results:
                                    content, _ = writing_results[key]
                                    if content:
                                        child_contents.append(content)

                                # 收集所有小节内容
                                subsections = sec.get('subsections', [])
                                for subsec_idx in range(len(subsections)):
                                    key = (chapter_idx, sec_idx, subsec_idx)
                                    if key in writing_results:
                                        content, _ = writing_results[key]
                                        if content:
                                            child_contents.append(content)

                            if child_contents:
                                existing_intro = intro_outro_dict.get('chapter_intro', {}).get(chapter_idx,
                                                                                               None) if intro_outro_dict else None
                                intro_outro_tasks.append({
                                    'type': 'chapter_intro',
                                    'key': chapter_idx,
                                    'parent_name': chapter_name,
                                    'parent_type': 'chapter',
                                    'child_contents': child_contents,
                                    'existing_content': existing_intro
                                })

                            # 需要章尾：收集此章所有节和小节的内容（不限制长度）
                            child_contents_outro = []
                            for sec_idx, sec in enumerate(sections):
                                # 收集节内容（如果没有小节）
                                key = (chapter_idx, sec_idx, None)
                                if key in writing_results:
                                    content, _ = writing_results[key]
                                    if content:
                                        child_contents_outro.append(content)

                                # 收集所有小节内容
                                subsections = sec.get('subsections', [])
                                for subsec_idx in range(len(subsections)):
                                    key = (chapter_idx, sec_idx, subsec_idx)
                                    if key in writing_results:
                                        content, _ = writing_results[key]
                                        if content:
                                            child_contents_outro.append(content)

                            if child_contents_outro:
                                existing_outro = intro_outro_dict.get('chapter_outro', {}).get(chapter_idx,
                                                                                               None) if intro_outro_dict else None
                                intro_outro_tasks.append({
                                    'type': 'chapter_outro',
                                    'key': chapter_idx,
                                    'parent_name': chapter_name,
                                    'parent_type': 'chapter',
                                    'child_contents': child_contents_outro,
                                    'existing_content': existing_outro
                                })

                        # 检查每个节是否需要节首/节尾（节下有多个小节，至少2个）
                        for section_idx, section_alloc in enumerate(sections):
                            section_name = section_alloc['name']
                            subsections = section_alloc.get('subsections', [])

                            if len(subsections) >= 2:
                                # 需要节首：收集此节所有小节的内容（不限制长度）
                                child_contents = []
                                for subsec_idx in range(len(subsections)):
                                    key = (chapter_idx, section_idx, subsec_idx)
                                    if key in writing_results:
                                        content, _ = writing_results[key]
                                        if content:
                                            child_contents.append(content)

                                if child_contents:
                                    existing_intro = intro_outro_dict.get('section_intro', {}).get(
                                        (chapter_idx, section_idx), None) if intro_outro_dict else None
                                    intro_outro_tasks.append({
                                        'type': 'section_intro',
                                        'key': (chapter_idx, section_idx),
                                        'parent_name': section_name,
                                        'parent_type': 'section',
                                        'parent_chapter_name': chapter_name,  # 🔥 添加所在章名
                                        'child_contents': child_contents,
                                        'existing_content': existing_intro
                                    })

                                # 需要节尾：收集此节所有小节的内容（不限制长度）
                                child_contents_outro = []
                                for subsec_idx in range(len(subsections)):
                                    key = (chapter_idx, section_idx, subsec_idx)
                                    if key in writing_results:
                                        content, _ = writing_results[key]
                                        if content:
                                            child_contents_outro.append(content)

                                if child_contents_outro:
                                    existing_outro = intro_outro_dict.get('section_outro', {}).get(
                                        (chapter_idx, section_idx), None) if intro_outro_dict else None
                                    intro_outro_tasks.append({
                                        'type': 'section_outro',
                                        'key': (chapter_idx, section_idx),
                                        'parent_name': section_name,
                                        'parent_type': 'section',
                                        'parent_chapter_name': chapter_name,  # 🔥 添加所在章名
                                        'child_contents': child_contents_outro,
                                        'existing_content': existing_outro
                                    })

                    # 生成/迭代章首/章尾/节首/节尾（4线程并发）
                    intro_outro_results = {}  # {type: {key: content, ...}, ...}
                    if intro_outro_tasks:
                        print(f"[generate_output_article] 需要生成/迭代{len(intro_outro_tasks)}个章首/章尾/节首/节尾")
                        # 🔥 更新总任务数和进度信息（一次性更新章节首尾+最终整理thinking/checking）
                        if task_id in global_var.tasks:
                            current_total = global_var.tasks[task_id]['total_items']
                            # 章节首尾任务数 + thinking/checking的1步
                            additional_tasks = len(intro_outro_tasks) + 1
                            global_var.tasks[task_id]['total_items'] = current_total + additional_tasks
                            global_var.tasks[task_id]['total_pages'] = current_total + additional_tasks
                            global_var.tasks[task_id]['current_section'] = '处理章节首尾'
                            print(
                                f"[generate_output_article] 更新总任务数（章节首尾+最终整理）: {current_total} -> {current_total + additional_tasks}")

                        def process_intro_outro(task):
                            """生成/迭代单个章首/章尾/节首/节尾"""
                            try:
                                # 🔥 获取所在章名（仅对节首节尾有效）
                                parent_chapter_name = task.get('parent_chapter_name')

                                if task['existing_content']:
                                    # 迭代模式
                                    content = _iterate_intro_outro(
                                        task['existing_content'],
                                        task['type'],
                                        task['parent_name'],
                                        task['parent_type'],
                                        task['child_contents'],
                                        directory_structure['title'],
                                        username,
                                        parent_chapter_name=parent_chapter_name  # 🔥 传递所在章名
                                    )
                                else:
                                    # 生成模式
                                    content = _generate_intro_outro(
                                        task['type'],
                                        task['parent_name'],
                                        task['parent_type'],
                                        task['child_contents'],
                                        directory_structure['title'],
                                        username,
                                        parent_chapter_name=parent_chapter_name  # 🔥 传递所在章名
                                    )
                                return task['type'], task['key'], content
                            except Exception as e:
                                print(f"[process_intro_outro] 处理{task['type']}失败: {e}")
                                import traceback
                                traceback.print_exc()
                                return task['type'], task['key'], None

                        # 使用线程池并发执行（最多4个并发）
                        with ThreadPoolExecutor(max_workers=4) as executor:
                            futures = {executor.submit(process_intro_outro, task): task for task in intro_outro_tasks}

                            completed_count = 0
                            for future in as_completed(futures):
                                try:
                                    intro_outro_type, key, content = future.result()
                                    if content:
                                        if intro_outro_type not in intro_outro_results:
                                            intro_outro_results[intro_outro_type] = {}
                                        intro_outro_results[intro_outro_type][key] = content
                                        print(f"[generate_output_article] ✅ 完成{intro_outro_type}: key={key}")
                                    # 🔥 更新进度（每个任务完成时更新）
                                    completed_count += 1
                                    if task_id in global_var.tasks:
                                        global_var.tasks[task_id]['current_item'] += 1
                                        global_var.tasks[task_id]['current_page'] += 1
                                except Exception as e:
                                    print(f"[generate_output_article] 获取章首/章尾/节首/节尾结果失败: {e}")
                                    # 即使失败也要更新进度
                                    completed_count += 1
                                    if task_id in global_var.tasks:
                                        global_var.tasks[task_id]['current_item'] += 1
                                        global_var.tasks[task_id]['current_page'] += 1

                    # 重新组装文章，插入章首/章尾/节首/节尾到正确位置
                    article_parts_with_intro_outro = []
                    allocations = word_count_allocation['allocations']['chapters']

                    for chapter_idx, chapter_alloc in enumerate(allocations):
                        chapter_name = chapter_alloc['name']
                        chapter_name_with_prefix = chapter_alloc.get('name_with_prefix', chapter_name)
                        sections = chapter_alloc.get('sections', [])

                        if not sections:
                            # 没有节，直接写章
                            key = (chapter_idx, None, None)
                            if key in writing_results:
                                content, _ = writing_results[key]
                                if content:
                                    article_parts_with_intro_outro.append(
                                        f"## {chapter_name_with_prefix}\n\n{content}\n\n")
                        else:
                            # 有节
                            article_parts_with_intro_outro.append(f"## {chapter_name_with_prefix}\n\n")

                            # 插入章首（如果存在）
                            if len(sections) >= 2 and 'chapter_intro' in intro_outro_results and chapter_idx in \
                                    intro_outro_results['chapter_intro']:
                                intro_content = intro_outro_results['chapter_intro'][chapter_idx]
                                article_parts_with_intro_outro.append(f"【章首】{intro_content}\n\n")

                            for section_idx, section_alloc in enumerate(sections):
                                section_name = section_alloc['name']
                                section_name_with_prefix = section_alloc.get('name_with_prefix', section_name)
                                subsections = section_alloc.get('subsections', [])

                                if not subsections:
                                    # 没有小节，直接写节
                                    key = (chapter_idx, section_idx, None)
                                    if key in writing_results:
                                        content, _ = writing_results[key]
                                        if content:
                                            article_parts_with_intro_outro.append(
                                                f"### {section_name_with_prefix}\n\n{content}\n\n")
                                else:
                                    # 有小节
                                    article_parts_with_intro_outro.append(f"### {section_name_with_prefix}\n\n")

                                    # 插入节首（如果存在）
                                    if len(subsections) >= 2 and 'section_intro' in intro_outro_results and (
                                            chapter_idx, section_idx) in intro_outro_results['section_intro']:
                                        intro_content = intro_outro_results['section_intro'][(chapter_idx, section_idx)]
                                        article_parts_with_intro_outro.append(f"【节首】{intro_content}\n\n")

                                    for subsection_idx, subsection_alloc in enumerate(subsections):
                                        subsection_name = subsection_alloc['name']
                                        subsection_name_with_prefix = subsection_alloc.get('name_with_prefix',
                                                                                           subsection_name)
                                        key = (chapter_idx, section_idx, subsection_idx)
                                        if key in writing_results:
                                            content, _ = writing_results[key]
                                            if content:
                                                article_parts_with_intro_outro.append(
                                                    f"#### {subsection_name_with_prefix}\n\n{content}\n\n")

                                    # 插入节尾（如果存在）
                                    if len(subsections) >= 2 and 'section_outro' in intro_outro_results and (
                                            chapter_idx, section_idx) in intro_outro_results['section_outro']:
                                        outro_content = intro_outro_results['section_outro'][(chapter_idx, section_idx)]
                                        article_parts_with_intro_outro.append(f"【节尾】{outro_content}\n\n")

                            # 插入章尾（如果存在）
                            if len(sections) >= 2 and 'chapter_outro' in intro_outro_results and chapter_idx in \
                                    intro_outro_results['chapter_outro']:
                                outro_content = intro_outro_results['chapter_outro'][chapter_idx]
                                article_parts_with_intro_outro.append(f"【章尾】{outro_content}\n\n")

                    # 使用包含章首/章尾/节首/节尾的文章
                    full_article = '\n'.join(article_parts_with_intro_outro)

                    # 🔥 如果有refined_doc_segments（第一次生成和迭代模式都需要），处理引用和参考文献
                    if all_refined_doc_segments:
                        # 🔥 提取旧的参考文献列表（仅迭代模式）
                        old_reference_dict = {}  # {序号: 文档名}
                        if has_existing_article and existing_article_content:
                            _, old_reference_dict = _extract_existing_reference_list(existing_article_content)
                            if old_reference_dict:
                                print(f"[generate_output_article] 提取到{len(old_reference_dict)}条旧参考文献，将保留其序号")

                        # 替换引用标记[文档名]为[序号]（使用合并后的映射）
                        full_article = _replace_citation_markers(full_article, all_refined_doc_segments,
                                                                 old_reference_dict)

                        # 生成参考文献列表（合并新旧列表）
                        reference_list = _generate_reference_list(all_refined_doc_segments, old_reference_dict)
                        if reference_list:
                            # 在文章最后添加参考文献（如果已有参考文献部分，先移除旧的部分）
                            if has_existing_article:
                                # 移除旧的参考文献部分
                                ref_pattern = r'##\s*参考文献.*?$'
                                full_article = re.sub(ref_pattern, '', full_article, flags=re.DOTALL | re.IGNORECASE)
                                full_article = full_article.rstrip()  # 移除末尾多余的空行

                            # 添加新的参考文献列表
                            full_article += "\n\n## 参考文献\n\n" + reference_list
                            print(f"[generate_output_article] 已添加参考文献列表，共{len(all_refined_doc_segments)}个章节的文档信息")

                # 🔥 处理摘要、关键词、边界问题描述（第一次生成和迭代模式都需要）
                if not has_existing_article or (has_existing_article and should_skip_body_iteration):
                    # 情况（1）：第一次生成，或者迭代模式但没有摘要/关键词/边界问题描述，生成它们
                    if not has_existing_article:
                        print(f"[generate_output_article] 第一次生成，开始生成摘要、关键词和边界问题描述...")
                    else:
                        print(f"[generate_output_article] 开始生成摘要和边界问题描述（跳过正文迭代）...")

                    # 从现有正文中提取各章内容（用于生成摘要和边界问题描述）
                    chapter_contents = {}  # {chapter_idx: chapter_content}
                    allocations = word_count_allocation['allocations']['chapters']

                    # 从现有正文（full_article）中提取各章内容
                    for chapter_idx, chapter_alloc in enumerate(allocations):
                        chapter_name = chapter_alloc['name']
                        chapter_name_with_prefix = chapter_alloc.get('name_with_prefix', chapter_name)

                        # 在现有正文中查找该章的内容
                        chapter_pattern = rf'##\s+{re.escape(chapter_name_with_prefix)}\s*\n(.*?)(?=\n##\s+|$)'
                        chapter_match = re.search(chapter_pattern, full_article, re.DOTALL)

                        if chapter_match:
                            chapter_content = chapter_match.group(1).strip()
                            chapter_contents[chapter_idx] = {
                                'name': chapter_name,
                                'content': chapter_content
                            }
                        else:
                            # 如果没找到，尝试使用章节名（不带序号）
                            chapter_pattern2 = rf'##\s+.*?{re.escape(chapter_name)}\s*\n(.*?)(?=\n##\s+|$)'
                            chapter_match2 = re.search(chapter_pattern2, full_article, re.DOTALL)
                            if chapter_match2:
                                chapter_content = chapter_match2.group(1).strip()
                                chapter_contents[chapter_idx] = {
                                    'name': chapter_name,
                                    'content': chapter_content
                                }

                    # 🔥 更新总任务数和进度信息（在提取完章节内容后）
                    num_chapters = len(chapter_contents)
                    additional_steps = num_chapters + 3  # 各章摘要边界描述 + 全文摘要 + 全文边界汇总 + 关键词
                    if task_id in global_var.tasks:
                        if not has_existing_article:
                            # 第一次生成：在原有任务数基础上增加
                            global_var.tasks[task_id]['total_items'] += additional_steps
                            global_var.tasks[task_id]['total_pages'] += additional_steps
                        else:
                            # 迭代模式：更新总任务数
                            global_var.tasks[task_id]['total_items'] = additional_steps
                            global_var.tasks[task_id]['total_pages'] = additional_steps
                            global_var.tasks[task_id]['current_item'] = 0
                        global_var.tasks[task_id]['current_section'] = '生成摘要和边界问题描述'
                        print(f"[generate_output_article] 更新总任务数: +{additional_steps}")

                    # 并发生成各章的摘要和边界问题描述（最多4个并发）
                    chapter_summaries = []  # [(章名, 摘要), ...]
                    chapter_boundaries = []  # [(章名, 边界问题描述), ...]

                    def generate_chapter_summary_boundary(chapter_idx):
                        """生成单章的摘要和边界问题描述"""
                        try:
                            if chapter_idx not in chapter_contents:
                                return None, None, None

                            chapter_data = chapter_contents[chapter_idx]
                            chapter_name = chapter_data['name']
                            chapter_content = chapter_data['content']

                            # 获取该章的目录结构信息
                            chapter_structure = None
                            allocations = word_count_allocation['allocations']['chapters']
                            if chapter_idx < len(allocations):
                                chapter_alloc = allocations[chapter_idx]
                                chapter_structure = {
                                    'sections': chapter_alloc.get('sections', [])
                                }

                            print(
                                f"[generate_chapter_summary_boundary] 开始生成第{chapter_idx + 1}章({chapter_name})的摘要和边界问题描述")

                            # 🔥 更新进度
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_section'] = f'生成第{chapter_idx + 1}章摘要和边界问题描述'

                            summary, boundary = _generate_chapter_summary_and_boundary(
                                chapter_name, chapter_content, directory_structure['title'], username,
                                chapter_structure=chapter_structure
                            )

                            if summary and boundary:
                                print(
                                    f"[generate_chapter_summary_boundary] 完成第{chapter_idx + 1}章({chapter_name})的摘要和边界问题描述")
                                # 🔥 更新进度
                                if task_id in global_var.tasks:
                                    global_var.tasks[task_id]['current_item'] += 1
                                    global_var.tasks[task_id]['current_page'] += 1
                                return chapter_idx, summary, boundary
                            else:
                                print(
                                    f"[generate_chapter_summary_boundary] ⚠️ 第{chapter_idx + 1}章({chapter_name})生成失败")
                                return None, None, None
                        except Exception as e:
                            print(f"[generate_chapter_summary_boundary] 生成第{chapter_idx + 1}章失败: {e}")
                            import traceback
                            traceback.print_exc()
                            return None, None, None

                    # 使用线程池并发执行（最多4个并发）
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        futures = {executor.submit(generate_chapter_summary_boundary, idx): idx
                                   for idx in chapter_contents.keys()}

                        results = {}  # {chapter_idx: (summary, boundary)}
                        for future in as_completed(futures):
                            try:
                                chapter_idx, summary, boundary = future.result()
                                if chapter_idx is not None and summary and boundary:
                                    results[chapter_idx] = (summary, boundary)
                            except Exception as e:
                                print(f"[generate_output_article] 获取章节摘要和边界问题描述结果失败: {e}")

                    # 按章节顺序整理
                    for chapter_idx in sorted(results.keys()):
                        summary, boundary = results[chapter_idx]
                        chapter_name = chapter_contents[chapter_idx]['name']
                        chapter_summaries.append((chapter_name, summary))
                        chapter_boundaries.append((chapter_name, boundary))

                    # 生成全文摘要和边界问题描述汇总（2个线程）
                    full_abstract = None
                    full_boundary_summary = None

                    def generate_full_abstract_task():
                        """生成全文摘要"""
                        try:
                            # 🔥 更新进度
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_section'] = '生成全文摘要'
                            if chapter_summaries:
                                result = _generate_full_abstract(chapter_summaries, directory_structure['title'],
                                                                 username)
                                # 🔥 更新进度
                                if task_id in global_var.tasks and result:
                                    global_var.tasks[task_id]['current_item'] += 1
                                    global_var.tasks[task_id]['current_page'] += 1
                                return result
                            return None
                        except Exception as e:
                            print(f"[generate_full_abstract_task] 生成全文摘要失败: {e}")
                            import traceback
                            traceback.print_exc()
                            return None

                    def generate_full_boundary_task():
                        """生成全文边界问题描述汇总"""
                        try:
                            # 🔥 更新进度
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_section'] = '生成全文边界问题描述汇总'
                            if chapter_boundaries:
                                result = _generate_full_boundary_summary(chapter_boundaries,
                                                                         directory_structure['title'], username)
                                # 🔥 更新进度
                                if task_id in global_var.tasks and result:
                                    global_var.tasks[task_id]['current_item'] += 1
                                    global_var.tasks[task_id]['current_page'] += 1
                                return result
                            return None
                        except Exception as e:
                            print(f"[generate_full_boundary_task] 生成全文边界问题描述汇总失败: {e}")
                            import traceback
                            traceback.print_exc()
                            return None

                    # 使用2个线程并发执行
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        future_abstract = executor.submit(generate_full_abstract_task)
                        future_boundary = executor.submit(generate_full_boundary_task)

                        full_abstract = future_abstract.result()
                        full_boundary_summary = future_boundary.result()

                    # 将摘要插入到目录标题后，正文内容前
                    if full_abstract:
                        # 🔥 更新进度
                        if task_id in global_var.tasks:
                            global_var.tasks[task_id]['current_section'] = '生成关键词'
                        # 提取关键词（从摘要中提取，或使用LLM生成）
                        keywords = _generate_keywords_from_abstract(full_abstract, directory_structure['title'],
                                                                    username)
                        # 🔥 更新进度
                        if task_id in global_var.tasks and keywords:
                            global_var.tasks[task_id]['current_item'] += 1
                            global_var.tasks[task_id]['current_page'] += 1
                            global_var.tasks[task_id]['current_section'] = '完成摘要和边界问题描述'

                        # 构建摘要和关键词部分
                        abstract_keywords_section = f"## 摘要\n\n{full_abstract}\n\n"
                        if keywords:
                            abstract_keywords_section += f"## 关键词\n\n{keywords}\n\n"

                        # 将摘要和关键词插入到正文开头（目录标题后）
                        full_article = abstract_keywords_section + full_article
                        print(f"[generate_output_article] 已添加摘要和关键词到正文开头")

                    # 将边界问题描述插入到参考文献后
                    if full_boundary_summary:
                        # 查找参考文献的位置
                        ref_pattern = r'##\s*参考文献'
                        ref_match = re.search(ref_pattern, full_article, re.IGNORECASE)
                        if ref_match:
                            # 在参考文献后插入边界问题描述
                            ref_end_pos = ref_match.end()
                            # 找到参考文献部分的结束位置（下一个##或文件结尾）
                            next_section_match = re.search(r'\n##\s+', full_article[ref_end_pos:])
                            if next_section_match:
                                insert_pos = ref_end_pos + next_section_match.start()
                            else:
                                insert_pos = len(full_article)

                            boundary_section = f"\n\n## 边界问题描述\n\n{full_boundary_summary}\n\n"
                            full_article = full_article[:insert_pos] + boundary_section + full_article[insert_pos:]
                            print(f"[generate_output_article] 已添加边界问题描述到参考文献后")
                        else:
                            # 如果没有参考文献，直接追加到末尾
                            full_article += f"\n\n## 边界问题描述\n\n{full_boundary_summary}\n\n"
                            print(f"[generate_output_article] 已添加边界问题描述到文章末尾")

                # 🔥 迭代模式（有摘要/关键词/边界问题描述）：迭代它们
                elif has_existing_article:
                    # 重新检测（已在上面检测过，这里复用结果）
                    if should_skip_body_iteration:
                        # 情况（1）：没有摘要/关键词/边界问题描述，生成它们
                        print(f"[generate_output_article] 开始生成摘要和边界问题描述（跳过正文迭代）...")

                        # 从现有正文中提取各章内容（用于生成摘要和边界问题描述）
                        chapter_contents = {}  # {chapter_idx: chapter_content}
                        allocations = word_count_allocation['allocations']['chapters']

                        # 从现有正文（full_article）中提取各章内容
                        for chapter_idx, chapter_alloc in enumerate(allocations):
                            chapter_name = chapter_alloc['name']
                            chapter_name_with_prefix = chapter_alloc.get('name_with_prefix', chapter_name)

                            # 在现有正文中查找该章的内容
                            chapter_pattern = rf'##\s+{re.escape(chapter_name_with_prefix)}\s*\n(.*?)(?=\n##\s+|$)'
                            chapter_match = re.search(chapter_pattern, full_article, re.DOTALL)

                            if chapter_match:
                                chapter_content = chapter_match.group(1).strip()
                                chapter_contents[chapter_idx] = {
                                    'name': chapter_name,
                                    'content': chapter_content
                                }
                            else:
                                # 如果没找到，尝试使用章节名（不带序号）
                                chapter_pattern2 = rf'##\s+.*?{re.escape(chapter_name)}\s*\n(.*?)(?=\n##\s+|$)'
                                chapter_match2 = re.search(chapter_pattern2, full_article, re.DOTALL)
                                if chapter_match2:
                                    chapter_content = chapter_match2.group(1).strip()
                                    chapter_contents[chapter_idx] = {
                                        'name': chapter_name,
                                        'content': chapter_content
                                    }

                        # 🔥 更新总任务数和进度信息（在提取完章节内容后）
                        num_chapters = len(chapter_contents)
                        additional_steps = num_chapters + 3  # 各章摘要边界描述 + 全文摘要 + 全文边界汇总 + 关键词
                        if task_id in global_var.tasks:
                            global_var.tasks[task_id]['total_items'] = additional_steps
                            global_var.tasks[task_id]['total_pages'] = additional_steps
                            global_var.tasks[task_id]['current_item'] = 0
                            global_var.tasks[task_id]['current_section'] = '生成摘要和边界问题描述'
                            print(f"[generate_output_article] 更新总任务数: {additional_steps}")

                        # 并发生成各章的摘要和边界问题描述（最多4个并发）
                        chapter_summaries = []  # [(章名, 摘要), ...]
                        chapter_boundaries = []  # [(章名, 边界问题描述), ...]

                        def generate_chapter_summary_boundary(chapter_idx):
                            """生成单章的摘要和边界问题描述"""
                            try:
                                if chapter_idx not in chapter_contents:
                                    return None, None, None

                                chapter_data = chapter_contents[chapter_idx]
                                chapter_name = chapter_data['name']
                                chapter_content = chapter_data['content']

                                # 获取该章的目录结构信息
                                chapter_structure = None
                                allocations = word_count_allocation['allocations']['chapters']
                                if chapter_idx < len(allocations):
                                    chapter_alloc = allocations[chapter_idx]
                                    chapter_structure = {
                                        'sections': chapter_alloc.get('sections', [])
                                    }

                                print(
                                    f"[generate_chapter_summary_boundary] 开始生成第{chapter_idx + 1}章({chapter_name})的摘要和边界问题描述")

                                # 🔥 更新进度
                                if task_id in global_var.tasks:
                                    global_var.tasks[task_id]['current_section'] = f'生成第{chapter_idx + 1}章摘要和边界问题描述'

                                summary, boundary = _generate_chapter_summary_and_boundary(
                                    chapter_name, chapter_content, directory_structure['title'], username,
                                    chapter_structure=chapter_structure
                                )

                                if summary and boundary:
                                    print(
                                        f"[generate_chapter_summary_boundary] 完成第{chapter_idx + 1}章({chapter_name})的摘要和边界问题描述")
                                    # 🔥 更新进度
                                    if task_id in global_var.tasks:
                                        global_var.tasks[task_id]['current_item'] += 1
                                        global_var.tasks[task_id]['current_page'] += 1
                                    return chapter_idx, summary, boundary
                                else:
                                    print(
                                        f"[generate_chapter_summary_boundary] ⚠️ 第{chapter_idx + 1}章({chapter_name})生成失败")
                                    return None, None, None
                            except Exception as e:
                                print(f"[generate_chapter_summary_boundary] 生成第{chapter_idx + 1}章失败: {e}")
                                import traceback
                                traceback.print_exc()
                                return None, None, None

                        # 使用线程池并发执行（最多4个并发）
                        with ThreadPoolExecutor(max_workers=4) as executor:
                            futures = {executor.submit(generate_chapter_summary_boundary, idx): idx
                                       for idx in chapter_contents.keys()}

                            results = {}  # {chapter_idx: (summary, boundary)}
                            for future in as_completed(futures):
                                try:
                                    chapter_idx, summary, boundary = future.result()
                                    if chapter_idx is not None and summary and boundary:
                                        results[chapter_idx] = (summary, boundary)
                                except Exception as e:
                                    print(f"[generate_output_article] 获取章节摘要和边界问题描述结果失败: {e}")

                        # 按章节顺序整理
                        for chapter_idx in sorted(results.keys()):
                            summary, boundary = results[chapter_idx]
                            chapter_name = chapter_contents[chapter_idx]['name']
                            chapter_summaries.append((chapter_name, summary))
                            chapter_boundaries.append((chapter_name, boundary))

                        # 生成全文摘要和边界问题描述汇总（2个线程）
                        full_abstract = None
                        full_boundary_summary = None

                        def generate_full_abstract_task():
                            """生成全文摘要"""
                            try:
                                # 🔥 更新进度
                                if task_id in global_var.tasks:
                                    global_var.tasks[task_id]['current_section'] = '生成全文摘要'
                                if chapter_summaries:
                                    result = _generate_full_abstract(chapter_summaries, directory_structure['title'],
                                                                     username)
                                    # 🔥 更新进度
                                    if task_id in global_var.tasks and result:
                                        global_var.tasks[task_id]['current_item'] += 1
                                        global_var.tasks[task_id]['current_page'] += 1
                                    return result
                                return None
                            except Exception as e:
                                print(f"[generate_full_abstract_task] 生成全文摘要失败: {e}")
                                import traceback
                                traceback.print_exc()
                                return None

                        def generate_full_boundary_task():
                            """生成全文边界问题描述汇总"""
                            try:
                                # 🔥 更新进度
                                if task_id in global_var.tasks:
                                    global_var.tasks[task_id]['current_section'] = '生成全文边界问题描述汇总'
                                if chapter_boundaries:
                                    result = _generate_full_boundary_summary(chapter_boundaries,
                                                                             directory_structure['title'], username)
                                    # 🔥 更新进度
                                    if task_id in global_var.tasks and result:
                                        global_var.tasks[task_id]['current_item'] += 1
                                        global_var.tasks[task_id]['current_page'] += 1
                                    return result
                                return None
                            except Exception as e:
                                print(f"[generate_full_boundary_task] 生成全文边界问题描述汇总失败: {e}")
                                import traceback
                                traceback.print_exc()
                                return None

                        # 使用2个线程并发执行
                        with ThreadPoolExecutor(max_workers=2) as executor:
                            future_abstract = executor.submit(generate_full_abstract_task)
                            future_boundary = executor.submit(generate_full_boundary_task)

                            full_abstract = future_abstract.result()
                            full_boundary_summary = future_boundary.result()

                        # 将摘要插入到目录标题后，正文内容前
                        if full_abstract:
                            # 🔥 更新进度
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_section'] = '生成关键词'
                            # 提取关键词（从摘要中提取，或使用LLM生成）
                            keywords = _generate_keywords_from_abstract(full_abstract, directory_structure['title'],
                                                                        username)
                            # 🔥 更新进度
                            if task_id in global_var.tasks and keywords:
                                global_var.tasks[task_id]['current_item'] += 1
                                global_var.tasks[task_id]['current_page'] += 1
                                global_var.tasks[task_id]['current_section'] = '完成摘要和边界问题描述'

                            # 构建摘要和关键词部分
                            abstract_keywords_section = f"## 摘要\n\n{full_abstract}\n\n"
                            if keywords:
                                abstract_keywords_section += f"## 关键词\n\n{keywords}\n\n"

                            # 将摘要和关键词插入到正文开头（目录标题后）
                            full_article = abstract_keywords_section + full_article
                            print(f"[generate_output_article] 已添加摘要和关键词到正文开头")

                        # 将边界问题描述插入到参考文献后
                        if full_boundary_summary:
                            # 查找参考文献的位置
                            ref_pattern = r'##\s*参考文献'
                            ref_match = re.search(ref_pattern, full_article, re.IGNORECASE)
                            if ref_match:
                                # 在参考文献后插入边界问题描述
                                ref_end_pos = ref_match.end()
                                # 找到参考文献部分的结束位置（下一个##或文件结尾）
                                next_section_match = re.search(r'\n##\s+', full_article[ref_end_pos:])
                                if next_section_match:
                                    insert_pos = ref_end_pos + next_section_match.start()
                                else:
                                    insert_pos = len(full_article)

                                boundary_section = f"\n\n## 边界问题描述\n\n{full_boundary_summary}\n\n"
                                full_article = full_article[:insert_pos] + boundary_section + full_article[insert_pos:]
                            else:
                                # 如果没有参考文献，直接追加到末尾
                                full_article += f"\n\n## 边界问题描述\n\n{full_boundary_summary}\n\n"

                            print(f"[generate_output_article] 已添加边界问题描述到正文末尾")
                    else:
                        # 情况（2）：有摘要/关键词/边界问题描述，迭代它们
                        print(f"[generate_output_article] 开始迭代摘要、关键词和边界问题描述...")

                        # 提取现有的摘要、关键词和边界问题描述
                        existing_abstract, existing_keywords, existing_boundary = _extract_abstract_keywords_boundary(
                            existing_article_content)

                        # 🔥 更新总任务数（在正文任务基础上增加摘要、关键词、边界问题描述的迭代任务）
                        if task_id in global_var.tasks:
                            current_total = global_var.tasks[task_id]['total_items']
                            # 最多3个额外任务：摘要迭代、关键词迭代、边界问题描述迭代
                            additional_steps = 0
                            if existing_abstract:
                                additional_steps += 1
                            if existing_keywords:
                                additional_steps += 1  # 虽然当前不迭代，但预留位置
                            if existing_boundary:
                                additional_steps += 1
                            global_var.tasks[task_id]['total_items'] = current_total + additional_steps
                            global_var.tasks[task_id]['total_pages'] = current_total + additional_steps
                            global_var.tasks[task_id]['current_section'] = '迭代摘要和边界问题描述'
                            print(
                                f"[generate_output_article] 更新总任务数: {current_total} -> {current_total + additional_steps}")

                        # 迭代摘要、关键词和边界问题描述（粒度更小，3-5%以内）
                        if existing_abstract:
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_section'] = '迭代摘要'
                            iterated_abstract = _iterate_abstract_keywords(existing_abstract, full_article,
                                                                           directory_structure['title'], username,
                                                                           is_abstract=True,
                                                                           directory_structure=directory_structure,
                                                                           max_iteration_in_full_article=max_iteration_in_full_article)  # 🔥 需求③：传递全文最大迭代次数
                            if iterated_abstract:
                                existing_abstract = iterated_abstract
                                # 🔥 更新进度
                                if task_id in global_var.tasks:
                                    global_var.tasks[task_id]['current_item'] += 1
                                    global_var.tasks[task_id]['current_page'] += 1

                        if existing_keywords:
                            # 如果没有大改动，关键词可以不调，微调摘要即可（3-5%以内）
                            # 这里先不迭代关键词，只迭代摘要
                            # 🔥 但更新进度（跳过但计入总数）
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_item'] += 1
                                global_var.tasks[task_id]['current_page'] += 1
                            pass

                        if existing_boundary:
                            if task_id in global_var.tasks:
                                global_var.tasks[task_id]['current_section'] = '迭代边界问题描述'
                            iterated_boundary = _iterate_boundary_description(existing_boundary, full_article,
                                                                              directory_structure['title'], username,
                                                                              directory_structure=directory_structure,
                                                                              max_iteration_in_full_article=max_iteration_in_full_article)  # 🔥 需求③：传递全文最大迭代次数
                            if iterated_boundary:
                                existing_boundary = iterated_boundary
                                # 🔥 更新进度
                                if task_id in global_var.tasks:
                                    global_var.tasks[task_id]['current_item'] += 1
                                    global_var.tasks[task_id]['current_page'] += 1
                                    global_var.tasks[task_id]['current_section'] = '完成迭代'

                        # 将迭代后的摘要、关键词和边界问题描述插入到正确位置
                        # 移除原有的摘要、关键词和边界问题描述
                        full_article = _remove_abstract_keywords_boundary(full_article)

                        # 插入摘要和关键词到正文开头
                        if existing_abstract:
                            abstract_keywords_section = f"## 摘要\n\n{existing_abstract}\n\n"
                            if existing_keywords:
                                abstract_keywords_section += f"## 关键词\n\n{existing_keywords}\n\n"
                            full_article = abstract_keywords_section + full_article

                        # 插入边界问题描述到参考文献后
                        if existing_boundary:
                            ref_pattern = r'##\s*参考文献'
                            ref_match = re.search(ref_pattern, full_article, re.IGNORECASE)
                            if ref_match:
                                ref_end_pos = ref_match.end()
                                next_section_match = re.search(r'\n##\s+', full_article[ref_end_pos:])
                                if next_section_match:
                                    insert_pos = ref_end_pos + next_section_match.start()
                                else:
                                    insert_pos = len(full_article)

                                boundary_section = f"\n\n## 边界问题描述\n\n{existing_boundary}\n\n"
                                full_article = full_article[:insert_pos] + boundary_section + full_article[insert_pos:]
                            else:
                                full_article += f"\n\n## 边界问题描述\n\n{existing_boundary}\n\n"

                # 🔥 步骤1：对各章各节进行红蓝卡标评分
                print(f"[generate_output_article] 开始对各章各节进行红蓝卡标评分...")
                sections_for_scoring = _extract_sections_for_scoring(full_article, directory_structure)
                scored_sections = _score_sections_with_small_model(sections_for_scoring, username)
                print(f"[generate_output_article] 红蓝卡标评分完成，共评分{len(scored_sections)}个节")

                # 🔥 步骤2：生成thinking/checking代码块（最终整理）
                thinking_checking_blocks = ""
                if scored_sections:
                    # 🔥 更新进度信息（最终整理）- 总任务数已在章节首尾处理时一次性更新
                    if task_id in global_var.tasks:
                        global_var.tasks[task_id]['current_section'] = '最终整理'
                    print(f"[generate_output_article] 开始生成thinking/checking代码块...")
                    thinking_checking_blocks = _generate_thinking_checking_with_claude(
                        scored_sections, directory_structure, full_article, username
                    )
                    if thinking_checking_blocks:
                        # 将thinking/checking代码块添加到边界问题描述后面
                        full_article += f"\n\n{thinking_checking_blocks}\n"
                        print(f"[generate_output_article] thinking/checking代码块已添加到文章末尾")
                        # 🔥 更新进度（最终整理完成）
                        if task_id in global_var.tasks:
                            global_var.tasks[task_id]['current_item'] += 1
                            global_var.tasks[task_id]['current_page'] += 1
                    else:
                        print(f"[generate_output_article] thinking/checking代码块生成失败或为空")
                        # 🔥 即使失败也要更新进度
                        if task_id in global_var.tasks:
                            global_var.tasks[task_id]['current_item'] += 1
                            global_var.tasks[task_id]['current_page'] += 1
                else:
                    print(f"[generate_output_article] 无评分结果，跳过thinking/checking代码块生成")

                # 更新卡片内容（将文章内容追加到目录后面）
                directory_card = Card.objects.get(cid=card_id, username=username)
                original_content = directory_card.content or ""

                # 提取目录部分（第一个"# "之前的内容）
                lines = original_content.split('\n')
                directory_end_idx = len(lines)
                for i, line in enumerate(lines):
                    if line.strip().startswith('# ') and i > 0:
                        directory_end_idx = i
                        break

                directory_part = '\n'.join(lines[:directory_end_idx]).rstrip()

                # 构建新内容：目录部分 + # 目录标题 + 文章内容（无论之前是否有文章，都替换）
                directory_title = directory_structure['title']
                new_content = directory_part + '\n\n# ' + directory_title + '\n\n' + full_article

                # 🔥 清理4字节UTF-8字符（emoji等），避免MySQL utf8字符集报错
                new_content = _clean_4byte_utf8_chars(new_content)
                original_content = _clean_4byte_utf8_chars(original_content) if original_content else original_content

                # 保存原内容到lastContent，新内容写入content
                directory_card.lastContent = original_content
                directory_card.content = new_content
                directory_card.save()

                # 清理任务进度
                if task_id in global_var.tasks:
                    del global_var.tasks[task_id]

                print(f"[generate_output_article] 后台任务完成: {task_id}")
            except Exception as e:
                print(f"[generate_output_article] 后台任务失败: {e}")
                import traceback
                traceback.print_exc()
                # 清理任务进度
                if task_id in global_var.tasks:
                    del global_var.tasks[task_id]

        # 🔥 在后台线程中执行生成任务
        thread = threading.Thread(target=generate_article_in_background)
        thread.daemon = True
        thread.start()

        # 🔥 立即返回task_id，不等待任务完成
        return JsonResponse({
            'error_num': 0,
            'msg': '文章生成已开始' if not has_existing_article else '文章迭代精进已开始',
            'card_id': card_id,
            'task_id': task_id,
            'total_tasks': total_tasks
        })

    except Exception as e:
        print(f"[generate_output_article] 错误: {e}")
        import traceback
        traceback.print_exc()
        # 清理任务进度（如果存在）
        if 'task_id' in locals():
            from llm_langchain import global_var
            if task_id in global_var.tasks:
                del global_var.tasks[task_id]

        return JsonResponse({
            'error_num': 1,
            'msg': f'生成失败: {str(e)}'
        })


#     """
#     根据目录卡片生成完整的输出文章

#     并发撰写各个章节（最多4个并发）
#     """
#     try:
#         data = json.loads(request.body)
#         card_id = data.get('card_id')
#         username = data.get('username')
#         scene_name = data.get('scene_name')

#         if not card_id or not username:
#             return JsonResponse({
#                 'error_num': 1,
#                 'msg': '参数不完整'
#             })

#         # 获取目录卡片
#         try:
#             directory_card = Card.objects.get(cid=card_id, username=username)
#         except Card.DoesNotExist:
#             return JsonResponse({
#                 'error_num': 1,
#                 'msg': '目录卡片不存在'
#             })

#         # 检查是否为目录卡
#         if directory_card.title != "本子输出目录卡":
#             return JsonResponse({
#                 'error_num': 1,
#                 'msg': '不是目录卡片'
#             })

#         # 解析目录结构（只解析目录部分，不包括已生成的文章）
#         original_content = directory_card.content or ""

#         # 提取目录部分（第一个"# "之前的内容，注意现在用# xxx分隔，而不是## xxx）
#         lines = original_content.split('\n')
#         directory_end_idx = len(lines)
#         for i, line in enumerate(lines):
#             if line.strip().startswith('# ') and i > 0:  # 不是第一行，且是章节标题（# xxx）
#                 directory_end_idx = i
#                 break

#         directory_content = '\n'.join(lines[:directory_end_idx]).rstrip()

#         directory_structure = _parse_directory_structure(directory_content)
#         if not directory_structure:
#             return JsonResponse({
#                 'error_num': 1,
#                 'msg': '目录结构解析失败'
#             })

#         # 计算字数分配
#         word_count_allocation = _calculate_word_count_allocation(directory_structure, target_total_words=5000)
#         if not word_count_allocation:
#             return JsonResponse({
#                 'error_num': 1,
#                 'msg': '字数分配计算失败'
#             })

#         # 准备所有需要撰写的任务
#         writing_tasks = []  # [(section_name, section_type, word_count, parent_section_name, parent_chapter_name, directory_title, ...), ...]

#         allocations = word_count_allocation['allocations']['chapters']
#         for chapter_idx, chapter_alloc in enumerate(allocations):
#             chapter_name = chapter_alloc['name']

#             if not chapter_alloc['sections']:
#                 # 没有节，直接写章
#                 writing_tasks.append({
#                     'section_name': chapter_name,
#                     'section_type': 'chapter',
#                     'word_count': chapter_alloc['word_count'],
#                     'parent_section_name': None,
#                     'parent_chapter_name': None,
#                     'directory_title': directory_structure['title'],
#                     'chapter_idx': chapter_idx,
#                     'section_idx': None,
#                     'subsection_idx': None
#                 })
#             else:
#                 for section_idx, section_alloc in enumerate(chapter_alloc['sections']):
#                     section_name = section_alloc['name']

#                     if not section_alloc['subsections']:
#                         # 没有小节，直接写节
#                         writing_tasks.append({
#                             'section_name': section_name,
#                             'section_type': 'section',
#                             'word_count': section_alloc['word_count'],
#                             'parent_section_name': None,
#                             'parent_chapter_name': chapter_name,
#                             'directory_title': directory_structure['title'],
#                             'chapter_idx': chapter_idx,
#                             'section_idx': section_idx,
#                             'subsection_idx': None
#                         })
#                     else:
#                         # 有小节，写每个小节
#                         for subsection_idx, subsection_alloc in enumerate(section_alloc['subsections']):
#                             subsection_name = subsection_alloc['name']

#                             # 获取相邻小节列表（用于过渡）
#                             adjacent_subsections = []
#                             if subsection_idx > 0:
#                                 prev_subsection = section_alloc['subsections'][subsection_idx - 1]
#                                 adjacent_subsections.append(prev_subsection['name'])
#                             if subsection_idx < len(section_alloc['subsections']) - 1:
#                                 next_subsection = section_alloc['subsections'][subsection_idx + 1]
#                                 adjacent_subsections.append(next_subsection['name'])

#                             writing_tasks.append({
#                                 'section_name': subsection_name,
#                                 'section_type': 'subsection',
#                                 'word_count': subsection_alloc['word_count'],
#                                 'parent_section_name': section_name,
#                                 'parent_chapter_name': chapter_name,
#                                 'directory_title': directory_structure['title'],
#                                 'chapter_idx': chapter_idx,
#                                 'section_idx': section_idx,
#                                 'subsection_idx': subsection_idx,
#                                 'adjacent_sections': adjacent_subsections,
#                                 'is_first': (chapter_idx == 0 and section_idx == 0 and subsection_idx == 0),
#                                 'is_last': (chapter_idx == len(allocations) - 1 and
#                                             section_idx == len(chapter_alloc['sections']) - 1 and
#                                             subsection_idx == len(section_alloc['subsections']) - 1)
#                             })

#         # 并发撰写（最多4个并发）
#         from concurrent.futures import ThreadPoolExecutor, as_completed
#         import uuid
#         from llm_langchain import global_var

#         # 🔥 创建任务ID用于进度跟踪
#         task_id = f"article_gen_{card_id}_{uuid.uuid4().hex[:8]}"
#         total_tasks = len(writing_tasks)

#         # 初始化进度
#         global_var.tasks[task_id] = {
#             'current_page': 0,
#             'total_pages': total_tasks,
#             'current_item': 0,
#             'total_items': total_tasks,
#             'current_section': ''
#         }

#         # 🔥 在后台线程中执行文章生成
#         def generate_article_in_background():
#             """在后台线程中执行文章生成"""
#             try:
#                 writing_results = {}  # {(chapter_idx, section_idx, subsection_idx): (content, model_used)}

#                 def write_section(task):
#                     """撰写单个章节的函数"""
#                     try:
#                         # 更新进度：当前正在处理的章节（在开始前就更新，让前端能立即看到）
#                         if task_id in global_var.tasks:
#                             global_var.tasks[task_id]['current_section'] = task['section_name']
#                             print(
#                                 f"[write_section] 开始撰写: {task['section_name']}, 进度: {global_var.tasks[task_id]['current_item']}/{global_var.tasks[task_id]['total_items']}")

#                         # 获取相关卡片和文档
#                         relevant_cards = _get_relevant_cards_for_section(
#                             task['section_name'], username, max_cards=5
#                         )
#                         relevant_docs = _get_relevant_documents_for_section(
#                             task['section_name'], username, max_docs=3
#                         )

#                         # 生成内容
#                         content, model_used = _generate_section_content(
#                             section_name=task['section_name'],
#                             section_type=task['section_type'],
#                             word_count=task['word_count'],
#                             parent_section_name=task['parent_section_name'],
#                             parent_chapter_name=task['parent_chapter_name'],
#                             directory_title=task['directory_title'],
#                             relevant_cards=relevant_cards,
#                             relevant_docs=relevant_docs,
#                             adjacent_sections=task.get('adjacent_sections', []),
#                             is_first=task.get('is_first', False),
#                             is_last=task.get('is_last', False)
#                         )

#                         # 更新进度：已完成数+1（在完成后更新）
#                         if task_id in global_var.tasks:
#                             global_var.tasks[task_id]['current_page'] += 1
#                             global_var.tasks[task_id]['current_item'] += 1
#                             print(
#                                 f"[write_section] 完成撰写: {task['section_name']}, 进度: {global_var.tasks[task_id]['current_item']}/{global_var.tasks[task_id]['total_items']}")

#                         key = (task['chapter_idx'], task['section_idx'], task['subsection_idx'])
#                         return (key, content, model_used)
#                     except Exception as e:
#                         print(f"[write_section] 撰写章节失败: {e}")
#                         import traceback
#                         traceback.print_exc()
#                         # 即使失败也要更新进度
#                         if task_id in global_var.tasks:
#                             global_var.tasks[task_id]['current_page'] += 1
#                             global_var.tasks[task_id]['current_item'] += 1
#                         key = (task['chapter_idx'], task['section_idx'], task['subsection_idx'])
#                         return (key, None, None)

#                 # 使用线程池并发执行（最多4个并发）
#                 with ThreadPoolExecutor(max_workers=4) as executor:
#                     futures = {executor.submit(write_section, task): task for task in writing_tasks}

#                     for future in as_completed(futures):
#                         try:
#                             key, content, model_used = future.result()
#                             writing_results[key] = (content, model_used)
#                         except Exception as e:
#                             print(f"[generate_output_article] 获取撰写结果失败: {e}")

#                 # 按顺序组装文章内容
#                 allocations = word_count_allocation['allocations']['chapters']
#                 article_parts = []
#                 print(f"[generate_output_article] 开始组装文章，共{len(allocations)}章")
#                 for chapter_idx, chapter_alloc in enumerate(allocations):
#                     chapter_name = chapter_alloc['name']
#                     chapter_name_with_prefix = chapter_alloc.get('name_with_prefix', chapter_name)  # 🔥 使用带序号的全名
#                     print(
#                         f"[generate_output_article] 处理第{chapter_idx + 1}章: {chapter_name}, 共{len(chapter_alloc.get('sections', []))}节")

#                     if not chapter_alloc['sections']:
#                         # 没有节，直接写章
#                         key = (chapter_idx, None, None)
#                         if key in writing_results:
#                             content, _ = writing_results[key]
#                             if content:
#                                 article_parts.append(f"## {chapter_name_with_prefix}\n\n{content}\n\n")  # 🔥 使用带序号的全名
#                         else:
#                             print(f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章({chapter_name})没有生成结果")
#                     else:
#                         # 有节
#                         article_parts.append(f"## {chapter_name_with_prefix}\n\n")  # 🔥 使用带序号的全名

#                         for section_idx, section_alloc in enumerate(chapter_alloc['sections']):
#                             section_name = section_alloc['name']
#                             section_name_with_prefix = section_alloc.get('name_with_prefix', section_name)  # 🔥 使用带序号的全名
#                             print(
#                                 f"[generate_output_article] 处理第{chapter_idx + 1}章第{section_idx + 1}节: {section_name}, 共{len(section_alloc.get('subsections', []))}小节")

#                             if not section_alloc['subsections']:
#                                 # 没有小节，直接写节
#                                 key = (chapter_idx, section_idx, None)
#                                 if key in writing_results:
#                                     content, _ = writing_results[key]
#                                     if content:
#                                         article_parts.append(f"### {section_name_with_prefix}\n\n{content}\n\n")  # 🔥 使用带序号的全名
#                                     else:
#                                         print(
#                                             f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章第{section_idx + 1}节({section_name})内容为空")
#                                 else:
#                                     print(
#                                         f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章第{section_idx + 1}节({section_name})没有生成结果")
#                             else:
#                                 # 有小节，写每个小节
#                                 article_parts.append(f"### {section_name_with_prefix}\n\n")  # 🔥 使用带序号的全名

#                                 for subsection_idx, subsection_alloc in enumerate(section_alloc['subsections']):
#                                     subsection_name = subsection_alloc['name']
#                                     subsection_name_with_prefix = subsection_alloc.get('name_with_prefix', subsection_name)  # 🔥 使用带序号的全名
#                                     key = (chapter_idx, section_idx, subsection_idx)
#                                     if key in writing_results:
#                                         content, _ = writing_results[key]
#                                         if content:
#                                             article_parts.append(f"#### {subsection_name_with_prefix}\n\n{content}\n\n")  # 🔥 使用带序号的全名
#                                         else:
#                                             print(
#                                                 f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章第{section_idx + 1}节第{subsection_idx + 1}小节({subsection_name})内容为空")
#                                     else:
#                                         print(
#                                             f"[generate_output_article] ⚠️ 警告：第{chapter_idx + 1}章第{section_idx + 1}节第{subsection_idx + 1}小节({subsection_name})没有生成结果")

#                 # 组装完整文章
#                 full_article = '\n'.join(article_parts)

#                 # 更新卡片内容（将文章内容追加到目录后面）
#                 directory_card = Card.objects.get(cid=card_id, username=username)
#                 original_content = directory_card.content or ""

#                 # 提取目录部分（第一个"# "之前的内容，注意现在用# xxx分隔，而不是## xxx）
#                 lines = original_content.split('\n')
#                 directory_end_idx = len(lines)
#                 for i, line in enumerate(lines):
#                     if line.strip().startswith('# ') and i > 0:  # 不是第一行，且是章节标题（# xxx）
#                         directory_end_idx = i
#                         break

#                 directory_part = '\n'.join(lines[:directory_end_idx]).rstrip()

#                 # 构建新内容：目录部分 + # 目录标题 + 文章内容（无论之前是否有文章，都替换）
#                 directory_title = directory_structure['title']
#                 new_content = directory_part + '\n\n# ' + directory_title + '\n\n' + full_article

#                 # 保存原内容到lastContent，新内容写入content
#                 directory_card.lastContent = original_content
#                 directory_card.content = new_content
#                 directory_card.save()

#                 # 清理任务进度
#                 if task_id in global_var.tasks:
#                     del global_var.tasks[task_id]

#                 print(f"[generate_output_article] 后台任务完成: {task_id}")
#             except Exception as e:
#                 print(f"[generate_output_article] 后台任务失败: {e}")
#                 import traceback
#                 traceback.print_exc()
#                 # 清理任务进度
#                 if task_id in global_var.tasks:
#                     del global_var.tasks[task_id]

#         # 🔥 在后台线程中执行生成任务
#         thread = threading.Thread(target=generate_article_in_background)
#         thread.daemon = True
#         thread.start()

#         # 🔥 立即返回task_id，不等待任务完成
#         return JsonResponse({
#             'error_num': 0,
#             'msg': '文章生成已开始',
#             'card_id': card_id,
#             'task_id': task_id,
#             'total_tasks': total_tasks
#         })

#     except Exception as e:
#         print(f"[generate_output_article] 错误: {e}")
#         import traceback
#         traceback.print_exc()
#         # 清理任务进度（如果存在）
#         if 'task_id' in locals() and task_id:
#             from llm_langchain import global_var
#             if task_id in global_var.tasks:
#                 del global_var.tasks[task_id]

#         return JsonResponse({
#             'error_num': 1,
#             'msg': f'生成失败: {str(e)}'
#         })


@csrf_exempt
def article_generation_progress(request, task_id):
    """
    查询文章生成进度（轮询方式，返回单次进度数据）
    """
    from llm_langchain import global_var

    print(f"[article_generation_progress] 查询文章生成进度: {task_id}")

    task = global_var.tasks.get(task_id)
    if task is None:
        # 任务不存在，返回错误
        return JsonResponse({
            'current_item': -1,
            'total_items': -1,
            'current_section': '',
            'completed': True,
            'error': 'Task not found'
        })

    current_item = task.get('current_item', 0)
    total_items = task.get('total_items', 0)
    current_section = task.get('current_section', '')

    # 检查是否完成
    completed = (current_item >= total_items and total_items > 0)

    print(f"[article_generation_progress] 返回进度: {current_item}/{total_items}, 当前章节: {current_section}, 完成: {completed}")

    return JsonResponse({
        'current_item': current_item,
        'total_items': total_items,
        'current_section': current_section,
        'completed': completed
    })