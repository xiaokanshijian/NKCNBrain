from llm_langchain import get_suma, parse_input
from llm_langchain import get_rel_que
from llm_langchain import normal_qa
from llm_langchain import red_bule_rate
from llm_langchain import get_topic
from llm_langchain import get_crad_text
from llm_langchain import global_var


def init():
    # 01234567是什么在get_model.py中自定义，初始化所有model的各种chain，以便于后续xx_chain[global_var.store_memory[user_name]["model_num"]]直接切换调用
    for i in range(9):
        get_suma.init_suma(i)
        get_rel_que.init_que(i)
        normal_qa.init_qa(i)
        get_topic.init_topic(i)
        red_bule_rate.init_rate()
        red_bule_rate.init_rate_next()
        get_crad_text.init_suma(i)


def switch(user_name, sequence):
    parse_input.set_user_model(user_name, sequence)
