# encoding=utf-8
"""
🔥 问题链智能排序API
"""
import json
import os
import re
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
from zym.models import UserNotebook
from app_chat.config.config_manager import config_manager
from openai import OpenAI


def classify_single_question(new_cid, new_question, existing_categories, username, scene_name):
    """
    🔥 分类单个新问题，判断是否属于某个现有分类，如果不属于则新增分类

    参数:
        new_cid: 新问题的CID
        new_question: 新问题的内容
        existing_categories: 现有的分类字典 {分类名: [cid1, cid2, ...]}
        username: 用户名
        scene_name: 场景名

    返回:
        dict: {'category_name': str, 'updated_categories': dict} 或 None（如果失败）
    """
    try:
        if not existing_categories:
            existing_categories = {}

        # 1. 获取场景信息
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None

        scene_summary_info = None
        notebook_desc = ""
        if scene_name:
            scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, None)
            notebook_desc = get_notebook_description(username, scene_name)
            final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
        else:
            final_scene_summary = None

        notebook_name_cn = ""
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                notebook_name_cn = notebook.bookdescription or ""
            except UserNotebook.DoesNotExist:
                pass

        # 2. 构建现有分类信息
        categories_info = "\n## 现有分类：\n"
        for cat_name, cids in existing_categories.items():
            categories_info += f"\n- {cat_name}: {len(cids)}个问题\n"

        # 3. 构建Prompt
        system_prompt = "你是专业的语义分析专家，擅长根据问题的具体内容语义进行分类。"

        user_prompt = f"""你需要判断一个新问题应该属于哪个现有分类，如果不属于任何现有分类，则为其创建一个新的分类名。

## 场景信息

- **场景名**: {scene_name or '未提供'}
- **场景摘要**: {final_scene_summary[:500] if final_scene_summary else '未提供'}
- **本子目标（中文名）**: {notebook_name_cn}
- **本子描述**: {notebook_desc[:300] if notebook_desc else '未提供'}

{categories_info}

## 新问题

- **CID**: {new_cid}
- **问题内容**: {new_question}

## 要求

1. 如果新问题的语义与某个现有分类匹配，返回该分类名
2. 如果新问题的语义与所有现有分类都不匹配，创建一个新的分类名（2-6个字，能准确反映问题的核心语义特征）
3. 分类名要根据问题的实际语义内容灵活命名，不要使用死板的标签

## 输出格式

请按照以下JSON格式输出：
```json
{{
    "category_name": "分类名（如果属于现有分类，使用现有分类名；如果不属于，创建新分类名）",
    "is_new_category": true/false
}}
```

**重要**：
- 如果属于现有分类，`category_name`必须是现有分类名之一
- 如果不属于现有分类，`category_name`是新创建的分类名（2-6个字）
- 只输出JSON，不要输出其他说明文字
"""

        # 4. 调用LLM
        model_name = "claude-4-sonnet"
        try:
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
            print(f"[classify_single_question] 使用{model_name}失败: {e}")
            # 尝试claude-3.7
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
                print(f"[classify_single_question] 使用{model_name}也失败: {e2}")
                return None

        if not response_content:
            return None

        # 5. 解析结果
        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_content, re.DOTALL)
            if json_match:
                result_data = json.loads(json_match.group(1))
            else:
                result_data = json.loads(response_content)

            category_name = result_data.get('category_name', '')
            is_new_category = result_data.get('is_new_category', False)

            if not category_name:
                return None

            # 6. 更新分类
            updated_categories = existing_categories.copy()
            if category_name in updated_categories:
                # 属于现有分类，添加到该分类
                if new_cid not in updated_categories[category_name]:
                    updated_categories[category_name].append(new_cid)
            else:
                # 新分类
                updated_categories[category_name] = [new_cid]

            print(f"[classify_single_question] 分类完成: CID={new_cid}, 分类={category_name}, 是否新分类={is_new_category}")

            return {
                'category_name': category_name,
                'is_new_category': is_new_category,
                'updated_categories': updated_categories
            }
        except Exception as e:
            print(f"[classify_single_question] 解析结果失败: {e}")
            return None

    except Exception as e:
        print(f"[classify_single_question] 错误: {e}")
        import traceback
        traceback.print_exc()
        return None


@csrf_exempt
def smart_sort_questions(request):
    """
    🔥 使用claude-4-sonnet对问题链索引卡进行智能排序（分两次调用：先排序，后分类）

    请求参数:
        username: 用户名
        scene_name: 场景名（可选）
        questions: 问题列表，每个问题包含 {cid, question, author, sub_scene, datetime}

    返回:
        dict: {'success': bool, 'msg': str, 'sorted_cids': list or None, 'categories': dict or None}
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        scene_name = data.get('scene_name')
        questions = data.get('questions', [])

        if not username or not questions:
            return JsonResponse({'success': False, 'msg': '缺少必要参数', 'sorted_cids': None, 'categories': None})

        print(f"[smart_sort_questions] 开始智能排序，用户名: {username}, 问题数量: {len(questions)}")

        # 1. 获取场景信息和本子描述
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None

        scene_summary_info = None
        notebook_desc = ""
        if scene_name:
            scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, None)
            notebook_desc = get_notebook_description(username, scene_name)
            final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
        else:
            final_scene_summary = None

        # 2. 获取本子中文名（目标）
        notebook_name_cn = ""
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                notebook_name_cn = notebook.bookdescription or ""
            except UserNotebook.DoesNotExist:
                pass

        # 3. 获取卡片的DMT四色信息
        from app_chat.models import Card
        cid_to_card = {}
        for q in questions:
            cid = q.get('cid', '')
            try:
                card = Card.objects.filter(cid=cid).values('four_color_type', 'dmt_level').first()
                if card:
                    cid_to_card[cid] = card
            except:
                pass

        # 4. 构建问题列表信息（包含DMT四色信息）
        questions_info = "\n## 问题列表：\n"
        for idx, q in enumerate(questions):
            cid = q.get('cid', '')
            card_info = cid_to_card.get(cid, {})
            four_color = card_info.get('four_color_type', '')
            dmt_level = card_info.get('dmt_level', '')
            color_desc = {'P': '紫色', 'G': '绿色', 'R': '红色', 'B': '蓝色'}.get(four_color, '无色')
            dmt_desc = {'D': '枝', 'M': '干', 'T': '根'}.get(dmt_level, '无')

            questions_info += f"\n问题 {idx + 1}:\n"
            questions_info += f"- CID: {cid}\n"
            questions_info += f"- 问题内容: {q.get('question', '')}\n"
            questions_info += f"- 子场景: {q.get('sub_scene', '')}\n"
            questions_info += f"- 提问时间: {q.get('datetime', '')}\n"
            questions_info += f"- 提问者: {q.get('author', '')}\n"
            questions_info += f"- 四色DMT: {color_desc}{dmt_desc}\n"

        # 5. 初始化LLM客户端（优先claude-4-sonnet）
        model_name = "claude-4-sonnet"
        try:
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
        except Exception as e:
            print(f"[smart_sort_questions] 初始化{model_name}失败: {e}")
            return JsonResponse(
                {'success': False, 'msg': f'LLM初始化失败: {str(e)}', 'sorted_cids': None, 'categories': None})

        # 6. 第一次调用：排序
        sort_system_prompt = "你是专业的认知分析和问题排序专家，擅长根据场景目标、认知进展和问题价值对问题链进行智能排序。"

        sort_user_prompt = f"""你需要对以下问题链进行智能排序，猜测推测使用者更想要先看到哪些问题，对于解决此场景目标更有帮助。

## 场景信息

- **场景名**: {scene_name or '未提供'}
- **场景摘要**: {final_scene_summary[:1000] if final_scene_summary else '未提供'}
- **本子目标（中文名）**: {notebook_name_cn}
- **本子描述**: {notebook_desc[:500] if notebook_desc else '未提供'}

{questions_info}

## 排序原则（按重要性排序）

1. **DMT四色优先**（最重要！）：
   - **优先紫色和绿色**的问题卡片提问排在前面（紫色=思维框架，绿色=简单深刻）
   - 然后是红色和蓝色的问题
   - 最后是无四色DMT属性的问题
2. **目标导向**: 优先考虑对解决场景目标和本子目标更有帮助的问题
3. **认知价值**: 评估问题的认知深度和价值（是否能推动认知进展）
4. **子场景位置**: 
   - 通常来说靠后的子场景（S4、S5、S6等）提出的问题更有价值，因为它们建立在前期认知基础上
   - **但这并不一定**：有些开头的子场景（S1、S2）也起到总领的重要作用，需要灵活分析
   - 如果开头的问题具有总领性、框架性、基础性，也应该优先考虑
5. **时间顺序**: 在同等价值下，较新的问题可能有更高的相关性
6. **问题质量**: 问题的清晰度、深度、可操作性

## 输出要求

请直接输出排序后的CID列表（用逗号分隔），格式如下：
排序后的CID列表（按重要性从高到低）: cid1,cid2,cid3,...

**重要**：
- 必须包含所有问题的CID
- 按重要性从高到低排列
- 只输出CID列表，不要输出其他说明文字
"""

        try:
            sort_response = client.chat.completions.create(
                model=full_model_name,
                messages=[
                    {"role": "system", "content": sort_system_prompt},
                    {"role": "user", "content": sort_user_prompt}
                ],
                max_tokens=hyper_para.max_tokens,
                temperature=hyper_para.temperature
            )
            sort_response_content = sort_response.choices[0].message.content
        except Exception as e:
            print(f"[smart_sort_questions] 使用{model_name}排序失败: {e}")
            # 尝试claude-3.7
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

                sort_response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": sort_system_prompt},
                        {"role": "user", "content": sort_user_prompt}
                    ],
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature
                )
                sort_response_content = sort_response.choices[0].message.content
            except Exception as e2:
                print(f"[smart_sort_questions] 使用{model_name}排序也失败: {e2}")
                return JsonResponse(
                    {'success': False, 'msg': f'LLM调用失败: {str(e2)}', 'sorted_cids': None, 'categories': None})

        if not sort_response_content:
            return JsonResponse({'success': False, 'msg': 'LLM未返回排序内容', 'sorted_cids': None, 'categories': None})

        # 7. 解析排序结果
        original_cids = set(str(q.get('cid', '')) for q in questions)
        validated_sorted_cids = []
        try:
            # 提取CID列表（从"排序后的CID列表（按重要性从高到低）: "之后的部分）
            cid_list_str = sort_response_content
            if ":" in sort_response_content:
                cid_list_str = sort_response_content.split(":")[-1].strip()

            # 解析CID列表（可能是逗号分隔的字符串或列表格式）
            cids_raw = [cid.strip() for cid in re.split(r'[,\s]+', cid_list_str) if cid.strip()]

            # 验证CID是否都在原始问题列表中，并去重
            seen = set()
            for cid in cids_raw:
                cid_str = str(cid)
                if cid_str in original_cids and cid_str not in seen:
                    validated_sorted_cids.append(cid_str)
                    seen.add(cid_str)

            # 如果排序后的CID数量与原始不一致，添加缺失的CID（按原始顺序）
            if len(validated_sorted_cids) < len(original_cids):
                missing_cids = [cid for cid in original_cids if cid not in seen]
                validated_sorted_cids.extend(missing_cids)

            print(f"[smart_sort_questions] 排序完成，排序后的CID数量: {len(validated_sorted_cids)}")
        except Exception as e:
            print(f"[smart_sort_questions] 解析排序结果失败: {e}")
            return JsonResponse(
                {'success': False, 'msg': f'解析排序结果失败: {str(e)}', 'sorted_cids': None, 'categories': None})

        # 8. 第二次调用：分类
        category_system_prompt = "你是专业的语义分析专家，擅长根据问题的具体内容语义进行灵活分类。"

        # 构建排序后的问题列表信息（用于分类）
        sorted_questions_info = "\n## 排序后的问题列表：\n"
        cid_to_question = {str(q.get('cid', '')): q for q in questions}
        for idx, cid in enumerate(validated_sorted_cids):
            q = cid_to_question.get(cid, {})
            card_info = cid_to_card.get(cid, {})
            four_color = card_info.get('four_color_type', '')
            dmt_level = card_info.get('dmt_level', '')
            color_desc = {'P': '紫色', 'G': '绿色', 'R': '红色', 'B': '蓝色'}.get(four_color, '无色')
            dmt_desc = {'D': '枝', 'M': '干', 'T': '根'}.get(dmt_level, '无')

            sorted_questions_info += f"\n问题 {idx + 1}:\n"
            sorted_questions_info += f"- CID: {cid}\n"
            sorted_questions_info += f"- 问题内容: {q.get('question', '')}\n"
            sorted_questions_info += f"- 子场景: {q.get('sub_scene', '')}\n"
            sorted_questions_info += f"- 提问时间: {q.get('datetime', '')}\n"
            sorted_questions_info += f"- 提问者: {q.get('author', '')}\n"
            sorted_questions_info += f"- 四色DMT: {color_desc}{dmt_desc}\n"

        category_user_prompt = f"""你需要对以下已排序的问题链进行语义分类。

## 场景信息

- **场景名**: {scene_name or '未提供'}
- **场景摘要**: {final_scene_summary[:1000] if final_scene_summary else '未提供'}
- **本子目标（中文名）**: {notebook_name_cn}
- **本子描述**: {notebook_desc[:500] if notebook_desc else '未提供'}

{sorted_questions_info}

## 分类要求

请按照问题的**具体内容语义**进行灵活分类，**不要使用死板的"思维类"、"追问类"、"疑惑类"等标签**，而是根据问题的实际语义内容灵活命名分类。

**分类原则**：
- 分类名要能准确反映该类问题的语义特征（要根据实际问题中关注的核心关键点xxx的语义灵活命名）
- 分类数量要合理（通常3-6个分类，若问题数量较多，可以适当增加分类数量），不要过多或过少
- 分类名要简洁明确（2-6个字），能准确反映该类问题的核心语义聚焦关注点xxx
- 每个问题CID必须且仅能出现在一个分类中

## 输出格式

请按照以下JSON格式输出：
```json
{{
    "categories": {{
        "分类名1（根据问题语义灵活命名）": ["cid1", "cid2", ...],
        "分类名2（根据问题语义灵活命名）": ["cid3", "cid4", ...],
        ...
    }}
}}
```

**重要**：
- 必须包含所有问题的CID
- 分类名要根据问题的实际语义内容灵活命名，不要使用死板的标签
- 只输出JSON，不要输出其他说明文字
"""

        validated_categories = {}
        try:
            category_response = client.chat.completions.create(
                model=full_model_name,
                messages=[
                    {"role": "system", "content": category_system_prompt},
                    {"role": "user", "content": category_user_prompt}
                ],
                max_tokens=hyper_para.max_tokens,
                temperature=hyper_para.temperature
            )
            category_response_content = category_response.choices[0].message.content

            if category_response_content:
                # 解析分类结果
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', category_response_content, re.DOTALL)
                if json_match:
                    category_result_data = json.loads(json_match.group(1))
                else:
                    category_result_data = json.loads(category_response_content)

                categories_raw = category_result_data.get('categories', {})

                # 验证和清理categories
                all_categorized_cids = set()
                for category_name, cid_list in categories_raw.items():
                    if not isinstance(cid_list, list):
                        continue
                    validated_cid_list = []
                    for cid in cid_list:
                        cid_str = str(cid)
                        if cid_str in original_cids and cid_str not in all_categorized_cids:
                            validated_cid_list.append(cid_str)
                            all_categorized_cids.add(cid_str)
                    if validated_cid_list:
                        validated_categories[category_name] = validated_cid_list

                # 将未分类的CID添加到"其他"分类（如果有）
                uncategorized_cids = [cid for cid in original_cids if cid not in all_categorized_cids]
                if uncategorized_cids:
                    validated_categories['其他'] = uncategorized_cids

                print(f"[smart_sort_questions] 分类完成，分类数量: {len(validated_categories)}")
            else:
                print(f"[smart_sort_questions] 分类LLM未返回内容，跳过分类")
        except Exception as e:
            print(f"[smart_sort_questions] 分类过程出错: {e}")
            import traceback
            traceback.print_exc()
            # 分类失败不影响排序结果，使用空分类

        # 9. 保存排序和分类结果到数据库
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                notebook.questionChainSorted = True
                notebook.questionChainSortedOrder = json.dumps(validated_sorted_cids, ensure_ascii=False)
                notebook.questionChainCategories = json.dumps(validated_categories, ensure_ascii=False)
                notebook.save()
                print(
                    f"[smart_sort_questions] 已保存排序和分类结果到数据库，CID数量: {len(validated_sorted_cids)}, 分类数量: {len(validated_categories)}")
            except UserNotebook.DoesNotExist:
                print(f"[smart_sort_questions] 未找到UserNotebook，跳过保存排序结果")

        return JsonResponse({
            'success': True,
            'msg': '排序和分类成功',
            'sorted_cids': validated_sorted_cids,
            'categories': validated_categories
        })

    except Exception as e:
        print(f"[smart_sort_questions] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'msg': f'排序失败: {str(e)}', 'sorted_cids': None, 'categories': None})
