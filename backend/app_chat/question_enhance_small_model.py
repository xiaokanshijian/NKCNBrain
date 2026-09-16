"""
Tab键触发小模型辅助问题补全模块
使用8卡端小模型快速辅助高质量、结构化补全、修正、提升用户发问内容
支持两种方式：
1. 直接调用moonshot-v1-8k（use_relay=False）
2. 通过中转服务器调用8卡服务端小模型（use_relay=True，默认）

注意：通过中转服务器调用时，复用了get_depth_suggestion接口，task_type设置为'question_enhance'。
如果8卡服务器不支持此task_type，可以临时使用'qa'类型，或者需要8卡服务器添加对question_enhance任务类型的支持。
"""
from openai import OpenAI
import json
import os
import re
from app_chat import scene_context_helper


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


def enhance_question_with_small_model(user_question, username, scene_name, sub_scene_name, 
                                      notebook_description, selected_documents=None, selected_cards=None,
                                      use_relay=True, all_document_names=None):
    """
    使用小模型辅助问题补全、修正、提升，并推荐应勾选的文档
    
    参数:
        user_question: 用户初步编辑的问题
        username: 用户名
        scene_name: 场景名
        sub_scene_name: 子场景名
        notebook_description: 本子描述
        selected_documents: 勾选的基础文档/增量文档列表，每个包含name、main_four_color、secondary_four_color、dmt_level
        selected_cards: 勾选的卡片列表，每个包含title、keyWords、four_color_type、dmt_level
        use_relay: 是否使用中转服务器
        all_document_names: 本子内的所有文档名列表
    
    返回:
        dict: {
            'enhanced_question': str,  # 增强后的问题
            'suggested_sub_scene': str|None,  # 建议的子场景
            'core_keyword': str|None,  # 提取的核心关键词（xxx）
            'suggested_documents': list  # 推荐的文档名列表
        }
    """
    try:
        # 1. 获取场景摘要（不超过300字，超过请截断）
        scene_summary, subscene_summary = scene_context_helper.get_scene_summary(scene_name, sub_scene_name)
        final_scene_summary = subscene_summary if subscene_summary else scene_summary
        
        # 截断至300字
        if len(final_scene_summary) > 300:
            final_scene_summary = final_scene_summary[:300] + "..."

        # 🔥 1.1 获取场景的所有子场景列表及其摘要
        all_subscenes_info = ""
        try:
            import os
            import pandas as pd

            # 读取场景的prompt.xlsx，获取所有子场景列表
            scene_dir_path = f'./received_dir/scene_excel/{scene_name}'
            prompt_excel_path = os.path.join(scene_dir_path, 'prompt.xlsx')

            if os.path.exists(prompt_excel_path):
                try:
                    excel_data = pd.read_excel(prompt_excel_path, sheet_name='LUI1')
                    sub_scene_col = 1

                    if excel_data.shape[1] > sub_scene_col:
                        first_subscene_col_name = excel_data.columns[sub_scene_col]
                        subscene_name_list = excel_data.iloc[:, sub_scene_col].dropna().tolist()
                        subscene_name_list_order = [first_subscene_col_name] + subscene_name_list

                        # 为每个子场景获取摘要
                        all_subscenes_info = "\n## 场景的所有子场景信息（用于判断问题最适合哪个子场景）：\n"
                        for idx, subscene_name in enumerate(subscene_name_list_order, start=1):
                            # 获取子场景摘要
                            _, subscene_summary_text = scene_context_helper.get_scene_summary(scene_name,
                                                                                              subscene_name)

                            # 截断至60字
                            if len(subscene_summary_text) > 60:
                                subscene_summary_text = subscene_summary_text[:60] + "..."

                            # 构建子场景信息（格式：S1: 子场景名 - 摘要）
                            all_subscenes_info += f"- S{idx}: {subscene_name}"
                            if subscene_summary_text:
                                all_subscenes_info += f" - {subscene_summary_text}"
                            all_subscenes_info += "\n"

                        print(f"[enhance_question_with_small_model] 成功获取{len(subscene_name_list_order)}个子场景信息")
                    else:
                        print(f"[enhance_question_with_small_model] ⚠️ prompt.xlsx列数不足，无法读取子场景列表")
                except Exception as e:
                    print(f"[enhance_question_with_small_model] ⚠️ 读取prompt.xlsx获取子场景列表失败: {e}")
            else:
                print(f"[enhance_question_with_small_model] ⚠️ prompt.xlsx不存在: {prompt_excel_path}")
        except Exception as e:
            print(f"[enhance_question_with_small_model] ⚠️ 获取所有子场景信息失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 2. 构建文档信息描述（谨慎描述，不明确指出是"勾选的文档"）
        docs_info = ""
        if selected_documents and len(selected_documents) > 0:
            docs_info = "\n可能参考（不一定）的各类文档信息：\n"
            for doc in selected_documents:
                doc_name = doc.get('name', '')
                main_color = doc.get('main_four_color', '')
                secondary_color = doc.get('secondary_four_color', '')
                dmt = doc.get('dmt_level', '')
                docs_info += f"- {doc_name}"
                if main_color or dmt:
                    docs_info += f"（主色:{main_color}"
                    if secondary_color:
                        docs_info += f", 辅色:{secondary_color}"
                    if dmt:
                        docs_info += f", DMT:{dmt}"
                    docs_info += "）"
                docs_info += "\n"
        
        # 3. 构建卡片信息描述
        cards_info = ""
        if selected_cards and len(selected_cards) > 0:
            cards_info = "\n勾选的卡片信息：\n"
            for card in selected_cards:
                title = card.get('title', '')
                keywords = card.get('keyWords', '')
                four_color = card.get('four_color_type', '')
                dmt = card.get('dmt_level', '')
                cards_info += f"- 标题：{title}"
                if keywords:
                    cards_info += f"，关键词：{keywords}"
                if four_color or dmt:
                    cards_info += f"（四色:{four_color}" if four_color else "（"
                    if dmt:
                        cards_info += f", DMT:{dmt}" if four_color else f"DMT:{dmt}"
                    cards_info += "）"
                cards_info += "\n"

        # 4. 构建本子内所有文档名列表信息
        all_docs_list_info = ""
        if all_document_names and len(all_document_names) > 0:
            all_docs_list_info = "\n## 本子内的所有文档列表（用于推荐应勾选的文档）：\n"
            for doc_name in all_document_names:
                all_docs_list_info += f"- {doc_name}\n"

        # 5. 构建prompt
        system_prompt = """你是专业的问答辅助专家，擅长基于场景上下文和文档/卡片信息，帮助用户补全、修正、提升问题的质量。

你的任务是：
1. 理解用户的初步问题意图
2. 结合当前场景、子场景、本子描述、可能会参考到的文档（不一定）/卡片（若有卡片要重视）信息、可能（不一定）会有全部文档列表，提供高质量、结构化的补全建议
3. 修正问题中的模糊或不准确之处
4. 提升问题的表达清晰度和针对性
5. 判断此问题应该在此场景下的哪个子场景（S1-Sn）最为合适
6. 分析用户原始问题里的核心需求（类似"哪些文档的哪些位置有与xxx相关的内容"中的"xxx"是什么）
7. 根据核心需求，从本子内的所有文档列表中推荐应勾选的文档名

请直接输出补全、修正、提升后的问题内容，不要添加任何解释性文字。"""
        
        user_prompt = f"""用户初步编辑的问题：
{user_question}

## 场景上下文信息
- 场景名：{scene_name}
- 当前子场景名：{sub_scene_name or '未指定'}
- 当前子场景摘要：{final_scene_summary[:500] if final_scene_summary else '未提供'}（已截断至300字）
- 本子描述：{notebook_description[:300] if notebook_description else '未提供'}（已截断至300字）

{all_subscenes_info if all_subscenes_info else ''}

{docs_info if docs_info else ''}

{cards_info if cards_info else ''}

{all_docs_list_info if all_docs_list_info else ''}

请基于以上信息，完成以下任务：

1. **问题补全、修正、提升**：对用户的问题进行高质量、结构化的补全、修正、提升，必须考虑到上述所有信息（对于各类可能参考但不一定的素材文档，不要明确列举具体文档名，而是提炼与用户初步问题的核心需求主体对象高度相关的主题和关键概念）。字数方面80-120字左右为佳（质量一定要高、理解要深刻）。

2. **子场景判断**：判断此问题应该在此场景下的哪个子场景（S1-Sn）最为合适。根据问题的认知层次和复杂度，不要受当前子场景限制。

3. **核心需求提取**：分析用户原始问题里的核心需求，提取出类似"哪些文档的哪些位置有与xxx相关的内容"中的"xxx"是什么。这个"xxx"应该是用户问题中要查找或关注的核心概念、主题、关键词等。

4. **文档推荐**：根据提取出的核心需求（xxx），从本子内的所有文档列表中，推荐应该勾选的文档名列表（推荐3-8个文档，选择与核心需求最相关的文档）。

**输出格式要求**：
请严格按照以下格式输出，不要有其他说明：

【增强后的问题】具体补全、修正、提升后的问题内容_Sn
【核心需求】提取出的核心需求关键词（xxx）
【推荐文档】文档名1，文档名2，文档名3...

注意：
- 增强后的问题格式为："问题内容_Sn"（Sn为子场景标识，如S1、S2等）
- 核心需求应该是一个简洁的关键词或短语，代表用户问题要查找的核心内容
- 推荐文档列表用中文逗号分隔，不要包含文件扩展名（如.pdf、.txt等）
- 如果无法提取核心需求或推荐文档，核心需求可以留空或写"无"，推荐文档可以留空或写"无"
"""
        
        # 5. 调用小模型进行问题补全
        if use_relay:
            # 方式1：通过中转服务器调用8卡服务端小模型
            enhanced_result_raw = _enhance_question_via_relay(
                user_prompt, system_prompt, username
            )
        else:
            # 方式2：直接调用deepseek-chat
            enhanced_result_raw = _enhance_question_via_moonshot(
                user_prompt, system_prompt
            )

        # 🔥 解析新格式的输出（包含增强后的问题、子场景、核心需求、推荐文档）
        enhanced_result = _parse_enhanced_question_result_new(enhanced_result_raw)

        if not enhanced_result or not enhanced_result.get('enhanced_question'):
            print(f"[enhance_question_with_small_model] 问题补全失败，返回原问题")
            return {
                'enhanced_question': user_question,
                'suggested_sub_scene': None,
                'core_keyword': None,
                'suggested_documents': []
            }

        enhanced_question_clean = enhanced_result.get('enhanced_question', '').strip()
        suggested_sub_scene = enhanced_result.get('suggested_sub_scene')
        core_keyword = enhanced_result.get('core_keyword')
        model_suggested_docs = enhanced_result.get('suggested_documents', [])

        if not enhanced_question_clean:
            print(f"[enhance_question_with_small_model] 问题补全结果为空，返回原问题")
            return {
                'enhanced_question': user_question,
                'suggested_sub_scene': None,
                'core_keyword': None,
                'suggested_documents': []
            }

        print(
            f"[enhance_question_with_small_model] 问题补全完成，原问题长度: {len(user_question)}, 补全后长度: {len(enhanced_question_clean)}")
        if suggested_sub_scene:
            print(f"[enhance_question_with_small_model] 子场景建议: {suggested_sub_scene}")
        if core_keyword:
            print(f"[enhance_question_with_small_model] 核心需求: {core_keyword}")
        if model_suggested_docs:
            print(f"[enhance_question_with_small_model] 模型推荐文档: {model_suggested_docs}")

            # 🔥 如果提取到核心关键词，从pre_summary目录查找包含该关键词的文档
        final_suggested_documents = []
        if core_keyword and core_keyword.strip() and core_keyword.strip().lower() not in ['无', 'none', '']:
            final_suggested_documents = _select_documents_by_keyword(
                core_keyword, username, model_suggested_docs, all_document_names
            )

        # 🔥 返回字典，包含增强后的问题、子场景建议、核心关键词、推荐文档列表
        return {
            'enhanced_question': enhanced_question_clean,
            'suggested_sub_scene': suggested_sub_scene,
            'core_keyword': core_keyword,
            'suggested_documents': final_suggested_documents
        }
        
    except Exception as e:
        print(f"[enhance_question_with_small_model] 问题补全失败: {e}")
        import traceback
        traceback.print_exc()
        # 🔥 失败时返回字典格式，包含原问题
        return {
            'enhanced_question': user_question,
            'suggested_sub_scene': None,
            'core_keyword': None,
            'suggested_documents': []
        }


def _parse_enhanced_question_result(enhanced_text):
    """
    解析增强后的问题结果，提取问题和子场景建议（旧格式兼容）

    参数:
        enhanced_text: 增强后的文本（可能包含格式："具体增强后的问题_Sn"）或字典

    返回:
        dict: {'enhanced_question': str, 'suggested_sub_scene': str|None}
    """
    # 🔥 容错处理：如果传入的已经是字典，直接返回
    if isinstance(enhanced_text, dict):
        return enhanced_text

    if not enhanced_text:
        return {'enhanced_question': '', 'suggested_sub_scene': None}

    # 🔥 确保是字符串类型
    if not isinstance(enhanced_text, str):
        print(f"[_parse_enhanced_question_result] ⚠️ 输入类型异常: {type(enhanced_text)}, 尝试转换为字符串")
        enhanced_text = str(enhanced_text)

    enhanced_question_clean = enhanced_text.strip()
    suggested_sub_scene = None

    # 🔥 尝试解析格式："具体增强后的问题_Sn"
    if '_' in enhanced_question_clean:
        # 查找最后一个下划线的位置（以防问题本身包含下划线）
        last_underscore_idx = enhanced_question_clean.rfind('_')
        if last_underscore_idx >= 0:
            question_part = enhanced_question_clean[:last_underscore_idx].strip()
            scene_part = enhanced_question_clean[last_underscore_idx + 1:].strip()

            # 验证子场景格式（S后跟数字，如S1, S2, S10等）
            import re
            if re.match(r'^S\d+$', scene_part):
                enhanced_question_clean = question_part
                suggested_sub_scene = scene_part
                print(f"[_parse_enhanced_question_result] ✅ 解析到子场景建议: {suggested_sub_scene}")

    # 🔥 如果没有按格式输出，进行容错处理
    if suggested_sub_scene is None:
        print(f"[_parse_enhanced_question_result] ⚠️ 输出不符合格式要求（未包含_Sn），使用完整文本作为问题")
        # 即使没有子场景建议，也返回增强后的问题

    return {
        'enhanced_question': enhanced_question_clean,
        'suggested_sub_scene': suggested_sub_scene
    }


def _parse_enhanced_question_result_new(enhanced_result_raw):
    """
    解析增强后的问题结果（新格式），提取问题、子场景、核心需求、推荐文档

    参数:
        enhanced_result_raw: 可能是字符串、字典或已解析的格式

    返回:
        dict: {
            'enhanced_question': str,
            'suggested_sub_scene': str|None,
            'core_keyword': str|None,
            'suggested_documents': list
        }
    """
    # 🔥 容错处理：如果传入的已经是字典（可能来自旧格式解析）
    if isinstance(enhanced_result_raw, dict):
        # 如果已经是新格式（包含core_keyword和suggested_documents），直接返回
        if 'core_keyword' in enhanced_result_raw or 'suggested_documents' in enhanced_result_raw:
            return enhanced_result_raw
        # 否则是旧格式，补充缺失字段
        return {
            'enhanced_question': enhanced_result_raw.get('enhanced_question', ''),
            'suggested_sub_scene': enhanced_result_raw.get('suggested_sub_scene'),
            'core_keyword': None,
            'suggested_documents': []
        }

    if not enhanced_result_raw:
        return {'enhanced_question': '', 'suggested_sub_scene': None, 'core_keyword': None, 'suggested_documents': []}

    # 🔥 确保是字符串类型
    if not isinstance(enhanced_result_raw, str):
        print(f"[_parse_enhanced_question_result_new] ⚠️ 输入类型异常: {type(enhanced_result_raw)}, 尝试转换为字符串")
        enhanced_result_raw = str(enhanced_result_raw)

    enhanced_text = enhanced_result_raw.strip()
    enhanced_question_clean = ''
    suggested_sub_scene = None
    core_keyword = None
    suggested_documents = []

    # 🔥 尝试解析新格式：【增强后的问题】..._Sn 【核心需求】xxx 【推荐文档】doc1，doc2...
    import re

    # 提取增强后的问题和子场景
    question_match = re.search(r'【增强后的问题】\s*(.+?)(?=\n【|$)', enhanced_text, re.DOTALL)
    if question_match:
        question_content = question_match.group(1).strip()
        # 解析问题内容中的子场景（格式：问题内容_Sn）
        if '_' in question_content:
            last_underscore_idx = question_content.rfind('_')
            if last_underscore_idx >= 0:
                question_part = question_content[:last_underscore_idx].strip()
                scene_part = question_content[last_underscore_idx + 1:].strip()
                if re.match(r'^S\d+$', scene_part):
                    enhanced_question_clean = question_part
                    suggested_sub_scene = scene_part
                else:
                    enhanced_question_clean = question_content
            else:
                enhanced_question_clean = question_content
        else:
            enhanced_question_clean = question_content
    else:
        # 如果新格式解析失败，尝试旧格式
        enhanced_result_old = _parse_enhanced_question_result(enhanced_text)
        enhanced_question_clean = enhanced_result_old.get('enhanced_question', enhanced_text)
        suggested_sub_scene = enhanced_result_old.get('suggested_sub_scene')

    # 提取核心需求
    core_keyword_match = re.search(r'【核心需求】\s*(.+?)(?=\n【|$)', enhanced_text, re.DOTALL)
    if core_keyword_match:
        core_keyword = core_keyword_match.group(1).strip()
        # 如果核心需求是"无"或"none"，设置为None
        if core_keyword.lower() in ['无', 'none', '']:
            core_keyword = None

    # 提取推荐文档列表
    docs_match = re.search(r'【推荐文档】\s*(.+?)(?=\n【|$)', enhanced_text, re.DOTALL)
    if docs_match:
        docs_text = docs_match.group(1).strip()
        if docs_text.lower() not in ['无', 'none', '']:
            # 按中文逗号或英文逗号分割
            suggested_documents = [doc.strip() for doc in re.split(r'[,，]', docs_text) if doc.strip()]

    print(
        f"[_parse_enhanced_question_result_new] ✅ 解析结果 - 问题长度: {len(enhanced_question_clean)}, 子场景: {suggested_sub_scene}, 核心需求: {core_keyword}, 推荐文档数: {len(suggested_documents)}")

    return {
        'enhanced_question': enhanced_question_clean,
        'suggested_sub_scene': suggested_sub_scene,
        'core_keyword': core_keyword,
        'suggested_documents': suggested_documents
    }


def _enhance_question_via_relay(user_prompt, system_prompt, username):
    """
    通过中转服务器调用8卡服务端小模型
    根据model_id选择服务器地址：
    - 3007 -> 192.0.2.1:8000
    - 3001-3006 -> 192.0.2.1:8000
    
    注意：这里复用了get_depth_suggestion接口，task_type设置为'question_enhance'。
    如果8卡服务器暂不支持此task_type，可以临时使用'qa'类型，或需要8卡服务器添加对question_enhance任务类型的支持。
    
    格式与get_rel_que.py中的get_depth_suggestion保持一致
    """
    try:
        import subprocess
        import json
        
        # 构造请求数据
        # 将system_prompt和user_prompt合并为完整的输入文本
        full_input_text = f"{system_prompt}\n\n{user_prompt}"
        
        # 处理特殊字符（与get_depth_suggestion格式保持一致）
        full_input_text = full_input_text.replace("\n", "\\n")
        full_input_text = full_input_text.replace('```', '').replace('"""', '').replace('"', '“').replace("'", '‘')
        
        json_data = json.dumps({
            "input_text": full_input_text,
            # "user_name": username.split('_')[0] if '_' in username else username,
            "user_name": username,
            "task_type": "question_enhance"  # 使用专门的任务类型
        }, ensure_ascii=False)  # 保持中文字符

        # 从全局变量获取小模型ID
        server_url = get_small_model_server_url(username)
        # 使用curl命令调用中转服务器的深度建议接口（与get_depth_suggestion格式保持一致）
        # command = f'curl -X POST -H "Content-Type: application/json" -d \'{json_data}\' http://192.0.2.1:8000/get_depth_suggestion'
        command = f'curl -X POST -H "Content-Type: application/json" -d \'{json_data}\' {server_url}/get_depth_suggestion'
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        
        # 解析返回结果
        result_data = json.loads(result.stdout)
        
        if result_data.get('error_num') == 0:
            suggestion = result_data.get('suggestion', '')
            print(f"[_enhance_question_via_relay] 通过中转服务器问题补全成功")
            # 🔥 返回原始文本，由调用方解析新格式
            return suggestion
        else:
            print(f"[_enhance_question_via_relay] 通过中转服务器问题补全失败: {result_data.get('message', '未知错误')}")
            return ''

    except subprocess.CalledProcessError as e:
        print(f"[_enhance_question_via_relay] curl命令执行失败: {e.stderr}")
        return {'enhanced_question': '', 'suggested_sub_scene': None}
    except json.JSONDecodeError as e:
        print(f"[_enhance_question_via_relay] JSON解析失败: {e}")
        return {'enhanced_question': '', 'suggested_sub_scene': None}
    except Exception as e:
        print(f"[_enhance_question_via_relay] 问题补全异常: {e}")
        import traceback
        traceback.print_exc()
        return {'enhanced_question': '', 'suggested_sub_scene': None}


def _enhance_question_via_moonshot(user_prompt, system_prompt):
    """
    直接调用moonshot-v1-8k模型
    """
    try:
        API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://api.deepseek.com",
        )
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,  # 较低温度，确保输出稳定
            max_tokens=800,  # 增加token数量以支持新格式输出（包含问题、核心需求、推荐文档）
        )

        # 🔥 安全地获取响应内容
        if response and response.choices and len(response.choices) > 0:
            enhanced_question_text = response.choices[0].message.content.strip()
            print(f"[_enhance_question_via_deepseek-chat] 直接调用deepseek-chat问题补全成功")
            # 🔥 返回原始文本，由调用方解析新格式
            return enhanced_question_text
        else:
            print(f"[_enhance_question_via_deepseek-chat] ⚠️ 响应格式异常：response为空或choices为空")
            return ''
        
    except Exception as e:
        print(f"[_enhance_question_via_moonshot] 直接调用moonshot失败: {e}")
        import traceback
        traceback.print_exc()
        return ''


def _select_documents_by_keyword(core_keyword, username, model_suggested_docs, all_document_names):
    """
    根据核心关键词，从pre_summary目录查找包含该关键词的文档，并实现文档选择逻辑

    参数:
        core_keyword: 核心关键词（xxx）
        username: 用户名（格式：用户名_本子名）
        model_suggested_docs: 模型推荐的文档名列表（可能包含扩展名或没有扩展名）
        all_document_names: 本子内的所有文档名列表（完整文件名，包含扩展名）

    返回:
        list: 最终推荐的文档名列表（最多6个，若本子内文档总数大于6）
    """
    try:
        # 1. 解析username获取realName和bookName
        if '_' not in username:
            print(f"[_select_documents_by_keyword] ⚠️ username格式不正确: {username}")
            return []

        realName = username.split('_')[0]
        bookName = username[len(realName) + 1:]

        # 2. 构建pre_summary目录路径
        pre_summary_dir = f'./received_dir/user_raw_file/{realName}_{bookName}/pre_summary'

        if not os.path.exists(pre_summary_dir):
            print(f"[_select_documents_by_keyword] ⚠️ pre_summary目录不存在: {pre_summary_dir}")
            return []

        # 3. 生成核心关键词的所有连续子字符串（从最长到最短）
        # 例如："子任务二的设计" -> ["子任务二的设计", "任务二的设计", "子任务二的设", "任务二的设计", "子任务二", ...]
        def generate_substrings(keyword):
            """生成所有连续子字符串，按长度从长到短排序"""
            substrings = []
            keyword_len = len(keyword)
            # 从最长到最短生成所有可能的连续子字符串
            for length in range(keyword_len, 0, -1):  # 从全长到1
                for start in range(keyword_len - length + 1):
                    substr = keyword[start:start + length]
                    if substr not in substrings:
                        substrings.append(substr)
            return substrings

        keyword_substrings = generate_substrings(core_keyword)
        print(f"[_select_documents_by_keyword] 核心关键词: '{core_keyword}', 生成{len(keyword_substrings)}个子字符串: {keyword_substrings[:10]}...")  # 只打印前10个

        # 4. 遍历pre_summary目录中的所有.md文件，查找包含关键词子字符串的文档
        # {文档名: {'score': 总分, 'matches': {子字符串: 出现次数}}}
        doc_scores = {}

        for filename in os.listdir(pre_summary_dir):
            if not filename.endswith('.md'):
                continue

            # 从文件名中提取原文档名（去掉_Presummary_filetype.md后缀）
            # 例如：original_filename_Presummary_filetype.md -> original_filename
            original_doc_name_match = re.match(r'^(.+?)_Presummary_.+\.md$', filename)
            if not original_doc_name_match:
                continue

            original_doc_name = original_doc_name_match.group(1)

            # 读取.md文件内容，统计关键词子字符串出现情况
            file_path = os.path.join(pre_summary_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                    # 统计每个子字符串的出现次数（不区分大小写）
                    matches = {}  # {子字符串: 出现次数}
                    total_score = 0  # 综合得分 = sum(子字符串长度 * 出现次数)

                    for substr in keyword_substrings:
                        # 转义特殊字符用于正则表达式
                        pattern = re.escape(substr)
                        count = len(re.findall(pattern, content, re.IGNORECASE))
                        if count > 0:
                            matches[substr] = count
                            # 得分 = 子字符串长度 * 出现次数（长度越长、频率越高，得分越高）
                            total_score += len(substr) * count

                    if total_score > 0:
                        # 尝试匹配完整的文档名（可能包含扩展名）
                        matched_doc_name = None
                        for doc_name in all_document_names:
                            # 如果original_doc_name是doc_name去掉扩展名后的结果，或者完全匹配
                            if doc_name == original_doc_name or doc_name.startswith(original_doc_name + '.'):
                                matched_doc_name = doc_name
                                break

                        if matched_doc_name:
                            doc_scores[matched_doc_name] = {
                                'score': total_score,
                                'matches': matches
                            }
                        else:
                            # 如果找不到匹配，使用original_doc_name
                            doc_scores[original_doc_name] = {
                                'score': total_score,
                                'matches': matches
                            }
            except Exception as e:
                print(f"[_select_documents_by_keyword] ⚠️ 读取文件失败 {file_path}: {e}")
                continue

        if not doc_scores:
            print(f"[_select_documents_by_keyword] ⚠️ 未找到包含关键词'{core_keyword}'或其子字符串的文档")
            return []

        # 5. 按综合得分由高到低排序（得分 = 子字符串长度 * 频率的总和）
        docs_sorted_by_score = sorted(
            doc_scores.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )
        print(f"[_select_documents_by_keyword] 找到{len(docs_sorted_by_score)}个包含关键词的文档:")
        for name, data in docs_sorted_by_score[:5]:  # 只打印前5个
            print(f"  - {name}: 得分={data['score']}, 匹配项={list(data['matches'].keys())[:3]}...")

        # 5.1 过滤文档：检测明显下降和设置最低分数阈值（严格模式）
        if not docs_sorted_by_score:
            return []

        top_score = docs_sorted_by_score[0][1]['score']
        # 最低分数阈值：第一名得分的40%（更严格）
        min_score_threshold = top_score * 0.4

        filtered_docs = []
        prev_score = top_score

        for doc_name, data in docs_sorted_by_score:
            current_score = data['score']

            # ① 检查是否低于最低分数阈值
            if current_score < min_score_threshold:
                print(f"[_select_documents_by_keyword] ⚠️ 文档 {doc_name} 得分 {current_score} 低于最低阈值 {min_score_threshold:.1f}，跳过")
                break

            # ② 检测明显下降：如果当前得分比前一个得分下降超过50%（即当前得分 < 前一个得分的50%），则停止（更严格）
            if prev_score > 0 and current_score < prev_score * 0.5:
                print(f"[_select_documents_by_keyword] ⚠️ 检测到明显得分下降：{prev_score} -> {current_score}（下降{((prev_score - current_score) / prev_score * 100):.1f}%），停止选择后续文档")
                break

            filtered_docs.append((doc_name, data))
            prev_score = current_score

        docs_sorted_by_score = filtered_docs
        print(f"[_select_documents_by_keyword] 经过过滤后，剩余 {len(docs_sorted_by_score)} 个文档（最低阈值: {min_score_threshold:.1f}）")

        # 6. 标准化模型推荐的文档名（去除扩展名，匹配完整文件名）
        model_suggested_docs_normalized = []
        for model_doc in model_suggested_docs:
            model_doc_clean = model_doc.strip()
            # 去掉扩展名
            model_doc_base = re.sub(r'\.[^.]+$', '', model_doc_clean)
            # 在all_document_names中查找匹配的完整文件名
            for doc_name in all_document_names:
                doc_name_base = re.sub(r'\.[^.]+$', '', doc_name)
                if doc_name_base == model_doc_base or doc_name == model_doc_clean:
                    model_suggested_docs_normalized.append(doc_name)
                    break

        # 7. 实现文档选择逻辑（基于综合得分排序）
        final_documents = []
        max_count = 6 if len(all_document_names) > 6 else len(all_document_names)

        # 7.1 优先选取得分前三的文档
        top_3_docs = [doc_name for doc_name, _ in docs_sorted_by_score[:3]]
        final_documents.extend(top_3_docs)

        # 7.2 从模型输出列表和后端查到列表的交集部分文档中，按得分由高到低地取出
        intersection_docs = []
        for doc_name, data in docs_sorted_by_score:
            if doc_name in model_suggested_docs_normalized and doc_name not in final_documents:
                intersection_docs.append((doc_name, data['score']))

        # 交集文档已经按得分排序（因为docs_sorted_by_score已经排序），直接添加
        for doc_name, _ in intersection_docs:
            if len(final_documents) >= max_count:
                break
            if doc_name not in final_documents:
                final_documents.append(doc_name)

        # 7.3 如果还没达到max_count，从剩余文档中继续添加（按得分排序）
        remaining_docs = [(doc_name, data['score']) for doc_name, data in docs_sorted_by_score if doc_name not in final_documents]
        for doc_name, _ in remaining_docs:
            if len(final_documents) >= max_count:
                break
            final_documents.append(doc_name)

        final_documents = final_documents[:max_count]  # 确保不超过max_count
        print(f"[_select_documents_by_keyword] 最终选择文档: {final_documents}")

        return final_documents

    except Exception as e:
        print(f"[_select_documents_by_keyword] 错误: {e}")
        import traceback
        traceback.print_exc()
        return []
