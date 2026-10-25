# encoding=utf-8
"""
🔥 认知状态分析相关的视图函数
"""
import nkcn_public_config as _public_config
import json
import base64
import asyncio
import subprocess
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
from app_chat.models import Card
from zym.models import scene, UserNotebook
from openai import OpenAI
from llm_langchain import red_bule_rate
from llm_langchain.red_bule_rate import extract_number_SFT, extract_color_SFT, extract_reason_SFT
from dashscope import MultiModalConversation
from app_chat.config.config_manager import config_manager
import re


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


def analyze_cognitive_state_with_tribal_md(username, scene_name, tribal_md, network_image_base64=None):
    """
    基于部落知识md生成认知状态分析卡（内部调用）。
    将部落知识语义层作为额外输入用于认知诊断。
    network_image_base64：关键词节点图（与原有 analyze_cognitive_state 一致，必须传入）。
    """
    try:
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
        notebook_desc = get_notebook_description(username)
        scene_summary, _ = get_scene_summary(scene_name or "", None)
        last_sub_scene_num = 1
        try:
            nb = UserNotebook.objects.get(username=realName, bookName=book_name)
            notebook_desc = nb.bookdescription or notebook_desc
            import pandas as pd
            excel_path = f'./received_dir/scene_excel/{scene_name}/prompt.xlsx'
            if scene_name and os.path.exists(excel_path):
                df = pd.read_excel(excel_path, sheet_name='LUI1')
                if df.shape[1] > 1:
                    sub_list = [df.columns[1]] + df.iloc[:, 1].dropna().tolist()
                    last_sub_scene_num = len(sub_list)
        except Exception:
            pass

        img_note = "\n（下方附有关键词节点图，请结合图片与部落知识语义层进行分析）\n\n" if network_image_base64 else "\n\n"
        user_prompt = f"""基于以下**部落知识语义层**内容，对本子内认知状态进行深度综合分析。{img_note}

**部落知识语义层**含义：由场景子场景下本子内多文档萃取出的升维语义层与部落知识，包含从个别专家中萃取出的可群组性隐性规则、直觉、经验（蛙鸣涌现）、行为逻辑，能关联打通不同文档、回溯源到原文档页数/段落；用四色语境语言与DMT枝-干-根层级（四色指红色：专业知识，蓝：工具手段，紫：思维框架，绿：简单深刻自然；DMT为Down<枝>、Middle<干>、Top<根>，各层次递进清晰且有“其内无小，其外无大”的延展张力）表述，产生类似Palantir的本体论价值；用于指导语义层统一不同文档数据在相同或相关语境下的语义，去除歧义和盲区。

## 场景与本子
- 场景：{scene_name or '未指定'}
- 本子描述：{notebook_desc or '未提供'}
- 场景摘要：{scene_summary[:300] if scene_summary else '未提供'}

## 部落知识语义层（核心输入，用于认知诊断）
{tribal_md[:6000]}{'...(截断)' if len(tribal_md) > 6000 else ''}

## 分析要求
结合部落知识中的隐性规则、行为逻辑、蛙鸣涌现、DMT层次，分析本子内认知推进情况、振荡检测、盲区及内耗区、最近发展区建议。
输出JSON：{{"contentTitle":"Sn:关键词节点图主体性认知推进建议","content":"完整分析内容","humanMachineRatio":"a:b","conclusionReason":"..."}}
"""
        # 默认 claude-sonnet-5，失败再试 4.5 / 4-sonnet
        tribal_model_priority = ["claude-sonnet-5", "claude-sonnet-4.5", "claude-4-sonnet"]
        raw = None
        model_id = None
        for candidate in tribal_model_priority:
            model_config = config_manager.get_model_config(candidate)
            if not model_config:
                continue
            try:
                cur_config = model_config.get_config()
                model_id = model_config.get_model_id()
                client = OpenAI(api_key=cur_config.get("openai_api_key"), base_url=cur_config.get("openai_api_base"))

                # 与原有 analyze_cognitive_state 一致：构建含图片的消息
                user_content = [{"type": "text", "text": user_prompt}]
                if network_image_base64:
                    image_data = network_image_base64
                    if ',' in image_data:
                        image_data = image_data.split(',')[1]
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"}
                    })

                resp = client.chat.completions.create(
                    model=model_config.get_full_name(),
                    messages=[
                        {"role": "system", "content": "你是专业的认知状态分析专家，擅长基于关键词网络图和卡片数据进行深度综合分析。高度结合部落知识语义层进行认知诊断。"},
                        {"role": "user", "content": user_content}
                    ],
                    max_tokens=4000, temperature=0.7, timeout=600
                )
                raw = resp.choices[0].message.content
                print(f"[analyze_cognitive_state_with_tribal_md] 使用{candidate}成功")
                break
            except Exception as e:
                print(f"[analyze_cognitive_state_with_tribal_md] 使用{candidate}失败: {e}")
                continue
        if not raw:
            return
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw, re.DOTALL)
        card_data = json.loads(json_match.group(1)) if json_match else json.loads(raw)
        full_content = card_data.get('content', '')
        if card_data.get('humanMachineRatio'):
            full_content += f"\n\n人机认知比例：{card_data['humanMachineRatio']}"
        if card_data.get('conclusionReason'):
            full_content += f"\n\n为什么可以得出这样的结论：{card_data['conclusionReason']}"

        # 并发打分和红蓝评测（与 analyze_cognitive_state 完全一致）
        async def score_and_evaluate():
            async def get_score():
                try:
                    s, c, r = red_bule_rate.get_rate(username, full_content)
                    return {'error_num': 0, 'score': s, 'color': c, 'reason': r}
                except Exception as e:
                    return {'error_num': 1, 'score': 4.5, 'color': '紫', 'reason': '认知状态深度分析'}
            async def get_evalSFT():
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
                        reasonSFT = extract_reason_SFT(dec) or "认知状态深度分析"
                        if scoreSFT >= 1.0 and colorSFT != "紫":
                            colorSFT = "紫"
                        return {'error_num': 0, 'scoreSFT': scoreSFT, 'colorSFT': colorSFT, 'reasonSFT': reasonSFT}
                    return {'error_num': 1, 'scoreSFT': 4.5, 'colorSFT': '紫', 'reasonSFT': '认知状态深度分析'}
                except Exception:
                    return {'error_num': 1, 'scoreSFT': 4.5, 'colorSFT': '紫', 'reasonSFT': '认知状态深度分析'}
            sr, er = await asyncio.gather(get_score(), get_evalSFT())
            return sr, er

        loop = asyncio.new_event_loop()
        score_result, eval_result = loop.run_until_complete(score_and_evaluate())
        loop.close()
        score = score_result.get('score', 4.5)
        color = score_result.get('color', '紫')
        reason = score_result.get('reason', '认知状态深度分析')
        scoreSFT = eval_result.get('scoreSFT', 4.5)
        colorSFT = eval_result.get('colorSFT', '紫')
        reasonSFT = eval_result.get('reasonSFT', '认知状态深度分析')

        new_card = Card.objects.create(
            username=username,
            model_id=model_id or "1126",
            status="0",
            content=full_content,
            title="关键词节点图主体性认知推进分析卡",
            score=score,
            scoreSFT=scoreSFT,
            color=color,
            colorSFT=colorSFT,
            reason=reason,
            reasonSFT=reasonSFT,
            keyWords="",
            contentTitle=f"S{last_sub_scene_num}:关键词节点图主体性认知推进建议" if last_sub_scene_num > 0 else card_data.get('contentTitle', ''),
            type="永久",
            postIndex="",
            four_color_type="P",
            dmt_level="T",
            is_neuron=True,
            is_analyzed_by_new_standard=True,
        )
        # 保存关键词网络图（与原有 analyze_cognitive_state 一致）
        if network_image_base64:
            try:
                image_dir = f'./received_dir/user_raw_file/{username}/cardImage'
                os.makedirs(image_dir, exist_ok=True)
                image_path = os.path.join(image_dir, f'{new_card.cid}.png')
                image_data = network_image_base64
                if ',' in image_data:
                    image_data = image_data.split(',')[1]
                image_bytes = base64.b64decode(image_data)
                with open(image_path, 'wb') as f:
                    f.write(image_bytes)
                print(f"[analyze_cognitive_state_with_tribal_md] 关键词网络图已保存: {image_path}")
            except Exception as e:
                print(f"[analyze_cognitive_state_with_tribal_md] 保存网络图失败: {e}")
        print("[analyze_cognitive_state_with_tribal_md] 认知状态分析卡已创建")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[analyze_cognitive_state_with_tribal_md] 失败: {e}")


@csrf_exempt
def analyze_cognitive_state(request):
    """
    🔥 分析认知状态API
    根据关键词网络图和卡片数据，使用gemini-3.1-pro-preview进行深度综合分析
    """
    try:
        # 获取参数（JSON格式）
        data = json.loads(request.body)
        network_image_base64 = data.get('network_image', '')
        data_source_info = data.get('data_source_info', {})
        username = data.get('username', '')
        scene_name = data.get('scene_name', '')
        sub_scene_name = data.get('sub_scene_name', '')
        is_group_notebook = data.get('is_group_notebook', False)
        origin_real_name = data.get('origin_real_name', '')

        if not username or not data_source_info:
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

        # 2.1 获取最后一个子场景的编号和名称（参考generate_permanent_card的逻辑）
        last_sub_scene = sub_scene_name or ""
        last_sub_scene_num = 0  # 最后一个子场景的编号（从1开始）
        if scene_name:
            try:
                import os
                import pandas as pd
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
                        print(f"[analyze_cognitive_state] 最后一个子场景编号: {last_sub_scene_num}, 名称: {last_sub_scene}")
            except Exception as e:
                print(f"[analyze_cognitive_state] 从excel获取子场景信息失败: {e}")

        # 3. 构建关键词网络图数据文本
        keywords_info = ""
        if data_source_info.get('keywords'):
            keywords_info = "\n## 关键词节点信息：\n"
            for kw in data_source_info['keywords']:
                four_color_desc = {
                    'R': '红色专业业务',
                    'B': '蓝色工具手段',
                    'P': '紫色思维框架',
                    'G': '绿色简单深刻'
                }.get(kw.get('four_color_type', ''), '未设置')

                dmt_desc = {
                    'D': '枝（具体执行层）',
                    'M': '干（中等关联层）',
                    'T': '根（抽象框架层）'
                }.get(kw.get('dmt_level', ''), '未设置')

                keywords_info += f"- {kw.get('label', '')}: 频率={kw.get('frequency', 0)}, 四色={four_color_desc}, DMT={dmt_desc}\n"

        # 4. 构建QA问题链信息
        qa_chain_info = ""
        if data_source_info.get('qa_questions_chain'):
            if is_group_notebook:
                # 🔥 组本：按作者分组显示问题链
                qa_chain_info = "\n## QA问答卡问题链（按作者和时间顺序）：\n"
                # 按作者分组
                qa_by_writer = {}
                for qa in data_source_info['qa_questions_chain']:
                    writer = qa.get('writer', '')
                    if writer:
                        writer_name = writer.split('_')[0] if '_' in writer else writer
                    else:
                        writer_name = '未知作者'

                    if writer_name not in qa_by_writer:
                        qa_by_writer[writer_name] = []

                    sub_scene = qa.get('sub_scene', '')
                    datetime_str = qa.get('datetime', '')
                    question = qa.get('question', '')
                    qa_by_writer[writer_name].append({
                        'sub_scene': sub_scene,
                        'datetime': datetime_str,
                        'question': question
                    })

                # 按作者分组输出，每个作者内按时间排序
                for writer_name, qa_list in sorted(qa_by_writer.items()):
                    qa_list.sort(key=lambda x: x['datetime'] or '')
                    qa_chain_info += f"\n### 作者：{writer_name}\n"
                    for idx, qa in enumerate(qa_list, 1):
                        qa_chain_info += f"  {idx}. [{qa['sub_scene']}] [{qa['datetime']}] {qa['question']}\n"
            else:
                # 个人本子：保持原逻辑
                qa_chain_info = "\n## QA问答卡问题链（按时间顺序）：\n"
                for idx, qa in enumerate(data_source_info['qa_questions_chain']):
                    sub_scene = qa.get('sub_scene', '')
                    datetime_str = qa.get('datetime', '')
                    question = qa.get('question', '')
                    qa_chain_info += f"{idx + 1}. [{sub_scene}] [{datetime_str}] {question}\n"

        # 4.5 🔥 若存在部落知识md，作为额外输入
        tribal_md_extra = ""
        try:
            from app_chat.views_tribal_knowledge import _read_tribal_md
            tmd = _read_tribal_md(username)
            if tmd:
                tribal_md_extra = f"""

                ## 部落知识语义层（额外输入，用于认知诊断）
                **含义**：由场景子场景下本子内多文档萃取出的升维语义层与部落知识，包含隐性规则、直觉、经验（蛙鸣涌现）、行为逻辑，能关联打通不同文档、回溯源到原文档页数/段落/知识/概念/定义；用四色语境语言与DMT枝-干-根层级表述；用于指导语义层统一不同文档数据在相同或相关语境下的语义，去除歧义和盲区（不同文档来源的数据和知识之间互为盲区的情况）。认知诊断时需结合此内容分析本子内认知推进、振荡、盲区、最近发展区。

                **内容**：
                {tmd[:4000]}{'...(截断)' if len(tmd) > 4000 else ''}
                """
        except Exception:
            pass

        # 5. 构建完整的user_prompt
        group_notebook_note = ""
        if is_group_notebook:
            group_notebook_note = "\n**重要提示：这是群组本子，数据中包含多个不同作者的内容。问题链已按作者分组显示。你需要分别分析每个作者的认知状态、问题链演进、认知推进情况、振荡情况、盲区和内耗区，然后综合考虑所有作者的整体认知状态，给出综合分析和建议。**\n"

        user_prompt = f"""你需要基于以下关键词网络图（图片）和数据来源信息（文本），对{"群组本子中所有使用者" if is_group_notebook else "个人本子"}的认知状态进行深度综合分析。
{group_notebook_note}
## 场景上下文
- 场景名：{scene_name}
- 子场景：{last_sub_scene}
- 本子名（中文）：{data_source_info.get('notebook_name', '')}
- 本子描述：{notebook_desc[:500] if notebook_desc else '未提供'}
- 场景摘要：{final_scene_summary[:500] if final_scene_summary else '未提供'}
{tribal_md_extra}

{keywords_info}

{qa_chain_info}

## 分析要求

### 1. 理解四色、DMT等内涵
- **四色类型**：
  - 红色（专业业务）：行业专业性、业务知识
  - 蓝色（工具手段）：技术工具、方法手段
  - 紫色（思维框架）：场景思维、认知框架
  - 绿色（简单深刻）：自然语言、简单深刻的理解
- **DMT层次**（枝/干/根三层逻辑，是相对而非绝对的，以小中大为例，小还可以有更小，大还可以有更大，所以用枝/干/根，枝还可以更末端到叶，根还可以更底层到须）：
  - 枝：具体执行层，操作性知识性内容
  - 干：中等关联层，策略性方法性内容
  - 根：抽象框架层，框架性思维性内容

**重要提醒**：在生成内容时，不要直接使用"R"、"B"、"P"、"G"、"D"、"M"、"T"等字母，而要使用完整的描述，如"红色专业业务"、"蓝色工具手段"、"紫色思维框架"、"绿色简单深刻"、"枝"、"干"、"根"。

### 2. 时间线分析
- 从S1-Sn推进来看：分析子场景的推进情况
- 从datetime时间线来看：分析问题链的时间分布和演进

### 3. 问题链深度分析
{"**对于群组本子，问题链已按作者分组。你需要分别分析每个作者的问题链，然后进行综合对比分析：**" if is_group_notebook else ""}
- **认知推进情况**：{"每个作者是否有明显的认知推进？不同作者之间的认知推进有何差异？整体是否有推进？" if is_group_notebook else "是否有明显的认知推进？问题是否在逐步深入？"}
- **振荡检测**：{"每个作者是否有产生振荡？即是否在相同或相似问题上反复，甚至自己颠覆或推翻自己？不同作者之间有何差异？" if is_group_notebook else "是否有产生振荡？即是否在相同或相似问题上反复，甚至自己颠覆或推翻自己？"}
- **情绪问题**：{"每个作者是否可能存在情绪问题？从问题的表达方式、重复程度等判断" if is_group_notebook else "是否可能存在情绪问题？从问题的表达方式、重复程度等判断"}

### 4. 目标完成情况
- 根据本子名（{data_source_info.get('notebook_name', '')}）综合体现的目标，评估完成情况如何

### 5. 盲区及内耗区分析
{"**对于群组本子，需要分别分析每个作者的盲区和内耗区，然后识别整体共同的盲区和内耗区：**" if is_group_notebook else ""}
- **盲区**：{"每个作者是否存在明显的认知盲区（不知道自己不知道）？哪些概念或认知角度明显缺失？不同作者之间有何差异？整体有共同盲区吗？" if is_group_notebook else "是否存在明显的认知盲区？哪些概念或认知角度明显缺失？（不知道自己不知道）"}
- **内耗区**：{"每个作者是否存在内耗区？是否在某个问题上反复纠结、无法突破？不同作者之间的内耗区有何差异？整体是否存在共同的内耗区？" if is_group_notebook else "是否存在内耗区？是否在某个问题上反复纠结、无法突破？（这非常重要！）"}

### 6. 最近发展区建议
- **若没有盲区/内耗区**：应该如何进一步深入？给出下一步的建议
- **若有盲区/内耗区**：如何找到"最近发展区"？
  - 这非常重要！！一定要帮助使用者走出自我振荡/内耗/盲区（特别是有中重度盲区倾向的）
  - 给出最近的、在现有状态下最可能达到的、对改变现状最直接有效的建议
  - 附以适度且精准精炼的原因解释
  - 让使用者感到醍醐灌顶，是其想不到但非常贴近其当前状况的
  - 让使用者觉得真正对解决其目前遇到的困境有显著的帮助和价值
  - **一定要具体到使用者最近的一到三步优先级应该具体做什么或问什么**

## 输出格式

请严格按照以下JSON格式输出：

```json
{{
    "contentTitle": "Sn:关键词节点图主体性认知推进建议",
    "content": "完整的分析内容（包括：认知推进情况、振荡检测、情绪问题、目标完成情况、盲区及内耗区分析、最近发展区建议等，要求深入、具体、有针对性）",
    "humanMachineRatio": "人机认知比例，例如：7:3",
    "conclusionReason": "为什么可以得出这样的结论（30字以内）"
}}
```

**重要提醒**：
1. 分析必须深入、具体、有针对性
2. 对于有中重度盲区倾向的，必须给出具体的一到三步优先级建议
3. 建议必须让使用者感到醍醐灌顶，真正对解决困境有显著帮助
4. 内容要具体到使用者最近应该具体做什么或问什么
5. 即使给你的信息不完全完整，也要基于已有的信息，尽可能完善地完成分析
"""

        # 6. 调用LLM API（默认claude-sonnet-5 → 4.5 → 4-sonnet，再降级 gemini / qwen）
        response_content = None
        model_id = None
        model_name = None
        claude_ok = False

        # 6.1 优先 Claude 链（均支持图片）
        from app_chat.core.model_manager import model_manager
        from app_chat.config.config_manager import config_manager
        claude_priority = ["claude-sonnet-5", "claude-sonnet-4.5", "claude-4-sonnet"]
        for candidate in claude_priority:
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

                user_content = [
                    {
                        "type": "text",
                        "text": user_prompt
                    }
                ]

                if network_image_base64:
                    image_data = network_image_base64
                    if ',' in image_data:
                        image_data = image_data.split(',')[1]

                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        }
                    })
                    print(f"[analyze_cognitive_state] 添加图片到{model_name}请求，图片数据长度: {len(image_data)}")
                else:
                    print(f"[analyze_cognitive_state] 警告：network_image_base64为空，{model_name}将只接收文本")

                response = client.chat.completions.create(
                    model=full_model_name,
                    messages=[
                        {"role": "system", "content": "你是专业的认知状态分析专家，擅长基于关键词网络图和卡片数据进行深度综合分析。"},
                        {"role": "user", "content": user_content}
                    ],
                    max_tokens=hyper_para.max_tokens,
                    temperature=hyper_para.temperature,
                    timeout=900  # 900秒超时
                )
                response_content = response.choices[0].message.content
                claude_ok = True
                print(f"[analyze_cognitive_state] 使用{model_name}成功" + (", 包含图片" if network_image_base64 else ", 无图片"))
                break
            except Exception as e:
                print(f"[analyze_cognitive_state] 使用{model_name}失败: {e}")
                continue

        if not claude_ok:
            # 6.2 降级使用gemini-3.1-pro-preview（支持图片）
            try:
                model_name = "gemini-3.1-pro-preview"
                client = OpenAI(
                    api_key=_public_config.secret('NKCN_LLM_DMXAPI_API_KEY'),
                    base_url=_public_config.endpoint('NKCN_REVIEW_GATEWAY_V1_URL', 'http://localhost:9999/v1/')
                )

                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt
                            }
                        ]
                    }
                ]

                # 如果有图片，添加到消息中
                if network_image_base64:
                    # 移除data:image/png;base64,前缀（如果有）
                    image_data = network_image_base64
                    if ',' in image_data:
                        image_data = image_data.split(',')[1]

                    messages[0]["content"].append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        }
                    })

                response = client.chat.completions.create(
                    model="gemini-3.1-pro-preview",
                    messages=messages,
                    max_tokens=4000,
                    temperature=0.7,
                    timeout=900  # 900秒超时
                )

                response_content = response.choices[0].message.content
                model_id = "gemini-3.1-pro-preview"
                print(f"[analyze_cognitive_state] 使用{model_name}成功")

            except Exception as e2:
                print(f"[analyze_cognitive_state] 使用{model_name}也失败: {e2}")
                # 6.3 再次降级使用qwen3.6-plus（支持图片）
                try:
                    model_name = "qwen3.6-plus"
                    model_id = "qwen3.6-plus"

                    # 准备图片数据
                    image_data_for_qwen = None
                    if network_image_base64:
                        # 移除data:image/png;base64,前缀（如果有）
                        image_data_for_qwen = network_image_base64
                        if ',' in image_data_for_qwen:
                            image_data_for_qwen = image_data_for_qwen.split(',')[1]
                        print(f"[analyze_cognitive_state] 添加图片到qwen3.6-plus请求，图片数据长度: {len(image_data_for_qwen)}")
                    else:
                        print(f"[analyze_cognitive_state] 警告：network_image_base64为空，qwen3.6-plus将只接收文本")

                    # 构建qwen-vl的消息格式
                    messages = [
                        {"role": "system", "content": [{"text": "你是专业的认知状态分析专家，擅长基于关键词网络图和卡片数据进行深度综合分析。"}]},
                        {'role': 'user', 'content': []}
                    ]

                    # 如果有图片，添加到消息中（qwen-vl格式）
                    if image_data_for_qwen:
                        messages[1]['content'].append({"image": f"data:image/png;base64,{image_data_for_qwen}"})

                    # 添加文本内容
                    messages[1]['content'].append({'text': user_prompt})

                    # 使用MultiModalConversation.call，设置900秒超时（使用concurrent.futures）
                    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

                    def call_qwen():
                        return MultiModalConversation.call(
                            api_key=_public_config.secret('NKCN_LLM_DASHSCOPE_API_KEY'),
                            model='qwen3.6-plus',
                            messages=messages,
                            vl_high_resolution_images=True
                        )

                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(call_qwen)
                        try:
                            response = future.result(timeout=900.0)
                            # 解析响应
                            response_content = response["output"]["choices"][0]["message"].content[0]["text"]
                            print(f"[analyze_cognitive_state] 使用{model_name}成功" + (
                                ", 包含图片" if image_data_for_qwen else ", 无图片"))
                        except FutureTimeoutError:
                            raise TimeoutError("qwen3.6-plus请求超时（900秒）")

                except Exception as e3:
                    print(f"[analyze_cognitive_state] 使用{model_name}也失败: {e3}")
                    import traceback
                    traceback.print_exc()
                    return JsonResponse({
                        'error_num': 1,
                        'msg': f'LLM调用失败: {str(e3)}'
                    })

        if not response_content:
            return JsonResponse({
                'error_num': 1,
                'msg': 'LLM未返回内容'
            })

        # 7. 解析LLM返回的JSON
        try:
            # 尝试提取JSON部分
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_content, re.DOTALL)
            if json_match:
                card_data = json.loads(json_match.group(1))
            else:
                # 尝试直接解析整个响应
                card_data = json.loads(response_content)
        except Exception as e:
            print(f"[analyze_cognitive_state] JSON解析失败: {e}")
            print(f"[analyze_cognitive_state] 响应内容: {response_content}")
            return JsonResponse({
                'error_num': 1,
                'msg': f'解析LLM响应失败: {str(e)}'
            })

        # 8. 构建完整的卡片内容（先构建，用于评分）
        full_content = card_data.get('content', '')
        if card_data.get('humanMachineRatio'):
            full_content += f"\n\n人机认知比例：{card_data['humanMachineRatio']}"
        if card_data.get('conclusionReason'):
            full_content += f"\n\n为什么可以得出这样的结论：{card_data['conclusionReason']}"

        # 9. 🔥 并发执行打分和红蓝评测（参考generate_permanent_card的逻辑）
        async def score_and_evaluate():
            tasks = []

            # 1. 打分任务（使用red_bule_rate.get_rate）
            async def get_score():
                try:
                    score, color, reason = red_bule_rate.get_rate(username, full_content)
                    return {'error_num': 0, 'score': score, 'color': color, 'reason': reason}
                except Exception as e:
                    print(f"[analyze_cognitive_state] 获取score/color/reason失败: {e}")
                    return {'error_num': 1, 'error': str(e)}

            # 2. 红蓝评测任务（使用execute_commands的逻辑）
            async def get_evalSFT():
                try:
                    # 模拟execute_commands的调用
                    text = full_content.replace("\n", "\\n")
                    # command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","text":"{text}"}}\' http://localhost:8000/invoke_rate'
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
                        reasonSFT = extract_reason_SFT(decoded_result) or "认知状态深度分析"
                        if scoreSFT >= 1.0 and colorSFT != "紫":
                            colorSFT = "紫"
                        return {'error_num': 0, 'scoreSFT': scoreSFT, 'colorSFT': colorSFT, 'reasonSFT': reasonSFT}
                    else:
                        return {'error_num': 1, 'error': '红蓝评测结果为fail'}
                except Exception as e:
                    print(f"[analyze_cognitive_state] 获取scoreSFT/colorSFT/reasonSFT失败: {e}")
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
        print(f"[analyze_cognitive_state] 开始调用模型获取score/color/reason和scoreSFT/colorSFT/reasonSFT...")
        try:
            loop = asyncio.new_event_loop()
            score_result, eval_result = loop.run_until_complete(score_and_evaluate())
            loop.close()
        except Exception as e:
            print(f"[analyze_cognitive_state] 并发执行评分失败: {e}")
            import traceback
            traceback.print_exc()
            score_result = {'error_num': 1}
            eval_result = {'error_num': 1}

        # 获取评分结果
        if score_result.get('error_num') == 0:
            score = score_result.get('score', 4.5)
            color = score_result.get('color', '紫')
            reason = score_result.get('reason', '认知状态深度分析')
            print(f"[analyze_cognitive_state] score={score}, color={color}, reason={reason[:50]}...")
        else:
            score = 4.5
            color = "紫"
            reason = "认知状态深度分析"
            print(f"[analyze_cognitive_state] 获取score/color/reason失败，使用默认值")

        if eval_result.get('error_num') == 0:
            scoreSFT = eval_result.get('scoreSFT', 4.5)
            colorSFT = eval_result.get('colorSFT', '紫')
            reasonSFT = eval_result.get('reasonSFT', '认知状态深度分析')
            print(f"[analyze_cognitive_state] scoreSFT={scoreSFT}, colorSFT={colorSFT}, reasonSFT={reasonSFT[:50]}...")
        else:
            scoreSFT = 4.5
            colorSFT = "紫"
            reasonSFT = "认知状态深度分析"
            print(f"[analyze_cognitive_state] 获取scoreSFT/colorSFT/reasonSFT失败，使用默认值")

        # 10. 保存新卡片到数据库
        new_card = Card.objects.create(
            username=username,
            model_id=model_id or "1126",  # 使用实际调用的模型ID
            status="0",
            content=full_content,
            title="关键词节点图主体性认知推进分析卡",
            score=score,  # 使用模型获取的评分
            scoreSFT=scoreSFT,  # 使用模型获取的SFT评分
            color=color,  # 使用模型获取的颜色
            colorSFT=colorSFT,  # 使用模型获取的SFT颜色
            reason=reason,  # 使用模型获取的理由
            reasonSFT=reasonSFT,  # 使用模型获取的SFT理由
            keyWords="",  # 分析卡片可能不关联特定关键词
            contentTitle=f"S{last_sub_scene_num}:关键词节点图主体性认知推进建议" if last_sub_scene_num > 0 else card_data.get(
                'contentTitle', last_sub_scene),
            type="永久",
            postIndex="",
            four_color_type="P",  # 分析卡片通常是思维框架类型
            dmt_level="T",  # 分析卡片通常是抽象框架层
            is_neuron=True,  # 标记为神经元卡
            is_analyzed_by_new_standard=True,  # 🔥 已按新标准分析，避免刷新后重新分析覆盖
            # writer=origin_real_name if is_group_notebook and origin_real_name else realName
        )

        # 11. 保存关键词网络图到指定路径
        if network_image_base64:
            try:
                # 构建图片保存路径：received_dir\user_raw_file\用户名_本子英文名\cardImage\cid.png
                image_dir = f'./received_dir/user_raw_file/{username}/cardImage'
                os.makedirs(image_dir, exist_ok=True)
                image_path = os.path.join(image_dir, f'{new_card.cid}.png')

                # 移除data:image/png;base64,前缀（如果有）
                image_data = network_image_base64
                if ',' in image_data:
                    image_data = image_data.split(',')[1]

                # 解码Base64并保存为PNG文件
                image_bytes = base64.b64decode(image_data)
                with open(image_path, 'wb') as f:
                    f.write(image_bytes)

                print(f"[analyze_cognitive_state] 关键词网络图已保存到: {image_path}")
            except Exception as e:
                print(f"[analyze_cognitive_state] 保存关键词网络图失败: {e}")
                import traceback
                traceback.print_exc()

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'card_id': new_card.cid,
            'contentTitle': new_card.contentTitle
        })

    except Exception as e:
        print(f"[analyze_cognitive_state] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'分析失败: {str(e)}'
        })

