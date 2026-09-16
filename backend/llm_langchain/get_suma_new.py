from langchain.chains.llm import LLMChain
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate
from llm_langchain import get_model
from llm_langchain import util
from llm_langchain import parse_input
from llm_langchain import global_var

from app_chat.core.model_manager import model_manager

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


def get_summary(user_name, docs, images, seqs):
    text = util.link_text([doc.page_content for doc in docs])
    # print(text)
    images_list = []
    count = 0
    
    cur_sequence = global_var.store_memory[user_name]["model_num"]
    
    # 先根据seq获取模型handler，再直接拿出来
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    
    if cur_sequence == 0:
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
    
    out = cur_handler.chain_run("sma_chain", {
                                 "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
                                 "text": text, "images_store": images_list})
    
    print("[DEBUG] Summary generation output:",out.content)
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


def get_summary_user_docs_way_split(user_name, docs_name, get_way):
    # 输入参数打印
    print("[DEBUG] get_summary_user_docs_way_split user_name:", user_name)
    print("[DEBUG] get_summary_user_docs_way_split docs_name:", docs_name)
    
    all_segments = util.get_docs_all_split(user_name, docs_name, get_way)
    all_images, all_seqs, all_exts, all_sources, all_pages = util.parse_image_in_segment_split(user_name, all_segments)
    
    # 打印调试信息
    print("[DEBUG] get_summary_user_docs_way_split all_segments:", str(all_segments)[:50])
    print("[DEBUG] get_summary_user_docs_way_split all_images:", all_images)
    print("[DEBUG] get_summary_user_docs_way_split all_seqs:", all_seqs)
    print("[DEBUG] get_summary_user_docs_way_split all_exts:", all_exts)
    
    return get_summary_split(user_name, all_segments, all_images, all_seqs, all_exts)


def get_summary_split(user_name, all_segments, all_images, all_seqs, all_exts):
    # text = util.link_text([doc.page_content for doc in docs])
    # print(text)
    mime_types = {
        'jpg': 'image/jpg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        # 添加其他需要支持的图片格式
    }
    info_list = []
    for i, doc_segments in enumerate(all_segments):
        text_docs = util.link_text([segment.page_content for segment in doc_segments[:len(doc_segments)-1]])
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
                        "text": doc_segments[len(doc_segments)-1].page_content
                    })
    images_list = [HumanMessage(content=info_list)]
    text = ""
    for i, doc_segments in enumerate(all_segments):
        text += util.link_text([segment.page_content for segment in doc_segments])
    
    cur_sequence = global_var.store_memory[user_name]["model_num"]
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    
    out = None
    out = cur_handler.chain_run("sma_chain", {
            "sum_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["summary"],
            "text": text, "images_store": images_list})
    
    # print(out.content)
    print("[DEBUG] Summary generation output:", out.content)
    return out.content



