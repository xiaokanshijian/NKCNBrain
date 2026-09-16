from llm_langchain import chat_gpt_model
# from llm_langchain import chat_mixtral_model
from llm_langchain import chat_llama3_model
from llm_langchain import chat_kimi_model
from llm_langchain import chat_claude_model
from llm_langchain import chat_deepseek_model
from llm_langchain import chat_dsreasoner_model
from llm_langchain import chat_gemini_model
from llm_langchain import chat_qwq_model
from typing import Iterable

all_model = [
    "chat_gpt_model",
    "chat_mixtral_model",
    "chat_llama3_model",
    "chat_kimi_model",
    "chat_claude_model",
    "chat_deepseek_model",
    "chat_dsreasoner_model"
]


def get_model_by_sequence(sequence):
    if sequence == 0:
        return chat_gpt_model
    elif sequence == 1:
        # return chat_mixtral_model
        return chat_gpt_model
    elif sequence == 2:
        return chat_llama3_model
    elif sequence == 3:
        return chat_kimi_model
    elif sequence == 4:
        return chat_claude_model
    elif sequence == 5:
        return chat_deepseek_model
    elif sequence == 6:
        return chat_dsreasoner_model
    elif sequence == 7:
        return chat_gemini_model
    elif sequence == 8:
        return chat_qwq_model


def get_chat(sequence):
    return get_model_by_sequence(sequence).get_model()
    # model_path = __import__(all_model[sequence])
    # if temperature is None:
    # return model_path.get_model()
    # return model_path.get_model(temperature)


def get_sum_msg(sequence):
    # model_path = __import__(all_model[sequence])
    # return model_path.get_sum_msg()
    return get_model_by_sequence(sequence).get_sum_msg()


def get_que_msg(sequence):
    # model_path = __import__(all_model[sequence])
    # return model_path.get_que_msg()
    return get_model_by_sequence(sequence).get_que_msg()


def get_qa_msg(sequence):
    # model_path = __import__(all_model[sequence])
    # return model_path.get_qa_msg()
    return get_model_by_sequence(sequence).get_qa_msg()


def get_topic_msg(sequence):
    # model_path = __import__(all_model[sequence])
    # return model_path.get_topic_msg()
    return get_model_by_sequence(sequence).get_topic_msg()


def unique_parse(sequence, qa_chain):
    # model_path = __import__(all_model[sequence])
    qa_chain = qa_chain | get_model_by_sequence(sequence).unique_parse
    return qa_chain

