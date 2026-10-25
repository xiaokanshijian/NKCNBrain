import nkcn_public_config as _public_config
import os

from langchain_community.chat_models.openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate


os.environ.setdefault("OPENAI_API_KEY", _public_config.secret('OPENAI_API_KEY'))   # openai new
OPEN_AI_KEY = _public_config.secret('OPENAI_API_KEY')

# OPEN_AI_KEY = "[redacted]"
# base_url = "http://localhost:9999/v1"

chat_model = ChatOpenAI(temperature=0,
                        openai_api_key=OPEN_AI_KEY,
                        openai_api_base=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
                        default_headers={"x-foo": "true"},
                        # openai_api_base=base_url,
                        # streaming=True,
                        model_name="gemini-2.5-pro-exp-03-25",
                        max_tokens=1000,
                        streaming=True,
                        )


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
            "不要把图片当成一个主要的部分，你应该以文本为主，当你需要的时候再从图片种提取信息。"),
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


def get_qa_msg():
    messages = [
        SystemMessagePromptTemplate.from_template(
            "Current scenario and stage hints:\n{qa_prompt}\n"
            "What you also need to notice is that the user may give you some images in the request in "
            "the form you can parse, you also need to exploit the possible images(Possible means that "
            "not have images all the time,sometimes user will not give the images)."),
        HumanMessagePromptTemplate.from_template(
            "Please complete the following request in Chinese :\n\n{question}\n"
            "Please complete the request in Chinese with the following reference text and possible images (If some "
            "images and text aren't highly relevant to the user's question, please focus on answering the query "
            "without being influenced by unrelated content):\n"),        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
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
