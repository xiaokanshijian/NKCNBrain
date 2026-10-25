import nkcn_public_config as _public_config
import os

from langchain_community.chat_models.huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_community.llms.huggingface_hub import HuggingFaceHub
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate

os.environ.setdefault('HUGGINGFACEHUB_API_TOKEN', _public_config.secret('NKCN_CHAT_MIXTRAL_MODEL_API_KEY'))
os.environ['CURL_CA_BUNDLE'] = ''
# os.environ["http_proxy"] = "http://localhost:7890"
# os.environ["https_proxy"] = "http://localhost:7890"
# os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# import transformers
# print(transformers.__version__)

llm = HuggingFaceHub(
        # repo_id="meta-llama/Llama-2-7b-chat-hf",
        # repo_id="mistralai/Mixtral-8x7B-Instruct-v0.1",
        repo_id="HuggingFaceH4/zephyr-7b-beta",
        task="text-generation",
        huggingfacehub_api_token=_public_config.secret('NKCN_CHAT_MIXTRAL_MODEL_API_KEY'),
        model_kwargs={
            "max_new_tokens": 250,
            "top_k": 30,
            "repetition_penalty": 1.03,
        },
        # token = '[redacted]'
    )

# llm = HuggingFaceEndpoint(
#     repo_id="mistralai/Mixtral-8x7B-Instruct-v0.1",
#     task="text-generation",
#     huggingfacehub_api_token='[redacted]',
#     max_new_tokens=512,
#     do_sample=False,
#     repetition_penalty=1.03,
# )

from langchain.schema import (
    HumanMessage,
    SystemMessage,
)
from langchain_community.chat_models.huggingface import ChatHuggingFace

messages = [
    SystemMessage(content="You're a helpful assistant"),
    HumanMessage(
        content="What happens when an unstoppable force meets an immovable object?"
    ),
]

chat_model = ChatHuggingFace(llm=llm)

ai_msg = chat_model.invoke(messages)
print(ai_msg.content)

def get_model():
    return chat_model


def get_sum_msg():
    messages = [
        HumanMessagePromptTemplate.from_template(
            "{sum_prompt}\n"
            "Please complete the request in Chinese with the following text:\n\n{text}"),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
    ]
    return messages


def get_que_msg():
    messages_1 = [
        HumanMessagePromptTemplate.from_template(
            "{que_prompt}\n"
        ),
        AIMessage(content=""),  # 对AI的指明极其影响效果
        HumanMessage(content=
                     "You need to offer just right three items for user.\n"
                     "For identifying easily the output， you should follow the format like that:\n"
                     "{'output_words1','output_words2','output_words3'}\n"
                     ),
        AIMessage(content="")
    ]
    messages_2 = [HumanMessagePromptTemplate.from_template(
        "Please complete the request in Chinese with the following text:\n\n{text}")]
    return messages_1, messages_2


def get_qa_msg():
    messages = [
        HumanMessagePromptTemplate.from_template(
            "{qa_prompt}\n"
            "Please complete the following request in Chinese :\n\n{question}\n"
            "You can use following text as auxiliary information:\n\n "
            "{text}"),
        # AIMessage(content="")  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
    ]
    return messages, []


def get_topic_msg():
    messages_1 = [
        HumanMessagePromptTemplate.from_template(
            "{topic_prompt}"
        ),
        AIMessage(content=""),  # 对AI的指明极其影响效果 #这里如果最后使用chat_model，不允许最后加AI结尾
        HumanMessage(content=
                     "For identifying easily the output， you should follow the format like that:\n"
                     "{'output_words1','output_words2','output_words3'}\n"
                     "Please complete the request with the help of following examples:\n"
                     ),
        AIMessage(content="")
    ]
    messages_2 = [
        HumanMessagePromptTemplate.from_template(
            "Please complete the request in Chinese with the following text:\n\n{text}")
    ]
    return messages_1, messages_2


def unique_parse(ai_message: AIMessage):
    logo_str = "[/INST]"
    index = ai_message.content.find(logo_str)
    while index != -1:
        ai_message.content = ai_message.content[index + 7:]
        index = ai_message.content.find(logo_str)
    return ai_message
    # index =
    # ai_message.content =