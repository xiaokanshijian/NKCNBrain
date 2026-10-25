import nkcn_public_config as _public_config
from langchain_community.chat_models.huggingface import ChatHuggingFace
import random

import os
os.environ.setdefault('HUGGINGFACEHUB_API_TOKEN', _public_config.secret('NKCN_HUGGFACE_GET_MODEL_API_KEY'))
os.environ['CURL_CA_BUNDLE'] = ''
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceInstructEmbeddings

from langchain import PromptTemplate, LLMChain
from langchain.document_loaders import PyPDFLoader
from langchain.schema import (
    HumanMessage,
    SystemMessage,
    AIMessage
)
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from langchain_community.llms import HuggingFaceHub

from typing import List
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field
# from langchain_openai import ChatOpenAI


# Define your desired data structure.

class Question(BaseModel):
    question: str = Field(description="question about the given text")


parser = JsonOutputParser(pydantic_object=Question)

llm = HuggingFaceHub(
    repo_id="google/flan-t5-large",
    task="text-generation",
    huggingfacehub_api_token=_public_config.secret('NKCN_HUGGFACE_GET_MODEL_API_KEY'),
    model_kwargs={
        "max_new_tokens": 250,
        "top_k": 30,
        "temperature": 0.1,
        "repetition_penalty": 1.03,
    },
    # token = '[redacted]'
)

chat_model = ChatHuggingFace(llm=llm)

que_chain = None


def get_que_chain():
    messages = [
        SystemMessage(content="You are an advanced assistant to put forward a question for a given text."),
        HumanMessagePromptTemplate.from_template(
            "Please put forward a question about the given text:\n\n {text}"),
        # AIMessage(content="")  # 对AI的指明极其影响效果
    ]
    chat_template = ChatPromptTemplate.from_messages(messages)
    # chat_template = chat_template.partial(format_instructions=parser.get_format_instructions())
    global que_chain
    que_chain = chat_template | chat_model


def get_question(text):
    global que_chain
    #for chunk in que_chain.stream({"text": text}):
    #    print(chunk, end="", flush=True)
    print(que_chain.invoke({"text": text}))


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
    print(docs[0].page_content)  # 得到的文档调用page_content得到内容
    return split_docs, vector_store


def get_random_docs(docs):
    len_docs = len(docs)
    random_num = []
    for i in range(3):
        random_num.append(random.randint(0, len_docs))
    texts = []
    for i in range(3):
        texts.append(docs[random_num[i]])
    return texts


def get_relevant_question(docs):
    texts = get_random_docs(docs)
    for text in texts:
        get_question(text.page_content)


if __name__ == '__main__':
    get_que_chain()
    docs, vectors = get_split_docs_vectors(None)
    get_relevant_question(docs)
