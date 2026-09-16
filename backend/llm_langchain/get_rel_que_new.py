import random
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, MessagesPlaceholder

from llm_langchain import chat_gpt_model
from llm_langchain import util
from llm_langchain import get_model
from llm_langchain import parse_input
from llm_langchain import global_var


from app_chat import gpt4_api
from app_chat.core.model_manager import model_manager



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
            
    
    
    chat_history = [HumanMessage(content="This is the last q&a:\n\n"+question), AIMessage(content=answer)]
    
    out = None
    cur_sequence = global_var.store_memory[user_name]["model_num"]
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    out = cur_handler.chain_run("que_chain", 
                          {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"],
                          "text": text, "chat_history": chat_history, "images_store": images_list})
    

    print('[DEBUG] que: ',out)
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
def get_rel_que_user_doc_way_split(user_name, docs_name, get_way, question, answer):
    try:
        if not docs_name:
            out_list = gpt4_api.get_question_split(question, answer, user_name)
            if global_var.store_memory[user_name]["params"]["qa_question"] < len(out_list):
                out_list = out_list[:global_var.store_memory[user_name]["params"]["qa_question"]]
            return out_list
        else:
            segments = util.get_docs_all_split(user_name, docs_name, get_way, question + answer)
            images, seqs, exts, sources, pages = util.parse_image_in_segment_split(user_name, segments)
            out_list = get_question_split(question, answer, user_name, segments, images, seqs, exts)
            if global_var.store_memory[user_name]["params"]["qa_question"] < len(out_list):
                out_list = out_list[:global_var.store_memory[user_name]["params"]["qa_question"]]
            return out_list
    except Exception as e:
        print("追问出错：" + str(e))
        default_list = ['其中还有哪些更深刻的思维转换理解问题？', '这些内容包含的重要核心内容是什么？', '这些文字内容来源的撰写意图最可能是什么？']
        return default_list


def get_question_split(question, answer, user_name, all_segments, all_images, all_seqs, all_exts):
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
    
    
    chat_history = [HumanMessage(content="This is the last Q&A:\n\n" + question), AIMessage(content=answer)]
    out = None
    
    cur_sequence = global_var.store_memory[user_name]["model_num"]
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    
    out = cur_handler.chain_run("que_chain", 
                             {"que_prompt": global_var.store_memory[user_name]["prompt"]["LUI2"]["qa_question"],
                              "text": text, "chat_history": chat_history, "images_store": images_list})
    
    print('[DEBUG] que: ',out)
    return out
