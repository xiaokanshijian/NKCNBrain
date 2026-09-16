from langchain.chains.llm import LLMChain
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate
from llm_langchain import get_model
from llm_langchain import util, global_var
from llm_langchain import parse_input
# 在使用前需要先对sma_chain进行初始化
card_chain = []


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
    messages = [
        HumanMessagePromptTemplate.from_template(
            "{text}"),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
    ]
    chat_template = ChatPromptTemplate.from_messages(messages)
    # 重整chat得到prompt
    # chat_val = chat_template.invoke({"text": "{text}"})
    # prompt_template = PromptTemplate.from_template(chat_val.to_string())
    global card_chain
    card_chain.append(chat_template | chat_model)
    card_chain[sequence] = get_model.unique_parse(sequence, card_chain[sequence])


def get_card_texts(texts, user_name):
    out = None
    text = util.link_text(texts)
    global card_chain
    if global_var.store_memory[user_name]["model_num"] == 0:
        out = util.chain_run(card_chain[global_var.store_memory[user_name]["model_num"]], {"text": text})
    if global_var.store_memory[user_name]["model_num"] == 1:
        out = util.chain_run_mixtral(card_chain[global_var.store_memory[user_name]["model_num"]], {"text": text})
    if global_var.store_memory[user_name]["model_num"] == 2:
        out = util.chain_run_llama3(card_chain[global_var.store_memory[user_name]["model_num"]], {"text": text})
    if global_var.store_memory[user_name]["model_num"] == 3:
        out = util.chain_run_kimi(card_chain[global_var.store_memory[user_name]["model_num"]], {"text": text})
    if global_var.store_memory[user_name]["model_num"] == 4:
        out = util.chain_run_claude(card_chain[global_var.store_memory[user_name]["model_num"]], {"text": text})
    if global_var.store_memory[user_name]["model_num"] == 5:
        out = util.chain_run_deepseek(card_chain[global_var.store_memory[user_name]["model_num"]], {"text": text})
    if global_var.store_memory[user_name]["model_num"] == 6:
        out = util.chain_run_dsreasoner(card_chain[global_var.store_memory[user_name]["model_num"]], {"text": text})
    if global_var.store_memory[user_name]["model_num"] == 7:
        out = util.chain_run_Gemini(card_chain[global_var.store_memory[user_name]["model_num"]], {"text": text})
    if global_var.store_memory[user_name]["model_num"] == 8:
        out = util.chain_run_Qwq(card_chain[global_var.store_memory[user_name]["model_num"]], {"text": text})
    # out = sma_chain.invoke({"text": text})
    print(out.content)
    return out.content


