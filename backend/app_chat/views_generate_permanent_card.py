# encoding=utf-8
"""
🔥 生成永久卡片相关的视图函数
"""
import json
import os
import pandas as pd
import asyncio
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from app_chat.core.model_manager import model_manager
from app_chat.config.config_manager import config_manager
from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
from app_chat.models import Card
from zym.models import scene, UserNotebook
from llm_langchain import red_bule_rate
from llm_langchain.red_bule_rate import extract_number_SFT, extract_color_SFT, extract_reason_SFT
from llm_langchain import global_var
import re
import subprocess


def get_small_model_server_url(username):
    """
    根据username从全局变量获取小模型ID，返回对应的服务器URL
    3007 -> 192.0.2.1
    3001-3006 -> 192.0.2.1
    """
    from app_chat.global_state import GLOBAL_STATE
    model_id = GLOBAL_STATE.user_little_model_id.get(username, "3003")
    if str(model_id) == "3007":
        return "http://192.0.2.1:8000"
    else:
        return "http://192.0.2.1:8000"


def _sample_words_from_cards(reference_cards, keyword, max_samples=15):
    """
    从参考卡片中采样词汇，用于查找页码

    参数:
        reference_cards: 参考卡片列表（可以是Card对象或字典）
        keyword: 原始关键词（用于排除）
        max_samples: 最多采样次数

    返回:
        list: 采样到的词汇列表（按质量排序）
    """
    try:
        # 1. 对卡片按质量排序（优先永久卡、高分卡）
        sorted_cards = []
        for card in reference_cards:
            if isinstance(card, dict):
                is_neuron = card.get('is_neuron', False)
                card_type = card.get('type', '') or ''
                score = float(card.get('score', 0) or 0)
                scoreSFT = float(card.get('scoreSFT', 0) or 0)
                content = card.get('content', '') or ''
                weighted_score = score * 0.3 + scoreSFT * 0.7
            else:
                is_neuron = getattr(card, 'is_neuron', False)
                card_type = getattr(card, 'type', '') or ''
                score = float(getattr(card, 'score', 0) or 0)
                scoreSFT = float(getattr(card, 'scoreSFT', 0) or 0)
                content = getattr(card, 'content', '') or ''
                weighted_score = score * 0.3 + scoreSFT * 0.7

            # 计算优先级：永久卡>高分卡>其他
            priority = 0
            if is_neuron and '永久' in card_type:
                priority = 1000
            elif weighted_score >= 3.5:
                priority = 500
            else:
                priority = weighted_score * 100

            sorted_cards.append((card, priority, weighted_score))

        # 按优先级降序排序
        sorted_cards.sort(key=lambda x: (x[1], x[2]), reverse=True)

        # 2. 从卡片内容中提取词汇（2-8字的中文词汇或2-15字符的英文短语）
        sampled_words = []
        used_words = {keyword}  # 排除原始关键词

        for card, _, _ in sorted_cards:
            if isinstance(card, dict):
                content = card.get('content', '') or ''
            else:
                content = getattr(card, 'content', '') or ''

            if not content or len(sampled_words) >= max_samples:
                break

            # 提取中文词汇（2-8字）
            chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,8}', content)
            for word in chinese_words:
                if word not in used_words and len(word) >= 2:
                    sampled_words.append(word)
                    used_words.add(word)
                    if len(sampled_words) >= max_samples:
                        break

            if len(sampled_words) >= max_samples:
                break

            # 提取英文短语（2-15字符，连续的字母数字）
            english_phrases = re.findall(r'[a-zA-Z0-9]{2,15}', content)
            for phrase in english_phrases:
                if phrase not in used_words and len(phrase) >= 2:
                    sampled_words.append(phrase)
                    used_words.add(phrase)
                    if len(sampled_words) >= max_samples:
                        break

            if len(sampled_words) >= max_samples:
                break

        print(f"[_sample_words_from_cards] 从{len(sorted_cards)}张卡片中采样到{len(sampled_words)}个词汇")
        return sampled_words[:max_samples]
    except Exception as e:
        print(f"[_sample_words_from_cards] 采样词汇失败: {e}")
        return []


def _parse_page_ranges_for_docs(doc_names, keyword, username, reference_cards=None):
    """
    对给定的文档列表，解析每个文档中包含关键词的页数区间
    如果原始关键词找不到页码，会从参考卡片中采样词汇继续尝试（最多15次）

    参数:
        doc_names: 文档名列表
        keyword: 关键词
        username: 用户名（格式：用户名_本子名）
        reference_cards: 参考卡片列表（用于采样词汇），可以是Card对象或字典

    返回:
        list: [(文档名, 页数区间), ...] 列表，页数区间为(start_page, end_page)或None
    """
    try:
        if '_' not in username:
            return []

        realName = username.split('_')[0]
        bookName = username[len(realName) + 1:]
        pre_summary_dir = f'./received_dir/user_raw_file/{realName}_{bookName}/pre_summary'

        if not os.path.exists(pre_summary_dir):
            return [(doc_name, None) for doc_name in doc_names]

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

        # 在文档中查找页码的核心逻辑（返回两段最贴近的页数区间）
        def find_page_range_for_doc(doc_name, search_keyword):
            """
            在指定文档中查找包含搜索关键词的页数区间
            返回两段得分最高的页数区间（如果存在）
            """
            doc_name_base = os.path.splitext(doc_name)[0]
            doc_ext = os.path.splitext(doc_name)[1].lstrip('.')
            if not doc_ext:
                doc_ext = 'pdf'

            md_filename = f"{doc_name_base}_Presummary_{doc_ext}.md"
            md_file_path = os.path.join(pre_summary_dir, md_filename)

            if not os.path.exists(md_file_path):
                return None

            try:
                with open(md_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                sections = content.split('---')
                # 存储所有有页码的section及其得分
                section_scores = []  # [(score, page_range), ...]

                keyword_substrings = generate_substrings(search_keyword)

                for section in sections:
                    if not section.strip():
                        continue

                    section_score = 0
                    for substr in keyword_substrings:
                        pattern = re.escape(substr)
                        count = len(re.findall(pattern, section, re.IGNORECASE))
                        if count > 0:
                            section_score += len(substr) * count

                    # 如果section有得分且有页码，记录下来
                    if section_score > 0:
                        page_match = re.search(r'\[页码：第(\d+)页(?:-第(\d+)页)?\]', section)
                        if page_match:
                            start_page = int(page_match.group(1))
                            end_page = int(page_match.group(2)) if page_match.group(2) else start_page
                            page_range = (start_page, end_page)
                            section_scores.append((section_score, page_range))

                # 如果没有找到任何匹配的section，返回None
                if not section_scores:
                    return None

                # 按得分降序排序
                section_scores.sort(key=lambda x: x[0], reverse=True)

                # 取得分最高的两段（如果只有一段，只返回一段）
                if len(section_scores) >= 2:
                    # 返回两段：[(start1, end1), (start2, end2)]
                    return [section_scores[0][1], section_scores[1][1]]
                else:
                    # 只有一段，返回单元素列表
                    return [section_scores[0][1]]

            except Exception as e:
                print(f"[_parse_page_ranges_for_docs] 解析文档{doc_name}失败: {e}")
                return None

        # 准备采样词汇列表（如果需要）
        sampled_words = []
        if reference_cards:
            sampled_words = _sample_words_from_cards(reference_cards, keyword, max_samples=15)

        # 对所有文档，尝试用原始关键词和采样词汇查找页码
        results = []
        for doc_name in doc_names:
            page_ranges = None  # 现在是列表，可能包含1-2个页数区间

            # 1. 首先尝试用原始关键词
            page_ranges = find_page_range_for_doc(doc_name, keyword)
            if page_ranges:
                print(f"[_parse_page_ranges_for_docs] 文档{doc_name}使用原始关键词'{keyword}'找到页码: {page_ranges}")
                results.append((doc_name, page_ranges))
                continue

            # 2. 如果原始关键词找不到，尝试采样词汇（最多15次）
            found = False
            for sampled_word in sampled_words:
                page_ranges = find_page_range_for_doc(doc_name, sampled_word)
                if page_ranges:
                    print(f"[_parse_page_ranges_for_docs] 文档{doc_name}使用采样词汇'{sampled_word}'找到页码: {page_ranges}")
                    results.append((doc_name, page_ranges))
                    found = True
                    break

            if not found:
                print(
                    f"[_parse_page_ranges_for_docs] 文档{doc_name}经过{len(sampled_words) + 1}次尝试（原始关键词+{len(sampled_words)}个采样词汇）仍未找到页码")
                results.append((doc_name, None))

        return results
    except Exception as e:
        print(f"[_parse_page_ranges_for_docs] 错误: {e}")
        import traceback
        traceback.print_exc()
        return [(doc_name, None) for doc_name in doc_names]


def _find_documents_by_keyword(keyword, username, max_count=3, min_count=1):
    """
    根据关键词从pre_summary目录查找文档（新策略：当旧策略返回的文档列表为空时使用）

    参数:
        keyword: 关键词
        username: 用户名（格式：用户名_本子名）
        max_count: 最多返回的文档数量（默认3）
        min_count: 至少返回的文档数量（默认1）

    返回:
        list: 文档名列表，如果未找到则返回空列表
    """
    try:
        # 解析username获取realName和bookName
        if '_' not in username:
            print(f"[_find_documents_by_keyword] username格式不正确: {username}")
            return []

        realName = username.split('_')[0]
        bookName = username[len(realName) + 1:]

        # 构建pre_summary目录路径
        pre_summary_dir = f'./received_dir/user_raw_file/{realName}_{bookName}/pre_summary'

        if not os.path.exists(pre_summary_dir):
            print(f"[_find_documents_by_keyword] pre_summary目录不存在: {pre_summary_dir}")
            return []

        # 生成关键词的所有连续子字符串（从最长到最短）
        def generate_substrings(kw):
            substrings = []
            kw_len = len(kw)
            for length in range(kw_len, 0, -1):
                for start in range(kw_len - length + 1):
                    substr = kw[start:start + length]
                    if substr not in substrings:
                        substrings.append(substr)
            return substrings

        keyword_substrings = generate_substrings(keyword)

        # 遍历pre_summary目录中的所有.md文件，计算文档得分
        doc_results = {}  # {文档名: {'score': 总分}}

        # 获取本子内的所有文档名（用于匹配）
        all_document_names = []
        try:
            from zym.models import UserNotebook
            notebook = UserNotebook.objects.get(username=realName, bookName=bookName)
            if notebook.selectedFiles:
                try:
                    if isinstance(notebook.selectedFiles, str):
                        all_document_names = json.loads(notebook.selectedFiles)
                    else:
                        all_document_names = notebook.selectedFiles
                except:
                    all_document_names = []
        except:
            pass

        for filename in os.listdir(pre_summary_dir):
            if not filename.endswith('.md'):
                continue

            # 从文件名中提取原文档名和扩展名
            # 格式：original_filename_Presummary_filetype.md
            original_doc_name_match = re.match(r'^(.+?)_Presummary_(.+)\.md$', filename)
            if not original_doc_name_match:
                continue

            original_doc_name_base = original_doc_name_match.group(1)
            file_type = original_doc_name_match.group(2)  # 文件扩展名（如pdf、txt）
            file_path = os.path.join(pre_summary_dir, filename)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 计算文档中关键词子字符串的总得分
                total_score = 0
                for substr in keyword_substrings:
                    pattern = re.escape(substr)
                    count = len(re.findall(pattern, content, re.IGNORECASE))
                    if count > 0:
                        total_score += len(substr) * count

                # 如果找到了匹配，记录该文档
                if total_score > 0:
                    # 尝试匹配完整的文档名（可能包含扩展名）
                    matched_doc_name = None
                    # 构建可能的文档名（带扩展名）
                    possible_doc_name = f"{original_doc_name_base}.{file_type}"
                    # 在所有文档名中查找匹配
                    for doc_name in all_document_names:
                        doc_name_base = os.path.splitext(doc_name)[0]
                        if doc_name_base == original_doc_name_base or doc_name == possible_doc_name or doc_name == original_doc_name_base:
                            matched_doc_name = doc_name
                            break

                    # 如果找到了匹配的文档名，使用它；否则使用原始名称（可能不包含扩展名）
                    final_doc_name = matched_doc_name if matched_doc_name else original_doc_name_base
                    if final_doc_name not in doc_results or total_score > doc_results[final_doc_name]['score']:
                        doc_results[final_doc_name] = {
                            'score': total_score
                        }
            except Exception as e:
                print(f"[_find_documents_by_keyword] 读取文件失败 {file_path}: {e}")
                continue

        if not doc_results:
            print(f"[_find_documents_by_keyword] 未找到包含关键词'{keyword}'的文档")
            return []

        # 按得分排序，选择前max_count个
        sorted_docs = sorted(doc_results.items(), key=lambda x: x[1]['score'], reverse=True)
        selected_docs = sorted_docs[:max_count]

        # 如果找到的文档少于min_count，至少返回一个（如果有一个的话）
        if len(selected_docs) < min_count and len(sorted_docs) > 0:
            selected_docs = sorted_docs[:min_count]

        # 返回文档名列表
        doc_names = [doc_name for doc_name, _ in selected_docs]
        print(f"[_find_documents_by_keyword] 找到{len(doc_names)}个文档: {doc_names}")
        return doc_names

    except Exception as e:
        print(f"[_find_documents_by_keyword] 错误: {e}")
        import traceback
        traceback.print_exc()
        return []


def _analyze_human_machine_ratio(qa_cards, reference_cards_objs, notebook_desc=""):
    """
    分析人机认知比例，综合考虑问题链质量、卡片留存动机、修正标签等因素

    参数:
        qa_cards: QA问答卡列表
        reference_cards_objs: 参考卡片对象列表
        notebook_desc: 本子描述（用于判断问题链是否指向本子目标）

    返回:
        str: 人机认知比例，例如"3:7"或"4:6"
    """
    try:
        # 1. 分析问题链质量
        question_chain_score = 0  # 0-100分
        question_count = len(qa_cards) if qa_cards else 0

        if question_count > 0:
            # 检查问题链是否逐步引导推进
            has_progressive_questions = False
            has_scene_aligned_questions = False
            has_target_aligned_questions = False
            has_mechanical_questions = False
            has_conceptual_only_questions = False
            has_understanding_questions = False
            has_original_questions = False
            has_thinking_questions = False

            for qa_card in qa_cards:
                question = ""
                if isinstance(qa_card, dict):
                    question = qa_card.get('question', '')
                    if not question and qa_card.get('content'):
                        match = re.search(r'提问[：:]\s*([^\n\r]+)', qa_card['content'])
                        if match:
                            question = match.group(1).strip()
                elif hasattr(qa_card, 'content'):
                    match = re.search(r'提问[：:]\s*([^\n\r]+)', qa_card.content)
                    if match:
                        question = match.group(1).strip()

                if not question:
                    continue

                question_lower = question.lower()

                # 检查是否逐步引导（包含"如何"、"为什么"、"怎么样"等引导词）
                if re.search(r'(如何|为什么|怎么样|怎么|怎样|能否)', question):
                    has_progressive_questions = True

                # 检查是否贴合场景（如果本子描述存在，检查问题是否与本子相关）
                if notebook_desc and len(notebook_desc) > 0:
                    # 简单的相关性检查：问题中包含本子描述中的关键词
                    notebook_keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', notebook_desc[:100])
                    if any(kw in question for kw in notebook_keywords[:5]):  # 只检查前5个关键词
                        has_scene_aligned_questions = True

                # 检查是否指向本子目标（如果本子描述存在，检查是否包含目标相关词汇）
                if notebook_desc and re.search(r'(目标|目的|任务|实现|达成)', notebook_desc):
                    has_target_aligned_questions = True

                # 检查是否是机械发问（包含"什么是"、"是什么"等）
                if re.search(r'(什么是|是什么|定义)', question):
                    has_mechanical_questions = True

                # 检查是否偏学究的知识性概念性问题
                if re.search(r'(概念|定义|原理|理论|含义)', question) and not re.search(r'(如何|为什么|怎样)', question):
                    has_conceptual_only_questions = True

                # 检查是否有理解性问题（包含"理解"、"含义"、"意义"等）
                if re.search(r'(理解|含义|意义|影响|作用)', question):
                    has_understanding_questions = True

                # 检查是否有原创性问题（包含"设计"、"创建"、"构建"、"创新"等）
                if re.search(r'(设计|创建|构建|创新|提出|开发)', question):
                    has_original_questions = True

                # 检查是否有思维性问题（包含"思考"、"分析"、"评估"、"比较"等）
                if re.search(r'(思考|分析|评估|比较|对比|判断)', question):
                    has_thinking_questions = True

            # 计算问题链质量得分
            if has_progressive_questions:
                question_chain_score += 20
            if has_scene_aligned_questions:
                question_chain_score += 15
            if has_target_aligned_questions:
                question_chain_score += 15
            if has_understanding_questions:
                question_chain_score += 15
            if has_original_questions:
                question_chain_score += 15
            if has_thinking_questions:
                question_chain_score += 10

            # 扣分项
            if has_mechanical_questions and not has_progressive_questions:
                question_chain_score -= 10
            if has_conceptual_only_questions and (not has_understanding_questions and not has_thinking_questions):
                question_chain_score -= 15

        # 2. 分析卡片留存动机（是否有高质量卡片）
        has_neuron_card = False
        has_high_score_card = False
        has_purple_green_card = False
        has_modified_card = False

        for card in reference_cards_objs:
            if isinstance(card, dict):
                is_neuron = card.get('is_neuron', False)
                card_type = card.get('type', '')
                score = card.get('score', 0) or 0
                scoreSFT = card.get('scoreSFT', 0) or 0
                combined_score = score * 0.3 + scoreSFT * 0.7
                color = card.get('color', '')
                content = card.get('content', '')
            else:
                is_neuron = getattr(card, 'is_neuron', False)
                card_type = getattr(card, 'type', '') or ''
                score = getattr(card, 'score', 0) or 0
                scoreSFT = getattr(card, 'scoreSFT', 0) or 0
                combined_score = score * 0.3 + scoreSFT * 0.7
                color = getattr(card, 'color', '') or ''
                content = getattr(card, 'content', '') or ''

            if is_neuron and '永久' in card_type:
                has_neuron_card = True
            if combined_score >= 3.5:
                has_high_score_card = True
            if color in ['紫', '绿']:
                has_purple_green_card = True
            if re.search(r'<第\d+次修改内容>', content):
                has_modified_card = True

        # 根据卡片留存动机调整分数
        card_motivation_score = 0
        if has_neuron_card:
            card_motivation_score += 10
        if has_high_score_card:
            card_motivation_score += 10
        if has_purple_green_card:
            card_motivation_score += 5
        if has_modified_card:
            card_motivation_score += 15  # 修正过的卡片说明用户有主动认知投入

        # 综合得分（问题链质量占60%，卡片留存动机占40%）
        total_score = question_chain_score * 0.6 + card_motivation_score * 0.4

        # 根据综合得分确定人机认知比例
        # 人的部分不超过50%
        if total_score >= 70:
            return "5:5"  # 高质量问题链+高质量卡片留存
        elif total_score >= 50:
            return "4:6"  # 较好的问题链或较好的卡片留存
        elif total_score >= 30:
            return "3:7"  # 中等水平
        else:
            return "2:8"  # 较低水平（机械发问、概念性问题为主）

    except Exception as e:
        print(f"[_analyze_human_machine_ratio] 分析人机认知比例失败: {e}")
        import traceback
        traceback.print_exc()
        # 默认返回中等水平
        return "3:7"


def generate_tribal_permanent_card_internal(username, keyword, tribal_md, other_tribal_keywords=None):
    """
    为部落知识关键词生成永久卡（内部调用，用于萃取流程）。
    使用部落知识md内容，以当前关键词为主，注意与其他关键词的DMT递进关系。
    """
    from app_chat.views_tribal_knowledge import _call_llm_with_retry as _tribal_llm
    other_tribal_keywords = other_tribal_keywords or []
    realName = username.split('_')[0] if '_' in username else username
    book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
    if not book_name:
        return None
    try:
        nb = UserNotebook.objects.get(username=realName, bookName=book_name)
        notebook_desc = nb.bookdescription or ''
        scene_obj = scene.objects.get(sid=nb.sid)
        scene_name = scene_obj.sceneDescription
    except Exception:
        scene_name = None
        notebook_desc = ''

    last_sub_scene_num = 1
    last_sub_scene = ''
    if scene_name:
        try:
            excel_path = f'./received_dir/scene_excel/{scene_name}/prompt.xlsx'
            if os.path.exists(excel_path):
                df = pd.read_excel(excel_path, sheet_name='LUI1')
                if df.shape[1] > 1:
                    first_col = df.columns[1]
                    sub_list = df.iloc[:, 1].dropna().tolist()
                    sub_list_order = [first_col] + sub_list
                    last_sub_scene_num = len(sub_list_order)
                    last_sub_scene = sub_list_order[-1] if sub_list_order else ''
        except Exception:
            pass

    scene_summary, _ = get_scene_summary(scene_name or "", None)
    other_kw_note = f"\n## 其他部落关键词（注意DMT递进关系）：\n" + ", ".join(other_tribal_keywords) if other_tribal_keywords else ""

    from app_chat.views import system_prompt_claude
    sys_prompt = system_prompt_claude + """

## 你的角色与任务
你是专家-群组部落知识卡片生成专家。基于部落知识语义层内容，为本子生成原子化、可溯源的深色永久神经元卡片。

## 核心理解
- 部落知识 = 从部分专家中萃取出的可群组性隐性规则、直觉、经验；四色DMT化（四色指红色：专业知识，蓝：工具手段，紫：思维框架，绿：简单深刻自然；DMT为Down<枝>、Middle<干>、Top<根>，各层次递进清晰且有“其内无小，其外无大”的延展张力）的部落知识即运用除法则找到本元；萃取出的应包含「蛙鸣涌现」（提出者自己都可能说不清、复述不出但非常优质且通常难以捕捉到的内容——这是验证萃取得是否精的标准）
- 须能关联打通不同文档、回溯源到原文档页数/段落/知识/概念/定义，产生类似Palantir的「本体论价值」；用四色语境语言、DMT枝-干-根层级表述；强烈避免虚伪浮夸；升维不代表故弄玄虚，如基因本体中"基因"是基础词却有力透纸背的张力，能够统一万千生物的进化和生存规律
- 一定避免复述原文显性知识，萃取出真正有用的新东西

## ⚠️ 重要：全文应该是原文素材中直接没有的内容
用户对原文内容已基本清楚。当前是萃取部落知识提升，不是在复述和复习。整张卡片全文都要说原文素材里直接没有的内容——隐性规则、行为逻辑、蛙鸣涌现、升维洞察、可执行的规则与行为等，而非复述已有的显性知识。"""
    user_prompt = f"""**关键词**：{keyword}
**场景**：{scene_name or '未指定'}
**本子描述**：{notebook_desc}
**场景摘要**：{scene_summary[:300] if scene_summary else '无'}
{other_kw_note}

## 部落知识语义层（核心输入）
{tribal_md[:8000]}{'...(截断)' if len(tribal_md) > 8000 else ''}

## 要求
- 以「{keyword}」为主要部分，体现隐性规则、行为逻辑、蛙鸣涌现，可溯源到文档页数
- 注意与其他部落关键词的DMT枝-干-根递进关系（"其内无小，其外无大"）
- 400-500字，深底色风格，避免复述显性知识，萃取出真正有用的新东西
- 输出JSON：{{"contentTitle":"S{last_sub_scene_num}:{keyword}","content":"...","postIndex":"","sourceReferences":"","humanMachineRatio":"a:b","conclusionReason":"..."}}
- 结构须包含：主体内容 + 支撑文献来源（sourceReferences，1/2/3标号换行）
"""
    content, _ = _tribal_llm(sys_prompt, user_prompt)
    if not content:
        return None
    try:
        m = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        raw = (m.group(1).strip() if m else content).strip()
        card_data = json.loads(raw)
    except Exception:
        card_data = {'contentTitle': f'S{last_sub_scene_num}:{keyword}', 'content': content[:500], 'postIndex': '', 'sourceReferences': '无', 'humanMachineRatio': '3:7', 'conclusionReason': '基于部落知识萃取'}

    four_color_type = ''
    dmt_level = ''
    try:
        nb = UserNotebook.objects.get(username=realName, bookName=book_name)
        kfd = json.loads(nb.keywordFourColorDMT or '{}')
        if keyword in kfd:
            four_color_type = kfd[keyword].get('four_color_type', '')
            dmt_level = kfd[keyword].get('dmt_level', '')
    except Exception:
        pass

    full_content = card_data.get('content', '')
    content_body = card_data.get('content', '')
    source_refs = card_data.get('sourceReferences', '无')
    # human_ratio = card_data.get('humanMachineRatio', '3:7')
    conclusion_reason = card_data.get('conclusionReason', '基于部落知识萃取')
    full_content = f"{content_body}\n\n---\n\n支撑文献来源：\n{source_refs}\n\n为什么可以得出这样的结论：{conclusion_reason}"
    post_index_value = card_data.get('postIndex', '')
    content_title = card_data.get('contentTitle', f'S{last_sub_scene_num}:{keyword}')
    if not content_title.startswith(f'S{last_sub_scene_num}:'):
        content_title = f'S{last_sub_scene_num}:{keyword}'

    # 并发打分和红蓝评测（与 generate_permanent_card 一致）
    async def _score_and_eval():
        async def _get_score():
            try:
                s, c, r = red_bule_rate.get_rate(username, full_content)
                return {'error_num': 0, 'score': s, 'color': c, 'reason': r}
            except Exception:
                return {'error_num': 1, 'score': 4.5, 'color': '紫', 'reason': '部落知识卡片'}
        async def _get_evalSFT():
            try:
                text = full_content.replace("\n", "\\n")
                server_url = get_small_model_server_url(username)
                cmd = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","text":"{text}"}}\' {server_url}/invoke_rate'
                result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
                data_str = result.stdout.strip()
                if data_str.startswith('"') and data_str.endswith('"'):
                    data_str = data_str[1:-1]
                data_str = data_str.replace('\\"', '"').replace('\\\\', '\\')
                robj = json.loads(data_str)
                dec = robj.get('result', '')
                if dec and dec != "fail":
                    scoreSFT = float(extract_number_SFT(dec)) if extract_number_SFT(dec) is not None else 4.5
                    colorSFT = extract_color_SFT(dec) or "紫"
                    reasonSFT = extract_reason_SFT(dec) or "部落知识卡片"
                    if scoreSFT >= 1.0 and colorSFT != "紫":
                        colorSFT = "紫"
                    return {'error_num': 0, 'scoreSFT': scoreSFT, 'colorSFT': colorSFT, 'reasonSFT': reasonSFT}
                return {'error_num': 1, 'scoreSFT': 4.5, 'colorSFT': '紫', 'reasonSFT': '部落知识卡片'}
            except Exception:
                return {'error_num': 1, 'scoreSFT': 4.5, 'colorSFT': '紫', 'reasonSFT': '部落知识卡片'}
        sr, er = await asyncio.gather(_get_score(), _get_evalSFT())
        return (sr.get('score', 4.5), sr.get('color', '紫'), sr.get('reason', '部落知识卡片'),
                er.get('scoreSFT', 4.5), er.get('colorSFT', '紫'), er.get('reasonSFT', '部落知识卡片'))

    try:
        loop = asyncio.new_event_loop()
        score, color, reason, scoreSFT, colorSFT, reasonSFT = loop.run_until_complete(_score_and_eval())
        loop.close()
    except Exception:
        score, color, reason, scoreSFT, colorSFT, reasonSFT = 4.5, '紫', '部落知识卡片', 4.5, '紫', '部落知识卡片'

    try:
        new_card = Card.objects.create(
            username=username,
            model_id="1126",
            status="0",
            content=full_content,
            title="关键词神经元永久卡",
            score=score,
            scoreSFT=scoreSFT,
            color=color,
            colorSFT=colorSFT,
            reason=reason,
            reasonSFT=reasonSFT,
            keyWords=keyword,
            contentTitle=content_title,
            type="永久",
            postIndex=post_index_value,
            four_color_type=four_color_type,
            dmt_level=dmt_level,
            is_neuron=True,
            is_analyzed_by_new_standard=True,
        )
        return new_card.cid
    except Exception as e:
        print(f"[generate_tribal_permanent_card_internal] 创建卡片失败: {e}")
        return None


@csrf_exempt
def generate_permanent_card(request):
    """
    🔥 生成永久卡片API
    根据关键词和相关卡片，生成原子化&原创化&可复用化的永久卡片
    """
    try:
        data = json.loads(request.body)
        keyword = data.get('keyword', '').strip()
        cards = data.get('cards', [])  # 最多5张卡片
        qa_cards = data.get('qa_cards', [])  # QA问答卡（按datetime排序的问题链）
        username = data.get('username', '')
        scene_name = data.get('scene_name', '')
        sub_scene_name = data.get('sub_scene_name', '')
        is_group_notebook = data.get('is_group_notebook', False)
        origin_real_name = data.get('origin_real_name', '')

        # if not keyword or not cards or not username:
        # 参数检查：keyword 和 username 必须存在，cards 可以为空数组（允许没有关联卡片的情况）
        if not keyword or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        # 1. 获取场景信息和本子描述
        scene_summary_info = None
        notebook_desc = ""
        if scene_name:
            scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, sub_scene_name)
            notebook_desc = get_notebook_description(username, scene_name)
            final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
        else:
            final_scene_summary = None

        # 2. 获取最后一个子场景（一般都含"神经元卡"几个字）
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
        if not book_name and scene_name:
            try:
                scene_obj = scene.objects.get(sceneDescription=scene_name)
                notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                if notebook:
                    book_name = notebook.bookName
            except:
                pass

        # 2.1 获取最后一个子场景名称和编号（参考card_upload的逻辑）
        # 2.1 获取最后一个子场景名称和编号（参考card_upload的逻辑，直接从excel读取）
        last_sub_scene = sub_scene_name or ""
        last_sub_scene_num = 0  # 最后一个子场景的编号（从1开始）
        if scene_name:
            try:
                # 从excel文件获取子场景列表，确定最后一个子场景的编号（参考card_upload的逻辑）
                scene_dir_path = './received_dir/scene_excel/' + scene_name
                prompt_excel_path = os.path.join(scene_dir_path, 'prompt.xlsx')
                if os.path.exists(prompt_excel_path):
                    excel_data = pd.read_excel(prompt_excel_path, sheet_name='LUI1')
                    sub_scene_col = 1
                    if excel_data.shape[1] > sub_scene_col:
                        first_subscene_col_name = excel_data.columns[sub_scene_col]
                        subscene_name_list = excel_data.iloc[:, sub_scene_col].dropna().tolist()
                        subscene_name_list_order = [first_subscene_col_name] + subscene_name_list
                        # 最后一个子场景的编号（从1开始，所以是列表长度）
                        last_sub_scene_num = len(subscene_name_list_order)
                        # 获取最后一个子场景的名称
                        if subscene_name_list_order:
                            last_sub_scene = subscene_name_list_order[-1]
                        print(f"[generate_permanent_card] 最后一个子场景编号: {last_sub_scene_num}, 名称: {last_sub_scene}")
            except Exception as e:
                print(f"[generate_permanent_card] 从excel获取子场景信息失败: {e}")

        # 3. 构建Prompt
        # 3.1 构建QA问答卡的问题链信息（按datetime排序）
        qa_questions_chain = ""
        if qa_cards:
            if is_group_notebook:
                # 🔥 组本：按作者分组显示问题链
                qa_questions_chain = "\n## QA问答卡问题链（按作者和时间顺序）：\n"
                # 按作者分组
                qa_by_writer = {}
                for qa_card in qa_cards:
                    writer = qa_card.get('writer', '')
                    if writer:
                        writer_name = writer.split('_')[0] if '_' in writer else writer
                    else:
                        writer_name = '未知作者'

                    if writer_name not in qa_by_writer:
                        qa_by_writer[writer_name] = []

                    # 提取问题
                    question = ""
                    if qa_card.get('history'):
                        history = qa_card['history']
                        if isinstance(history, list) and len(history) > 0:
                            first_msg = history[0]
                            if isinstance(first_msg, dict):
                                question = first_msg.get('content', '')
                    elif qa_card.get('content'):
                        content = qa_card['content']
                        match = re.search(r'提问[：:]\s*([^\n\r]+)', content)
                        if match:
                            question = match.group(1).strip()

                    if question:
                        datetime_str = qa_card.get('datetime', '')
                        # 提取子场景（从contentTitle中提取S1-Sn）
                        sub_scene = ""
                        content_title = qa_card.get('contentTitle', '')
                        if content_title:
                            match = re.search(r'^(S\d+)', content_title)
                            if match:
                                sub_scene = match.group(1)
                        qa_by_writer[writer_name].append({
                            'datetime': datetime_str,
                            'question': question,
                            'sub_scene': sub_scene
                        })

                # 按作者分组输出，每个作者内按时间排序
                for writer_name, qa_list in sorted(qa_by_writer.items()):
                    qa_list.sort(key=lambda x: x['datetime'] or '')
                    qa_questions_chain += f"\n### 作者：{writer_name}\n"
                    for idx, qa in enumerate(qa_list, 1):
                        qa_questions_chain += f"  {idx}. [{qa['sub_scene']}] [{qa['datetime']}] {qa['question']}\n"
            else:
                # 个人本子：保持原逻辑
                qa_questions_chain = "\n## QA问答卡问题链（按时间顺序）：\n"
                for idx, qa_card in enumerate(qa_cards):
                    # 提取问题
                    question = ""
                    if qa_card.get('history'):
                        history = qa_card['history']
                        if isinstance(history, list) and len(history) > 0:
                            first_msg = history[0]
                            if isinstance(first_msg, dict):
                                question = first_msg.get('content', '')
                    elif qa_card.get('content'):
                        content = qa_card['content']
                        match = re.search(r'提问[：:]\s*([^\n\r]+)', content)
                        if match:
                            question = match.group(1).strip()

                    if question:
                        datetime_str = qa_card.get('datetime', '')
                        qa_questions_chain += f"{idx + 1}. [{datetime_str}] {question}\n"

        # 3.2 构建参考卡片内容
        reference_cards_info = "\n## 参考卡片内容：\n"
        card_cids = []  # 收集所有参考卡片的cid，用于postIndex
        all_selected_docs = set()  # 收集所有参考卡片的selected_docs，用于sourceReferences

        if not cards:
            reference_cards_info += "（无关联卡片，请基于关键词本身和问题链生成永久卡片）\n"

        for idx, card in enumerate(cards):
            card_cid = card.get('cid', '')
            if card_cid:
                card_cids.append(str(card_cid))

            # 收集selected_docs（优先 selected_docs，其次从 history 中提取）
            card_selected_docs = card.get('selected_docs', '')
            docs_list = []

            # 1. 优先从 selected_docs 获取
            if card_selected_docs:
                try:
                    if isinstance(card_selected_docs, str):
                        docs_list = json.loads(card_selected_docs)
                    else:
                        docs_list = card_selected_docs
                    if isinstance(docs_list, list) and len(docs_list) > 0:
                        all_selected_docs.update(docs_list)
                except:
                    docs_list = []

            # 2. 如果 selected_docs 为空，从 history 中提取
            if not docs_list:
                card_history = card.get('history')
                if card_history:
                    try:
                        # 如果 history 是字符串，先解析
                        if isinstance(card_history, str):
                            history = json.loads(card_history)
                        else:
                            history = card_history

                        # history 可能是 { data: [...] } 结构，或者直接是 data 数组
                        history_data = None
                        if history and isinstance(history, dict) and history.get('data') and isinstance(
                                history['data'], list):
                            history_data = history['data']
                        elif isinstance(history, list):
                            history_data = history

                        # 从所有轮次对话中提取文件列表的并集
                        if history_data and isinstance(history_data, list):
                            file_set = set()
                            for data_item in history_data:
                                if isinstance(data_item, dict) and data_item.get('filelist'):
                                    filelist = data_item['filelist']
                                    if isinstance(filelist, list):
                                        for file_name in filelist:
                                            if file_name:
                                                file_set.add(file_name)
                            if file_set:
                                docs_list = list(file_set)
                                all_selected_docs.update(docs_list)
                    except Exception as e:
                        print(f"[generate_permanent_card] 从history提取文件列表失败: {e}")
                        pass

            card_content = card.get('content', '')
            card_title = card.get('title', '')
            card_score = card.get('score', 0)
            card_scoreSFT = card.get('scoreSFT', 0)
            combined_score = card_score * 0.3 + card_scoreSFT * 0.7

            # 🔥 组本：显示作者信息
            writer_info = ""
            if is_group_notebook:
                writer = card.get('writer', '')
                if writer:
                    writer_name = writer.split('_')[0] if '_' in writer else writer
                    writer_info = f"作者：{writer_name}\n"

            reference_cards_info += f"\n--- 参考卡片 {idx + 1} (CID: {card_cid}) ---\n"
            if writer_info:
                reference_cards_info += writer_info
            reference_cards_info += f"标题：{card_title}\n"
            reference_cards_info += f"综合得分：{combined_score:.2f} (score={card_score}×0.3 + scoreSFT={card_scoreSFT}×0.7)\n"
            reference_cards_info += f"内容：{card_content}\n"
            # 显示勾选文档（使用上面提取的docs_list）
            if docs_list:
                reference_cards_info += f"勾选文档：{', '.join(docs_list)}\n"
            # if card_selected_docs:
            #     try:
            #         if isinstance(card_selected_docs, str):
            #             docs_list = json.loads(card_selected_docs)
            #         else:
            #             docs_list = card_selected_docs
            #         if isinstance(docs_list, list) and len(docs_list) > 0:
            #             reference_cards_info += f"勾选文档：{', '.join(docs_list)}\n"
            #     except:
            #         pass

        # 3.2.5 🔥 若存在部落知识md，追加进输入
        tribal_md_section = ""
        other_tribal_kws = []
        try:
            from app_chat.views_tribal_knowledge import _read_tribal_md, _get_tribal_md_path
            md_content = _read_tribal_md(username)
            if md_content:
                tribal_md_section = f"""

                ## 部落知识语义层（若适用，优先体现隐性规则/蛙鸣涌现/可溯源）
                **含义**：由场景子场景下本子内多文档萃取的升维语义层与部落知识，包含隐性规则、直觉、经验（蛙鸣涌现）、行为逻辑，能关联打通不同文档、回溯源到原文档页数/段落；用四色语境语言与DMT枝-干-根层级表述；用于统一不同文档数据在相同或相关语境下的语义，去除歧义和盲区。

                **内容**：
                {md_content[:6000]}{'...(截断)' if len(md_content) > 6000 else ''}
                """
                try:
                    nb = UserNotebook.objects.get(username=realName, bookName=book_name)
                    kfd = json.loads(nb.keywordFourColorDMT or '{}')
                    other_tribal_kws = [k for k, v in kfd.items() if
                                        isinstance(v, dict) and v.get('is_tribal') and k != keyword]
                except Exception:
                    pass
        except Exception:
            pass

        other_tribal_note = f"\n注意与其他部落关键词的DMT递进关系：{', '.join(other_tribal_kws[:10])}" if other_tribal_kws else ""
        tribal_content_note = """- **若有部落知识语义层输入**：部落知识=隐性规则、直觉经验、行为逻辑和蛙鸣涌现；四色DMT化的部落知识即运用除法则找到本元；萃取出的应包含「蛙鸣涌现」（提出者自己都可能说不清、复述不出的内容——验证萃取得是否精）。须能关联打通不同文档、回溯源到原文档知识/概念/定义；用四色语境语言、DMT枝-干-根层级表述；强烈避免虚伪浮夸；**全文应该都是原文素材中直接找不到的内容**，用户对原文已基本清楚，是萃取拔升不是复述复习；一定避免复述原文显性知识，萃取出真正有用的新东西。
        """ if tribal_md_section else ""

        # 3.3 构建完整的user_prompt
        notebook_type_note = ""
        if is_group_notebook:
            # notebook_type_note = "\n**注意：这是群组本子，参考卡片和问题链中包含不同作者的内容。你需要分别分析不同作者的认知状态和问题链，并在生成内容时综合考虑不同作者的观点和认知推进情况。**\n"
            notebook_type_note = f"""
** 组本特殊要求**：
- 这是群组本子，参考卡片和问题链中包含不同作者的内容
- 你需要**挨个分析每个参与贡献卡片的作者**（问题链中已按作者分组显示）：
  - 分别理解他们各自的主要方向和问题链关注重点
  - 分析各自的认知状态（盲区/填充/迁移/增强）及应给的建议
  - 在正文中要综合体现所有作者的观点和认知推进，但需要体现不同作者的差异化认知
  - 在**人机认知比例（humanMachineRatio）和结论理由（conclusionReason）中也要分别说明每个作者的情况**
- 但**正文内容依然保持300-500字**，需要综合所有作者的观点，体现多作者认知的融合与涌现，**严禁空话套话！**
"""

        user_prompt = f"""你需要基于关键词"{keyword}"（生成必须围绕此关键词展开）和以下参考卡片，生成一张原子化&原创化&可复用化的永久卡片（类似卢曼卡片盒笔记法中的永久卡片）。
{notebook_type_note}
## 场景上下文
- 场景名：{scene_name}
- 子场景：{last_sub_scene}
- 本子描述：{notebook_desc[:300] if notebook_desc else '未提供'}
- 场景摘要：{final_scene_summary[:500] if final_scene_summary else '未提供'}

{qa_questions_chain if qa_questions_chain else ''}

{reference_cards_info}
{tribal_md_section}
{other_tribal_note}

## 生成要求

### 1. 卡片基本信息
- **contentTitle**：S{last_sub_scene_num}:{keyword}（S{last_sub_scene_num}是最后一个子场景编号，子场景名称：{last_sub_scene}）
- **关键词**：{keyword}

### 2. 内容要求（300-500字，不可更多）
{tribal_content_note}
- **开头要求（至少100字）**：开头至少100字要围绕**深入理解和具体解释此关键词本身的原意**，说明关键词的核心含义、本质特征、适用范围等
- **中间要求（50-100字）**：中间50-100字要说明**此关键词如何与其他相关概念/主题等产生关联涌现**，体现概念间的联系、融合、新内涵的产生等
- **格式要求**：开头&中间部分一体，和下面的后续篇幅之间要用三个连字符"---"分隔
- **后续篇幅**：按如下的内容要求（原子化、原创化、可复用化、聚焦主体、具体化等）
- **原子化**：内容应该是独立完整的概念单元，不依赖其他卡片即可理解
- **原创化**：必须交叉创造、融合、涌现明显，是多张参考卡片的交叉混合结果，不能简单复制粘贴
- **可复用化**：内容应该可以在不同场景下复用，具有通用性
- **聚焦主体**：必须聚焦此场景此本子的主体目标，不可偏离
- **具体化**：**严禁空话套话！** 必须具体、有真正认知上的行动指向价值
  - 如果提到"用户提问"、"追问"等，必须具体引用问题链中的实际提问内容，不能泛泛而谈
  - 如果提到"认知推进"、"振荡"等，必须基于问题链中的具体问题进行分析，指出具体的问题内容和时间线
  - 避免"使用户能针对文本提出针对性追问"这样的空话，要写"用户提出了'xxx'、'yyy'等问题，体现了从...到...的认知推进"

### 3. 去QA化要求
- 去除QA问答的形式，提取核心观点和概念
- 对于QA问答卡，要特别关注Q（问题）部分，因为Q能最大程度体现使用者的认知状态
- **根据问题链（按datetime排序）具体分析**：
  - 必须引用问题链中的具体问题内容（至少引用2-3个关键问题）
  {"  - **如果是群组本子，问题链已按作者分组。你需要**分别分析每个作者（要明确指出！）**，分别理解他们各自的主要方向和问题链关注重点，了解不同作者的认知推进情况、问题演进模式、可能的振荡或阻碍，然后综合考虑多作者的观点来生成卡片内容。**" if is_group_notebook else ""}
  - 分析使用者的认知推进情况：从S1到Sn，问题是如何演进的？具体问题是什么？
  - 识别是否有阻碍/振荡：如果有，具体是哪些问题体现了振荡？问题内容是什么？
  - 分析认知状态：基于具体问题，判断使用者情况是盲区/填充/迁移/增强（不知道自己不知道/知道自己不知道/不知道自己知道/知道自己知道），特别要关注盲区/内耗区/困惑点，找到最近发展区突破点
- 加强人机协同的原创性与主体性，突出使用者本身人参与的部分

### 4. 后置索引（postIndex）要求
- **必须是参考卡片的CID列表**（用逗号分隔，例如："123,456,789"）
- 这些CID是生成此永久卡片时用到的参考卡片的标识符
- 不要写其他内容，只写CID数字，用逗号分隔

### 5. 支撑文献来源（sourceReferences）要求
- **必须是参考文档列表**（不是参考卡片！）
- **说明**：系统会自动从参考卡片中提取文档列表并解析页数，你只需要在JSON中返回格式化的字符串即可（如果系统未提供，可返回"无"）
- **格式要求**（如果系统提供了文档列表）：必须使用1/2/3标号，每个文档换行，格式为"1. 文档名（第X页）"或"1. 文档名（第X-Y页）"
- **示例格式**：
  1. 文档1.pdf（第10页）
  2. 文档2.txt（第15-20页）
  3. 文档3.pdf（第5页）

### 6. 结尾要求
{"- **如果是组本**：必须分别说明每个参与贡献卡片的作者的人机认知比例和理由（要具体指出作者）" if is_group_notebook else "- 必须显式标识人/机认知比例（例如：人机认知比例 3:7 或 4:6 等等）"}
{"- **如果是个人本子**：必须显式标识人/机认知比例（例如：人机认知比例 3:7 或 4:6 等等）" if not is_group_notebook else ""}
- **人机认知比例判断标准**：
  - 本子里的卡片大多都是问答卡，人的认知进行引导和指向的部分应该**不多于50%**
  - **人参与认知比例较高**（4:6或5:5）：问题链逐步引导推进、贴合场景子场景、指向本子的目标（从本子中文名可以看出）质量较高
  - **人参与认知比例较低**（2:8或3:7）：问题链仅为机械的发问、偏学究的知识性概念性问题占绝大多数，且缺少理解性、原创性、思维性的问题
  - **居中情况**（3:7或4:6）：灵活判别，综合考虑问题链的质量、引导性、原创性等因素
- 必须用一段话（50-100字，不可少于50字，不可超过100字）精准详细地总结：为什么可以得出这样的人机认知比例结论{"（组本需要为每个作者分别总结，所有加起来不可超过150字！）" if is_group_notebook else ""}

## 输出格式

请严格按照以下JSON格式输出：

```json
{{
    "contentTitle": "S{last_sub_scene_num}:{keyword}",
    "content": "生成的卡片内容（300-500字，必须围绕关键词展开，开头至少100字深入解释关键词原意，中间50-100字说明与其他概念的关联涌现，开头&中间部分一体，与后续部分之间用---分隔，后续篇幅必须具体引用问题链中的具体问题，体现使用者本身的认知推进情况，有感同身受的价值和具体认知帮助，记得住说得出，原子原创可复用，以及其他已经提及的要求都要注意，避免空话套话）",
    "postIndex": "{','.join(card_cids) if card_cids else ''}",
    "sourceReferences": "支撑文献来源，格式为1/2/3标号换行（最多3个，至少1个），每个文档需包含页数",
    "humanMachineRatio": "人机认知比例，例如：3:7 或 4:6 等等（人的部分不超过50%）（注意如果是组本要分别说各个作者）",
    "conclusionReason": "为什么可以得出这样的人机认知比例结论（50-100字，不可少于50字，不可超过100字）（如果是组本同上，但总共150字以内）"
}}
```

**postIndex示例**：如果参考卡片CID是123, 456, 789，则postIndex应为："123,456,789"
**sourceReferences示例**：如果参考卡片的勾选文档有"文档1.pdf, 文档2.txt"，则sourceReferences应为："文档1.pdf, 文档2.txt"

**重要提醒**：
1. 内容必须是多张参考卡片的交叉创造、融合、涌现的结果
2. 必须去QA化，提取核心观点
3. 必须加强人机协同的原创性与主体性，一定要考虑多张问答卡形成的Q问题链情况（真实引用，不可编造），这体现“人”的主体认知状态
4. 内容字数严格控制在300-500字
5. 结论理由必须30字以内
6. **生成的内容必须围绕关键词"{keyword}"展开**，这是关键词神经元永久卡的核心要求
7. **在描述中不要直接使用"R"、"B"、"P"、"G"、"D"、"M"、"T"等字母**，而要使用完整的描述，如"红色专业业务"、"蓝色工具手段"、"紫色思维框架"、"绿色简单深刻"、"枝"、"干"、"根"
"""

        # 4. 调用LLM生成卡片内容（默认claude-sonnet-5，失败则降级4.5 → 4-sonnet → 3.7）
        model_name = None
        model_id = None
        response_content = None
        last_error = None

        # 构建system_prompt
        system_prompt = "你是专业的知识卡片生成专家，擅长基于关键词和相关卡片内容，生成原子化、原创化、可复用化的永久卡片，围绕此关键词展开，其中考虑使用者所提问题链的认知状态。"

        model_priority = [
            "claude-sonnet-5",
            "claude-sonnet-4.5",
            "claude-4-sonnet",
            "claude-3.7",
        ]
        from openai import OpenAI
        for candidate in model_priority:
            try:
                model_name = candidate
                model_config = config_manager.get_model_config(model_name)
                model_id = model_config.get_model_id()
                cur_config = model_config.get_config()
                api_key = cur_config.get("openai_api_key")
                base_url = cur_config.get("openai_api_base")
                full_model_name = model_config.get_full_name()
                hyper_para = model_config.get_hyper_para()

                client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    default_headers={"x-foo": "true"}
                )

                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )
                response_content = response.choices[0].message.content
                print(f"[generate_permanent_card] 使用{model_name}成功")
                break
            except Exception as e:
                last_error = e
                print(f"[generate_permanent_card] 使用{model_name}失败: {e}")
                continue

        if not response_content:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'error_num': 1,
                'msg': f'LLM调用失败: {str(last_error)}'
            })

        if not response_content:
            return JsonResponse({
                'error_num': 1,
                'msg': 'LLM未返回内容'
            })

        # 5. 解析LLM返回的JSON（使用健壮的解析函数）
        # 🔥 定义转义JSON字符串中未转义双引号的函数
        def escape_quotes_in_json_string(json_string):
            """
            转义JSON字符串值中的未转义英文双引号

            策略：逐字符解析，识别字符串值区域
            - 在字符串值中的未转义双引号需要转义为 \"
            - 字符串边界（字段名、字段值的开始/结束）的双引号保持不变
            """
            result = []
            i = 0
            in_string = False
            escape_next = False

            while i < len(json_string):
                char = json_string[i]

                if escape_next:
                    # 当前字符是转义字符后的字符，直接添加
                    result.append(char)
                    escape_next = False
                    i += 1
                    continue

                if char == '\\':
                    # 转义字符，下一个字符会被转义
                    result.append(char)
                    escape_next = True
                    i += 1
                    continue

                if char == '"':
                    if not in_string:
                        # 字符串开始（字段名或字段值的开始引号）
                        in_string = True
                        result.append(char)
                    else:
                        # 在字符串中遇到引号
                        # 需要判断：这是字符串结束，还是字符串值中的未转义双引号

                        # 向前查找，跳过空白字符，看下一个非空白字符
                        j = i + 1
                        while j < len(json_string) and json_string[j] in ' \t\n\r':
                            j += 1

                        if j >= len(json_string):
                            # 字符串结束（最后一个字符）
                            in_string = False
                            result.append(char)
                        else:
                            next_char = json_string[j]
                            # 如果下一个非空白字符是:、,、}、]，说明这是字符串结束
                            if next_char in [':', ',', '}', ']']:
                                in_string = False
                                result.append(char)
                            else:
                                # 否则，这是字符串值中的未转义双引号，需要转义
                                result.append('\\"')
                    i += 1
                    continue

                # 其他字符直接添加
                result.append(char)
                i += 1

            return ''.join(result)

        # 定义解析JSON的辅助函数
        def parse_json_response(response_content):
            """解析LLM返回的JSON，返回(card_data, success)"""
            try:
                # 尝试提取JSON部分（使用更健壮的方式处理换行符）
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # 尝试查找第一个 { 到最后一个 } 之间的内容
                    first_brace = response_content.find('{')
                    last_brace = response_content.rfind('}')
                    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                        json_str = response_content[first_brace:last_brace + 1]
                    else:
                        json_str = response_content

                # 🔥 修复所有字符串字段中的未转义英文双引号
                json_str = escape_quotes_in_json_string(json_str)

                # 解析JSON（允许处理换行符等）
                card_data = json.loads(json_str)
                return card_data, True
            except Exception as e:
                print(f"[generate_permanent_card] JSON解析失败: {e}")
                # 尝试更宽松的解析方式：去除可能的markdown标记后重试
                try:
                    cleaned_content = response_content
                    # 移除```json和```标记
                    cleaned_content = re.sub(r'```json\s*', '', cleaned_content)
                    cleaned_content = re.sub(r'```\s*$', '', cleaned_content, flags=re.MULTILINE)
                    cleaned_content = cleaned_content.strip()
                    # 再次尝试解析
                    first_brace = cleaned_content.find('{')
                    last_brace = cleaned_content.rfind('}')
                    if first_brace != -1 and last_brace != -1:
                        json_str = cleaned_content[first_brace:last_brace + 1]

                        # 🔥 修复未转义的英文双引号
                        json_str = escape_quotes_in_json_string(json_str)

                        # 🔥 尝试修复不完整的JSON
                        # 1. 检查是否有未闭合的括号
                        brace_count = json_str.count('{') - json_str.count('}')
                        if brace_count > 0:
                            # 尝试补全缺失的闭合括号
                            json_str += '}' * brace_count

                        # 2. 尝试修复被截断的字符串（如果最后一个字段的字符串没有闭合引号）
                        # 查找最后一个未闭合的字符串引号
                        last_quote_pos = json_str.rfind('"')
                        if last_quote_pos > 0:
                            # 检查从最后一个引号到末尾是否有未闭合的字符串
                            after_last_quote = json_str[last_quote_pos + 1:]
                            # 如果末尾不是引号、逗号、}或]，可能是字符串被截断了
                            if after_last_quote and not after_last_quote.rstrip().endswith(('"', ',', '}', ']')):
                                # 尝试补全字符串和JSON结构
                                # 找到最后一个字段名
                                last_colon = json_str.rfind(':')
                                if last_colon > 0:
                                    # 检查是否在字符串值中
                                    before_colon = json_str[:last_colon]
                                    last_field_quote = before_colon.rfind('"')
                                    if last_field_quote > 0:
                                        # 可能是字符串值被截断了，尝试补全
                                        field_name = json_str[last_field_quote + 1:last_colon].strip().strip('"')
                                        # 如果字段名是已知的，尝试补全
                                        known_fields = ['contentTitle', 'content', 'postIndex', 'sourceReferences',
                                                        'humanMachineRatio', 'conclusionReason']
                                        if field_name in known_fields:
                                            # 补全字符串引号和闭合括号
                                            json_str = json_str.rstrip() + '"' + '}' * brace_count

                        try:
                            card_data = json.loads(json_str)
                            print(f"[generate_permanent_card] 使用宽松解析成功")
                            return card_data, True
                        except:
                            # 如果还是失败，尝试更激进的方法：只提取已知字段
                            card_data = {}
                            # 尝试提取各个字段（正确处理转义的引号）
                            for field in ['contentTitle', 'content', 'postIndex', 'sourceReferences',
                                          'humanMachineRatio', 'conclusionReason']:
                                # 🔥 使用能正确处理转义引号的正则表达式
                                # 匹配：字段名后跟冒号，然后匹配引号内的内容（包括转义的引号和反斜杠）
                                pattern = rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"'
                                match = re.search(pattern, json_str, re.DOTALL)
                                if match:
                                    # 处理转义字符：将\"还原为"，将\\还原为\
                                    value = match.group(1)
                                    value = value.replace('\\"', '"').replace('\\\\', '\\')
                                    card_data[field] = value
                                else:
                                    # 尝试匹配可能被截断的字符串（到下一个字段或JSON结构结束）
                                    # 找到字段位置
                                    field_start = json_str.find(f'"{field}"')
                                    if field_start != -1:
                                        # 找到冒号后的第一个引号
                                        colon_pos = json_str.find(':', field_start)
                                        if colon_pos != -1:
                                            quote_start = json_str.find('"', colon_pos)
                                            if quote_start != -1:
                                                quote_start += 1  # 跳过开始的引号
                                                # 找到下一个字段或结构结束的位置
                                                next_field_pos = len(json_str)
                                                for other_field in ['contentTitle', 'content', 'postIndex',
                                                                    'sourceReferences',
                                                                    'humanMachineRatio', 'conclusionReason']:
                                                    if other_field != field:
                                                        other_pos = json_str.find(f'"{other_field}"', quote_start)
                                                        if other_pos != -1 and other_pos < next_field_pos:
                                                            next_field_pos = other_pos

                                                # 从quote_start到next_field_pos提取值（不包括结尾的引号）
                                                # 需要找到最后一个非转义的引号
                                                quote_end = quote_start
                                                i = quote_start
                                                while i < next_field_pos:
                                                    if json_str[i] == '"':
                                                        # 检查是否是转义的引号（前面有奇数个反斜杠）
                                                        backslash_count = 0
                                                        j = i - 1
                                                        while j >= quote_start and json_str[j] == '\\':
                                                            backslash_count += 1
                                                            j -= 1
                                                        if backslash_count % 2 == 0:
                                                            # 非转义的引号，这是字符串的结束
                                                            quote_end = i
                                                            break
                                                    i += 1

                                                if quote_end > quote_start:
                                                    value = json_str[quote_start:quote_end]
                                                    # 处理转义字符
                                                    value = value.replace('\\"', '"').replace('\\\\', '\\')
                                                    card_data[field] = value
                                                elif quote_end == quote_start:
                                                    # 没有找到结束引号，可能被截断了，取到下一个字段之前
                                                    value = json_str[quote_start:next_field_pos].rstrip().rstrip('"')
                                                    # 处理转义字符
                                                    value = value.replace('\\"', '"').replace('\\\\', '\\')
                                                    if value:
                                                        card_data[field] = value

                            if card_data:
                                print(f"[generate_permanent_card] 使用字段提取解析成功")
                                return card_data, True
                            raise e
                    else:
                        raise e
                except Exception as e2:
                    print(f"[generate_permanent_card] 宽松解析也失败: {e2}")
                    print(f"[generate_permanent_card] 响应内容: {response_content[:1000]}")  # 打印前1000字符用于调试
                    return None, False

        card_data, success = parse_json_response(response_content)
        if not success or not card_data:
            return JsonResponse({
                'error_num': 1,
                'msg': f'解析LLM响应失败'
            })

        # 6. 获取关键词的四色DMT属性（从关键词节点获取，而不是从卡片中提取）
        # 🔥 优先使用关键词节点的四色属性，如果没有则从参考卡片中提取
        four_color_type = ""
        dmt_level = ""

        # 尝试从UserNotebook的keywordFourColorDMT字段获取关键词的四色DMT属性
        try:
            realName = username.split('_')[0] if '_' in username else username
            book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
            if not book_name and scene_name:
                try:
                    scene_obj = scene.objects.get(sceneDescription=scene_name)
                    notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                    if notebook:
                        book_name = notebook.bookName
                except:
                    pass

            if book_name:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                if notebook.keywordFourColorDMT:
                    keyword_data = json.loads(notebook.keywordFourColorDMT)
                    if keyword in keyword_data:
                        keyword_attr = keyword_data[keyword]
                        four_color_type = keyword_attr.get('four_color_type', '')
                        dmt_level = keyword_attr.get('dmt_level', '')
                        print(f"[generate_permanent_card] 从关键词节点获取四色DMT属性: {keyword} -> {four_color_type}/{dmt_level}")
        except Exception as e:
            print(f"[generate_permanent_card] 从关键词节点获取四色DMT属性失败: {e}")

        # 如果关键词节点没有四色DMT属性，则从参考卡片中提取（作为备选）
        if not four_color_type and cards:
            # 找到综合得分最高的卡片
            top_card = max(cards, key=lambda c: (c.get('score', 0) * 0.3 + c.get('scoreSFT', 0) * 0.7))
            four_color_type = top_card.get('four_color_type', '')
            dmt_level = top_card.get('dmt_level', '')
            print(f"[generate_permanent_card] 从参考卡片获取四色DMT属性: {four_color_type}/{dmt_level}")

        # 7. 处理postIndex（确保是cid列表，用逗号分隔）
        post_index_value = card_data.get('postIndex', '')
        if not post_index_value and card_cids:
            # 如果LLM没有生成postIndex，使用我们收集的cid列表
            post_index_value = ','.join(card_cids)
        elif post_index_value:
            # 确保postIndex是字符串格式（cid列表，逗号分隔）
            try:
                # 如果是JSON数组，转换为逗号分隔的字符串
                parsed = json.loads(post_index_value)
                if isinstance(parsed, list):
                    post_index_value = ','.join(str(item) for item in parsed)
            except:
                # 已经是字符串格式，直接使用
                pass

        # 8. 构建完整的卡片内容（先构建，用于评分）
        # 8. 获取支撑文献来源（新旧策略融合）
        # 8.1 旧策略：从参考卡片的selected_docs中提取文档列表
        doc_names_from_cards = []
        if all_selected_docs:
            doc_names_from_cards = list(all_selected_docs)
            print(f"[generate_permanent_card] 旧策略找到{len(doc_names_from_cards)}个文档: {doc_names_from_cards}")

        # 8.2 如果旧策略为空，使用新策略：根据关键词从pre_summary查找文档
        final_doc_names = []
        doc_page_ranges = None  # 如果在新策略测试时已经解析过，保存结果避免重复解析
        if doc_names_from_cards:
            # 如果超过3个文档，先用新策略查找，如果找不到页码则回退到均匀抽取
            if len(doc_names_from_cards) > 3:
                # 辅助函数：均匀抽取3个文档（靠前、靠中、靠后各一个）
                def uniformly_sample_docs(doc_list):
                    front_idx = len(doc_list) // 4  # 约1/4位置（靠前）
                    middle_idx = len(doc_list) // 2  # 中间位置
                    back_idx = len(doc_list) - 1 - len(doc_list) // 4  # 约3/4位置（靠后）
                    indices = sorted(list(set([front_idx, middle_idx, back_idx])))
                    if len(indices) == 2:
                        if 0 not in indices:
                            indices.insert(0, 0)
                        elif len(doc_list) - 1 not in indices:
                            indices.append(len(doc_list) - 1)
                    return [doc_list[i] for i in indices[:3]]

                # 先用新策略：根据关键词从pre_summary查找文档（取前3个）
                new_strategy_docs = _find_documents_by_keyword(keyword, username, max_count=3, min_count=1)
                print(f"[generate_permanent_card] 旧策略找到{len(doc_names_from_cards)}个文档（>3），先用新策略查找: {new_strategy_docs}")

                if new_strategy_docs:
                    # 尝试解析页码（包括15次采样）
                    test_page_ranges = _parse_page_ranges_for_docs(new_strategy_docs, keyword, username,
                                                                   reference_cards=cards)
                    # 检查是否有至少一个文档能找到页码
                    has_valid_page = any(page_ranges is not None for _, page_ranges in test_page_ranges)

                    if has_valid_page:
                        # 新策略找到的文档能解析出页码，使用新策略（保存已解析的结果）
                        final_doc_names = new_strategy_docs
                        doc_page_ranges = test_page_ranges  # 直接使用已解析的结果，避免重复解析
                        print(f"[generate_permanent_card] 新策略找到的文档能解析出页码，使用新策略结果: {final_doc_names}")
                    else:
                        # 新策略找到的文档经过15次采样都找不到页码，回退到均匀抽取
                        final_doc_names = uniformly_sample_docs(doc_names_from_cards)
                        print(f"[generate_permanent_card] 新策略找到的文档无法解析页码，回退到均匀抽取: {final_doc_names}")
                else:
                    # 新策略没有找到文档，回退到均匀抽取
                    final_doc_names = uniformly_sample_docs(doc_names_from_cards)
                    print(f"[generate_permanent_card] 新策略未找到文档，回退到均匀抽取: {final_doc_names}")
            else:
                final_doc_names = doc_names_from_cards  # 3个或更少，全部使用
        else:
            # 新策略：从pre_summary目录根据关键词查找
            final_doc_names = _find_documents_by_keyword(keyword, username, max_count=3, min_count=1)
            print(f"[generate_permanent_card] 旧策略为空，新策略找到{len(final_doc_names)}个文档: {final_doc_names}")

        # 8.3 对最终文档列表解析页数（传入参考卡片用于采样词汇）
        if final_doc_names:
            # 如果之前在新策略测试时已经解析过，直接使用；否则现在解析
            if doc_page_ranges is None:
                doc_page_ranges = _parse_page_ranges_for_docs(final_doc_names, keyword, username, reference_cards=cards)
            # 格式化输出（1/2/3标号换行格式），只包含有页码的文档
            result_lines = []
            valid_docs = [(doc_name, page_ranges) for doc_name, page_ranges in doc_page_ranges if
                          page_ranges is not None]
            for idx, (doc_name, page_ranges) in enumerate(valid_docs[:3], 1):  # 最多3个
                # page_ranges是列表，可能包含1-2个页数区间
                page_strs = []
                for page_range in page_ranges:
                    if page_range[0] == page_range[1]:
                        page_strs.append(f"第{page_range[0]}页")
                    else:
                        page_strs.append(f"第{page_range[0]}-{page_range[1]}页")
                # 用顿号连接多个页数区间
                page_str = "、".join(page_strs)
                result_lines.append(f"{idx}. {doc_name}（{page_str}）")
            source_references = "\n".join(result_lines) if result_lines else "无"
        else:
            source_references = "无"

        # 9. 分析人机认知比例（使用辅助函数）
        # 准备参考卡片对象列表（用于分析）
        reference_cards_for_ratio = []
        if cards:
            for card in cards:
                if isinstance(card, dict):
                    reference_cards_for_ratio.append(card)

        # 准备QA卡片列表（用于分析）
        qa_cards_for_ratio = []
        if qa_cards:
            for qa_card in qa_cards:
                if isinstance(qa_card, dict):
                    qa_cards_for_ratio.append(qa_card)

        human_machine_ratio = _analyze_human_machine_ratio(qa_cards_for_ratio, reference_cards_for_ratio,
                                                           notebook_desc)

        # 如果LLM生成的人机认知比例存在，优先使用LLM生成的（但如果格式不对，使用我们分析的）
        if card_data.get('humanMachineRatio'):
            llm_ratio = card_data.get('humanMachineRatio', '').strip()
            if llm_ratio:
                human_machine_ratio = llm_ratio

        conclusion_reason = card_data.get('conclusionReason', '').strip()

        # 10. 构建完整的卡片内容（先构建，用于评分）
        content_body = card_data.get('content', '').strip()

        # 确保开头&中间部分（一体）与后续部分之间有---分隔符（如果LLM没有添加的话）
        if '---' not in content_body:
            # 尝试在开头&中间部分（约150-200字）之后，与后续部分之间添加---分隔符
            if len(content_body) > 150:
                # 在150-200字之间查找句号或换行，在其后插入---（分隔开头&中间部分与后续部分）
                insert_pos = -1
                for i in range(150, min(200, len(content_body))):
                    if content_body[i] in ['。', '\n', '！', '？']:
                        insert_pos = i + 1
                        break
                if insert_pos > 0:
                    content_body = content_body[:insert_pos] + '\n\n---\n\n' + content_body[insert_pos:]

        # 构建完整内容：主体内容在前，然后是支撑文献来源、人机认知比例、为什么可以得出这样的结论（用---分隔）
        if source_references and source_references != "无":
            full_content = f"{content_body}\n\n---\n\n支撑文献来源：\n{source_references}\n\n人机认知比例：{human_machine_ratio}\n\n为什么可以得出这样的结论：{conclusion_reason}"
        else:
            full_content = f"{content_body}\n\n---\n\n支撑文献来源：无\n\n人机认知比例：{human_machine_ratio}\n\n为什么可以得出这样的结论：{conclusion_reason}"

        # 9. 🔥 并发执行打分和红蓝评测（参考automation的逻辑）
        async def score_and_evaluate():
            tasks = []

            # 1. 打分任务（使用red_bule_rate.get_rate）
            async def get_score():
                try:
                    score, color, reason = red_bule_rate.get_rate(username, full_content)
                    return {'error_num': 0, 'score': score, 'color': color, 'reason': reason}
                except Exception as e:
                    print(f"[generate_permanent_card] 获取score/color/reason失败: {e}")
                    return {'error_num': 1, 'error': str(e)}

            # 2. 红蓝评测任务（使用execute_commands的逻辑）
            async def get_evalSFT():
                try:
                    # 模拟execute_commands的调用
                    text = full_content.replace("\n", "\\n")
                    # command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","text":"{text}"}}\' http://192.0.2.1:8000/invoke_rate'
                    server_url = get_small_model_server_url(username)
                    command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","text":"{text}"}}\' {server_url}/invoke_rate'
                    result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, text=True, timeout=30)

                    # 解析结果（参考automation的处理逻辑）
                    data_str = result.stdout.strip()
                    if data_str.startswith('"') and data_str.endswith('"'):
                        data_str = data_str[1:-1]
                    data_str = data_str.replace('\\"', '"').replace('\\\\', '\\')

                    # 解析JSON
                    result_object = json.loads(data_str)
                    decoded_result = result_object.get('result', '')

                    if decoded_result and decoded_result != "fail":
                        # 提取scoreSFT, colorSFT, reasonSFT（参考card_evalSFT的逻辑）
                        scoreSFT = float(extract_number_SFT(decoded_result)) if extract_number_SFT(
                            decoded_result) is not None else 4.5
                        colorSFT = extract_color_SFT(decoded_result) or "紫"
                        reasonSFT = extract_reason_SFT(decoded_result) or "永久卡片（原子化&原创化&可复用化）"
                        if scoreSFT >= 1.0 and colorSFT != "紫":
                            colorSFT = "紫"
                        return {'error_num': 0, 'scoreSFT': scoreSFT, 'colorSFT': colorSFT, 'reasonSFT': reasonSFT}
                    else:
                        return {'error_num': 1, 'error': '红蓝评测结果为fail'}
                except Exception as e:
                    print(f"[generate_permanent_card] 获取scoreSFT/colorSFT/reasonSFT失败: {e}")
                    import traceback
                    traceback.print_exc()
                    return {'error_num': 1, 'error': str(e)}

            # 并发执行
            score_result, eval_result = await asyncio.gather(get_score(), get_evalSFT(), return_exceptions=True)

            # 处理异常
            if isinstance(score_result, Exception):
                score_result = {'error_num': 1, 'error': str(score_result)}
            if isinstance(eval_result, Exception):
                eval_result = {'error_num': 1, 'error': str(eval_result)}

            return score_result, eval_result

        # 执行并发操作
        print(f"[generate_permanent_card] 开始调用模型获取score/color/reason和scoreSFT/colorSFT/reasonSFT...")
        try:
            loop = asyncio.new_event_loop()
            score_result, eval_result = loop.run_until_complete(score_and_evaluate())
            loop.close()
        except Exception as e:
            print(f"[generate_permanent_card] 并发执行评分失败: {e}")
            import traceback
            traceback.print_exc()
            score_result = {'error_num': 1}
            eval_result = {'error_num': 1}

        # 获取评分结果
        if score_result.get('error_num') == 0:
            score = score_result.get('score', 4.5)
            color = score_result.get('color', '紫')
            reason = score_result.get('reason', '永久卡片（原子化&原创化&可复用化）')
            print(f"[generate_permanent_card] score={score}, color={color}, reason={reason[:50]}...")
        else:
            score = 4.5
            color = "紫"
            reason = "永久卡片（原子化&原创化&可复用化）"
            print(f"[generate_permanent_card] 获取score/color/reason失败，使用默认值")

        if eval_result.get('error_num') == 0:
            scoreSFT = eval_result.get('scoreSFT', 4.5)
            colorSFT = eval_result.get('colorSFT', '紫')
            reasonSFT = eval_result.get('reasonSFT', '永久卡片（原子化&原创化&可复用化）')
            print(f"[generate_permanent_card] scoreSFT={scoreSFT}, colorSFT={colorSFT}, reasonSFT={reasonSFT[:50]}...")
        else:
            scoreSFT = 4.5
            colorSFT = "紫"
            reasonSFT = "永久卡片（原子化&原创化&可复用化）"
            print(f"[generate_permanent_card] 获取scoreSFT/colorSFT/reasonSFT失败，使用默认值")

        # 10. 处理contentTitle（确保格式正确：Sm:keyword）
        content_title = card_data.get('contentTitle', f"S{last_sub_scene_num}:{keyword}")
        if not content_title.startswith(f"S{last_sub_scene_num}:"):
            # 如果LLM生成的contentTitle格式不对，修正它
            content_title = f"S{last_sub_scene_num}:{keyword}"

        # 11. 检查是否已有对应卡片（title="关键词神经元永久卡" 且 keyWords=keyword）
        existing_card = None
        try:
            existing_card = Card.objects.get(
                username=username,
                title="关键词神经元永久卡",
                keyWords=keyword
            )
        except Card.DoesNotExist:
            existing_card = None
        except Card.MultipleObjectsReturned:
            # 如果有多张，取最新的一张
            existing_card = Card.objects.filter(
                username=username,
                title="关键词神经元永久卡",
                keyWords=keyword
            ).order_by('-datetime').first()

        if existing_card:
            # 🔥 更新现有卡片：将原content赋值给lastContent，新content写入content
            existing_card.lastContent = existing_card.content
            existing_card.content = full_content
            existing_card.score = score
            existing_card.scoreSFT = scoreSFT
            existing_card.color = color
            existing_card.colorSFT = colorSFT
            existing_card.reason = reason
            existing_card.reasonSFT = reasonSFT
            existing_card.contentTitle = content_title
            existing_card.postIndex = post_index_value
            existing_card.four_color_type = four_color_type
            existing_card.dmt_level = dmt_level
            existing_card.is_analyzed_by_new_standard = True
            existing_card.save()
            new_card = existing_card
        else:
            # 新建卡片
            new_card = Card.objects.create(
                username=username,
                model_id=model_id or "1769",  # 默认使用claude-sonnet-5的model_id
                status="0",
                content=full_content,
                title="关键词神经元永久卡",  # 🔥 title改为"关键词神经元永久卡"
                score=score,  # 使用模型获取的评分
                scoreSFT=scoreSFT,  # 使用模型获取的SFT评分
                color=color,  # 使用模型获取的颜色
                colorSFT=colorSFT,  # 使用模型获取的SFT颜色
                reason=reason,  # 使用模型获取的理由
                reasonSFT=reasonSFT,  # 使用模型获取的SFT理由
                keyWords=keyword,
                contentTitle=content_title,  # 使用处理后的contentTitle（Sm:keyword格式）
                type="永久",
                postIndex=post_index_value,  # 使用处理后的postIndex（cid列表，逗号分隔）
                four_color_type=four_color_type,
                dmt_level=dmt_level,
                is_neuron=True,  # 标记为神经元卡
                is_analyzed_by_new_standard=True,  # 🔥 已按新标准分析，避免刷新后重新分析覆盖
                # writer=origin_real_name if is_group_notebook and origin_real_name else realName
            )

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'card_id': new_card.cid,
            'contentTitle': new_card.contentTitle
        })

    except Exception as e:
        print(f"[generate_permanent_card] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'生成失败: {str(e)}'
        })


def _cleanup_keyword_from_notebook_if_orphan(username, keyword, exclude_cids=None):
    """
    若关键词在本子其他卡片中不再出现，则从 keywordFourColorDMT、keywordFusionRelations 中清理。
    exclude_cids: 要排除的卡片 cid 列表（已删除或即将删除的）
    """
    exclude_cids = exclude_cids or []
    try:
        other_cards = Card.objects.filter(username=username).exclude(cid__in=exclude_cids)
        for card in other_cards:
            if not card.keyWords:
                continue
            kws = [k.strip() for k in re.split(r'[,，]', card.keyWords or '') if k.strip()]
            if keyword in kws:
                return  # 关键词仍存在于其他卡片，无需清理
        # 关键词已不在任何卡片中，清理
        realName = username.split('_')[0] if '_' in username else username
        bookName = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
        if not bookName:
            return
        nb = UserNotebook.objects.get(username=realName, bookName=bookName)
        updated = False
        if nb.keywordFourColorDMT:
            kfd = json.loads(nb.keywordFourColorDMT or '{}')
            if keyword in kfd:
                del kfd[keyword]
                nb.keywordFourColorDMT = json.dumps(kfd, ensure_ascii=False)
                updated = True
        if nb.keywordFusionRelations:
            fusion = json.loads(nb.keywordFusionRelations or '{}')
            if keyword in fusion:
                del fusion[keyword]
                updated = True
            for k, v in list(fusion.items()):
                if isinstance(v, dict) and v.get('source_keywords'):
                    src = v['source_keywords']
                    if keyword in src:
                        src_new = [x for x in src if x != keyword]
                        if len(src_new) < 2:
                            del fusion[k]
                        else:
                            fusion[k] = {'source_keywords': src_new}
                        updated = True
            if updated:
                nb.keywordFusionRelations = json.dumps(fusion, ensure_ascii=False)
        if updated:
            nb.save()
            print(f"[_cleanup_keyword_from_notebook_if_orphan] 已清理关键词'{keyword}'的 keywordFourColorDMT/keywordFusionRelations")
    except Exception as e:
        print(f"[_cleanup_keyword_from_notebook_if_orphan] 清理失败: {e}")


@csrf_exempt
def delete_permanent_card(request):
    """
    🔥 删除关键词神经元永久卡API
    根据关键词删除对应的永久卡片
    """
    try:
        data = json.loads(request.body)
        keyword = data.get('keyword', '').strip()
        username = data.get('username', '')

        if not keyword or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整：缺少keyword或username'
            })

        # 查找并删除永久卡
        try:
            # 查找该关键词的永久卡
            permanent_cards = Card.objects.filter(
                username=username,
                title="关键词神经元永久卡",
                keyWords=keyword
            )

            if not permanent_cards.exists():
                return JsonResponse({
                    'error_num': 1,
                    'msg': f'未找到关键词"{keyword}"的神经元永久卡'
                })

            # 删除所有匹配的永久卡
            exclude_cids = list(permanent_cards.values_list('cid', flat=True))
            deleted_count = permanent_cards.count()
            permanent_cards.delete()

            _cleanup_keyword_from_notebook_if_orphan(username, keyword, exclude_cids)

            return JsonResponse({
                'error_num': 0,
                'msg': 'success',
                'deleted_count': deleted_count
            })

        except Exception as e:
            print(f"[delete_permanent_card] 删除失败: {e}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'error_num': 1,
                'msg': f'删除失败: {str(e)}'
            })

    except Exception as e:
        print(f"[delete_permanent_card] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'请求处理失败: {str(e)}'
        })