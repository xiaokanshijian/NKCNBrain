import nkcn_public_config as _public_config
import os
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import HumanMessagePromptTemplate
# from llamaapi import LlamaAPI
from langchain_experimental.llms import ChatLlamaAPI
from openai import AsyncOpenAI, OpenAI


NVIDIA_API_KEY = _public_config.secret('NVIDIA_API_KEY')
LLAMA3_ENGINE = "meta/llama-3.1-405b-instruct"   # llama3上下文只有8192，而llama3.1有128k
class LLAMA3_CONFIG:
    def __init__(
            self,
            engine=LLAMA3_ENGINE,
            max_tokens=1024,
            temperature=0.7,
            top_p=0.5,
            frequency_penalty=0,
            presence_penalty=2,
            stop_sequences=["\n\n", "\n16", "16.", "16 ."],
            logprobs=1,
            n=1,
            best_of=1,
            api_key=NVIDIA_API_KEY,
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


class LLAMA3:
    def __init__(self, config: LLAMA3_CONFIG):
        self.config = config

    def make_requests(self, messages):
        # print(f"Calling LLAMA3 API with config: {self.config.__dict__}")
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.config.api_key,
        )

        response = client.chat.completions.create(
            model=self.config.engine,
            messages=messages,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens = self.config.max_tokens
        )
        return response


    def stream_messages(self, messages):
        # print(f"Calling LLAMA3 API with config: {self.config.__dict__}")
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
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
            base_url="https://integrate.api.nvidia.com/v1",
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


llama3_config = LLAMA3_CONFIG()
llama = LLAMA3(llama3_config)
chat_model = ChatLlamaAPI(client=llama)

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
            "Current scenario and stage hints:\n{que_prompt}\n"
        ),
        AIMessage(content=""),  # 对AI的指明极其影响效果
        HumanMessage(content=
                     "You need to offer just right three items for user.\n"
                     "For identifying easily the output， you should follow the format like that:\n"
                     "{'output_question1','output_question2','output_question3'}\n"
                     ),
        AIMessage(content="")
    ]
    messages_2 = [HumanMessagePromptTemplate.from_template(
        "Please complete the follow-up questions of the above Q&A pair in Chinese with the following related "
        "text.When posing follow-up questions, it's also important to consider the current scenario and stage "
        "of the interaction. (It is best to have no more than 50 Chinese characters per question):\n\n{text}")]
    return messages_1, messages_2


def get_qa_msg():
    messages = [
        HumanMessagePromptTemplate.from_template(
            "Current scenario and stage hints:\n{qa_prompt}\n"
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

def unique_parse(ai_message: AIMessage) -> AIMessage:
    return ai_message

    # index =
    # ai_message.content =
