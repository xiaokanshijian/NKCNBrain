import time
from langchain.chains.llm import LLMChain
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate
from llm_langchain import get_model
from llm_langchain import util
from llm_langchain import parse_input
from llm_langchain import global_var

# 在使用前需要先对sma_chain进行初始化
sma_chain = []


# 这里是对summary的链条进行初始化，现在只是一个极其简单的链条，甚至没有对输出的处理，只有在加入对输出的处理之后才能得到格式化的文本
# 这里也没有使用到关于ReAct，Agent等技术方法，有待之后看需要增加
def init_suma(sequence):
    chat_model = get_model.get_chat(sequence)
    """
    messages = [
        SystemMessage(content="You are an advanced assistant to summary the text."),
        HumanMessagePromptTemplate.from_template(
            "Summary the following text in Chinese with less 100 words:\n\n {text}"),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
    ]
    """
    messages = get_model.get_sum_msg(sequence)
    chat_template = ChatPromptTemplate.from_messages(messages)
    # 重整chat得到prompt
    # chat_val = chat_template.invoke({"text": "{text}"})
    # prompt_template = PromptTemplate.from_template(chat_val.to_string())
    global sma_chain
    sma_chain.append(chat_template | chat_model)
    sma_chain[sequence] = get_model.unique_parse(sequence, sma_chain[sequence])


def take_first(len_record):
    return len_record[0]


def take_second(len_record):
    return len_record[1]


# 根据列表长度进行处理
# 为了获得尽可能完善的得到摘要，这里的处理是等距获取
# 目前策略：拿到尽可能多的文档
# 这里目前由于最大字符数目是500
# 这里按贪心拿
def get_Same_distance_docs(docs):
    left_char = global_var.max_token_num[0] // global_var.token_per_char - global_var.left_char_for_prompt_answer
    len_doc = 0
    len_record = []
    i = 0
    texts = []
    for doc in docs:
        len_doc += len(doc.page_content) + 2  # 多加一个/n/n
        len_record.append([len_doc, i])
        i += 1
    if len_doc < left_char:
        texts = docs
    else:
        len_record.sort(key=take_first)
        all_len = 0
        last_take = 0
        for len_record_i in len_record:
            all_len += len_record_i[0]
            if all_len < left_char:
                last_take += 1
            else:
                break
        len_record = len_record[:last_take]
        len_record.sort(key=take_second)
        for len_record_i in len_record:
            texts.append(docs[len_record_i[1]])
    return texts


def get_summary_texts(texts):
    text = util.link_text(texts)
    global sma_chain
    out = util.chain_run(sma_chain, {"text": text})
    # out = sma_chain.invoke({"text": text})
    print(out.content)
    return out.content


def get_summary(user_name, docs, images, seqs):
    text = util.link_text([doc.page_content for doc in docs])
    # print(text)
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
        out = util.chain_run(sma_chain[global_var.store_memory[user_name]["model_num"]], {
                                 "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
                                 "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 1:
        out = util.chain_run_mixtral(sma_chain[global_var.store_memory[user_name]["model_num"]], {
                                 "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
                                 "text": text})
    if global_var.store_memory[user_name]["model_num"] == 2:
        out = util.chain_run_llama3(sma_chain[global_var.store_memory[user_name]["model_num"]], {
                                 "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
                                 "text": text})
    if global_var.store_memory[user_name]["model_num"] == 3:
        out = util.chain_run_kimi(sma_chain[global_var.store_memory[user_name]["model_num"]], {
                                 "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
                                 "text": text, "images_store": images_list})
    print(out.content)
    return out.content


# 这里初步决定还是先使用一个文档的分割文档，不用进行向量存储之后的（因为不确定存储后还能不能找到原文档里的顺序）
# 之后可以做更细致地处理，比如要把摘要一定放进去等等
# 强调：这是初步决定的对外部的接口。如果需要
def get_summary_docs(user_name, docs):
    docs = util.get_Same_distance_docs(docs)
    images = []
    seqs = []
    for doc in docs:
        if "type" in doc.metadata and doc.metadata["type"] == "image":
            images.append(global_var.store_memory[user_name]["images"][util.back_file_path(doc.metadata["source"])]
                          [doc.metadata["seq"] - 1])
            seqs.append(doc.metadata["seq"])
    return get_summary(user_name, docs, images, seqs)


# 废弃
def get_summary_user_docs(user_name, docs_name):
    docs = parse_input.get_split_by_user_docs(user_name, docs_name)
    return get_summary_docs(user_name, docs)


def get_summary_user_docs_way_split(user_name, docs_name, get_way, main_doc_name=None):
    begin_time = time.time()
    all_segments = util.get_docs_all_split(user_name, docs_name, get_way)
    print(f"执行 get_docs_all_split 耗时: {time.time() - begin_time}秒")
    begin_time = time.time()
    all_images, all_seqs, all_exts, all_sources, all_pages = util.parse_image_in_segment_split(user_name, all_segments)
    print(f"执行 parse_image_in_segment_split 耗时: {time.time() - begin_time}秒")
    print(all_segments)
    return get_summary_split(user_name, all_segments, all_images, all_seqs, all_exts, main_doc_name)


def get_summary_split(user_name, all_segments, all_images, all_seqs, all_exts, main_doc_name=None):
    # text = util.link_text([doc.page_content for doc in docs])
    # print(text)
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
    print(f"[get_suma主文档判断] main_doc_name={main_doc_name}, all_segments数量={len(all_segments)}")

    # 🔥 重新组织文本：主文档在前，辅助文档在后
    main_text = ""
    auxiliary_text = ""

    for i, doc_segments in enumerate(all_segments):
        # 🔥 判断当前文档是否是主文档
        is_main = False
        if main_doc_name and doc_segments:
            # 从第一个segment的metadata获取文档名
            doc_source = doc_segments[0].metadata.get('source', '')
            is_main = main_doc_name in doc_source
            print(f"[get_suma主文档判断] 文档{i}: doc_source={doc_source}, is_main={is_main}")
        elif i == 0:
            # 如果没指定主文档，默认第一个是主文档
            is_main = True
            print(f"[get_suma主文档判断] 文档{i}: 默认第一个为主文档")

        if is_main:
            # 主文档：使用完整内容
            doc_content = util.link_text([segment.page_content for segment in doc_segments])
            main_text += "【主文档】（用户点开的文档，摘要应以此为主，占比80%以上）\n" + doc_content + "\n\n"
        else:
            # 🔥 辅助文档：只使用前3段，避免干扰
            doc_content_preview = util.link_text([segment.page_content for segment in doc_segments[:3]])
            auxiliary_text += "【辅助文档】（仅供参考，已精简）\n" + doc_content_preview + "\n...(辅助文档内容已省略，请专注于主文档)\n\n"

    # 主文档在前，辅助文档在后
    # 🔥 在最前面添加明确的总指令，直接告知主文档名
    if main_text and auxiliary_text:
        main_doc_display = f"《{main_doc_name}》" if main_doc_name else "【主文档】"
        text = f"【重要提示】本次摘要生成的核心对象是{main_doc_display}，这是用户点开查看的文档。请务必以该文档为主体（占比80%以上），生成的摘要应主要围绕该文档内容展开。其他文档仅作为辅助参考，切勿本末倒置！\n\n" + main_text + auxiliary_text
    else:
        text = main_text + auxiliary_text

    # 🔥 使用增强prompt（基于飞书启发）
    try:
        from llm_langchain.prompt_enhancement_config import get_enhanced_prompt
        sum_prompt = get_enhanced_prompt(
            global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "summary"
        )
        print("[Summary-Split] 使用增强prompt")
    except:
        sum_prompt = global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"]
        print("[Summary-Split] 使用原始prompt")

    global sma_chain
    out = None
    begin_time = time.time()

    if global_var.store_memory[user_name]["model_num"] == 0:
        out = util.chain_run(sma_chain[global_var.store_memory[user_name]["model_num"]], {
            # "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 1:
        out = util.chain_run_mixtral(sma_chain[global_var.store_memory[user_name]["model_num"]], {
            # "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text})
    if global_var.store_memory[user_name]["model_num"] == 2:
        out = util.chain_run_llama3(sma_chain[global_var.store_memory[user_name]["model_num"]], {
            # "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text})
    if global_var.store_memory[user_name]["model_num"] == 3:
        out = util.chain_run_kimi(sma_chain[global_var.store_memory[user_name]["model_num"]], {
            # "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 4:
        out = util.chain_run_claude(sma_chain[global_var.store_memory[user_name]["model_num"]], {
            # "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 5:
        out = util.chain_run_deepseek(sma_chain[global_var.store_memory[user_name]["model_num"]], {
            # "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 6:
        out = util.chain_run_dsreasoner(sma_chain[global_var.store_memory[user_name]["model_num"]], {
            # "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 7:
        out = util.chain_run_Gemini(sma_chain[global_var.store_memory[user_name]["model_num"]], {
            # "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text, "images_store": images_list})
    if global_var.store_memory[user_name]["model_num"] == 8:
        out = util.chain_run_Qwq(sma_chain[global_var.store_memory[user_name]["model_num"]], {
            # "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text, "images_store": images_list})
    print(f"模型 {global_var.store_memory[user_name]['model_num']} 执行 chain_run 耗时: {time.time() - begin_time}秒")
    print(out.content)
    return out.content



