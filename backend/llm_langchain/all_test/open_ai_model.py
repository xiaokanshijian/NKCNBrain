import nkcn_public_config as _public_config
#coding=UTF-8
from langchain_community.chat_models.huggingface import ChatHuggingFace
import random
from langchain.docstore.document import Document
from langchain_community.llms.huggingface_text_gen_inference import HuggingFaceTextGenInference
from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
import os
# os.environ["http_proxy"] = "http://localhost:7890"
# os.environ["https_proxy"] = "http://localhost:7890"

os.environ.setdefault('HUGGINGFACEHUB_API_TOKEN', _public_config.secret('NKCN_HUGGFACE_GET_MODEL_API_KEY'))
from huggingface_hub import notebook_login

import torch
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceInstructEmbeddings

from langchain import HuggingFacePipeline
from langchain import PromptTemplate, LLMChain
from transformers import AutoModelForCausalLM, AutoTokenizer
from langchain.document_loaders import PyPDFLoader
import json
import textwrap
from langchain.schema import (
    HumanMessage,
    SystemMessage,
    AIMessage
)
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from langchain_community.llms import HuggingFaceHub
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field


chat_template = None
chat_model = ChatOpenAI(temperature=0, openai_api_key=_public_config.secret('NKCN_CLAUDE_API_API_KEY'),streaming = True,model_name="gpt-3.5-turbo")
que_chain = None
class Question(BaseModel):
    question: str = Field(description="question about the given text")


parser = JsonOutputParser(pydantic_object=Question)

def get_que_chain():
    messages = [
        SystemMessage(content="You are an advanced assistant to put forward a question for a given text.\n"),
        HumanMessagePromptTemplate.from_template(
            "{format_instructions}\nPlease put forward a question about the given text in Chinese:\n\n {text}"),
        #AIMessage(content="")  # 对AI的指明极其影响效果
    ]
    global  chat_template
    chat_template = ChatPromptTemplate.from_messages(messages)
    global que_chain
    chat_template = chat_template.partial(format_instructions=parser.get_format_instructions())
    print(chat_template)
    #print(chat_template.format(text =  "sssssss"))
    #que_chain = LLMChain(prompt=chat_template, llm=chat_model, output_parser = parser)
    #que_chain = LLMChain(prompt=chat_template, llm=chat_model)
    que_chain = chat_template | chat_model | parser


def get_question(text):
    #for chunk in que_chain.stream({"text": text}):
        #print(chunk["text"], end="\n", flush=True)
    for chunk in que_chain.stream({"text":text}):
        print(chunk, end="\n", flush = True)
    #    print(chunk)
        #print(chunk['prompt'])
     #   print(2)
    #print(que_chain.invoke({"text":text}))

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
    #vector_store.add_documents(split_docs)
    #翻阅源码后也并未找到使用add_documents与add_texts的问题所在，目前应该只能使用from_documents
    vector_store = Chroma.from_documents(split_docs,embeddings)
    #query = "What is attention"
    #docs = vector_store.similarity_search(query)
    #print(docs[0].page_content) #得到的文档调用page_content得到内容
    return split_docs, vector_store


def get_random_docs(docs):
    len_docs = len(docs)
    random_num = []
    for i in range(min(len_docs,3)):
        random_num.append(random.randint(0, len_docs-1))
    texts = []
    for i in range(min(len_docs,3)):
        texts.append(docs[random_num[i]])
    return texts


def get_relevant_question(docs):
    texts = get_random_docs(docs)
    for text in texts:
        get_question(text)

#import asyncio
import normal_qa
#import get_suma
if __name__ == '__main__':
    normal_qa.init_qa(1, None)
    #get_suma.init_suma()
    #get_que_chain()
    text = "路上只我一个人，背着手踱着。这一片天地好像是我的;我也像超出了平常旳自己，到了另一世界里。我爱热闹，也爱冷静;爱群居，也爱独处。像今晚上，一个人在这苍茫旳月下，什么都可以想，什么都可以不想，便觉是个自由的人。白天里一定要做的事，一定要说的话，现在都可不理。这是独处的妙处，我且受用这无边的荷香月色好了。曲曲折折的荷塘上面，弥望旳是田田的叶子。叶子出水很高，像亭亭旳舞女旳裙。层层的叶子中间，零星地点缀着些白花，有袅娜(niǎo,nuó)地开着旳，有羞涩地打着朵儿旳;正如一粒粒的明珠，又如碧天里的星星，又如刚出浴的美人。微风过处，送来缕缕清香，仿佛远处高楼上渺茫的歌声似的。这时候叶子与花也有一丝的颤动，像闪电般，霎时传过荷塘的那边去了。叶子本是肩并肩密密地挨着，这便宛然有了一道凝碧的波痕。叶子底下是脉脉(mò)的流水，遮住了，不能见一些颜色;而叶子却更见风致了。月光如流水一般，静静地泻在这一片叶子和花上。薄薄的青雾浮起在荷塘里。叶子和花仿佛在牛乳中洗过一样;又像笼着轻纱的梦。虽然是满月，天上却有一层淡淡的云，所以不能朗照;但我以为这恰是到了好处——酣眠固不可少，小睡也别有风味的。月光是隔了树照过来的，高处丛生的灌木，落下参差的斑驳的黑影，峭楞楞如鬼一般;弯弯的杨柳的稀疏的倩影，却又像是画在荷叶上。塘中的月色并不均匀;但光与影有着和谐的旋律，如梵婀(ē)玲(英语violin小提琴的译音)上奏着的名曲。荷塘的四面，远远近近，高高低低都是树，而杨柳最多。这些树将一片荷塘重重围住;只在小路一旁，漏着几段空隙，像是特为月光留下的。树色一例是阴阴的，乍看像一团烟雾;但杨柳的丰姿，便在烟雾里也辨得出。树梢上隐隐约约的是一带远山，只有些大意罢了。树缝里也漏着一两点路灯光，没精打采的，是渴睡人的眼。这时候最热闹的，要数树上的蝉声与水里的蛙声;但热闹是它们的，我什么也没有。"
    docs, vectors = get_split_docs_vectors(text)
    #loop = asyncio.get_event_loop()
    #res = loop.run_until_complete(get_relevant_question(docs))
    #get_suma.get_summary_text(docs)
    #for vector in vectors:
        #print(vector)
    normal_qa.get_qa("what is attention？", vectors)
    #loop.close()
    #get_relevant_question(docs)