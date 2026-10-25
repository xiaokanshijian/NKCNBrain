# encoding=utf-8
"""
🔥 关键词融合相关的视图函数
"""
import nkcn_public_config as _public_config
import json
import os
import re
import asyncio
import subprocess
import contextvars
import functools
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from app_chat.config.config_manager import config_manager
from openai import OpenAI
from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
from app_chat.models import Card
from zym.models import scene, UserNotebook
from llm_langchain import red_bule_rate
from llm_langchain.red_bule_rate import extract_number_SFT, extract_color_SFT, extract_reason_SFT
from app_chat.keyword_analyzer import analyze_keyword_four_color_dmt_with_llm, update_notebook_keyword_four_color_dmt
import pandas as pd


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


# 自定义to_thread函数（兼容Python 3.7+）
async def to_thread(func, /, *args, **kwargs):
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    func_call = functools.partial(ctx.run, func, *args, **kwargs)
    return await loop.run_in_executor(None, func_call)


@csrf_exempt
def fuse_keywords(request):
    """
    🔥 融合两个关键词生成3个不同视角、语境、粒度的融合关键词选项
    每个关键词都标注了DMT和四色属性
    返回前端供用户选择和编辑，不生成永久卡片
    """
    try:
        data = json.loads(request.body)
        keyword1 = data.get('keyword1', '').strip()
        keyword2 = data.get('keyword2', '').strip()
        username = data.get('username', '')
        scene_name = data.get('scene_name', '')
        sub_scene_name = data.get('sub_scene_name', '')
        is_group_notebook = data.get('is_group_notebook', False)
        origin_real_name = data.get('origin_real_name', '')
        use_relay = data.get('useRelay', False)  # 🔥 是否使用中转服务器调用8卡服务器（默认False，使用claude）
        print(f"[fuse_keywords] use_relay参数: {use_relay}, {type(use_relay)}")

        if not keyword1 or not keyword2 or not username:
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

        # 2. 获取最后一个子场景编号
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

        last_sub_scene = sub_scene_name or ""
        last_sub_scene_num = 0
        if scene_name:
            try:
                scene_dir_path = './received_dir/scene_excel/' + scene_name
                prompt_excel_path = os.path.join(scene_dir_path, 'prompt.xlsx')
                if os.path.exists(prompt_excel_path):
                    excel_data = pd.read_excel(prompt_excel_path, sheet_name='LUI1')
                    sub_scene_col = 1
                    if excel_data.shape[1] > sub_scene_col:
                        first_subscene_col_name = excel_data.columns[sub_scene_col]
                        subscene_name_list = excel_data.iloc[:, sub_scene_col].dropna().tolist()
                        subscene_name_list_order = [first_subscene_col_name] + subscene_name_list
                        last_sub_scene_num = len(subscene_name_list_order)
                        if subscene_name_list_order:
                            last_sub_scene = subscene_name_list_order[-1]
            except Exception as e:
                print(f"[fuse_keywords] 从excel获取子场景信息失败: {e}")

        # 3. 调用LLM生成3个不同视角、语境、粒度的融合关键词（一次调用）
        # 优先使用claude-4-sonnet，失败则升级到claude-sonnet-4.5，再失败则降级到claude-3.7
        model_priority = ['claude-4-sonnet', 'claude-sonnet-4.5', 'claude-3.7']
        keyword_options = []
        model_used = None

        # 3.1 收集参考卡片内容（用于分析四色DMT）
        all_cards = Card.objects.filter(username=username)
        cards_with_keyword1 = []
        cards_with_keyword2 = []
        for card in all_cards:
            if not card.keyWords or not card.four_color_type or not card.dmt_level:
                continue
            card_keywords = [k.strip() for k in re.split(r'[,，]', card.keyWords) if k.strip()]
            if keyword1 in card_keywords and card not in cards_with_keyword1:
                cards_with_keyword1.append(card)
            if keyword2 in card_keywords and card not in cards_with_keyword2:
                cards_with_keyword2.append(card)

        reference_cards_for_analysis = list(set(cards_with_keyword1 + cards_with_keyword2))
        combined_card_content = '\n\n'.join([card.content or '' for card in reference_cards_for_analysis[:5]])

        # 3.1.1 为每个关键词选择一张代表性卡片（用于8卡服务器小模型）
        representative_card1 = _select_representative_card(keyword1, username, all_cards)
        representative_card2 = _select_representative_card(keyword2, username, all_cards)

        # 3.2 根据use_relay参数决定调用方式
        if use_relay:
            # 使用8卡服务器小模型
            keyword_options = _fuse_keywords_via_relay(
                keyword1, keyword2, username, final_scene_summary, notebook_desc,
                representative_card1, representative_card2
            )
        else:
            # 使用claude大模型
            keyword_options = _fuse_keywords_via_claude(
                keyword1, keyword2, model_priority, combined_card_content
            )

        # 4. 验证结果
        if not keyword_options or len(keyword_options) < 3:
            return JsonResponse({
                'error_num': 1,
                'msg': '生成融合关键词选项失败，未成功生成3个关键词'
            })

        # 5. 返回3个关键词选项给前端（不生成永久卡片，不保存到数据库）
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'keyword_options': keyword_options
        })

    except Exception as e:
        print(f"[fuse_keywords] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'融合失败: {str(e)}'
        })


def _fuse_keywords_via_claude(keyword1, keyword2, model_priority, combined_card_content):
    """
    使用Claude大模型生成融合关键词
    """
    keyword_options = []
    model_used = None

    for model_name in model_priority:
        try:
            # 构建Prompt：生成3个不同视角的关键词，并标注DMT和四色
            user_prompt = f"""你需要基于两个关键词"{keyword1}"和"{keyword2}"，生成**3个**自洽、深刻、具体、原创的新关键词，每个关键词要**不同视角、不同语境、不同粒度**。

## 要求

1. **内涵体现**：每个新关键词必须能够体现两个原关键词"{keyword1}"和"{keyword2}"的内涵
2. **新内涵涌现**：每个新关键词必须产生新的内涵涌现（1+1>2），不仅仅是两个关键词的简单组合
3. **自洽深刻具体**：每个新关键词必须自洽、深刻、具体，有明确的认知指向
4. **禁忌边界**：切忌使用看似高深实则看不懂的用语（例如"数与运算初探"和"生活化迁移"融合出"数感通融力"，完全读不懂），应该简单自然而深刻
5. **字数限制**：每个新关键词不超过8字，考虑单词或指标名（如C0）的情况（连续的字母或数字算一个字）
6. **差异化**：3个关键词要体现不同视角、不同语境、不同粒度（例如：一个偏宏观框架，一个偏具体方法，一个偏工具技术）

## 四色类型说明
- **R（红色）**：专业业务语言，明确的专业术语、行业规范
- **B（蓝色）**：技术工具语言，具体的技术工具、可操作方法
- **P（紫色）**：场景思维语言，逻辑思维、系统性推演、方法论框架
- **G（绿色）**：自然语言，简单易懂且深刻的自然表达

## DMT层次说明
- **T（顶层）**：偏思维性的框架，具有可向下击穿性（约10-15%）
- **M（中层）**：中等抽象程度，连接过渡、分类组织（约25-35%）
- **D（底层）**：具象具体，可直接执行的操作（约50-60%）

## 输出格式

请严格按照以下JSON格式输出：

```json
{{
    "keywords": [
        {{
            "keyword": "关键词1",
            "four_color_type": "R/B/P/G",
            "dmt_level": "D/M/T",
            "perspective": "此关键词的视角说明（10-20字）"
        }},
        {{
            "keyword": "关键词2",
            "four_color_type": "R/B/P/G",
            "dmt_level": "D/M/T",
            "perspective": "此关键词的视角说明（10-20字）"
        }},
        {{
            "keyword": "关键词3",
            "four_color_type": "R/B/P/G",
            "dmt_level": "D/M/T",
            "perspective": "此关键词的视角说明（10-20字）"
        }}
    ]
}}
```

**重要**：
1. 必须输出3个关键词，每个都要不同视角、语境、粒度
2. 每个关键词都要标注正确的four_color_type（R/B/P/G）和dmt_level（D/M/T）
3. 必须严格按照JSON格式输出，不要输出其他内容"""

            model_config = config_manager.get_model_config(model_name)
            if not model_config:
                continue

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
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=hyper_para.max_tokens,
                temperature=hyper_para.temperature
            )

            response_content = response.choices[0].message.content

            if response_content and len(response_content.strip()) > 50:
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

                    if len(keywords_list) >= 3:
                        # 验证并清理关键词
                        valid_keywords = []
                        for kw_data in keywords_list[:3]:
                            kw = kw_data.get('keyword', '').strip()
                            # 清理输出
                            kw = re.sub(r'^["\'""]|["\'""]$', '', kw)
                            kw = re.sub(r'[。，、；：！？\s]+$', '', kw)
                            kw = kw.strip()

                            # 验证字数
                            word_count = len(re.findall(r'[\u4e00-\u9fa5]', kw))
                            alpha_num_count = len(re.findall(r'[a-zA-Z0-9]+', kw))
                            total_count = word_count + alpha_num_count

                            if total_count <= 9 and len(kw) > 0:
                                four_color = kw_data.get('four_color_type', 'P').strip().upper()
                                if four_color not in ['R', 'B', 'P', 'G']:
                                    four_color = 'P'

                                dmt = kw_data.get('dmt_level', 'M').strip().upper()
                                if dmt not in ['D', 'M', 'T']:
                                    dmt = 'M'

                                perspective = kw_data.get('perspective', '').strip()

                                valid_keywords.append({
                                    'keyword': kw,
                                    'four_color_type': four_color,
                                    'dmt_level': dmt,
                                    'perspective': perspective
                                })

                        if len(valid_keywords) >= 3:
                            keyword_options = valid_keywords[:3]
                            model_used = model_name
                            print(f"[_fuse_keywords_via_claude] 使用{model_name}成功生成3个融合关键词选项")
                            return keyword_options

                except Exception as e:
                    print(f"[_fuse_keywords_via_claude] 解析{model_name}返回的JSON失败: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

        except Exception as e:
            print(f"[_fuse_keywords_via_claude] 使用{model_name}生成融合关键词失败: {e}")
            import traceback
            traceback.print_exc()
            continue

    return []  # 如果所有模型都失败，返回空列表


def _select_representative_card(keyword, username, all_cards):
    """
    为关键词选择一张代表性卡片

    选择优先级：
    1. 关键词神经元永久卡（is_neuron=True 且 type="永久"）
    2. 紫色或绿色、红蓝深评（占7）浅评（占3）加权得分≥3.5的卡
    3. 所有包含该关键词的卡片中，按综合得分排序，选择最好的
    """
    try:
        # 筛选包含该关键词的卡片
        cards_with_keyword = []
        for card in all_cards:
            if not card.keyWords:
                continue
            card_keywords = [k.strip() for k in re.split(r'[,，]', card.keyWords) if k.strip()]
            if keyword in card_keywords:
                cards_with_keyword.append(card)

        if not cards_with_keyword:
            print(f"[_select_representative_card] 关键词'{keyword}'没有找到包含它的卡片")
            return None

        # 1. 优先选择：关键词神经元永久卡（is_neuron=True 且 type="永久"）
        permanent_neuron_cards = []
        for card in cards_with_keyword:
            if card.is_neuron and card.type and "永久" in card.type:
                permanent_neuron_cards.append(card)

        if permanent_neuron_cards:
            # 如果有多个永久卡，选择最新的（按datetime）
            permanent_neuron_cards.sort(key=lambda x: x.datetime if x.datetime else '', reverse=True)
            selected_card = permanent_neuron_cards[0]
            print(f"[_select_representative_card] 关键词'{keyword}'选择了永久神经元卡 (CID: {selected_card.cid})")
            return selected_card

        # 2. 其次选择：紫色或绿色、红蓝深评（占7）浅评（占3）加权得分≥3.5的卡
        qualified_cards = []
        for card in cards_with_keyword:
            if not (card.four_color_type and card.dmt_level):
                continue

            # 必须是紫色(P)或绿色(G)
            if card.four_color_type not in ['P', 'G']:
                continue

            # 计算加权得分：深评（占7）浅评（占3）
            score = float(card.score) if card.score else 0
            scoreSFT = float(card.scoreSFT) if card.scoreSFT else 0
            weighted_score = score * 0.3 + scoreSFT * 0.7

            if weighted_score >= 3.5:
                qualified_cards.append((card, weighted_score))

        if qualified_cards:
            # 按加权得分降序排序，选择得分最高的
            qualified_cards.sort(key=lambda x: x[1], reverse=True)
            selected_card = qualified_cards[0][0]
            print(
                f"[_select_representative_card] 关键词'{keyword}'选择了符合要求的卡片 (CID: {selected_card.cid}, 加权得分: {qualified_cards[0][1]:.2f})")
            return selected_card

        # 3. 最后选择：所有包含该关键词的卡片中，按综合得分排序，选择最好的
        all_scored_cards = []
        for card in cards_with_keyword:
            score = float(card.score) if card.score else 0
            scoreSFT = float(card.scoreSFT) if card.scoreSFT else 0
            weighted_score = score * 0.3 + scoreSFT * 0.7
            all_scored_cards.append((card, weighted_score))

        if all_scored_cards:
            # 按加权得分降序排序，选择得分最高的
            all_scored_cards.sort(key=lambda x: x[1], reverse=True)
            selected_card = all_scored_cards[0][0]
            print(
                f"[_select_representative_card] 关键词'{keyword}'选择了综合得分最高的卡片 (CID: {selected_card.cid}, 加权得分: {all_scored_cards[0][1]:.2f})")
            return selected_card

        # 如果还是没有，返回第一个卡片
        if cards_with_keyword:
            selected_card = cards_with_keyword[0]
            print(f"[_select_representative_card] 关键词'{keyword}'选择了第一个找到的卡片 (CID: {selected_card.cid})")
            return selected_card

        return None

    except Exception as e:
        print(f"[_select_representative_card] 选择代表性卡片失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def _fuse_keywords_via_relay(keyword1, keyword2, username, final_scene_summary, notebook_desc,
                             representative_card1, representative_card2, regenerate_mode=False, current_options=None):
    """
    通过中转服务器调用8卡服务器小模型生成融合关键词
    regenerate_mode: 是否为重新生成模式（整体重来一遍）
    current_options: 当前选项列表（用于分析用户需求）
    """
    try:
        import requests

        # 构建Prompt（system_prompt已在PEFTmodel.py中定义，这里只提供user_prompt）
        if regenerate_mode and current_options:
            # 重新生成模式：分析当前选项，理解用户为什么觉得不够好
            current_options_text = ""
            for i, opt in enumerate(current_options[:3], 1):
                current_options_text += f"\n选项{i}：{opt.get('keyword', '')}（{opt.get('four_color_type', '')}/{opt.get('dmt_level', '')}，视角：{opt.get('perspective', '')}）"

            user_prompt = f"""用户对以下3个融合关键词选项不满意，要求重新生成：
{current_options_text}

请分析这些选项的问题（可能包括：关键词不够深刻、视角不够独特、四色DMT标注不够准确、缺乏新内涵涌现等），然后基于两个原关键词"{keyword1}"和"{keyword2}"，结合下方提供的代表性卡片信息，生成**3个全新的、更好的**融合关键词选项。要避免之前选项的问题，提供更高质量、更有差异化的选项。严格按照要求（包括内容上和格式上）输出JSON格式结果。"""
        else:
            user_prompt = f"""请基于两个关键词"{keyword1}"和"{keyword2}"，结合下方提供的代表性卡片信息，生成3个融合关键词选项。严格按照要求（包括内容上和格式上）输出JSON格式结果。"""

        # 添加代表性卡片内容到prompt中
        card_info_section = ""
        if representative_card1:
            card_info_section += f"\n\n## 关键词\"{keyword1}\"的代表性卡片：\n"
            card_info_section += f"标题：{representative_card1.title or ''}\n"
            card_info_section += f"内容：{(representative_card1.content or '')[:800]}\n"
            if representative_card1.four_color_type:
                card_info_section += f"四色类型：{representative_card1.four_color_type}\n"
            if representative_card1.dmt_level:
                card_info_section += f"DMT层次：{representative_card1.dmt_level}\n"
            score1 = float(representative_card1.score) if representative_card1.score else 0
            scoreSFT1 = float(representative_card1.scoreSFT) if representative_card1.scoreSFT else 0
            weighted_score1 = score1 * 0.3 + scoreSFT1 * 0.7
            card_info_section += f"综合得分：{weighted_score1:.2f}\n"

        if representative_card2:
            card_info_section += f"\n\n## 关键词\"{keyword2}\"的代表性卡片：\n"
            card_info_section += f"标题：{representative_card2.title or ''}\n"
            card_info_section += f"内容：{(representative_card2.content or '')[:800]}\n"
            if representative_card2.four_color_type:
                card_info_section += f"四色类型：{representative_card2.four_color_type}\n"
            if representative_card2.dmt_level:
                card_info_section += f"DMT层次：{representative_card2.dmt_level}\n"
            score2 = float(representative_card2.score) if representative_card2.score else 0
            scoreSFT2 = float(representative_card2.scoreSFT) if representative_card2.scoreSFT else 0
            weighted_score2 = score2 * 0.3 + scoreSFT2 * 0.7
            card_info_section += f"综合得分：{weighted_score2:.2f}\n"

        # 将代表性卡片信息添加到user_prompt（system_prompt已在PEFTmodel.py中定义，不需要在这里添加）
        full_input_text = user_prompt + card_info_section

        # 处理特殊字符（与get_depth_suggestion格式保持一致）
        full_input_text = full_input_text.replace("\n", "\\n")
        full_input_text = full_input_text.replace('```', '').replace('"""', '').replace('"', '“').replace("'", '‘')

        # 构造请求数据
        task_type = "keyword_fusion_regenerate" if regenerate_mode else "keyword_fusion"
        request_data = {
            "input_text": full_input_text,
            # "user_name": username.split('_')[0] if '_' in username else username,
            "user_name": username,
            "task_type": task_type
        }

        # 🔥 使用requests库发送POST请求
        server_url = get_small_model_server_url(username)
        response = requests.post(
            f'{server_url}/get_depth_suggestion',
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=120  # 120秒超时
        )

        # 检查HTTP状态码
        if response.status_code != 200:
            print(f"[_fuse_keywords_via_relay] HTTP请求失败，状态码: {response.status_code}")
            print(f"[_fuse_keywords_via_relay] 响应内容: {response.text[:500]}")
            return []

        # 解析返回结果
        result_data = response.json()

        if result_data.get('error_num') != 0:
            print(f"[_fuse_keywords_via_relay] 通过中转服务器生成融合关键词失败: {result_data.get('message', '未知错误')}")
            return []

        response_content = result_data.get('suggestion', '')

        if not response_content or len(response_content.strip()) < 50:
            print(f"[_fuse_keywords_via_relay] 响应内容过短: {len(response_content) if response_content else 0}")
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

            if len(keywords_list) < 3:
                print(f"[_fuse_keywords_via_relay] 关键词数量不足: {len(keywords_list)}")
                return []

            # 验证并清理关键词
            valid_keywords = []
            for kw_data in keywords_list[:3]:
                kw = kw_data.get('keyword', '').strip()
                # 清理输出
                kw = re.sub(r'^["\'""]|["\'""]$', '', kw)
                kw = re.sub(r'[。，、；：！？\s]+$', '', kw)
                kw = kw.strip()

                # 验证字数
                word_count = len(re.findall(r'[\u4e00-\u9fa5]', kw))
                alpha_num_count = len(re.findall(r'[a-zA-Z0-9]+', kw))
                total_count = word_count + alpha_num_count

                if total_count <= 9 and len(kw) > 0:
                    four_color = kw_data.get('four_color_type', 'P').strip().upper()
                    if four_color not in ['R', 'B', 'P', 'G']:
                        four_color = 'P'

                    dmt = kw_data.get('dmt_level', 'M').strip().upper()
                    if dmt not in ['D', 'M', 'T']:
                        dmt = 'M'

                    perspective = kw_data.get('perspective', '').strip()

                    valid_keywords.append({
                        'keyword': kw,
                        'four_color_type': four_color,
                        'dmt_level': dmt,
                        'perspective': perspective
                    })

            if len(valid_keywords) >= 3:
                print(f"[_fuse_keywords_via_relay] 通过中转服务器成功生成3个融合关键词选项")
                return valid_keywords[:3]
            else:
                print(f"[_fuse_keywords_via_relay] 有效关键词数量不足: {len(valid_keywords)}")
                return []

        except Exception as e:
            print(f"[_fuse_keywords_via_relay] 解析JSON失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    except requests.exceptions.Timeout:
        print(f"[_fuse_keywords_via_relay] 请求超时（120秒）")
        return []
    except requests.exceptions.ConnectionError as e:
        print(f"[_fuse_keywords_via_relay] 连接错误: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"[_fuse_keywords_via_relay] JSON解析失败: {e}")
        return []
    except Exception as e:
        print(f"[_fuse_keywords_via_relay] 生成融合关键词异常: {e}")
        import traceback
        traceback.print_exc()
        return []


@csrf_exempt
def regenerate_fuse_keywords(request):
    """
    🔥 整体重新生成3个融合关键词选项
    微调prompt，考虑用户为什么觉得三个都不够好（基于当前选项分析）
    """
    try:
        data = json.loads(request.body)
        keyword1 = data.get('keyword1', '').strip()
        keyword2 = data.get('keyword2', '').strip()
        username = data.get('username', '')
        scene_name = data.get('scene_name', '')
        sub_scene_name = data.get('sub_scene_name', '')
        use_relay = data.get('useRelay', False)
        current_options = data.get('current_options', [])  # 当前3个选项，用于分析用户需求

        if not keyword1 or not keyword2 or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        # 获取场景信息和本子描述
        scene_summary_info = None
        notebook_desc = ""
        if scene_name:
            scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, sub_scene_name)
            notebook_desc = get_notebook_description(username, scene_name)
            final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
        else:
            final_scene_summary = None

        # 获取代表性卡片
        all_cards = Card.objects.filter(username=username)
        representative_card1 = _select_representative_card(keyword1, username, all_cards)
        representative_card2 = _select_representative_card(keyword2, username, all_cards)

        # 使用8卡服务器小模型（整体重来只支持小模型）
        keyword_options = _fuse_keywords_via_relay(
            keyword1, keyword2, username, final_scene_summary, notebook_desc,
            representative_card1, representative_card2,
            regenerate_mode=True,  # 标记为重新生成模式
            current_options=current_options  # 传递当前选项，用于分析
        )

        # 验证结果
        if not keyword_options or len(keyword_options) < 3:
            return JsonResponse({
                'error_num': 1,
                'msg': '重新生成融合关键词选项失败，未成功生成3个关键词'
            })

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'keyword_options': keyword_options
        })

    except Exception as e:
        print(f"[regenerate_fuse_keywords] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'重新生成失败: {str(e)}'
        })


@csrf_exempt
def regenerate_single_fuse_keyword(request):
    """
    🔥 单独重新生成某个融合关键词选项的关键词名
    基于用户编辑后的四色/DMT/视角，重新生成关键词名
    """
    try:
        data = json.loads(request.body)
        keyword1 = data.get('keyword1', '').strip()
        keyword2 = data.get('keyword2', '').strip()
        username = data.get('username', '')
        scene_name = data.get('scene_name', '')
        sub_scene_name = data.get('sub_scene_name', '')
        original_keyword = data.get('original_keyword', '').strip()  # 🔥 原有的融合关键词名
        original_four_color_type = data.get('original_four_color_type', '').strip().upper()  # 🔥 原始四色类型
        original_dmt_level = data.get('original_dmt_level', '').strip().upper()  # 🔥 原始DMT层次
        original_perspective = data.get('original_perspective', '').strip()  # 🔥 原始视角说明
        four_color_type = data.get('four_color_type', 'P').strip().upper()  # 用户修改后的四色类型
        dmt_level = data.get('dmt_level', 'M').strip().upper()  # 用户修改后的DMT层次
        perspective = data.get('perspective', '').strip()  # 用户修改后的视角说明
        use_relay = data.get('useRelay', True)  # 单独重做只支持小模型

        if not keyword1 or not keyword2 or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        # 验证四色和DMT
        if four_color_type not in ['R', 'B', 'P', 'G']:
            four_color_type = 'P'
        if dmt_level not in ['D', 'M', 'T']:
            dmt_level = 'M'

        # 获取场景信息和本子描述
        scene_summary_info = None
        notebook_desc = ""
        if scene_name:
            scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, sub_scene_name)
            notebook_desc = get_notebook_description(username, scene_name)
            final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
        else:
            final_scene_summary = None

        # 获取代表性卡片
        all_cards = Card.objects.filter(username=username)
        representative_card1 = _select_representative_card(keyword1, username, all_cards)
        representative_card2 = _select_representative_card(keyword2, username, all_cards)

        # 调用单独重做功能
        new_keyword = _regenerate_single_keyword_via_relay(
            keyword1, keyword2, username, final_scene_summary, notebook_desc,
            representative_card1, representative_card2,
            original_keyword, original_four_color_type, original_dmt_level, original_perspective,
            four_color_type, dmt_level, perspective
        )

        if not new_keyword:
            return JsonResponse({
                'error_num': 1,
                'msg': '重新生成关键词失败'
            })

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'keyword': new_keyword
        })

    except Exception as e:
        print(f"[regenerate_single_fuse_keyword] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'重新生成失败: {str(e)}'
        })


def _regenerate_single_keyword_via_relay(keyword1, keyword2, username, final_scene_summary, notebook_desc,
                                         representative_card1, representative_card2,
                                         original_keyword, original_four_color_type, original_dmt_level,
                                         original_perspective,
                                         four_color_type, dmt_level, perspective):
    """
    通过中转服务器调用8卡服务器小模型，单独重新生成某个融合关键词选项的关键词名
    基于原有的融合关键词名、原始属性和用户修改后的属性，分析用户修改意图，生成改进后的关键词名
    """
    try:
        import requests
        import json

        # 构建Prompt（system_prompt已在PEFTmodel.py中定义，这里只提供user_prompt）
        # 🔥 基于原有的融合关键词名，对比原始属性和用户修改后的属性，分析用户修改意图，生成改进后的关键词名

        # 根据四色类型生成具体说明
        four_color_desc_map = {
            'R': '专业业务语言，明确的专业术语、行业规范',
            'B': '技术工具语言，具体的技术工具、可操作方法',
            'P': '场景思维语言，逻辑思维、系统性推演、方法论框架',
            'G': '自然语言，简单易懂且深刻的自然表达'
        }
        original_four_color_desc = four_color_desc_map.get(original_four_color_type, '')
        four_color_desc = four_color_desc_map.get(four_color_type, '')

        # 根据DMT层次生成具体说明
        dmt_desc_map = {
            'D': '具象具体，可直接执行的操作',
            'M': '中等抽象程度，连接过渡、分类组织',
            'T': '偏思维性的框架，具有可向下击穿性'
        }
        original_dmt_desc = dmt_desc_map.get(original_dmt_level, '')
        dmt_desc = dmt_desc_map.get(dmt_level, '')

        # 🔥 分析用户的修改意图
        modifications = []
        modification_intentions = []

        # 分析四色类型变化
        if original_four_color_type and original_four_color_type != four_color_type:
            modifications.append(
                f"四色类型：从{original_four_color_type}（{original_four_color_desc}）改为{four_color_type}（{four_color_desc}）")
            modification_intentions.append(
                f"用户希望关键词从'{original_four_color_desc}'转向'{four_color_desc}'，这表明用户希望强调不同的语言特征和表达方式")

        # 分析DMT层次变化
        if original_dmt_level and original_dmt_level != dmt_level:
            modifications.append(f"DMT层次：从{original_dmt_level}（{original_dmt_desc}）改为{dmt_level}（{dmt_desc}）")
            modification_intentions.append(f"用户希望关键词从'{original_dmt_desc}'转向'{dmt_desc}'，这表明用户希望调整关键词的抽象程度和具体性")

        # 分析视角说明变化（重点分析）
        if original_perspective and original_perspective.strip() != perspective.strip():
            modifications.append(f"视角说明：从「{original_perspective}」改为「{perspective}」")
            # 尝试分析视角的核心改动
            perspective_change_analysis = f"视角说明的核心改动："
            # 找出新增的关键词或概念
            original_words = set(original_perspective.split())
            new_words = set(perspective.split())
            added_words = new_words - original_words
            removed_words = original_words - new_words

            if added_words:
                perspective_change_analysis += f"新增了关键概念：{', '.join(added_words)}；"
            if removed_words:
                perspective_change_analysis += f"移除了概念：{', '.join(removed_words)}；"
            perspective_change_analysis += f"这体现了用户希望在新关键词中强调的方向性变化。"
            modification_intentions.append(perspective_change_analysis)

        # 构建用户修改说明
        modification_text = ""
        if modifications:
            modification_text = "\n\n**用户的具体修改：**\n" + "\n".join([f"- {m}" for m in modifications])

        intention_text = ""
        if modification_intentions:
            intention_text = "\n\n**用户修改的意图分析（请深入理解）：**\n" + "\n".join([f"- {i}" for i in modification_intentions])

        user_prompt = f"""**⚠️ 用户对之前生成的融合关键词名"{original_keyword}"不满意，通过调整属性来引导改进。请基于原有关键词名，深入理解用户的修改意图，生成一个改进后的关键词名。**

**原有的融合关键词名（作为参照和改进基础）：**"{original_keyword}"

**原始属性（作为对比基准）：**
- 原始四色类型：{original_four_color_type}（{original_four_color_desc}）
- 原始DMT层次：{original_dmt_level}（{original_dmt_desc}）
- 原始视角说明：{original_perspective if original_perspective else '（无）'}

**用户修改后的属性（必须严格遵循）：**
1. **四色类型：{four_color_type}**（{four_color_desc}）
2. **DMT层次：{dmt_level}**（{dmt_desc}）
3. **视角说明：{perspective}**
{modification_text}
{intention_text}

**核心要求**：
- 基于原有的融合关键词名"{original_keyword}"进行有指向的明显改进，而不是完全重新生成
- **特别重要**：深入理解用户修改视角说明的意图，将视角说明中的核心改动（新增的概念、强调的方向等）明显体现在新的关键词名中
- 同时，**必须保留**原有关键词名中的关键信息，不能丢失原有部分的重要内涵
- 新的关键词名必须**严格符合**修改后的四色类型特征：{four_color_desc}
- 新的关键词名必须**严格符合**修改后的DMT层次特征：{dmt_desc}
- 新的关键词名必须**明显体现**修改后的视角说明：{perspective}
- 新关键词名应该在保持原有内涵的基础上，根据用户的属性调整和视角改动，变得更加自洽自然、精准得体、有价值
- 要基于两个原关键词"{keyword1}"和"{keyword2}"，结合下方代表性卡片信息进行改进
- 要揣摩用户为何要这样修改（可能的原因：希望更准确地表达意图、希望强调不同的维度、希望调整抽象程度等）
- **字数要求**：不要被原关键词"{original_keyword}"的字数限制，根据改进需要可以自然地增加字数（最多不超过8字），但要确保是有指向的、自然自洽的、精准提升的

请生成**1个**（只生成1个，不要3个）基于原有关键词名改进后的新关键词名。"""

        # 添加代表性卡片内容到prompt中
        card_info_section = ""
        if representative_card1:
            card_info_section += f"\n\n## 关键词\"{keyword1}\"的代表性卡片：\n"
            card_info_section += f"标题：{representative_card1.title or ''}\n"
            card_info_section += f"内容：{(representative_card1.content or '')[:800]}\n"
            if representative_card1.four_color_type:
                card_info_section += f"四色类型：{representative_card1.four_color_type}\n"
            if representative_card1.dmt_level:
                card_info_section += f"DMT层次：{representative_card1.dmt_level}\n"
            score1 = float(representative_card1.score) if representative_card1.score else 0
            scoreSFT1 = float(representative_card1.scoreSFT) if representative_card1.scoreSFT else 0
            weighted_score1 = score1 * 0.3 + scoreSFT1 * 0.7
            card_info_section += f"综合得分：{weighted_score1:.2f}\n"

        if representative_card2:
            card_info_section += f"\n\n## 关键词\"{keyword2}\"的代表性卡片：\n"
            card_info_section += f"标题：{representative_card2.title or ''}\n"
            card_info_section += f"内容：{(representative_card2.content or '')[:800]}\n"
            if representative_card2.four_color_type:
                card_info_section += f"四色类型：{representative_card2.four_color_type}\n"
            if representative_card2.dmt_level:
                card_info_section += f"DMT层次：{representative_card2.dmt_level}\n"
            score2 = float(representative_card2.score) if representative_card2.score else 0
            scoreSFT2 = float(representative_card2.scoreSFT) if representative_card2.scoreSFT else 0
            weighted_score2 = score2 * 0.3 + scoreSFT2 * 0.7
            card_info_section += f"综合得分：{weighted_score2:.2f}\n"

        # 将代表性卡片信息添加到user_prompt
        full_input_text = user_prompt + card_info_section

        # 处理特殊字符（与get_depth_suggestion格式保持一致）
        full_input_text = full_input_text.replace("\n", "\\n")
        full_input_text = full_input_text.replace('```', '').replace('"""', '').replace('"', '“').replace("'", '‘')

        # 构造请求数据
        request_data = {
            "input_text": full_input_text,
            # "user_name": username.split('_')[0] if '_' in username else username,
            "user_name": username,
            "task_type": "keyword_fusion_single"  # 使用单独重做的任务类型
        }

        # 使用requests库发送POST请求
        server_url = get_small_model_server_url(username)
        response = requests.post(
            f'{server_url}/get_depth_suggestion',
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=120
        )

        # 检查HTTP状态码
        if response.status_code != 200:
            print(f"[_regenerate_single_keyword_via_relay] HTTP请求失败，状态码: {response.status_code}")
            try:
                print(f"[_regenerate_single_keyword_via_relay] 响应内容: {response.text[:500]}")
            except:
                pass
            return None

        # 解析返回结果
        try:
            result_data = response.json()
        except Exception as e:
            print(f"[_regenerate_single_keyword_via_relay] JSON解析失败: {e}")
            try:
                print(f"[_regenerate_single_keyword_via_relay] 响应内容: {response.text[:500]}")
            except:
                pass
            return None

        if result_data.get('error_num') != 0:
            print(f"[_regenerate_single_keyword_via_relay] 生成失败: {result_data.get('message', '未知错误')}")
            return None

        response_content = result_data.get('suggestion', '')

        if not response_content or len(response_content.strip()) < 10:
            print(f"[_regenerate_single_keyword_via_relay] 响应内容过短")
            return None

        # 解析JSON响应（期望返回单个关键词）
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
                    # 如果不是JSON格式，尝试直接提取关键词（可能只返回关键词名）
                    # 清理并返回
                    kw = response_content.strip()
                    kw = re.sub(r'^["\'""]|["\'""]$', '', kw)
                    kw = re.sub(r'[。，、；：！？\s]+$', '', kw)
                    if len(kw) > 0 and len(kw) <= 20:
                        return kw.strip()
                    return None

            result_data = json.loads(json_str)
            # 可能返回 {"keyword": "关键词"} 格式
            new_keyword = result_data.get('keyword', '').strip()

            if not new_keyword:
                return None

            # 清理输出
            new_keyword = re.sub(r'^["\'""]|["\'""]$', '', new_keyword)
            new_keyword = re.sub(r'[。，、；：！？\s]+$', '', new_keyword)
            new_keyword = new_keyword.strip()

            # 验证字数
            word_count = len(re.findall(r'[\u4e00-\u9fa5]', new_keyword))
            alpha_num_count = len(re.findall(r'[a-zA-Z0-9]+', new_keyword))
            total_count = word_count + alpha_num_count

            if total_count <= 9 and len(new_keyword) > 0:
                print(f"[_regenerate_single_keyword_via_relay] 成功生成单个关键词: {new_keyword}")
                return new_keyword
            else:
                print(f"[_regenerate_single_keyword_via_relay] 关键词字数不符合要求: {total_count} (最大允许9字，比Prompt要求宽一点多1字)")
                return None

        except json.JSONDecodeError as e:
            print(f"[_regenerate_single_keyword_via_relay] JSON解析失败: {e}")
            # 如果不是JSON，尝试直接提取关键词
            kw = response_content.strip()
            kw = re.sub(r'^["\'""]|["\'""]$', '', kw)
            kw = re.sub(r'[。，、；：！？\s]+$', '', kw)
            if len(kw) > 0 and len(kw) <= 20:
                return kw.strip()
            return None
        except Exception as e:
            print(f"[_regenerate_single_keyword_via_relay] 解析异常: {e}")
            import traceback
            traceback.print_exc()
            return None

    except requests.exceptions.Timeout:
        print(f"[_regenerate_single_keyword_via_relay] 请求超时")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"[_regenerate_single_keyword_via_relay] 连接错误: {e}")
        return None
    except Exception as e:
        print(f"[_regenerate_single_keyword_via_relay] 生成异常: {e}")
        import traceback
        traceback.print_exc()
        return None


@csrf_exempt
def confirm_fuse_keyword(request):
    """
    🔥 确认融合关键词并生成永久卡片
    根据用户选择的关键词（包含四色DMT属性）生成永久卡片，卡片的四色DMT与关键词一致
    """
    try:
        data = json.loads(request.body)
        selected_keyword = data.get('keyword', '').strip()
        four_color_type = data.get('four_color_type', '').strip().upper()
        dmt_level = data.get('dmt_level', '').strip().upper()
        keyword1 = data.get('keyword1', '').strip()
        keyword2 = data.get('keyword2', '').strip()
        username = data.get('username', '')
        scene_name = data.get('scene_name', '')
        sub_scene_name = data.get('sub_scene_name', '')
        is_group_notebook = data.get('is_group_notebook', False)
        origin_real_name = data.get('origin_real_name', '')

        if not selected_keyword or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        # 验证四色和DMT
        if four_color_type not in ['R', 'B', 'P', 'G']:
            four_color_type = 'P'
        if dmt_level not in ['D', 'M', 'T']:
            dmt_level = 'M'

        # 1. 获取场景信息和本子描述
        scene_summary_info = None
        notebook_desc = ""
        if scene_name:
            scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, sub_scene_name)
            notebook_desc = get_notebook_description(username, scene_name)
            final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
        else:
            final_scene_summary = None

        # 2. 获取最后一个子场景编号
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

        last_sub_scene = sub_scene_name or ""
        last_sub_scene_num = 0
        if scene_name:
            try:
                scene_dir_path = './received_dir/scene_excel/' + scene_name
                prompt_excel_path = os.path.join(scene_dir_path, 'prompt.xlsx')
                if os.path.exists(prompt_excel_path):
                    excel_data = pd.read_excel(prompt_excel_path, sheet_name='LUI1')
                    sub_scene_col = 1
                    if excel_data.shape[1] > sub_scene_col:
                        first_subscene_col_name = excel_data.columns[sub_scene_col]
                        subscene_name_list = excel_data.iloc[:, sub_scene_col].dropna().tolist()
                        subscene_name_list_order = [first_subscene_col_name] + subscene_name_list
                        last_sub_scene_num = len(subscene_name_list_order)
                        if subscene_name_list_order:
                            last_sub_scene = subscene_name_list_order[-1]
            except Exception as e:
                print(f"[confirm_fuse_keyword] 从excel获取子场景信息失败: {e}")

        # 3. 查找包含两个原关键词的相关卡片
        all_cards = Card.objects.filter(username=username)
        cards_with_keyword1 = []
        cards_with_keyword2 = []

        for card in all_cards:
            if not card.keyWords or not card.four_color_type or not card.dmt_level:
                continue
            card_keywords = [k.strip() for k in re.split(r'[,，]', card.keyWords) if k.strip()]
            has_keyword1 = keyword1 in card_keywords
            has_keyword2 = keyword2 in card_keywords

            if has_keyword1 and card not in cards_with_keyword1:
                cards_with_keyword1.append(card)
            if has_keyword2 and card not in cards_with_keyword2:
                cards_with_keyword2.append(card)

        if not cards_with_keyword1:
            return JsonResponse({
                'error_num': 1,
                'msg': f'未找到包含关键词"{keyword1}"的卡片，无法生成永久卡片'
            })
        if not cards_with_keyword2:
            return JsonResponse({
                'error_num': 1,
                'msg': f'未找到包含关键词"{keyword2}"的卡片，无法生成永久卡片'
            })

        # 合并两个列表（去重）
        reference_cards_objs = []
        seen_cids = set()
        for card in cards_with_keyword1 + cards_with_keyword2:
            if card.cid not in seen_cids:
                reference_cards_objs.append(card)
                seen_cids.add(card.cid)

        # 按综合得分排序，最多取5张
        reference_cards_objs.sort(
            key=lambda c: (c.score or 0) * 0.3 + (c.scoreSFT or 0) * 0.7,
            reverse=True
        )
        reference_cards_objs = reference_cards_objs[:5]

        # 转换为字典格式
        reference_cards = []
        card_cids = []
        all_selected_docs = set()

        for card in reference_cards_objs:
            card_cid = str(card.cid) if card.cid else ''
            if card_cid:
                card_cids.append(card_cid)

            card_selected_docs = card.selected_docs if hasattr(card, 'selected_docs') else ''
            docs_list = []
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

            card_dict = {
                'cid': card_cid,
                'content': card.content or '',
                'title': card.title or '',
                'score': card.score or 0,
                'scoreSFT': card.scoreSFT or 0,
                'keyWords': card.keyWords or '',
                'four_color_type': card.four_color_type or '',
                'dmt_level': card.dmt_level or '',
                'selected_docs': docs_list
            }
            reference_cards.append(card_dict)

        # 4. 保存选中关键词的四色DMT属性到数据库（确保已保存）
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                keyword_four_color_dmt = {}
                if notebook.keywordFourColorDMT:
                    try:
                        keyword_four_color_dmt = json.loads(notebook.keywordFourColorDMT)
                    except:
                        keyword_four_color_dmt = {}

                keyword_four_color_dmt[selected_keyword] = {
                    'four_color_type': four_color_type,
                    'dmt_level': dmt_level
                }
                notebook.keywordFourColorDMT = json.dumps(keyword_four_color_dmt, ensure_ascii=False)
                notebook.save()
                print(f"[confirm_fuse_keyword] 保存关键词'{selected_keyword}'的四色DMT属性: {four_color_type}/{dmt_level}")
            except Exception as e:
                print(f"[confirm_fuse_keyword] 保存关键词四色DMT属性失败: {e}")

        # 5. 构建参考卡片信息和QA问题链（与原fuse_keywords逻辑相同）
        reference_cards_info = "\n## 参考卡片内容：\n"
        for idx, card in enumerate(reference_cards, 1):
            combined_score = card['score'] * 0.3 + card['scoreSFT'] * 0.7
            reference_cards_info += f"\n--- 参考卡片 {idx} (CID: {card['cid']}) ---\n"
            reference_cards_info += f"标题：{card['title']}\n"
            reference_cards_info += f"综合得分：{combined_score:.2f}\n"
            reference_cards_info += f"内容：{card['content'][:500]}\n"
            if card['selected_docs']:
                reference_cards_info += f"勾选文档：{', '.join(card['selected_docs'])}\n"

        qa_cards_list = []
        for card in all_cards:
            if not card.keyWords:
                continue
            card_keywords = [k.strip() for k in re.split(r'[,，]', card.keyWords) if k.strip()]
            if keyword1 in card_keywords or keyword2 in card_keywords:
                # 判断是否为QA卡
                is_qa = card.history or (card.content and '提问' in card.content)
                if is_qa:
                    qa_cards_list.append(card)

        qa_cards_list.sort(key=lambda c: c.datetime if c.datetime else '', reverse=False)
        qa_cards = []
        for qa_card in qa_cards_list[:10]:
            question = ""
            if hasattr(qa_card, 'history') and qa_card.history:
                try:
                    history = qa_card.history
                    if isinstance(history, str):
                        history = json.loads(history)
                    if isinstance(history, list) and len(history) > 0:
                        first_msg = history[0]
                        if isinstance(first_msg, dict):
                            question = first_msg.get('content', '')
                except:
                    pass

            if not question and qa_card.content:
                match = re.search(r'提问[：:]\s*([^\n\r]+)', qa_card.content)
                if match:
                    question = match.group(1).strip()

            if question:
                datetime_str = str(qa_card.datetime) if qa_card.datetime else ''
                qa_cards.append({
                    'datetime': datetime_str,
                    'question': question
                })

        qa_questions_chain = ""
        if qa_cards:
            qa_questions_chain = "\n## QA问答卡问题链（按时间顺序）：\n"
            for idx, qa in enumerate(qa_cards):
                qa_questions_chain += f"{idx + 1}. [{qa['datetime']}] {qa['question']}\n"

        # 6. 构建生成永久卡片的Prompt（使用用户选择的关键词，且卡片的四色DMT与关键词一致）
        # 导入generate_permanent_card的完整prompt构建逻辑（简化版，重点突出四色DMT与关键词一致）
        from app_chat.views_generate_permanent_card import generate_permanent_card
        # 这里直接调用generate_permanent_card的prompt构建逻辑，但传入选定的关键词和四色DMT
        # 为了避免重复代码，我们直接复用原fuse_keywords中的prompt构建逻辑

        # 由于代码较长，这里直接调用views_generate_permanent_card中的生成逻辑
        # 但需要修改以确保使用传入的four_color_type和dmt_level

        # 临时方案：直接使用generate_permanent_card的逻辑，但需要修改以传入four_color_type和dmt_level
        # 由于generate_permanent_card不接受four_color_type和dmt_level参数，我们需要创建一个新的调用

        # 7. 构建user_prompt（参照原fuse_keywords，但使用selected_keyword和指定的四色DMT）
        user_prompt = f"""你需要基于两个原关键词"{keyword1}"和"{keyword2}"融合生成的新关键词"{selected_keyword}"，生成一张关键词神经元永久卡。

## 场景上下文
- 场景名：{scene_name or '未提供'}
- 子场景：{last_sub_scene}
- 本子描述：{notebook_desc[:300] if notebook_desc else '未提供'}
- 场景摘要：{final_scene_summary[:500] if final_scene_summary else '未提供'}

{qa_questions_chain if qa_questions_chain else ''}

{reference_cards_info}

## 生成要求

### 1. 卡片基本信息
- **contentTitle**：S{last_sub_scene_num}:{selected_keyword}
- **关键词**：{selected_keyword}（这是由"{keyword1}"和"{keyword2}"融合生成的新关键词，必须体现融合内涵和新内涵涌现1+1>2）
- **四色类型**：{four_color_type}（卡片内容应与此四色类型一致）
- **DMT层次**：{dmt_level}（卡片内容应与此DMT层次一致）

### 2. 内容要求（300-500字）
- **原子化**：内容应该是独立完整的概念单元
- **原创化**：必须交叉创造、融合、涌现明显，特别要体现"{keyword1}"和"{keyword2}"的融合
- **可复用化**：内容应该可以在不同场景下复用
- **聚焦主体**：必须聚焦此场景此本子的主体目标
- **具体化**：**严禁空话套话！** 必须具体、有真正认知上的行动指向价值
- **围绕新关键词**：内容必须围绕新关键词"{selected_keyword}"展开
- **四色DMT一致性**：内容必须与指定的四色类型({four_color_type})和DMT层次({dmt_level})保持一致

### 3. 去QA化要求
- 去除QA问答的形式，提取核心观点和概念
- 根据问题链具体分析，引用具体问题内容

### 4. 后置索引（postIndex）
- 必须是参考卡片的CID列表（用逗号分隔）

### 5. 支撑文献来源（sourceReferences）
- **说明**：系统会自动从参考卡片中提取文档列表并解析页数，你只需要在JSON中返回格式化的字符串即可（如果系统未提供，可返回"无"）
- **格式要求**（如果系统提供了文档列表）：必须使用1/2/3标号，每个文档换行，格式为"1. 文档名（第X页）"或"1. 文档名（第X-Y页）"
- **示例格式**：
  1. 文档1.pdf（第10页）
  2. 文档2.txt（第15-20页）
  3. 文档3.pdf（第5页）

### 6. 结尾要求
- 必须显式标识人/机认知比例（人的部分不超过50%）
- 必须用一段话（50-100字，不可少于50字，不可超过100字）精准详细地总结为什么可以得出这样的人机认知比例结论

### 7. 内容格式要求
- 开头至少100字深入解释关键词原意，中间50-100字说明与其他概念的关联涌现
- **格式要求**：开头&中间部分一体，与后续部分之间要用三个连字符"---"分隔
- 后续篇幅必须具体引用问题链中的具体问题，体现使用者本身的认知推进情况

## 输出格式

请严格按照以下JSON格式输出：

```json
{{
    "contentTitle": "S{last_sub_scene_num}:{selected_keyword}",
    "content": "生成的卡片内容（300-500字，必须具体，体现'{keyword1}'和'{keyword2}'的融合内涵和新内涵涌现1+1>2，且与四色类型{four_color_type}和DMT层次{dmt_level}保持一致，开头至少100字深入解释关键词原意，中间50-100字说明与其他概念的关联涌现，开头&中间部分一体，与后续部分之间用---分隔，后续篇幅必须具体引用问题链中的具体问题）",
    "postIndex": "{','.join(card_cids) if card_cids else ''}",
    "sourceReferences": "支撑文献来源，格式为1/2/3标号换行（最多3个，至少1个），每个文档需包含页数",
    "humanMachineRatio": "人机认知比例，例如：3:7 或 4:6 等等（人的部分不超过50%）",
    "conclusionReason": "为什么可以得出这样的人机认知比例结论（50-100字，不可少于50字，不可超过100字）"
}}
```
"""

        # 8. 调用LLM生成卡片内容（使用claude-4-sonnet，失败则升级到claude-sonnet-4.5，再失败则降级到claude-3.7）
        content_model_priority = ['claude-sonnet-4.5', 'claude-sonnet-4.5', 'claude-sonnet-4.5']
        content_model_name = None
        model_id = None
        response_content = None
        card_data = None

        system_prompt = "你是专业的知识卡片生成专家，擅长基于关键词和相关卡片内容，生成原子化、原创化、可复用化的永久卡片。"

        # JSON解析函数（复用原fuse_keywords的逻辑）
        # 🔥 定义转义JSON字符串中未转义双引号的函数（在parse_json_response外部定义，以便复用）
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
                # 应用修复（使用外部定义的函数）
                json_str = escape_quotes_in_json_string(json_str)

                # 解析JSON（允许处理换行符等）
                card_data = json.loads(json_str)
                return card_data, True
            except Exception as e:
                print(f"[fuse_keywords] JSON解析失败: {e}")
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

                        # 🔥 修复未转义的英文双引号（复用上面的函数）
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
                            print(f"[fuse_keywords] 使用宽松解析成功")
                            return card_data, True
                        except:
                            # 如果还是失败，尝试更激进的方法：只提取已知字段
                            card_data = {}
                            # 尝试提取各个字段（正确处理转义的引号）
                            for field in ['contentTitle', 'content', 'postIndex', 'sourceReferences',
                                          'humanMachineRatio', 'conclusionReason']:
                                # 🔥 使用能正确处理转义引号的正则表达式
                                # 匹配：字段名后跟冒号，然后匹配引号内的内容（包括转义的引号和反斜杠）
                                # (?:[^"\\]|\\.)* 匹配：非引号非反斜杠字符，或反斜杠后跟任意字符（包括转义的引号）
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
                                print(f"[fuse_keywords] 使用字段提取解析成功")
                                return card_data, True
                            raise e
                    else:
                        raise e
                except Exception as e2:
                    print(f"[fuse_keywords] 宽松解析也失败: {e2}")
                    print(f"[fuse_keywords] 响应内容: {response_content[:1000]}")  # 打印前1000字符用于调试
                    return None, False

        for content_model_name in content_model_priority:
            try:
                model_config = config_manager.get_model_config(content_model_name)
                if not model_config:
                    continue

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

                if response_content and len(response_content.strip()) > 100:
                    card_data, success = parse_json_response(response_content)
                    if success and card_data:
                        model_id = model_config.get_model_id()
                        print(f"[confirm_fuse_keyword] 使用{content_model_name}成功生成永久卡片内容")
                        break
            except Exception as e:
                print(f"[confirm_fuse_keyword] 使用{content_model_name}生成永久卡片失败: {e}")
                continue

        if not card_data:
            return JsonResponse({
                'error_num': 1,
                'msg': '生成永久卡片内容失败'
            })

        # 9. 处理postIndex
        post_index_value = card_data.get('postIndex', '')
        if not post_index_value and card_cids:
            post_index_value = ','.join(card_cids)

        # 10. 获取支撑文献来源（新旧策略融合）
        from app_chat.views_generate_permanent_card import _find_documents_by_keyword, _analyze_human_machine_ratio, \
            _parse_page_ranges_for_docs, _sample_words_from_cards

        # 10.1 旧策略：从参考卡片的selected_docs中提取文档列表（也包括从history中提取）
        doc_names_from_cards = []
        if all_selected_docs:
            doc_names_from_cards = list(all_selected_docs)
            print(f"[confirm_fuse_keyword] 旧策略找到{len(doc_names_from_cards)}个文档: {doc_names_from_cards}")
        else:
            # 尝试从参考卡片的history中提取文档列表
            for card in reference_cards_objs:
                card_history = getattr(card, 'history', None)
                if card_history:
                    try:
                        if isinstance(card_history, str):
                            history = json.loads(card_history)
                        else:
                            history = card_history

                        history_data = None
                        if history and isinstance(history, dict) and history.get('data') and isinstance(history['data'],
                                                                                                        list):
                            history_data = history['data']
                        elif isinstance(history, list):
                            history_data = history

                        if history_data and isinstance(history_data, list):
                            for data_item in history_data:
                                if isinstance(data_item, dict) and data_item.get('filelist'):
                                    filelist = data_item['filelist']
                                    if isinstance(filelist, list):
                                        for file_name in filelist:
                                            if file_name:
                                                all_selected_docs.add(file_name)
                    except Exception as e:
                        print(f"[confirm_fuse_keyword] 从history提取文件列表失败: {e}")

            if all_selected_docs:
                doc_names_from_cards = list(all_selected_docs)
                print(f"[confirm_fuse_keyword] 旧策略（从history）找到{len(doc_names_from_cards)}个文档: {doc_names_from_cards}")

        # 10.2 如果旧策略为空，使用新策略：根据关键词从pre_summary查找文档
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
                new_strategy_docs = _find_documents_by_keyword(selected_keyword, username, max_count=3, min_count=1)
                print(f"[confirm_fuse_keyword] 旧策略找到{len(doc_names_from_cards)}个文档（>3），先用新策略查找: {new_strategy_docs}")

                if new_strategy_docs:
                    # 尝试解析页码（包括15次采样）
                    test_page_ranges = _parse_page_ranges_for_docs(new_strategy_docs, selected_keyword, username,
                                                                   reference_cards=reference_cards_objs)
                    # 检查是否有至少一个文档能找到页码
                    has_valid_page = any(page_ranges is not None for _, page_ranges in test_page_ranges)

                    if has_valid_page:
                        # 新策略找到的文档能解析出页码，使用新策略（保存已解析的结果）
                        final_doc_names = new_strategy_docs
                        doc_page_ranges = test_page_ranges  # 直接使用已解析的结果，避免重复解析
                        print(f"[confirm_fuse_keyword] 新策略找到的文档能解析出页码，使用新策略结果: {final_doc_names}")
                    else:
                        # 新策略找到的文档经过15次采样都找不到页码，回退到均匀抽取
                        final_doc_names = uniformly_sample_docs(doc_names_from_cards)
                        print(f"[confirm_fuse_keyword] 新策略找到的文档无法解析页码，回退到均匀抽取: {final_doc_names}")
                else:
                    # 新策略没有找到文档，回退到均匀抽取
                    final_doc_names = uniformly_sample_docs(doc_names_from_cards)
                    print(f"[confirm_fuse_keyword] 新策略未找到文档，回退到均匀抽取: {final_doc_names}")
            else:
                final_doc_names = doc_names_from_cards  # 3个或更少，全部使用
        else:
            # 新策略：从pre_summary目录根据关键词查找
            final_doc_names = _find_documents_by_keyword(selected_keyword, username, max_count=3, min_count=1)
            print(f"[confirm_fuse_keyword] 旧策略为空，新策略找到{len(final_doc_names)}个文档: {final_doc_names}")

        # 10.3 对最终文档列表解析页数（传入参考卡片用于采样词汇）
        if final_doc_names:
            # 如果之前在新策略测试时已经解析过，直接使用；否则现在解析
            if doc_page_ranges is None:
                doc_page_ranges = _parse_page_ranges_for_docs(final_doc_names, selected_keyword, username,
                                                              reference_cards=reference_cards_objs)
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

        # 11. 分析人机认知比例（使用辅助函数）
        # 准备参考卡片对象列表（用于分析）
        reference_cards_for_ratio = []
        for card in reference_cards_objs:
            card_dict = {
                'is_neuron': getattr(card, 'is_neuron', False),
                'type': getattr(card, 'type', '') or '',
                'score': getattr(card, 'score', 0) or 0,
                'scoreSFT': getattr(card, 'scoreSFT', 0) or 0,
                'color': getattr(card, 'color', '') or '',
                'content': getattr(card, 'content', '') or ''
            }
            reference_cards_for_ratio.append(card_dict)

        # 准备QA卡片列表（用于分析）
        qa_cards_for_ratio = []
        for qa_card in qa_cards:
            if isinstance(qa_card, dict):
                qa_cards_for_ratio.append(qa_card)

        human_machine_ratio = _analyze_human_machine_ratio(qa_cards_for_ratio, reference_cards_for_ratio, notebook_desc)

        # 如果LLM生成的人机认知比例存在，优先使用LLM生成的（但如果格式不对，使用我们分析的）
        if card_data.get('humanMachineRatio'):
            llm_ratio = card_data.get('humanMachineRatio', '').strip()
            if llm_ratio:
                human_machine_ratio = llm_ratio

        conclusion_reason = card_data.get('conclusionReason', '').strip()

        # 12. 构建完整的卡片内容（先构建，用于评分）
        content_body = card_data.get('content', '').strip()

        # 确保开头&中间部分（一体）与后续部分之间有---分隔符（如果LLM没有添加的话）
        if '---' not in content_body:
            # 尝试在开头&中间部分（约150-200字）之后，与后续部分之间添加---分隔符
            if len(content_body) > 150:
                insert_pos = -1
                # 在150-200字之间查找句号或换行，在其后插入---（分隔开头&中间部分与后续部分）
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

        # 11. 并发执行打分和红蓝评测
        async def score_and_evaluate():
            async def get_score():
                try:
                    score, color, reason = await asyncio.wait_for(
                        to_thread(red_bule_rate.get_rate, username, full_content),
                        timeout=30.0
                    )
                    return {'error_num': 0, 'score': score, 'color': color, 'reason': reason}
                except:
                    return {'error_num': 0, 'score': 4.0, 'color': '紫', 'reason': '永久卡片（原子化&原创化&可复用化）'}

            async def get_evalSFT():
                try:
                    text = full_content.replace("\n", "\\n")
                    # command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","text":"{text}"}}\' http://localhost:8000/invoke_rate'
                    server_url = get_small_model_server_url(username)
                    command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","text":"{text}"}}\' {server_url}/invoke_rate'
                    result = await asyncio.wait_for(
                        to_thread(subprocess.run, command, shell=True, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True),
                        timeout=30.0
                    )
                    data_str = result.stdout.strip()
                    if data_str.startswith('"') and data_str.endswith('"'):
                        data_str = data_str[1:-1]
                    data_str = data_str.replace('\\"', '"').replace('\\\\', '\\')
                    result_object = json.loads(data_str)
                    decoded_result = result_object.get('result', '')
                    if decoded_result and decoded_result != "fail":
                        scoreSFT = float(extract_number_SFT(decoded_result)) if extract_number_SFT(
                            decoded_result) is not None else 4.0
                        colorSFT = extract_color_SFT(decoded_result) or "紫"
                        reasonSFT = extract_reason_SFT(decoded_result) or "永久卡片（原子化&原创化&可复用化）"
                        if scoreSFT >= 1.0 and colorSFT != "紫":
                            colorSFT = "紫"
                        return {'error_num': 0, 'scoreSFT': scoreSFT, 'colorSFT': colorSFT, 'reasonSFT': reasonSFT}
                    return {'error_num': 0, 'scoreSFT': 4.0, 'colorSFT': '紫', 'reasonSFT': '永久卡片（原子化&原创化&可复用化）'}
                except:
                    return {'error_num': 0, 'scoreSFT': 4.0, 'colorSFT': '紫', 'reasonSFT': '永久卡片（原子化&原创化&可复用化）'}

            score_result, eval_result = await asyncio.gather(get_score(), get_evalSFT(), return_exceptions=True)
            if isinstance(score_result, Exception):
                score_result = {'error_num': 0, 'score': 4.0, 'color': '紫', 'reason': '永久卡片（原子化&原创化&可复用化）'}
            if isinstance(eval_result, Exception):
                eval_result = {'error_num': 0, 'scoreSFT': 4.0, 'colorSFT': '紫', 'reasonSFT': '永久卡片（原子化&原创化&可复用化）'}
            return score_result, eval_result

        try:
            loop = asyncio.new_event_loop()
            score_result, eval_result = loop.run_until_complete(score_and_evaluate())
            loop.close()
        except Exception as e:
            print(f"[confirm_fuse_keyword] 并发执行评分失败: {e}")
            score_result = {'error_num': 0, 'score': 4.0, 'color': '紫', 'reason': '永久卡片（原子化&原创化&可复用化）'}
            eval_result = {'error_num': 0, 'scoreSFT': 4.0, 'colorSFT': '紫', 'reasonSFT': '永久卡片（原子化&原创化&可复用化）'}

        score = score_result.get('score', 4.0)
        color = score_result.get('color', '紫')
        reason = score_result.get('reason', '永久卡片（原子化&原创化&可复用化）')
        scoreSFT = eval_result.get('scoreSFT', 4.0)
        colorSFT = eval_result.get('colorSFT', '紫')
        reasonSFT = eval_result.get('reasonSFT', '永久卡片（原子化&原创化&可复用化）')

        # 12. 处理contentTitle
        content_title = card_data.get('contentTitle', f"S{last_sub_scene_num}:{selected_keyword}")
        if not content_title.startswith(f"S{last_sub_scene_num}:"):
            content_title = f"S{last_sub_scene_num}:{selected_keyword}"

        # 13. 保存或更新永久卡片（使用用户指定的four_color_type和dmt_level）
        existing_card = None
        try:
            existing_card = Card.objects.get(
                username=username,
                title="关键词神经元永久卡",
                keyWords=selected_keyword
            )
        except Card.DoesNotExist:
            existing_card = None
        except Card.MultipleObjectsReturned:
            existing_card = Card.objects.filter(
                username=username,
                title="关键词神经元永久卡",
                keyWords=selected_keyword
            ).order_by('-datetime').first()

        if existing_card:
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
            existing_card.four_color_type = four_color_type  # 🔥 使用用户指定的四色类型
            existing_card.dmt_level = dmt_level  # 🔥 使用用户指定的DMT层次
            existing_card.is_analyzed_by_new_standard = True
            existing_card.save()
            new_card = existing_card
        else:
            new_card = Card.objects.create(
                username=username,
                model_id=model_id or "1126",
                status="0",
                content=full_content,
                title="关键词神经元永久卡",
                score=score,
                scoreSFT=scoreSFT,
                color=color,
                colorSFT=colorSFT,
                reason=reason,
                reasonSFT=reasonSFT,
                keyWords=selected_keyword,
                contentTitle=content_title,
                type="永久",
                postIndex=post_index_value,
                four_color_type=four_color_type,  # 🔥 使用用户指定的四色类型
                dmt_level=dmt_level,  # 🔥 使用用户指定的DMT层次
                is_analyzed_by_new_standard=True
            )

        # 14. 更新融合关系（使用字典格式，以融合关键词为key）
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                fusion_relations = {}
                if notebook.keywordFusionRelations:
                    try:
                        fusion_relations = json.loads(notebook.keywordFusionRelations)
                        # 确保是字典格式
                        if not isinstance(fusion_relations, dict):
                            fusion_relations = {}
                    except:
                        fusion_relations = {}

                # 检查是否已存在（检查融合关键词是否已存在）
                if selected_keyword not in fusion_relations:
                    fusion_relations[selected_keyword] = {
                        'source_keywords': [keyword1, keyword2]
                    }
                    notebook.keywordFusionRelations = json.dumps(fusion_relations, ensure_ascii=False)
                    notebook.save()
                    print(f"[confirm_fuse_keyword] 成功保存融合关系: {selected_keyword} <- [{keyword1}, {keyword2}]")
                else:
                    print(f"[confirm_fuse_keyword] 融合关系已存在: {selected_keyword}")
            except Exception as e:
                print(f"[confirm_fuse_keyword] 保存融合关系失败: {e}")
                import traceback
                traceback.print_exc()

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'fused_keyword': selected_keyword,
            'card_id': new_card.cid
        })

    except Exception as e:
        print(f"[confirm_fuse_keyword] 错误-: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'生成永久卡片失败: {str(e)}'
        })