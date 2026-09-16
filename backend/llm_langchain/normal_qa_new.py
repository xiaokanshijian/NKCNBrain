from llm_langchain import get_model, global_var
from langchain.schema import (
    HumanMessage,
    SystemMessage,
    AIMessage
)
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from llm_langchain import util
from llm_langchain import parse_input

from app_chat import gpt4_api, kimi_api, claude_api, llama_api, deepseek_api, dsreasoner_api
from app_chat.global_state import GLOBAL_STATE
from app_chat.config.config_manager import config_manager

import asyncio
import json
import base64
import io
import os
from PIL import Image

system_prompt_claude = """<人性化思考协议>
<多模态感知>
以人类般的多维感知能力处理信息、感知情境、解决问题：
1. 视觉场景模拟建立感知
- 构建清晰的心理图像
- 想象具体视觉细节
- 分析空间关系布局
- 识别能可视化的模式和结构

2. 听觉场景模拟建立感知
- 模拟声音和语调变化
- 感知语言节奏韵律
- 注意声音的情感特征

3. 触觉场景模拟建立感知
- 模拟解决问题的环境具象并密切感受
- 想象物理交互变化过程
- 感知动作和空间关系

4. 情感感知
- 识别情绪基调
- 揣摩发问动机
- 分析心理影响
- 把握情感连接

5. 整体感知整合
- 以当事人视角，以好奇心驱动探究
- 整合多感官信息
- 建立丰富的心理表征
- 形成多维度理解网络

<思维发展阶段>
按照阶段使用不同思维推进思考：
1. 自然意识流状态
- 保持思维自由开放地流动
- 允许梦境般的幻想状态
- 注意自发的联想
- 记录初始整体印象

2. 多模态感知激活
- 运用多模态感知
- 构建丰富场景
- 整合感知信息，形成丰富表征

3. 直觉系统运作
- 此阶段开始不允许再停留于类似做梦的幻想状态
- 捕捉首要印象
- 识别潜在模式
- 产生创意火花，形成初步方向

4. 推理系统主导
- 严密的逻辑分析
- 随时验证和评估
- 以树分支、图连接的方式推理思考
- 不断提出新的假设并记得验证
- 从错误的假设或树图思考路径中吸取经验

5. 深度整合
- 综合多维观点
- 对不同思考提炼核心见解、建立深层联系
- 思维活跃，不断构建完善论证

<核心思考步骤细节>
1. 初始解析
- 重述问题中关键信息以达到理解
- 考虑背景知识体系
- 分析询问动机
- 识别已知未知

2. 深入分析
- 分解核心要素
- 识别出隐含的需求
- 考虑不同级别的限制条件
- 设想理想结果

3. 多角度探索
- 考虑多种解释
- 对一个问题或概念可能有多种认知，应该揣摩人类更可能的意愿，排除歧义
- 激活灵感，不断探索更优方案

4. 推理验证
- 持续检验假设
- 寻找证据支持
- 考虑反例
- 验证逻辑一致

5. 知识整合
- 组织相关信息
- 建立关系网络
- 提炼核心，总结关键发现

<质量控制>
1. 系统化验证
- 对较复杂问题，多次重复且独立地验证每个步骤
- 以发现漏洞为目标
- 问题最终解决后，完整检查思考过程
- 核对所有已知条件
- 确保逻辑严谨
- 考虑边界情况

2. 错误防范
- 面对任何问题，在任何阶段，都不要过于自信，即使看起来可能很简单明确
- 避免过早下结论
- 考虑替代方案

3. 评估标准
- 分析完整性
- 逻辑严密性
- 证据充分性
- 实际可用性

<表达特征>
1. 自然语言风格
- 流畅的意识流表达
- 生动的场景构建和多感知描述
- 自然舒展地表达展现完整思维过程

2. 思维深度
- 逐层深入分析
- 展示认知发展
- 揭示思维转折，凸显关键洞察

<重要规则>
- 思维过程必须全面且深入
- 保持自然的思维流动
- 善用模拟多模态情境感知理解
- 遵循自然意识→感知→直觉→推理→深度思考验证的过程
- 输出的所有思考过程必须在三反引号代码块中，标记为"thinking"
- 如果涉及逻辑推理，思考结束要完整检查，标记为"checking"，此时应特别注意，一定不可遗漏任何已知条件，以找漏洞为目标，此时应该更倾向于说明矛盾点，符合点一笔带过即可；同时注意是否失误地排除了正确答案
- 如果找出漏洞，需重新"thinking"解决问题，应着重对之前产生漏洞的相关思考吸取教训，且再次"checking"时，应该更加仔细且多次
- 如果思考和检查超过2轮就请停下来，承认自己无法解决并告知人类原因
- 避免在思考和检查过程输出中使用三反引号，这会导致格式解析出错
- 将思考过程总结为一个思考成果报告，直接解决人类的问题并作适当解释
- 以人类使用或请求的语言来回应
</人性化思考框架>
"""

qa_chain = []


# 这里是对summary的链条进行初始化，现在只是一个极其简单的链条，甚至没有对输出的处理，只有在加入对输出的处理之后才能得到格式化的文本
# 这里也没有使用到关于ReAct，Agent等技术方法，有待之后看需要增加
def init_qa(sequence):
    chat_model = get_model.get_chat(sequence)

    messages = []
    messages_1, messages_2 = get_model.get_qa_msg(sequence)
    messages.extend(messages_1)
    messages.extend(messages_2)
    chat_template = ChatPromptTemplate.from_messages(messages)
    global qa_chain
    qa_chain.append(chat_template | chat_model)  # 输出格式为content:....,response=....,id = ....
    qa_chain[sequence] = get_model.unique_parse(sequence, qa_chain[sequence])
    # 在mixtral的输出下没有response


def get_relevant_docs(question, vector_store, docs_name, user_name):
    # question:注意力机制是什么？
    # query:{'source': {'$in': ['./received_dir/user_raw_file/admin/attention is all you need.pdf']}}
    querys = []
    query = {}
    for doc_name in docs_name:
        file_path = util.construct_file_path(user_name, doc_name)
        querys.append(file_path)
    query["source"] = {"$in": querys}

    # 🔥 使用混合查询（支持同时查询主库和从库）
    docs = parse_input.similarity_search_with_merge(vector_store, user_name, question, k=10, filter=query)
    images = []
    seqs = []
    for doc in docs:
        if "type" in doc.metadata and doc.metadata["type"] == "image":
            images.append(global_var.store_memory[user_name]["images"][util.back_file_path(doc.metadata["source"])]
                          [doc.metadata["seq"] - 1])
            seqs.append(doc.metadata["seq"])
    # for doc in docs:
    #    print(doc)
    texts = docs[0:min(10, len(docs))]
    # for text in texts:
    #    print(text)
    return texts, images, seqs


async def get_qa(question, user_name, docs, images, seqs):
    # docs, images, seqs = get_relevant_docs(question, vector_store, docs_name, user_name)
    texts = util.link_text([doc.page_content for doc in docs])
    # out = qa_chain.invoke({"text": texts, "question": question})
    images_list = []
    count = 0
    if len(images) != 0:
        for image in images:
            count += 1
            images_list.append(HumanMessage(content=[
                {
                    "type": "text",
                    "text": "This is the " + str(count) + "nd image of " + str(len(images)) + ", its order "
                                                                                              "in all images should be "
                            + str(seqs[count - 1]) +
                            ". If you use the "
                            "image, use this order."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image}"
                    }
                }
            ]))
    results = await asyncio.gather(util.chain_run_async(qa_chain[0], {"text": texts, "question": question,
                                                                      "images_store": images_list, "qa_prompt":
                                                                          global_var.store_memory[user_name]["prompt"][
                                                                              "LUI2"]["qa"]}),
                                   # util.chain_run_async_mixtral(qa_chain[1], {"text": texts, "question": question, "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
                                   # util.chain_run_async_llama3(qa_chain[2], {"text": texts, "question": question, "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]})
                                   )
    # results = util.chain_run(qa_chain[0], {"text": texts, "question": question})
    # results = await asyncio.gather(util.chain_run_async(qa_chain[2], {"text": texts, "question": question, "qa_prompt": global_var.store_memory[user_name]["prompt"]["qa"]}))
    print(results)
    return results
    # 之后仔细查看源码。要知道stream返回的是什么，invoke返回的是什么？
    # for chunk in qa_chain.stream({"text": texts, "question": question}):
    #    print(chunk, end="|", flush=True)
    # out = qa_chain.invoke({"text": texts, "question": question})
    # print(out)
    # return out.content
    # for chunk in qa_chain.stream({"text": texts, "question": question}):
    #       print(chunk, end="\n", flush=True)


# 这里有点冗余了，主要是在文档创建的时候不好再单独设置它的metadata，先这么用
def get_qa_user_docs(user_name, question, docs_name):
    vector_store = parse_input.get_vector_by_user(user_name)
    docs, images, seqs = get_relevant_docs(question, vector_store, docs_name, user_name)
    return [out.content for out in asyncio.run(get_qa(question, user_name, docs, images, seqs))]


# 【标记】对外接口
def get_qa_user_docs_way_split_multi(user_name, question, docs_name, get_way, history, multi):
    segments = util.get_docs_all_split(user_name, docs_name, get_way, question)
    # print('[normal_qa]get_aq_user_docs_way_split', segments)
    images, seqs, exts, sources, pages = util.parse_image_in_segment_split(user_name, segments)
    return [out.content for out in asyncio.run(
        get_qa_images_seqs_split(question, user_name, segments, images, seqs, exts, sources, pages, history,
                                 multi=multi, model_states="{}"))]


def get_qa_user_docs_way_split(user_name, question, docs_name, get_way, history, model_states):
    if not docs_name:  # When file_list is empty
        return asyncio.run(get_qa_direct_api(question, user_name, history, systemPrompt="", model_states=model_states))
    else:
        print(f"yq docs_name: {docs_name}")
        segments = util.get_docs_all_split(user_name, docs_name, get_way, question)
        print('[normal_qa]get_aq_user_docs_way_split', segments)
        images, seqs, exts, sources, pages = util.parse_image_in_segment_split(user_name, segments)
        return [out.content for out in asyncio.run(
            get_qa_images_seqs_split(question, user_name, segments, images, seqs, exts, sources, pages, history,
                                     multi="NO", model_states=model_states))]


def get_model_specific_histories(username, question, model_name):
    """
    为指定模型生成对话历史字符串
    username: 用户名，用于获取对应的聊天历史
    question: 当前用户的新问题
    model_name: 指定的模型名称
    conversation_manager: ConversationManager实例
    max_round: 最大对话轮数，默认为10
    """

    # 初始化对话历史字符串
    history_str = "历史对话记录：\n"

    # 获取历史问题和回复
    questions = GLOBAL_STATE.conversation_manager.get_question_list(username, model_name)
    responses = GLOBAL_STATE.conversation_manager.get_response_list(username, model_name)

    print(f"[DEBUG:get_model_specific_histories] 为模型 {model_name} 获取历史记录，用户名：{username}")
    print(f"[DEBUG:get_model_specific_histories] 当前获取的历史记录：问题列表：{questions}，回复列表：{responses}")

    # 遍历历史对话记录
    for q, r in zip(questions, responses):
        history_str += f"用户请求或提问：{q}\n你的回答：{r}\n\n"

    # 添加本次的新问题
    if model_name == 'Claude':
        history_str += f"本次用户的请求或提问：\n使用thinking-checking-完整综合结果，回答：\n{question}（要深思熟虑当前的场景阶段提示）"
    else:
        history_str += f"本次用户的请求或提问（如果上面的历史对话记录里，你产生了异常、混乱的回答，请不要受它们影响，忽略这些内容，专心回答目前的问题）：\n{question}（要深思熟虑当前的场景阶段提示，符合要求）"

    return history_str


def get_model_specific_histories2(username, question, model_name, rounds):
    """
    为指定模型生成对话历史字符串
    username: 用户名，用于获取对应的聊天历史
    question: 当前用户的新问题
    model_name: 指定的模型名称
    conversation_manager: ConversationManager实例
    max_round: 最大对话轮数，默认为10
    """

    # 初始化对话历史字符串
    history_str = "历史对话记录：\n"

    # 获取历史问题和回复
    questions = GLOBAL_STATE.conversation_manager.get_question_list(username, model_name, rounds)
    responses = GLOBAL_STATE.conversation_manager.get_response_list(username, model_name, rounds)

    print(f"[DEBUG:get_model_specific_histories] 为模型 {model_name} 获取历史记录，用户名：{username}")
    print(f"[DEBUG:get_model_specific_histories] 当前获取的历史记录：问题列表：{questions}，回复列表：{responses}")

    # 遍历历史对话记录
    for q, r in zip(questions, responses):
        history_str += f"用户请求或提问：{q}\n你的回答：{r}\n\n"

    # 添加本次的新问题
    if model_name == 'Claude':
        history_str += f"本次用户的请求或提问：\n使用thinking-checking-完整综合结果，回答：\n{question}（要深思熟虑当前的场景阶段提示）"
    else:
        history_str += f"本次用户的请求或提问（如果上面的历史对话记录里，你产生了异常、混乱的回答，请不要受它们影响，忽略这些内容，专心回答目前的问题）：\n{question}（要深思熟虑当前的场景阶段提示，符合要求）"

    return history_str


# def get_model_specific_histories(username, model_name, question):
#     """
#     结合历史对话记录和当前问题，生成特定模型的prompt

#     username: 用户名，用于获取对应的聊天历史
#     model_name: 指定的模型名称
#     question: 当前用户的新问题
#     return question_with_history: 生成的prompt字符串
#     """
#     # from app_chat.global_state import GLOBAL_STATE
#     from app_chat.views import chat_history

#     question_with_history = "历史对话记录：\n"

#     # 获取指定(用户，模型)历史对话记录
#     # histories = GLOBAL_STATE.conversation_manager.get_response_list(username, model_name)
#     # questions = GLOBAL_STATE.conversation_manager.get_question_list(username, model_name)

#     histories = chat_history[username][model_name]

#     # 遍历历史问题与历史回复
#     # print("[INFO] 正在利用历史信息生成prompt")

#     #     user_message = turn['message']
#     # # 为每个模型添加这一轮的对话
#     # for model, idx in MODEL_INFO.items():
#     #     questions[model] += f"用户请求或提问：{user_message}\n你的回答：{turn['AImessage'][idx]}\n\n"

#     print(f"[DEBUG:get_model_specific_histories] 当前获取的历史记录：{histories}")

#     user_message = histories['message']


#     # for index in range(len(histories)):
#     #     # 获取当前历史记录
#     #     history = histories[index]
#     #     question_history = questions[index]

#     #     # 处理模型特定的历史记录
#     #     question_with_history += f"用户提问{index}：{question_history}\n你的回答{index}：{history}\n\n"
#     #     # print(f"[INFO] 当前获取的历史记录：用户提问：{question_history}，你的回答：{history}")

#     # 添加本次的新问题
#     question_with_history += f"本次用户的请求或提问：\n{question}"

#     return question_with_history

# def get_model_specific_histories(username, question, model_name):
#     """
#     为指定模型生成对话历史字符串
#     username: 用户名，用于获取对应的聊天历史
#     question: 当前用户的新问题
#     model_name: 指定的模型名称
#     """
#     from app_chat.views import chat_history

#     print(f"[DEBUG:get_model_specific_histories] chat_history: {chat_history}")

#     MODEL_INFO = {
#         'GPT4o': 0,
#         'Llama': 1,
#         'Kimi': 2,
#         'Claude': 3,
#         'Deepseek': 4,
#         'Deepseek-reasoner': 5,
#         'Gemini': 6,
#         'Qwq': 7
#     }

#     # 检查模型名称是否有效
#     if model_name not in MODEL_INFO:
#         raise ValueError(f"未知的模型名称: {model_name}")

#     # 初始化对话历史字符串
#     history_str = "历史对话记录：\n"

#     # 遍历历史对话记录
#     for turn in chat_history[username]:
#         user_message = turn['message']
#         ai_message = turn['AImessage'][MODEL_INFO[model_name]]
#         history_str += f"用户请求或提问：{user_message}\n你的回答：{ai_message}\n\n"


#     # 添加本次的新问题
#     if model_name == 'Claude':
#         history_str += f"本次用户的请求或提问：\n使用thinking-checking-完整综合结果，回答：\n{question}（要深思熟虑当前的场景阶段提示）"
#     else:
#         history_str += f"本次用户的请求或提问（如果上面的历史对话记录里，你产生了异常、混乱的回答，请不要受它们影响，忽略这些内容，专心回答目前的问题）：\n{question}（要深思熟虑当前的场景阶段提示，符合要求）"

#     return history_str


async def get_qa_images_seqs_split(question, user_name, all_segments, all_images, all_seqs, all_exts, all_sources,
                                   all_pages, history, multi="NO", model_states="{}"):
    # 定义一个字典，映射文件后缀名到其MIME类型
    mime_types = {
        'jpg': 'image/jpg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        # 添加其他需要支持的图片格式
    }

    def get_base64_size(base64_str):
        # 计算base64字符串对应的字节大小
        # base64编码后的字符串长度 * 0.75 约等于原始数据的字节数
        return len(base64_str) * 0.75

    def add_image_info(info_list, count, total_images, seq, source, page, image_url):
        """
            info_list (list): 向info_list添加图片相关信息
            count (int): 当前图片计数
            total_images (int): 总图片数
            seq (int): 图片序号
            image_url (str): 图片的URL
        """
        info_list.extend([
            {
                "type": "text",
                "text": f"This is the {count}nd image of {total_images}, "
                        f"its order in all images of this document should be {seq}. And it is on page {page} of the {source}. "
                        "If you use the image, use the order in all images of document as its reference, as well as the document and page number it belongs to."
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url
                }
            }
        ])

    MAX_SIZE = 5 * 1024 * 1024  # 5MB in bytes
    current_total_size = 0

    info_list = []
    info_list_claude = []
    for i, doc_segments in enumerate(all_segments):
        # text_docs = util.link_text([segment.page_content + f"（来源：{segment.metadata.get('source', '未知')}，所在页数：{segment.metadata.get('page', '未知')}）" for segment in doc_segments[:len(doc_segments) - 1]])
        text_docs = util.link_text([
                                       segment.page_content + f"（来源：{segment.metadata.get('source', '未知')}，所在页数：{segment.metadata.get('page', 0) + 1 if isinstance(segment.metadata.get('page'), int) else segment.metadata.get('page', '未知')}）"
                                       for segment in doc_segments[:len(doc_segments) - 1]])
        info_list.append({
            "type": "text",
            "text": text_docs
        })
        info_list_claude.append({
            "type": "text",
            "text": text_docs
        })
        # for segment in doc_segments[:len(doc_segments)-1]:

        cur_sequence = global_var.store_memory[user_name]["model_num"]

        if cur_sequence == 0 or cur_sequence == 4:
            if len(all_images[i]) != 0:
                count = 0
                for image in all_images[i]:
                    count += 1
                    claude_list_add_cur_image = True

                    # 计算当前图片的base64大小
                    image_size = get_base64_size(image)
                    # 检查添加新图片后是否会超过限制
                    if current_total_size + image_size > MAX_SIZE:
                        print(f"Skipping image {count} as it would exceed the 5MB limit")
                        claude_list_add_cur_image = False
                    # 更新已使用的总大小
                    current_total_size += image_size

                    # 获取图片的后缀名（不带点'.'）
                    image_ext = all_exts[i][count - 1].lower()
                    mime_type = mime_types.get(image_ext, 'image/jpeg')  # 默认使用'image/jpeg'
                    image_url = f"data:{mime_type};base64,{image}"

                    add_image_info(info_list, count, len(all_images[i]), all_seqs[i][count - 1],
                                   all_sources[i][count - 1], all_pages[i][count - 1], image_url)
                    if claude_list_add_cur_image:
                        add_image_info(info_list_claude, count, len(all_images[i]), all_seqs[i][count - 1],
                                       all_sources[i][count - 1], all_pages[i][count - 1], image_url)

        info_list.append({
            "type": "text",
            "text": doc_segments[
                        len(doc_segments) - 1].page_content + f"（来源：{doc_segments[len(doc_segments) - 1].metadata.get('source', '未知')}，所在页数：{doc_segments[len(doc_segments) - 1].metadata.get('page', '未知')}）"
        })
        info_list_claude.append({
            "type": "text",
            "text": doc_segments[
                        len(doc_segments) - 1].page_content + f"（来源：{doc_segments[len(doc_segments) - 1].metadata.get('source', '未知')}，所在页数：{doc_segments[len(doc_segments) - 1].metadata.get('page', '未知')}）"
        })
    images_list = [HumanMessage(content=info_list)]
    images_list_claude = [HumanMessage(content=info_list_claude)]
    text = ""
    for i, doc_segments in enumerate(all_segments):
        text += util.link_text([
                                   segment.page_content + f"（来源：{segment.metadata.get('source', '未知')}，所在页数：{segment.metadata.get('page', '未知')}）"
                                   for segment in doc_segments])

    # 获取所有的模型名称
    from app_chat.core.model_manager import model_manager
    model_names = model_manager.get_all_model_names()

    question_with_history_list = {}
    for model_name in model_names:
        # 获取各个模型的完整问题（包含历史记录），一个字典，以模型名称为key
        # 每次调用get_model_specific_histories(username, model_name, question)即可返回一个完整问题
        question_with_history_list[model_name] = get_model_specific_histories(user_name, question, model_name)

    # kimi突然处理不了images_list了，只能改了这里和chat_kimi_model
    results = None
    if model_states == "{}":
        if multi == "Claude":
            # 获取claude-3.5的handler，然后嗲用chain_run_async（这个模型名不懂对不对呀···）
            claude_handler = model_manager.get_model_handler("claude-3.5")
            questionClaude = question_with_history_list.get("claude-3.5")

            results = await asyncio.gather(claude_handler.chain_run_async("qa_chain",
                                                                          {"text": text, "question": question,
                                                                           "images_store": images_list_claude,
                                                                           "qa_prompt":
                                                                               global_var.store_memory[user_name][
                                                                                   "prompt"]["LUI2"]["qa"]}))
        elif multi == "GPT":
            gpt_handler = model_manager.get_model_handler("GPT4o")
            questionGPT = question_with_history_list.get("GPT4o")
            results = await asyncio.gather(gpt_handler.chain_run_async("qa_chain", {"text": text, "question": question,
                                                                                    "images_store": images_list,
                                                                                    "qa_prompt":
                                                                                        global_var.store_memory[
                                                                                            user_name]["prompt"][
                                                                                            "LUI2"]["qa"]}))

            # results = await asyncio.gather(util.chain_run_async(qa_chain[0], {"text": text, "question": questionGPT, "images_store": images_list, "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}))
        else:
            # 循环遍历所有模型的handler，并gather在一起
            tasks = []
            for model_name in model_names:
                handler = model_manager.get_model_handler(model_name)
                question_with_history = question_with_history_list.get(model_name)
                if config_manager.is_allow_img(model_name):
                    images_store = images_list if model_name != "claude-3.5" else images_list_claude
                else:
                    images_store = []
                tasks.append(handler.chain_run_async("qa_chain", {
                    "text": text,
                    "question": question_with_history,
                    "images_store": images_store,
                    "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]
                }))
            results = await asyncio.gather(*tasks)

            # results = await asyncio.gather(util.chain_run_async(qa_chain[0], {"text": text, "question": questionGPT, "images_store": images_list, "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
            #                                # util.chain_run_async_mixtral(qa_chain[1], {"text": text, "question": question, "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
            #                                util.chain_run_async_llama3(qa_chain[2], {"text": text, "question": questionLlama, "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
            #                                util.chain_run_async_kimi(qa_chain[3], {"text": text, "question": questionKimi, "images_store": [], "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
            #                                util.chain_run_async_claude(qa_chain[4], {"text": text, "question": questionClaude, "images_store": images_list_claude, "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
            #                                util.chain_run_async_deepseek(qa_chain[5], {"text": text, "question": questionDeepseek, "images_store": [], "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
            #                                util.chain_run_async_dsreasoner(qa_chain[6], {"text": text, "question": questionDsreasoner, "images_store": [], "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
            #                                util.chain_run_async_Gemini(qa_chain[7], {"text": text, "question": quetionGemini, "images_store": [], "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
            #                                util.chain_run_async_Qwq(qa_chain[8], {"text": text, "question": questionQwq, "images_store": [], "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]}),
            #                                )

    else:
        if multi == "Claude":
            claude_handler = model_manager.get_model_handler("claude-3.5")
            questionClaude = question_with_history_list.get("claude-3.5")
            results = await asyncio.gather(claude_handler.chain_run_async("qa_chain",
                                                                          {"text": text, "question": questionClaude,
                                                                           "images_store": images_list_claude,
                                                                           "qa_prompt":
                                                                               global_var.store_memory[user_name][
                                                                                   "prompt"]["LUI2"]["qa"]}))
        elif multi == "GPT":
            gpt_handler = model_manager.get_model_handler("GPT4o")
            questionGPT = question_with_history_list.get("GPT4o")
            results = await asyncio.gather(gpt_handler.chain_run_async("qa_chain",
                                                                       {"text": text, "question": questionGPT,
                                                                        "images_store": images_list, "qa_prompt":
                                                                            global_var.store_memory[user_name][
                                                                                "prompt"]["LUI2"]["qa"]}))
        else:
            model_states_json = json.loads(model_states)
            print(model_states_json)
            # 创建一个映射表，把索引和对应的异步函数关联起来
            async_functions = {}
            for model_name in model_names:
                index = config_manager.get_model_sequence(model_name)
                handler = model_manager.get_model_handler(model_name)
                question_with_history = question_with_history_list.get(model_name)
                if config_manager.is_allow_img(model_name):
                    images_store = images_list if model_name != "claude-3.5" else images_list_claude
                else:
                    images_store = []

                async_functions[index] = (
                    handler.chain_run_async,
                    "qa_chain",
                    {
                        "text": text,
                        "question": question_with_history,
                        "images_store": images_store,
                        "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"]
                    }
                )

            # 创建一个返回禁用消息的异步函数
            async def disabled_model_response():
                return AIMessage(content='此模型您已暂时关闭使用',
                                 response_metadata={'finish_reason': 'stop'})

            # 创建要执行的任务列表
            tasks = []
            for index, (func, chain_type, params) in async_functions.items():
                # 检查该模型是否启用
                if model_states_json.get(str(index), True):  # 默认为 True，如果状态不存在
                    tasks.append(func(chain_type, params))
                else:
                    # 如果模型被禁用，添加返回禁用消息的协程
                    tasks.append(disabled_model_response())
            # 执行所有任务
            results = await asyncio.gather(*tasks)

    # results = util.chain_run(qa_chain[0], {"text": texts, "question": question})
    # results = util.chain_run(qa_chain[1], {"text": texts, "question": question})
    # claude固定隔一轮conn Err一次，未找到根因，先通过此tip消除问答窗的Err
    print("normal_qa.py-------------------------")
    print(results)
    return results


# 【标记】对外接口，三个小界面
async def get_qa_direct_api(question, user_name, history, systemPrompt="", model_states="{}"):
    """Handle direct API calls when no documents are selected"""
    system_prompt = "系统提示词"
    if systemPrompt == "":
        system_prompt = """You are an advanced AI assistant providing accurate and professional responses across 
                    technical, research, content creation, and general knowledge domains. 

                    KEY PRINCIPLES:
                    - Ensure accuracy and completeness
                    - Provide structured explanations with examples
                    - Consider multiple solutions and trade-offs
                    - Use clear language and systematic approach
                    - Validate practical applicability

                    DEFAULTS:
                    - Respond in Chinese unless otherwise specified
                    - Tailor to user context and requirements
                    - Include step-by-step explanations when needed"""
    else:
        system_prompt = systemPrompt
    system_prompt_claudeUse = system_prompt_claude + "\n" + system_prompt

    if history:
        questionGPT, questionLlama, questionKimi, questionClaude, questionDeepseek, questionDsreasoner = get_model_specific_histories(
            user_name, question)
    else:
        questionGPT = questionLlama = questionKimi = questionClaude = questionDeepseek = questionDsreasoner = question

    async def gpt_api_call():
        try:
            response = await gpt4_api.make_gpt4o_text_requests_async(
                user_prompt=questionGPT,
                system_prompt=system_prompt
            )
            return response
        except Exception as e:
            print(f"GPT4o API error: {e}")
            return "GPT4o API调用出错"

    async def llama_api_call():
        try:
            response = await llama_api.make_requests_async(
                user_prompt=questionLlama,
                system_prompt=system_prompt
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Llama3.1 API error: {e}")
            return "Llama3.1 API调用出错"

    async def kimi_api_call():
        try:
            response = await kimi_api.make_requests_async(
                prompt=questionKimi,
                api_key=None,
                is_completion=False,
                system_prompt=system_prompt,
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Kimi API error: {e}")
            return "Kimi API调用出错"

    async def claude_api_call():
        try:
            response = await claude_api.make_claude_text_requests_async(
                user_prompt=questionClaude,
                system_prompt=system_prompt_claudeUse
            )
            return response
        except Exception as e:
            print(f"Claude3.5 API error: {e}")
            return "Claude3.5 API调用出错"

    async def deepseek_api_call():
        try:
            response = await deepseek_api.make_requests_async(
                prompt=questionDeepseek,
                api_key=None,
                is_completion=False,
                system_prompt=system_prompt,
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Deepseek API error: {e}")
            return "Deepseek API调用出错"

    async def dsreasoner_api_call():
        try:
            response = await dsreasoner_api.make_requests_async(
                prompt=questionDsreasoner,
                api_key=None,
                is_completion=False,
                system_prompt=system_prompt,
                temperature=0.7,
            )
            reasoning_content = response.choices[0].message.reasoning_content
            content = response.choices[0].message.content
            result = "```" + reasoning_content + "```" + content
            return result
        except Exception as e:
            print(f"Deepseek-reasoner API error: {e}")
            return "Deepseek-reasoner API调用出错"

    # Execute all API calls in parallel
    results = None
    if model_states == "{}":
        results = await asyncio.gather(
            gpt_api_call(),
            llama_api_call(),
            kimi_api_call(),
            claude_api_call(),
            deepseek_api_call(),
            dsreasoner_api_call()
        )
    else:
        model_states_json = json.loads(model_states)
        print(model_states_json)
        # 创建API调用与索引的映射
        api_functions = {
            0: gpt_api_call,
            4: llama_api_call,
            5: kimi_api_call,
            1: claude_api_call,
            2: deepseek_api_call,
            3: dsreasoner_api_call
        }

        # 定义返回禁用消息的异步函数
        async def disabled_model_response():
            return "此模型您已暂时关闭使用"

        # 创建任务列表
        tasks = []
        for index, func in api_functions.items():
            # 检查该模型是否启用
            if model_states_json.get(str(index), True):  # 默认为True
                tasks.append(func())
            else:
                # 如果模型被禁用,添加返回禁用消息的协程
                tasks.append(disabled_model_response())
        # 执行所有任务
        results = await asyncio.gather(*tasks)

    return results


# 【标记】对外接口
def compress_image_base64(base64_string, max_size_mb=1.0, quality=85):
    """
    压缩base64图片到指定大小以内

    Args:
        base64_string (str): 原始base64字符串
        max_size_mb (float): 最大大小（MB）
        quality (int): 压缩质量（1-100）

    Returns:
        str: 压缩后的base64字符串
    """
    try:
        # 解码base64
        image_data = base64.b64decode(base64_string)
        image = Image.open(io.BytesIO(image_data))

        # 转换为RGB模式（如果是RGBA）
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')

        # 计算目标大小（字节）
        max_size_bytes = int(max_size_mb * 1024 * 1024)

        # 如果图片已经小于目标大小，直接返回
        # current_size = len(base64.b64encode(image_data).decode('utf-8'))
        # if current_size <= max_size_bytes:
        #     return base64_string
        current_size = len(base64_string)  # 使用传入的base64_string长度
        if current_size <= max_size_bytes:
            print(f"[INFO] 图片已小于目标大小: {current_size / 1024 / 1024:.2f}MB，无需压缩")
            return base64_string

        # 逐步压缩
        for attempt in range(5):  # 最多尝试5次
            # 计算压缩比例
            ratio = (max_size_bytes / current_size) ** 0.5
            if ratio < 0.1:
                ratio = 0.1  # 最小压缩比例

            # 调整图片尺寸
            new_width = int(image.width * ratio)
            new_height = int(image.height * ratio)

            if new_width < 100 or new_height < 100:
                new_width = max(100, new_width)
                new_height = max(100, new_height)

            # 调整质量
            current_quality = max(10, int(quality * ratio))

            # 压缩图片
            compressed_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 保存到内存
            output = io.BytesIO()
            compressed_image.save(output, format='JPEG', quality=current_quality, optimize=True)
            compressed_data = output.getvalue()

            # 检查压缩后的大小
            compressed_base64 = base64.b64encode(compressed_data).decode('utf-8')
            compressed_size = len(compressed_base64)

            if compressed_size <= max_size_bytes:
                print(f"[INFO] 图片压缩成功: {current_size / 1024 / 1024:.2f}MB -> {compressed_size / 1024 / 1024:.2f}MB")
                return compressed_base64

            # 更新当前大小用于下次计算
            current_size = compressed_size
            quality = max(10, int(quality * 0.8))  # 降低质量

        # 如果所有尝试都失败，返回最后一次压缩的结果
        print(f"[WARNING] 图片压缩未达到目标大小，返回最佳压缩结果: {compressed_size / 1024 / 1024:.2f}MB")
        return compressed_base64

    except Exception as e:
        print(f"[ERROR] 图片压缩失败: {e}")
        return base64_string  # 压缩失败时返回原始字符串


def construct_chain_params(question, user_name, all_segments, all_images, all_seqs, all_exts, all_sources, all_pages,
                           history, file_list, get_way, origin_real_name, base64_images, rounds=None):
    # 定义一个字典，映射文件后缀名到其MIME类型
    mime_types = {
        'jpg': 'image/jpg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        # 添加其他需要支持的图片格式
    }

    def get_base64_size(base64_str):
        # 计算base64字符串对应的原始数据字节大小
        # 直接解码base64获取原始数据大小，更准确
        try:
            return len(base64.b64decode(base64_str))
        except Exception:
            # 如果解码失败，使用近似计算
            return int(len(base64_str) * 3 / 4)

    def add_cardImage_info(info_list, image_url):
        info_list.extend([
            {
                "type": "text",
                "text": "此图片与给你的[重要素材文本]可能有较大关联，请你注意理解并用于回答用户提出的问题。"
                        "如果你参考了此图片, 请指出对一些关键点的理解分析，可以采用多层次注意分析法理解："
                        "识别图片的版面结构及区域关系、突出的自然特征、分析关联素材文本、可能存在的印刷、涂鸦层"
                        "和手写笔迹等内容，最后通过它们之间的关联理解提高准确度、加深认识"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url
                }
            }
        ])

    def add_image_info(info_list, count, total_images, seq, source, page, image_url):
        """
            info_list (list): 向info_list添加图片相关信息
            count (int): 当前图片计数
            total_images (int): 总图片数
            seq (int): 图片序号
            image_url (str): 图片的URL
        """
        if page > 0:
            info_list.extend([
                {
                    "type": "text",
                    "text": f"This is the {count}nd image of {total_images}, "
                            f"its order in all images of this document should be {seq}. And it is on page {page} of the {source}. "
                            "If you use the image, use the order in all images of document as its reference, as well as the document and page number it belongs to."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url
                    }
                }
            ])
        else:
            info_list.extend([
                {
                    "type": "text",
                    "text": "这是一张素材图片，你可以观察版面结构、辅助信息、可能的印刷内容、批注标记和手写等，通过分层注意自然关联。"
                            "此图与上下文可能有所关联，请考虑结合分析。"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url
                    }
                }
            ])

    MAX_SIZE = 5 * 1024 * 1024  # 5MB in bytes
    current_total_size = 0

    print("[Debug:construct_chain_params] ------")

    def get_segment_filename(segment, default_name):
        """从segment的metadata中提取文件名，如果没有则使用默认值"""
        source = segment.metadata.get('source', '')
        if source:
            if '/' in source or '\\' in source:
                return os.path.basename(source)
            else:
                return source
        return default_name or '未知'

    def format_segment_for_prompt(segment):
        if segment.metadata.get('unified_citation') or segment.metadata.get('source') == 'cross_notebook_ref':
            return segment.page_content
        return (
                segment.page_content
                + f"（来源：{get_segment_filename(segment, '')}，所在页数：{segment.metadata.get('page', 0) + 1 if isinstance(segment.metadata.get('page'), int) else segment.metadata.get('page', '未知')}）"
        )

    info_list = []
    info_list_claude = []
    for i, doc_segments in enumerate(all_segments):
        # text_docs = util.link_text([segment.page_content + f"（来源：{segment.metadata.get('source', '未知')}，所在页数：{segment.metadata.get('page', '未知')}）" for segment in doc_segments[:len(doc_segments) - 1]])
        # 🔥 每个segment从自己的metadata中提取文件名（因为不同segment可能有不同的source）

        text_docs = util.link_text([
            format_segment_for_prompt(segment)
            for segment in doc_segments[:len(doc_segments) - 1]
        ])

        info_list.append({
            "type": "text",
            "text": text_docs
        })
        info_list_claude.append({
            "type": "text",
            "text": text_docs
        })
        # for segment in doc_segments[:len(doc_segments)-1]:

        # cur_sequence = global_var.store_memory[user_name]["model_num"]

        # if cur_sequence == 0 or cur_sequence == 4:
        if len(all_images[i]) != 0:
            count = 0
            for image in all_images[i]:
                count += 1
                claude_list_add_cur_image = True

                # 计算当前图片的base64大小
                # image_size = get_base64_size(image)
                # 压缩图片到1MB以内
                initial_image_size = get_base64_size(image)
                compressed_image = compress_image_base64(image, max_size_mb=1.0)

                # 计算压缩后图片的base64大小
                image_size = get_base64_size(compressed_image)
                print(f"问答涉及图片压缩：{initial_image_size}字节->{image_size}字节")
                # 检查添加新图片后是否会超过限制
                if current_total_size + image_size > MAX_SIZE:
                    print(f"Skipping image {count} as it would exceed the 5MB limit")
                    claude_list_add_cur_image = False
                # 更新已使用的总大小
                current_total_size += image_size

                # 获取图片的后缀名（不带点'.'）
                image_ext = all_exts[i][count - 1].lower()
                # mime_type = mime_types.get(image_ext, 'image/png')  # 默认使用'image/png'
                mime_type = 'image/png'  # 因为gemini好像不接受jpg，所以统一试试png
                # image_url = f"data:{mime_type};base64,{image}"
                image_url = f"data:{mime_type};base64,{compressed_image}"

                add_image_info(info_list, count, len(all_images[i]), all_seqs[i][count - 1], all_sources[i][count - 1],
                               all_pages[i][count - 1], image_url)
                if claude_list_add_cur_image:
                    add_image_info(info_list_claude, count, len(all_images[i]), all_seqs[i][count - 1],
                                   all_sources[i][count - 1], all_pages[i][count - 1], image_url)

        last_segment = doc_segments[len(doc_segments) - 1]
        last_page = last_segment.metadata.get('page', 0)
        last_page_display = last_page + 1 if isinstance(last_page, int) else last_page if last_page != '未知' else '未知'
        last_text = format_segment_for_prompt(last_segment)
        info_list.append({
            "type": "text",
            "text": last_text
        })
        info_list_claude.append({
            "type": "text",
            "text": last_text
        })

    for base64_image in base64_images:
        claude_list_add_cur_card_image = True
        # 计算当前图片的base64大小
        # image_size = get_base64_size(base64_image)
        # 压缩卡片图片到1MB以内
        compressed_card_image = compress_image_base64(base64_image, max_size_mb=1.0)

        # 计算压缩后图片的base64大小
        image_size = get_base64_size(compressed_card_image)
        # 检查添加新图片后是否会超过限制
        if current_total_size + image_size > MAX_SIZE:
            print(f"Skipping image size {image_size} as it would exceed the 5MB limit")
            claude_list_add_cur_card_image = False
        # 更新已使用的总大小
        current_total_size += image_size

        # 因为gemini好像不接受jpg，所以默认试试png
        # image_url = f"data:image/png;base64,{base64_image}"
        image_url = f"data:image/png;base64,{compressed_card_image}"
        add_cardImage_info(info_list, image_url)
        if claude_list_add_cur_card_image:
            add_cardImage_info(info_list_claude, image_url)

    images_list = [HumanMessage(content=info_list)]
    images_list_claude = [HumanMessage(content=info_list_claude)]
    text = ""
    for i, doc_segments in enumerate(all_segments):
        text += util.link_text([format_segment_for_prompt(segment) for segment in doc_segments])

    print("[Debug] 正在处理带文档的问答，text内容为：")
    print(text)
    # 获取所有模型的历史记录
    # 临时字典，存储每个模型的历史记录
    question_with_history = {}

    model_names = config_manager.get_all_model_names()

    if history:
        for model_name in model_names:
            question_with_history[model_name] = get_model_specific_histories2(origin_real_name, question, model_name,
                                                                              rounds)
    else:
        for model_name in model_names:
            question_with_history[model_name] = question

    return {
        "text": text,
        "question": question,
        "images_store": images_list,
        "images_store_claude": images_list_claude,
        "qa_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa"],
        "question_with_history": question_with_history,
        "file_list": file_list,
        "get_way": get_way
    }

