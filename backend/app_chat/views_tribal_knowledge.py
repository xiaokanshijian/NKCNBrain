# encoding=utf-8
"""
🔥 部落知识语义层萃取相关视图
"""
import json
import os
import re
import threading
import uuid
import time
import pandas as pd
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI
from app_chat.config.config_manager import config_manager
from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
from app_chat.models import Card
from zym.models import scene, UserNotebook
from llm_langchain import global_var


# 重试模型优先级：优先 Sonnet 5，再 4.5 / 4 Sonnet，最后 3.7 / 3.5
_TRIBAL_LLM_MODEL_PRIORITY = [
    'claude-sonnet-5', 'claude-sonnet-5',  # 优先5，失败再试一次5
    'claude-sonnet-4.5', 'claude-sonnet-4.5',
    'claude-4-sonnet', 'claude-4-sonnet',
    'claude-3.7', 'claude-3.7',
    'claude-3.5'
]
_TIMEOUT_SEC = 900
_MAX_RETRIES = 10


def _call_llm_with_retry(system_prompt, user_prompt, use_thinking=False):
    """调用LLM，按方案重试机制。超时直接中止当次调用。"""
    tried_4_5 = 0
    tried_4 = 0
    tried_3_7 = 0
    retry_3_5_count = 0

    for model_name in _TRIBAL_LLM_MODEL_PRIORITY:
        try:
            model_config = config_manager.get_model_config(model_name)
            if not model_config:
                continue
            cur_config = model_config.get_config()
            api_key = cur_config.get("openai_api_key")
            base_url = cur_config.get("openai_api_base")
            full_model_name = model_config.get_full_name()
            hyper_para = model_config.get_hyper_para()

            client = OpenAI(api_key=api_key, base_url=base_url)
            start = time.time()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            resp = client.chat.completions.create(
                model=full_model_name,
                messages=messages,
                timeout=_TIMEOUT_SEC,
                max_tokens=hyper_para.max_tokens,
                temperature=hyper_para.temperature
            )
            elapsed = time.time() - start
            if elapsed > _TIMEOUT_SEC:
                print(f"[tribal_llm] {model_name} 超时({elapsed:.1f}s)，中止当次调用")
                continue

            return resp.choices[0].message.content.strip(), model_name
        except Exception as e:
            err = str(e).lower()
            if 'timeout' in err or 'timed out' in err:
                print(f"[tribal_llm] {model_name} 超时失败: {e}")
            else:
                print(f"[tribal_llm] {model_name} 失败: {e}")

    # 4.5/4/3.7 都试过后，用 3.5 重试最多10次
    for _ in range(_MAX_RETRIES):
        try:
            model_config = config_manager.get_model_config('claude-3.5')
            if not model_config:
                break
            cur_config = model_config.get_config()
            client = OpenAI(api_key=cur_config.get("openai_api_key"), base_url=cur_config.get("openai_api_base"))
            resp = client.chat.completions.create(
                model=model_config.get_full_name(),
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                timeout=_TIMEOUT_SEC,
                max_tokens=model_config.get_hyper_para().max_tokens,
                temperature=model_config.get_hyper_para().temperature
            )
            return resp.choices[0].message.content.strip(), 'claude-3.5'
        except Exception as e:
            retry_3_5_count += 1
            print(f"[tribal_llm] claude-3.5 第{retry_3_5_count}次失败: {e}")
    return None, None


def _get_tribal_md_path(username):
    """返回 TribalKnowledgeSemanticLayer.md 的路径。目录用 realName_bookName，文件名用 bookName。"""
    realName = username.split('_')[0] if '_' in username else username
    bookName = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
    if not bookName:
        return None, None
    base = f'./received_dir/user_raw_file/{realName}_{bookName}'
    return f"{base}/pre_tribal_knowledge/{bookName}_TribalKnowledgeSemanticLayer.md", (realName, bookName)


def _read_tribal_md(username):
    """读取部落知识 md 内容。"""
    path, _ = _get_tribal_md_path(username)
    if not path or not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def extract_notebook_tribal_knowledge_semantic_layer(username, task_id=None):
    """
    萃取本子部落知识语义层。
    输入：场景摘要、本子中文名(bookdescription)、pre_summary、pre_image_summary
    输出：写入 pre_tribal_knowledge/本子名_TribalKnowledgeSemanticLayer.md
    """
    realName = username.split('_')[0] if '_' in username else username
    bookName = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
    if not bookName:
        return False, "无法解析本子名"

    notebook_desc = get_notebook_description(username)
    scene_name = None
    try:
        scene_obj = scene.objects.get(sid=UserNotebook.objects.get(username=realName, bookName=bookName).sid)
        scene_name = scene_obj.sceneDescription
    except Exception:
        pass

    scene_summary, _ = get_scene_summary(scene_name or "", None)
    all_subscenes = ""
    if scene_name:
        try:
            excel_path = f'./received_dir/scene_excel/{scene_name}/prompt.xlsx'
            if os.path.exists(excel_path):
                df = pd.read_excel(excel_path, sheet_name='LUI1')
                if df.shape[1] > 1:
                    first_col = df.columns[1]
                    sub_list = df.iloc[:, 1].dropna().tolist()
                    sub_list_order = [first_col] + sub_list
                    all_subscenes = "\n## 子场景摘要：\n"
                    for i, sn in enumerate(sub_list_order, 1):
                        _, sub_sum = get_scene_summary(scene_name, sn)
                        sub_sum = (sub_sum or "")[:80] + ("..." if len(sub_sum or "") > 80 else "")
                        all_subscenes += f"- S{i}: {sn} - {sub_sum}\n"
        except Exception as e:
            print(f"[tribal] 读取子场景失败: {e}")

    base_dir = f'./received_dir/user_raw_file/{realName}_{bookName}'
    pre_summary_dir = f'{base_dir}/pre_summary'
    pre_image_dir = f'{base_dir}/pre_image_summary'

    pre_summary_text = ""
    if os.path.exists(pre_summary_dir):
        for f in os.listdir(pre_summary_dir):
            if f.endswith('_Presummary_pdf.md') or f.endswith('_Presummary_txt.md'):
                with open(os.path.join(pre_summary_dir, f), 'r', encoding='utf-8') as fp:
                    pre_summary_text += f"\n\n### 文档 {f}\n" + fp.read()

    pre_image_text = ""
    if os.path.exists(pre_image_dir):
        for f in os.listdir(pre_image_dir):
            if f.endswith('_PreImageSummary_pdf.md'):
                with open(os.path.join(pre_image_dir, f), 'r', encoding='utf-8') as fp:
                    pre_image_text += f"\n\n### 图片摘要 {f}\n" + fp.read()

    if not pre_summary_text and not pre_image_text:
        return False, "无 pre_summary 或 pre_image_summary 内容"

    # 步骤1：小模型快速梳理（可选，此处用大模型一并完成以简化）
    # 步骤2：Claude 第一步 - 升维语义层 + 萃取的部落知识（使用完整人性化思考协议）
    from app_chat.views import system_prompt_claude
    sys1 = system_prompt_claude + """

## 你的角色与任务
你是领域知识萃取专家。基于场景、本子目标、文档摘要与图片摘要，萃取「升维语义层描述」和「萃取的部落知识」，产生类似Palantir的本体论价值。

## 核心理解（务必深刻领会）
1. **本体论≠增强版知识图谱**：传统知识图谱关注数据是什么、如何连接、静态关系，局限于"看"和"分析"。部落知识萃取更关注**动态行为和过程**，在"看"和"分析"基础上支撑"做"和"执行"——是什么行为导致形成数据结果？什么显性或隐性规则驱动数据流转？能做什么及如何做？如何将隐性的专家-群组经验和直觉转化沉淀为可解释和执行的规则与行为？

2. **升维语义层**：如基因本体用一套术语统一描述生物体中基因和蛋白质功能——生物无比复杂，却能从更高维度统一。认知低则不能解释万千生物为何遵循类似进化和生存规律，而合适的升维考虑就能解释。本子内各类文档知识也需建立类似升维语义层，通过可解释可复用的具体行为过程性主导的全面思考，萃取出能统一此场景子场景下本子内语义语境的个人-群组部落知识。

3. **部落知识本质**：隐性规则、直觉、经验即需萃取的部落知识，将一部分专家个体的这些隐性知识提炼出可群组性部落知识；四色DMT化（四色指红色：专业知识，蓝：工具手段，紫：思维框架，绿：简单深刻自然；DMT为Down<枝>、Middle<干>、Top<根>，各层次递进清晰且有“其内无小，其外无大”的延展张力）的部落知识即运用除法则找到本元。萃取出的部落知识应包含提出/发现者自己都可能说不清、复述不出的「蛙鸣涌现」——这是验证萃取得是否对、是否精的标准。

4. **必须做到**：关联打通不同文档数据/知识形成统一语义；萃取部落知识的同时能回溯源到原文档页数、段落、知识/概念/定义，产生本体论价值；用合适的四色语境语言、DMT层级表述和标识；**强烈避免虚伪浮夸**；**全文70-80%以上都应该是原文素材中直接找不到的内容**——用户对原文已基本清楚，是萃取部落知识拔升，不是在复述和复习，**一定避免复述原文里显性已有的知识和思想**，萃取出真正有用的新东西。

## 输出格式（严格遵守，不要输出关键词列表，后续会单独提取）
## 升维语义层描述
（内容：统一本子内多文档语义的元描述，与基因本体类比说明）

## 萃取的部落知识
### 隐性规则与行为逻辑
- [规则1] 溯源：文档A第3-5页、文档B第7页...
### 行为过程
- ..."""
    user1 = f"""## 输入材料

**场景**：{scene_name or '未指定'}
**场景摘要**：{scene_summary or '无'}
**本子中文名/目标**：{notebook_desc or '无'}
{all_subscenes}

**文档摘要**：
{pre_summary_text[:12000]}{'...(截断)' if len(pre_summary_text) > 12000 else ''}

**图片摘要**：
{pre_image_text[:6000]}{'...(截断)' if len(pre_image_text) > 6000 else ''}

请按前述要求，先进行 thinking 和 checking，最后输出升维语义层描述与萃取的部落知识（不包含关键词列表）。"""
    if task_id and task_id in global_var.tasks:
        global_var.tasks[task_id]['current_section'] = '萃取部落知识主体'
    content1, _ = _call_llm_with_retry(sys1, user1)
    if not content1:
        return False, "第一步萃取失败"

    def _clean_thinking(t):
        for pat in [r'```thinking\s*\n.*?```', r'```checking\s*\n.*?```']:
            t = re.sub(pat, '', t, flags=re.DOTALL | re.IGNORECASE)
        return t.strip()

    part1 = _clean_thinking(content1)
    if not part1.startswith('# '):
        part1 = "## 升维语义层描述\n\n" + part1

    # 步骤3：Claude 第二步 - 专门提取关键词列表（四色、DMT、溯源、关联原有关键词）
    if task_id and task_id in global_var.tasks:
        global_var.tasks[task_id]['current_section'] = '提取关键词列表'
    existing_keywords = []
    try:
        nb = UserNotebook.objects.get(username=realName, bookName=bookName)
        kfd = json.loads(nb.keywordFourColorDMT or '{}')
        existing_keywords = [k for k, v in kfd.items() if not (isinstance(v, dict) and v.get('is_tribal'))]
    except Exception:
        pass
    existing_kw_str = "、".join(existing_keywords[:150]) if existing_keywords else "（暂无，可留空）"
    sys2 = f"""你是关键词与四色DMT标注专家。根据上文部落知识内容，提取关键词列表。

要求：关键词个数控制在6-9个为宜，不得超过10个；关键词须有实际熟知意义、既抽象又具象价值、覆盖完整；每个关键词需有四色/DMT标识；溯源到文档名+页数，若不确定则溯源到知识/概念/定义。
部落关键词应作为核心关键词，与节点图中较为重要的原有关键词建立语义关联连线。**关联原有关键词**必须从下方原有关键词列表中选取，每个部落关键词填2个与之语义关联最强的原有关键词（用中文顿号分隔），须真正有语义关联如D-M-T递进关系，而非随便连。
四色：R(红/专业业务)、B(蓝/工具手段)、P(紫/思维框架)、G(绿/简单深刻自然)
DMT：D(枝/具体执行层)、M(干/中等关联层)、T(根/抽象框架层)，枝-干-根层次清晰（"其内无小，其外无大"）

原有关键词列表（从中选2个填关联）：{existing_kw_str}

格式为 Markdown 表格：
## 关键词列表（四色/DMT/溯源/关联原有关键词）
| 关键词 | 四色 | DMT | 溯源 | 关联原有关键词 |
|--------|------|-----|------|----------------|
| xxx | R | M | 文档A p3-5 知识/概念/定义 | 原有关键词A、原有关键词B |

只输出表格，不要其他说明。"""
    content2, _ = _call_llm_with_retry(sys2, "上文部落知识内容：\n\n" + part1[:8000])
    if not content2:
        return False, "第二步关键词提取失败"

    # 合并写入
    full_md = part1 + "\n\n" + content2
    out_dir = f'{base_dir}/pre_tribal_knowledge'
    os.makedirs(out_dir, exist_ok=True)
    out_path = f'{out_dir}/{bookName}_TribalKnowledgeSemanticLayer.md'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("# 本子部落知识语义层\n\n" + full_md)

    # 解析关键词并写入 keywordFourColorDMT，同时更新 keywordFusionRelations 建立部落关键词与原有关键词的语义连线
    keywords_parsed = []
    table_match = re.search(r'\|[^\n]+\|\s*\n\|[-:\s|]+\|\s*\n((?:\|[^\n]+\|\s*\n?)+)', content2, re.MULTILINE)
    if table_match:
        rows = table_match.group(1).strip().split('\n')
        for row in rows:
            cells = [c.strip() for c in row.split('|') if c.strip()]
            if len(cells) >= 4:
                kw, fc, dmt, trace = cells[0], cells[1], cells[2], cells[3]
                related = []
                if len(cells) >= 5 and cells[4]:
                    related = [x.strip() for x in re.split(r'[、,，]', cells[4]) if x.strip()][:2]
                keywords_parsed.append(
                    {'keyword': kw, 'four_color': fc, 'dmt': dmt, 'trace': trace, 'related': related})

    try:
        notebook = UserNotebook.objects.get(username=realName, bookName=bookName)
        kfd = json.loads(notebook.keywordFourColorDMT or '{}')
        fusion = json.loads(notebook.keywordFusionRelations or '{}')
        existing_set = set(kfd.keys())
        for item in keywords_parsed:
            kw = item['keyword']
            if kw and len(kw) <= 20:
                kfd[kw] = {
                    'four_color_type': item.get('four_color', ''),
                    'dmt_level': item.get('dmt', ''),
                    'is_tribal': True
                }
                related = item.get('related', [])
                valid_related = [r for r in related if r in existing_set]
                if len(valid_related) >= 2:
                    fusion[kw] = {'source_keywords': valid_related[:2]}
                elif len(valid_related) == 1 and len(existing_set) > 1:
                    other = next((x for x in existing_set if x != valid_related[0] and x != kw), None)
                    if other:
                        fusion[kw] = {'source_keywords': [valid_related[0], other]}
        notebook.keywordFourColorDMT = json.dumps(kfd, ensure_ascii=False)
        notebook.keywordFusionRelations = json.dumps(fusion, ensure_ascii=False)
        notebook.save()
    except Exception as e:
        print(f"[tribal] 更新 keywordFourColorDMT/keywordFusionRelations 失败: {e}")

    return True, out_path


def _run_tribal_full_pipeline(username, task_id):
    """串行+4并发执行：md → 关键词入图 → 深卡(4并发) → 认知状态分析卡"""
    try:
        ok, msg = extract_notebook_tribal_knowledge_semantic_layer(username, task_id)
        if not ok:
            if task_id in global_var.tasks:
                global_var.tasks[task_id]['error'] = msg
                global_var.tasks[task_id]['completed'] = True
            return

        md_content = _read_tribal_md(username)
        if not md_content:
            if task_id in global_var.tasks:
                global_var.tasks[task_id]['completed'] = True
            return

        path, (realName, bookName) = _get_tribal_md_path(username)
        if not path:
            if task_id in global_var.tasks:
                global_var.tasks[task_id]['completed'] = True
            return

        try:
            notebook = UserNotebook.objects.get(username=realName, bookName=bookName)
            kfd = json.loads(notebook.keywordFourColorDMT or '{}')
            tribal_kws = [k for k, v in kfd.items() if isinstance(v, dict) and v.get('is_tribal')]
        except Exception:
            tribal_kws = []

        if not tribal_kws:
            if task_id in global_var.tasks:
                global_var.tasks[task_id]['current_section'] = '无部落关键词，跳过深卡'
                global_var.tasks[task_id]['completed'] = True
            return

        total = len(tribal_kws) + 1
        if task_id in global_var.tasks:
            global_var.tasks[task_id]['total_items'] = total

        from concurrent.futures import ThreadPoolExecutor, as_completed
        from app_chat.views_generate_permanent_card import generate_tribal_permanent_card_internal
        from app_chat.views_analyze_cognitive_state import analyze_cognitive_state_with_tribal_md

        done = 0

        def gen_one(kw):
            return generate_tribal_permanent_card_internal(
                username=username, keyword=kw,
                tribal_md=md_content, other_tribal_keywords=[x for x in tribal_kws if x != kw]
            )

        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(gen_one, kw): kw for kw in tribal_kws}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    print(f"[tribal] 深卡生成失败: {e}")
                done += 1
                if task_id in global_var.tasks:
                    global_var.tasks[task_id]['current_item'] = done
                    global_var.tasks[task_id]['current_section'] = f'深卡 {done}/{len(tribal_kws)}'

        if task_id in global_var.tasks:
            global_var.tasks[task_id]['current_section'] = '生成认知状态分析卡'
        network_image = global_var.tasks.get(task_id, {}).get('network_image', '') if task_id else ''
        try:
            scene_name = None
            try:
                nb = UserNotebook.objects.get(username=realName, bookName=bookName)
                scene_obj = scene.objects.get(sid=nb.sid)
                scene_name = scene_obj.sceneDescription
            except Exception:
                pass
            analyze_cognitive_state_with_tribal_md(username, scene_name, tribal_md=md_content,
                                                   network_image_base64=network_image)
        except Exception as e:
            print(f"[tribal] 认知状态分析卡失败: {e}")

        if task_id in global_var.tasks:
            global_var.tasks[task_id]['current_item'] = total
            global_var.tasks[task_id]['current_section'] = '完成'
            global_var.tasks[task_id]['completed'] = True
    except Exception as e:
        import traceback
        traceback.print_exc()
        if task_id in global_var.tasks:
            global_var.tasks[task_id]['error'] = str(e)
            global_var.tasks[task_id]['completed'] = True


@csrf_exempt
def extract_tribal_knowledge(request):
    """API：点击「提取部落知识」触发，返回 task_id，前端轮询进度。"""
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        if not username:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username'})

        task_id = f"tribal_{username}_{uuid.uuid4().hex[:8]}"
        network_image = data.get('network_image', '')  # 关键词节点图（与原有认知分析一致）
        global_var.tasks[task_id] = {
            'current_item': 0,
            'total_items': 1,
            'current_section': '准备中',
            'completed': False,
            'error': None,
            'network_image': network_image
        }

        t = threading.Thread(target=_run_tribal_full_pipeline, args=(username, task_id), daemon=True)
        t.start()

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'task_id': task_id,
            'total_tasks': 5
        })
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': str(e)})


def tribal_knowledge_progress(request, task_id):
    """API：轮询部落知识萃取进度。"""
    task = global_var.tasks.get(task_id) if task_id else None
    if not task:
        return JsonResponse({
            'current_item': 0,
            'total_items': 1,
            'current_section': '',
            'completed': True
        })
    return JsonResponse({
        'current_item': task.get('current_item', 0),
        'total_items': task.get('total_items', 1),
        'current_section': task.get('current_section', ''),
        'completed': task.get('completed', False),
        'error': task.get('error')
    })
