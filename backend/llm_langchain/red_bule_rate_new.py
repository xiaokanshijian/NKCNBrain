from langchain.chains.llm import LLMChain
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate, SystemMessagePromptTemplate
from llm_langchain import get_model
from llm_langchain import util
from llm_langchain import parse_input
from llm_langchain import global_var
import re

from app_chat.core.model_manager import model_manager

def extract_number_SFT(text):
    # 使用正则表达式匹配 'xxxxx分yyyy' 中的 'xxxxx'
    match = re.search(r'(\d+(?:\.\d+)?)_', text)
    if match:
        # 从匹配结果中提取数字，并转换为浮点数
        number = float(match.group(1))
        return number
    else:
        # 如果没有匹配到，返回None
        return None


def extract_color_SFT(text):
    match = re.search(r"(\d+(?:\.\d+)?)_(\w+)_", text)
    if match:
        # 从匹配结果中提取颜色
        color = match.group(2)
        return color
    else:
        # 如果没有匹配到，返回None
        return "紫"


def extract_reason_SFT(text):
    match = re.search(r"(\d+(?:\.\d+)?)_(\w+)_([^_]+)", text)
    if match:
        # 从匹配结果中提取打分理由
        reason = match.group(3)
        return reason
    else:
        # 如果没有匹配到，返回空字符串
        return ""


def extract_number(text):
    # 使用正则表达式匹配 'xxxxx分yyyy' 中的 'xxxxx'
    match = re.search(r'(\d+(?:\.\d+)?)分_', text)
    if match:
        # 从匹配结果中提取数字，并转换为浮点数
        number = float(match.group(1))
        return number
    else:
        # 如果没有匹配到，返回None
        return None


def extract_color(text):
    match = re.search(r"(\d+(?:\.\d+)?)分_(\w+)_", text)
    if match:
        # 从匹配结果中提取颜色
        color = match.group(2)
        color = color[:-1]
        return color
    else:
        # 如果没有匹配到，返回None
        return "紫"


def extract_reason(text):
    match = re.search(r"(\d+(?:\.\d+)?)分_(\w+)_([^_]+)", text)
    if match:
        # 从匹配结果中提取打分理由
        reason = match.group(3)
        return reason
    else:
        # 如果没有匹配到，返回空字符串
        return ""


def get_rate(user_name, text):
    cur_sequence = 0 # 暂时表示GPT4o
    cur_handler = model_manager.get_model_handler_by_seq(cur_sequence)
    
    out = cur_handler.chain_run("rate_chain", {
        "rate": global_var.store_memory[user_name]["prompt"]["LUI4"]["rate"],
        "text": text
    })
    
    print("LUI4初始结果：-------------------" + out.content)
    return float(extract_number(out.content)), extract_color(out.content), extract_reason(out.content)
