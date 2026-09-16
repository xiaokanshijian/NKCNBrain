from langchain.chains.llm import LLMChain
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate, \
    FewShotChatMessagePromptTemplate
from llm_langchain import get_model, global_var
from llm_langchain import util
from llm_langchain import parse_input

# 在使用前需要先对sma_chain进行初始化
topic_chain = []


# 以{}包裹的str
# 现在这些处理函数都没写异步
# 异步现在只存在于调用api那一步上
def parse_str_to_list(ai_message: AIMessage) -> list:
    print(ai_message.content)
    begin = ai_message.content.rfind('{')
    end = ai_message.content.rfind('}')
    all_message = ai_message.content[begin + 1:end]
    all_message = all_message.replace("'", '')
    topic_list = all_message.split(',')
    return topic_list


# 这里是对summary的链条进行初始化，现在只是一个极其简单的链条，甚至没有对输出的处理，只有在加入对输出的处理之后才能得到格式化的文本
# 这里也没有使用到关于ReAct，Agent等技术方法，有待之后看需要增加
def init_topic(sequence):
    chat_model = get_model.get_chat(sequence)
    """
    messages = [
        SystemMessage(content="You are an advanced assistant to summary the text."),
        HumanMessagePromptTemplate.from_template(
            "Summary the following text in Chinese with less 100 words:\n\n {text}"),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
    ]
    """
    examples = [
        {"input": "大语言模型的研究融合了自然语言处理、机器学习、分布式计算、并行计算等多个学科领域。"
                  "其发展历程可以分为基础模型阶段、能力探索阶段和突破发展阶段。",
         "output": "{'大语言模型'}"},
        {"input": "有监督微调（Supervised Finetuning），也称为指令微调（Instruction Tuning），利用少量高质量数据"
                  "集合，包含用户输入的提示词（Prompt）和对应的理想输出结果。用户输入包括问题、闲聊对话、任务指令等多种形式和任务。。",
         "output": "{'指令微调'}"}
    ]
    example_prompt = ChatPromptTemplate.from_messages(
        [
            ("human", "{input}"),
            ("ai", "{output}"),
        ]
    )
    few_shot_prompt = FewShotChatMessagePromptTemplate(
        example_prompt=example_prompt,
        examples=examples,
    )
    messages_1, messages_2 = get_model.get_topic_msg(sequence)
    messages = []
    messages.extend(messages_1)
    messages.append(few_shot_prompt)
    messages.extend(messages_2)
    print(messages)
    chat_template = ChatPromptTemplate.from_messages(messages)
    # 重整chat得到prompt
    # chat_val = chat_template.invoke({"text": "{text}"})
    # prompt_template = PromptTemplate.from_template(chat_val.to_string())
    global topic_chain
    topic_chain.append(chat_template | chat_model)
    topic_chain[sequence] = get_model.unique_parse(sequence, topic_chain[sequence])
    topic_chain[sequence] = topic_chain[sequence] | parse_str_to_list


def get_topic(user_name, text, images, seqs):
    global topic_chain
    images_list = []
    count = 0
    global sma_chain
    if global_var.store_memory[user_name]["model_num"] == 0:
        if len(images) != 0:
            for image in images:
                count += 1
                images_list.append(HumanMessage(content=[
                    {
                        "type": "text",
                        "text": "This is the " + str(count) + "nd image of " + str(len(images)) + ", its order "
                                                                                                  "in all images "
                                                                                                  "should be"
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
    out = None
    if global_var.store_memory[user_name]["model_num"] == 0:
        out = util.chain_run(topic_chain[global_var.store_memory[user_name]["model_num"]], {
               "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
                "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 1:
        out = util.chain_run_mixtral(topic_chain[global_var.store_memory[user_name]["model_num"]], {
               "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
                "text": text})
    if global_var.store_memory[user_name]["model_num"] == 2:
        out = util.chain_run_llama3(topic_chain[global_var.store_memory[user_name]["model_num"]], {
               "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
                "text": text})
    if global_var.store_memory[user_name]["model_num"] == 3:
        out = util.chain_run_kimi(topic_chain[global_var.store_memory[user_name]["model_num"]], {
               "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
                "text": text, "images_store": images_list})
    # out = que_chain.invoke({"text": text})
    print(out)
    return out


def get_topic_docs(user_name, docs):
    docs = util.get_Same_distance_docs(docs)
    images = []
    seqs = []
    for doc in docs:
        if "type" in doc.metadata and doc.metadata["type"] == "image":
            images.append(global_var.store_memory[user_name]["images"][util.back_file_path(doc.metadata["source"])]
                          [doc.metadata["seq"] - 1])
            seqs.append(doc.metadata["seq"])
    text = util.link_text([doc.page_content for doc in docs])
    out_list = get_topic(user_name, text, images, seqs)
    return out_list


def get_topic_user_docs(user_name, docs_name):
    docs = parse_input.get_split_by_user_docs(user_name, docs_name)
    out_list = get_topic_docs(user_name, docs)
    if global_var.store_memory[user_name]["params"]["topic"] < len(out_list):
        out_list = out_list[:global_var.store_memory[user_name]["params"]["topic"]]
    return out_list



# FIXME
def get_topic_user_docs_way_split(user_name, docs_name, get_way, main_doc_name=None):
    segments = util.get_docs_all_split(user_name, docs_name, get_way)
    images, seqs, exts, sources, pages = util.parse_image_in_segment_split(user_name, segments)
    print(segments)
    out_list = get_topic_split(user_name, segments, images, seqs, exts, main_doc_name)
    if global_var.store_memory[user_name]["params"]["topic"] < len(out_list):
        out_list = out_list[:global_var.store_memory[user_name]["params"]["topic"]]
    return out_list


def get_topic_split(user_name, all_segments, all_images, all_seqs, all_exts, main_doc_name=None):
    mime_types = {
        'jpg': 'image/jpg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        # 添加其他需要支持的图片格式
    }

    # 🔥 先识别主文档索引，调整处理顺序
    main_doc_index = -1
    if main_doc_name:
        for i, doc_segments in enumerate(all_segments):
            if doc_segments:
                doc_source = doc_segments[0].metadata.get('source', '')
                if main_doc_name in doc_source:
                    main_doc_index = i
                    break
    if main_doc_index == -1:
        main_doc_index = 0  # 默认第一个

    # 重排索引：主文档在前
    doc_indices = [main_doc_index] + [i for i in range(len(all_segments)) if i != main_doc_index]

    info_list = []

    # 🔥 读取每个文档的预处理md摘要和图片分析摘要（如果存在），添加到info_list开头
    import os
    if all_segments:
        # 从第一个segment获取username信息
        first_segment = all_segments[0][0] if all_segments[0] else None
        if first_segment and 'source' in first_segment.metadata:
            source_path = first_segment.metadata['source']
            # 从source路径中提取username（格式：received_dir/user_raw_file/用户名_本子名/文件名）
            try:
                parts = source_path.split('/')
                if 'user_raw_file' in parts:
                    user_raw_file_idx = parts.index('user_raw_file')
                    if user_raw_file_idx + 1 < len(parts):
                        username = parts[user_raw_file_idx + 1]
                        if '_' in username:
                            realName = username.split('_')[0]
                            bookName = username[len(realName) + 1:]

                            # 遍历所有文档，读取pre_summary和pre_image_summary
                            for i, doc_segments in enumerate(all_segments):
                                if not doc_segments:
                                    continue
                                doc_source = doc_segments[0].metadata.get('source', '')
                                # 从source路径中提取文档名
                                doc_name = os.path.basename(doc_source)
                                if not doc_name:
                                    continue

                                # 读取pre_summary
                                doc_name_base = os.path.splitext(doc_name)[0]
                                doc_ext = os.path.splitext(doc_name)[1].lstrip('.')
                                md_file_path = f'./received_dir/user_raw_file/{realName}_{bookName}/pre_summary/{doc_name_base}_Presummary_{doc_ext}.md'

                                if os.path.exists(md_file_path):
                                    try:
                                        with open(md_file_path, 'r', encoding='utf-8') as f:
                                            md_content = f.read().strip()
                                            if md_content:
                                                info_list.append({
                                                    "type": "text",
                                                    "text": f"【文档 {doc_name} 的预处理章节分段摘要】\n（最终主题提取时不要输出此处这些[页数]信息，而应该聚焦其中具体分段内容）\n{md_content}"
                                                })
                                                print(f"[get_topic_split] 已添加文档 {doc_name} 的预处理摘要")
                                    except Exception as e:
                                        print(f"[get_topic_split] 读取文档 {doc_name} 的预处理摘要失败: {e}")

                                # 🔥 如果存在图片分析摘要，也一并输入给模型
                                if doc_name.lower().endswith('.pdf'):
                                    pre_image_summary_path = f'./received_dir/user_raw_file/{realName}_{bookName}/pre_image_summary/{doc_name_base}_PreImageSummary_pdf.md'
                                    if os.path.exists(pre_image_summary_path):
                                        try:
                                            with open(pre_image_summary_path, 'r', encoding='utf-8') as f:
                                                image_summary_content = f.read().strip()
                                                if image_summary_content:
                                                    info_list.append({
                                                        "type": "text",
                                                        "text": f"【文档 {doc_name} 的图片分析摘要】\n（这是文档中所有图片的智能分析摘要，包含图片内容、位置和上下文信息。在提取主题时，请结合文本内容和图片信息，提供更全面的主题。最终主题提取时不要输出此处这些[页数]信息，而应该聚焦其中具体分段内容）\n{image_summary_content}"
                                                    })
                                                    print(f"[get_topic_split] 已添加文档 {doc_name} 的图片分析摘要")
                                        except Exception as e:
                                            print(f"[get_topic_split] 读取文档 {doc_name} 的图片分析摘要失败: {e}")
            except Exception as e:
                print(f"[get_topic_split] 解析username失败: {e}")

    for idx in doc_indices:
        doc_segments = all_segments[idx]
        text_docs = util.link_text([segment.page_content for segment in doc_segments[:len(doc_segments) - 1]])
        info_list.append({
            "type": "text",
            "text": text_docs
        })
        # for segment in doc_segments[:len(doc_segments)-1]:
        if global_var.store_memory[user_name]["model_num"] == 0 or global_var.store_memory[user_name]["model_num"] == 4:
            if len(all_images[idx]) != 0:
                count = 0
                for image in all_images[idx]:
                    count += 1
                    # 获取图片的后缀名（不带点'.'）
                    image_ext = all_exts[idx][count - 1].lower()
                    mime_type = mime_types.get(image_ext, 'image/jpeg')  # 默认使用'image/jpeg'
                    image_url = f"data:{mime_type};base64,{image}"
                    info_list.extend([
                        {
                            "type": "text",
                            "text": "This is the " + str(count) + "nd image of " + str(len(all_images[idx])) +
                                    ", its order in all images of this document should be"
                                    + str(all_seqs[idx][count - 1]) +
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
    # text = ""
    print(f"[get_topic主文档判断] main_doc_name={main_doc_name}, all_segments数量={len(all_segments)}")

    # 🔥 重新组织文本：主文档在前，辅助文档在后
    main_text = ""
    auxiliary_text = ""

    for i, doc_segments in enumerate(all_segments):
        # 🔥 判断当前文档是否是主文档
        is_main = False
        if main_doc_name and doc_segments:
            doc_source = doc_segments[0].metadata.get('source', '')
            is_main = main_doc_name in doc_source
            print(f"[get_topic主文档判断] 文档{i}: doc_source={doc_source}, is_main={is_main}")
        elif i == 0:
            is_main = True
            print(f"[get_topic主文档判断] 文档{i}: 默认第一个为主文档")

        if is_main:
            # 主文档：使用完整内容
            doc_content = util.link_text([segment.page_content for segment in doc_segments])
            main_text += "【主文档】（用户点开的文档，主题应以此为主，占比80%以上）\n" + doc_content + "\n\n"
        else:
            # 🔥 辅助文档：只使用前3段，避免干扰
            doc_content_preview = util.link_text([segment.page_content for segment in doc_segments[:3]])
            auxiliary_text += "【辅助文档】（仅供参考，已精简）\n" + doc_content_preview + "\n...(辅助文档内容已省略，请专注于主文档)\n\n"

    # 主文档在前，辅助文档在后
    # 🔥 在最前面添加明确的总指令，直接告知主文档名
    if main_text and auxiliary_text:
        main_doc_display = f"《{main_doc_name}》" if main_doc_name else "【主文档】"
        text = f"【重要提示】本次主题提取的核心对象是{main_doc_display}，这是用户点开查看的文档。请务必以该文档为主体（占比80%以上），提取的主题应主要来自该文档内容。其他文档仅作为辅助参考，切勿本末倒置！\n\n" + main_text + auxiliary_text
    else:
        text = main_text + auxiliary_text

    # 🔥 使用增强prompt（基于飞书启发）
    try:
        from llm_langchain.prompt_enhancement_config import get_enhanced_prompt
        topic_prompt = get_enhanced_prompt(
            global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic"
        )
        print("[Topic-Split] 使用增强prompt")
    except:
        topic_prompt = global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"]
        print("[Topic-Split] 使用原始prompt")

    global topic_chain
    print(global_var.store_memory[user_name]["model_num"])
    out = None

    if global_var.store_memory[user_name]["model_num"] == 0:
        out = util.chain_run(topic_chain[global_var.store_memory[user_name]["model_num"]], {
            # "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic_prompt": topic_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 1:
        out = util.chain_run_mixtral(topic_chain[global_var.store_memory[user_name]["model_num"]], {
            # "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic_prompt": topic_prompt,
            "text": text})
    if global_var.store_memory[user_name]["model_num"] == 2:
        out = util.chain_run_llama3(topic_chain[global_var.store_memory[user_name]["model_num"]], {
            # "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic_prompt": topic_prompt,
            "text": text})
    if global_var.store_memory[user_name]["model_num"] == 3:
        out = util.chain_run_kimi(topic_chain[global_var.store_memory[user_name]["model_num"]], {
            # "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic_prompt": topic_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 4:
        out = util.chain_run_claude(topic_chain[global_var.store_memory[user_name]["model_num"]], {
            # "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic_prompt": topic_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 5:
        out = util.chain_run_deepseek(topic_chain[global_var.store_memory[user_name]["model_num"]], {
            # "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic_prompt": topic_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 6:
        out = util.chain_run_dsreasoner(topic_chain[global_var.store_memory[user_name]["model_num"]], {
            # "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic_prompt": topic_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 7:
        out = util.chain_run_Gemini(topic_chain[global_var.store_memory[user_name]["model_num"]], {
            # "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic_prompt": topic_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 8:
        out = util.chain_run_Qwq(topic_chain[global_var.store_memory[user_name]["model_num"]], {
            # "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
            "topic_prompt": topic_prompt,
            "text": text, "images_store": images_list})

    # claude_model_num = 4
    # try:
    #     if claude_model_num in topic_chain and global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"]:
    #         out = util.chain_run_claude(topic_chain[claude_model_num], {
    #             "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #             "text": text, "images_store": images_list})
    #
    #     # Claude调用貌似第一次经常失败，给两次机会
    #     if out is None:
    #         out = util.chain_run_claude(topic_chain[claude_model_num], {
    #             "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #             "text": text, "images_store": images_list})
    #
    #     # 如果Claude 3.5连续两次调用失败或返回None，使用原用户模型作为回退
    #     if out is None:
    #         if global_var.store_memory[user_name]["model_num"] == 0:
    #             out = util.chain_run(topic_chain[global_var.store_memory[user_name]["model_num"]], {
    #                    "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #                     "text": text, "images_store": images_list})
    #         if global_var.store_memory[user_name]["model_num"] == 1:
    #             out = util.chain_run_mixtral(topic_chain[global_var.store_memory[user_name]["model_num"]], {
    #                    "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #                     "text": text})
    #         if global_var.store_memory[user_name]["model_num"] == 2:
    #             out = util.chain_run_llama3(topic_chain[global_var.store_memory[user_name]["model_num"]], {
    #                    "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #                     "text": text})
    #         if global_var.store_memory[user_name]["model_num"] == 3:
    #             out = util.chain_run_kimi(topic_chain[global_var.store_memory[user_name]["model_num"]], {
    #                    "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #                     "text": text, "images_store": images_list})
    #         if global_var.store_memory[user_name]["model_num"] == 4:
    #             out = util.chain_run_claude(topic_chain[global_var.store_memory[user_name]["model_num"]], {
    #                    "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #                     "text": text, "images_store": images_list})
    #         if global_var.store_memory[user_name]["model_num"] == 5:
    #             out = util.chain_run_deepseek(topic_chain[global_var.store_memory[user_name]["model_num"]], {
    #                    "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #                     "text": text, "images_store": images_list})
    #         if global_var.store_memory[user_name]["model_num"] == 6:
    #             out = util.chain_run_dsreasoner(topic_chain[global_var.store_memory[user_name]["model_num"]], {
    #                    "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #                     "text": text, "images_store": images_list})
    #         if global_var.store_memory[user_name]["model_num"] == 7:
    #             out = util.chain_run_Gemini(topic_chain[global_var.store_memory[user_name]["model_num"]], {
    #                    "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #                     "text": text, "images_store": images_list})
    #         if global_var.store_memory[user_name]["model_num"] == 8:
    #             out = util.chain_run_Qwq(topic_chain[global_var.store_memory[user_name]["model_num"]], {
    #                    "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
    #                     "text": text, "images_store": images_list})
    # except Exception as e:
    #     print(f"[topic生成] Claude 3.7调用失败: {e}")
    #     # 如果仍有问题，返回空列表
    #     out = []

    print(out)
    return out
