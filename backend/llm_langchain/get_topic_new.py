from langchain.chains.llm import LLMChain
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate, \
    FewShotChatMessagePromptTemplate
from llm_langchain import get_model, global_var
from llm_langchain import util
from llm_langchain import parse_input

from app_chat.core.model_manager import model_manager


def get_topic(user_name, text, images, seqs):
    images_list = []
    count = 0
    
    cur_sequence = global_var.store_memory[user_name]["model_num"]

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
    
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    out = cur_handler.chain_run("topic_chain", {
               "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
                "text": text, "images_store": images_list})

    print('[DEBUG] topic:', out)
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
def get_topic_user_docs_way_split(user_name, docs_name, get_way):
    segments = util.get_docs_all_split(user_name, docs_name, get_way)
    images, seqs, exts, sources, pages = util.parse_image_in_segment_split(user_name, segments)
    print(segments)
    out_list = get_topic_split(user_name, segments, images, seqs, exts)
    if global_var.store_memory[user_name]["params"]["topic"] < len(out_list):
        out_list = out_list[:global_var.store_memory[user_name]["params"]["topic"]]
    return out_list


def get_topic_split(user_name, all_segments, all_images, all_seqs, all_exts):
    mime_types = {
        'jpg': 'image/jpg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        # 添加其他需要支持的图片格式
    }
    info_list = []
    for i, doc_segments in enumerate(all_segments):
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
    text = ""
    for i, doc_segments in enumerate(all_segments):
        text += util.link_text([segment.page_content for segment in doc_segments])

    cur_sequence = global_var.store_memory[user_name]["model_num"]
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    out = cur_handler.chain_run("topic_chain", {
               "topic_prompt": global_var.store_memory[user_name]["prompt"]["LUI1"]["topic"],
                "text": text, "images_store": images_list})

    print('[DEBUG] topic:', out)
    return out
