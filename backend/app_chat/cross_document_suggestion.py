"""
文档全面交叉梳理建议卡片生成模块
根据场景信息、场景基础文档和本子增量文档，生成包含A、B、C三个部分的建议卡片
"""
import os
import json
import concurrent.futures
import re
from app_chat import scene_context_helper
from app_chat import gpt4_api, claude_api
from llm_langchain import parse_input


def generate_cross_document_suggestion(username, scene_name, sub_scene_name, notebook_description, 
                                       base_documents, incremental_documents):
    """
    生成文档全面交叉梳理建议卡片
    
    参数:
        username: 用户名
        scene_name: 场景名
        sub_scene_name: 子场景名
        notebook_description: 本子描述
        base_documents: 场景基础文档列表（包含文档名、四色、DMT信息）
        incremental_documents: 本子增量文档列表（包含文档名、四色、DMT信息）
    
    返回:
        包含A、B、C三个部分的建议卡片内容
    """
    try:
        import pandas as pd

        # 1. 获取场景摘要（不使用子场景摘要，因为卡片是针对整个本子的）
        scene_summary, _ = scene_context_helper.get_scene_summary(scene_name, None)
        final_scene_summary = scene_summary

        # 2. 获取该场景下的所有子场景名
        all_subscene_names = []
        try:
            scene_dir_path = f'./received_dir/scene_excel/{scene_name}'
            prompt_excel_path = os.path.join(scene_dir_path, 'prompt.xlsx')

            if os.path.exists(prompt_excel_path):
                # 从LUI1表格读取子场景名列表
                excel_data = pd.read_excel(prompt_excel_path, sheet_name='LUI1')
                sub_scene_col = 1
                if excel_data.shape[1] > sub_scene_col:
                    first_subscene_col_name = excel_data.columns[sub_scene_col]
                    subscene_name_list = excel_data.iloc[:, sub_scene_col].dropna().tolist()
                    # 将第一列的列名也加入列表（通常是第一个子场景名）
                    all_subscene_names = [first_subscene_col_name] + subscene_name_list
                    print(f"[generate_cross_document_suggestion] 获取子场景列表成功: {all_subscene_names}")
        except Exception as e:
            print(f"[generate_cross_document_suggestion] 获取子场景列表失败: {e}")
            all_subscene_names = []

        # 3. 构建文档信息描述
        base_docs_info = []
        for doc in base_documents:
            doc_name = doc.get('name', '')
            main_color = doc.get('main_four_color', '')
            secondary_color = doc.get('secondary_four_color', '')
            dmt = doc.get('dmt_level', '')
            info = f"- {doc_name}"
            if main_color or dmt:
                info += f"（主色:{main_color}"
                if secondary_color:
                    info += f", 辅色:{secondary_color}"
                if dmt:
                    info += f", DMT:{dmt}"
                info += "）"
            base_docs_info.append(info)
        
        incremental_docs_info = []
        for doc in incremental_documents:
            doc_name = doc.get('name', '')
            main_color = doc.get('main_four_color', '')
            secondary_color = doc.get('secondary_four_color', '')
            dmt = doc.get('dmt_level', '')
            info = f"- {doc_name}"
            if main_color or dmt:
                info += f"（主色:{main_color}"
                if secondary_color:
                    info += f", 辅色:{secondary_color}"
                if dmt:
                    info += f", DMT:{dmt}"
                info += "）"
            incremental_docs_info.append(info)
        
        # 4. 构建prompt
        system_prompt = """你是一个专业的文档分析专家，擅长从多文档交叉梳理的角度提供深刻、具体、有指向性的建议。
你需要基于场景信息、场景基础文档和本子增量文档，生成一份全面的交叉梳理建议卡片。
建议卡片需要包含三个部分，按顺序深入展开：
A. 权威置信度要求：深入评估文档的权威性、可靠性要求，综合考虑文档的特性和认知层次
B. 本子目标任务描述摘要：深刻理解并清晰指向本子的真实目标与任务方向（必须先完成此部分，才能为C部分提供基础）
C. 文档二次浓缩整理建议：基于A和B的深入分析，提供从浅到深、从忠实理解到认知提升的递进建议

请用清晰、深刻、具体、有指向的方式组织你的回答，避免空泛和标签化的描述。

**严格字数限制**：整个卡片（A+B+C）总字数必须≤1500字，内容精炼精准、深刻具体、有指向性。"""

        user_prompt = f"""请基于以下信息，生成文档全面交叉梳理建议卡片：

## 场景信息
- 场景名：{scene_name}
- 所有子场景：{', '.join(all_subscene_names) if all_subscene_names else '未提供'}
- 场景摘要：{final_scene_summary[:500] if final_scene_summary else '未提供'}（已截断至500字）
- 本子名描述：{notebook_description[:500] if notebook_description else '未提供'}（已截断至500字）

**重要说明**：此建议卡片是针对整个本子的全过程梳理，涉及该场景下的所有子场景，而非单一子场景。请综合考虑所有子场景的完整流程和递进关系。

## 场景基础文档（共{len(base_documents)}个）
{chr(10).join(base_docs_info) if base_docs_info else '无'}

## 本子增量文档（共{len(incremental_documents)}个）
{chr(10).join(incremental_docs_info) if incremental_docs_info else '无'}

---

请按照以下格式和要求，深入、具体、有指向地输出建议卡片：

## A. 权威置信度要求

你需要深入评估每个文档的权威性和可靠性，**不仅要给出置信度判断，更要基于深入理解给出依据和分析**。

### 文档类型判别与深入理解

请对每个文档进行细致的类型判别，参考但不限于以下类型：
- 发行出版的正式图书、教材、专著
- 教授级学者或领域专家的权威著作
- 学术会议、期刊发表的学术论文（区分不同级别）
- 硕士学位论文
- 博士学位论文
- 其他类型的文献报告、技术文档
- 时间较为久远的文献（需考虑时效性）
- 个人讨论、观点性文档
- 包含个人理解和经验总结的文档
...

**重要提示**：你在评估时可以综合考虑文档的特性特征和认知层次（比如文档是否包含专业术语、技术工具、方法论框架、形象化表达等不同层次的内容，以及认知深度），但**不要在输出中直接使用"四色"、"DMT"等内部术语**，而是用自然语言描述文档的特性。

### 评估要求

1. **不要只是打标签**：不要简单地说"这是学术论文"或"这是个人观点"，而要深入分析：
   - 该文档在什么层面提供了什么样的价值
   - 其内容的认知层次和深度如何
   - 作为知识来源的可靠性、权威性和时效性
   - 在不同使用场景下的置信度要求

2. **基于判别的深入理解**：
   - 对于不同类型的文档，分析其在当前场景和本子目标下的置信度要求
   - 说明为什么需要这种置信度要求
   - 指出使用这些文档时需要注意的事项和限制

3. **综合评估**：综合考虑文档的类型、来源、时间、内容特征、认知层次等因素，给出清晰、有依据的置信度评估。

4. **字数要求**：A部分300到400字，字数严格把控！不必每个文档的分析均分字数，而是有详有略

---

## B. 本子目标任务描述摘要

**这是关键部分**：只有深刻理解本子的真实目标，才能给出有针对性的文档整理建议。

### 目标推测与指向

请根据场景名、各子场景名、本子名描述、文档内容等信息，**自洽而深刻**地推测本子要做什么的真实目标。

1. **给出2种可能的目标方向**（这样有比对价值）：
   - 方向一：[精准、精炼、清晰描述一种可能的目标方向，说清核心目标]
   - 方向二：[精准、精炼、清晰描述另一种可能的目标方向，说清核心目标]
   - 简要分析两种方向的差异、适用场景和推荐选择

2. **根据确定的目标，给出具体而简洁精炼的任务指向**：
   - **立足点**：基于哪些文档、哪些基础内容来开展工作
   - **面向点**：要解决什么问题、达到什么效果
   - **放眼点**：最终的成果形式、认知提升、创造涌现的方向

3. **具体任务规划**：
   - 需要整理哪些文档（为什么是这些文档，它们之间的关系如何）
   - 根据哪些文档如何产出什么类型和数量的卡片
   - 文档梳理的优先级和顺序
   - 卡片产出的层次和递进关系

### 输出要求

- 目标描述要清晰、深刻、具体、有指向性
- 任务规划要可操作、有逻辑、有层次
- 避免空泛的目标描述，要能看出真实的使用意图和预期成果
- **字数要求**：B部分300到500字，字数严格把控！

---

## C. 文档二次浓缩整理建议

**注意**：此部分必须在A和B的基础上展开。只有先理解文档的置信度要求（A）和本子的真实目标（B），才能给出有针对性的整理建议。

### 递进式梳理思路

请提供**从偏浅到深刻而具体**的递进建议，这是一个从忠实理解文档转向认知提升、创造涌现的过程：

1. **初级阶段（简单了解文档）**：
   - 如何快速把握文档的核心内容和关键信息
   - 如何提取文档的基本要点和结构

2. **中级阶段（深入理解文档）**：
   - 如何深入理解文档的内在逻辑、论证结构、核心观点
   - 如何把握文档在不同认知层次上的内容（专业术语、技术方法、思维框架、形象表达等）
   - 如何理解文档的深层含义和理论背景
   - 同样有详有略，以重要关键文档为重点描述

3. **高级阶段（文档交叉关联与认知提升）**：
   - 文档之间的大小粒度/层次关系如何梳理
   - 文档内容的交叉关联点在哪里，如何建立连接
   - 理论与工程如何强烈结合
   - 哪些文档应该如何通过拆解/合并实现内容的深度整合
   - 如何让梳理出的文档和卡片在内容类型上相对完整齐全、比例合适
   - 如何提升认知深度和厚度，实现从忠实理解到认知提升、创造涌现

### 针对多文档情况

**特别强调**：如果文档很多（当前有{len(base_documents) + len(incremental_documents)}个文档），说明用户可能想要寻求深度的认知提升路径。此时，**一定要给出真实具体有价值的建议**：

- 如何处理文档数量多、内容复杂的挑战
- 如何建立这些文档之间的层次结构和关联
- 这些文档如何避免简单堆砌，实现深度整合
- 如何通过文档梳理实现认知的递进提升
- 具体而简洁精炼的操作步骤和优先级建议
- 以上几点一定是都是针对内容上的，切忌泛泛而谈，要通过文档名等深入，但也不可过度臆测文档内容

### 具体建议内容

下面几点同样一定也都是针对具体内容上的，切忌泛泛而谈，要通过文档名等深入，但也不可臆测文档内容。控制字数精准精炼而自洽贴合！

1. **文档结构优化**：
   - 如何优化文档结构，提取核心内容
   - 如何建立文档内容的层次和逻辑关系

2. **文档拆解/合并建议**：
   - **拆解建议**：针对内容较为综合复杂的文档，是否应该按内容逻辑分层次/模块拆解成多个小文档
     - 例如：复杂项目代码应分模块拆解；大单元教案学案应分层次拆解；普通文章可考虑分章节；简单说明文档可不拆分
   - **合并建议**：哪些文档之间可以关联、合并成更全面、聚焦的文档
     - 分析文档之间的关联性、互补性
     - 提出具体的合并方案和价值分析
   - **精准精炼建议**：对于不适合拆解的文档，如何精准精炼浓缩摘要

3. **内容类型完整性**：
   - 如何确保梳理出的文档和卡片在内容类型上相对完整齐全
   - 不同类型的比例如何安排（如专业内容、技术方法、思维框架、形象表达等）
   - 如何平衡不同认知层次的内容

4. **认知深度和厚度提升**：
   - 如何实现从浅层理解到深层认知的递进
   - 如何通过文档交叉梳理实现认知提升和创造涌现
   - 具体的思路和方法建议

### 输出要求

- 建议要基于A和B的分析结果，有针对性、有逻辑性，要能给用户醍醐灌顶的感觉“我怎么想不到这么全”、“我怎么没想到这一点”
- 从浅到深递进，层次清晰，且一定是具体到文档可操作的，避免空泛描述
- 特别关注多文档情况下的深度整合建议
- 一定要避免类似这样不错的废话“明确各文档侧重点，文档拆解与合并兼顾灵活应用，重点突破教学中关键瓶颈与技术难题，推动教学方案和学习路径的实质改进”
- **字数要求**：C部分400到600字，内容要精炼精准、自洽贴合，字数要严格把控！"""

        # 4. 调用Claude生成建议（优先，带超时和错误处理）
        response = None
        use_gpt_fallback = False

        def call_claude():
            try:
                return claude_api.make_claude_text_requests(user_prompt, system_prompt)
            except Exception as e:
                print(f"[generate_cross_document_suggestion] Claude调用异常: {e}")
                raise

        try:
            # 使用线程池执行Claude调用，设置90s超时
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(call_claude)
                try:
                    response = future.result(timeout=90.0)
                except concurrent.futures.TimeoutError:
                    print(f"[generate_cross_document_suggestion] Claude调用超时（>90s），切换到GPT备用方案")
                    future.cancel()
                    use_gpt_fallback = True
                except Exception as e:
                    print(f"[generate_cross_document_suggestion] Claude调用失败: {e}，切换到GPT备用方案")
                    use_gpt_fallback = True
        except Exception as e:
            print(f"[generate_cross_document_suggestion] Claude调用异常: {e}，切换到GPT备用方案")
            use_gpt_fallback = True

        # 🔥 检测生成内容是否过少（只包含标题，没有实际内容）
        if response:
            response_stripped = response.strip()
            # 检查是否只包含标题（A、B、C部分），没有实际内容
            # 如果内容长度小于200字符，或者只包含标题行，认为内容过少
            if len(response_stripped) < 200:
                print(f"[generate_cross_document_suggestion] Claude生成内容过少（{len(response_stripped)}字符），切换到GPT备用方案")
                use_gpt_fallback = True
            else:
                # 检查是否包含A、B、C三个部分的内容（不只是标题）
                # 注意：B和C的顺序已交换，B是本子目标任务描述摘要，C是文档二次浓缩整理建议
                has_section_a = bool(re.search(r'##\s*A\.\s*权威置信度要求', response_stripped, re.IGNORECASE))
                has_section_b = bool(re.search(r'##\s*B\.\s*本子目标任务描述摘要', response_stripped, re.IGNORECASE))
                has_section_c = bool(re.search(r'##\s*C\.\s*文档二次浓缩整理建议', response_stripped, re.IGNORECASE))

                # 如果只有标题没有内容，或者缺少某个部分，认为内容不完整
                if not (has_section_a and has_section_b and has_section_c):
                    print(f"[generate_cross_document_suggestion] Claude生成内容不完整（缺少部分），切换到GPT备用方案")
                    use_gpt_fallback = True
                else:
                    # 检查每个部分是否有实际内容（不只是标题和占位符）
                    # B和C的顺序已交换：A -> B(本子目标任务) -> C(文档二次浓缩)
                    section_a_match = re.search(r'##\s*A\.\s*权威置信度要求\s*\n(.*?)(?=##\s*B\.|$)', response_stripped,
                                                re.DOTALL | re.IGNORECASE)
                    section_b_match = re.search(r'##\s*B\.\s*本子目标任务描述摘要\s*\n(.*?)(?=##\s*C\.|$)', response_stripped,
                                                re.DOTALL | re.IGNORECASE)
                    section_c_match = re.search(r'##\s*C\.\s*文档二次浓缩整理建议\s*\n(.*?)$', response_stripped,
                                                re.DOTALL | re.IGNORECASE)

                    content_a = section_a_match.group(1).strip() if section_a_match else ""
                    content_b = section_b_match.group(1).strip() if section_b_match else ""
                    content_c = section_c_match.group(1).strip() if section_c_match else ""

                    # 如果某个部分内容过少（少于50字符）或只包含占位符，认为内容不完整
                    if len(content_a) < 50 or len(content_b) < 50 or len(content_c) < 50:
                        print(f"[generate_cross_document_suggestion] Claude生成内容部分过少，切换到GPT备用方案")
                        use_gpt_fallback = True

        # 🔥 如果Claude失败/超时/内容过少，使用GPT备用方案
        if use_gpt_fallback or not response:
            print(f"[generate_cross_document_suggestion] 使用GPT备用方案生成建议...")
            try:
                response = gpt4_api.make_gpt4o_text_requests(user_prompt, system_prompt)
                print(f"[generate_cross_document_suggestion] GPT备用方案生成成功")
            except Exception as e:
                print(f"[generate_cross_document_suggestion] GPT备用方案也失败: {e}")
                return f"生成建议时发生错误: Claude和GPT都调用失败 - {str(e)}"

        return response.strip() if response else "生成建议失败：无法获取响应"
        
    except Exception as e:
        print(f"[generate_cross_document_suggestion] 生成建议失败: {e}")
        import traceback
        traceback.print_exc()
        return f"生成建议时发生错误: {str(e)}"


def check_if_base_document(scene_name, document_name):
    """
    检查文档是否是场景基础文档
    如果文档在received_dir/scene_excel/具体场景名路径下也存在，则是场景基础文档
    """
    try:
        scene_dir_path = f"./received_dir/scene_excel/{scene_name}"
        if os.path.exists(scene_dir_path):
            scene_file_path = os.path.join(scene_dir_path, document_name)
            return os.path.exists(scene_file_path) and os.path.isfile(scene_file_path)
        return False
    except Exception as e:
        print(f"[check_if_base_document] 检查失败: {e}")
        return False

