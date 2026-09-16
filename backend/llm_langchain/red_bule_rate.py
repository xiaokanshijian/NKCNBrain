from langchain.chains.llm import LLMChain
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, PromptTemplate, SystemMessagePromptTemplate
from llm_langchain import get_model
from llm_langchain import util
from llm_langchain import parse_input
from llm_langchain import global_var
import re
# 在使用前需要先对sma_chain进行初始化
rate_chain = None
rate_chain_next = None  # 添加备用链


# 这里是对summary的链条进行初始化，现在只是一个极其简单的链条，甚至没有对输出的处理，只有在加入对输出的处理之后才能得到格式化的文本
# 这里也没有使用到关于ReAct，Agent等技术方法，有待之后看需要增加
def init_rate():
    chat_model = get_model.get_chat(4)
    """
    messages = [
        SystemMessage(content="You are an advanced assistant to summary the text."),
        HumanMessagePromptTemplate.from_template(
            "Summary the following text in Chinese with less 100 words:\n\n {text}"),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
    ]
    """
    # messages = get_model.get_sum_msg(sequence)
    # 下面的 HumanMessagePromptTemplate 里格式只有理由没有改进建议，可能会有问题，但暂时没有，所以先不改，之后如果返回的没有改进建议，就把这里加上
    messages = [
        SystemMessagePromptTemplate.from_template(
            "{rate}"
        ),
        HumanMessagePromptTemplate.from_template(
            "请针对以下文本完成上述任务，记得上面的输出格式要求，涉及“红蓝融合第n层”要在后面括号具体描述，例如'1.5分_紫色_达到红蓝融合第一层（人文+科技）但"
            "不到第二层（认知+行动），建议增加实践方法'，文本如下：{text}"
        )
    ]
    chat_template = ChatPromptTemplate.from_messages(messages)
    # 重整chat得到prompt
    # chat_val = chat_template.invoke({"text": "{text}"})
    # prompt_template = PromptTemplate.from_template(chat_val.to_string())
    global rate_chain
    rate_chain = chat_template | chat_model
    rate_chain = get_model.unique_parse(4, rate_chain)


# 初始化备用链
def init_rate_next():
    chat_model = get_model.get_chat(0)
    messages = [
        SystemMessagePromptTemplate.from_template(
            "{rate}"
        ),
        HumanMessagePromptTemplate.from_template(
            "请针对以下文本完成上述任务，记得上面的输出格式要求，涉及“红蓝融合第n层”要在后面括号具体描述，例如'1.5分_紫色_达到红蓝融合第一层（人文+科技）但"
            "不到第二层（认知+行动），建议增加实践方法'，文本如下：{text}"
        )
    ]
    chat_template = ChatPromptTemplate.from_messages(messages)
    global rate_chain_next
    rate_chain_next = chat_template | chat_model
    rate_chain_next = get_model.unique_parse(0, rate_chain_next)


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


def is_valid_format(text):
    """检查文本是否符合预期格式：数字分_颜色_理由"""
    if not text:
        return False

    # 检查是否包含基本的格式元素
    pattern = r'(\d+(?:\.\d+)?)分_(\w+)_(.+)'
    match = re.search(pattern, text)
    return match is not None


# def get_rate(user_name, text):
#     out = util.chain_run(rate_chain, {
#         "rate": global_var.store_memory[user_name]["prompt"]["LUI4"]["rate"],
#         "text": text
#     })
#     print("LUI4初始结果：-------------------" + out.content)
#     return float(extract_number(out.content)), extract_color(out.content), extract_reason(out.content)


def get_rate(user_name, text):
    params = {
        "rate": global_var.store_memory[user_name]["prompt"]["LUI4"]["rate"],
        "text": text
    }

    # 尝试主链
    try:
        out = util.chain_run_claude(rate_chain, params)
        if hasattr(out, 'content') and is_valid_format(out.content):
            print("LUI4初始结果：-------------------" + out.content)
            return float(extract_number(out.content)), extract_color(out.content), extract_reason(out.content)
        else:
            print(f"主链格式错误，切换备用链：{getattr(out, 'content', 'No content')}")
    except Exception as e:
        print(f"主链出错，切换备用链：{e}")

    # 备用链
    try:
        out = util.chain_run(rate_chain_next, params)
        if hasattr(out, 'content') and is_valid_format(out.content):
            print("LUI4备用结果：-------------------" + out.content)
            return float(extract_number(out.content)), extract_color(out.content), extract_reason(out.content)
    except Exception as e:
        print(f"备用链也出错：{e}")

    # 都失败了，返回默认值
    return 2.5, "紫", "系统错误，未成功获取评分"