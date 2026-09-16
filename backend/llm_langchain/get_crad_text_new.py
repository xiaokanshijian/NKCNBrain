from langchain.chains.llm import LLMChain
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate
from llm_langchain import get_model
from llm_langchain import util, global_var
from llm_langchain import parse_input

from app_chat.core.model_manager import model_manager


def get_card_texts(texts, user_name):
    out = None
    text = util.link_text(texts)
    
    cur_sequence = global_var.store_memory[user_name]["model_num"]
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    
    out = cur_handler.chain_run("card_chain", {"text": text})
    
    print("[DEBUG] card_out: ", out.content)
    return out.content


