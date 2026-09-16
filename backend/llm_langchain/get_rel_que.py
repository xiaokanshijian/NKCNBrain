import random
import re
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, MessagesPlaceholder

from llm_langchain import chat_gpt_model
from llm_langchain import util
from llm_langchain import get_model
from llm_langchain import parse_input
from llm_langchain import global_var
from app_chat import gpt4_api, claude_api
que_chain = []


def parse_str_to_list(ai_message: AIMessage) -> list:
    print(ai_message.content)
    begin = ai_message.content.rfind('{')
    end = ai_message.content.rfind('}')
    all_message = ai_message.content[begin+1:end]
    all_message = all_message.replace("'", '')
    topic_list = all_message.split(',')
    return topic_list


def init_que(sequence):
    chat_model = get_model.get_chat(sequence)
    """
    messages = [
        SystemMessage(content="You are an advanced assistant to put forward a question for a given text.\n"),
        HumanMessagePromptTemplate.from_template(
            "Please put forward a question about the given text in Chinese:\n\n {text}"),
        # AIMessage(content="")  # 对AI的指明极其影响效果
    ]
    """
    messages_1, messages_2 = get_model.get_que_msg(sequence)
    messages = []
    messages.extend(messages_1)
    messages.append(MessagesPlaceholder("chat_history"))
    messages.extend(messages_2)
    chat_template = ChatPromptTemplate.from_messages(messages)
    global que_chain
    # chat_template = chat_template.partial(format_instructions=parser.get_format_instructions())
    # print(chat_template)
    # que_chain = LLMChain(prompt=chat_template, llm=chat_model, output_parser = parser)
    # que_chain = LLMChain(prompt=chat_template, llm=chat_model)
    # 两种不同形式的构造链的方式会得到不同的结果，原因未知，目前未找到LlmChain的代码并分析
    # 下面的这种符号构造将不会得chat_
    que_chain.append(chat_template | chat_model)
    que_chain[sequence] = get_model.unique_parse(sequence, que_chain[sequence])
    que_chain[sequence] = que_chain[sequence] | parse_str_to_list


# 为了获得更广范围的问题，选取随机的文本进行生成
def get_random_docs(docs):
    len_docs = len(docs)
    random_num = []
    for i in range(min(3, len_docs)):
        random_num.append(random.randint(0, len_docs - 1))
    texts = []
    for i in range(min(3, len_docs)):
        texts.append(docs[random_num[i]])
    return texts


def get_question(text, question, answer, user_name, images, seqs):
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
                            ". If you use the image, use the order in all images as its reference."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image}"
                    }
                }
            ]))
    global que_chain
    chat_history = [HumanMessage(content="This is the last q&a:\n\n"+question), AIMessage(content=answer)]
    out = None
    if global_var.store_memory[user_name]["model_num"] == 0:
        out = util.chain_run(que_chain[global_var.store_memory[user_name]["model_num"]],
                         {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"],
                          "text": text, "chat_history": chat_history, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 1:
        out = util.chain_run_mixtral(que_chain[global_var.store_memory[user_name]["model_num"]],
                         {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"],
                          "text": text, "chat_history": chat_history})
    if global_var.store_memory[user_name]["model_num"] == 2:
        out = util.chain_run_llama3(que_chain[global_var.store_memory[user_name]["model_num"]],
                         {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"],
                          "text": text, "chat_history": chat_history})
    if global_var.store_memory[user_name]["model_num"] == 3:
        out = util.chain_run_kimi(que_chain[global_var.store_memory[user_name]["model_num"]],
                         {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"],
                          "text": text, "chat_history": chat_history, "images_store": images_list})
    # out = que_chain.invoke({"text": text})
    print(out)
    return out


def get_relevant_docs(question, vector_store, docs_name, user_name):
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


# 对外的接口，输入应该是文档，是由文本、文件等分割后得到的文档序列
def get_relevant_question(vector, docs_name, question, answer, user_name):
    docs, images, seqs = get_relevant_docs(question + answer, vector, docs_name, user_name)
    # docs = util.get_random_docs(docs)
    text = util.link_text([doc.page_content for doc in docs])
    out = get_question(text, question, answer, user_name, images, seqs)
    return out


def get_rel_que_user_doc(user_name, docs_name, question, answer):
    vector = parse_input.get_vector_by_user(user_name)
    out_list = get_relevant_question(vector, docs_name, question, answer, user_name)
    if global_var.store_memory[user_name]["params"]["qa_question"] < len(out_list):
        out_list = out_list[:global_var.store_memory[user_name]["params"]["qa_question"]]
    return out_list


# FIXME
def get_rel_que_user_doc_way_split(user_name, docs_name, get_way, question, answer, special_prompt="", depth_suggestion=""):
    try:
        if not docs_name:
            out_list = claude_api.get_question_split(question, answer, user_name, special_prompt, depth_suggestion)
            # out_list = gpt4_api.get_question_split(question, answer, user_name, special_prompt, depth_suggestion)
            # 无文档情况：使用优化后的导问生成
            # out_list = get_question_split_no_docs(question, answer, user_name, special_prompt)
            if global_var.store_memory[user_name]["params"]["qa_question"] < len(out_list):
                out_list = out_list[:global_var.store_memory[user_name]["params"]["qa_question"]]
            return out_list
        else:
            segments = util.get_docs_all_split(user_name, docs_name, get_way, question + answer)
            images, seqs, exts, sources, pages = util.parse_image_in_segment_split(user_name, segments)
            out_list = get_question_split(question, answer, user_name, segments, images, seqs, exts, special_prompt, depth_suggestion)
            if global_var.store_memory[user_name]["params"]["qa_question"] < len(out_list):
                out_list = out_list[:global_var.store_memory[user_name]["params"]["qa_question"]]
            return out_list
    except Exception as e:
        print("追问出错：" + str(e))
        default_list = ['其中还有哪些更深刻的思维转换理解问题？', '这些内容包含的重要核心内容是什么？', '这些文字内容来源的撰写意图最可能是什么？']
        return default_list


def get_question_split(question, answer, user_name, all_segments, all_images, all_seqs, all_exts, special_prompt, depth_suggestion=""):
    # 1. 清理回答中的thinking/checking内容
    cleaned_answer = clean_thinking_checking(answer)

    # 2. 优化文档选择：第一段+最后一段+中间随机一段
    optimized_segments = optimize_document_selection(all_segments)

    # 3. 获取历史对话信息（最近3段）
    history_context = get_recent_conversation_history(user_name, 3)

    # 4. 获取历史问题链（只要问题，不要回答）
    question_chain = get_question_chain_history(user_name, 3)

    # 5. 先让小模型生成深度建议
    # depth_suggestion = get_depth_suggestion_from_small_model(question, cleaned_answer, question_chain,
    #                                                          optimized_segments, user_name)

    mime_types = {
        'jpg': 'image/jpg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        # 添加其他需要支持的图片格式
    }
    info_list = []
    for i, doc_segments in enumerate(optimized_segments):
    # for i, doc_segments in enumerate(all_segments):
        text_docs = util.link_text([segment.page_content for segment in doc_segments[:len(doc_segments) - 1]])
        info_list.append({
            "type": "text",
            "text": text_docs
        })
        # for segment in doc_segments[:len(doc_segments)-1]:
        if global_var.store_memory[user_name]["model_num"] == 0 or global_var.store_memory[user_name]["model_num"] == 4:
            if len(all_images[i]) != 0:
                count = 0
                for image in all_images[i]:
                    count += 1
                    # 获取图片的后缀名（不带点'.'）
                    image_ext = all_exts[i][count - 1].lower()
                    mime_type = mime_types.get(image_ext, 'image/jpeg')  # 默认使用'image/jpeg'
                    image_url = f"data:{mime_type};base64,{image}"
                    info_list.extend([
                        {
                            "type": "text",
                            "text": "This is the " + str(count) + "nd image of " + str(len(all_images[i])) +
                                    ", its order in all images of this document should be"
                                    + str(all_seqs[i][count - 1]) +
                                    ". If you use the image, use the order in all images of document as its reference."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ])
        info_list.append({
            "type": "text",
            "text": doc_segments[len(doc_segments) - 1].page_content
        })
    images_list = [HumanMessage(content=info_list)]

    # 6. 构造优化的文本内容
    text = ""
    for i, doc_segments in enumerate(optimized_segments):
    # for i, doc_segments in enumerate(all_segments):
        text += util.link_text([segment.page_content for segment in doc_segments])

    # 7. 添加历史对话上下文和深度小模型建议
    if history_context:
        text += "\n\n【历史对话脉络】\n" + history_context

    if depth_suggestion:
        text += "\n\n【追问策略建议】（小模型建议，供你生成追问时作为重要参考之一）：\n" + depth_suggestion

    global que_chain
    chat_history = [HumanMessage(content="This is the last Q&A:\n\n" + question), AIMessage(content=cleaned_answer)]
    out = None

    # # 🔥 使用增强prompt（基于飞书启发，适用于topic追问场景）
    # try:
    #     from llm_langchain.prompt_enhancement_config import get_enhanced_prompt
    #     base_prompt = global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"]
    #     # 如果special_prompt包含"topic"或"主题"，说明是topic追问场景，使用topic_question增强
    #     if "topic" in special_prompt.lower() or "主题" in special_prompt:
    #         enhanced_prompt = get_enhanced_prompt(base_prompt, "topic_question")
    #         print("[Topic追问] 使用增强prompt")
    #     else:
    #         enhanced_prompt = base_prompt
    #         print("[QA追问] 使用原始prompt")
    #     que_prompt = enhanced_prompt + special_prompt
    # except:
    #     que_prompt = global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt
    #     print("[追问] 使用原始prompt")

    # 🔥 回退：使用原始的简单prompt拼接
    que_prompt = global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt

    # 固定使用Claude 3.5/7生成追问（model_num=4）
    claude_model_num = 4
    try:
        if claude_model_num in que_chain and global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"]:
            out = util.chain_run_claude(que_chain[claude_model_num],
                                        # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                        {"que_prompt": que_prompt,
                                         "text": text, "chat_history": chat_history, "images_store": images_list})

        # Claude调用貌似第一次经常失败，给两次机会
        if out is None:
            out = util.chain_run_claude(que_chain[claude_model_num],
                                        # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                        {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                         "text": text, "chat_history": chat_history, "images_store": images_list})

        # 如果Claude 3.5连续两次调用失败或返回None，使用原用户模型作为回退
        if out is None:
            user_model_num = global_var.store_memory[user_name]["model_num"]
            if user_model_num == 0:
                out = util.chain_run(que_chain[user_model_num],
                                     # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                     {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                      "text": text, "chat_history": chat_history, "images_store": images_list})
            elif user_model_num == 1:
                out = util.chain_run_mixtral(que_chain[user_model_num],
                                             # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                             {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                              "text": text, "chat_history": chat_history})
            elif user_model_num == 2:
                out = util.chain_run_llama3(que_chain[user_model_num],
                                            # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                            {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                             "text": text, "chat_history": chat_history})
            elif user_model_num == 3:
                out = util.chain_run_kimi(que_chain[user_model_num],
                                          # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                          {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                           "text": text, "chat_history": chat_history, "images_store": images_list})
            elif user_model_num == 4:
                out = util.chain_run_claude(que_chain[user_model_num],
                                            # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                            {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                             "text": text, "chat_history": chat_history, "images_store": images_list})
            elif user_model_num == 5:
                out = util.chain_run_deepseek(que_chain[user_model_num],
                                              # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                              {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                               "text": text, "chat_history": chat_history, "images_store": images_list})
            elif user_model_num == 6:
                out = util.chain_run_dsreasoner(que_chain[user_model_num],
                                                # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                                {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                                 "text": text, "chat_history": chat_history,
                                                 "images_store": images_list})
            elif user_model_num == 7:
                out = util.chain_run_Gemini(que_chain[user_model_num],
                                            # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                            {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                             "text": text, "chat_history": chat_history, "images_store": images_list})
            elif user_model_num == 8:
                out = util.chain_run_Qwq(que_chain[user_model_num],
                                         # {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
                                         {"que_prompt": que_prompt,  # 🔥 使用增强后的que_prompt
                                          "text": text, "chat_history": chat_history, "images_store": images_list})
    except Exception as e:
        print(f"[追问生成] Claude 3.5调用失败: {e}")
        # 如果仍有问题，返回空列表
        out = []

    # 以下是原代码，已注释保留（以防需要回滚）
    # if global_var.store_memory[user_name]["model_num"] == 0:
    #     out = util.chain_run(que_chain[global_var.store_memory[user_name]["model_num"]],
    #                          {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
    #                           "text": text, "chat_history": chat_history, "images_store": images_list})
    # if global_var.store_memory[user_name]["model_num"] == 1:
    #     out = util.chain_run_mixtral(que_chain[global_var.store_memory[user_name]["model_num"]],
    #                                  {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
    #                                   "text": text, "chat_history": chat_history})
    # if global_var.store_memory[user_name]["model_num"] == 2:
    #     out = util.chain_run_llama3(que_chain[global_var.store_memory[user_name]["model_num"]],
    #                                 {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
    #                                  "text": text, "chat_history": chat_history})
    # if global_var.store_memory[user_name]["model_num"] == 3:
    #     out = util.chain_run_kimi(que_chain[global_var.store_memory[user_name]["model_num"]],
    #                               {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
    #                                "text": text, "chat_history": chat_history, "images_store": images_list})
    # if global_var.store_memory[user_name]["model_num"] == 4:
    #     out = util.chain_run_claude(que_chain[global_var.store_memory[user_name]["model_num"]],
    #                               {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
    #                                "text": text, "chat_history": chat_history, "images_store": images_list})
    # if global_var.store_memory[user_name]["model_num"] == 5:
    #     out = util.chain_run_deepseek(que_chain[global_var.store_memory[user_name]["model_num"]],
    #                               {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
    #                                "text": text, "chat_history": chat_history, "images_store": images_list})
    # if global_var.store_memory[user_name]["model_num"] == 6:
    #     out = util.chain_run_dsreasoner(que_chain[global_var.store_memory[user_name]["model_num"]],
    #                               {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
    #                                "text": text, "chat_history": chat_history, "images_store": images_list})
    # if global_var.store_memory[user_name]["model_num"] == 7:
    #     out = util.chain_run_Gemini(que_chain[global_var.store_memory[user_name]["model_num"]],
    #                               {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
    #                                "text": text, "chat_history": chat_history, "images_store": images_list})
    # if global_var.store_memory[user_name]["model_num"] == 8:
    #     out = util.chain_run_Qwq(que_chain[global_var.store_memory[user_name]["model_num"]],
    #                               {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"] + special_prompt,
    #                                "text": text, "chat_history": chat_history, "images_store": images_list})
    # out = que_chain.invoke({"text": text})
    print(out)
    return out


def clean_thinking_checking(text):
    """清理回答中的thinking/checking内容"""
    if not text:
        return text

    # 移除thinking块
    text = re.sub(r'```thinking[\s\S]*?```', '', text)
    # 移除checking块
    text = re.sub(r'```checking[\s\S]*?```', '', text)
    # 清理多余的空行
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()


def optimize_document_selection(all_segments):
    """优化文档选择：第一段+最后一段+中间随机一段"""
    optimized_segments = []

    for doc_segments in all_segments:
        if len(doc_segments) <= 3:
            # 如果段落数<=3，全部保留
            optimized_segments.append(doc_segments)
        else:
            # 选择第一段、最后一段、中间随机一段
            selected_segments = []
            selected_segments.append(doc_segments[0])  # 第一段

            # 中间随机一段
            if len(doc_segments) > 2:
                middle_index = random.randint(1, len(doc_segments) - 2)
                selected_segments.append(doc_segments[middle_index])

            selected_segments.append(doc_segments[-1])  # 最后一段
            optimized_segments.append(selected_segments)

    return optimized_segments


def get_recent_conversation_history(user_name, count=3):
    """获取最近的历史对话信息"""
    try:
        # 从全局变量中获取历史对话
        if hasattr(global_var, 'chat_history') and user_name in global_var.chat_history:
            history = global_var.chat_history[user_name]
            if len(history) <= 1:  # 只有当前对话，没有历史
                return ""

            # 获取最近的count段对话（排除当前对话）
            recent_history = history[-(count + 1):-1] if len(history) > count else history[:-1]

            history_text = ""
            for i, conv in enumerate(recent_history):
                question = conv.get('message', '')
                answer = conv.get('AImessage', '')

                # 处理问题：限制100字，取最后一个问号前的内容
                if len(question) > 100:
                    last_question_mark = max(question.rfind('？'), question.rfind('?'))
                    if last_question_mark > 0:
                        question = question[:last_question_mark + 1]
                    else:
                        question = question[:100] + '...'

                # 处理回答：智能压缩
                if isinstance(answer, list) and len(answer) > 0:
                    answer = answer[0]  # 取第一个回答

                compressed_answer = compress_answer_text(answer)

                history_text += f"第{i + 1}轮对话：\n"
                history_text += f"问题：{question}\n"
                history_text += f"回答：{compressed_answer}\n\n"

            return history_text
        else:
            return ""
    except Exception as e:
        print(f"获取历史对话失败: {e}")
        return ""


def compress_answer_text(text):
    """智能压缩回答文本"""
    if not text or len(text) <= 500:
        return text

    # 判断是否为换行密集型文本（诗歌/代码类）
    lines = text.split('\n')
    avg_line_length = sum(len(line) for line in lines) / len(lines) if lines else 0

    if avg_line_length < 30:  # 换行密集型文本
        # 保留前1/4和后1/4
        quarter = len(text) // 4
        return text[:quarter] + "\n...\n" + text[-quarter:]
    else:
        # 普通文本：保留第一段和最后一段，中间段落压缩
        paragraphs = text.split('\n\n')
        if len(paragraphs) <= 2:
            return text

        compressed_paragraphs = [paragraphs[0]]  # 第一段

        # 压缩中间段落
        for para in paragraphs[1:-1]:
            if len(para) <= 100:
                compressed_paragraphs.append(para)
            else:
                # 保留前50字和后50字
                compressed_para = para[:50] + "..." + para[-50:]
                compressed_paragraphs.append(compressed_para)

        compressed_paragraphs.append(paragraphs[-1])  # 最后一段
        return '\n\n'.join(compressed_paragraphs)


def get_question_chain_history(user_name, count=3):
    """获取历史问题链（只要问题，不要回答）"""
    try:
        if hasattr(global_var, 'chat_history') and user_name in global_var.chat_history:
            history = global_var.chat_history[user_name]
            if len(history) <= 1:
                return ""

            # 获取最近的count段对话（排除当前对话）
            recent_history = history[-(count + 1):-1] if len(history) > count else history[:-1]

            question_chain = ""
            for i, conv in enumerate(recent_history):
                question = conv.get('message', '')

                # 处理问题：限制100字，取最后一个问号前的内容
                if len(question) > 100:
                    last_question_mark = max(question.rfind('？'), question.rfind('?'))
                    if last_question_mark > 0:
                        question = question[:last_question_mark + 1]
                    else:
                        question = question[:100] + '...'

                question_chain += f"第{i + 1}轮问题：{question}\n"

            return question_chain
        else:
            return ""
    except Exception as e:
        print(f"获取历史问题链失败: {e}")
        return ""


def get_depth_suggestion_from_small_model(question, answer, question_chain, optimized_segments, user_name):
    """让小模型生成深度建议"""
    try:
        # 构造输入文本
        input_text = ""
        if question_chain:
            input_text += "【历史问题链】\n" + question_chain + "\n\n"

        input_text += "【当前问答】\n"
        input_text += f"问题：{question}\n"
        input_text += f"回答：{answer}\n"

        # 添加RAG采样（三段每段100字）
        if optimized_segments:
            input_text += "\n【参考文档】\n"
            for i, doc_segments in enumerate(optimized_segments):
                for j, segment in enumerate(doc_segments):
                    content = segment.page_content
                    if len(content) > 100:
                        content = content[:100] + "..."
                    input_text += f"文档{i + 1}段落{j + 1}：{content}\n"

        # 调用小模型生成深度建议
        suggestion = get_depth_suggestion(input_text, user_name)
        return suggestion
    except Exception as e:
        print(f"小模型深度建议生成失败: {e}")
        return ""


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


def get_depth_suggestion(input_text, user_name, task_type="qa"):
    """
    应用服务器方式：调用小模型生成深度追问建议
    参数:
        task_type: "qa" 表示增强追问，"summary" 表示增强摘要/主题
    """
    try:
        import subprocess
        import json
        import requests

        # 处理特殊字符
        input_text = input_text.replace("\n", "\\n")
        input_text = input_text.replace('```', '').replace('"""', '').replace('"', '“').replace("'", '‘')

        json_data = json.dumps({
            "input_text": input_text,
            "user_name": user_name,
            "task_type": task_type
        }, ensure_ascii=False)  # 保持中文字符

        # 从全局变量获取小模型ID
        server_url = get_small_model_server_url(user_name)
        # 使用curl命令调用中转服务器的深度建议接口
        # command = f'curl -X POST -H "Content-Type: application/json" -d \'{json_data}\' http://192.0.2.1:8000/get_depth_suggestion'
        command = f'curl -X POST -H "Content-Type: application/json" -d \'{json_data}\' {server_url}/get_depth_suggestion'
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

        # 解析返回结果
        result_data = json.loads(result.stdout)

        if result_data.get('error_num') == 0:
            suggestion = result_data.get('suggestion', '')
            print(f"[应用服务器方式] 深度建议生成成功")
            return suggestion
        else:
            print(f"[应用服务器方式] 深度建议生成失败: {result_data.get('message', '未知错误')}")
            return ""

    except subprocess.CalledProcessError as e:
        print(f"[应用服务器方式] curl命令执行失败: {e.stderr}")
        return ""
    except json.JSONDecodeError as e:
        print(f"[应用服务器方式] JSON解析失败: {e}")
        return ""
    except Exception as e:
        print(f"[应用服务器方式] 深度建议生成异常: {e}")
        return ""


# def get_question_split_no_docs(question, answer, user_name, special_prompt):
#     """无文档情况下的导问生成"""
#     # 1. 清理回答中的thinking/checking内容
#     cleaned_answer = clean_thinking_checking(answer)
#
#     # 2. 获取历史对话信息（最近3段）
#     history_context = get_recent_conversation_history(user_name, 3)
#
#     # 3. 获取历史问题链（只要问题，不要回答）
#     question_chain = get_question_chain_history(user_name, 3)
#
#     # 4. 先让小模型生成深度建议
#     depth_suggestion = get_depth_suggestion_from_small_model(question, cleaned_answer, question_chain, [], user_name)
#
#     # 5. 构造优化的输入文本
#     text = ""
#     if history_context:
#         text += "【历史对话脉络】\n" + history_context + "\n\n"
#
#     text += "【当前问答】\n"
#     text += f"问题：{question}\n"
#     text += f"回答：{cleaned_answer}\n"
#
#     if depth_suggestion:
#         text += "\n【深度建议】\n" + depth_suggestion + "\n"
#
#     chat_history = [HumanMessage(content="This is the last Q&A:\n\n" + question), AIMessage(content=cleaned_answer)]
#
#     # 6. 调用模型生成导问
#     global que_chain
#     out = None
#     if global_var.store_memory[user_name]["model_num"] == 0:
#         out = util.chain_run(que_chain[global_var.store_memory[user_name]["model_num"]],
#                              {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"][
#                                                 "qa_question"] + special_prompt,
#                               "text": text, "chat_history": chat_history, "images_store": []})
#     elif global_var.store_memory[user_name]["model_num"] == 1:
#         out = util.chain_run_mixtral(que_chain[global_var.store_memory[user_name]["model_num"]],
#                                      {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"][
#                                                         "qa_question"] + special_prompt,
#                                       "text": text, "chat_history": chat_history})
#     elif global_var.store_memory[user_name]["model_num"] == 2:
#         out = util.chain_run_llama3(que_chain[global_var.store_memory[user_name]["model_num"]],
#                                     {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"][
#                                                        "qa_question"] + special_prompt,
#                                      "text": text, "chat_history": chat_history})
#     elif global_var.store_memory[user_name]["model_num"] == 3:
#         out = util.chain_run_kimi(que_chain[global_var.store_memory[user_name]["model_num"]],
#                                   {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"][
#                                                      "qa_question"] + special_prompt,
#                                    "text": text, "chat_history": chat_history, "images_store": []})
#     elif global_var.store_memory[user_name]["model_num"] == 4:
#         out = util.chain_run_claude(que_chain[global_var.store_memory[user_name]["model_num"]],
#                                     {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"][
#                                                        "qa_question"] + special_prompt,
#                                      "text": text, "chat_history": chat_history, "images_store": []})
#     elif global_var.store_memory[user_name]["model_num"] == 5:
#         out = util.chain_run_deepseek(que_chain[global_var.store_memory[user_name]["model_num"]],
#                                       {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"][
#                                                          "qa_question"] + special_prompt,
#                                        "text": text, "chat_history": chat_history, "images_store": []})
#     elif global_var.store_memory[user_name]["model_num"] == 6:
#         out = util.chain_run_dsreasoner(que_chain[global_var.store_memory[user_name]["model_num"]],
#                                         {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"][
#                                                            "qa_question"] + special_prompt,
#                                          "text": text, "chat_history": chat_history, "images_store": []})
#     elif global_var.store_memory[user_name]["model_num"] == 7:
#         out = util.chain_run_Gemini(que_chain[global_var.store_memory[user_name]["model_num"]],
#                                     {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"][
#                                                        "qa_question"] + special_prompt,
#                                      "text": text, "chat_history": chat_history, "images_store": []})
#     elif global_var.store_memory[user_name]["model_num"] == 8:
#         out = util.chain_run_Qwq(que_chain[global_var.store_memory[user_name]["model_num"]],
#                                  {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"][
#                                                     "qa_question"] + special_prompt,
#                                   "text": text, "chat_history": chat_history, "images_store": []})
#
#     print(out)
#     return out
