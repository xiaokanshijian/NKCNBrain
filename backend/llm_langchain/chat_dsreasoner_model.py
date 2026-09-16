import os
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate
from langchain_community.chat_models.openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate
from langchain_experimental.llms import ChatLlamaAPI
from openai import AsyncOpenAI, OpenAI

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_KEY_ALI= os.environ.get("DASHSCOPE_API_KEY", "")
DEEPSEEK_ENGINE = "deepseek-r1" #"deepseek-reasoner"  # DeepSeek模型名称

class DEEPSEEK_CONFIG:
    def __init__(
            self,
            engine=DEEPSEEK_ENGINE,
            max_tokens=1000,
            temperature=0.1,
            top_p=0.5,
            frequency_penalty=0,
            presence_penalty=2,
            stop_sequences=["\n\n", "\n16", "16.", "16 ."],
            logprobs=1,
            n=1,
            best_of=1,
            api_key=DEEPSEEK_API_KEY_ALI,
            retries=3,
            ):
        self.engine = engine
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.stop_sequences = stop_sequences if stop_sequences is not None else []
        self.logprobs = logprobs
        self.n = n
        self.best_of = best_of
        self.api_key = api_key
        self.retries = retries


class DEEPSEEK:
    def __init__(self, config: DEEPSEEK_CONFIG):
        self.config = config

    def make_requests(self, messages):
        client = ChatOpenAI(
            temperature=self.config.temperature,
            openai_api_key=self.config.api_key,
            openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1", # "https://api.deepseek.com",
            model_name=self.config.engine,
            max_tokens=self.config.max_tokens
        )

        response = client(messages)
        return response

    def stream_messages(self, messages):
        client = OpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", # "https://api.deepseek.com",
            api_key=self.config.api_key,
        )

        response = client.chat.completions.create(
            model=self.config.engine,
            messages=messages,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens = self.config.max_tokens,
            stream=True, # FIXME yq: 现在暂时默认都开启流式输出
        )

        for chunk in response:
            yield chunk

    async def astream_messages(self, messages):
        # print(f"Calling LLAMA3 API with config: {self.config.__dict__}")
        client = AsyncOpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=self.config.api_key,
        )

        response = await client.chat.completions.create(
            model=self.config.engine,
            messages=messages,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens = self.config.max_tokens,
            stream=True, # FIXME yq: 现在暂时默认都开启流式输出
        )

        async for chunk in response:
            yield chunk


deepseek_config = DEEPSEEK_CONFIG()
deepseek = DEEPSEEK(deepseek_config)
chat_model = ChatLlamaAPI(client=deepseek)


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
            "Current scenario and stage hints:\n{qa_prompt}\n"
            "What you also need to notice is that user may give you some images in the request in "
            "the form you can parse, you also need to exploit the possible images(Possible means that "
            "not have images all the time,sometimes user will not give the images)."),
        HumanMessagePromptTemplate.from_template(
            "Please complete the following request in Chinese :\n\n{question}\n"
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


# def unique_parse(ai_message):
#     print(f"Dsreasoner type(ai_message): {type(ai_message)}")
#     print(f"Dsreasoner ai_message: {ai_message}")
#     ai_message.content = "```" + ai_message.reasoning_content + "```" + ai_message.content
#     return ai_message

def unique_parse(ai_message: AIMessage) -> AIMessage:
    return ai_message
