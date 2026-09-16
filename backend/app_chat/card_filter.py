"""
卡片价值筛分工具
基于"5+3"框架中的"5"个维度筛选高价值卡片
新增：问题链索引卡中提问得分较高的卡片
"""

import json
import re
from collections import defaultdict


def extract_questions_from_card(card):
    """
    从卡片内容中提取问题（匹配"提问："或"迭代追问："格式）

    返回：问题列表
    """
    questions = []
    content = card.get('content', '')

    if not content:
        return questions

    # 匹配 "提问：xxx" 或 "迭代追问：xxx" 格式
    question_patterns = [
        r'提问[：:]\s*([^\n\r]+)',
        r'迭代追问[：:]\s*([^\n\r]+)'
    ]

    for pattern in question_patterns:
        matches = re.finditer(pattern, content)
        for match in matches:
            question = match.group(1).strip()
            if question and len(question) > 5:  # 过滤太短的问题
                questions.append(question)

    return questions


def calculate_question_score(question):
    """
    计算问题的综合评分（简版，基于问题长度、词汇多样性等）

    返回：0-5之间的评分
    """
    if not question:
        return 0

    length = len(question)
    question_marks = len(re.findall(r'[？?]', question))

    # 简单的中文分词：移除标点，按字符统计
    clean_text = re.sub(r'[，。！？；：""''（）【】\s]', '', question)
    unique_chars = len(set(clean_text))
    total_chars = len(clean_text)

    # 基础分数（调整为5分制）
    score = min(length / 10, 2.0)  # 长度分数，每10字符1分，最多2.0分
    score += min(question_marks * 1, 1.5)  # 问号分数，最多1.5分
    if total_chars > 0:
        score += min(unique_chars / total_chars * 2.5, 1.5)  # 字符多样性，最多1.5分

    return min(score, 5)  # 总分不超过5分


def filter_high_value_cards(cards_data):
    """
    从卡片列表中筛选出高价值卡片（DMT四色化卡片层）

    筛分规则（基于"6+1"维度）：
    1. 卡片勾选关系：被勾选次数最多的卡片 + 这些卡片的postIndex中的卡片
    2. 四色化：所有有四色标识的卡片（R/B/P/G）
    3. DMT化：所有有DMT标识的卡片（D/M/T）
    4. 卡片进化：做过进化的卡片
    5. 神经元卡：神经元卡（进化过的神经元卡很高价值）
    6. 问题链索引卡：包含提问得分较高（>=3.0分）问题的卡片
    7. 文件摘要卡片：以【文件摘要】或【综合摘要】开头的卡片

    返回：高价值卡片ID集合
    """
    if not cards_data:
        return set()

    # 统计每张卡片被勾选的次数（通过postIndex统计）
    selection_count_map = defaultdict(int)
    card_post_index_map = {}  # cid -> postIndex列表

    for card in cards_data:
        cid = card['cid']
        post_index_str = card.get('postIndex', '')
        if post_index_str:
            try:
                post_index_list = json.loads(post_index_str) if isinstance(post_index_str, str) else post_index_str
                if isinstance(post_index_list, list):
                    card_post_index_map[cid] = post_index_list
                    # 统计每张卡片被勾选的次数
                    for selected_cid in post_index_list:
                        selected_cid_int = int(selected_cid) if isinstance(selected_cid, str) else selected_cid
                        selection_count_map[selected_cid_int] += 1
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    # 更新selection_count
    for card in cards_data:
        cid = card['cid']
        card['selection_count'] = selection_count_map.get(cid, 0)

    # 找出被勾选次数最多的卡片
    if selection_count_map:
        max_selection_count = max(selection_count_map.values())
        # 被勾选次数最多的卡片（允许有多个并列）
        most_selected_cids = {cid for cid, count in selection_count_map.items() if count == max_selection_count}
    else:
        most_selected_cids = set()

    # 这些被勾选次数最多的卡片的postIndex中的卡片（也很重要）
    related_high_value_cids = set()
    for cid in most_selected_cids:
        if cid in card_post_index_map:
            related_high_value_cids.update([int(x) if isinstance(x, str) else x for x in card_post_index_map[cid]])

    # 1. 勾选关系：被勾选次数最多的卡片 + 这些卡片的postIndex中的卡片
    high_value_cids = most_selected_cids | related_high_value_cids

    # 2. 四色化：所有有四色标识的卡片（R/B/P/G）
    for card in cards_data:
        four_color_type = card.get('four_color_type', '')
        if four_color_type and four_color_type.strip() != '':
            high_value_cids.add(card['cid'])

    # 3. DMT化：所有有DMT标识的卡片（D/M/T）
    for card in cards_data:
        dmt_level = card.get('dmt_level', '')
        if dmt_level and dmt_level.strip() != '':
            high_value_cids.add(card['cid'])

    # 4. 卡片进化：做过进化的卡片
    for card in cards_data:
        if card.get('is_evolved', False):
            high_value_cids.add(card['cid'])

    # 5. 神经元卡：神经元卡（进化过的神经元卡很高价值）
    for card in cards_data:
        if card.get('is_neuron', False):
            high_value_cids.add(card['cid'])

    # 6. 问题链索引卡：包含提问得分较高（>=3.0分）问题的卡片
    for card in cards_data:
        questions = extract_questions_from_card(card)
        if questions:
            # 计算所有问题的平均得分
            question_scores = [calculate_question_score(q) for q in questions]
            if question_scores:
                avg_score = sum(question_scores) / len(question_scores)
                max_score = max(question_scores)
                # 如果平均分>=3.0或最高分>=3.5，认为是高价值问题链卡片
                if avg_score >= 3.0 or max_score >= 3.5:
                    high_value_cids.add(card['cid'])
                    print(f"[问题链筛分] 卡片{card['cid']}被识别为高价值问题链卡片: 平均分={avg_score:.2f}, 最高分={max_score:.2f}")

    # 7. 文件摘要卡片：以【文件摘要】或【综合摘要】开头的卡片
    for card in cards_data:
        content = card.get('content', '')
        if content:
            s = content.strip()
            if s.startswith('【文件摘要】') or s.startswith('【综合摘要】'):
                high_value_cids.add(card['cid'])
                print(f"[文件摘要筛分] 卡片{card['cid']}被识别为高价值文件摘要卡片")

    # 8. 文档交叉梳理建议卡片：以【文档全面交叉梳理建议卡片】开头的卡片
    for card in cards_data:
        content = card.get('content', '')
        if content and content.strip().startswith('【文档全面交叉梳理建议卡片】'):
            high_value_cids.add(card['cid'])
            print(f"[文档交叉梳理建议筛分] 卡片{card['cid']}被识别为高价值文档交叉梳理建议卡片")

    return high_value_cids


def get_filtered_cards(cards_data, target_count=None):
    """
    根据筛分规则，获取高价值卡片列表

    参数：
    - cards_data: 所有卡片数据列表
    - target_count: 已废弃，不再使用（保留参数以保持兼容性）

    返回：
    - (high_value_cards, all_cards): (高价值卡片列表, 所有卡片列表（高价值卡片在前）)
    """
    if not cards_data:
        return [], []

    # 获取高价值卡片ID集合
    high_value_cids = filter_high_value_cards(cards_data)

    # 计算每张卡片的价值分（用于排序）
    card_scores = {}
    for card in cards_data:
        cid = card['cid']
        score = 0

        # 神经元卡 + 进化 = 很高价值
        if card.get('is_neuron', False) and card.get('is_evolved', False):
            score += 100
        # 神经元卡
        elif card.get('is_neuron', False):
            score += 50
        # 进化卡
        elif card.get('is_evolved', False):
            score += 30

        # 四色类型：绿色 > 紫色 > 蓝色 > 红色
        four_color_type = card.get('four_color_type', '')
        if four_color_type == 'G':
            score += 20
        elif four_color_type == 'P':
            score += 15
        elif four_color_type == 'B':
            score += 5

        # DMT层次：T > M > D
        dmt_level = card.get('dmt_level', '')
        if dmt_level == 'T':
            score += 20
        elif dmt_level == 'M':
            score += 5

        # 被勾选次数
        selection_count = card.get('selection_count', 0)
        score += selection_count * 2

        # 文件摘要卡片：以【文件摘要】或【综合摘要】开头的卡片
        content = card.get('content', '')
        if content:
            s = content.strip()
            is_doc_summary = (
                (s.startswith('【文件摘要】') or s.startswith('【综合摘要】'))
                and (
                    '二、金句萃取与重要细节标注' in s
                    or '【跨文档综合】' in s
                    or '【分文档要点】' in s
                )
            )
            if is_doc_summary:
                score += 60  # 文件摘要卡片，加分较高

        # 文档交叉梳理建议卡片：以【文档全面交叉梳理建议卡片】开头的卡片
        if content and content.strip().startswith('【文档全面交叉梳理建议卡片】'):
            score += 60  # 文档交叉梳理建议卡片，加分和摘要卡片一样

        # 问题链索引卡：提问得分较高的卡片
        questions = extract_questions_from_card(card)
        if questions:
            question_scores = [calculate_question_score(q) for q in questions]
            if question_scores:
                avg_score = sum(question_scores) / len(question_scores)
                max_score = max(question_scores)
                # 根据问题得分给予额外加分（优先检查最高条件）
                if avg_score >= 3.5 and max_score >= 4.5:
                    # 同时满足综合评分>=3.5和最高分>=4.5，额外加分最多
                    score += 50
                elif avg_score >= 3.5:
                    # 综合评分>=3.5，加分较多
                    score += 40
                elif max_score >= 4.5:
                    # 最高分>=4.5，加分较多
                    score += 35

        card_scores[cid] = score

    # 🔥 只保留高价值卡片，并按价值分排序（不再有数量限制）
    high_value_cards = [card for card in cards_data if card['cid'] in high_value_cids]
    high_value_cards.sort(key=lambda x: card_scores.get(x['cid'], 0), reverse=True)

    high_value_cids = {card['cid'] for card in high_value_cards}

    # 所有卡片：高价值卡片在前，其他在后
    all_cards_ordered = []

    # 先添加高价值卡片（已排序）
    all_cards_ordered.extend(high_value_cards)

    # 再添加其他卡片（保持原顺序）
    for card in cards_data:
        if card['cid'] not in high_value_cids:
            all_cards_ordered.append(card)

    return high_value_cards, all_cards_ordered

