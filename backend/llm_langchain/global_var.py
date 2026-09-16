from llm_langchain import util

store_memory = {}

tasks = {}

unable_to_be_translated = {}

# 🔥 PDF类型缓存: {"username_bookname/filename.pdf": "scanned" | "digital" | "error"}
# 避免重复检测，提高性能
pdf_type_cache = {}

k_num = 1024

left_char_for_prompt_answer = 2000

max_token_num = [32 * k_num, 32 * k_num]

token_per_char = 2.5  # 这里先设定的大一点

chat_histroy = {}

params_init = {
    "topic": 5,
    "image": 10,
    "img_topic": 9,
    "topic_question": 5,
    "qa_question": 3,
}

# GPT4超参，此处与前端不调超参的默认值相同，gpt-4完全正常，gpt-4o则 max_tokens 不能超过 4096 否则报 completion_tokens 超限
config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "frequency_penalty": 1.0,
    "presence_penalty": 1.0,
    "max_tokens": 7192,
    "n": 1
}

# Mixtral超参
mixtralConfig = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 30,
    "max_length": 2048,
    "do_sample": True,
    "num_beams": 1,
    "num_beam_groups": 1,
    "num_return_sequences": 1,
    "repetition_penalty": 1.5,
    "max_new_tokens": 4096,
    "diversity_penalty": 1.1,
    "length_penalty": 0,
}

# kimi超参
kimiConfig = {
    "temperature": 0.7,
    "top_p": 0.95,
    "frequency_penalty": 1.0,
    "presence_penalty": 1.0,
    "max_tokens": 4096,
    "n": 1
}

# llama3超参
llama3Config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "frequency_penalty": 1.0,
    "presence_penalty": 1.0,
    "max_tokens": 4096
}

# claude超参
claudeConfig = {
    "temperature": 0.7,
    "top_p": 0.95,
    # "top_k": 30,
    "max_tokens": 7192
}

# deepseek超参
deepseekConfig = {
    "temperature": 0.7,
    "top_p": 0.95,
    "frequency_penalty": 1.0,
    "presence_penalty": 1.0,
    "max_tokens": 8192
}

# qwen超参
qwqConfig = {
    "temperature": 0.7,
    "top_p": 0.95,
    "frequency_penalty": 1.0,
    "presence_penalty": 1.0,
    "max_tokens": 4096
}

# gemini超参
geminiConfig = {
    "temperature": 0.7,
    "top_p": 0.95,
    "frequency_penalty": 1.0,
    "presence_penalty": 1.0,
    "max_tokens": 4096
}

# prompt = {
#     "sum": "You are an advanced assistant to summary the text.\n"
#            "You just need to return the summary.If you can, better use succinct words.\n"
#            "You Should first determine the topic or main content, then get the summary on "
#            "the basis of topic identified by yourself.\n"
#            "Summary the following text in Chinese with less 1000 words\n\n",
#     "que": "You are an advanced assistant to put forward some questions for the content of a given text.\n"
#            "The given text is related to the last q&a, which have a question and its answer given by yourself.\n "
#            "Here will give the q&a and the related text, you need to first determine some topics of q&a and "
#            "then get some questions on the basis of given texts.\n"
#            "You just need to return the question without any other information such as description.\n"
#            "You can not give a question such as 'what is the content of the text' but the question need"
#            "to related to specific content.\n",
#     "qa": "You are an advanced assistant to answer the question with the help of given relevant "
#           "text.\n"
#           "When user give you some texts, you may find that some of them is not relevant to the"
#           "question given by user, now you need to identify the correspondence and overlook the"
#           "not relevant.\n"
#           "May be you have had the knowledge about the question, you better answer with the text,"
#           "which is expected by user.\n"
#           "You can first determine the topic of question ,them use it as direction to give the "
#           "answer.\n "
#           "You do not need to return the topic or quote!\n",
#     "topic": "You are an advanced assistant to give key topics of given relevant "
#              "text.You better give the user 3 to 5 topics for the use by user.\n"
#              "Giving a text, if it is too short to give 3 key topic, you can put forward "
#              "some not completely related topics but can not pass the num of 3.\n"
#              "Facing a text, may be there are many topic here, you just need to get the"
#              "most important of them, do not forget you can not pass 5.\n"
# }

prompt = {
    "LUI1": {
        "summary":  "You are an advanced assistant to summary the text.\n"
           "You just need to return the summary.If you can, better use succinct words.\n"
           "You Should first determine the topic or main content, then get the summary on "
           "the basis of topic identified by yourself.\n",

        "topic": "You are an advanced assistant to give key topics of given relevant "
             "text.You better give the user 3 to 5 topics for the use by user.\n"
             "Giving a text, if it is too short to give 3 key topic, you can put forward "
             "some not completely related topics but can not pass the num of 3.\n"
             "Facing a text, may be there are many topic here, you just need to get the"
             "most important of them, do not forget you can not pass 5.\n"
    },
    "LUI2": {
        "qa": "You are an advanced assistant to answer the question with the help of given relevant "
          "text.\n"
          "When user give you some texts, you may find that some of them is not relevant to the"
          "question given by user, now you need to identify the correspondence and overlook the"
          "not relevant.\n"
          "May be you have had the knowledge about the question, you better answer with the text,"
          "which is expected by user.\n"
          "You can first determine the topic of question ,them use it as direction to give the "
          "answer.\n "
          "You do not need to return the topic or quote!\n",
        "qa_question": "You are an advanced assistant to put forward some questions for the content of a given text.\n"
            "The given text is related to the last q&a, which have a question and its answer given by yourself.\n "
           "Here will give the q&a and the related text, you need to first determine some topics of q&a and "
           "then get some questions on the basis of given texts.\n"
           "You just need to return the question without any other information such as description.\n"
           "You can not give a question such as 'what is the content of the text' but the question need"
           "to related to specific content.\n"
            "Notice that you should generate 3 questions",
        "img_topic": "请从以上文本提取关键词，不超过9个：",
        "topic_question": "请结合文本背景，提出关键词相关的问题，不超过5个："
    },
    "LUI3": {
        "multi_summarize": "You are an expert in analyzing articles and learning, and you can perform a series of operations "
            "on the given text according to the requirements. Please summarize one or more paragraphs of the following text in Chinese :\n",
        "multi_suggestions": "You are an expert in analyzing articles and learning, and you can perform a series of operations on the given "
          "text according to the requirements. Please provide suggestions in Chinese for one or more paragraphs of the following text :\n",
        "multi_study_guide": "You are an expert in analyzing articles and learning, and you can perform a series of operations on the given "
            "text according to the requirements. Please create a study guide in Chinese for one or more paragraphs of the following text :\n",
        "single_understand": "You are an expert in analyzing articles and learning, and you can perform a series of operations on the given "
            "text according to the requirements. Please help me understand the content in Chinese for one or more paragraphs of the following text :",
        "single_critique": "You are an expert in analyzing articles and learning, and you can perform a series of operations on the given text "
            "according to the requirements. Please critique one or more paragraphs of the following text in Chinese :\n",
        "single_outline": "You are an expert in analyzing articles and learning, and you can perform a series of operations on the given text"
            " according to the requirements. Please provide outline in Chinese for one or more paragraphs of the following text :",
        "user_define": "Do something you want."
    },
    "LUI4": {
        "rate": "你需要对给出的文本进行红蓝融合度评估打分，红蓝融合度打分规则如下:\n"
            "1.红蓝融合理念由浅到深、由表面到内在共分为5层，对应1-5分，1分最低、5分最高，如果该文本能体现红蓝融合理念、得高分，否则得低分，\n"
            "若文本内容红蓝融合理念深度能达到第1层，得1分；能达到第3层，得3分；介于两层之间，得小数分值；另外，文本内容与红蓝融合无关则得低分\n"
            "请注意：当你想要打高分时，如高于3分，需要慎重考虑！\n"
            "2.红蓝融合理念如下：第一层：文化和科技的融合；\n"
            "第二层：知行合一的融合；\n第三层：自上而下贯彻带领+自下而上创造示范的融合；\n"
            "第四层：先进组织认知中目标和任务的有机结合；\n 第五层：高维思想堤坝和基层落实洪流的融合\n3.注意，你只需要输出分值！\n"
            "示例如下：文本：传统文化和新兴科技是可以有机结合的，传统文化要延续继承，信息时代的科技也要利用来为文化赋能\n1分\n文本："
            "传统文化和科技是对立的，它们可能难以相融，因为守旧派和维新派始终存在矛盾\n0.5分\n"
            "文本：思维变思想，思想变思路，思路变行动，行动变举措，举措变成效\n2分\n"
            "文本：“又红又专” 是毛泽东同志1957年在中共八届三中全会上鲜明提出了“又红又专”的思想。他说：“政治和业务是对立统一"
            "的，政治是主要的，是第一位的，一定要反对不问政治的倾向；但专搞政治，不懂技术，不懂业务，也不行。我们的同志"
            "，无论搞工业的，搞农业的，搞商业的，搞文教的，都要学一点技术和业务。各行各业的干部都要努力精通技术和业务，使自己"
            "成为内行，‘又红又专’。”\n3.4分\n"
            "文本：习近平：守正创新，必须坚持人民至上，必须坚持自信自立，必须坚持守正创新，必须坚持问题导向，必须坚持系统观念，"
            "必须坚持胸怀天下\n4.2分\n",
    },
}

def init_store_memory():
    global store_memory
    store_memory = {}


def set_task_current_page(task_id, current_page):
    global tasks
    if task_id not in tasks:
        tasks[task_id] = {}
    tasks[task_id]["current_page"] = current_page


def set_task_total_pages(task_id, total_pages):
    global tasks
    if task_id not in tasks:
        tasks[task_id] = {}
    tasks[task_id]["total_pages"] = total_pages


def set_task_current_item(task_id, current_item):
    global tasks
    if task_id not in tasks:
        tasks[task_id] = {}
    tasks[task_id]["current_item"] = current_item


def set_task_total_items(task_id, total_items):
    global tasks
    if task_id not in tasks:
        tasks[task_id] = {}
    tasks[task_id]["total_items"] = total_items


def set_user_split(user_name, doc_name, docs):
    global store_memory
    if user_name not in store_memory:
        store_memory[user_name] = {}
    if "split_docs" not in store_memory[user_name]:
        store_memory[user_name]["split_docs"] = {}
    store_memory[user_name]["split_docs"][doc_name] = docs



def set_user_prompt(user_name, prompt_all=None):
    if user_name not in store_memory:
        store_memory[user_name] = {}
    if "prompt" not in store_memory[user_name]:
        store_memory[user_name]["prompt"] = {}
    # for key in prompt:
    #     if prompt_all is None:
    #         store_memory[user_name]["prompt"][key] = prompt[key]
    #     else:
    #         store_memory[user_name]["prompt"][key] = prompt_all[key]
    if prompt_all is None:
        store_memory[user_name]["prompt"] = prompt   # 默认
    else:
        store_memory[user_name]["prompt"] = prompt_all


def set_user_image(user_name, doc_name, docs):
    global store_memory
    if user_name not in store_memory:
        store_memory[user_name] = {}
    if "images" not in store_memory[user_name]:
        store_memory[user_name]["images"] = {}
    store_memory[user_name]["images"][doc_name] = docs


def set_user_vector(user_name, vector_store):
    global store_memory
    if user_name not in store_memory:
        store_memory[user_name] = {}
    store_memory[user_name]["vector_store"] = vector_store


def save_config(modelID, **kwargs):
    global config, mixtralConfig, kimiConfig, llama3Config, claudeConfig, deepseekConfig
    if modelID == '1002':
        for key in config:
            config[key] = kwargs[key]
    if modelID == '1003':
        for key in mixtralConfig:
            mixtralConfig[key] = kwargs[key]
        mixtralConfig['do_sample'] = kwargs['do_sample'] == 1
    if modelID == '1004':
        for key in kimiConfig:
            kimiConfig[key] = kwargs[key]
    if modelID == '1005':
        for key in llama3Config:
            llama3Config[key] = kwargs[key]
    if modelID == '1006':
        for key in claudeConfig:
            claudeConfig[key] = kwargs[key]
    if modelID == '1007':
        for key in deepseekConfig:
            deepseekConfig[key] = kwargs[key]
    if modelID == '1008':
        for key in deepseekConfig:
            deepseekConfig[key] = kwargs[key]
    if modelID == '1009':
        for key in geminiConfig:
            geminiConfig[key] = kwargs[key]
    if modelID == '1010':
        for key in qwqConfig:
            qwqConfig[key] = kwargs[key]


def set_user_model(user_name, model_num):
    global store_memory
    if user_name not in store_memory:
        store_memory[user_name] = {}
    store_memory[user_name]["model_num"] = model_num


def set_user_params(user_name, params=None):
    global store_memory
    if user_name not in store_memory:
        store_memory[user_name] = {}
    if params is None:
        store_memory[user_name]["params"] = params_init
    else:
        store_memory[user_name]["params"] = params


def add_split_file(user_name, file_name):
    global store_memory
    if user_name not in store_memory:
        store_memory[user_name] = {}
    if "split_file" not in store_memory[user_name]:
        store_memory[user_name]["split_file"] = []

    store_memory[user_name]["split_file"].append(file_name)


def set_split_file(user_name):
    global store_memory
    if user_name not in store_memory:
        store_memory[user_name] = {}
    store_memory[user_name]["split_file"] = []


def get_user_split(user_name, doc_name):
    """获取用户的分割文档"""
    global store_memory
    if user_name not in store_memory:
        return None
    if "split_docs" not in store_memory[user_name]:
        return None
    return store_memory[user_name]["split_docs"].get(doc_name)


def get_user_image(user_name, doc_name):
    """获取用户的图片数据"""
    global store_memory
    if user_name not in store_memory:
        return None
    if "images" not in store_memory[user_name]:
        return None
    return store_memory[user_name]["images"].get(doc_name)


def get_user_vector(user_name):
    """获取用户的向量存储"""
    global store_memory
    if user_name not in store_memory:
        return None
    return store_memory[user_name].get("vector_store")


# 🔥 PDF类型缓存相关函数
def get_pdf_type(file_key):
    """从缓存获取PDF类型

    参数:
        file_key: 文件键，格式为 "username/bookname/filename.pdf"

    返回:
        PDF类型: 'scanned' | 'digital' | 'error' | None(未缓存)
    """
    global pdf_type_cache
    return pdf_type_cache.get(file_key)


def set_pdf_type(file_key, pdf_type):
    """设置PDF类型到缓存

    参数:
        file_key: 文件键，格式为 "username/bookname/filename.pdf"
        pdf_type: PDF类型 'scanned' | 'digital' | 'error'
    """
    global pdf_type_cache
    pdf_type_cache[file_key] = pdf_type
    print(f"[PDF缓存] 已缓存: {file_key} -> {pdf_type}")


def clear_pdf_type_cache():
    """清空PDF类型缓存"""
    global pdf_type_cache
    pdf_type_cache.clear()
    print("[PDF缓存] 已清空所有缓存")
