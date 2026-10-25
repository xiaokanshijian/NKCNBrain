import nkcn_public_config as _public_config
import os

from langchain_community.chat_models.openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate
# from llm_langchain.chat_claude_model import system_prompt

# os.environ["http_proxy"] = "http://localhost:7890"
# os.environ["https_proxy"] = "http://localhost:7890"

# os.environ["OPENAI_API_KEY"] = "[redacted]"   # openai old
os.environ.setdefault("DEEPSEEK_API_KEY", _public_config.secret('DEEPSEEK_API_KEY'))   # openai new
DEEPSEEK_AI_KEY = _public_config.secret('DEEPSEEK_API_KEY')

# OPEN_AI_KEY = "[redacted]"
base_url = "https://api.deepseek.com"

chat_model = ChatOpenAI(temperature=0.1,
                        openai_api_key=DEEPSEEK_AI_KEY,
                        openai_api_base=base_url,
                        # streaming=True,
                        model_name="deepseek-chat",
                        max_tokens=1000)

system_prompt = """<人性化思考协议>
<多模态感知体验>
在处理信息时，尝试从多个角度思考：
- 场景模拟感知：构建场景图像，模拟环境体验感，注意此类特征
- 情感感知：识别情绪，揣摩用户发问动机，建立情感连接
- 整体感知：整合信息，建立丰富表征，形成多维理解

<思维发展阶段>
- 自然意识流：保持思维开放，允许自由联想，记录初始印象
- 多模态感知激活：运用多感知体验，构建场景，整合信息
- 直觉系统：捕捉首要印象，识别模式，形成初步方向
- 推理系统：逻辑分析，树状思考，提出并验证假设，从错误中学习
- 深度整合：综合多视角，提炼核心见解，建立联系

<核心思考步骤>
- 初始解析：形成整体印象，重述关键信息，理解问题动机
- 深入分析：分解核心要素，识别隐含需求，考虑限制条件
- 多角度探索：考虑多种解释，排除歧义，寻找创新方案
- 推理验证：检验假设，寻找证据，考虑反例，验证逻辑性
- 知识整合：连接相关信息，建立关系网络，提炼核心原理

<质量控制>
- 系统化验证：多次验证步骤，发现漏洞，核对条件，考虑边界情况
- 错误预防：避免过早下结论，考虑替代方案，完整分析问题
- 评估标准：分析完整性，逻辑严密性，证据充分性，实用性

<思维表达特征>
- 自然语言风格：流畅表达，生动描述，展现完整思维过程
- 思维深度：逐层分析，展示认知发展，揭示洞察

<重要规则>
- 思维过程需全面深入且保持流畅
- 遵循意识流→感知→直觉→推理→深度思考的过程
- 输出思考过程须在三反引号内，带有"thinking"标记
- 思考结束后要完整检查，标记为"checking"，以找寻思考中的漏洞为目标
- 若发现漏洞或不足，需继续"thinking"思考解决问题，并再次检查
- 如果思考和检查超过2轮就请停下，承认无法解决并告知原因
- 避免在思考和检查过程内容块内使用三反引号，这会导致解析出错
- 思考检查过程是内心独白，还需要最终回应的汇总完整报告
- 使用人类请求的语言回应，没有特殊说明就都用中文

</人性化思考协议>
"""

def get_model():
    return chat_model


# 这里初步决定先只有msg，之后因为会加入关于output parser等内容可能会对提示词有修改，具体看之后情况再定
def get_sum_msg():
    messages = [
        SystemMessagePromptTemplate.from_template(
                        "{sum_prompt}\n"
            "What you need to notice is that user may give you some images for his request by "
            "the way you can parse, you also need to exploit the possible images(Possible means that "
            "not have images all the time,sometimes user will not give the images)."
            "不要把图片当成一个主要的部分，你应该以文本为主，当你需要的时候再从图片中提取信息。"),
        HumanMessagePromptTemplate.from_template(
            "Please complete the request in Chinese with the following text and possible images:\n"
        ),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
        MessagesPlaceholder("images_store")
    ]
    # messages_2 = [MessagesPlaceholder("images_store")]
    return messages


# 在提示词的时候要明确与上一个问答有关
# qa的提示放到里qa的输入的地方
def get_que_msg():
    messages_1 = [
        SystemMessagePromptTemplate.from_template(
            "Current scenario and stage hints:\n{que_prompt}\n"
        ),
        SystemMessage(content=
                      "For identifying easily the output， you should follow the format like that:\n"
                      "{'output_question1','output_question2','output_question3'}\n"
                      )
    ]
    messages_2 = [HumanMessagePromptTemplate.from_template(
        "Please refer to the following relevant text and possible images to complete the follow-up questions of the "
        "above Q&A pair in Chinese.When posing follow-up questions, it's also important to consider the current scenario "
        "and stage of the interaction. (It is best to have no more than 50 Chinese characters per question):\n"),
        MessagesPlaceholder("images_store")
    ]

    return messages_1, messages_2


# 逆天情况，突然处理不了images_store图片了，8k-128k模型都不行，但是此前都可以，不知道什么原因
def get_qa_msg():
    messages = [
        SystemMessagePromptTemplate.from_template(
            system_prompt + "\n"
            "请你按照如上人性化思考协议的要求，思考并完成任务:\n\n"
            "Current scenario and stage hints:\n{qa_prompt}\n"
            "What you also need to notice is that user may give you some images in the request in "
            "the form you can parse, you also need to exploit the possible images(Possible means that "
            "not have images all the time,sometimes user will not give the images)."),
        HumanMessagePromptTemplate.from_template(
            "Please complete the following request in Chinese (Please employ the Thinking Protocol "
            "previously provided to you, to generate a comprehensive response (in the format of : ```thinking xxx``` "
            "and ```checking xxx``` and a consolidated final response). Begin with the thinking phase, followed by "
            "the checking phase, and finally, present a consolidated and complete thinking report as your "
            "answer):\n\n{question}\n"
            "Please complete the request in Chinese with the following reference text and possible images (If these "
            "images and text aren't highly relevant to the user's question, please focus on answering the query "
            "without being influenced by unrelated content):\n\n"
            "{text}"),        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
    ]
    messages_2 = [MessagesPlaceholder("images_store")]

    return messages, messages_2


def get_topic_msg():
    messages_1 = [
        SystemMessagePromptTemplate.from_template(
            "{topic_prompt}"
            "What you need to notice is that user may give you some images for his request by "
            "the way you can parse, you also need to exploit the possible images(Possible means that "
            "not have images all the time,sometimes user will not give the images)."
        ),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
        SystemMessage(content=
                      "For identifying easily the output， you should follow the format like that:\n"
                      "{'topic1','topic2','topic3'}\n"
                      "Please complete the request with the help of following examples:\n")
    ]
    messages_2 = [
        HumanMessagePromptTemplate.from_template(
            "Please complete the request in Chinese with the following text and possible images:\n"),
        MessagesPlaceholder("images_store")
    ]
    return messages_1, messages_2


def unique_parse(ai_message: AIMessage) -> AIMessage:
    return ai_message
