# encoding=utf-8
"""
🔥 更新关键词神经元永久卡（基于关键词修改）
"""
import json
import os
import pandas as pd
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from app_chat.models import Card
from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
from zym.models import scene, UserNotebook
from app_chat.config.config_manager import config_manager
from openai import OpenAI


@csrf_exempt
def update_permanent_card_by_keyword(old_keyword, new_keyword, username, scene_name, sub_scene_name,
                                     permanent_card_cid=None):
    """
    🔥 更新关键词神经元永久卡（当关键词被修改时）

    参数:
        old_keyword: 旧关键词
        new_keyword: 新关键词
        username: 用户名
        scene_name: 场景名
        sub_scene_name: 子场景名
        permanent_card_cid: 永久卡的CID（可选，如果提供则直接使用CID查找）

    返回:
        dict: {'success': bool, 'msg': str, 'card_id': str or None}
    """
    import re
    try:
        # 1. 查找对应的永久卡
        permanent_card = None
        if permanent_card_cid:
            # 🔥 优先使用CID查找（因为keyWords可能已经被更新）
            try:
                permanent_card = Card.objects.get(cid=permanent_card_cid, username=username, title="关键词神经元永久卡")
            except Card.DoesNotExist:
                print(f"[update_permanent_card_by_keyword] 通过CID={permanent_card_cid}未找到永久卡")
        else:
            # 使用keyWords查找（兼容旧调用方式）
            try:
                permanent_card = Card.objects.get(
                    username=username,
                    title="关键词神经元永久卡",
                    keyWords=old_keyword
                )
            except Card.DoesNotExist:
                pass
            except Card.MultipleObjectsReturned:
                permanent_card = Card.objects.filter(
                    username=username,
                    title="关键词神经元永久卡",
                    keyWords=old_keyword
                ).order_by('-datetime').first()

        if not permanent_card:
            print(f"[update_permanent_card_by_keyword] 未找到关键词'{old_keyword}'对应的永久卡")
            return {'success': False, 'msg': '未找到对应的永久卡', 'card_id': None}

        # 2. 获取场景信息和本子描述
        scene_summary_info = None
        notebook_desc = ""
        if scene_name:
            scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, sub_scene_name)
            notebook_desc = get_notebook_description(username, scene_name)
            final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
        else:
            final_scene_summary = None

        # 3. 获取最后一个子场景编号（用于contentTitle）
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
            except Exception as e:
                print(f"[update_permanent_card_by_keyword] 从excel获取子场景信息失败: {e}")

        # 4. 获取参考卡片（包含新关键词的卡片，四色DMT属性，综合得分≥3.5，最多5张）
        # 🔥 使用精确匹配（关键词用逗号分隔，需要匹配完整的关键词）
        all_cards = Card.objects.filter(username=username)
        cards_with_keyword = []
        for card in all_cards:
            if not card.keyWords:
                continue
            # 分割关键词并精确匹配
            keywords = re.split(r'[,，]', card.keyWords)
            keywords_clean = [kw.strip() for kw in keywords]
            if new_keyword in keywords_clean:
                cards_with_keyword.append(card)

        print(f"[update_permanent_card_by_keyword] 找到包含关键词'{new_keyword}'的卡片数量: {len(cards_with_keyword)}")

        # 筛选：有四色DMT属性，且是绿色/紫色/红蓝深评综合得分≥3.5
        reference_cards = []
        for card in cards_with_keyword:
            if not (card.four_color_type and card.dmt_level):
                continue

            # 计算综合得分
            score = float(card.score) if card.score else 0
            scoreSFT = float(card.scoreSFT) if card.scoreSFT else 0
            combined_score = score * 0.3 + scoreSFT * 0.7

            if combined_score >= 3.5:
                reference_cards.append(card)

        print(f"[update_permanent_card_by_keyword] 筛选后符合要求的卡片数量: {len(reference_cards)}")

        # 排序：优先QA问答卡（按datetime），然后按综合得分降序
        qa_cards = []
        other_cards = []
        for card in reference_cards:
            # 判断是否是QA问答卡（根据contentTitle或content中包含"提问"等）
            is_qa = False
            if card.contentTitle and ('S' in card.contentTitle or '提问' in (card.content or '')):
                is_qa = True

            if is_qa:
                qa_cards.append(card)
            else:
                other_cards.append(card)

        # QA卡按datetime排序
        qa_cards.sort(key=lambda x: x.datetime or '')
        # 其他卡按综合得分降序
        other_cards.sort(
            key=lambda x: (float(x.score) if x.score else 0) * 0.3 + (float(x.scoreSFT) if x.scoreSFT else 0) * 0.7,
            reverse=True)

        # 合并，最多5张
        final_reference_cards = (qa_cards + other_cards)[:5]

        print(f"[update_permanent_card_by_keyword] 最终选择的参考卡片数量: {len(final_reference_cards)}")

        # 🔥 如果没有严格符合要求的参考卡片，使用相对可接受的卡片作为后备
        if not final_reference_cards:
            print(f"[update_permanent_card_by_keyword] 未找到严格符合要求的参考卡片，尝试使用后备方案")
            # 后备：只要包含新关键词且有四色DMT属性的卡片（不要求得分）
            fallback_cards = []
            for card in cards_with_keyword:
                if card.four_color_type and card.dmt_level:
                    fallback_cards.append(card)

            if fallback_cards:
                # 按得分降序排序，取前5张
                fallback_cards.sort(key=lambda x: (float(x.score) if x.score else 0) * 0.3 + (
                    float(x.scoreSFT) if x.scoreSFT else 0) * 0.7, reverse=True)
                final_reference_cards = fallback_cards[:5]
                print(f"[update_permanent_card_by_keyword] 使用后备卡片，数量: {len(final_reference_cards)}")
            else:
                print(f"[update_permanent_card_by_keyword] 未找到符合要求的参考卡片（包括后备）")
                return {'success': False, 'msg': '未找到符合要求的参考卡片', 'card_id': None}

        # 5. 构建参考卡片信息
        reference_cards_info = "\n## 参考卡片内容：\n"
        card_cids = []
        all_selected_docs = set()

        for idx, card in enumerate(final_reference_cards):
            card_cids.append(str(card.cid))

            # 收集selected_docs
            docs_list = []
            if card.selected_docs:
                try:
                    if isinstance(card.selected_docs, str):
                        docs_list = json.loads(card.selected_docs)
                    else:
                        docs_list = card.selected_docs
                    if isinstance(docs_list, list):
                        all_selected_docs.update(docs_list)
                except:
                    pass

            # 从history提取
            if not docs_list and card.history:
                try:
                    history = json.loads(card.history) if isinstance(card.history, str) else card.history
                    history_data = history.get('data') if isinstance(history, dict) else history
                    if isinstance(history_data, list):
                        file_set = set()
                        for item in history_data:
                            if isinstance(item, dict) and item.get('filelist'):
                                for f in item['filelist']:
                                    if f:
                                        file_set.add(f)
                        if file_set:
                            docs_list = list(file_set)
                            all_selected_docs.update(docs_list)
                except:
                    pass

            score = float(card.score) if card.score else 0
            scoreSFT = float(card.scoreSFT) if card.scoreSFT else 0
            combined_score = score * 0.3 + scoreSFT * 0.7

            reference_cards_info += f"\n--- 参考卡片 {idx + 1} (CID: {card.cid}) ---\n"
            reference_cards_info += f"标题：{card.title or ''}\n"
            reference_cards_info += f"综合得分：{combined_score:.2f} (score={score}×0.3 + scoreSFT={scoreSFT}×0.7)\n"
            reference_cards_info += f"内容：{card.content or ''}\n"
            if docs_list:
                reference_cards_info += f"勾选文档：{', '.join(docs_list)}\n"

        # 6. 构建QA问题链
        qa_questions_chain = "\n## QA问答卡问题链（按时间顺序）：\n"
        for idx, qa_card in enumerate(qa_cards[:5]):  # 最多5张QA卡
            # 提取问题
            question = ""
            if qa_card.history:
                try:
                    history = json.loads(qa_card.history) if isinstance(qa_card.history, str) else qa_card.history
                    history_data = history.get('data') if isinstance(history, dict) else history
                    if isinstance(history_data, list) and len(history_data) > 0:
                        first_msg = history_data[0]
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
                qa_questions_chain += f"{idx + 1}. [{datetime_str}] {question}\n"

        # 7. 构建Prompt（专门的修改Prompt）
        system_prompt = "你是专业的知识卡片修改专家，擅长基于关键词修改来精准调整永久卡片内容。"

        # 获取原有内容的修改次数（通过检查<第n次修改内容>标签）
        existing_content = permanent_card.content or ''
        max_modify_count = 0
        matches = re.findall(r'<第(\d+)次修改内容>', existing_content)
        if matches:
            max_modify_count = max([int(m) for m in matches])

        next_modify_count = max_modify_count + 1

        user_prompt = f"""你需要基于关键词从"{old_keyword}"修改为"{new_keyword}"这一用户操作，对现有关键词神经元永久卡的内容进行精准修改。

## 核心理解要求

**关键任务**：这不是重新生成，而是**基于现有内容进行精准修改**。

**修改动机分析**（最重要！）：
- 用户将关键词从"{old_keyword}"改为"{new_keyword}"，这一行为体现了用户的主体性认知
- **你必须深入思考：用户为什么要这样修改？本意和目的是什么？**
  - 是概念更精准？是范围扩大/缩小？是视角转变？是理解深化？
  - 这个修改体现了用户对关键词理解的哪些变化？认知层次是否提升？
- **基于这个理解，再来修改内容，会更加精准精炼且思维深刻**

## 现有卡片内容

**contentTitle**：{permanent_card.contentTitle or ''}
**当前内容**：
{existing_content}

## 场景上下文
- 场景名：{scene_name or '未提供'}
- 子场景：{sub_scene_name or '未提供'}
- 本子描述：{notebook_desc[:300] if notebook_desc else '未提供'}
- 场景摘要：{final_scene_summary[:500] if final_scene_summary else '未提供'}

{qa_questions_chain if qa_cards else ''}

{reference_cards_info}

## 修改要求

### 1. 内容修改原则（核心！）
- **基于现有内容修改**，切忌另起炉灶或重新生成
- **保留原有内容**：必须保留所有原有文字和<第n次修改内容>标签，只修改与关键词"{old_keyword}"相关的部分
- **迭代递进**：这是第{next_modify_count}次修改，要基于第1次、第2次...的内容继续深化，不是覆盖重写
- **聚焦精准**：只修改与关键词相关的部分（包括对关键词本身的解释、理解、延展等），其他部分完全保留
- **修改范围**：可以修改前序次改过的段落，也可以修改前序次没改的段落，但要合理自洽、精准精炼
- **修改篇幅**：本次修改的篇幅应该大约占全文的20%左右（上下可灵活浮动5%-10%），不要陷入修改过多或过少的极端（其中一定不可过多！）
- **修改粒度**：每次修改的篇幅要合适，不要大段替换，要精准调整
- **篇幅控制**：修改后整体字数不能明显增加，应该控制在合理范围内

### 2. 关键词聚焦度与准确度调整
- **分析原内容**：检查原内容中对此关键词"{old_keyword}"的聚焦度、准确度
- **结合参考卡片**：参考上述{len(final_reference_cards)}张素材卡片的具体内容，判断原内容对关键词的解释是否准确、是否充分
- **调整方向**：如果原内容聚焦度低、准确度低，需要扭转此情况，使其更聚焦、更准确
- **朝向新关键词**：修改后的内容要朝向新关键词"{new_keyword}"，体现用户修改的意图

### 3. 字数控制（保持合理范围）
- 修改后的**完整内容**应该保持与原内容相近的字数，不要大幅增加
- 优先保证：改得准、改得对、改得精、改得深，而不是改得多
- 如果原内容在300-500字，修改后也应在300-500字之间

### 4. 输出格式要求（必须严格遵守！）
- **标记新修改部分**：本次新增、修改、删除的部分用<第{next_modify_count}次修改内容>和</第{next_modify_count}次修改内容>标签包裹
- **保留历史标签**：原内容中的<第1次修改内容>、<第2次修改内容>等标签要保留（除非这部分内容被完全删除）
- **标签准确性**：标签只包裹本次真正被修改的文字内容（新增、修改、删除的部分），未修改的部分不要放入新标签
- **嵌套标签的使用**：
  - **不要完全覆盖前序修改的内容**：如果前序修改的内容只有一部分需要调整，应该使用嵌套标签
  - **嵌套格式**：`<第n次修改内容><第m次修改内容>新修改的部分</第m次修改内容>保留的前序修改部分</第n次修改内容>`
  - **示例正确格式**：
    - 如果原内容是"xxx<第2次修改内容>yyy</第2次修改内容>zzz"，现在只修改yyy的前半部分，应该是"xxx<第2次修改内容><第3次修改内容>修改后的yyy前半部分</第3次修改内容>yyy后半部分</第2次修改内容>zzz"
    - 如果原内容是"xxx<第2次修改内容>yyy</第2次修改内容>zzz"，现在在yyy后面新增内容，应该是"xxx<第2次修改内容>yyy<第3次修改内容>新增的内容</第3次修改内容></第2次修改内容>zzz"
    - 另外，如果原内容是"xxx<第1次修改内容>yyy</第1次修改内容>zzz"，现在要删除yyy，应该是"xxxzzz<第2次修改内容>（已删除yyy部分，因为...）</第2次修改内容>"
  - **错误示例（要避免）**：`<第2次修改内容><第3次修改内容>完全覆盖的内容</第3次修改内容></第2次修改内容>`（这样会导致第2次修改的内容完全被覆盖，应该保留未修改的部分）

### 5. 内容质量要求
- **严禁空话套话**：必须具体、有真正认知上的行动指向价值
- **去QA化要求**：去除QA问答的形式，提取核心观点和概念；根据问题链具体分析，引用具体问题内容
- **引用具体问题**：如果提到用户提问、追问，必须引用问题链中的具体问题
- **体现认知推进**：如果提到认知推进、振荡，必须基于具体问题分析
- **人机协同**：加强人机协同的原创性与主体性，突出使用者本身人参与的部分
- **原子化&原创化&可复用化**：保持这三个特性
- **围绕关键词**：内容必须围绕关键词"{new_keyword}"展开

### 6. 描述规范
- **不要直接使用"R"、"B"、"P"、"G"、"D"、"M"、"T"等字母**
- 要使用完整的描述，如"红色专业业务"、"蓝色工具手段"、"紫色思维框架"、"绿色简单深刻"、"枝"、"干"、"根"

### 7. contentTitle更新
- **contentTitle**：S{last_sub_scene_num}:{new_keyword}（将旧关键词替换为新关键词）

## 输出格式

请直接输出修改后的完整内容，不要输出其他说明。

**重要**：
1. **允许修改和删除**：可以修改、删除原有内容的一部分，也可以新增内容，但要合理自洽
2. **标记新修改部分**：本次新增、修改、删除的部分用<第{next_modify_count}次修改内容>和</第{next_modify_count}次修改内容>标签包裹
3. **保留历史标签**：原内容中的<第n次修改内容>标签要保留（除非这部分内容被完全删除）
4. **迭代递进**：这是第{next_modify_count}次修改，要在原有内容基础上深化精准，不是覆盖
5. **修改范围**：可以修改前序次改过的段落，也可以修改前序次没改的段落，但要合理自洽、精准精炼
6. **修改篇幅**：本次修改的篇幅应该大约占全文的20%左右（上下可灵活浮动5%-10%），不要陷入修改过多或过少的极端（其中一定不可过多！）
7. **修改粒度合适**：每次修改篇幅要合适，不要大段替换，**不要完全覆盖前序修改的内容**
8. **嵌套标签使用**：如果只修改前序修改内容的一部分，使用嵌套标签，保留未修改的部分
9. **字数不增加**：修改后整体字数应保持合理，不要明显增加（例如从600字增加到900字是不合理的）
10. 修改后要体现用户修改关键词的意图和认知提升；以及修改内容不可仅有宏大的理论性描述（不错的废话），一定要具体自洽有实施价值
"""

        # 8. 调用LLM（优先claude-4-sonnet，失败则claude-3.7）
        model_name = None
        response_content = None

        try:
            # 8.1 尝试claude-4-sonnet
            model_name = "claude-4-sonnet"
            model_config = config_manager.get_model_config(model_name)
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

        except Exception as e:
            print(f"[update_permanent_card_by_keyword] 使用{model_name}失败: {e}")
            # 8.2 降级使用claude-3.7
            try:
                model_name = "claude-3.7"
                model_config = config_manager.get_model_config(model_name)
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
            except Exception as e2:
                print(f"[update_permanent_card_by_keyword] 使用{model_name}也失败: {e2}")
                return {'success': False, 'msg': f'LLM调用失败: {str(e2)}', 'card_id': None}

        if not response_content:
            return {'success': False, 'msg': 'LLM未返回内容', 'card_id': None}

        # 🔥 清理LLM返回内容中的contentTitle前缀（如 "**contentTitle**：S6:xxx"）
        cleaned_content = response_content.strip()
        # 移除开头的 "**contentTitle**：" 或 "contentTitle：" 等格式
        import re
        cleaned_content = re.sub(r'^\*\*contentTitle\*\*[：:]\s*S\d+:[^\n]+\n+', '', cleaned_content, flags=re.MULTILINE)
        cleaned_content = re.sub(r'^contentTitle[：:]\s*S\d+:[^\n]+\n+', '', cleaned_content, flags=re.MULTILINE)
        cleaned_content = cleaned_content.strip()

        # 9. 更新永久卡
        old_content = permanent_card.content
        old_contentTitle = permanent_card.contentTitle
        old_keyWords = permanent_card.keyWords

        print(f"[update_permanent_card_by_keyword] 准备更新永久卡 CID={permanent_card.cid}")
        print(f"[update_permanent_card_by_keyword] 旧contentTitle: {old_contentTitle}")
        print(f"[update_permanent_card_by_keyword] 旧keyWords: {old_keyWords}")
        print(f"[update_permanent_card_by_keyword] 旧content长度: {len(old_content) if old_content else 0}")
        print(f"[update_permanent_card_by_keyword] 新content长度: {len(cleaned_content) if cleaned_content else 0}")

        # 更新contentTitle
        # 🔥 直接替换为 S{last_sub_scene_num}:{new_keyword} 格式
        permanent_card.contentTitle = f"S{last_sub_scene_num}:{new_keyword}"

        # 更新keyWords（确保使用新关键词）
        permanent_card.keyWords = new_keyword

        # 更新content（将原content保存到lastContent，新content写入content）
        permanent_card.lastContent = old_content
        permanent_card.content = cleaned_content

        # 🔥 保持原有的四色DMT属性不变（不重新分析）
        # permanent_card.four_color_type 和 permanent_card.dmt_level 保持不变

        permanent_card.save()

        print(f"[update_permanent_card_by_keyword] ✅ 成功更新永久卡 CID={permanent_card.cid}")
        print(f"[update_permanent_card_by_keyword] 新contentTitle: {permanent_card.contentTitle}")
        print(f"[update_permanent_card_by_keyword] 新keyWords: {permanent_card.keyWords}")
        print(
            f"[update_permanent_card_by_keyword] 新content长度: {len(permanent_card.content) if permanent_card.content else 0}")

        return {'success': True, 'msg': '更新成功', 'card_id': str(permanent_card.cid)}

    except Exception as e:
        print(f"[update_permanent_card_by_keyword] 错误: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'msg': f'更新失败: {str(e)}', 'card_id': None}

