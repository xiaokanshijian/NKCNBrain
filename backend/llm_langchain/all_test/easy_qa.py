# 这里得到的模型是一个在运行期间不关闭的model
# 必须先获取，再使用
# 对于如何使用llama2获取chat_model目前还没有方式，所以这里先使用llms的llama2做示范
# 对于chat_model的示范将在之后获得api之后进行重构
# 为了对之后的chat_model的使用做示范，这里所有的提示词的构成都由chat的方式构成再转换为prompt
# 这里先使用简单的问答形式，不涉及agent与role playing，
# 对于它们的使用需要在之后进行可能的补充
# 以上
import random

import torch
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceInstructEmbeddings

from langchain import HuggingFacePipeline
from langchain import PromptTemplate, LLMChain
from transformers import AutoModelForCausalLM, AutoTokenizer
from langchain.document_loaders import PyPDFLoader
from transformers import pipeline
import json
import textwrap
from langchain.schema import (
    HumanMessage,
    SystemMessage,
    AIMessage
)
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

# model先使用llama2


llm = None
sma_chain = None
que_chain = None
max_token = 2048


# 实现对需要的全局变量的初始化
def init_all():
    get_model()
    get_sma_chain()
    get_que_chain()


def get_que_chain():
    messages = [
        SystemMessage(content="You are an advanced assistant to put forward a question for a given text."),
        HumanMessagePromptTemplate.from_template(
            "Please put forward a question about the given text:\n\n {text}"),
        AIMessage(content="")  # 对AI的指明极其影响效果
    ]
    chat_template = ChatPromptTemplate.from_messages(messages)
    # 重整chat得到prompt
    chatval = chat_template.invoke({"text": "{text}"})
    prompt_template = PromptTemplate.from_template(chatval.to_string())

    global que_chain
    que_chain = LLMChain(prompt=prompt_template, llm=llm)


def get_sma_chain():
    messages = [
        SystemMessage(content="You are an advanced assistant to summary the text."),
        HumanMessagePromptTemplate.from_template("Summary the following text in English with less 100 words:\n\n {text}"),
        AIMessage(content="") # 对AI的指明极其影响效果
    ]
    chat_template = ChatPromptTemplate.from_messages(messages)
    # 重整chat得到prompt
    chatval = chat_template.invoke({"text": "{text}"})
    prompt_template = PromptTemplate.from_template(chatval.to_string())

    global sma_chain
    sma_chain = LLMChain(prompt=prompt_template, llm=llm)


def get_model():
    model_path = "../Llama-2-7b-chat-hf"
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        load_in_4bit=True,
        torch_dtype=torch.float16,
        device_map='auto'
    )
    tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=False)
    pipe = pipeline(
        "text-generation",
        model=model,
        torch_dtype=torch.bfloat16,
        device_map='auto',
        max_new_tokens=512,
        do_sample=True,
        top_k=30,
        num_return_sequences=1,
        tokenizer=tokenizer,
        eos_token_id=tokenizer.eos_token_id
    )
    global llm
    llm = HuggingFacePipeline(pipeline=pipe, model_kwargs={'temperature': 0})


def get_relevant_docs(question, vector_store):
    docs = vector_store.similarity_search(question)
    texts = docs[0:10]
    return texts


def get_random_docs(docs):
    len_docs = len(docs)
    random_num = []
    for i in range(3):
        random_num.append(random.randint(0, len_docs))
    texts = []
    for i in range(3):
        texts.append(docs[random_num[i]])
    return texts


# 根据列表长度进行处理
def get_Same_distance_docs(docs):
    len_docs = len(docs)
    texts = []
    num = 10  # 这里指要拿到的分割文档的数量，这里暂定为10，之后有待处理
    pos = 0
    len_jmp = len_docs // num
    for i in range(10):
        pos = pos + len_jmp
        texts.append(docs[pos])
    return texts


def link_text(texts):
    text = ""
    for in_text in texts:
        text += in_text.page_content
        text += "\n\n"
    text += "\n"
    return text


def get_summary(texts):
    text = link_text(texts)
    global sma_chain
    print(sma_chain.invoke({"text": text}))


# 这里初步决定还是先使用一个文档的分割文档，不用进行向量存储之后的（因为不确定存储后还能不能找到原文档里的顺序）
# 之后可以做更细致地处理，比如要把摘要一定放进去等等
def get_summary_text(docs):
    texts = get_Same_distance_docs(docs)
    get_summary(texts)


# 之后有待更细致地分割手段
def get_split_docs_vectors(docs):
    pdf_file_path = "../attention is all you need.pdf"
    pdf_loader = PyPDFLoader(pdf_file_path)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=0)
    split_docs = text_splitter.split_documents(pdf_loader.load())

    EMBEDDING_MODEL_NAME = "./instructor-large"

    embeddings = HuggingFaceInstructEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        query_instruction="Represent the query for retrieval: "
    )

    vector_store = Chroma(
        collection_name='llama2_demo',
        embedding_function=embeddings,
        persist_directory='./'
    )
    vector_store.add_documents(split_docs)
    query = "What is attention"
    docs = vector_store.similarity_search(query)
    print(docs[0].page_content) #得到的文档调用page_content得到内容
    return split_docs, vector_store


def get_question(text):
    global que_chain
    print(que_chain.invoke({"text": text}))


def get_relevant_question(docs):
    texts = get_random_docs(docs)
    for text in texts:
        get_question(text.page_content)


def get_qa(question, vector_store):
    texts = get_relevant_docs(question, vector_store)


