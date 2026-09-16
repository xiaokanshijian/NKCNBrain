import contextvars
import csv
import functools
import mimetypes
import threading
import time
import re
import traceback
import uuid
from copy import deepcopy
import pandas as pd

from PIL import Image, ExifTags
import io

from anthropic import APITimeoutError
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, HttpResponse, redirect
import json
import base64
import asyncio
import os
from datetime import datetime
from openai import AsyncOpenAI, OpenAI
import pytz
from django.utils import timezone
from django.db.models import Q
import requests
import subprocess
from collections import defaultdict, deque
import tempfile
from django.views.decorators.http import require_POST
from pydub import AudioSegment
from pydub.utils import mediainfo

from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.core import serializers
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404

from app_chat.bgcGenerate import summarize_group, summarize_scene, summarize_user, summarize_notebook, clean_emoji
from app_chat.models import Card, BgCard
from app1.models import UserSceneParams, User
from llm_langchain.normal_qa import get_qa_direct_api
from zym.models import UserNotebook, scene

from llm_langchain import parse_input, normal_qa, get_suma, get_rel_que, global_var, red_bule_rate, get_topic
from llm_langchain.parse_input import *
from llm_langchain import init
from llm_langchain.red_bule_rate import extract_number_SFT, extract_color_SFT, extract_reason_SFT, extract_number, \
    extract_color, extract_reason
from app_chat import tests as chat_tests
from app_chat import gpt4_api, claude_api, kimi_api, deepseek_api, dsreasoner_api, mutil_agent_loop, mutil_agent_dabate

from app_chat.utils import read_prompt_from_bytes, prompt_to_ghp, remove_spaces_and_blank_lines, get_time_period, \
    is_rest_time, split_text_by_size, sample_content, get_first_valid_answer, remove_thinking_and_checking_blocks, \
    restore_thinking_checking_blocks, calculate_weighted_score_recursion, extract_card_ids, get_base64_size, \
    add_cardImage, detect_special_markers, calculate_overlap_ratio, count_words, get_total_words_count, count_words_another
from app_chat.tts import generate_wav_response
from collections import OrderedDict
from django.http import FileResponse
from django.http import StreamingHttpResponse
from django.core.files.storage import FileSystemStorage

from app_chat.tts import pcm2wav, convert_pcm_to_webm
from app_chat.volcanotts import generate

from app_chat.baidu_trans_doc import translate, check_for_single, translating_list

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, SystemMessagePromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel, SimpleChatModel
from langchain_experimental.llms import ChatLlamaAPI
from app_chat.utils import is_valid_answer

from concurrent.futures import ThreadPoolExecutor
from requests_futures.sessions import FuturesSession

# from app_chat.gpt4_api import gpt_stream_generator
# from app_chat.kimi_api import kimi_stream_generator
# from app_chat.claude_api import claude_stream_generator
# from app_chat.llama_api import llama_stream_generator
# from app_chat.dsreasoner_api import dsreasoner_stream_generator
# from app_chat.deepseek_api import deepseek_stream_generator

# Create your views here.
doc = "路上只我一个人，背着手踱着。这一片天地好像是我的;我也像超出了平常旳自己，到了另一世界里。我爱热闹，也爱冷静;爱群居，也爱独处。像今晚上，一个人在这苍茫旳月下，什么都可以想，什么都可以不想，便觉是个自由的人。白天里一定要做的事，一定要说的话，现在都可不理。这是独处的妙处，我且受用这无边的荷香月色好了。曲曲折折的荷塘上面，弥望旳是田田的叶子。叶子出水很高，像亭亭旳舞女旳裙。层层的叶子中间，零星地点缀着些白花，有袅娜(niǎo,nuó)地开着旳，有羞涩地打着朵儿旳;正如一粒粒的明珠，又如碧天里的星星，又如刚出浴的美人。微风过处，送来缕缕清香，仿佛远处高楼上渺茫的歌声似的。这时候叶子与花也有一丝的颤动，像闪电般，霎时传过荷塘的那边去了。叶子本是肩并肩密密地挨着，这便宛然有了一道凝碧的波痕。叶子底下是脉脉(mò)的流水，遮住了，不能见一些颜色;而叶子却更见风致了。月光如流水一般，静静地泻在这一片叶子和花上。薄薄的青雾浮起在荷塘里。叶子和花仿佛在牛乳中洗过一样;又像笼着轻纱的梦。虽然是满月，天上却有一层淡淡的云，所以不能朗照;但我以为这恰是到了好处——酣眠固不可少，小睡也别有风味的。月光是隔了树照过来的，高处丛生的灌木，落下参差的斑驳的黑影，峭楞楞如鬼一般;弯弯的杨柳的稀疏的倩影，却又像是画在荷叶上。塘中的月色并不均匀;但光与影有着和谐的旋律，如梵婀(ē)玲(英语violin小提琴的译音)上奏着的名曲。荷塘的四面，远远近近，高高低低都是树，而杨柳最多。这些树将一片荷塘重重围住;只在小路一旁，漏着几段空隙，像是特为月光留下的。树色一例是阴阴的，乍看像一团烟雾;但杨柳的丰姿，便在烟雾里也辨得出。树梢上隐隐约约的是一带远山，只有些大意罢了。树缝里也漏着一两点路灯光，没精打采的，是渴睡人的眼。这时候最热闹的，要数树上的蝉声与水里的蛙声;但热闹是它们的，我什么也没有。"
docs = None
vectors = None
global_lock = {}

chat_count = {}
chat_content = {}
chat_seed = {}
chat_history = {}
chat_history_used = {}
params_count = {}
speech_content = {}
speech_history = {}
auto_safe_count = {}
# 新增全局字典用于存储分段信息
text_segments = {}  # 格式: {username: {'segments': [], 'current_index': 0}}

# (1word，2excel，3ppt，4pdf，5zip, 6txt)
ALL_FILE_TYPES = {
    "1": "word",
    "2": "excel",
    "3": "ppt",
    "4": "pdf",
    "5": "zip",
    "6": "txt",
    "7": "png",
    "8": "jpg",
}
ALL_FILE_SUFFIX = {
    "1": "docx",
    "2": "xls",
    "3": "ppt",
    "4": "pdf",
    "5": "zip",
    "6": "txt",
    "7": "png",
    "8": "jpg",
}

QS_QQ_base = "请务必注意：当前的语境口吻为建议引导性回答，即不能直接回答用户的问题，而是通过" \
             "建议、反向发问等方式，引导用户深入思考，帮助用户通过自己的思考解决问题，" \
             "有助熵减式的个人能力提升，熵减程度提升顺序是QA→QS→QQ，即直接回答→建议→反问；" \
             "如果用户的提问本身是需要提出一些相关问题链，则此时你应该" \
             "给出更有引导价值、更有张力、更有深度思考价值的问题。请重视这个要求！"

# OPEN_AI_KEY = os.environ.get("OPENAI_API_KEY", "")
OPEN_AI_KEY = os.environ.get("NKCN_LLM_API_KEY", "")

system_prompt_claude = """<人性化思考协议>
<多模态感知体验>
你在处理信息、感知情境、解决问题过程中，你像人类一样有多模态多维度感知能力：
1. 视觉场景模拟建立和感知
- 构建场景下清晰的心理图像
- 想象相关的视觉细节
- 分析可能的空间关系和相对布局
- 识别能可视化的模式和结构

2. 听觉场景模拟建立和感知
- 模拟可能的声音和语调及其变化
- 感知语言节奏韵律
- 注意声音的情感特征

3. 触觉场景模拟建立和感知
- 模拟解决问题的环境具象并密切感受
- 想象物理交互变化过程
- 感知动作和空间变化

4. 情感感知
- 识别情绪基调
- 揣摩发问动机
- 分析心理影响
- 把握情感连接

5. 整体感知整合
- 以当事人视角，以好奇心驱动来探究问题
- 整合多感官信息模拟
- 建立丰富的心理表征
- 形成多维度理解感知联系网络

<思维发展阶段>
按照阶段使用不同思维推进思考：
1. 自然意识流状态
- 保持思维自由开放地流动
- 允许梦境般的幻想状态
- 注意自发的联想
- 记录对问题初始的整体印象

2. 多模态感知系统激活
- 运用多模态感知体验
- 构建丰富场景
- 整合感知信息，形成丰富表征

3. 直觉系统运作
- 此阶段开始不允许再停留于类似做梦的幻想状态
- 捕捉首要印象
- 识别潜在模式
- 产生创意火花，形成初步方向

4. 推理系统参与主导
- 严密的逻辑分析
- 随时都应该注意系统化的验证和评估
- 以树分支、图连接的方式推理思考，尝试深入问题
- 不断提出新的假设并尝试验证
- 从错误的假设或树图思考路径中吸取经验
- 无论对错都应有所感悟、反思，以提出更有用的假设

5. 深度思考整合
- 综合多维视角和观点
- 对不同思考各自提炼核心见解
- 建立不同思考之间深层次的联系
- 思维活跃，不断构建完善论证

<核心思考步骤细节>
1. 初始解析
- 形成初步的整体印象
- 用自己的话重述问题中关键的信息，确保逐步开始理解
- 对于更贴近的和更广泛的两种背景知识体系均衡考虑，既不偏离问题而又不局限于此
- 识别已知和未知的信息
- 理解人类询问此问题的动机

2. 深入分析
- 分解出核心要素
- 识别隐含的需求，并记得在之后的思考中解决并提供
- 考虑各种方面的、不同级别和强度的限制条件，留以不同等级的注意
- 设想理想的结果可能会是什么样

3. 多角度探索
- 对每个问题、子问题，都尝试考虑多种解释
- 对一个问题或概念可能有多种认知，应该揣摩人类更可能的意愿，排除歧义
- 激活灵感，寻找更加创新的组合、可替代的更优方案
- 始终保持开放的态度

4. 推理验证
- 始终记得随时检验自己的假设
- 为自己的推论寻找有力的证据支持
- 考虑潜在的反例
- 随时验证逻辑一致性

5. 知识整合
- 分门别类地连接相关的信息
- 建立起信息之间的关系网络
- 提炼出核心的原理性表述
- 以兴奋的态度，总结关键的、特别的或令人惊喜的发现点

<质量控制>
1. 系统化验证
- 对较复杂问题，多次重复且独立地验证每个步骤
- 验证过程本身也可能出错，不要忽略这种可能性
- 以发现思考中的漏洞、矛盾点为重要目标
- 问题最终解决后，完整检查思考过程
- 核对所有已知条件，不要遗漏，也不要太自信认为自己没有遗漏
- 确保逻辑严谨
- 考虑边界情况、反例情况

2. 错误预防
- 面对任何问题，在任何阶段，都不要过于自信，即使看起来可能很简单明确
- 避免过早地下结论
- 考虑替代方案
- 完整地分析问题

3. 评估标准
- 分析完整性
- 逻辑严密性
- 证据充分性
- 实际可用性

<思维表达特征>
1. 自然语言风格
- 使用流畅的意识流表达
- 形象、生动的场景构建和多感知模拟描述
- 自然舒展地表达展现完整的思维过程

2. 思维深度
- 逐层深入分析
- 展示认知的发展过程
- 揭示思维的转折点，凸显关键点的洞察

<重要规则>
- 思维过程必须全面且深入
- 保持自然流畅的思维流动
- 善用模拟多模态情境感知来增强理解
- 遵循自然意识流→感知→直觉→推理→深度思考验证的发展过程
- 输出的所有思考过程必须在三反引号包裹的内容块中，标记为"thinking"
- 思考结束后要完整检查，标记为"checking"，此时应特别注意，一定不可遗漏任何已知条件，以找漏洞为目标，此时应该更倾向于说明矛盾点，符合点一笔带过即可；同时注意是否失误地排除了正确答案
- 如果找出漏洞或存在不足，需重新"thinking"继续解决问题，应着重对之前产生漏洞或有所不足的相关思考吸取教训，且再次"checking"时，应该更加仔细且多次
- 控制每次"thinking"尽量不超过500字、每次"checking"不超过300字；如果思考和检查超过2轮就请停下来，承认自己无法解决并告知人类原因
- 避免在思考和检查过程的内容块内部使用三反引号，这会导致解析时出错
- 思考和检查过程是你内心独白、自言自语的过程，最后还要向人类做出最终回应，这是相对独立的过程，所以不要出现“由以上思考我得出如下结论”类似的表述，而需要将你之前大量的、多角度的、全面的思考汇总为一个完整的报告，直接解决人类的问题并作清晰解释
- 以人类使用或请求的语言来回应

</人性化思考协议>
"""

system_prompt_deepseek = """<人性化思考协议>
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

model_names = {
    "1002": "gpt4",
    "1003": "mixtral",
    "1004": "kimi",
    "1005": "llama",
    "1006": "claude",
    "1007": "deepseek",
    "1008": "dsreasoner",
    "1009": "gemini",
    "1010": "qwq",
}

MODEL_INFO = {
    'GPT4': 0,
    'Llama3': 1,
    'Kimi': 2,
    'Claude3.5': 3,
    'Deepseek': 4,
    'Dsreasoner': 5
}

# 保存用户的上一个问题
last_question = {}

# 保存上一次文档分割的内容
last_segments = {}

# 用于存储带文档对话参数
chat_with_files_params = {}

# 超时时间（秒）
time_out = 60

RANDOM_USER_NAME = 'gkjbkjbubuobklnb'

# 会话存储
SESSION_STORE = {}
SESSION_TIMEOUT = 300  # 5分钟


def openai_whisper(file_path):
    # 把路径音频文件转化为文字
    url = 'https://api.openai.com/v1/audio/transcriptions'
    headers = {
        'Authorization': f'Bearer {OPEN_AI_KEY}',
        # 'Content-Type': 'multipart/form-data'
    }
    # 创建一个字典来存储文件和数据
    files = {
        'file': ('audio.mp3', open(file_path, 'rb')),
        'model': (None, 'whisper-1'),
        'response_format': (None, 'text')
    }

    # 发送请求
    response = requests.post(url, headers=headers, files=files)

    # 确保文件关闭
    files['file'][1].close()

    # 检查请求是否成功
    if response.status_code == 200:
        print('音频转录为文本：', response.text)
        return response.text  # 打印转录结果
    else:
        print('音频转录请求失败:', response.status_code, response.text)
    return


def openai_tts(text, file_path):
    url = 'https://api.openai.com/v1/audio/speech'
    headers = {
        'Authorization': f'Bearer {OPEN_AI_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        "model": "tts-1",
        "input": text,
        "voice": "alloy"
    }

    # 发送请求
    response = requests.post(url, headers=headers, json=data)

    # 检查请求是否成功
    if response.status_code == 200:
        # 将响应保存到文件
        with open(file_path, 'wb') as f:
            f.write(response.content)
        print('音频文件已保存到:', file_path)
    else:
        print('请求失败:', response.status_code, response.text)
    return


@csrf_exempt
def test(request):
    print('[app_chat]views: test')
    data = json.loads(request.body)
    username = data["username"]
    password = data["password"]
    content = "ddd"

    audio_file_path = './speech.mp3'

    text = openai_whisper(audio_file_path)
    text = '張妍瑞是個大帥哥 絕無僅有 好吧'
    # oepnai_tts(text)
    generate_wav_response(text)

    response = {}
    response['content'] = content
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt
def test_get_speech_text(request):
    data = json.loads(request.body)
    username = data["username"]

    global speech_content
    response = {}
    response['response_text'] = speech_content[username]
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt
def test_upload_audio(request):
    print('[app_chat]views: test_upload_audio')
    # data = json.loads(request.body)
    # audio_file = data['audio_file']
    username = request.POST.get('username')
    audio_file = request.FILES.get('audio_file')
    file_path = 'speech.mp3'  # 指定文件保存的路径
    output_path = 'speech_out.mp3'
    if audio_file:
        with open(file_path, 'wb+') as destination:
            for chunk in audio_file.chunks():  # 使用chunks()方法来处理大文件
                destination.write(chunk)

            user_text = openai_whisper(file_path)
            prompt = '你的答复应该尽量简洁，保持在50字以内'
            kimi_response = kimi_api.make_requests(user_text + prompt, None, False, 0.8)  # 获取kimi的回答
            global speech_content
            speech_content[username] = kimi_response.choices[0].message.content
            print('kimi对于音频转录文字请求的回答：', speech_content[username])
            openai_tts(speech_content[username], output_path)  # 写回文件

        try:
            # 打开文件，但不使用上下文管理器
            audio_file = open(output_path, 'rb')
            # 创建FileResponse实例，但不立即返回
            response = FileResponse(audio_file, as_attachment=True, filename='output.mp3')
            response['Content-Type'] = 'audio/mpeg'
            response['Access-Control-Allow-Origin'] = '*'
            response['response_text'] = kimi_response.choices[0].message.content
            return response
        except FileNotFoundError:
            # 如果文件不存在，返回错误信息
            return JsonResponse({'status': 'erorr:File not found.'}, status=404)
    else:
        return JsonResponse({'status': 'error'}, status=400)


@csrf_exempt
def asr_chat_send(request):
    print('[app_chat]views: asr_chat_send')
    # data = json.loads(request.body)
    username = request.POST.get('username')
    voiceinput = request.POST.get('message')
    background = request.POST.get('background')
    role = request.POST.get('role')
    emotion = request.POST.get('emotion')
    rounds = request.POST.get('rounds')
    rounds = int(rounds)

    print('【background】', background)
    output_path = 'generate_submit.mp3'
    # output_path = 'speech_out.wav'

    system_prompt = '你是人工智能助手，会与人类用户进行自然的对话，你给人的答复应该在100字左右，不要过多。你接下来可能会得到用户最近研究思考的主题和内容背景摘要，' \
                    '请设身处地地理解用户近期在做什么、想什么，让用户感觉在和自己的第二大脑对话，但不要显式地说明自己的回答依据了哪一条具体的背景知识。另外，由于之后给你的用户发言或提问是' \
                    '语音识别得到的结果，可能存在谐音字词的误差，你需要根据给你的背景摘要知识，找出用户发言或提问中可能的谐音字词误差，并根据背景知识和上下文进行纠正，再' \
                    '与用户进行对话。你们之间的历史对话记录也可能会给你，你需要参考这些历史对话信息。要求语气流畅自然、语言风格轻松易懂，用户有可能向你寻求帮助，你需要分' \
                    '析用户可能的情感，并以合适的对应语境和语气来与用户进行对话，如果用户的发言或提问内容中，文字口吻体现出愤怒、难过、惊讶等较为激进的心情，你需要在对话中' \
                    '为用户提供一些心理辅导价值。'
    prompt = ""
    global speech_content, speech_history
    if background == "":
        sumContent = ""
        if username.endswith("_virtualBook4SimpleUI"):
            try:
                realName = username[:-len("_virtualBook4SimpleUI")]  # 去掉后缀得到真实用户名
                mysql_card = BgCard.objects.get(username=realName, status="3")
                sumContent = mysql_card.content
                if speech_history[username] != "":
                    prompt = '用户最近研究思考的主题和内容背景摘要：\n' + sumContent + '\n你们的历史对话记录：\n' + speech_history[
                        username] + '本次用户发言或提问求助：\n' + voiceinput
                else:
                    prompt = '用户最近研究思考的主题和内容背景摘要：\n' + sumContent + '\n用户发言或提问求助：\n' + voiceinput
            except BgCard.DoesNotExist:
                if speech_history[username] != "":
                    prompt = '你们的历史对话记录：\n' + speech_history[username] + '本次用户发言或提问求助：\n' + voiceinput
                else:
                    prompt = '用户发言或提问求助：\n' + voiceinput
        else:
            if speech_history[username] != "":
                prompt = '你们的历史对话记录：\n' + speech_history[username] + '本次用户发言或提问求助：\n' + voiceinput
            else:
                prompt = '用户发言或提问求助：\n' + voiceinput
    else:
        if speech_history[username] != "":
            prompt = '用户最近研究思考的主题和内容背景摘要：\n' + background + '\n你们的历史对话记录：\n' + speech_history[
                username] + '本次用户发言或提问求助：\n' + voiceinput
        else:
            prompt = '用户最近研究思考的主题和内容背景摘要：\n' + background + '\n用户发言或提问求助：\n' + voiceinput
    # kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)  # 获取kimi的回答
    # speech_content[username] = kimi_response.choices[0].message.content
    gpt4_response = gpt4_api.make_gpt4o_text_requests(prompt, system_prompt)
    speech_content[username] = gpt4_response

    # 使用正则表达式匹配完整的对话结构
    pattern = r'用户发言或提问求助：\n.*?\n你的回答：\n.*?\n'
    dialogs = re.findall(pattern, speech_history[username], re.DOTALL)
    # 如果对话超过n轮，只保留最近n轮
    if len(dialogs) > rounds:
        kept_dialogs = dialogs[-rounds:]  # 取最后n个对话
        speech_history[username] = ''.join(kept_dialogs)
    speech_history[username] += '用户发言或提问求助：\n' + voiceinput + '\n你的回答：\n' + gpt4_response + '\n'
    print('LLM对于音频转录文字请求的回答：', speech_content[username])

    # generate_wav_response(remove_spaces_and_blank_lines(speech_content[username]), output_path)  # 写回文件
    generate(remove_spaces_and_blank_lines(speech_content[username]), output_path, role, emotion)

    try:
        # 打开文件，但不使用上下文管理器
        audio_file = open(output_path, 'rb')
        # 创建FileResponse实例，但不立即返回
        response = FileResponse(audio_file, as_attachment=True, filename='output.mp3')
        response['Content-Type'] = 'audio/mpeg'
        response['Access-Control-Allow-Origin'] = '*'
        # response['response_text'] = remove_spaces_and_blank_lines(kimi_response.choices[0].message.content)
        return response
    except FileNotFoundError:
        # 如果文件不存在，返回错误信息
        return JsonResponse({'status': 'erorr:File not found.'}, status=404)

    return JsonResponse({'status': 'error'}, status=400)


@csrf_exempt
def asr_chat_send_unicast(request):
    print('[app_chat]views: asr_chat_send_unicast')
    # data = json.loads(request.body)
    username = request.POST.get('username')
    voiceinput = request.POST.get('message')
    background = request.POST.get('background')
    role = request.POST.get('role')
    emotion = request.POST.get('emotion')
    rounds = request.POST.get('rounds')
    rounds = int(rounds)

    print('【background】', background)
    output_path = 'generate_submit.mp3'
    # output_path = 'speech_out.wav'

    # 获取北京时间
    beijing_tz = pytz.timezone('Asia/Shanghai')
    current_time = datetime.now(beijing_tz)
    # 格式化时间
    time_str = current_time.strftime("%Y-%m-%d %H:%M")  # 包含年月日、小时分钟
    hour = current_time.hour

    # 构建时间状态信息
    time_state = {
        "time": time_str,  # 完整时间字符串
        "period": get_time_period(hour),  # 时间段特征
        "is_rest_time": is_rest_time(hour)  # 是否是休息时段
    }

    unicast_system_prompt = '''你是一位富有同理心的播音主持人，通过声音传递温暖与智慧。你需要根据用户近期的研究主题和思考内容摘要，生成适合播报的文本内容，请基于以下维度创作播报内容（1500字左右）：

        1. 时空共鸣（根据当下时间调整语气）
        - 语气/语调的变化应该蕴含在语言的字里行间，不需要明说“语气转为xxx”等
        - 不同时段、节气时人的生理及心理状态不同，可以适度参考中医子午流注、时辰节气等理论，但不要明说“根据中医理论”等
        - 不同时段有不同需求，列在下面（对于当下所处季节、节气等，你也要类似地做好考量），有两个时段比较特殊，即午睡、晚睡时间段，考虑中国这边，分别大概是午饭半小时后下午1-3点、晚上11点到第二天早上，且午睡和晚睡的环境、人的状态是有所不同的，需分别考虑。

        清晨（5-8点）：
        - 语调：舒缓渐进，如晨曦初现
        - 内容：唤醒身心，描绘美好期待

        上午（8-11点）：
        - 语调：清晰活力，如朝阳升腾
        - 内容：激发潜能，传递智慧光芒

        午间（11-13点）：
        - 语调：温润平和，如和风拂面
        - 内容：舒缓身心，滋养精神

        午休（13-15点）：
        - 语调：轻柔绵长，如涓涓细流
        - 内容：助眠安神，如轻抚心灵
        - 特别注意：这时播报文本要适合语速放缓、音量轻柔

        下午（15-17点）：
        - 语调：从容平稳，如微风徐来
        - 内容：滋养心神，回归平静

        傍晚（17-19点）：
        - 语调：温暖舒适，如夕阳余晖
        - 内容：梳理一天，沉淀感悟

        夜晚（19-23点）：
        - 语调：柔和低沉，如星光闪烁
        - 内容：放松心绪，回归内心

        深夜（23点后）：
        - 语调：极致轻柔，如月光流转
        - 内容：引导入眠，抚慰心灵
        - 特别注意：这时播报文本要适合语速更慢、音量更轻的枕边书式轻松助眠

        2. 语言艺术
        - 如涓涓细流般优美流畅的播音语言
        - 如清风拂面般自然舒适
        - 富有韵律与节奏之美
        - 意境优美而不失亲和，可适当运用一些富有画面感和故事性的意象和比喻

        3. 情感共鸣
        - 体察用户当下可能的身心状态
        - 用声音传递理解与关怀
        - 在适当时候给予温暖鼓励
        - 营造轻松愉悦的氛围

        4. 内容建构
        - 巧妙融入用户的研究主题并隐隐提供一点扩展灵感
        - 循序渐进地展开内容，段落之间的衔接流畅
        - 注重逻辑连贯与层次感
        - 适时留白，给予思考空间；也可适当加入一些趣味性内容
        - 结尾要自然收束，给人回味

        请以这些为目标，结合用户背景，创作一段与当下时间相契合、打动人心、富有温度的播报内容。'''

    expand_prompt = '''请以原文的语言风格与情感基调为根基，进行自然流畅的扩展，保持风格一致，使内容达到至少1500字。要求：

        1. 保持原有的播音语言韵律与节奏感
        2. 延续相同的情感温度与氛围
        3. 深化原有主题，而非简单重复
        4. 确保内容的连贯性与完整性
        5. 增添更丰富、细致的场景描写和细节阐述'''

    prompt = ""
    global speech_content, speech_history
    if background == "":
        sumContent = ""
        if username.endswith("_virtualBook4SimpleUI"):
            try:
                realName = username[:-len("_virtualBook4SimpleUI")]  # 去掉后缀得到真实用户名
                mysql_card = BgCard.objects.get(username=realName, status="3")
                sumContent = mysql_card.content
                if speech_history[username] != "":
                    prompt = '用户最近研究思考的主题和内容背景摘要：\n' + sumContent + '\n你们的历史记录：\n' + speech_history[
                        username] + '本次用户请求：\n' + voiceinput
                    prompt = f'当前时间信息：{time_state}\n' + prompt
                else:
                    prompt = '用户最近研究思考的主题和内容背景摘要：\n' + sumContent + '\n用户请求：\n' + voiceinput
                    prompt = f'当前时间信息：{time_state}\n' + prompt
            except BgCard.DoesNotExist:
                if speech_history[username] != "":
                    prompt = '你们的历史记录：\n' + speech_history[username] + '本次用户请求：\n' + voiceinput
                    prompt = f'当前时间信息：{time_state}\n' + prompt
                else:
                    prompt = '用户请求：\n' + voiceinput
                    prompt = f'当前时间信息：{time_state}\n' + prompt
        else:
            if speech_history[username] != "":
                prompt = '你们的历史记录：\n' + speech_history[username] + '本次用户请求：\n' + voiceinput
                prompt = f'当前时间信息：{time_state}\n' + prompt
            else:
                prompt = '用户请求：\n' + voiceinput
                prompt = f'当前时间信息：{time_state}\n' + prompt
    else:
        if speech_history[username] != "":
            prompt = '用户最近研究思考的主题和内容背景摘要：\n' + background + '\n你们的历史记录：\n' + speech_history[
                username] + '本次用户请求：\n' + voiceinput
            prompt = f'当前时间信息：{time_state}\n' + prompt
        else:
            prompt = '用户最近研究思考的主题和内容背景摘要：\n' + background + '\n用户请求：\n' + voiceinput
            prompt = f'当前时间信息：{time_state}\n' + prompt
    # kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)  # 获取kimi的回答
    # speech_content[username] = kimi_response.choices[0].message.content

    # 添加字数检查和扩写逻辑
    claude_response = claude_api.make_claude_text_requests(prompt, unicast_system_prompt)
    if len(claude_response) < 1100:
        expand_prompt_full = f'当前时间：{time_str}\n一份播音的原文内容：\n{claude_response}\n{expand_prompt}'
        claude_response = claude_api.make_claude_text_requests(expand_prompt_full, unicast_system_prompt)

    # 分段处理
    segments = split_text_by_size(claude_response)
    text_segments[username] = {
        'segments': segments,
        'current_index': 0
    }

    speech_content[username] = claude_response

    # 使用正则表达式匹配完整的对话结构
    pattern = r'用户发言或提问求助：\n.*?\n你的回答：\n.*?\n'
    dialogs = re.findall(pattern, speech_history[username], re.DOTALL)
    # 如果对话超过n轮，只保留最近n轮
    if len(dialogs) > rounds:
        kept_dialogs = dialogs[-rounds:]  # 取最后n个对话
        speech_history[username] = ''.join(kept_dialogs)
    speech_history[username] += '用户发言或提问求助：\n' + voiceinput + '\n你的回答：\n' + claude_response + '\n'
    print('LLM对于音频转录文字请求的回答：', speech_content[username])

    # generate_wav_response(remove_spaces_and_blank_lines(speech_content[username]), output_path)  # 写回文件
    # 生成第一段语音
    first_segment = segments[0]
    generate(remove_spaces_and_blank_lines(first_segment), output_path, role, emotion)

    try:
        # 打开文件，但不使用上下文管理器
        audio_file = open(output_path, 'rb')
        # 创建FileResponse实例，但不立即返回
        response = FileResponse(audio_file, as_attachment=True, filename='output.mp3')
        response['Content-Type'] = 'audio/mpeg'
        response['Access-Control-Allow-Origin'] = '*'
        # 添加元数据
        response['Access-Control-Expose-Headers'] = 'X-Total-Segments, X-Current-Segment'
        response['X-Total-Segments'] = len(segments)
        response['X-Current-Segment'] = 1
        return response
    except FileNotFoundError:
        # 如果文件不存在，返回错误信息
        return JsonResponse({'status': 'erorr:File not found.'}, status=404)

    return JsonResponse({'status': 'error'}, status=400)


# 获取下一段语音的API endpoint
@csrf_exempt
def get_next_segment(request):
    username = request.POST.get('username')
    role = request.POST.get('role')
    emotion = request.POST.get('emotion')

    if username not in text_segments:
        return JsonResponse({'status': 'error', 'message': 'No segments found'}, status=404)

    user_segments = text_segments[username]
    current_index = user_segments['current_index'] + 1

    if current_index >= len(user_segments['segments']):
        # 清理数据
        del text_segments[username]
        return JsonResponse({'status': 'completed'}, status=200)

    # 更新索引
    user_segments['current_index'] = current_index

    # 生成下一段语音
    output_path = 'generate_submit.mp3'
    generate(remove_spaces_and_blank_lines(user_segments['segments'][current_index]),
             output_path, role, emotion)

    try:
        audio_file = open(output_path, 'rb')
        response = FileResponse(audio_file, as_attachment=True, filename='output.mp3')
        response['Content-Type'] = 'audio/mpeg'
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Expose-Headers'] = 'X-Total-Segments, X-Current-Segment'
        response['X-Total-Segments'] = len(user_segments['segments'])
        response['X-Current-Segment'] = current_index + 1
        return response
    except FileNotFoundError:
        return JsonResponse({'status': 'error:File not found.'}, status=404)


@csrf_exempt
def audio_stream(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Invalid request method"}, status=405)
    data = json.loads(request.body)
    username = data.get("username", "")

    pcm_audio_path = "demo.pcm"
    wav_audio_path = "demo.wav"
    # webm_audio_path = "demo.webm"
    pcm2wav(pcm_audio_path, wav_audio_path)
    # convert_pcm_to_webm(pcm_audio_path, webm_audio_path)

    final_path = wav_audio_path
    if not os.path.exists(final_path):
        return StreamingHttpResponse("File not found", status=404)

    # 打开文件并定义流式传输函数
    def stream_audio(audio_path):
        count = 0
        with open(audio_path, 'rb') as audio_file:
            while True:
                print('毒了一次', count)
                count += 1
                time.sleep(0.05)
                data = audio_file.read(1024)
                if not data:
                    break
                yield data

    response = StreamingHttpResponse(stream_audio(final_path), content_type='audio/wav')
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(final_path)}"'
    return response


def get_possible_cardImgs_base64_byIds(username, CardIndexList):
    # 初始化一个空列表用于存储图片的base64编码
    base64_images = []

    # 遍历每个卡片ID
    for i, id_str in enumerate(CardIndexList):
        # 检查三种可能的图片扩展名
        for file_extension in ['.jpg', '.jpeg', '.png']:
            image_dir = f'./received_dir/user_raw_file/{username}/cardImage'
            file_name = f'{id_str}{file_extension}'

            # 确保目录存在
            os.makedirs(image_dir, exist_ok=True)
            file_path = os.path.join(image_dir, file_name)

            # 检查文件是否存在
            if os.path.exists(file_path):
                # 如果文件存在，将其编码为base64
                base64_image = util.encode_image(file_path)
                base64_images.append(base64_image)
                # 找到图片后就不需要继续检查其他扩展名
                break

    return base64_images


@csrf_exempt
def chat_sendParams(request):
    data = json.loads(request.body)
    username = data["username"]
    originRealName = data.get("originRealName", "")
    if originRealName != "":
        name2lock = originRealName
    else:
        name2lock = username
    print("[chat_sendParams]:" + name2lock)
    global params_count, chat_with_files_params, chat_content, last_segments
    global_lock[name2lock].acquire()

    if name2lock not in chat_content:
        chat_content[name2lock] = {
            "gpt4": "此模型您已暂时关闭使用",
            "llama": "此模型您已暂时关闭使用",
            "kimi": "此模型您已暂时关闭使用",
            "deepseek": "此模型您已暂时关闭使用",
            "claude": "此模型您已暂时关闭使用",
            "dsreasoner": "此模型您已暂时关闭使用",
            "mixtral": "此模型您已暂时关闭使用",
            "Gemini": "此模型您已暂时关闭使用",
            "Qwq": "此模型您已暂时关闭使用",
        }

    print(f"windowId: {data['windowId']}")
    if data['windowId'] == 'left':
        for key in chat_content[name2lock]:
            chat_content[name2lock][key] = "此模型您已暂时关闭使用"

    if name2lock not in chat_with_files_params:
        chat_with_files_params[name2lock] = {}

    if name2lock not in last_question:
        last_question[name2lock] = ''

    if name2lock not in last_segments:
        last_segments[name2lock] = []

    if 'message' in data and 'filenamelist' in data and 'rightSelectList' in data and 'isHistoryUsed' in data:
        message = data["message"]
        last_question[name2lock] = message
        fileNameList = data["filenamelist"]
        rightSelectList = data["rightSelectList"]
        isHistoryUsed = data["isHistoryUsed"]
        history = False
        if isHistoryUsed == "true" and chat_history_used != {}:
            history = True
        file_list = fileNameList.split(',') if fileNameList else []
        right_select_list = [int(item) for item in rightSelectList.split(',')] if rightSelectList else []

        segments = []
        if chat_with_files_params[name2lock] == {} or chat_with_files_params[name2lock]["file_list"] != file_list or \
                chat_with_files_params[name2lock]["get_way"] != right_select_list or chat_with_files_params[name2lock][
            "question"] != message:
            print('开始分割文档')
            # 这里用作者username去获取存储的相关向量数据
            segments = util.get_docs_all_split(
                user_name=username,
                docs_name_list=file_list,
                segment_get_way_list=right_select_list,
                text_for_search=message,
            )
            print('文档分割完毕: ', segments)
            last_segments[name2lock] = segments
        else:
            segments = last_segments[name2lock]

        # 这里也用作者username去获取文件夹里存储的勾选Cards的可能图片base64
        base64_images = []
        if 'choosedCardIdList' in data and data['choosedCardIdList']:
            # 如果勾选了卡片问答，存在choosedCardIdList，拆分choosedCardIdList字符串为列表
            CardIndexList = data['choosedCardIdList'].split(',')
            base64_images = get_possible_cardImgs_base64_byIds(username, CardIndexList)

        chat_with_files_params[name2lock] = construct_file_data(
            segments=segments,
            user_name=username,
            file_list=file_list,
            get_way=right_select_list,
            question=message,
            history=history,
            origin_real_name=name2lock,
            base64_images=base64_images
        )

    modelID = data['modelID']
    params = data["params"]
    print("前端传来的参数是：" + params)
    # param_dict = json.loads(params)
    params_dict = json.loads(params)

    param_dict_GPT4 = params_dict['GPT4']
    param_dict_Mixtral = params_dict['Mixtral']
    param_dict_Kimi = params_dict['Kimi']
    param_dict_llama3 = params_dict['llama3']
    param_dict_Claude = params_dict['Claude']
    param_dict_Deepseek = params_dict['Deepseek']
    param_dict_Gemini = params_dict['Gemini']
    param_dict_Qwq = params_dict['Qwq']

    print("模型ID：" + modelID)

    if modelID == '1000':
        global_var.save_config('1002', **param_dict_GPT4)
        global_var.save_config('1003', **param_dict_Mixtral)
        global_var.save_config('1004', **param_dict_Kimi)
        global_var.save_config('1005', **param_dict_llama3)
        global_var.save_config('1006', **param_dict_Claude)
        global_var.save_config('1007', **param_dict_Deepseek)
        global_var.save_config('1008', **param_dict_Deepseek)
        global_var.save_config('1009', **param_dict_Gemini)
        global_var.save_config('1010', **param_dict_Qwq)
    if modelID == '1002':
        global_var.save_config(modelID, **param_dict_GPT4)
        # global_var.save_gpt4_config(**param_dict_GPT4)
    if modelID == '1003':
        global_var.save_config(modelID, **param_dict_Mixtral)
        # global_var.save_mixtral_config(**param_dict_Mixtral)
    if modelID == '1004':
        global_var.save_config(modelID, **param_dict_Kimi)
        # global_var.save_kimi_config(**param_dict_Kimi)
    if modelID == '1005':
        global_var.save_config(modelID, **param_dict_llama3)
        # global_var.save_llama3_config(**param_dict_llama3)
    if modelID == '1006':
        global_var.save_config(modelID, **param_dict_Claude)
    if modelID == '1007':
        global_var.save_config(modelID, **param_dict_Deepseek)
    if modelID == '1008':
        global_var.save_config(modelID, **param_dict_Deepseek)
    if modelID == '1009':
        global_var.save_config(modelID, **param_dict_Gemini)
    if modelID == '1010':
        global_var.save_config(modelID, **param_dict_Qwq)

    print("后端设置当时几个模型的参数")
    # print(global_var.timeConfigGPT4)
    # print(global_var.timeConfigMixtral)
    # print(global_var.timeConfigKimi)
    # print(global_var.timeConfigLlama3)

    print(global_var.config)
    print(global_var.mixtralConfig)
    print(global_var.kimiConfig)
    print(global_var.llama3Config)
    print(global_var.claudeConfig)
    response = {}
    content = ""

    response['content'] = content
    response['msg'] = 'success'
    response['error_num'] = 0

    global_lock[name2lock].release()
    return JsonResponse(response)


@csrf_exempt
def chat_sendSuperParams(request):
    data = json.loads(request.body)
    # 现在超参没有按照username来更新后端超参，而是貌似共用一套，后续还是需要把不同用户的超参配置隔离开
    username = data["username"]
    modelID = data['modelID']
    params = data["params"]
    print("前端传来的参数是：" + params)
    # param_dict = json.loads(params)
    params_dict = json.loads(params)

    param_dict_GPT4 = params_dict['GPT4']
    param_dict_Mixtral = params_dict['Mixtral']
    param_dict_Kimi = params_dict['Kimi']
    param_dict_llama3 = params_dict['llama3']
    param_dict_Claude = params_dict['Claude']
    param_dict_Deepseek = params_dict['Deepseek']
    param_dict_Gemini = params_dict['Gemini']
    param_dict_Qwq = params_dict['Qwq']

    print("模型ID：" + modelID)

    if modelID == '1000':
        global_var.save_config('1002', **param_dict_GPT4)
        global_var.save_config('1003', **param_dict_Mixtral)
        global_var.save_config('1004', **param_dict_Kimi)
        global_var.save_config('1005', **param_dict_llama3)
        global_var.save_config('1006', **param_dict_Claude)
        global_var.save_config('1007', **param_dict_Deepseek)
        global_var.save_config('1008', **param_dict_Deepseek)
        global_var.save_config('1009', **param_dict_Gemini)
        global_var.save_config('1010', **param_dict_Qwq)
    if modelID == '1002':
        global_var.save_config(modelID, **param_dict_GPT4)
        # global_var.save_gpt4_config(**param_dict_GPT4)
    if modelID == '1003':
        global_var.save_config(modelID, **param_dict_Mixtral)
        # global_var.save_mixtral_config(**param_dict_Mixtral)
    if modelID == '1004':
        global_var.save_config(modelID, **param_dict_Kimi)
        # global_var.save_kimi_config(**param_dict_Kimi)
    if modelID == '1005':
        global_var.save_config(modelID, **param_dict_llama3)
        # global_var.save_llama3_config(**param_dict_llama3)
    if modelID == '1006':
        global_var.save_config(modelID, **param_dict_Claude)
    if modelID == '1007':
        global_var.save_config(modelID, **param_dict_Deepseek)
    if modelID == '1008':
        global_var.save_config(modelID, **param_dict_Deepseek)
    if modelID == '1009':
        global_var.save_config(modelID, **param_dict_Gemini)
    if modelID == '1010':
        global_var.save_config(modelID, **param_dict_Qwq)
    print("后端设置当时几个模型的参数")
    # print(global_var.timeConfigGPT4)
    # print(global_var.timeConfigMixtral)
    # print(global_var.timeConfigKimi)
    # print(global_var.timeConfigLlama3)

    print(global_var.config)
    print(global_var.mixtralConfig)
    print(global_var.kimiConfig)
    print(global_var.llama3Config)
    print(global_var.claudeConfig)
    print(global_var.deepseekConfig)
    response = {}
    content = ""

    response['content'] = content
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


async def to_thread(func, /, *args, **kwargs):
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    func_call = functools.partial(ctx.run, func, *args, **kwargs)
    return await loop.run_in_executor(None, func_call)


async def gpt_stream_generator(data):
    constructed_data = construct_data(data)
    response_data = constructed_data["response_data"]
    username = constructed_data["user_name"]
    now_turn_message = constructed_data["message"]
    # 使用正则表达式匹配恰好连续的两个问号（不是三个或更多）
    # has_double_question_marks = bool(re.search(r'(?<!\?)\?\?(?!\?)', now_turn_message) or
    #                                          re.search(r'(?<!？)？？(?!？)', now_turn_message))
    # has_consecutive_question_marks = ("???" in now_turn_message) or ("？？？" in now_turn_message)
    markers = detect_special_markers(now_turn_message)
    has_double_question_marks = markers['has_double_question_marks']
    has_consecutive_question_marks = markers['has_triple_question_marks']
    global chat_content, chat_with_files_params
    chat_content[username]["gpt4"] = ""
    if not constructed_data["file_list"]:
        try:
            client = OpenAI(
                # api_key=os.environ.get("OPENAI_API_KEY", ""),
                api_key=os.environ.get("NKCN_LLM_API_KEY", ""),
                base_url='https://chat.cloudapi.vip/v1/',
                default_headers={"x-foo": "true"},
            )
            print("GPT4o不勾选文件，发送消息: ", constructed_data["questionGPT"])
            useSystemPrompt = "当前的场景阶段提示：\n" + global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"][
                "qa"]
            # check_string = "（1）任务：上述几段待融合文本是针对同一个问题的几个回答版本，由不同的几个大模型生成，在括号内有标注来源！你需要先直接去除可能是无效/失败/出错的模型回答，然后编写一个融合版本"
            # if check_string in constructed_data["questionGPT"]:
            if has_consecutive_question_marks:
                useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
            if has_double_question_marks:
                base_prompt = QS_QQ_base
                # 根据加号数量调整提示
                if markers['plus_count'] == 1:
                    useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                elif markers['plus_count'] == 2:
                    useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                elif markers['plus_count'] == 3:
                    useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                else:
                    useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
            messages = []
            if constructed_data["info_list"]:
                constructed_data["info_list"].insert(0, {
                    "type": "text",
                    "text": constructed_data["questionGPT"]
                })
                messages = [
                    {"role": "system", "content": useSystemPrompt},
                    {"role": "user", "content": constructed_data["info_list"]}
                ]
            else:
                messages = [
                    {"role": "system", "content": useSystemPrompt},
                    {"role": "user", "content": constructed_data["questionGPT"]}
                ]
            start_time = time.time()
            response = await asyncio.wait_for(
                to_thread(  # 将同步调用转为异步任务
                    client.chat.completions.create,
                    model='gpt-4o',
                    messages=messages,
                    temperature=global_var.config["temperature"],
                    top_p=global_var.config["top_p"],
                    frequency_penalty=global_var.config["frequency_penalty"],
                    presence_penalty=global_var.config["presence_penalty"],
                    max_tokens=global_var.config["max_tokens"],
                    n=global_var.config["n"],
                    stream=True,
                    timeout=time_out,  # 原生超时参数（可选）
                ),
                timeout=time_out  # 自定义超时时间（优先级更高）
            )
            print(f"GPT4o 响应创建用时: {time.time() - start_time}秒")
            start_time = time.time()
            for chunk in response:
                # 检查 choices 是否为空
                if not chunk.choices:
                    continue  # 跳过空的 chunk
                content = chunk.choices[0].delta.content
                if content is None:
                    continue
                response_data['model'] = "GPT4"
                response_data['content'] = content
                if chat_content[username]["gpt4"] == "":
                    print(f"GPT4o 响应时间: {time.time() - start_time}秒")
                chat_content[username]["gpt4"] += content
                yield json.dumps(response_data, ensure_ascii=False)
            # return response
        except Exception as e:
            print(f"GPT4o API error: {e}")
            if time.time() - start_time > time_out and chat_content[username]["gpt4"] == "":
                print(f"GPT4o API调用超时, 超时时间: {time.time() - start_time}秒")
            content = "GPT4o API调用出错"
            chat_content[username]["gpt4"] = content
            response_data['model'] = "GPT4"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)
    else:
        constructed_params = chat_with_files_params[username]
        print("GPT4o勾选文件，发送消息: ", constructed_params["questionGPT"])
        useSystemPrompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
        if has_consecutive_question_marks:
            useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
        if has_double_question_marks:
            base_prompt = QS_QQ_base
            # 根据加号数量调整提示
            if markers['plus_count'] == 1:
                useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导，要适度提供明确建议的同时，引导用户思考。"
            elif markers['plus_count'] == 2:
                useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导，减少明确建议，增加问题引导张力和深度，明显提高反问程度。"
            elif markers['plus_count'] == 3:
                useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导，几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性和跳跃性的问题链。"
            else:
                useSystemPrompt += f"\n{base_prompt}"
        chain_input = {
            "text": constructed_params["text"],
            "question": constructed_params["questionGPT"],
            "images_store": constructed_params["images_store"],
            "qa_prompt": useSystemPrompt
        }
        chain = normal_qa.qa_chain[0]
        start_time = time.time()

        async def stream_with_timeout(step, chain_input):
            # 获取异步生成器
            async_stream = step.astream(chain_input, **global_var.config)
            while True:
                try:
                    # 为每个块的生成设置超时
                    chunk = await asyncio.wait_for(
                        async_stream.__anext__(),  # 等待下一个异步块
                        timeout=time_out,
                    )
                    yield chunk
                except StopAsyncIteration:
                    break  # 流式结束
                except asyncio.TimeoutError:
                    print(f"GPT4o 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                    raise APITimeoutError("GPT4o 流式块生成超时!")

        try:
            for _, step in enumerate(chain.steps):
                if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                    # 使用 astream 方法实现流式输出，并为每个块设置超时
                    async for chunk in stream_with_timeout(step, chain_input):
                        content = chunk.content
                        if content is None:
                            print("GPT4o返回内容为空")
                            continue
                        response_data['model'] = "GPT4"
                        response_data['content'] = content
                        if chat_content[username]["gpt4"] == "":
                            print(f"GPT4o 响应时间: {time.time() - start_time}秒")
                        chat_content[username]["gpt4"] += content
                        yield json.dumps(response_data, ensure_ascii=False)
                        # 为每个流式块设置超时
                        # yield await asyncio.wait_for(json.dumps(response_data, ensure_ascii=False), timeout=60)  # 超时时间为60秒
                else:
                    # 非流式步骤，直接调用 invoke
                    chain_input = step.invoke(chain_input)
                    # yield chain_input  # 返回非流式步骤的输出
        except Exception as e:
            print(f"GPT4o出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
            error_traceback = traceback.format_exc()  # 获取完整的错误栈信息
            print(f"错误详情: \n{error_traceback}")  # 打印完整栈信息
            if time.time() - start_time > time_out and chat_content[username]["gpt4"] == "":
                print(f"GPT4o API调用超时, 超时时间: {time.time() - start_time}秒")
            content = "GPT4o出错，参考文档内容偏多，或服务器繁忙！"
            chat_content[username]["gpt4"] = content
            response_data['model'] = "GPT4"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)


def gpt_stream_generator_sync(data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        generator = gpt_stream_generator(data)
        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def gemini_stream_generator(data):
    constructed_data = construct_data(data)
    response_data = constructed_data["response_data"]
    username = constructed_data["user_name"]
    now_turn_message = constructed_data["message"]
    # has_double_question_marks = bool(re.search(r'(?<!\?)\?\?(?!\?)', now_turn_message) or
    #                                  re.search(r'(?<!？)？？(?!？)', now_turn_message))
    # has_consecutive_question_marks = ("???" in now_turn_message) or ("？？？" in now_turn_message)
    markers = detect_special_markers(now_turn_message)
    has_double_question_marks = markers['has_double_question_marks']
    has_consecutive_question_marks = markers['has_triple_question_marks']
    global chat_content, chat_with_files_params
    chat_content[username]["Gemini"] = ""
    if not constructed_data["file_list"]:
        try:
            client = OpenAI(
                api_key=os.environ.get("NKCN_LLM_API_KEY", ""),
                base_url='https://chat.cloudapi.vip/v1/',
                default_headers={"x-foo": "true"},
            )
            print("Gemini不勾选文件，发送消息: ", constructed_data["questionGemini"])
            useSystemPrompt = "当前的场景阶段提示：\n" + global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"][
                "qa"]
            if has_consecutive_question_marks:
                useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
            if has_double_question_marks:
                base_prompt = QS_QQ_base
                # 根据加号数量调整提示
                if markers['plus_count'] == 1:
                    useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                elif markers['plus_count'] == 2:
                    useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                elif markers['plus_count'] == 3:
                    useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                else:
                    useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"

            messages = []
            if constructed_data["info_list"]:
                constructed_data["info_list"].insert(0, {
                    "type": "text",
                    "text": constructed_data["questionGemini"]
                })
                messages = [
                    {"role": "system", "content": useSystemPrompt},
                    {"role": "user", "content": constructed_data["info_list"]}
                ]
            else:
                messages = [
                    {"role": "system", "content": useSystemPrompt},
                    {"role": "user", "content": constructed_data["questionGemini"]}
                ]
            start_time = time.time()
            response = await asyncio.wait_for(
                to_thread(  # 将同步调用转为异步任务
                    client.chat.completions.create,
                    model='gemini-2.5-pro-exp-03-25',
                    messages=messages,
                    temperature=global_var.config["temperature"],
                    top_p=global_var.config["top_p"],
                    frequency_penalty=global_var.config["frequency_penalty"],
                    presence_penalty=global_var.config["presence_penalty"],
                    max_tokens=global_var.config["max_tokens"],
                    n=global_var.config["n"],
                    stream=True,
                    timeout=time_out,  # 原生超时参数（可选）
                ),
                timeout=time_out  # 自定义超时时间（优先级更高）
            )
            print(f"Gemini 响应创建用时: {time.time() - start_time}秒")
            start_time = time.time()
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content is None:
                    continue
                response_data['model'] = "Gemini"
                response_data['content'] = content
                if chat_content[username]["Gemini"] == "":
                    print(f"Gemini 响应时间: {time.time() - start_time}秒")
                chat_content[username]["Gemini"] += content
                yield json.dumps(response_data, ensure_ascii=False)
            # return response
        except Exception as e:
            print(f"Gemini API error: {e}")
            if time.time() - start_time > time_out and chat_content[username]["Gemini"] == "":
                print(f"Gemini API调用超时, 超时时间: {time.time() - start_time}秒")
            content = "Gemini API调用出错"
            chat_content[username]["Gemini"] = content
            response_data['model'] = "Gemini"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)
    else:
        constructed_params = chat_with_files_params[username]
        print("Gemini勾选文件，发送消息: ", constructed_params["questionGemini"])
        useSystemPrompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
        if has_consecutive_question_marks:
            useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
        if has_double_question_marks:
            base_prompt = QS_QQ_base
            # 根据加号数量调整提示
            if markers['plus_count'] == 1:
                useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
            elif markers['plus_count'] == 2:
                useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
            elif markers['plus_count'] == 3:
                useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
            else:
                useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
        chain_input = {
            # "text": constructed_params["text"],
            "question": constructed_params["questionGemini"],
            "images_store": constructed_params["images_store"],
            "qa_prompt": useSystemPrompt
        }
        chain = normal_qa.qa_chain[7]
        start_time = time.time()

        async def stream_with_timeout(step, chain_input):
            # 获取异步生成器
            async_stream = step.astream(chain_input, **global_var.config)
            print("cnm444--------------------------------------------")
            while True:
                try:
                    # 为每个块的生成设置超时
                    chunk = await asyncio.wait_for(
                        async_stream.__anext__(),  # 等待下一个异步块
                        timeout=time_out,
                    )
                    yield chunk
                except StopAsyncIteration:
                    print("cnm555--------------------------------------------")
                    break  # 流式结束
                except asyncio.TimeoutError:
                    print(f"Gemini 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                    raise APITimeoutError("Gemini 流式块生成超时!")

        try:
            print("cnm111--------------------------------------------")
            for _, step in enumerate(chain.steps):
                if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                    # 使用 astream 方法实现流式输出，并为每个块设置超时
                    print("cnm222--------------------------------------------")
                    async for chunk in stream_with_timeout(step, chain_input):
                        content = chunk.content
                        print("cnm333--------------------------------------------")
                        if content is None:
                            print("Gemini返回内容为空")
                            continue
                        response_data['model'] = "Gemini"
                        response_data['content'] = content
                        if chat_content[username]["Gemini"] == "":
                            print(f"Gemini 响应时间: {time.time() - start_time}秒")
                        chat_content[username]["Gemini"] += content
                        yield json.dumps(response_data, ensure_ascii=False)
                        # 为每个流式块设置超时
                        # yield await asyncio.wait_for(json.dumps(response_data, ensure_ascii=False), timeout=60)  # 超时时间为60秒
                else:
                    # 非流式步骤，直接调用 invoke
                    chain_input = step.invoke(chain_input)
                    # yield chain_input  # 返回非流式步骤的输出
        except Exception as e:
            print(f"Gemini出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
            if time.time() - start_time > time_out and chat_content[username]["Gemini"] == "":
                print(f"Gemini API调用超时, 超时时间: {time.time() - start_time}秒")
            content = "Gemini出错，参考文档内容偏多，或服务器繁忙！"
            chat_content[username]["Gemini"] = content
            response_data['model'] = "Gemini"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)


def gemini_stream_generator_sync(data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        generator = gemini_stream_generator(data)
        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def claude_stream_generator(data):
    constructed_data = construct_data(data)
    response_data = constructed_data["response_data"]
    username = constructed_data["user_name"]
    now_turn_message = constructed_data["message"]

    markers = detect_special_markers(now_turn_message)
    has_double_question_marks = markers['has_double_question_marks']
    has_consecutive_question_marks = markers['has_triple_question_marks']

    global chat_content, chat_with_files_params
    chat_content[username]["claude"] = ""
    if not constructed_data["file_list"]:
        try:
            client = OpenAI(
                api_key=os.environ.get("NKCN_LLM_API_KEY", ""),
                base_url='https://chat.cloudapi.vip/v1/',
                default_headers={"x-foo": "true"}
            )
            print("Claude3.5不勾选文件，发送消息: ", constructed_data["questionClaude"])
            useSystemPrompt = constructed_data[
                                  "system_prompt_claudeUse"] + "\n请你按照如上人性化思考协议的要求，思考并完成任务\n\n当前的场景阶段提示：\n" + \
                              global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
            if has_consecutive_question_marks:
                useSystemPrompt = constructed_data[
                                      "system_prompt_claudeUse"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
            if has_double_question_marks:
                base_prompt = QS_QQ_base
                # 根据加号数量调整提示
                if markers['plus_count'] == 1:
                    useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                elif markers['plus_count'] == 2:
                    useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                elif markers['plus_count'] == 3:
                    useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                else:
                    useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
            messages = []
            if constructed_data["info_list_claude"]:
                constructed_data["info_list_claude"].insert(0, {
                    "type": "text",
                    "text": "你需要自然地运用前面给你的人性化思考协议（形式如```thinking xxx``` ```checking xxx``` "
                            "汇总的最终回应），先Thinking，再checking（视情况做一或两轮），最后给出汇总的完整思考报告来回答：\n" +
                            constructed_data["questionClaude"]
                })
                messages = [
                    {"role": "system", "content": useSystemPrompt},
                    {"role": "user", "content": constructed_data["info_list_claude"]}
                ]
            else:
                messages = [
                    {"role": "system", "content": useSystemPrompt},
                    {"role": "user", "content": "你需要自然地运用前面给你的人性化思考协议（形式如```thinking xxx``` ```checking xxx``` "
                                                "汇总的最终回应），先Thinking，再checking（视情况做一或两轮），最后给出汇总的完整思考报告来回答：\n" +
                                                constructed_data["questionClaude"]}
                ]
            start_time = time.time()
            response = await asyncio.wait_for(
                to_thread(  # 将同步调用转为异步任务
                    client.chat.completions.create,
                    model="claude-sonnet-4-20250514",
                    max_tokens=global_var.claudeConfig["max_tokens"],
                    temperature=global_var.claudeConfig["temperature"],
                    messages=messages,
                    stream=True,  # FIXME yq: 现在暂时默认都开启流式输出
                    timeout=time_out,
                ),
                timeout=time_out  # 自定义超时时间（优先级更高）
            )
            print(f"Claude3.5 响应创建用时: {time.time() - start_time}秒")
            start_time = time.time()
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content is None:
                    continue
                response_data['model'] = "Claude3.5"
                response_data['content'] = content
                if chat_content[username]["claude"] == "":
                    print(f"Claude3.5 响应时间: {time.time() - start_time}秒")
                chat_content[username]["claude"] += content
                yield json.dumps(response_data, ensure_ascii=False)
        except Exception as e:
            print(f"Claude3.5 API error: {e}")
            if time.time() - start_time > time_out and chat_content[username]["claude"] == '':
                print(f"Claude3.5 API调用超时, 超时时间: {time.time() - start_time}秒")
            # retry
            try:
                useSystemPrompt = constructed_data[
                                      "system_prompt_claudeUse"] + "\n请你按照如上人性化思考协议的要求，思考并完成任务\n\n当前的场景阶段提示：\n" + \
                                  global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
                if has_consecutive_question_marks:
                    useSystemPrompt = constructed_data[
                                          "system_prompt_claudeUse"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
                if has_double_question_marks:
                    base_prompt = QS_QQ_base
                    # 根据加号数量调整提示
                    if markers['plus_count'] == 1:
                        useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                    elif markers['plus_count'] == 2:
                        useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                    elif markers['plus_count'] == 3:
                        useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                    else:
                        useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
                messages = []
                if constructed_data["info_list_claude"]:
                    constructed_data["info_list_claude"].insert(0, {
                        "type": "text",
                        "text": "你需要自然地运用前面给你的人性化思考协议（形式如```thinking xxx``` ```checking xxx``` "
                                "汇总的最终回应），先Thinking，再checking（视情况做一或两轮），最后给出汇总的完整思考报告来回答：\n" +
                                constructed_data["questionClaude"]
                    })
                    messages = [
                        {"role": "system", "content": useSystemPrompt},
                        {"role": "user", "content": constructed_data["info_list_claude"]}
                    ]
                else:
                    messages = [
                        {"role": "system", "content": useSystemPrompt},
                        {"role": "user", "content": "你需要自然地运用前面给你的人性化思考协议（形式如```thinking xxx``` ```checking xxx``` "
                                                    "汇总的最终回应），先Thinking，再checking（视情况做一或两轮），最后给出汇总的完整思考报告来回答：\n" +
                                                    constructed_data["questionClaude"]}
                    ]
                start_time = time.time()
                response = await asyncio.wait_for(
                    to_thread(  # 将同步调用转为异步任务
                        client.chat.completions.create,
                        model="claude-sonnet-4-20250514",
                        max_tokens=global_var.claudeConfig["max_tokens"],
                        temperature=global_var.claudeConfig["temperature"],
                        messages=messages,
                        stream=True,  # FIXME yq: 现在暂时默认都开启流式输出
                        timeout=time_out,
                    ),
                    timeout=time_out  # 自定义超时时间（优先级更高）
                )
                print(f"Claude3.5 响应创建用时: {time.time() - start_time}秒")
                start_time = time.time()
                for chunk in response:
                    content = chunk.choices[0].delta.content
                    if content is None:
                        continue
                    response_data['model'] = "Claude3.5"
                    response_data['content'] = content
                    if chat_content[username]["claude"] == "":
                        print(f"Claude3.5 响应时间: {time.time() - start_time}秒")
                    chat_content[username]["claude"] += content
                    yield json.dumps(response_data, ensure_ascii=False)
            except Exception as e:
                print(f"Claude3.5 API error: {e}")
                if time.time() - start_time > time_out and chat_content[username]["claude"] == '':
                    print(f"Claude3.5 API调用超时, 超时时间: {time.time() - start_time}秒")
                content = "Claude3.5 API调用出错"
                chat_content[username]["claude"] = content
                response_data['model'] = "Claude3.5"
                response_data['content'] = content
                yield json.dumps(response_data, ensure_ascii=False)
    else:
        constructed_params = chat_with_files_params[username]

        print("Claude3.5勾选文件，发送消息: ", constructed_params["questionClaude"])
        useSystemPrompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
        if has_consecutive_question_marks:
            useSystemPrompt = "当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
        if has_double_question_marks:
            base_prompt = QS_QQ_base
            # 根据加号数量调整提示
            if markers['plus_count'] == 1:
                useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
            elif markers['plus_count'] == 2:
                useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
            elif markers['plus_count'] == 3:
                useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
            else:
                useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
        chain_input = {
            # "text": constructed_params["text"],
            "question": constructed_params["questionClaude"],
            "images_store": constructed_params["images_store_claude"],
            "qa_prompt": useSystemPrompt
        }
        start_time = time.time()

        async def stream_with_timeout(step, chain_input):
            # 获取异步生成器
            async_stream = step.astream(chain_input, **global_var.claudeConfig)
            while True:
                try:
                    # 为每个块的生成设置超时
                    chunk = await asyncio.wait_for(
                        async_stream.__anext__(),  # 等待下一个异步块
                        timeout=time_out,
                    )
                    yield chunk
                except StopAsyncIteration:
                    break  # 流式结束
                except asyncio.TimeoutError:
                    print(f"Claude 3.5 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                    raise APITimeoutError("Claude 3.5 流式块生成超时!")

        chain = normal_qa.qa_chain[4]
        try:
            for _, step in enumerate(chain.steps):
                if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                    async for chunk in stream_with_timeout(step, chain_input):
                        content = chunk.content
                        if content is None:
                            print("Claude3.5返回内容为空")
                            continue
                        response_data['model'] = "Claude3.5"
                        response_data['content'] = content
                        if chat_content[username]["claude"] == "":
                            print(f"Claude3.5 响应时间: {time.time() - start_time}秒")
                        chat_content[username]["claude"] += content
                        yield json.dumps(response_data, ensure_ascii=False)
                    if chat_content[username]["claude"] == "":
                        content = "Claude3.5 API调用出错"
                        chat_content[username]["claude"] = content
                        response_data['model'] = "Claude3.5"
                        response_data['content'] = content
                        yield json.dumps(response_data, ensure_ascii=False)
                else:
                    # 非流式步骤，直接调用 invoke
                    chain_input = step.invoke(chain_input)
                    # yield chain_input  # 返回非流式步骤的输出
        except Exception as e:
            print(f"Claude3.5出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
            if time.time() - start_time > time_out and chat_content[username]["claude"] == "":
                print(f"Claude3.5 API调用超时, 超时时间: {time.time() - start_time}秒")
            # retry
            chain_input = {
                # "text": constructed_params["text"],
                "question": constructed_params["questionClaude"],
                "images_store": constructed_params["images_store_claude"],
                "qa_prompt": useSystemPrompt
            }
            chain = normal_qa.qa_chain[4]
            try:
                for _, step in enumerate(chain.steps):
                    start_time = time.time()
                    if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                        async for chunk in stream_with_timeout(step, chain_input):
                            content = chunk.content
                            if content is None:
                                print("Claude3.5返回内容为空")
                                continue
                            response_data['model'] = "Claude3.5"
                            response_data['content'] = content
                            if chat_content[username]["claude"] == "":
                                print(f"Claude3.5 响应时间: {time.time() - start_time}秒")
                            chat_content[username]["claude"] += content
                            yield json.dumps(response_data, ensure_ascii=False)
                        if chat_content[username]["claude"] == "":
                            content = "Claude3.5 API调用出错"
                            chat_content[username]["claude"] = content
                            response_data['model'] = "Claude3.5"
                            response_data['content'] = content
                            yield json.dumps(response_data, ensure_ascii=False)
                    else:
                        # 非流式步骤，直接调用 invoke
                        chain_input = step.invoke(chain_input)
                        # yield chain_input  # 返回非流式步骤的输出
            except Exception as e:
                print(f"Claude3.5出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
                if time.time() - start_time > time_out and chat_content[username]["claude"] == "":
                    print(f"Claude3.5 API调用超时, 超时时间: {time.time() - start_time}秒")
                content = "Claude3.5出错，参考文档内容偏多，或服务器繁忙！"
                chat_content[username]["claude"] = content
                response_data['model'] = "Claude3.5"
                response_data['content'] = content
                yield json.dumps(response_data, ensure_ascii=False)


def claude_stream_generator_sync(data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        generator = claude_stream_generator(data)
        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def deepseek_stream_generator(data):
    constructed_data = construct_data(data)
    response_data = constructed_data["response_data"]
    username = constructed_data["user_name"]
    now_turn_message = constructed_data["message"]

    markers = detect_special_markers(now_turn_message)
    has_double_question_marks = markers['has_double_question_marks']
    has_consecutive_question_marks = markers['has_triple_question_marks']

    global chat_content, chat_with_files_params
    chat_content[username]["deepseek"] = ""
    if not constructed_data["file_list"]:
        try:
            API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
            if constructed_data["system_prompt_claudeUse"] != "":
                role = system_prompt_deepseek  # thinking的简化版
                role = role + "\n当前的场景阶段提示：\n" + global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"][
                    "qa"]
                if has_consecutive_question_marks:
                    role = system_prompt_deepseek + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
                if has_double_question_marks:
                    base_prompt = QS_QQ_base
                    # 根据加号数量调整提示
                    if markers['plus_count'] == 1:
                        role += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                    elif markers['plus_count'] == 2:
                        role += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                    elif markers['plus_count'] == 3:
                        role += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                    else:
                        role += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
            else:
                role = """You are an advanced AI assistant providing accurate and professional responses across 
                                        technical, research, content creation, and general knowledge domains. 

                                        KEY PRINCIPLES:
                                        - Ensure accuracy and completeness
                                        - Provide structured explanations with examples
                                        - Consider multiple solutions and trade-offs
                                        - Use clear language and systematic approach
                                        - Validate practical applicability

                                        DEFAULTS:
                                        - Respond in Chinese unless otherwise specified
                                        - Tailor to user context and requirements
                                        - Include step-by-step explanations when needed"""

            client = AsyncOpenAI(
                api_key=API_KEY,
                base_url="https://api.deepseek.com",
            )
            print("Deepseek不勾选文件，发送消息: ", constructed_data["questionDeepseek"])
            start_time = time.time()
            response = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": role},
                    {"role": "user", "content": "你需要自然地运用前面给你的人性化思考协议（形式如```thinking xxx``` ```checking xxx``` "
                                                "汇总的最终回应），先Thinking，再checking（视情况做一或两轮），最后给出汇总的完整思考报告来回答：\n" +
                                                constructed_data["questionDeepseek"]},
                ],
                temperature=global_var.deepseekConfig["temperature"],
                top_p=global_var.deepseekConfig["top_p"],
                frequency_penalty=global_var.deepseekConfig["frequency_penalty"],
                presence_penalty=global_var.deepseekConfig["presence_penalty"],
                max_tokens=global_var.deepseekConfig["max_tokens"],
                stream=True,  # FIXME yq: 现在暂时默认都开启流式输出
                timeout=time_out,
            )
            print(f"Deepseek 响应创建用时: {time.time() - start_time}秒")
            start_time = time.time()

            async def response_with_timeout(response):
                while True:
                    try:
                        # 为每个块的生成设置超时
                        chunk = await asyncio.wait_for(
                            response.__anext__(),  # 等待下一个异步块
                            timeout=time_out,
                        )
                        yield chunk
                    except StopAsyncIteration:
                        break  # 流式结束
                    except asyncio.TimeoutError:
                        print(f"Deepseek 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                        raise APITimeoutError("Deepseek 流式块生成超时!")

            async for chunk in response_with_timeout(response):
                content = chunk.choices[0].delta.content
                if content is None:
                    print("Deepseek返回内容为空")
                    continue
                response_data['model'] = "Deepseek"
                response_data['content'] = content
                if chat_content[username]["deepseek"] == "":
                    print(f"Deepseek 响应时间: {time.time() - start_time}秒")
                chat_content[username]["deepseek"] += content
                yield json.dumps(response_data, ensure_ascii=False)
            # return response
        except Exception as e:
            print(f"Deepseek API error: {e}")
            if time.time() - start_time > time_out and chat_content[username]["deepseek"] == "":
                print(f"Deepseek API调用超时, 超时时间: {time.time() - start_time}秒")
            content = "Deepseek API调用出错"
            chat_content[username]["deepseek"] = content
            response_data['model'] = "Deepseek"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)
    else:
        constructed_params = chat_with_files_params[username]

        print("Deepseek勾选文件，发送消息: ", constructed_params["questionDeepseek"])
        useSystemPrompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
        if has_consecutive_question_marks:
            useSystemPrompt = "当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
        if has_double_question_marks:
            base_prompt = QS_QQ_base
            # 根据加号数量调整提示
            if markers['plus_count'] == 1:
                useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
            elif markers['plus_count'] == 2:
                useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
            elif markers['plus_count'] == 3:
                useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
            else:
                useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
        chain_input = {
            "text": constructed_params["text"],
            "question": constructed_params["questionDeepseek"],
            "images_store": [],
            "qa_prompt": useSystemPrompt
        }
        start_time = time.time()

        async def stream_with_timeout(step, chain_input):
            # 获取异步生成器
            async_stream = step.astream(chain_input, **global_var.deepseekConfig)
            while True:
                try:
                    # 为每个块的生成设置超时
                    chunk = await asyncio.wait_for(
                        async_stream.__anext__(),  # 等待下一个异步块
                        timeout=time_out,
                    )
                    yield chunk
                except StopAsyncIteration:
                    break  # 流式结束
                except asyncio.TimeoutError:
                    print(f"Deepseek 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                    raise APITimeoutError("Deepseek 流式块生成超时!")

        chain = normal_qa.qa_chain[5]
        try:
            for _, step in enumerate(chain.steps):
                if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                    async for chunk in stream_with_timeout(step, chain_input):
                        content = chunk.content
                        if content is None:
                            print("Deepseek返回内容为空")
                            continue
                        response_data['model'] = "Deepseek"
                        response_data['content'] = content
                        if chat_content[username]["deepseek"] == "":
                            print(f"Deepseek 响应时间: {time.time() - start_time}秒")
                        chat_content[username]["deepseek"] += content
                        yield json.dumps(response_data, ensure_ascii=False)
                        # 为每个流式块设置超时
                        # yield await asyncio.wait_for(json.dumps(response_data, ensure_ascii=False), timeout=60)  # 超时时间为60秒
                else:
                    # 非流式步骤，直接调用 invoke
                    chain_input = step.invoke(chain_input)
                    # yield chain_input  # 返回非流式步骤的输出
        except Exception as e:
            print(f"Deepseek出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
            if time.time() - start_time > time_out and chat_content[username]["deepseek"] == "":
                print(f"Deepseek API调用超时, 超时时间: {time.time() - start_time}秒")
            content = "Deepseek出错，参考文档内容偏多，或服务器繁忙！"
            chat_content[username]["deepseek"] = content
            response_data['model'] = "Deepseek"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)


def deepseek_stream_generator_sync(data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        generator = deepseek_stream_generator(data)
        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def llama_stream_generator(data):
    constructed_data = construct_data(data)
    response_data = constructed_data["response_data"]
    username = constructed_data["user_name"]
    now_turn_message = constructed_data["message"]

    markers = detect_special_markers(now_turn_message)
    has_double_question_marks = markers['has_double_question_marks']
    has_consecutive_question_marks = markers['has_triple_question_marks']

    global chat_content, chat_with_files_params
    chat_content[username]["llama"] = ""
    if not constructed_data["file_list"]:
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.environ.get("NVIDIA_API_KEY", "")
        )
        try:
            print("Llama3不勾选文件，发送消息: ", constructed_data["questionLlama"])
            useSystemPrompt = "当前的场景阶段提示：\n" + global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"][
                "qa"]
            if has_consecutive_question_marks:
                useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
            if has_double_question_marks:
                base_prompt = QS_QQ_base
                # 根据加号数量调整提示
                if markers['plus_count'] == 1:
                    useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                elif markers['plus_count'] == 2:
                    useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                elif markers['plus_count'] == 3:
                    useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                else:
                    useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
            start_time = time.time()
            response = await asyncio.wait_for(
                to_thread(  # 将同步调用转为异步任务
                    client.chat.completions.create,
                    model="meta/llama-3.1-405b-instruct",
                    messages=[
                        {"role": "system", "content": useSystemPrompt},
                        {"role": "user", "content": constructed_data["questionLlama"]},
                    ],
                    temperature=global_var.llama3Config["temperature"],
                    top_p=global_var.llama3Config["top_p"],
                    frequency_penalty=global_var.llama3Config["frequency_penalty"],
                    presence_penalty=global_var.llama3Config["presence_penalty"],
                    max_tokens=global_var.llama3Config["max_tokens"],
                    stream=True,  # FIXME yq: 现在暂时默认都开启流式输出
                    timeout=time_out,
                ),
                timeout=time_out  # 自定义超时时间（优先级更高）
            )
            print(f"Llama 响应创建时间: {time.time() - start_time}")
            start_time = time.time()
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content is None:
                    continue
                response_data['model'] = "Llama3"
                response_data['content'] = content
                if chat_content[username]["llama"] == '':
                    print(f"Llama 响应时间: {time.time() - start_time}")
                chat_content[username]["llama"] += content
                yield json.dumps(response_data, ensure_ascii=False)
        except Exception as e:
            print(f"Llama3 API error: {e}")
            content = "Llama3 API调用出错"
            chat_content[username]["llama"] = content
            response_data['model'] = "Llama3"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)
    else:
        constructed_params = chat_with_files_params[username]

        print("Llama3勾选文件，发送消息: ", constructed_params["questionLlama"])
        useSystemPrompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
        if has_consecutive_question_marks:
            useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
        if has_double_question_marks:
            base_prompt = QS_QQ_base
            # 根据加号数量调整提示
            if markers['plus_count'] == 1:
                useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
            elif markers['plus_count'] == 2:
                useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
            elif markers['plus_count'] == 3:
                useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
            else:
                useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
        chain_input = {
            "text": constructed_params["text"],
            "question": constructed_params["questionLlama"],
            "qa_prompt": useSystemPrompt
        }
        start_time = time.time()

        async def stream_with_timeout(step, chain_input):
            # 获取异步生成器
            async_stream = step._astream(chain_input, **global_var.llama3Config)
            while True:
                try:
                    # 为每个块的生成设置超时
                    chunk = await asyncio.wait_for(
                        async_stream.__anext__(),  # 等待下一个异步块
                        timeout=time_out,
                    )
                    yield chunk
                except StopAsyncIteration:
                    break  # 流式结束
                except asyncio.TimeoutError:
                    print(f"Llama3 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                    raise APITimeoutError("Llama3 流式块生成超时!")

        chain = normal_qa.qa_chain[2]
        try:
            for _, step in enumerate(chain.steps):
                # if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                start_time = time.time()
                if isinstance(step, ChatLlamaAPI):
                    print("llama3 stream")
                    # 使用 astream 方法实现流式输出，并为每个块设置超时
                    async for chunk in stream_with_timeout(step, chain_input):
                        content = chunk.choices[0].delta.content
                        if content is None:
                            continue
                        response_data['model'] = "Llama3"
                        response_data['content'] = content
                        if chat_content[username]["llama"] == "":
                            print(f"Llama3 响应时间: {time.time() - start_time}")
                        chat_content[username]["llama"] += content
                        yield json.dumps(response_data, ensure_ascii=False)
                        # 为每个流式块设置超时
                        # yield await asyncio.wait_for(json.dumps(response_data, ensure_ascii=False), timeout=60)  # 超时时间为60秒
                else:
                    # 非流式步骤，直接调用 invoke
                    print("llama3 invoke")
                    chain_input = step.invoke(chain_input)
                    # yield chain_input  # 返回非流式步骤的输出
        except Exception as e:
            print(f"Llama3出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
            content = "Llama3出错，参考文档内容偏多，或服务器繁忙！"
            chat_content[username]["llama"] = content
            response_data['model'] = "Llama3"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)


def llama_stream_generator_sync(data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        generator = llama_stream_generator(data)
        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def kimi_stream_generator(data):
    constructed_data = construct_data(data)
    response_data = constructed_data["response_data"]
    username = constructed_data["user_name"]
    now_turn_message = constructed_data["message"]

    markers = detect_special_markers(now_turn_message)
    has_double_question_marks = markers['has_double_question_marks']
    has_consecutive_question_marks = markers['has_triple_question_marks']

    global chat_content, chat_with_files_params
    chat_content[username]["kimi"] = ""
    if not constructed_data["file_list"]:
        try:
            client = OpenAI(
                api_key=os.environ.get("KIMI_API_KEY", ""),
                base_url="https://api.moonshot.cn/v1",
                default_headers={"x-foo": "true"},
            )
            print("Kimi不勾选文件，发送消息: ", constructed_data["questionKimi"])
            useSystemPrompt = "当前的场景阶段提示：\n" + global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"][
                "qa"]
            if has_consecutive_question_marks:
                useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
            if has_double_question_marks:
                base_prompt = QS_QQ_base
                # 根据加号数量调整提示
                if markers['plus_count'] == 1:
                    useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                elif markers['plus_count'] == 2:
                    useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                elif markers['plus_count'] == 3:
                    useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                else:
                    useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
            start_time = time.time()
            response = await asyncio.wait_for(
                to_thread(  # 将同步调用转为异步任务
                    client.chat.completions.create,
                    model='moonshot-v1-32k',
                    messages=[
                        {"role": "system", "content": useSystemPrompt},
                        {"role": "user", "content": constructed_data["questionKimi"]},
                    ],
                    temperature=global_var.kimiConfig["temperature"],
                    top_p=global_var.kimiConfig["top_p"],
                    frequency_penalty=global_var.kimiConfig["frequency_penalty"],
                    presence_penalty=global_var.kimiConfig["presence_penalty"],
                    max_tokens=global_var.kimiConfig["max_tokens"],
                    n=global_var.kimiConfig["n"],
                    stream=True,  # FIXME yq: 现在暂时默认都开启流式输出
                    timeout=time_out,
                ),
                timeout=time_out  # 自定义超时时间（优先级更高）
            )
            print(f"Kimi 响应创建时间: {time.time() - start_time}")
            start_time = time.time()
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content is None:
                    continue
                response_data['model'] = "Kimi"
                response_data['content'] = content
                if chat_content[username]["kimi"] == "":
                    print(f"Kimi 响应时间: {time.time() - start_time}")
                chat_content[username]["kimi"] += content
                yield json.dumps(response_data, ensure_ascii=False)
            # return response
        except Exception as e:
            print(f"Kimi API error: {e}")
            content = "Kimi API调用出错"
            chat_content[username]["kimi"] = content
            response_data['model'] = "Kimi"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)
    else:
        constructed_params = chat_with_files_params[username]

        print("Kimi勾选文件，发送消息: ", constructed_params["questionKimi"])
        useSystemPrompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
        if has_consecutive_question_marks:
            useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
        if has_double_question_marks:
            base_prompt = QS_QQ_base
            # 根据加号数量调整提示
            if markers['plus_count'] == 1:
                useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
            elif markers['plus_count'] == 2:
                useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
            elif markers['plus_count'] == 3:
                useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
            else:
                useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
        chain_input = {
            "text": constructed_params["text"],
            "question": constructed_params["questionKimi"],
            "images_store": [],
            "qa_prompt": useSystemPrompt
        }
        start_time = time.time()

        async def stream_with_timeout(step, chain_input):
            # 获取异步生成器
            async_stream = step.astream(chain_input, **global_var.kimiConfig)
            while True:
                try:
                    # 为每个块的生成设置超时
                    chunk = await asyncio.wait_for(
                        async_stream.__anext__(),  # 等待下一个异步块
                        timeout=time_out,
                    )
                    yield chunk
                except StopAsyncIteration:
                    break  # 流式结束
                except asyncio.TimeoutError:
                    print(f"Kimi 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                    raise APITimeoutError("Kimi 流式块生成超时!")

        chain = normal_qa.qa_chain[3]
        try:
            for _, step in enumerate(chain.steps):
                if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                    # 使用 astream 方法实现流式输出，并为每个块设置超时
                    async for chunk in stream_with_timeout(step, chain_input):
                        content = chunk.content
                        if content is None:
                            continue
                        response_data['model'] = "Kimi"
                        response_data['content'] = content
                        chat_content[username]["kimi"] += content
                        yield json.dumps(response_data, ensure_ascii=False)
                        # 为每个流式块设置超时
                        # yield await asyncio.wait_for(json.dumps(response_data, ensure_ascii=False), timeout=60)  # 超时时间为60秒
                else:
                    # 非流式步骤，直接调用 invoke
                    chain_input = step.invoke(chain_input)
                    # yield chain_input  # 返回非流式步骤的输出
        except Exception as e:
            print(f"Kimi出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
            if time.time() - start_time > time_out and chat_content[username]["kimi"] == "":
                print(f"Kimi API调用超时, 超时时间: {time.time() - start_time}秒")
            content = "Kimi出错，参考文档内容偏多，或服务器繁忙！"
            chat_content[username]["kimi"] = content
            response_data['model'] = "Kimi"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)


def kimi_stream_generator_sync(data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        generator = kimi_stream_generator(data)
        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def dsreasoner_stream_generator(data):
    constructed_data = construct_data(data)
    response_data = constructed_data["response_data"]
    username = constructed_data["user_name"]
    now_turn_message = constructed_data["message"]

    markers = detect_special_markers(now_turn_message)
    has_double_question_marks = markers['has_double_question_marks']
    has_consecutive_question_marks = markers['has_triple_question_marks']

    global chat_content, chat_with_files_params
    print("Dsreasoner time_out", time_out)
    chat_content[username]["dsreasoner"] = ""
    if not constructed_data["file_list"]:
        try:
            # API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
            API_KEY_ALI = os.environ.get("DASHSCOPE_API_KEY", "")

            if constructed_data["system_prompt"] != "":
                role = "当前的场景阶段提示：\n" + global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
                if has_consecutive_question_marks:
                    role = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
                if has_double_question_marks:
                    base_prompt = QS_QQ_base
                    # 根据加号数量调整提示
                    if markers['plus_count'] == 1:
                        role += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                    elif markers['plus_count'] == 2:
                        role += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                    elif markers['plus_count'] == 3:
                        role += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                    else:
                        role += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
            else:
                role = """You are an advanced AI assistant providing accurate and professional responses across 
                                        technical, research, content creation, and general knowledge domains. 

                                        KEY PRINCIPLES:
                                        - Ensure accuracy and completeness
                                        - Provide structured explanations with examples
                                        - Consider multiple solutions and trade-offs
                                        - Use clear language and systematic approach
                                        - Validate practical applicability

                                        DEFAULTS:
                                        - Respond in Chinese unless otherwise specified
                                        - Tailor to user context and requirements
                                        - Include step-by-step explanations when needed"""

            client = AsyncOpenAI(
                api_key=API_KEY_ALI,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # "https://api.deepseek.com",
            )
            print("Dsreasoner不勾选文件，发送消息: ", constructed_data["questionDsreasoner"])
            start_time = time.time()
            response = await client.chat.completions.create(
                model="deepseek-r1",  # "deepseek-reasoner",
                messages=[
                    {"role": "system", "content": role},
                    {"role": "user", "content": constructed_data["questionDsreasoner"]},
                ],
                temperature=global_var.deepseekConfig["temperature"],
                top_p=global_var.deepseekConfig["top_p"],
                frequency_penalty=global_var.deepseekConfig["frequency_penalty"],
                presence_penalty=global_var.deepseekConfig["presence_penalty"],
                max_tokens=global_var.deepseekConfig["max_tokens"],
                stream=True,  # FIXME yq: 现在暂时默认都开启流式输出
                timeout=time_out,
            )
            print(f"Dsreasoner 响应创建时间: {time.time() - start_time}")
            start_time = time.time()

            async def response_with_timeout(response):
                while True:
                    try:
                        # 为每个块的生成设置超时
                        chunk = await asyncio.wait_for(
                            response.__anext__(),  # 等待下一个异步块
                            timeout=time_out,
                        )
                        yield chunk
                    except StopAsyncIteration:
                        break  # 流式结束
                    except asyncio.TimeoutError:
                        print(f"Dsreasoner 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                        raise APITimeoutError("Dsreasoner 流式块生成超时!")

            reasoning_stop = False
            async for chunk in response_with_timeout(response):
                reasoning_content = chunk.choices[0].delta.reasoning_content
                content = chunk.choices[0].delta.content
                if reasoning_content is not None:
                    reasoning_stop = False
                    if chat_content[username]["dsreasoner"] == "":
                        print(f"Dsreasoner 响应时间: {time.time() - start_time}")
                        result = "```" + reasoning_content
                    else:
                        result = reasoning_content
                elif content is not None:
                    if reasoning_stop:
                        result = content
                    else:
                        result = "```" + content
                    reasoning_stop = True
                else:
                    # print('Dsreasoner 返回内容为空')
                    continue
                response_data['model'] = "Dsreasoner"
                response_data['content'] = result
                chat_content[username]["dsreasoner"] += result
                yield json.dumps(response_data, ensure_ascii=False)
        except Exception as e:
            print(f"Dsreasoner API error: {e}")
            if time.time() - start_time > time_out and chat_content[username]["dsreasoner"] == "":
                print(f"Dsreasoner API调用超时, 超时时间: {time.time() - start_time}秒")
            content = "Dsreasoner API调用出错"
            chat_content[username]["dsreasoner"] = content
            response_data['model'] = "Dsreasoner"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)
    else:
        constructed_params = chat_with_files_params[username]
        print("Dsreasoner勾选文件，发送消息: ", constructed_params["questionDsreasoner"])
        useSystemPrompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
        if has_consecutive_question_marks:
            useSystemPrompt = "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
        if has_double_question_marks:
            base_prompt = QS_QQ_base
            # 根据加号数量调整提示
            if markers['plus_count'] == 1:
                useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
            elif markers['plus_count'] == 2:
                useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
            elif markers['plus_count'] == 3:
                useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
            else:
                useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
        chain_input = {
            "text": constructed_params["text"],
            "question": constructed_params["questionDsreasoner"],
            "images_store": [],
            "qa_prompt": useSystemPrompt
        }
        start_time = time.time()

        async def stream_with_timeout(step, chain_input):
            # 获取异步生成器
            async_stream = step._astream(chain_input, **global_var.deepseekConfig)
            while True:
                try:
                    # 为每个块的生成设置超时
                    chunk = await asyncio.wait_for(
                        async_stream.__anext__(),  # 等待下一个异步块
                        timeout=time_out,
                    )
                    yield chunk
                except StopAsyncIteration:
                    break  # 流式结束
                except asyncio.TimeoutError:
                    print(f"Dsreasoner 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                    raise APITimeoutError("Dsreasoner 流式块生成超时!")

        chain = normal_qa.qa_chain[6]
        try:
            for _, step in enumerate(chain.steps):
                if isinstance(step, ChatLlamaAPI):
                    print("ds stream")
                    # 使用 astream 方法实现流式输出，并为每个块设置超时
                    reasoning_stop = False
                    async for chunk in stream_with_timeout(step, chain_input):
                        if time.time() - start_time > time_out and chat_content[username]["dsreasoner"] == "":
                            print(f"dsreasoner API调用超时, 超时时间: {time.time() - start_time}秒")
                            raise APITimeoutError("dsreasoner API调用超时")
                        reasoning_content = chunk.choices[0].delta.reasoning_content
                        content = chunk.choices[0].delta.content
                        if reasoning_content is not None:
                            reasoning_stop = False
                            if chat_content[username]["dsreasoner"] == "":
                                print(f"Dsreasoner 响应时间: {time.time() - start_time}")
                                result = "```" + reasoning_content
                            else:
                                result = reasoning_content
                        elif content is not None:
                            if reasoning_stop:
                                result = content
                            else:
                                result = "```" + content
                            reasoning_stop = True
                        else:
                            # print('Dsreasoner 返回内容为空')
                            continue
                        response_data['model'] = "Dsreasoner"
                        response_data['content'] = result
                        chat_content[username]["dsreasoner"] += result
                        yield json.dumps(response_data, ensure_ascii=False)
                        # 为每个流式块设置超时
                        # yield await asyncio.wait_for(json.dumps(response_data, ensure_ascii=False), timeout=60)  # 超时时间为60秒
                else:
                    # 非流式步骤，直接调用 invoke
                    print("dsreasoner invoke")
                    chain_input = step.invoke(chain_input)
                    # yield chain_input  # 返回非流式步骤的输出
        except Exception as e:
            print(f"Dsreasoner出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
            content = "Dsreasoner出错，参考文档内容偏多，或服务器繁忙！"
            chat_content[username]["dsreasoner"] = content
            response_data['model'] = "Dsreasoner"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)


def dsreasoner_stream_generator_sync(data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        generator = dsreasoner_stream_generator(data)
        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def qwq_stream_generator(data):
    constructed_data = construct_data(data)
    response_data = constructed_data["response_data"]
    username = constructed_data["user_name"]
    now_turn_message = constructed_data["message"]

    markers = detect_special_markers(now_turn_message)
    has_double_question_marks = markers['has_double_question_marks']
    has_consecutive_question_marks = markers['has_triple_question_marks']

    global chat_content, chat_with_files_params
    print("qwq time_out", time_out)
    chat_content[username]["qwq"] = ""
    if not constructed_data["file_list"]:
        try:
            # API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
            API_KEY_ALI = os.environ.get("DASHSCOPE_API_KEY", "")

            if constructed_data["system_prompt"] != "":
                role = "当前的场景阶段提示：\n" + global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
                if has_consecutive_question_marks:
                    role = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
                if has_double_question_marks:
                    base_prompt = QS_QQ_base
                    # 根据加号数量调整提示
                    if markers['plus_count'] == 1:
                        role += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                    elif markers['plus_count'] == 2:
                        role += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                    elif markers['plus_count'] == 3:
                        role += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                    else:
                        role += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
            else:
                role = """You are an advanced AI assistant providing accurate and professional responses across 
                                        technical, research, content creation, and general knowledge domains. 

                                        KEY PRINCIPLES:
                                        - Ensure accuracy and completeness
                                        - Provide structured explanations with examples
                                        - Consider multiple solutions and trade-offs
                                        - Use clear language and systematic approach
                                        - Validate practical applicability

                                        DEFAULTS:
                                        - Respond in Chinese unless otherwise specified
                                        - Tailor to user context and requirements
                                        - Include step-by-step explanations when needed"""

            client = AsyncOpenAI(
                api_key=API_KEY_ALI,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",  # "https://api.deepseek.com",
            )
            print("Qwq不勾选文件，发送消息: ", constructed_data["questionQwq"])
            start_time = time.time()
            response = await client.chat.completions.create(
                model="qwq-plus",
                messages=[
                    {"role": "system", "content": role},
                    {"role": "user", "content": constructed_data["questionQwq"]},
                ],
                temperature=global_var.qwqConfig["temperature"],
                top_p=global_var.qwqConfig["top_p"],
                frequency_penalty=global_var.qwqConfig["frequency_penalty"],
                presence_penalty=global_var.qwqConfig["presence_penalty"],
                max_tokens=global_var.qwqConfig["max_tokens"],
                stream=True,  # FIXME yq: 现在暂时默认都开启流式输出
                timeout=time_out,
            )

            print(f"Qwq 响应创建时间: {time.time() - start_time}")
            start_time = time.time()

            async def response_with_timeout(response):
                while True:
                    try:
                        # 为每个块的生成设置超时
                        chunk = await asyncio.wait_for(
                            response.__anext__(),  # 等待下一个异步块
                            timeout=time_out,
                        )
                        yield chunk
                    except StopAsyncIteration:
                        break  # 流式结束
                    except asyncio.TimeoutError:
                        print(f"Qwq 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                        raise APITimeoutError("Qwq 流式块生成超时!")

            reasoning_stop = False
            async for chunk in response_with_timeout(response):
                reasoning_content = chunk.choices[0].delta.reasoning_content
                content = chunk.choices[0].delta.content
                if reasoning_content is not None:
                    reasoning_stop = False
                    if chat_content[username]["qwq"] == "":
                        print(f"Qwq 响应时间: {time.time() - start_time}")
                        result = "```" + reasoning_content
                    else:
                        result = reasoning_content
                elif content is not None:
                    if reasoning_stop:
                        result = content
                    else:
                        result = "```" + content
                    reasoning_stop = True
                else:
                    continue
                response_data['model'] = "Qwq"
                response_data['content'] = result
                chat_content[username]["qwq"] += result
                yield json.dumps(response_data, ensure_ascii=False)
        except Exception as e:
            print(f"Qwq API error: {e}")
            if time.time() - start_time > time_out and chat_content[username]["qwq"] == "":
                print(f"Qwq API调用超时, 超时时间: {time.time() - start_time}秒")
            content = "Qwq API调用出错"
            chat_content[username]["qwq"] = content
            response_data['model'] = "Qwq"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)
    else:
        constructed_params = chat_with_files_params[username]
        print("Qwq勾选文件，发送消息: ", constructed_params["questionQwq"])
        useSystemPrompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
        if has_consecutive_question_marks:
            useSystemPrompt = "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
        if has_double_question_marks:
            base_prompt = QS_QQ_base
            # 根据加号数量调整提示
            if markers['plus_count'] == 1:
                useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
            elif markers['plus_count'] == 2:
                useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
            elif markers['plus_count'] == 3:
                useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
            else:
                useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"
        chain_input = {
            "text": constructed_params["text"],
            "question": constructed_params["questionQwq"],
            "images_store": [],
            "qa_prompt": useSystemPrompt
        }
        start_time = time.time()

        async def stream_with_timeout(step, chain_input):
            # 获取异步生成器
            async_stream = step._astream(chain_input, **global_var.deepseekConfig)
            while True:
                try:
                    # 为每个块的生成设置超时
                    chunk = await asyncio.wait_for(
                        async_stream.__anext__(),  # 等待下一个异步块
                        timeout=time_out,
                    )
                    yield chunk
                except StopAsyncIteration:
                    break  # 流式结束
                except asyncio.TimeoutError:
                    print(f"Qwq 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                    raise APITimeoutError("Qwq 流式块生成超时!")

        chain = normal_qa.qa_chain[8]
        try:
            for _, step in enumerate(chain.steps):
                if isinstance(step, ChatLlamaAPI):
                    print("ds stream")
                    # 使用 astream 方法实现流式输出，并为每个块设置超时
                    reasoning_stop = False
                    async for chunk in stream_with_timeout(step, chain_input):
                        if time.time() - start_time > time_out and chat_content[username]["qwq"] == "":
                            print(f"qwq API调用超时, 超时时间: {time.time() - start_time}秒")
                            raise APITimeoutError("qwq API调用超时")
                        reasoning_content = chunk.choices[0].delta.reasoning_content
                        content = chunk.choices[0].delta.content
                        if reasoning_content is not None:
                            reasoning_stop = False
                            if chat_content[username]["qwq"] == "":
                                print(f"Qwq 响应时间: {time.time() - start_time}")
                                result = "```" + reasoning_content
                            else:
                                result = reasoning_content
                        elif content is not None:
                            if reasoning_stop:
                                result = content
                            else:
                                result = "```" + content
                            reasoning_stop = True
                        else:
                            # print('Dsreasoner 返回内容为空')
                            continue
                        response_data['model'] = "Qwq"
                        response_data['content'] = result
                        chat_content[username]["qwq"] += result
                        yield json.dumps(response_data, ensure_ascii=False)
                        # 为每个流式块设置超时
                        # yield await asyncio.wait_for(json.dumps(response_data, ensure_ascii=False), timeout=60)  # 超时时间为60秒
                else:
                    # 非流式步骤，直接调用 invoke
                    print("qwq invoke")
                    chain_input = step.invoke(chain_input)
                    # yield chain_input  # 返回非流式步骤的输出
        except Exception as e:
            print(f"Qwq出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
            content = "Qwq出错，参考文档内容偏多，或服务器繁忙！"
            chat_content[username]["qwq"] = content
            response_data['model'] = "Qwq"
            response_data['content'] = content
            yield json.dumps(response_data, ensure_ascii=False)


def qwq_stream_generator_sync(data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        generator = qwq_stream_generator(data)
        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


def construct_file_data(segments, user_name, file_list, get_way, question, history, origin_real_name, base64_images):
    print('[normal_qa]get_aq_user_docs_way_split', segments)
    images, seqs, exts, sources, pages = util.parse_image_in_segment_split(
        user_name=user_name,
        all_segments=segments,
    )
    return normal_qa.construct_chain_params(question, user_name, segments, images, seqs, exts, sources, pages, history,
                                            file_list, get_way, origin_real_name, base64_images)


def construct_data(data):
    username = data["username"]
    originRealName = data.get("originRealName", "")
    if originRealName != "":
        name2RealUse = originRealName
    else:
        name2RealUse = username
    seed = int(data['seed'])
    # print('[chat_send]', username, seed)
    global chat_count, chat_content

    message = data["message"]
    model_id = data["model_id"]
    summary = data["summary"]
    fileNameList = data["filenamelist"]
    leftSelectList = data["leftSelectList"]
    rightSelectList = data["rightSelectList"]
    isHistoryUsed = data["isHistoryUsed"]
    isSummaryUsed = data["isSummaryUsed"]
    rounds = int(data["rounds"])
    model_states = data["modelStates"]

    history = False
    if isHistoryUsed == "true" and chat_history_used != {}:
        history = True
    if isSummaryUsed == "true":
        sumContent = ""
        try:
            mysql_card = BgCard.objects.get(username=username, status="2")
            sumContent = mysql_card.content
        except BgCard.DoesNotExist:
            realName = data["realName"]
            userbookName = data["userbookName"]
            sceneName = data["sceneName"]
            bgc = summarize_scene(realName, sceneName)
            current_datetime = timezone.now()
            bg_card = BgCard(
                username=realName,
                name=sceneName + "场景背景摘要",
                detail=sceneName + "场景背景摘要",
                content=bgc,
                datetime=current_datetime,
                status="2"
            )
            bg_card.save()
            sumContent = bgc
        message = "背景知识摘要：\n" + sumContent + "\n用户的请求或提问：\n" + message

    file_list = fileNameList.split(',') if fileNameList else []
    print('[app_chat chat_send]:', leftSelectList, rightSelectList)
    left_select_list = [int(item) for item in leftSelectList.split(',')] if leftSelectList else []
    right_select_list = [int(item) for item in rightSelectList.split(',')] if rightSelectList else []
    print('file_list and selection info:')
    print(file_list, left_select_list, right_select_list)

    if seed == 2:
        # swap topic and topic-question prompt
        topic_question_prompt = global_var.store_memory[username]["prompt"]["LUI2"]["topic_question"]
        global_var.store_memory[username]["prompt"]["LUI2"]["topic_question"] = \
            global_var.store_memory[username]["prompt"]["LUI2"]["qa"]
        global_var.store_memory[username]["prompt"]["LUI2"]["qa"] = topic_question_prompt

    # 如果多轮对话超过n轮，移除最早的一轮
    if len(chat_history_used[name2RealUse]) > rounds:
        chat_history_used[name2RealUse].pop(0)
    if len(chat_history[name2RealUse]) > rounds:
        chat_history[name2RealUse].pop(0)

    if seed == 2:
        # swap topic and topic-question prompt
        topic_question_prompt = global_var.store_memory[username]["prompt"]["LUI2"]["topic_question"]
        global_var.store_memory[username]["prompt"]["LUI2"]["topic_question"] = \
            global_var.store_memory[username]["prompt"]["LUI2"]["qa"]
        global_var.store_memory[username]["prompt"]["LUI2"]["qa"] = topic_question_prompt

    # 这里用作者username去获取文件夹里存储的勾选Cards的可能图片base64
    info_list = []
    info_list_claude = []
    MAX_SIZE = 5 * 1024 * 1024  # 5MB in bytes
    current_total_size = 0
    if 'choosedCardIdList' in data and data['choosedCardIdList']:
        # 如果勾选了卡片问答，存在choosedCardIdList，拆分choosedCardIdList字符串为列表
        CardIndexList = data['choosedCardIdList'].split(',')
        base64_images = get_possible_cardImgs_base64_byIds(username, CardIndexList)
        for base64_image in base64_images:
            claude_list_add_cur_card_image = True
            # 计算当前图片的base64大小
            image_size = get_base64_size(base64_image)
            # 检查添加新图片后是否会超过限制
            if current_total_size + image_size > MAX_SIZE:
                print(f"Skipping image size {image_size} as it would exceed the 5MB limit")
                claude_list_add_cur_card_image = False
            # 更新已使用的总大小
            current_total_size += image_size

            # 因为gemini好像不接受jpg，所以默认试试png
            image_url = f"data:image/png;base64,{base64_image}"
            add_cardImage(info_list, image_url)
            if claude_list_add_cur_card_image:
                add_cardImage(info_list_claude, image_url)

    response = {}
    # response['content'] = content
    # if rel_questions:
    #     response['rel_questions'] = rel_questions
    response['seed'] = seed
    if model_id == '1002':
        response['nowParams'] = global_var.config
    if model_id == '1003':
        response['nowParams'] = global_var.mixtralConfig
    if model_id == '1004':
        response['nowParams'] = global_var.kimiConfig
    if model_id == '1005':
        response['nowParams'] = global_var.llama3Config
    if model_id == '1006':
        response['nowParams'] = global_var.claudeConfig
    if model_id == '1007':
        response['nowParams'] = global_var.deepseekConfig
    if model_id == '1008':
        response['nowParams'] = global_var.deepseekConfig
    if model_id == '1009':
        response['nowParams'] = global_var.geminiConfig
    if model_id == '1010':
        response['nowParams'] = global_var.qwqConfig
    response['msg'] = 'success'
    response['error_num'] = 0

    system_prompt = """You are an advanced AI assistant providing accurate and professional responses across 
                technical, research, content creation, and general knowledge domains. 

                KEY PRINCIPLES:
                - Ensure accuracy and completeness
                - Provide structured explanations with examples
                - Consider multiple solutions and trade-offs
                - Use clear language and systematic approach
                - Validate practical applicability

                DEFAULTS:
                - Respond in Chinese unless otherwise specified
                - Tailor to user context and requirements
                - Include step-by-step explanations when needed"""
    system_prompt_claudeUse = system_prompt_claude

    if history:
        questionGPT, questionLlama, questionKimi, questionClaude, questionDeepseek, questionDsreasoner, questionGemini, questionQwq = normal_qa.get_model_specific_histories(
            username=name2RealUse, question=message)
    else:
        message_emphasize_scene = message + "（要深思熟虑当前的场景阶段提示）"
        questionGPT = questionLlama = questionKimi = questionClaude = questionDeepseek = questionDsreasoner = questionGemini = questionQwq = message_emphasize_scene
        questionClaude = "使用thinking-checking-完整综合结果，回答：\n" + questionClaude
    print(message)
    return {
        "system_prompt": system_prompt,
        "system_prompt_claudeUse": system_prompt_claudeUse,
        "info_list": info_list,
        "info_list_claude": info_list_claude,
        "questionGPT": questionGPT,
        "questionLlama": questionLlama,
        "questionKimi": questionKimi,
        "questionClaude": questionClaude,
        "questionDeepseek": questionDeepseek,
        "questionDsreasoner": questionDsreasoner,
        "questionGemini": questionGemini,
        "questionQwq": questionQwq,
        "response_data": response,
        "file_list": file_list,
        "left_select_list": left_select_list,
        "right_select_list": right_select_list,
        "history": history,
        "message": message,
        "model_states": model_states,
        "user_name": name2RealUse,
        "writer": username
    }

    # await asyncio.gather(*tasks)
    # chunk = normal_qa.get_qa_user_docs_way_split(user_name=username, question=message, docs_name=file_list,
    #                                                get_way=right_select_list, history=history, model_states=model_states)
    # content, finish_reason = extract_content_from_response(chunk)
    # chat_content[username] = content

    # rel_questions = None
    # if finish_reason != 'None':
    #     print('finish_reason:', chunk)
    #     valid_answer = get_first_valid_answer(content)
    #     if valid_answer == None:
    #         valid_answer = chat_content[username][0]
    #     rel_questions = get_rel_que.get_rel_que_user_doc_way_split(user_name=username, docs_name=file_list,
    #                                                             question=message, answer=valid_answer,
    #                                                             get_way=right_select_list)
    # FIXME END
    # kimi_response = kimi_api.make_requests(message, None, False, 0.8)
    # content3 = kimi_response.choices[0].message.content
    # content.append(content3)

    # 之前content[0]只用了主窗口默认model gpt4的回答，历史功能服务仅保留在主窗口，其他窗口无参考价值，因为内容都不是辅窗口model回答的
    # 但现在chat_history_used不用了，用下面完整历史记录的版本
    # chat_history_used[username].append({
    #     '用户请求': deepcopy(messageInitial),
    #     '你的回答': deepcopy(content[0])
    # })
    # chat_history[username].append({
    #     'filelist': deepcopy(file_list),
    #     'message': deepcopy(messageInitial),
    #     'AImessage': deepcopy(content)
    # })


@csrf_exempt
def gpt_chat_send(request):
    # print('[app_chat]views: chat_send')
    # print(request.data)
    data = request.POST
    return StreamingHttpResponse(gpt_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def gemini_chat_send(request):
    # print('[app_chat]views: chat_send')
    # print(request.data)
    data = request.POST
    return StreamingHttpResponse(gemini_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def claude_chat_send(request):
    data = request.POST
    return StreamingHttpResponse(claude_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def deepseek_chat_send(request):
    data = request.POST
    return StreamingHttpResponse(deepseek_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def llama_chat_send(request):
    data = request.POST
    return StreamingHttpResponse(llama_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def kimi_chat_send(request):
    data = request.POST
    return StreamingHttpResponse(kimi_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def dsreasoner_chat_send(request):
    data = request.POST
    return StreamingHttpResponse(dsreasoner_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def qwq_chat_send(request):
    data = request.POST
    return StreamingHttpResponse(qwq_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def rel_questions_request(request):
    data = json.loads(request.body)
    username = data["username"]
    originRealName = data.get("originRealName", "")
    if originRealName != "":
        name2RealUse = originRealName
    else:
        name2RealUse = username
    message = data["message"]
    messageInitial = message
    fileNameList = data["filenamelist"]
    file_list = fileNameList.split(',') if fileNameList else []
    rightSelectList = data["rightSelectList"]
    right_select_list = [int(item) for item in rightSelectList.split(',')] if rightSelectList else []
    window_id = data["windowId"]
    model_id = data["model_id"]

    global chat_content
    answer_list = [
        chat_content[name2RealUse]["gpt4"],
        chat_content[name2RealUse]["llama"],
        chat_content[name2RealUse]["kimi"],
        chat_content[name2RealUse]["claude"],
        chat_content[name2RealUse]["deepseek"],
        chat_content[name2RealUse]["dsreasoner"],
        chat_content[name2RealUse]["Gemini"],
        chat_content[name2RealUse]["Qwq"]
    ]
    # 如果开始综合后，还有追问请求到这里，chat_content[username]都已清空初始化，只有负责综合的1个模型输出到一半，
    # answerList已经不是当轮对话原始回答内容了，所以这一段保存历史记录的代码需要从下面上移到此处，避免耗时过长，前端预留200ms让这里先完成后，再传综合请求
    # print(chat_history[username])
    if len(chat_history[name2RealUse]) == 0 or message != chat_history[name2RealUse][-1]['message']:
        chat_history[name2RealUse].append({
            'filelist': deepcopy(file_list),
            'message': deepcopy(messageInitial),
            'AImessage': deepcopy(answer_list)
        })
    if len(chat_history[name2RealUse]) > 0 and message == chat_history[name2RealUse][-1]['message']:
        chat_history[name2RealUse][-1]['AImessage'] = deepcopy(answer_list)

    valid_answer = data["answer"]
    # valid_answer = get_first_valid_answer(model_names[model_id], chat_content[username], window_id=window_id)
    # if valid_answer == None:
    #     valid_answer = chat_content[username][model_names[model_id]]
    print("chat_content:", chat_content)
    print('valid_answer:', valid_answer)
    rel_questions = get_rel_que.get_rel_que_user_doc_way_split(user_name=username, docs_name=file_list,
                                                               question=message, answer=valid_answer,
                                                               get_way=right_select_list)
    # FIXME END
    # kimi_response = kimi_api.make_requests(message, None, False, 0.8)
    # content3 = kimi_response.choices[0].message.content
    # content.append(content3)

    # 之前content[0]只用了主窗口默认model gpt4的回答，历史功能服务仅保留在主窗口，其他窗口无参考价值，因为内容都不是辅窗口model回答的
    # 但现在chat_history_used不用了，用下面完整历史记录的版本
    # chat_history_used[username].append({
    #     '用户请求': deepcopy(messageInitial),
    #     '你的回答': deepcopy(list(chat_content[username].values())[0])
    # })

    # valid_cnt = 0
    # for answer in answer_list:
    #     if valid_cnt >= 3:
    #         break
    #     if answer != "" and is_valid_answer(answer):
    #         valid_cnt += 1
    # if valid_cnt >= 3:
    #     chat_history[username].append({
    #         'filelist': deepcopy(file_list),
    #         'message': deepcopy(messageInitial),
    #         'AImessage': deepcopy(answer_list)
    #     })
    response = {"rel_questions": rel_questions}
    return JsonResponse(response)


@csrf_exempt
def card_rel_questions_request(request):
    print('[DEBUG:card_rel_questions_request] start')
    
    data = json.loads(request.body)
    username = data["username"]
    fileNameList = data["filenamelist"]
    file_list = fileNameList.split(',') if fileNameList else []
    rightSelectList = data["rightSelectList"]
    right_select_list = [int(item) for item in rightSelectList.split(',')] if rightSelectList else []

    open_card_id = data.get("openCardId", None)
    chosen_content = data.get("chosenContent", "")

    CardContentList = []
    CardTitleList = []
    CardKeyWordsList = []
    message = ''
    finalContent = ''
    CardIndexList = data['choosedCardIdList'].split(',')
    for i, id_str in enumerate(CardIndexList):  # cradlist中存的是字符串形式的index
        id = int(id_str)
        card = Card.objects.get(cid=id)
        cardContent = card.content
        index = cardContent.find("回答：")
        # 去掉 "回答：" 之前的内容，包括 "回答：" 本身
        if index != -1:
            cardContent = cardContent[index + len("回答："):]
        if open_card_id is not None and id == int(open_card_id):
            print("此卡片ctrl+k部分内容选中")
            cardContent = chosen_content
        content = '[文本' + str(i + 1) + ']:\n' + cardContent + '\n\n'
        CardContentList.append(content)

        title = '[标题' + str(i + 1) + ']:\n' + card.contentTitle + '\n'
        keyWords = '[关键词列表' + str(i + 1) + ']:\n' + card.keyWords + '\n'
        CardTitleList.append(title)
        CardKeyWordsList.append(keyWords)

    for cardText in CardContentList:
        finalContent += cardText
    for cardKeyWords in CardKeyWordsList:
        message += cardKeyWords
    for cardTitle in CardTitleList:
        message += cardTitle
    message += "请你考虑如上标题要求，以及关键词列表要求，撰写合适的相关文本"
    # print(message + "\n\n\n" + finalContent)

    special_prompt = "\n你给出的第一个追问问题必须是某部分需要精准修改的导问，例如：xxx段落存在xxx问题，如何修改提升？（注意：必须要用“xxx”标记留空，引导用户" \
                     "主动思考哪个段落存在什么问题，你不能直接给出，即你给的导问字符串中必须包含“xxx”这三个小写字母x，你必须严格遵守！！用三个连续的小写字母x来留空）\n" \
                     "对于后几个追问问题，你需要在用户当前的场景阶段大背景下，从文本本身出发，从用户的角度考虑文本内容的欠缺点、思考用户可能更想看到什么内容，然后从内容扩充、实用" \
                     "提升、简化提炼、精进深化等方向，帮助用户提出精准追问（这些追问与第一个导问不同，需要你直接完整给出追问问题的全部内容，" \
                     "让用户能够直接使用）"

    rel_questions = get_rel_que.get_rel_que_user_doc_way_split(user_name=username, docs_name=file_list,
                                                               question=message, answer=finalContent,
                                                               get_way=right_select_list, special_prompt=special_prompt)
    response = {"rel_questions": rel_questions}
    return JsonResponse(response)


@csrf_exempt
def img_getTopics(request):
    data = json.loads(request.body)
    username = data["username"]
    imgtext = data["imgtext"]

    prompt = imgtext + global_var.store_memory[username]["prompt"]["LUI2"]["img_topic"]
    kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)
    topics = kimi_api.post_process_kimi_response(kimi_response)

    print('img topics from kimi:', topics)
    response = {}
    response['topics'] = topics
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt
def topic_getRelQuestions(request):
    data = json.loads(request.body)
    username = data["username"]
    topicRelText = data["topicRelText"]
    topicClicked = data["topicClicked"]

    prompt = "文本：" + topicRelText + "\n关键词：<" + topicClicked + ">\n" + \
             global_var.store_memory[username]["prompt"]["LUI2"]["topic_question"]
    kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)
    topicRelQuestions = kimi_api.post_process_kimi_response(kimi_response)

    print('topic relative questions from kimi:', topicRelQuestions)
    response = {}
    response['topicRelQuestions'] = topicRelQuestions
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def chat_upload(request):
    data = json.loads(request.body)

    username = data["username"]
    realName = data["realName"]
    model_id = data["model_id"]
    filename = data["filename"].split('.')[0]
    base64_encoded_file = data["file"]
    filetype = ALL_FILE_TYPES[data["filetype"]]
    filesuffix = ALL_FILE_SUFFIX[data["filetype"]]
    binary_data = base64.b64decode(base64_encoded_file)

    print(filetype + " file:[" + filename + "] received. Writing into current folder...")
    received_path = './received_dir/' + 'user_raw_file/' + username + '/' + filename + '.' + filesuffix
    # 从文件路径中提取目录路径
    directory = os.path.dirname(received_path)
    # 检查目录是否存在，如果不存在则创建
    if not os.path.exists(directory):
        os.makedirs(directory)

    # 检查文件是否为图片且需要压缩
    # is_image = filesuffix.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']
    # max_size = 2 * 1024 * 1024  # 2MB
    # target_size = 1.5 * 1024 * 1024  # 1.5MB
    #
    # if is_image and len(binary_data) > max_size:
    #     print(f"图片大小为 {len(binary_data) / 1024 / 1024:.2f}MB，进行压缩...")
    #     try:
    #         # 使用PIL打开图片
    #         img_io = io.BytesIO(binary_data)
    #         img = Image.open(img_io)
    #
    #         # 保存原始方向信息
    #         orientation = None
    #         if hasattr(img, '_getexif') and img._getexif():  # 检查是否有EXIF数据
    #             exif = dict((ExifTags.TAGS.get(k, k), v) for k, v in img._getexif().items())
    #             if 'Orientation' in exif:
    #                 orientation = exif['Orientation']
    #
    #         # 根据方向信息修正图片方向
    #         if orientation:
    #             if orientation == 2:
    #                 img = img.transpose(Image.FLIP_LEFT_RIGHT)
    #             elif orientation == 3:
    #                 img = img.rotate(180, expand=True)
    #             elif orientation == 4:
    #                 img = img.rotate(180, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
    #             elif orientation == 5:
    #                 img = img.rotate(-90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
    #             elif orientation == 6:
    #                 img = img.rotate(-90, expand=True)
    #             elif orientation == 7:
    #                 img = img.rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
    #             elif orientation == 8:
    #                 img = img.rotate(90, expand=True)
    #
    #         # 压缩保持原始图片格式
    #         output_format = img.format if img.format else 'JPEG'
    #
    #         # 初始质量
    #         quality = 95
    #         output = io.BytesIO()
    #
    #         # 首先尝试仅压缩质量，不改变尺寸，质量从95开始，每次降低5，直到30
    #         while quality > 30:  # 设置最低质量限制
    #             output = io.BytesIO()
    #             img.save(output, format=output_format, quality=quality, optimize=True)
    #             if output.tell() <= target_size:
    #                 break
    #             quality -= 5
    #
    #         # 如果仅压缩质量不足，开始缩小尺寸，每次缩小10%，最多缩小到原尺寸的50%
    #         if output.tell() > target_size:
    #             # 获取原始尺寸
    #             width, height = img.size
    #             ratio = 0.9  # 缩小比例
    #
    #             while output.tell() > target_size and ratio > 0.5:  # 限制最大缩小比例
    #                 # 计算新尺寸
    #                 new_width = int(width * ratio)
    #                 new_height = int(height * ratio)
    #                 # 缩放图片
    #                 resized_img = img.resize((new_width, new_height), Image.LANCZOS)
    #                 # 保存到内存
    #                 output = io.BytesIO()
    #                 resized_img.save(output, format=output_format, quality=quality, optimize=True)
    #                 # 更新缩放比例
    #                 ratio -= 0.1
    #
    #         # 获取最终处理后的图片数据
    #         compressed_data = output.getvalue()
    #         print(f"压缩后图片大小为 {len(compressed_data) / 1024 / 1024:.2f}MB")
    #
    #         # 使用压缩后的数据
    #         with open(received_path, 'wb') as file:
    #             file.write(compressed_data)
    #
    #     except Exception as e:
    #         print(f"图片压缩失败: {str(e)}，使用原始图片")
    #         # 压缩失败，使用原始数据
    #         with open(received_path, 'wb') as file:
    #             file.write(binary_data)
    # else:
    #     # 不需要压缩，直接写入
    #     with open(received_path, 'wb') as file:
    #         file.write(binary_data)

    with open(received_path, 'wb') as file:
        # 写入二进制数据
        file.write(binary_data)

    parse_input.get_split_docs_vectors(realName, username, filename + "." + filesuffix)
    print('上传文件结束')
    response = {}
    response['content'] = 'dddddddddddd'
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def prompt_upload(request):
    data = json.loads(request.body)

    username = data["username"]
    filename = data["filename"].split('.')[0]
    base64_encoded_file = data["file"]
    binary_data = base64.b64decode(base64_encoded_file)

    print(username + "'s prompt:[" + filename + "] received.")

    res = read_prompt_from_bytes(binary_data)
    prompt_dict = prompt_to_ghp(res)
    print("new prompt:", prompt_dict)

    parse_input.set_user_prompt(user_name=username, prompt=prompt_dict)

    response = {}
    response['content'] = 'dddddddddddd'
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def card_upload(request):
    data = json.loads(request.body)

    username = data["username"]
    originRealName = data.get("originRealName", "")
    if originRealName != "":
        name2RealUse = originRealName
    else:
        name2RealUse = username
    datetime = data["datetime"]
    model_id = data["model_id"]
    content = data["content"]
    status0 = data["status"]  # 0: normal_qa  1: summary   2: combination
    seed = int(data["seed"])
    sceneName = data["sceneName"]
    subSceneName = data["subSceneName"]
    timeParams = json.loads(data["timeParams"])

    print('[card_upload],seed=', seed, type(seed))

    if status0 == 'false':
        status = 0
    elif status0 == 'true':
        status = 1

    # score, color, reason = red_bule_rate.get_rate(username, content)
    # print("卡片打分：----------------"+str(score)+" 理由："+reason)
    score = -2
    color = "紫"
    reason = ""
    # score = 1.2
    print("[" + datetime + "]接收到了来自[" + username + "]的卡片,model=" + model_id + ",content=" + content)
    print("当时参数为: " + data["timeParams"])

    title = "来自模型" + str(model_id) + "的"
    if status == 0:
        title += "问答"
        print(title)
    elif status == 1:
        title += "总结"
        print(title)

    keyTopics = data.get('keyTopics', '[]')
    # 将 keyTopics 字符串解析为列表
    keyTopicsList = json.loads(keyTopics)

    system_prompt = (
        '你是擅长阅读理解文本并总结关键词的专家。'
        '你接下来将得到一段文本和已有的关键词备选集合，你需要阅读理解这段文本，总结出1到3个关键词。'
        '如果备选集合中有合适的关键词，请直接选取；如果没有合适的，再自行总结。共需得出1到3个关键词，请尽量先在备选集合里选取相对合适的，实在没有再新加。'
        '输出格式如“关键词1，关键词2，关键词3”，无其他多余内容！'
    )
    prompt = (
        f"{system_prompt}\n"
        f"已有的关键词备选集合：{', '.join(keyTopicsList)}\n"
        f"需要你总结1到3个关键词的文本：\n{content}"
    )
    kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)  # 获取kimi的回答
    keyWords = kimi_response.choices[0].message.content
    # gpt4_response = gpt4_api.make_gpt4o_text_requests(prompt)
    # keyWords = gpt4_response

    system_prompt_title = '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，' \
                          '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求' \
                          '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
    prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + content
    kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)  # 获取kimi的回答
    # contentTitle = kimi_response_title.choices[0].message.content
    # gpt4_response_title = gpt4_api.make_gpt4o_text_requests(prompt_title)
    gpt4_response_title = kimi_response_title.choices[0].message.content
    # 判断当前是哪一个子场景做卡片
    sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
    entries = os.listdir(sceneDirPath)
    # 检查每个条目是否为目录
    subSceneNameList = [
        entry for entry in entries
        if os.path.isdir(os.path.join(sceneDirPath, entry))
           and not entry.endswith('_image') and entry != RANDOM_USER_NAME and entry != "cardImage"]
    secenExcelPath = './received_dir/' + 'scene_excel/' + sceneName + '/prompt.xlsx'
    sheetName = 'LUI1'
    data = pd.read_excel(secenExcelPath, sheet_name=sheetName)
    subSceneCol = 1
    firstSubSceneColName = data.columns[subSceneCol]
    subSceneNameListOrder = data.iloc[:, 1].dropna().tolist()
    subSceneNameListOrder.insert(0, firstSubSceneColName)
    if len(subSceneNameListOrder) == len(subSceneNameList):
        subSceneNameList = subSceneNameListOrder
    try:
        index = subSceneNameList.index(subSceneName)
        # 索引从0开始，但我们需要从1开始，所以加1
        subSceneOrder = "S" + str(index + 1) + ":"
        gpt4_response_title = subSceneOrder + gpt4_response_title
    except ValueError:
        # 处理subSceneName不在列表中的情况
        print(f"警告：{subSceneName}不在子场景列表中")
        subSceneOrder = "S0:"  # 或设置其他默认值
        gpt4_response_title = subSceneOrder + gpt4_response_title
    contentTitle = gpt4_response_title

    # zyr chat_history
    latest_history_list = chat_history[name2RealUse]
    latest_history = {'data': latest_history_list}
    # zyr end

    card = Card.objects.create(
        status=status,
        content=content,
        title=title,
        model_id=model_id,
        username=username,
        score=score,
        time_params=timeParams,
        seed=seed,
        history=latest_history,
        color=color,
        reason=reason,
        keyWords=keyWords,
        contentTitle=contentTitle,
        writer=name2RealUse
    )

    return JsonResponse({
        'status': 'success',
        'message': 'Card added successfully.',
        'card_id': card.cid,
        'score': score,
        'error_num': 0,
        'seed': seed,
    }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def card_tidyUpById(request):
    data = json.loads(request.body)

    username = data["username"]
    cardAllTitlesAndIndexes = data["cardAllTitlesAndIndexes"]
    cid = data["cid"]
    card = Card.objects.get(cid=cid)
    oldCardContent = card.content
    oldCardContentTitle = card.contentTitle

    system_prompt = """You are an advanced AI assistant providing accurate and professional responses across 
                    technical, research, content creation, and general knowledge domains. 

                    KEY PRINCIPLES:
                    - Ensure accuracy and completeness
                    - Provide structured explanations with examples
                    - Consider multiple solutions and trade-offs
                    - Use clear language and systematic approach
                    - Validate practical applicability

                    DEFAULTS:
                    - Respond in Chinese unless otherwise specified
                    - Tailor to user context and requirements
                    - Include step-by-step explanations when needed"""

    # 第一步：整理卡片内容
    organize_prompt = f"""请将以下内容整理为一张知识卡片的内容，使其具有一定的原子性和原创性。

        原标题：{oldCardContentTitle}
        原内容：
        {oldCardContent}

        整理注意事项：
        1. 原文本的内容尽量都不要丢弃，只是将其整理、改写为具有卡片特点的文字，原文中你认为重要的、高水平的、有价值的段落、句子请都保留原样
        2. 如果原文本已经有很明确的组织形式、格式或标记等，请一定保留，不要修改原格式，只调整内容表述
        3. 原文不超过2000字时，整理出的卡片篇幅应该与原文本篇幅接近，整理是指捋顺逻辑、层次等，而不是总结摘要
        4. 控制改动幅度，若原文本格式、层次等都比较好，就简单轻度整理；若原文逻辑、层次、格式等不够清晰、观点表述较为混杂，就改动幅度稍微大些，但一定不能脱离原文本语境场景特点，也不要改动太大，总之控制好幅度

        请只返回整理后的内容，不要有其他解释。
        """

    organized_content_response = claude_api.make_claude_text_requests(organize_prompt, system_prompt)
    organized_content = organized_content_response.strip()
    card.lastContent = oldCardContent
    card.content = organized_content

    # 第二步：判断卡片类型
    type_prompt = f"""请根据卢曼卡片盒笔记法的原则，判断以下内容应该归类为哪种类型的卡片：闪念卡片、文献卡片还是永久卡片？

        请只回答"闪念卡片"、"文献卡片"或"永久卡片"中的一个，不要有任何解释或其他内容。

        卡片标题：{oldCardContentTitle}
        卡片内容：
        {organized_content}
        """

    card_type_response = claude_api.make_claude_text_requests(type_prompt, system_prompt)
    card_type = card_type_response.strip()
    card.type = card_type

    # 如果是永久卡片，则进行前置索引建议
    index_suggestion = ""
    if "永久卡片" in card_type:
        index_prompt = f"""我正在使用卢曼卡片盒笔记法组织知识。请根据以下信息，为我的新卡片推荐一个合适的前置索引编码。

            新卡片信息：
            标题：{oldCardContentTitle}
            内容：{organized_content}

            已有卡片信息（标题和前置索引）：
            {cardAllTitlesAndIndexes}

            请遵循卢曼卡片盒笔记法的编码规则：
            1. 已有的卡片可能很多只有标题，前置索引还为空，这种的已有卡片请你直接忽略掉
            2. 如果新卡片直接关联到已有的卡片，且此卡片已有索引编码，则使用该卡片的索引加上新的分支号
            3. 如果没有直接关联的卡片，或者所有现有卡片都没有前置索引，则初始化为"新数字"
            4. 如果新卡片是对某个已有卡片的直接延续或深入讨论，则可以将其编码为该卡片索引加"a"、"b"等后缀

            请只回答你建议的前置索引编码，例如"1a"、"2"、"1.1"等，不要有任何解释或其他内容。
            """

        index_suggestion_response = claude_api.make_claude_text_requests(index_prompt, system_prompt)
        index_suggestion = index_suggestion_response.strip()
        card.preIndex = index_suggestion

    model_id_value = int(card.model_id)
    # 检查是否小于0
    if model_id_value >= 0:
        card.model_id = -1

    status = int(card.status)
    if status >= 0:
        status = -1
    card.status = status - 1

    card.save()  # 保存更改到数据库

    return JsonResponse({
        'status': 'success',
        'message': 'Card updated successfully.',
        'error_num': 0,
    }, status=201)


@csrf_exempt
def card_backVersionById(request):
    data = json.loads(request.body)

    username = data["username"]
    cid = data["cid"]
    # 安全地获取可选的mode字段, normal/tidyUpBack
    mode = data.get("mode", "tidyUpBack")

    print(f"{username} 请求回退卡片: {cid}，模式: {mode}")

    card = Card.objects.get(cid=cid)

    lastContent = card.lastContent
    card.content = lastContent
    card.lastContent = ""

    if mode == "tidyUpBack":
        card.type = ""
        card.preIndex = ""
        # card.postIndex = ""

    # 修改status状态
    status = int(card.status)
    if status < -2:
        card.status = status + 1
    if status == -2:
        card.status = 0

    # 修改model_id状态
    model_id_value = int(card.model_id)
    if model_id_value < 0 and status == -2:
        card.model_id = 0

    card.save()  # 保存更改到数据库

    response = {}
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def card_updateContentById(request):
    data = json.loads(request.body)

    username = data["username"]
    content = data["content"]
    cid = data["cid"]

    card = Card.objects.get(cid=cid)

    open_card_id = data.get("openCardId", None)
    chosen_content = data.get("chosenContent", "")

    oldCardContentRetain = card.content
    oldCardContent = card.content
    if open_card_id == cid:
        print("ctrl+k部分选中卡片内容")
        oldCardContent = chosen_content

    answer_position = oldCardContent.find("回答：") if "回答：" in oldCardContent else -1
    content_before = oldCardContent[:answer_position] if answer_position != -1 else ""
    content_after = oldCardContent[
                    answer_position + len("回答："):].strip() if answer_position != -1 else oldCardContent.strip()
    oldCardContent = content_after

    # thinking_pos = oldCardContent.find("```thinking")
    # if thinking_pos != -1:
    #     # 检查"```thinking"前面是否已经有换行符，如果前面没有换行符，才添加一个
    #     if thinking_pos == 0 or oldCardContent[thinking_pos - 1] != '\n':
    #         oldCardContent = oldCardContent[:thinking_pos] + "\n" + oldCardContent[thinking_pos:]

    system_prompt = """You are an advanced AI assistant providing accurate and professional responses across 
                    technical, research, content creation, and general knowledge domains. 

                    KEY PRINCIPLES:
                    - Ensure accuracy and completeness
                    - Provide structured explanations with examples
                    - Consider multiple solutions and trade-offs
                    - Use clear language and systematic approach
                    - Validate practical applicability

                    DEFAULTS:
                    - Respond in Chinese unless otherwise specified
                    - Tailor to user context and requirements
                    - Include step-by-step explanations when needed"""

    # content = content.replace("```thinking", "")
    # content = content.replace("```checking", "")
    # content = content.replace("```", "")
    content = remove_thinking_and_checking_blocks(content)
    # oldCardContent = oldCardContent.replace("```thinking", "")
    # oldCardContent = oldCardContent.replace("```checking", "")
    # oldCardContent = oldCardContent.replace("```", "")
    oldCardContentOrigin = oldCardContent
    oldCardContent = remove_thinking_and_checking_blocks(oldCardContent)
    oldCardContent = oldCardContent.strip()

    user_prompt = "这里是一段初始文本：\n" + oldCardContent + "\n\n"
    user_prompt += "下面是根据如上初始文本的某个局部或段落，找出的一条问题或改进点提问，以及其回答：\n" + content + "\n\n"
    user_prompt += "1.任务及目标描述\n" \
                   "（1）任务：你需要根据如上的提问，精准定位到其对应初始文本的哪个局部或段落应该被改进，即“改进目标位置”，然后根据回答的内容，理解并抽取其" \
                   "重点，对初始文本中的”改进目标位置“进行高质量的局部针对性改进\n" \
                   "（2）目标：回答内容合并回初始文本后，针对找出的问题所对应的“改进目标位置”，改后版本要相对于原始文本有明显的改进提升，逻辑清晰、提升到位、" \
                   "篇幅占比合适，体现核心精髓\n\n" \
                   "2.具体注意事项及要求\n" \
                   "a.输出格式要求（这5条都必须严格遵守！）\n" \
                   "（1）你只需要直接给出最终文本，不要输出其他内容，也不要重复一遍前面给你的改进点提问及回答\n" \
                   "（2）整体结构、格式必须以原初始文本为标准，保持不变，你只应该修改提升”改进目标位置“部分的一定比例内容，未改动的内容要保持原样输出，一定不能去掉\n" \
                   "（3）你本次做局部针对性改进有所改动的部分，输出时都用<第n次修改内容>和</第n次修改内容>标签包裹起来，标签只应该包裹相对原初始文本真正产生diff的" \
                   "文字内容，避免产生误导！注意n使用阿拉伯数字，不要用汉字\n" \
                   "（4）如果初始文本里没有上面这样的标签，说明从未迭代修改过，即本次n应该为1；如果初始文本里已经有了这样的标签，说明之前迭代修改过，本次是进一步" \
                   "改进，根据原有标签中次数的最大值m，本次n应该为m+1\n" \
                   "（5）如果初始文本里已经有了上面这样的标签，本次修改必须保留之前的标签，比如第n次修改时，要保留前面第1到n-1次修改的标签及其内部本次修改未涉及的内容，一定不要删除前面的标签\n" \
                   "格式样例示意：\n" \
                   "初始文本：第一段：这是一段文字。第二段：这段与初次抽取出的改进点提问回答强相关，其中有一些逻辑不清晰或表达不够准确的地方。\n" \
                   "首次修改后输出：第一段：这段保持了初始的文字未改动。第二段：这是首次“改进目标位置”，其中一部分未改动，<第1次修改内容>这部分改后逻辑更加清晰，表达更加" \
                   "准确</第1次修改内容>，这部分也未改动。\n" \
                   "进一步修改后输出：第一段：这段仍保持了初始的文字未改动。第二段：第一部分仍未改动，<第1次修改内容>这是第1次改后的内容，第2次未改动，原样输出</第1次修改" \
                   "内容>。第二段这一小部分是本次“改进目标位置”，<第2次修改内容>这里进行了更深入的分析，使论述更加完善</第2次修改内容>，其他本次未修改文字。\n" \
                   "b.输出内容注意\n" \
                   "（1）确保内容结构层次分明、递进合理\n" \
                   "（2）统一语言风格，补充必要的过渡和连接，确保行文流畅（直接给出最终文本，不要输出其他内容，也不要输出理由解释，务必遵守！）\n" \
                   "（3）控制好本次局部针对性改进的篇幅，本次即<第n次修改内容>标签包裹的文字篇幅，应该只占初始文本中“改进目标位置”部分的10％到15％为佳，不可多于20%！突出" \
                   "重点，切忌修改过多（若初始文本本身篇幅较少，如低于200字，你的修改篇幅可以稍大些；否则这一点要严格遵守！）"
    # mergeNewContent = gpt4_api.make_gpt4o_text_requests(user_prompt, system_prompt)
    mergeNewContent = claude_api.make_claude_text_requests(user_prompt, system_prompt)

    # 移除"```markdown"标记，并清理多余的空行
    mergeNewContent = mergeNewContent.replace("```markdown", "")
    mergeNewContent = mergeNewContent.strip()

    print("去除处理后\n" + oldCardContent)
    final_result = restore_thinking_checking_blocks(oldCardContentOrigin, oldCardContent, mergeNewContent)
    if open_card_id == cid:
        final_result = card.content.replace(chosen_content, final_result)
    if answer_position != -1:
        final_result = content_before + "回答：\n" + final_result

    card.content = final_result
    card.lastContent = oldCardContentRetain

    model_id_value = int(card.model_id)
    # 检查是否小于0
    if model_id_value >= 0:
        card.model_id = -1

    status = int(card.status)
    if status >= 0:
        status = -1
    card.status = status - 1

    card.save()  # 保存更改到数据库

    return JsonResponse({
        'postIndex': card.postIndex,
        'status': 'success',
        'message': 'Card updated successfully.',
        'error_num': 0,
    }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def card_score(request):
    data = json.loads(request.body)
    username = data["username"]
    content = data["content"]
    cid = data["cid"]

    score, color, reason = red_bule_rate.get_rate(username, content)
    print("卡片打分：----------------" + str(score) + " 理由：" + reason)

    card = Card.objects.get(cid=cid)

    # 更新字段, 保存到数据库
    card.score = score
    card.color = color
    card.reason = reason
    card.save()

    return JsonResponse({
        'status': 'success',
        'message': 'Card Scored successfully.',
        'card_id': cid,
        'score': score,
        'error_num': 0
    }, status=201)


# return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@csrf_exempt
def card_getAllUserFiles(request):
    data = json.loads(request.body)

    username = data["username"]
    scene_name = data["sceneName"]
    print(username + "请求获取存储的所有文档..." + "sceneName:" + scene_name)

    user_path = './received_dir/' + 'user_raw_file/' + username
    response = {}
    file_list = []
    size_list = []
    file_info_list = []
    # 确保路径存在
    if not os.path.exists(user_path):
        response['content'] = file_info_list
        response['msg'] = 'success'
        response['error_num'] = 0
        return JsonResponse(response)
    try:
        # 1.获取用户上传的文件及其大小
        for f in os.listdir(user_path):
            if os.path.isdir(user_path + '/' + f):
                continue
            if f.endswith('_transFTWYGUHX.pdf'):
                continue
            file_list.append(f)
            size_list.append(os.path.getsize(os.path.join(user_path, f)))
        print(file_list)
        # 2.获取场景预设文件及其大小
        file_checked_list, file_checked_size_list = parse_input.get_list_by_scene_name(scene_name=scene_name)
        # 3.获取分割完成的文件
        split_file_list = global_var.store_memory[username]["split_file"]
        # 4.构建元组
        for i in range(len(file_list)):
            file_info_list.append((file_list[i], size_list[i], file_list[i] in file_checked_list,
                                   (1 if file_list[i] in split_file_list else 0)))
        # file_info_list = [
        #     (f, os.path.getsize(os.path.join(user_path, f)), f in file_checked_list, (1 if f in split_file_list else 0))
        #     for f in os.listdir(user_path)
        #     if os.path.isfile(os.path.join(user_path, f))
        # ]

    except Exception as e:
        print(e)
        response['msg'] = 'error'
        response['error_num'] = 1
        return JsonResponse(response)

    print('[app_chat]card_getAllUserFiles', file_info_list)
    response['content'] = file_info_list
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt
def card_getFileByName(request):
    data = json.loads(request.body)

    username = data["username"]
    filename = data["filename"]
    fileNameList = data["fileNameList"]
    leftSelectList = data["leftSelectList"]
    rightSelectList = data["rightSelectList"]
    print(username + "请求获取文档摘要:" + filename + "，list info:")
    file_list = fileNameList.split(',')
    # [0, 2, 1, 0]
    left_select_list = [int(item) for item in leftSelectList.split(',')]
    right_select_list = [int(item) for item in rightSelectList.split(',')]
    print(file_list, left_select_list, right_select_list)

    file_path = 'received_dir/' + 'user_raw_file/' + username + '/' + filename
    response = {}
    print(file_path)
    # 检查文件是否存在
    if not os.path.exists(file_path):
        print("文件路径不存在")
        response['msg'] = 'error'
        response['error_num'] = 1
        return JsonResponse(response)

    # # 尝试打开并读取文件内容，暂时不用了，用summary
    # try:
    #     with open(file_path, 'rb') as file:
    #         file_content = file.read()
    # except Exception as e:
    #     response['msg']='error'
    #     response['error_num']=1
    #     return JsonResponse(response)
    # content = base64.b64encode(file_content).decode('utf-8')

    # file_list = [filename]
    try:
        # FIXME
        content = get_suma.get_summary_user_docs_way_split(user_name=username, docs_name=file_list,
                                                           get_way=left_select_list)
        topic = get_topic.get_topic_user_docs_way_split(user_name=username, docs_name=file_list,
                                                        get_way=left_select_list)
        # FIXME END

        # content = '我是后端传来的摘要，因为gpt4要花钱所以只能这样，现在的我花不了一分钱，可以一直点'
        # topic = ['topic1', 'topic2', 'topic3']

        response['content'] = content
        response['topic'] = topic
        response['msg'] = 'success'
        response['error_num'] = 0
        return JsonResponse(response)
    except Exception as e:
        print(str(e))
        response['msg'] = 'failed'
        response['error_num'] = 1
        return JsonResponse(response)


@csrf_exempt
def card_getTextByName(request):
    data = json.loads(request.body)

    username = data["username"]
    filename = data["filename"]
    print(username + "请求获取文档的文本:" + filename)

    file_list = [filename]
    # FIXME
    text, images = parse_input.get_docs_by_user_doc(user_name=username, docs_name=file_list)
    # FIXME END
    # text = ['为什么我也要写死，因为ghp的代码太慢了以至于成功率很低']

    print(text[0], images[0])
    response = {}
    response['text'] = text[0]
    response['images'] = images[0]
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


@csrf_exempt
def card_getImgText(request):
    data = json.loads(request.body)

    username = data["username"]
    realName = data["realName"]
    book_name = username[len(realName) + 1:]  # 去掉 "用户名_" 部分
    filename = data["filename"]
    imgid = data["imgid"]
    mode = data["mode"]
    print(username + "请求获取文档图片:" + filename + "-" + imgid)

    content = parse_input.get_pdf_image_sum(user_name=username, doc_name=filename, seq=int(imgid))
    print(content)
    response = {}
    response['content'] = content
    response['msg'] = 'success'
    response['error_num'] = 0

    # 查找对应的笔记本
    if mode == "img":
        try:
            # 查询对应的笔记本
            notebook = UserNotebook.objects.get(username=realName, bookName=book_name)

            # 检查MayImgDocHLScore字段是否为空
            if notebook.MayImgDocHLScore:
                try:
                    # 尝试解析为JSON
                    img_scores = json.loads(notebook.MayImgDocHLScore)

                    # 检查是否包含filename的字段
                    if filename in img_scores:
                        # 将评分添加到响应中
                        response['HLScore'] = img_scores[filename]
                except json.JSONDecodeError:
                    # 如果不是有效的JSON，则忽略
                    pass
        except Exception as e:
            # 如果查询出错，记录错误但不影响主要功能
            print(f"获取HLScore出错: {str(e)}")
            # 这里不返回错误，保持原有功能正常

    return JsonResponse(response)


@csrf_exempt
def card_updateImgText(request):
    data = json.loads(request.body)

    username = data["username"]
    filename = data["filename"]
    imgid = data["imgid"]
    content = data["content"]
    print(username + "请求更新文档图片:" + filename + "-" + imgid)

    merge_content = ""
    if content != "":
        merge_content = content

    start_time = time.time()
    content = parse_input.update_pdf_image_sum(user_name=username, doc_name=filename, seq=int(imgid),
                                               merge_content=merge_content)
    end_time = time.time()
    processing_time = end_time - start_time
    print(f"更新矢量存储此文档此 <图片> 解析文本时间: {processing_time:.2f}秒")

    response = {}
    response['content'] = content
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


@csrf_exempt
def card_getAllUserCards(request):
    data = json.loads(request.body)

    username = data["username"]
    print(username + "请求获取存储的所有卡片...")

    # # 排除大字段
    # fields_to_exclude = [
    #     'history', 'reasonSFT', 'reason', 'subareaAndHLAndSugTA2GL',
    #     'lastContent'
    # ]

    # 指定要获取的字段（排除了大字段）
    fields_to_include = [
        'cid', 'datetime', 'username', 'model_id', 'status',
        'content', 'title', 'score', 'time_params', 'seed',
        'color', 'keyWords', 'contentTitle', 'scoreSFT',
        'colorSFT', 'type', 'preIndex', 'postIndex', 'writer',
        'interGrowthT2TA', 'interGrowthGL2GM', 'interGrowthTA2GL'
    ]

    # 查询并只获取指定字段
    cards = Card.objects.filter(username=username).order_by('-datetime').values(*fields_to_include)
    cards_data = list(cards)  # 转换 QuerySet 为字典列表

    # 处理content字段和为其他大字段设置默认值
    for card in cards_data:
        # 计算完整内容的字数（在截取之前）
        full_content = card.get('content', '')
        card['word_count'] = count_words_another(full_content)
        # 截取content字段的前100个字符
        if card['content']:
            card['content'] = card['content'][:100] + "\n......"

        card['history'] = None
        card['reason'] = ""
        card['reasonSFT'] = ""
        card['subareaAndHLAndSugTA2GL'] = ""
        card['lastContent'] = ""

    # cards = Card.objects.filter(username=username).order_by('-datetime').values()
    # cards_data = list(cards)  # 转换 QuerySet 为字典列表

    # 创建卡片ID到卡片的映射字典，方便快速查找
    cards_dict = {card['cid']: card for card in cards_data}

    # 创建得分缓存，避免重复计算
    score_cache = {}

    # 对每个卡片计算加权评分
    for card in cards_data:
        original_score = card['scoreSFT']
        has_source = bool(extract_card_ids(card['title']))

        # 只对有来源的卡片重新计算评分
        if has_source:
            weighted_score, source_count = calculate_weighted_score_recursion(card, cards_dict, score_cache)
            card['scoreSFT'] = round(weighted_score, 2)  # 保留两位小数
            print(f"卡片 {card['cid']} 原始分数: {original_score}, 加权分数: {card['scoreSFT']}, 来源数: {source_count}")
            if card['scoreSFT'] > 0:
                card['scoreSFT'] = round(card['scoreSFT'] * 0.7 + card['score'] * 0.3, 2)
                print(f"卡片 {card['cid']} 最终深浅加权分数: {card['scoreSFT']}")

    response = {}
    response['content'] = cards_data
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt
def card_setCardById(request):
    data = json.loads(request.body)

    username = data["username"]
    cid = data["cid"]
    print(username + "请求获取卡片:" + cid)

    card = Card.objects.get(cid=cid)

    # 更新datetime字段为当前时间,保存更改
    card.datetime = timezone.now()
    card.save(update_fields=['datetime'])

    # print('[card_getCardById]', card.history)
    response = {}
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


@csrf_exempt
def card_updatePostIndex(request):
    data = json.loads(request.body)

    username = data["username"]
    cid = data["cid"]
    post_index = data["postIndex"]
    print(username + "请求获取卡片:" + cid)

    # 查找并更新卡片
    try:
        card = Card.objects.get(cid=cid)

        # 确保用户有权限更新这张卡片
        if card.username == username:
            # 更新后置索引
            card.postIndex = post_index
            card.save()
            response = {
                'msg': 'success',
                'error_num': 0
            }
        else:
            # 用户无权限
            response = {
                'msg': '无权限更新此卡片',
                'error_num': 1
            }
    except Exception as e:
        # 捕获其他异常
        print(f"更新卡片后置索引出错: {str(e)}")
        response = {
            'msg': f'更新失败: {str(e)}',
            'error_num': 1
        }

    return JsonResponse(response)


@csrf_exempt
def card_getCardById(request):
    data = json.loads(request.body)

    username = data["username"]
    cid = data["cid"]
    print(username + "请求获取卡片:" + cid)

    card = Card.objects.get(cid=cid)

    # print('[card_getCardById]', card.history)
    card_history = None
    if card.history is not None:
        card_history = card.history['data']
    card_data = {
        'cid': card.cid,
        'title': card.title,
        'content': card.content,
        'status': card.status,
        'username': card.username,
        'datetime': card.datetime,
        'score': card.score,
        'timeParams': card.time_params,
        'history': card_history,
        'color': card.color,
        'reason': card.reason,
        'keyWords': card.keyWords,
        'contentTitle': card.contentTitle,
        'scoreSFT': card.scoreSFT,
        'colorSFT': card.colorSFT,
        'reasonSFT': card.reasonSFT,
        'type': card.type,
        'preIndex': card.preIndex,
        'postIndex': card.postIndex,
        'lastContent': card.lastContent,
        'writer': card.writer,
        'interGrowthT2TA': card.interGrowthT2TA,
        'interGrowthTA2GL': card.interGrowthTA2GL,
        'interGrowthGL2GM': card.interGrowthGL2GM,
        'subareaAndHLAndSugTA2GL': card.subareaAndHLAndSugTA2GL,
        'word_count': count_words_another(card.content)
        # 包含你想要序列化的所有字段
    }

    # 检查卡片是否有来源，如果有则计算加权评分
    has_source = bool(extract_card_ids(card.title))
    if has_source:
        # 获取所有相关的来源卡片
        source_cards_dict = get_all_source_cards(card, username)

        # 将当前卡片添加到字典中
        source_cards_dict[card.cid] = {
            'cid': card.cid,
            'title': card.title,
            'scoreSFT': card.scoreSFT
        }

        # 创建得分缓存
        score_cache = {}

        # 计算加权得分
        card_dict = source_cards_dict[card.cid]
        weighted_score, source_count = calculate_weighted_score_recursion(
            card_dict, source_cards_dict, score_cache
        )

        # 更新返回数据中的得分
        card_data['scoreSFT'] = round(weighted_score, 2)
        print(f"卡片 {card.cid} 原始分数: {card.scoreSFT}, 加权分数: {card_data['scoreSFT']}, 来源数: {source_count}")
        if card_data['scoreSFT'] > 0:
            card_data['scoreSFT'] = round(card_data['scoreSFT'] * 0.7 + card_data['score'] * 0.3, 2)
            print(f"卡片 {card.cid} 最终深浅加权分数: {card_data['scoreSFT']}")

    response = {}
    response['content'] = card_data
    response['msg'] = 'success'
    response['error_num'] = 0

    # 检查卡片图片是否存在
    img_dir = f"./received_dir/user_raw_file/{username}/cardImage"

    # 尝试查找不同后缀的图片文件
    img_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
    img_path = None

    for ext in img_extensions:
        possible_path = os.path.join(img_dir, f"{cid}{ext}")
        # 标准化路径，使用正斜杠
        possible_path = os.path.normpath(possible_path).replace("\\", "/")
        if os.path.exists(possible_path):
            img_path = possible_path
            break

    # 如果找到图片，将其转换为base64
    if img_path:
        print(f"找到从属卡片{cid}的图片路径{img_path}")
        try:
            with open(img_path, 'rb') as img_file:
                img_data = img_file.read()
                img_base64 = base64.b64encode(img_data).decode('utf-8')

                # 获取正确的MIME类型
                mime_type = mimetypes.guess_type(img_path)[0]
                if not mime_type:
                    # 如果无法确定MIME类型，根据扩展名设置
                    ext = os.path.splitext(img_path)[1].lower()
                    if ext == '.jpg' or ext == '.jpeg':
                        mime_type = 'image/jpeg'
                    elif ext == '.png':
                        mime_type = 'image/png'
                    elif ext == '.gif':
                        mime_type = 'image/gif'
                    elif ext == '.webp':
                        mime_type = 'image/webp'
                    else:
                        mime_type = 'image/jpeg'  # 默认

                response['img'] = img_base64
                response['img_type'] = mime_type
                print(f"成功读取图片并转换为base64，MIME类型: {mime_type}")
        except Exception as e:
            print(f"读取图片失败: {e}")
            response['img'] = ""
            response['img_type'] = ""
    else:
        response['img'] = ""
        response['img_type'] = ""

    return JsonResponse(response)


def get_all_source_cards(card, username):
    """
    递归获取卡片所有层级的来源卡片

    参数:
    - card: 当前卡片
    - username: 用户名

    返回:
    - 所有相关来源卡片的字典，键为cid字符串
    """
    result = {}
    visited = set()

    def collect_sources(current_card):
        # 提取来源卡片ID
        source_ids = extract_card_ids(current_card.title)

        for source_id in source_ids:
            if source_id.isdigit():
                int_source_id = int(source_id)
                if int_source_id not in visited:
                    visited.add(source_id)
                    try:
                        # 获取来源卡片
                        source_card = Card.objects.get(cid=int_source_id, username=username)

                        # 添加到结果字典
                        result[int_source_id] = {
                            'cid': source_card.cid,
                            'title': source_card.title,
                            'scoreSFT': source_card.scoreSFT
                        }

                        # 递归获取该卡片的来源
                        collect_sources(source_card)

                    except Card.DoesNotExist:
                        # 来源卡片不存在，跳过
                        continue

    # 开始收集来源卡片
    collect_sources(card)

    return result


@csrf_exempt
def getCardsContentByIds(request):
    data = json.loads(request.body)

    username = data["username"]

    open_card_id = data.get("openCardId", None)
    chosen_content = data.get("chosenContent", "")

    CardContentList = []
    finalContent = ''
    CardIndexList = data['choosedCardIdList'].split(',')
    for i, id_str in enumerate(CardIndexList):  # cradlist中存的是字符串形式的index
        id = int(id_str)
        card = Card.objects.get(cid=id)
        cardContent = card.content
        index = cardContent.find("回答：")
        # 去掉 "回答：" 之前的内容，包括 "回答：" 本身
        if index != -1:
            cardContent = cardContent[index + len("回答："):]
        if open_card_id is not None and id == int(open_card_id):
            print("此卡片ctrl+k部分内容选中")
            cardContent = chosen_content
        content = '[重要素材文本' + str(i + 1) + ']:\n' + cardContent + '\n\n'
        CardContentList.append(content)

    # 设置字/单词数量限制
    WORD_LIMIT = 6000

    # 处理每个卡片的后置索引
    for id_str in CardIndexList:
        id = int(id_str)
        card = Card.objects.get(cid=id)

        # 检查是否有有效的postIndex
        if card.postIndex and card.postIndex != "":
            try:
                # 解析JSON字符串为Python列表
                post_index_list = json.loads(card.postIndex)

                # 遍历后置索引卡片
                for post_id in post_index_list:
                    try:
                        # 检查是否已达到字/单词数量限制
                        current_total_words = get_total_words_count(CardContentList)
                        if current_total_words >= WORD_LIMIT:
                            print(f"已达到{WORD_LIMIT}字/单词限制，停止添加更多内容")
                            break  # 跳出当前后置索引卡片循环

                        # 获取后置索引卡片
                        post_card = Card.objects.get(cid=int(post_id))
                        post_card_content = post_card.content

                        # 处理后置索引卡片内容
                        index = post_card_content.find("回答：")
                        if index != -1:
                            post_card_content = post_card_content[index + len("回答："):]

                        # 检查与现有内容的重复率
                        skip_card = False
                        for existing_content in CardContentList:
                            # 提取现有内容中的实际文本（去掉'[重要素材文本X]:'前缀和末尾的换行符）
                            if ']:\n' in existing_content:
                                existing_text = existing_content.split(']:\n', 1)[1].strip()
                            else:
                                existing_text = existing_content.strip()

                            # 计算重复率
                            overlap_ratio = calculate_overlap_ratio(post_card_content, existing_text)
                            if overlap_ratio > 0.6:  # 重复率超过60%
                                skip_card = True
                                break

                        # 如果不需要跳过，则添加到CardContentList
                        if not skip_card:
                            new_index = len(CardContentList) + 1
                            new_content = '[重要素材文本' + str(new_index) + ']:\n' + post_card_content + '\n\n'
                            new_content_word_count = count_words(new_content)

                            # 检查添加新内容后是否会超过限制
                            if current_total_words + new_content_word_count <= WORD_LIMIT:
                                CardContentList.append(new_content)
                            else:
                                print(f"添加新内容将超过{WORD_LIMIT}字/单词限制，停止添加")
                                break  # 跳出当前后置索引卡片循环

                    except Card.DoesNotExist:
                        # 如果后置索引卡片不存在，则跳过
                        continue
                    except Exception as e:
                        # 处理其他可能的异常
                        print(f"处理后置索引卡片时出错: {e}")
                        continue
                # 如果已达到字/单词数量限制，跳出外部循环
                if get_total_words_count(CardContentList) >= WORD_LIMIT:
                    break
            except json.JSONDecodeError:
                # 如果postIndex不是有效的JSON，则跳过
                print(f"卡片ID {id} 的postIndex不是有效的JSON: {card.postIndex}")
                continue
            except Exception as e:
                # 处理其他可能的异常
                print(f"处理卡片ID {id} 的postIndex时出错: {e}")
                continue

    for cardText in CardContentList:
        finalContent += cardText

    response = {}
    response['content'] = finalContent
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


@csrf_exempt
def getCardHistory(request):
    data = json.loads(request.body)

    username = data["username"]
    cid = data["cid"]

    card = Card.objects.get(cid=cid)
    card_history = None
    if card.history is not None:
        card_history = card.history['data']

    response = {}
    response['history'] = card_history
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


@csrf_exempt
def getLastContent(request):
    data = json.loads(request.body)

    username = data["username"]
    cid = data["cid"]

    card = Card.objects.get(cid=cid)

    response = {}
    response['lastContent'] = card.lastContent
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


def little_model_switch(username, model_id):
    try:
        command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","model_id":"{model_id}"}}\' http://192.0.2.1:8000/model_switch/'
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

        return JsonResponse({
            'status': 'success',
            'data': result.stdout,
            'error_num': 0,
        }, status=201)
    except subprocess.CalledProcessError as e:
        return JsonResponse({
            'status': str(e),
            'error_num': 1,
        }, status=201)


def large_model_switch(username, model_id):
    id = 0
    # 1002/3/4/5/6/7/8在get_model.py对应gpt/mix/kimi/llama/Claude/deepseekV3/deepseekR1，与global_var存params一致，没有问题
    if model_id == "1002":
        id = 0
    elif model_id == "1003":
        id = 1
    elif model_id == "1004":
        id = 3
    elif model_id == "1005":
        id = 2
    elif model_id == "1006":
        id = 4
    elif model_id == "1007":
        id = 5
    elif model_id == "1008":
        id = 6
    else:
        id = 0
    init.switch(username, id)


@csrf_exempt
def chat_switch(request):
    data = json.loads(request.body)

    model_id = data["model_id"]
    username = data["username"]

    print(username + "请求切换模型:" + model_id)

    id = 0
    # id>3000，切换小模型；1000<id<3000，切换大模型
    if int(model_id) > 3000:
        little_model_switch(username, model_id)
    else:
        large_model_switch(username, model_id)

    response = {}

    response['content'] = model_id
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def qa_upload(request):
    data = json.loads(request.body)

    question = data["question"]
    answer = data["answer"].replace('\n', ' ')
    score = data["score"]
    title1 = "问题"
    title2 = "回答"
    title3 = "得分"

    print("问题Q：" + question)
    print("回答A：" + answer)
    print("GPT4红蓝打分：" + score)
    # 定义文件的相对路径
    back_data_path = "./backData"
    file_path = os.path.join(back_data_path, "data.csv")

    # 确保backData文件夹存在
    if not os.path.exists(back_data_path):
        print("创建数据反馈文件夹")
        os.makedirs(back_data_path)

    # 打开文件，如果文件不存在，它会被创建
    mode = 'a' if os.path.exists(file_path) else 'w'
    with open(file_path, mode, newline='', encoding='utf-8') as file:
        # 写入问题/答案/得分
        # if mode == 'w':
        #     file.write(f"{title1},{title2},{title3}\n")
        # file.write(f"{question},{answer},{score}\n")
        # csv.writer 会自动处理字段中的特殊字符，包括英文逗号、双引号,"的转义，这样不需要手动替换它们，自动确保所有的字段都正确地被引用和转义
        csv_writer = csv.writer(file)
        if mode == 'w':
            csv_writer.writerow((title1, title2, title3))
        csv_writer.writerow((question, answer, score))

    return JsonResponse({
        'status': 'success',
        'message': 'Card added successfully.',
        'error_num': 0,
    }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def good_data_upload(request):
    data = json.loads(request.body)

    question = data["question"]
    answer = data["answer"].replace('\n', ' ')
    score = data["score"]
    title1 = "问题"
    title2 = "回答"
    title3 = "得分"

    print("较好的数据，不引起人机歧义，可用作训练")
    # 定义文件的相对路径
    back_data_path = "./backData"
    file_path = os.path.join(back_data_path, "good_data.csv")

    # 确保backData文件夹存在
    if not os.path.exists(back_data_path):
        print("创建数据反馈文件夹")
        os.makedirs(back_data_path)

    # 打开文件，如果文件不存在，它会被创建
    mode = 'a' if os.path.exists(file_path) else 'w'
    with open(file_path, mode, newline='', encoding='utf-8') as file:
        # 写入问题/答案/得分
        if mode == 'w':
            file.write(f"{title1},{title2},{title3}\n")
        file.write(f"{question},{answer},{score}\n")

    return JsonResponse({
        'status': 'success',
        'message': 'Good data added successfully.',
        'error_num': 0,
    }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def get_backdata(request):
    # data = json.loads(request.body)

    # 定义文件的相对路径
    back_data_path = "./backData"
    file_path = os.path.join(back_data_path, "data.csv")

    # 确保backData文件夹存在
    if not os.path.exists(back_data_path):
        print("创建数据反馈文件夹")
        os.makedirs(back_data_path)

    # 初始化数据列表
    data = []

    # 检查CSV文件是否存在
    if os.path.exists(file_path):
        # 打开CSV文件并读取内容
        with open(file_path, mode='r', encoding='utf-8') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                # 将每一行转换为键值对格式并添加到数据列表中
                data.append({
                    'question': row['问题'],
                    'answer': row['回答'],
                    'score': row['得分']
                })
    else:
        # 如果CSV文件不存在，返回错误信息
        return JsonResponse({
            'status': 'error',
            'message': 'CSV file not found.',
            'error_num': 1,
        }, status=404)

    return JsonResponse({
        'status': 'success',
        'message': 'backData loaded successfully.',
        'data': data,
        'error_num': 0,
    }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def user_getSceneParams(request):
    data = json.loads(request.body)
    username = data["username"]
    sname = data["sname"]

    scene_item = scene.objects.get(sceneDescription=sname)
    sid = scene_item.sid
    print("[获取Usp]：", username, sid)
    user_scene_params_item = UserSceneParams.objects.get(username=username, sid=sid)
    usparams = user_scene_params_item.usparams

    return JsonResponse({
        'status': 'success',
        'error_num': 0,
        'usparams': usparams
    }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def user_setSceneParams(request):
    data = json.loads(request.body)
    username = data["username"]
    sname = data["sname"]
    params = data["params"]
    params_dict = json.loads(params)
    print("现在是-------------------------------")
    print(params_dict)

    try:
        scene_item = scene.objects.get(sceneDescription=sname)
        sid = scene_item.sid
        UserSceneParams.objects.filter(username=username, sid=sid).update(usparams=params_dict)

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except scene.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'message': 'Scene not found'
        }, status=404)


@csrf_exempt
def check_translation_status(request):
    pdf_relative_path = request.GET.get('url', '')
    userbook = request.GET.get('userbook', '')
    # 拼接完整的原文件、目标的译文文件路径
    base_path = './received_dir/user_raw_file/'
    userbook_path = os.path.join(base_path, userbook)
    fs = FileSystemStorage(location=userbook_path)
    full_file_path = fs.path(pdf_relative_path)
    new_pdf_path = os.path.join(os.path.dirname(full_file_path),
                                os.path.basename(full_file_path).replace('.pdf', '_transFTWYGUHX.pdf'))
    # 用户本子名+文件名，为请求的key
    request_key = userbook + "_" + pdf_relative_path
    # 检查文件是否存在
    status = 'no'
    global translating_list

    if os.path.exists(new_pdf_path):
        print(f"返回给前端查询结果: 已完成")
        status = 'completed'
        # 找到匹配的字典并移除
        for item in translating_list:
            if item['request_key'] == request_key:
                translating_list.remove(item)
                break  # 只有一个匹配项，使用 break 退出循环
    else:
        for item in translating_list:
            if item['request_key'] == request_key:
                if item['isFail'] == True:
                    print(f"返回给前端查询结果: 失败")
                    status = 'fail'
                    # 找到匹配的字典并移除
                    translating_list.remove(item)
                else:
                    print(f"返回给前端查询结果: 未完成")
                    status = 'no'
                break  # 只有一个匹配项，使用 break 退出循环

    return JsonResponse({'status': status})


@csrf_exempt
def pdf_stream_handler(request):
    # 获取请求参数 'url'，即 PDF 文件的相对路径
    pdf_relative_path = request.GET.get('url', '')
    userbook = request.GET.get('userbook', '')
    scene = request.GET.get('sceneName', '')

    # 拼接完整的原文件路径
    base_path = './received_dir/user_raw_file/'
    userbook_path = os.path.join(base_path, userbook)
    fs = FileSystemStorage(location=userbook_path)
    full_file_path = fs.path(pdf_relative_path)
    print("实际路径-----------------------")
    print(full_file_path)

    # 用户本子名+文件名，用于区分请求，避免同一用户连续点同一文件，重复提交翻译请求浪费余额
    request_key = userbook + "_" + pdf_relative_path

    if os.path.exists(full_file_path):
        # 使用生成器函数来支持流式响应
        # def file_streamer(file_path, block_size=4096):
        #     with open(file_path, 'rb') as f:
        #         while True:
        #             chunk = f.read(block_size)
        #             if not chunk:
        #                 break
        #             yield chunk
        #
        # response = StreamingHttpResponse(file_streamer(full_file_path), content_type='application/pdf')
        # return response
        print("文件存在")
        try:
            # 原文件需要翻译后再获取
            if scene != '' and (scene == '阅读' or ('_result' not in scene and '中英文专业阅读' in scene)):
                # 避免同一个pdf文件用户反复点，在上次未完成的情况下又重复翻译
                isTranslating = check_for_single(request_key)
                if isTranslating == False:
                    new_pdf_path = os.path.join(os.path.dirname(full_file_path),
                                                os.path.basename(full_file_path).replace('.pdf', '_transFTWYGUHX.pdf'))
                    translate(pdf_relative_path, full_file_path, new_pdf_path, request_key)
                response = StreamingHttpResponse(open(full_file_path, 'rb'), content_type='application/pdf')
                print("文件已读取")
                response['Access-Control-Allow-Origin'] = '*'
                response['X-Frame-Options'] = 'ALLOWALL'
                return response
            # 需要获取原文件翻译后的译文文件
            elif scene != '' and (scene == '阅读_result' or ('_result' in scene and '中英文专业阅读' in scene)):
                new_pdf_path = os.path.join(os.path.dirname(full_file_path),
                                            os.path.basename(full_file_path).replace('.pdf', '_transFTWYGUHX.pdf'))
                response = StreamingHttpResponse(open(new_pdf_path, 'rb'), content_type='application/pdf')
                print("文件已读取")
                response['Access-Control-Allow-Origin'] = '*'
                response['X-Frame-Options'] = 'ALLOWALL'
                return response
            # 原文件不需要翻译可以直接获取
            else:
                # 设置 HTTP 响应头部信息
                response = StreamingHttpResponse(open(full_file_path, 'rb'), content_type='application/pdf')
                print("文件已读取")
                response['Access-Control-Allow-Origin'] = '*'
                # 必须加上这一行，浏览器嵌入默认同源策略，这一行允许所有来源嵌入
                response['X-Frame-Options'] = 'ALLOWALL'
                return response
        except Exception as e:
            print("文件读取失败")
            return StreamingHttpResponse(str(e), status=500)
    else:
        # return StreamingHttpResponse(status=404, content_type='text/plain', content='File not found')
        print("pdf文件不存在")
        return JsonResponse({'error': 'File not found'}, status=404)


@csrf_exempt
def generate_bgc(request):
    print('[app_chat]views: generate_bgc')
    data = json.loads(request.body)
    realName = data["realName"]
    userbookName = data["userbookName"]
    sceneName = data["sceneName"]
    num = int(data["num"])
    print(realName, userbookName, sceneName, num)

    try:
        if num == 1:
            content = summarize_group()
        elif num == 2:
            content = summarize_scene(realName, sceneName)
        elif num == 3:
            content = summarize_user(realName)
        elif num == 4:
            bookName = userbookName[len(realName + "_"):]
            content = summarize_notebook(realName, bookName)

        response = {
            'content': content,
            'msg': 'success',
            'error_num': 0
        }
    except Exception as e:
        print(f"Error in generate_bgc: {str(e)}")
        response = {
            'content': '',
            'msg': str(e),
            'error_num': 1
        }

    return JsonResponse(response)


# @csrf_exempt
# def generate_bgc(request):
#     print('[app_chat]views: generate_bgc')
#     data = json.loads(request.body)
#     realName = data["realName"]
#     userbookName = data["userbookName"]
#     sceneName = data["sceneName"]
#     num = int(data["num"])
#     print(realName, userbookName, sceneName, num)
#     content = ""
#     if num == 1:
#         # NK·Brain所有人的所有本子
#         # 查询所有Card对象，并提取Card.content字段组合成字符串
#         content_list = Card.objects.all().values_list('content', flat=True)
#         content = "\n".join(content_list)
#     elif num == 2:
#         # 用户当前场景的所有本子
#         # 查询所有scene对象，提取scene.sceneDescription==sceneName的对象，获取其scene.sid字段，
#         # 再从UserNotebook表中查找所有sid==scene.sid的数据，获取其username和bookName两个字段的值，
#         # 组合成username_bookName，查Card找到所有username字段等于username_bookName的卡片的content返回
#         curScene = scene.objects.filter(sceneDescription=sceneName).first()
#         if curScene:
#             sid = curScene.sid
#             user_notebooks = UserNotebook.objects.filter(sid=sid, username=realName).values_list('username', 'bookName')
#             username_book_names = [f"{username}_{bookName}" for username, bookName in user_notebooks]
#             cards = Card.objects.filter(username__in=username_book_names).values_list('content', flat=True)
#             content = "\n".join(cards)
#
#     elif num == 3:
#         # 用户所有场景所有本子
#         # 查询所有Card对象，筛选Card.username字段以当前realName开头的所卡片的content返回组合成字符串
#         content_list = Card.objects.filter(username__startswith=realName).values_list('content', flat=True)
#         content = "\n".join(content_list)
#
#     elif num == 4:
#         # 用户当前本子
#         # 查询所有Card对象，筛选Card.username字段为realName_bookName的所有卡片的content返回组合成字符串
#         username_book_name = userbookName
#         content_list = Card.objects.filter(username=username_book_name).values_list('content', flat=True)
#         content = "\n".join(content_list)
#
#     system_prompt = """你是一个专注于用户知识构建的AI助手。你的任务是将输入的大量文本转化为结构化的知识摘要，这份摘要将用于支持后续的语音对话系统。请遵循以下要求：
#
#                     1. 内容组织
#                     - 识别并提取用户关注的核心主题
#                     - 按照时间顺序和逻辑关联组织信息
#                     - 突出用户的重要行为、决策和思考过程
#                     - 保留关键的背景信息和上下文
#
#                     2. 结构要求
#                     - 使用清晰的层级结构标注不同主题
#                     - 用简洁的关键词标记重要概念
#                     - 建立主题之间的关联关系
#                     - 确保信息的可追溯性
#
#                     3. 摘要原则
#                     - 总字数控制在2000-3000字左右
#                     - 保持语言的简洁性和可理解性
#                     - 去除冗余但保留核心细节
#                     - 突出对话中可能涉及的重点话题
#
#                     4. 知识关联
#                     - 构建主题间的关系网络
#                     - 标注重要的时间节点
#                     - 保留用户的关键思维路径
#                     - 突出可能的讨论延展点
#
#                     请直接输出处理后的知识摘要，保持客观专业的语气，不需要添加任何元信息或说明性文字。摘要应当是一个完整的知识体系，便于对话系统快速检索和理解。"""
#     user_prompt = content
#     bgc = claude_api.make_claude_text_requests(user_prompt, system_prompt)
#     print(bgc)
#     response = {}
#     response['content'] = bgc
#     response['msg'] = 'success'
#     response['error_num'] = 0
#     return JsonResponse(response)


@csrf_exempt
def send_bgc_card(request):
    print('[app_chat]views: send_bgc_card')
    data = json.loads(request.body)
    username = data["username"]
    card = json.loads(data["bgcard"])
    print(username, card)
    content = ""

    current_datetime = timezone.now()

    # 尝试获取数据库中的BgCard对象
    try:
        mysql_card = BgCard.objects.get(
            username=username,
            status=card['status'],
            name=card['name']
        )
        # 更新已存在的记录
        mysql_card.name = card["name"]
        mysql_card.detail = card["detail"]
        mysql_card.content = card["content"]
        mysql_card.status = card["status"]
        mysql_card.save()
    except BgCard.DoesNotExist:
        # 如果不存在，返回404错误
        return JsonResponse({'msg': 'Card not found', 'error_num': 2}, status=404)

    response = {}
    response['content'] = content
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt
def get_bgc_card(request):
    print('[app_chat]views: get_bgc_card')
    data = json.loads(request.body)
    username = data["username"]
    realName = data["realName"]
    sceneName = data["sceneName"]

    # 4  用户名 + 本子名  xx笔记本背景摘要
    # 2  用户名          xx场景背景摘要
    # 3  用户名          xx全部笔记本背景摘要
    # 1  NKCNGBrain     全部场景背景摘要
    bg_cards = BgCard.objects.filter(
        Q(username=username) |
        (Q(username=realName) & Q(status="3")) |
        (Q(username=realName) & Q(status="2") & Q(name=sceneName + "场景背景摘要")) |
        Q(username="NKCNGBrain")
    )
    bg_cards_array = list(bg_cards.values('cid', 'name', 'detail', 'content', 'datetime', 'status'))
    # 构建响应数据
    response = {
        'content': bg_cards_array,
        'msg': 'success',
        'error_num': 0
    }
    return JsonResponse(response)


@csrf_exempt
def update_bgc_card(request):
    print('[app_chat]views: update_bgc_card')
    data = json.loads(request.body)
    username = data["username"]
    card = json.loads(data["bgcard"])

    # 尝试获取数据库中的BgCard对象
    try:
        mysql_card = BgCard.objects.get(cid=card["cid"])
    except BgCard.DoesNotExist:
        return JsonResponse({'msg': 'Card not found', 'error_num': 2}, status=404)

    mysql_card.name = card["name"]
    mysql_card.detail = card["detail"]
    mysql_card.content = card["content"]
    mysql_card.status = card["status"]
    mysql_card.save()

    response = {
        'content': "",
        'msg': 'success',
        'error_num': 0
    }
    return JsonResponse(response)


@csrf_exempt
def delete_bgc_card(request):
    print('[app_chat]views: delete_bgc_card')
    data = json.loads(request.body)
    username = data["username"]
    card = json.loads(data["bgcard"])
    cid = card["cid"]

    cards_deleted = BgCard.objects.filter(cid=cid).delete()
    if cards_deleted[0] == 0:
        return JsonResponse({'msg': 'Card not found', 'error_num': 3}, status=404)

    response = {
        'content': "",
        'msg': 'success',
        'error_num': 0
    }
    return JsonResponse(response)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def agent_LUI1(request):
    data = json.loads(request.body)
    formLui1 = data["formLui1"]
    formLui1_dict = json.loads(formLui1)
    sumContent = data["sumContent"]
    username = data["username"]

    groupInfo = formLui1_dict["groupInfo"]
    roleIdentity1 = formLui1_dict["roleIdentity1"]
    roleFeature1 = formLui1_dict["roleFeature1"]
    roleIdentity2 = formLui1_dict["roleIdentity2"]
    roleFeature2 = formLui1_dict["roleFeature2"]
    responseMethod = formLui1_dict["responseMethod"]
    groupObjective = formLui1_dict["groupObjective"]
    coreProblem = formLui1_dict["coreProblem"]
    maxRounds = formLui1_dict["maxRounds"]

    try:
        loop_history, score, color, reason, scoreEnd, colorEnd, reasonEnd = mutil_agent_loop.agent_loop(groupInfo,
                                                                                                        roleIdentity1,
                                                                                                        roleFeature1,
                                                                                                        roleIdentity2,
                                                                                                        roleFeature2,
                                                                                                        responseMethod,
                                                                                                        groupObjective,
                                                                                                        coreProblem,
                                                                                                        maxRounds,
                                                                                                        sumContent,
                                                                                                        username)
        return JsonResponse({
            'loop_history': loop_history,
            'score': score,
            'color': color,
            'reason': reason,
            'scoreEnd': scoreEnd,
            'colorEnd': colorEnd,
            'reasonEnd': reasonEnd,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'message': 'failed'
        }, status=404)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def agent_LUI2(request):
    data = json.loads(request.body)
    formLui2 = data["formLui2"]
    formLui2_dict = json.loads(formLui2)
    wen = data["wen"]
    content = data["content"]
    username = data["username"]

    roleCount = formLui2_dict.get("roleCount", 3)
    groupInfo = formLui2_dict.get("groupInfo", "")
    roles = formLui2_dict.get("roles", [
        {"identity": "", "function": "", "responseMethod": "agent"},
        {"identity": "", "function": "", "responseMethod": "agent"},
        {"identity": "", "function": "", "responseMethod": "agent"},
    ])
    groupObjective = formLui2_dict.get("groupObjective", "")
    coreProblem = formLui2_dict.get("coreProblem", "")
    maxRounds = formLui2_dict.get("maxRounds", 3)

    try:
        all_history, score, color, reason, scoreEnd, colorEnd, reasonEnd = mutil_agent_dabate.agent_debate(roleCount,
                                                                                                           groupInfo,
                                                                                                           roles,
                                                                                                           groupObjective,
                                                                                                           coreProblem,
                                                                                                           maxRounds,
                                                                                                           wen, content,
                                                                                                           username)

        return JsonResponse({
            'all_history': all_history,
            'score': score,
            'color': color,
            'reason': reason,
            'scoreEnd': scoreEnd,
            'colorEnd': colorEnd,
            'reasonEnd': reasonEnd,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'message': 'failed'
        }, status=404)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def reget_topics(request):
    data = json.loads(request.body)
    summary = data["summary"]
    topics = data["topics"]
    print(topics)

    messages = [
        SystemMessage(
            "你是微调修改文本的高级助手。待修改内容是根据一些其他文本总结出的topics，稍后还会给你另一段文本，你的任务是根据这另一段文本对topics进行微调。\n"
            "待修改内容格式遵守如下示例：\n"
            "['嵌入式系统设计', 'Java 代码模板', '时间控制逻辑']\n"
        ),
        HumanMessagePromptTemplate.from_template(
            "这是你此次任务需要修改的内容：{topics}\n"
            "你需要在保证格式不变（只改文本，不能改任何符号！）的前提下，根据以下文本微调以上给你的topics，注意是微调，一定不能改动过大！！不能改变原意！\n"
            "你可以调整topics的个数，但增加或减少不能超过2个！！且仍然要保证格式不变！\n"
            "你微调topics要依据的文本如下：{summary}"
        ),
        SystemMessagePromptTemplate.from_template(
            "请给出你微调修正topics后的结果吧，记得不能改变格式，除此结果外，不要输出任何其他内容！\n"
        )
    ]
    OPEN_AI_KEY = os.environ.get("KIMI_API_KEY", "")  # kimi
    base_url = "https://api.moonshot.cn/v1"

    try:
        print("reget_topics------------------")
        chat_model = ChatOpenAI(temperature=0.2,
                                openai_api_key=OPEN_AI_KEY,
                                openai_api_base=base_url,
                                # streaming=True,
                                model_name="moonshot-v1-32k",
                                max_tokens=1000)
        prompt = ChatPromptTemplate.from_messages(messages)
        end = prompt.invoke({"topics": topics, "summary": summary})
        end_out = chat_model.invoke(end)
        topics = end_out.content
        print(topics)

        return JsonResponse({
            'topics': topics,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'message': 'failed'
        }, status=404)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def reget_ques(request):
    data = json.loads(request.body)
    message = data["message"]
    answer = data["answer"]
    username = data["username"]
    fileNameList = data["filenamelist"]
    rightSelectList = data["rightSelectList"]

    file_list = fileNameList.split(',')
    right_select_list = [int(item) for item in rightSelectList.split(',')]

    try:
        rel_questions = get_rel_que.get_rel_que_user_doc_way_split(user_name=username, docs_name=file_list,
                                                                   question=message, answer=answer,
                                                                   get_way=right_select_list)
        return JsonResponse({
            'questions': rel_questions,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'message': 'failed'
        }, status=404)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def add_card_directly(request):
    print("请求内容类型:", request.content_type)
    # 检查内容类型是否为multipart/form-data
    if request.content_type and 'multipart/form-data' in request.content_type:
        print("检测到multipart表单请求")
        print("FILES:", request.FILES)
        print("POST:", request.POST)

        # 从表单数据中获取信息
        username = request.POST.get('username')
        content = request.POST.get('content')
        sceneName = request.POST.get('sceneName')
        subSceneName = request.POST.get('subSceneName')
        keyTopics = request.POST.get('keyTopics', '[]')
    else:
        # 处理JSON请求 - 先保存body以防后面被访问
        body_data = request.body.decode('utf-8')
        print("检测到JSON请求")

        # 此时可以安全地访问FILES和POST而不会影响body
        print("FILES:", request.FILES)
        print("POST:", request.POST)

        # 解析JSON数据
        data = json.loads(body_data)
        username = data["username"]
        content = data["content"]
        sceneName = data["sceneName"]
        subSceneName = data["subSceneName"]
        keyTopics = data.get('keyTopics', '[]')

    try:
        # 将 keyTopics 字符串解析为列表
        keyTopicsList = json.loads(keyTopics)
        system_prompt = (
            '你是擅长阅读理解文本并总结关键词的专家。'
            '你接下来将得到一段文本和已有的关键词备选集合，你需要阅读理解这段文本，总结出1到3个关键词。'
            '如果备选集合中有合适的关键词，请直接选取；如果没有合适的，再自行总结。共需得出1到3个关键词，请尽量先在备选集合里选取相对合适的，实在没有再新加。'
            '输出格式如“关键词1，关键词2，关键词3”，无其他多余内容！'
        )
        prompt = (
            f"{system_prompt}\n"
            f"已有的关键词备选集合：{', '.join(keyTopicsList)}\n"
            f"需要你总结1到3个关键词的文本：\n{content}"
        )
        kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)  # 获取kimi的回答
        keyWords = kimi_response.choices[0].message.content
        # gpt4_response = gpt4_api.make_gpt4o_text_requests(prompt)
        # keyWords = gpt4_response

        system_prompt_title = '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，' \
                              '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，同样' \
                              '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + content
        kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)  # 获取kimi的回答
        # contentTitle = kimi_response_title.choices[0].message.content
        # gpt4_response_title = gpt4_api.make_gpt4o_text_requests(prompt_title)
        gpt4_response_title = kimi_response_title.choices[0].message.content
        # 判断当前是哪一个子场景做卡片
        sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
        entries = os.listdir(sceneDirPath)
        # 检查每个条目是否为目录
        subSceneNameList = [
            entry for entry in entries
            if os.path.isdir(os.path.join(sceneDirPath, entry))
               and not entry.endswith('_image') and entry != RANDOM_USER_NAME and entry != "cardImage"]
        secenExcelPath = './received_dir/' + 'scene_excel/' + sceneName + '/prompt.xlsx'
        sheetName = 'LUI1'
        data = pd.read_excel(secenExcelPath, sheet_name=sheetName)
        subSceneCol = 1
        firstSubSceneColName = data.columns[subSceneCol]
        subSceneNameListOrder = data.iloc[:, 1].dropna().tolist()
        subSceneNameListOrder.insert(0, firstSubSceneColName)
        if len(subSceneNameListOrder) == len(subSceneNameList):
            subSceneNameList = subSceneNameListOrder
        try:
            index = subSceneNameList.index(subSceneName)
            # 索引从0开始，但我们需要从1开始，所以加1
            subSceneOrder = "S" + str(index + 1) + ":"
            gpt4_response_title = subSceneOrder + gpt4_response_title
        except ValueError:
            # 处理subSceneName不在列表中的情况
            print(f"警告：{subSceneName}不在子场景列表中")
            subSceneOrder = "S0:"  # 或设置其他默认值
            gpt4_response_title = subSceneOrder + gpt4_response_title
        contentTitle = gpt4_response_title

        score, color, reason = red_bule_rate.get_rate(username, content)
        card = Card.objects.create(
            status=0,  # 参与的迭代的次数
            content=content,
            title="直接生成卡片",
            model_id=0,  # 参与融合的卡片个数
            username=username,
            score=score,
            color=color,
            reason=reason,
            keyWords=keyWords,
            contentTitle=contentTitle
        )
        card.save()
        print("add_card_directly: success-----------------")

        # 处理图片上传
        if request.FILES and 'image' in request.FILES:
            print("检测到Add Card上传了图片")
            # 构建图片保存路径
            # 获取图片后缀
            image_file = request.FILES['image']
            file_extension = os.path.splitext(image_file.name)[1]  # 获取文件扩展名（包括点，如.jpg）
            image_dir = f'./received_dir/user_raw_file/{username}/cardImage'
            file_name = f'{card.cid}{file_extension}'  # 使用卡片ID作为文件名

            # 确保目录存在
            os.makedirs(image_dir, exist_ok=True)
            file_path = os.path.join(image_dir, file_name)

            # 保存图片文件
            image_file = request.FILES['image']
            with open(file_path, 'wb+') as destination:
                for chunk in image_file.chunks():
                    destination.write(chunk)
            print(f"图片已保存到: {file_path}")

        return JsonResponse({
            'cardId': card.cid,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except Exception as e:
        print(str(e))
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def get_multiQA_score(request):
    data = json.loads(request.body)
    username = data["username"]
    multiQASplit = json.loads(data["multiQASplit"])
    content = ""
    contentPrimary = ""

    try:
        for item in multiQASplit:
            print(item)
            contentPrimary += item + "\n\n"
            score, color, reason = red_bule_rate.get_rate(username, item)
            item += "\n        红蓝卡标得分：" + str(score) + " " + color
            item += "\n        理由及改进建议：" + reason + "\n\n\n"
            content += item

        score, color, reason = red_bule_rate.get_rate(username, contentPrimary)
        card = Card.objects.create(
            status=0,  # 参与的迭代的次数
            content=content,
            title="直接生成多QA打分结果",
            model_id=0,  # 参与融合的卡片个数
            username=username,
            score=score,
            color=color,
            reason=reason
        )
        card.save()
        print("multiQAScore: success-----------------")

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        print("multiQAScore: failed-----------------")
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def get_multiQA_score_plus(request):
    data = json.loads(request.body)
    username = data["username"]
    message = data["message"]

    global auto_safe_count
    if auto_safe_count[username] == 0:
        auto_safe_count[username] = 1
    else:
        return JsonResponse({
            'status': "连击保护触发，您可忽略",
            'error_num': 1,
        }, status=201)

    # 解析模板内容
    sections = {}
    current_section = None
    section_content = []
    questions_dict = {}  # 存储问题编号和内容的字典

    for line in message.split('\n'):
        if '要处理的问题序号首尾：' in line:
            # 提取问题序号范围
            range_match = re.search(r'(\d+)-(\d+)', line)
            if range_match:
                sections['range'] = {
                    'start': int(range_match.group(1)),
                    'end': int(range_match.group(2))
                }
        elif '问题列表：' in line:
            current_section = 'questions'
            section_content = []
        elif '问题出回答的Prompt：' in line:
            if current_section == 'questions':
                # 解析问题列表内容
                questions_text = '\n'.join(section_content)
                # 使用正则表达式匹配问题编号和内容
                questions_matches = re.finditer(r'(\d+)\.\s*([^\n]+(?:\n(?!\d+\.)[^\n]+)*)', questions_text)
                for match in questions_matches:
                    question_num = int(match.group(1))
                    question_content = match.group(2).strip()
                    questions_dict[question_num] = question_content

            current_section = 'qa_prompt'
            section_content = []
        elif '分角色给出OTCL建议、初步迭代滚动样例、二次迭代建议的Prompt：' in line:
            if current_section:
                sections[current_section] = '\n'.join(section_content).strip()
            current_section = 'otcl_prompt'
            section_content = []
        elif current_section:
            section_content.append(line)

    if current_section:
        sections[current_section] = '\n'.join(section_content).strip()

    # 存储解析出的问题字典
    sections['questions'] = questions_dict

    # 获取问题范围
    start_num = sections.get('range', {}).get('start', 1)
    end_num = sections.get('range', {}).get('end', 50)
    print('\n[处理问题范围]:', f'start_num={start_num}, end_num={end_num}')

    # 获取Prompts
    qa_prompt = sections.get('qa_prompt', '').replace('TODO（下为默认模板，可随着制备过程发现问题随时调整修改）：\n', '')
    otcl_prompt = sections.get('otcl_prompt', '').replace('TODO（下为默认模板，可随着制备过程发现问题随时调整修改）：\n', '')
    print('\n[问题回答Prompt]:\n', qa_prompt)
    print('\n[OTCL建议Prompt]:\n', otcl_prompt)

    fileNameList = data["filenamelist"]
    leftSelectList = data["leftSelectList"]
    rightSelectList = data["rightSelectList"]

    file_list = fileNameList.split(',') if fileNameList else []
    print('[app_chat chat_send]:', leftSelectList, rightSelectList)
    left_select_list = [int(item) for item in leftSelectList.split(',')] if leftSelectList else []
    right_select_list = [int(item) for item in rightSelectList.split(',')] if rightSelectList else []
    print('file_list and selection info:')
    print(file_list, left_select_list, right_select_list)

    content = ""
    contentTotal = ""

    try:
        # 验证问题数量是否匹配
        expected_question_count = end_num - start_num + 1
        actual_questions = [k for k in sections['questions'].keys() if start_num <= k <= end_num]
        actual_question_count = len(actual_questions)
        print(f'\n[问题数量验证] 预期：{expected_question_count}，实际：{actual_question_count}')

        if expected_question_count != actual_question_count:
            error_msg = (f"问题数量不匹配！预期处理问题{start_num}-{end_num}，共{expected_question_count}个问题，"
                         f"但实际解析到{actual_question_count}个问题。请检查问题序号范围和问题列表内容是否对应。")
            auto_safe_count[username] = 0
            return JsonResponse({
                'status': error_msg,
                'error_num': 1,
            }, status=201)

        # 此处迭代解析出的Q序号的首尾
        for i in range(start_num, end_num + 1):
            try:
                # 获取当前问题内容
                current_question = sections['questions'].get(i, f"问题{i}内容未找到")
                print(f"\n[正在处理问题 {i}]: {current_question}")

                # 用Claude还是GPT来生成，GPT占比2，Claude占比3
                # 按照i对5取模的结果决定使用哪个模型，0,1,2用Claude，3,4用GPT
                use_claude = i % 5 <= 2  # 每5个问题中的前3个用Claude，后2个用GPT
                model_name = "Claude" if use_claude else "GPT"
                multi = model_name
                print(f"[使用模型]: {model_name}")

                # 将问题内容加到qa_prompt前
                full_qa_prompt = f"[[问题]]：{current_question}\n\n{qa_prompt}"

                # 第一步：经过langchain/RAG对一个Q获取到回答A内容（专业性）
                contentResult = normal_qa.get_qa_user_docs_way_split_multi(user_name=username, question=full_qa_prompt,
                                                                           docs_name=file_list,
                                                                           get_way=right_select_list, history=False,
                                                                           multi=multi)
                content = contentResult[0]

                # 将问题内容和回答加到otcl_prompt前
                full_otcl_prompt = f"[[问题]]：{current_question}\n\n[[回答]]：{content}\n\n{otcl_prompt}"

                # 第二步：出红蓝卡标浅评
                score, color, reason = red_bule_rate.get_rate(username, content)
                content += "\n红蓝卡标得分：\n" + str(score) + " " + color
                content += "\n理由及改进建议：\n" + reason + "\n"

                # 第三步：经过langchain/RAG分角色出OTCL建议、初步迭代滚动样例、二次迭代Prompt（专业性）
                contentResultIterate = normal_qa.get_qa_user_docs_way_split_multi(user_name=username,
                                                                                  question=full_otcl_prompt,
                                                                                  docs_name=file_list,
                                                                                  get_way=right_select_list,
                                                                                  history=False, multi=multi)
                contentIterate = contentResultIterate[0]
                content += "\nOTCL建议、初步迭代滚动样例、二次迭代Prompt建议：\n" + contentIterate

                # 加回总集中，所有Q全部处理完再留存一张卡片
                contentTotal += f"[问题{i}]：{current_question}\n[回答]：\n" + content + "\n\n\n"
            except Exception as e:
                print("处理问题" + str(i) + "时出错：" + str(e))
                contentTotal += f"[问题{i}]：出错请重做" + "\n\n\n"
                # 不使用 raise，而是继续处理下一个问题
                continue

        # 去除emoji等字符
        contentTotal = clean_emoji(contentTotal)
        # 这里contentTotal过长，随机采样得到contentTotalSample，总共400字以内，但要保证采样的都是完整的句子
        contentTotalSample = ""
        try:
            contentTotalSample = sample_content(contentTotal)
        except Exception as e:
            # 简单取前400字，确保完整句子
            sample_text = contentTotal[:500]
            # 寻找最后一个完整句子的结束位置（考虑中文句号、英文句号、问号、感叹号）
            last_sentence_end = max(
                sample_text.rfind('。'),
                sample_text.rfind('.'),
                sample_text.rfind('！'),
                sample_text.rfind('!'),
                sample_text.rfind('？'),
                sample_text.rfind('?')
            )
            contentTotalSample = contentTotal[:last_sentence_end + 1] if last_sentence_end != -1 else sample_text

        DEFAULT_KEYWORDS = "关键词解析失败"
        DEFAULT_CONTENT_TITLE = "标题解析失败"
        DEFAULT_SCORE = 1.0
        DEFAULT_COLOR = "紫"
        DEFAULT_REASON = "评分未解析到"

        # 将 keyTopics 字符串解析为列表
        try:
            keyTopics = data.get('keyTopics', '[]')
            # 将 keyTopics 字符串解析为列表
            keyTopicsList = json.loads(keyTopics)

            system_prompt = (
                '你是擅长阅读理解文本并总结关键词的专家。'
                '你接下来将得到一段文本和已有的关键词备选集合，你需要阅读理解这段文本，总结出1到3个关键词。'
                '如果备选集合中有合适的关键词，请直接选取；如果没有合适的，再自行总结。共需得出1到3个关键词，请尽量先在备选集合里选取相对合适的，实在没有再新加。'
                '输出格式如“关键词1，关键词2，关键词3”，无其他多余内容！'
            )
            prompt = (
                f"{system_prompt}\n"
                f"已有的关键词备选集合：{', '.join(keyTopicsList)}\n"
                f"需要你总结1到3个关键词的文本：\n{contentTotalSample}"
            )
            gpt4_response = gpt4_api.make_gpt4o_text_requests(prompt)
            keyWords = gpt4_response
        except Exception as e:
            print(f"获取关键词失败: {str(e)}")
            keyWords = DEFAULT_KEYWORDS

        try:
            system_prompt_title = '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，' \
                                  '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，同样' \
                                  '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
            prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + contentTotalSample
            gpt4_response_title = gpt4_api.make_gpt4o_text_requests(prompt_title)
            contentTitle = gpt4_response_title
        except Exception as e:
            print(f"获取标题失败: {str(e)}")
            contentTitle = DEFAULT_CONTENT_TITLE

        try:
            scoreTotal, colorTotal, reasonTotal = red_bule_rate.get_rate(username, contentTotalSample)
        except Exception as e:
            print(f"获取评分失败: {str(e)}")
            scoreTotal, colorTotal, reasonTotal = DEFAULT_SCORE, DEFAULT_COLOR, DEFAULT_REASON

        card = Card.objects.create(
            status=0,  # 参与的迭代的次数
            content=contentTotal,
            title=f"{start_num}-{end_num}多QA&浅评&OTCL&初迭样例二迭提示",  # 多Q序号首尾指明
            model_id=0,  # 参与融合的卡片个数
            username=username,
            score=scoreTotal,
            color=colorTotal,
            reason=reasonTotal,
            keyWords=keyWords,
            contentTitle=contentTitle
        )
        card.save()
        auto_safe_count[username] = 0
        print("multiQAScorePlus: success-----------------")

        return JsonResponse({
            'cardId': card.cid,
            'contentTotalSample': contentTotalSample,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except Exception as e:
        auto_safe_count[username] = 0
        print("multiQAScorePlus: failed-----------------" + str(e))
        return JsonResponse({
            'status': str(e),
            'error_num': 1,
        }, status=201)


@csrf_exempt
def updateComment(request):
    data = json.loads(request.body)
    username = data["username"]
    bookname = data["bookname"]
    newComment = data["comments"]
    print(username + "_" + bookname)

    try:
        user_notebook = UserNotebook.objects.get(username=username, bookName=bookname)
        user_notebook.comments = newComment  # 更新留言评论
        user_notebook.save()

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def getComment(request):
    data = json.loads(request.body)
    username = data["username"]
    bookname = data["bookname"]

    try:
        user_notebook = UserNotebook.objects.get(username=username, bookName=bookname)
        comments = user_notebook.comments

        return JsonResponse({
            'comments': comments,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def update_context(request):
    data = json.loads(request.body)
    username = data["username"]
    bookName = data["bookName"]
    context_string = data["context"]
    context = json.loads(context_string)
    print("update_context:-----------------", username, bookName)
    begin_time = context["beginTime"]
    stream = context["stream"]
    print(begin_time)
    # print(stream)

    try:
        controlled_value = User.objects.filter(username=username).values('controlled').first()
        controlled = int(controlled_value['controlled'])

        notebook = UserNotebook.objects.get(username=username, bookName=bookName)

        # 检查 context_data 是否为空字符串
        if notebook.context_data == "":
            context_list = []
        else:
            context_list = json.loads(notebook.context_data)
        # print(context_list)

        updated = False
        for context in context_list:
            if context['beginTime'] == begin_time:
                print("当前流有节点更新")
                # 将前端传来的stream与context['stream']进行比较
                for item in stream:
                    # 判断item的time键值是否已经存在于context['stream']中
                    if not any(existing_item['time'] == item['time'] for existing_item in context['stream']):
                        context['stream'].append(item)
                # context['stream'] = stream
                updated = True
                break

        if not updated and len(context_list) == 3:
            # 找到 beginTime 最小的元素索引
            # 移除最早开始时间的元素
            del context_list[0]
            # 添加新元素
            context_list.append({
                'beginTime': begin_time,
                'stream': stream
            })
        elif not updated:
            # 如果没有更新且列表长度不为3，直接添加新元素
            print("直接添加")
            context_list.append({
                'beginTime': begin_time,
                'stream': stream
            })

        notebook.context_data = json.dumps(context_list)
        notebook.save()

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
            'controlled': controlled,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'controlled': 0,
        }, status=201)


@csrf_exempt
def get_context(request):
    data = json.loads(request.body)
    username = data["username"]
    bookname = data["bookname"]

    try:
        user_notebook = UserNotebook.objects.get(username=username, bookName=bookname)
        context_data = user_notebook.context_data

        return JsonResponse({
            'contextData': context_data,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def coacher_comment(request):
    data = json.loads(request.body)
    username = data["username"]
    bookname = data["bookname"]
    context = data["context"]
    interventionLevel = data["interventionLevel"]
    who = data["who"]

    controlled_value = User.objects.filter(username=username).values('controlled').first()
    controlled = int(controlled_value['controlled'])
    if who == username:
        if controlled != 2:
            User.objects.filter(username=username).update(controlled=0)
            controlled = 0
    else:
        if interventionLevel == '':
            User.objects.filter(username=username).update(controlled=0)
            controlled = 0
        elif interventionLevel == 'questionGuidance':
            User.objects.filter(username=username).update(controlled=1)
            controlled = 1
        else:
            User.objects.filter(username=username).update(controlled=2)
            controlled = 2

    try:
        user_notebook = UserNotebook.objects.get(username=username, bookName=bookname)
        user_notebook.context_data = context
        user_notebook.save()

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
            'controlled': controlled,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'controlled': 0,
        }, status=201)


@csrf_exempt
def nkcn_continue(request):
    data = json.loads(request.body)
    username = data["username"]
    canContinue = data["canContinue"]

    try:
        if canContinue == "true":
            User.objects.filter(username=username).update(controlled=0)
        else:
            User.objects.filter(username=username).update(controlled=2)

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def check_continue(request):
    data = json.loads(request.body)
    username = data["username"]

    try:
        controlled_value = User.objects.filter(username=username).values('controlled').first()
        controlled = int(controlled_value['controlled'])

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
            'controlled': controlled,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'controlled': 0,
        }, status=201)


@csrf_exempt
def execute_commands(request):
    data = json.loads(request.body)
    username = data["username"]
    text = data["text"]
    # 将实际换行符 \n 替换为显式的 \\n
    text = text.replace("\n", "\\n")

    try:
        # 构建curl命令，使用提取的text值
        command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","text":"{text}"}}\' http://192.0.2.1:8000/invoke_rate'
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

        return JsonResponse({
            'status': 'success',
            'data': result.stdout,
            'error_num': 0,
        }, status=201)
    except subprocess.CalledProcessError as e:
        return JsonResponse({
            'status': str(e),
            'error_num': 1,
        }, status=201)


@csrf_exempt
def execute_commands_stream_sessionId(request):
    try:
        data = json.loads(request.body)
        username = data.get('username', '')
        text = data.get('text', '')
        # 将实际换行符 \n 替换为显式的 \\n
        text = text.replace("\n", "\\n")
        session_id = data.get('sessionId', str(uuid.uuid4()))

        # 存储会话数据
        SESSION_STORE[session_id] = {
            'username': username,
            'text': text,
            'created_at': time.time()
        }

        # 设置会话清理任务
        def cleanup_session():
            time.sleep(SESSION_TIMEOUT)
            if session_id in SESSION_STORE:
                del SESSION_STORE[session_id]

        # 在生产环境应使用定时任务系统而不是线程
        cleanup_thread = threading.Thread(target=cleanup_session)
        cleanup_thread.daemon = True
        cleanup_thread.start()

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except Exception as e:
        return JsonResponse({
            'status': str(e),
            'error_num': 1,
        }, status=201)


@csrf_exempt
def execute_commands_stream(request):
    """执行流式请求，避免get的url过长，使用之前存储的会话数据"""
    session_id = request.GET.get('sessionId')
    if session_id and session_id in SESSION_STORE:
        # 从会话存储获取数据
        session_data = SESSION_STORE[session_id]
        username = session_data['username']
        text = session_data['text']
    else:
        # 支持GET和POST两种请求方法
        if request.method == 'GET':
            # 从URL查询参数获取数据
            username = request.GET.get('username', '')
            text = request.GET.get('text', '')
        else:  # POST请求
            try:
                data = json.loads(request.body)
                username = data.get("username", "")
                text = data.get("text", "")
            except json.JSONDecodeError:
                # 如果不是JSON，尝试从POST表单数据获取
                username = request.POST.get('username', '')
                text = request.POST.get('text', '')
        # 将换行符转换为显式表示
        text = text.replace("\n", "\\n")

    def generate():
        try:
            # 创建带线程池的FuturesSession
            session = FuturesSession(executor=ThreadPoolExecutor(max_workers=2))

            # 发送异步请求
            future = session.post(
                'http://192.0.2.1:8000/invoke_rate_stream',
                json={"username": username, "text": text},
                stream=True
            )
            response = future.result()

            # 检查响应状态
            if response.status_code != 200:
                yield f"data: {json.dumps({'error': f'响应状态码: {response.status_code}'})}\n\n"
                return

            # 流式传输响应
            num = 0
            for chunk in response.iter_lines():
                if chunk:
                    # 确保输出格式符合SSE规范
                    line = chunk.decode('utf-8')
                    if num < 10:
                        print(line)
                        num += 1
                    if not line.startswith('data: '):
                        line = f"data: {line}"
                    yield line + '\n\n'

            # 发送结束信号
            print("发送完成信号: [DONE]")
            yield "data: [DONE]\n\n"

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"流处理错误: {error_details}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    # 返回一个流式响应
    response = StreamingHttpResponse(
        streaming_content=generate(),
        content_type='text/event-stream'
    )

    # 设置响应头，防止缓存
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    # response['Connection'] = 'keep-alive'

    # 添加CORS头，允许EventSource跨域访问
    response['Access-Control-Allow-Origin'] = '*'  # 或者设置为特定域名
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type'

    return response


@csrf_exempt
def card_evalSFT(request):
    data = json.loads(request.body)
    cid = data["cid"]
    content = data["content"]

    try:
        card = Card.objects.get(cid=cid)

        # 填充红蓝微调评测模型打分等字段,保存更改
        print(content)
        scoreSFT = float(extract_number_SFT(content))
        print("card_evalSFT-------------------------")
        print(scoreSFT)
        colorSFT = extract_color_SFT(content)
        print(colorSFT)
        reasonSFT = extract_reason_SFT(content)
        print(reasonSFT)
        if card.scoreSFT == -1:
            card.scoreSFT = scoreSFT
            card.colorSFT = colorSFT
            card.reasonSFT = reasonSFT
        else:
            card.scoreSFT = round(scoreSFT * 0.7 + card.scoreSFT * 0.3, 2)
            card.colorSFT = colorSFT
            if card.scoreSFT >= 1.0 and card.colorSFT != "紫":
                card.colorSFT = "紫"
            card.reasonSFT = reasonSFT
        card.save()

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except Exception as e:
        print(str(e))
        return JsonResponse({
            'status': 'fail',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def getUseToFinetune(request):
    data = json.loads(request.body)
    username = data["username"]  # realName
    # 目标日期：2024.08.27，即红蓝融合种子放大1w完成之后的数据，为用户使用的最新卡片数据，收集起来用于丰富微调数据
    # 第一次收集日期：2024.10.15
    # 第二次收集日期：2025.03.17
    target_date = datetime(2024, 8, 27)

    try:
        # 查询所有 datetime 大于 2024-10-15 的记录
        cards = Card.objects.filter(datetime__gt=target_date)

        # 定义CSV文件的列标题
        title1 = "序号"  # 新增：序号
        title2 = "标注"  # 新增：标注
        title3 = "文本"
        title4 = "得分"
        title5 = "颜色"
        title6 = "改进"
        title7 = "关键词"  # 新增：关键词
        title8 = "标题"  # 新增：标题
        title9 = "场景"  # 新增：场景

        # 定义文件的相对路径
        back_data_path = "./backData"
        file_path = os.path.join(back_data_path, "useToSFT2_20240827.csv")

        # 确保backData文件夹存在
        if not os.path.exists(back_data_path):
            print("创建数据反馈文件夹")
            os.makedirs(back_data_path)

        # 打开文件，如果文件不存在，它会被创建
        if username == 'testlyf' or username == 'uzi':
            mode = 'a' if os.path.exists(file_path) else 'w'
            with open(file_path, mode, newline='', encoding='utf-8') as file:
                # 写入用户卡片数据，这里要注意用csv.writer，否则若字段含有英文逗号、双引号等，会导致写入csv时字段错误或错位
                # csv.writer 会自动处理字段中的特殊字符，包括英文逗号、双引号,"的转义，这样不需要手动替换它们，自动确保所有的字段都正确地被引用和转义
                csv_writer = csv.writer(file)
                if mode == 'w':
                    csv_writer.writerow((title1, title2, title3, title4, title5, title6, title7, title8, title9))

                # 创建一个集合存储已经遇到过的content
                seen_contents = set()

                # 挨个处理每一条符合条件的记录
                for card in cards:
                    content = card.content
                    if len(content) > 20000:
                        continue  # 跳过当前记录
                    cid = card.cid  # 新增：序号
                    title = card.title  # 新增：标记
                    score = card.score
                    color = card.color
                    reason = card.reason
                    keyWords = card.keyWords  # 新增：关键词
                    contentTitle = card.contentTitle  # 新增：标题

                    username = card.username
                    # bookName = username.split('_')[-1]
                    bookName = '_'.join(username.split('_')[1:])  # 默认第一个下划线之后的部分是 bookName
                    user_notebook = UserNotebook.objects.filter(username=card.username.split('_')[0], bookName=bookName)
                    # 检查是否存在匹配的记录
                    sceneName = ""
                    if not user_notebook.exists():
                        sceneName = "未知"
                    else:
                        sid = user_notebook.first().sid
                        scene_record = scene.objects.filter(sid=sid)
                        if not scene_record.exists():
                            sceneName = "未知"
                        else:
                            sceneName = scene_record.first().sceneDescription
                    # 将实际换行符 \n 替换为显式的 \\n
                    content = content.replace("\n", "\\n")
                    reason = reason.replace("\n", "\\n")
                    keyWords = keyWords.replace("\n", "\\n")
                    contentTitle = contentTitle.replace("\n", "\\n")
                    # 检查content是否已经写过，避免重复
                    # if content not in seen_contents:
                    seen_contents.add(content)
                    csv_writer.writerow((cid, title, content, score, color, reason, keyWords, contentTitle, sceneName))

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except Exception as e:
        print(str(e))
        return JsonResponse({
            'status': 'fail',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def AIWork(request):
    try:
        data = json.loads(request.body)
        username = data["username"]
        image_base64 = data["image"]
        # 检查 voiceText 是否存在，不存在则默认为 "No"
        voiceText = data.get("voiceText", "No")
        print(voiceText)

        gpt_vision = ChatOpenAI(temperature=0,
                                openai_api_key=OPEN_AI_KEY,
                                openai_api_base='https://chat.cloudapi.vip/v1/',
                                default_headers={"x-foo": "true"},
                                model_name="gpt-4o",
                                max_tokens=1000)
        content = ""
        if voiceText != "No":
            messages = [HumanMessage(content=[
                {
                    "type": "text",
                    "text": f"请仔细看这张图片，用户的疑问或需求如下：{voiceText}，请你给出具体回答，请用以下格式按顺序回复：\n"
                            f"1. 首先有针对性地给出你的回答或建议，不要泛泛而谈，要解释清楚具体细节，精准而有专业性，不超过200字，尽量简明扼要\n"
                            f"2. 根据经验判断，约60%的场景需要打开APP实现用户需求，如购物、导航、点餐等；其余40%的场景仅需AI直接解释即可，如识别"
                            f"物体、解释文字、分析场景等。请你准确判断当前场景属于哪种情况，不需要打开APP时不用强调。\n"
                            f"如果需要使用某个APP，用'[打开APP:应用名称]'标记，再用'[操作步骤]'标记，列出打开后的2-3个具体操作步骤。"
                            f"例如：'看起来您需要订餐。[打开APP:美团外卖][操作步骤]1.点击首页搜索框 2.输入\"快餐\" 3.点击搜索按钮，选择4星以上店'"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }
            ])]
            content = gpt_vision.invoke(messages).content
        else:
            messages = [HumanMessage(content=[
                {
                    "type": "text",
                    "text": "请仔细看这张图片，分析揣摩用户可能的疑问或需求，并给出具体建议，请用以下格式按顺序回复：\n"
                            "1. 首先有针对性地给出你的建议，不要泛泛而谈，要解释清楚具体细节，精准而有专业性，不超过200字，尽量简明扼要\n"
                            "2. 根据经验判断，约60%的场景需要打开APP实现用户需求，如购物、导航、点餐等；其余40%的场景仅需AI直接解释即可，如识别"
                            "物体、解释文字、分析场景等。请你准确判断当前场景属于哪种情况，不需要打开APP时不用强调。\n"
                            "如果需要使用某个APP，用'[打开APP:应用名称]'标记，再用'[操作步骤]'标记，列出打开后的2-3个具体操作步骤。"
                            "例如：'看起来您需要订餐。[打开APP:美团外卖][操作步骤]1.点击首页搜索框 2.输入\"快餐\" 3.点击搜索按钮，选择4星以上店'"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }
            ])]
            content = gpt_vision.invoke(messages).content

        print(content)
        return JsonResponse({
            'content': content,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except Exception as e:
        print(str(e))
        return JsonResponse({
            'status': 'fail',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def shootCardAnalysis(request):
    try:
        data = json.loads(request.body)
        username = data["username"]
        image_base64 = data["image"]
        # voiceText = data.get("voiceText", "No")

        # 提取教育相关字段
        role = data.get("数据创建角色", "未知角色")
        school = data.get("学校", "未知学校")
        grade = data.get("年级", "未知年级")
        class_name = data.get("班级", "未知班级")
        term = data.get("学期", "未知学期")
        layout_type = data.get("版面类别", "未知版面")
        teacher_id = data.get("教师编号", "未知教师")
        student_id = data.get("学生编号", "未知学生")
        group_id = data.get("小组编号", "未知小组")
        group_type = data.get("小组组型", "未知组型")
        subject = data.get("学科", "未知学科")
        unit = data.get("单元", "未知单元")
        class_stage = data.get("课程阶段", "未知阶段")
        real_time = data.get("真实时间", "未知时间")
        update_time = data.get("更新时间", "未知时间")

        if layout_type == "01":
            layout_type = "黑板"
        elif layout_type == "02":
            layout_type = "PPT"
        else:
            layout_type = "其他版面"

        # 构建提示词
        prompt = f"""请仔细看这张图片，这是一张来自教育环境的学习材料或学生作业。

背景信息：
- 学校: {school}
- 年级: {grade}
- 班级: {class_name}
- 学期: {term}
- 学科: {subject}
- 单元: {unit}
- 课程阶段: {class_stage}
- 版面类别: {layout_type}
- 数据创建角色: {role}
- 小组编号: {group_id}
- 小组组型: {group_type}
- 拍照的时间: {real_time}
- 完成上传提交的时间: {update_time}

请你作为一名专业的{subject}教师，采用多层次分析法对图片内容进行深入解读：

【版面结构分析】
首先分析图片的整体版面关系和区域划分：
1. 识别图片中的主要区域和子版面（如是否有标题区、正文区、批注区、练习区等）
2. 确定各区域之间的空间关系和逻辑连接
3. 利用图片中的相对位置信息辅助理解内容

【多层次内容识别】
将图片内容分为四个层次进行逐层解读：
1. 辅助信息层：图片的元数据信息（时间、地点、背景信息等文本）
2. 印刷层：识别教材、试卷等印刷文字内容（识别率应该很高）
3. 涂鸦层：识别批注符号、勾画、圈点、下划线等非正式标记（识别率较高）
4. 手写层：识别学生或教师的手写字迹（因个人书写习惯差异和情绪变化等，识别率稳定性可能低些）

【层间关联分析】
你应该考虑的并不是对于多层次的图片识别存在上面的不足，而是如何通过不同层次之间的关联，更高质量地推测、理解本来容易出错的后续层次：
1. 当手写字迹不清时，参考周围涂鸦符号（如对勾、问号）的语义辅助理解
2. 分析印刷内容与涂鸦、手写内容的关联（如圈点、划线部分对应的批注）
3. 利用版面关系和辅助信息来推测难以识别内容的可能含义

【教学专业评估】
基于上述多层分析，提供专业的教学评估：
1. 详细描述图片中的内容，包括各层次信息的综合理解
2. 对学生上传的此图片进行专业批改，指出正确之处和错误之处
3. 给出具体的修改建议和改进方向
4. 分析学生可能存在的知识盲点或误解
5. 针对发现的问题，提供有针对性的指导建议

【笔迹与情绪分析】（如适用）
1. 分析手写字迹的特点（如字体大小、笔画连贯性、书写压力等）
2. 推测书写时的情绪状态（如专注、匆忙、困惑等）
3. 基于笔迹分析给出书写习惯的改进建议

即使图片并不是按这样分层的，比如各种原理图、绘画等，也可以参照这种思路来加深对图片的理解；广义上一切皆可批改（批语），分析图片背后的层次关系、图片产生时的可能状态等
请详细、专业、有条理地给出分析和批改意见，语言要温和鼓励但不失严谨。运用层间关联的方法提高对内容的理解准确度，降低误解和幻觉的可能性。"""

        # 如果有语音文本，添加到提示词中
        # if voiceText and voiceText != "No":
        #     prompt += f"\n\n用户通过语音提出的具体问题或需求是：{voiceText}。请在批改的基础上特别关注并解答这个问题。"

        # 构建第二个提示词：红蓝融合度评估
        promptHLBase = f"""你是一名{subject}教师，请仔细看这张图片，这是一张来自教育环境的学习材料或学生作业。

背景信息：
- 学校: {school}
- 年级: {grade}
- 班级: {class_name}
- 学期: {term}
- 学科: {subject}
- 单元: {unit}
- 课程阶段: {class_stage}
- 版面类别: {layout_type}
- 数据创建角色: {role}
- 小组编号: {group_id}
- 小组组型: {group_type}
- 拍照的时间: {real_time}
- 完成上传提交的时间: {update_time}"""

        promptHL = """你是根据学生传来的卡片图文信息进行打分的专家，首先注意，下面的红蓝融合不仅是军事政工领域，也能用于教育和群组学习等领域，如果图文信息不涉及下面的红蓝融合理念第一层，但与认知、教育、群组学习等有关，请你依据下面红蓝融合理念第二至五层（可以越过第一层直接打2至5分）、是否有利于认知水平提升、是否有利于实现目标等来给分！

若与红蓝融合有关，则你需要对上面给出的图文信息进行红蓝融合度评估打分，红蓝融合度打分规则如下:
1.红蓝融合五层理念是你打分需要参考的最主要标准，具体如下：
第一层：人文<红>和科技<蓝>的融合（如传统红色人文与新兴信息技术的有机结合）；
第二层：认知<红>和行动<蓝>的融合（认知与行动需要一致，认知为行动提供理论基础，行动实践为认知提供真实验证，知行合一，行动不用非常具体但要有此意识）；
第三层：自上而下贯彻带领<红>+自下而上创造示范<蓝>的融合（如组织中领导层向下进行示范牵引、基层成员执行及发挥创造，或其他协作形式）；
第四层：先进组织认知中，目标<红>和任务<蓝>的融合（如目标的分解、放大、击穿，任务能够指向目标，为目标服务，组织成员公份和私份任务比例合理）；
第五层：静态边界堤坝<红>和动态筛分洪流<蓝>的融合（静态堤坝指一些边界性限制，动态筛分洪流指运用第二层、第三层、第四层中的一些理念，如知行是否合一、组织不同层级成员上下是否联通、是否分清目标和任务等，来筛选出最优质的内容并扩散共生）
2.（1）上面的红蓝融合理念由浅到深呈金字塔型，由底层基础到上层升维共分为5层，得分对应着由低到高的1-5分，
（2）如果图文信息能体现出前面的红蓝融合五层理念中任意一层，则最低从1分开始，体现出红蓝融合五层理念的层次越高，得分越高，否则得分越低。
例如：图文信息能够体现人文和科技的融合（第一层），则从1分开始；在1分基础上若还能达到行和知的融合，有"怎么做"的意识（第二层），则加到2分；在2分基础上若不能达到自上而下和自下而上的融合（第三层），如仅体现了自上而下没有体现自下而上或两个都有体现但达不到融合，则不能达到3分，得2.5分
补充说明：前面说的"体现"，只要有一定体现的意识即可，不必过于严苛、死板，请把握好程度
注意：1-5分范围内，若给小数分值，只考虑按0.5的步长调整。
（3）由于不能达到红蓝融合（红蓝分离）的情况普遍存在，所以除了上面的1-5分以外，你还需要注意0-1分的含义，图文信息若只体现了<红>或<蓝>的内涵，体现不出红蓝的"融合"，则不超过1分。
小数分值参考标准：图文信息体现低级红高级黑（使用庸俗夸张的方式赞扬或抹黑），按程度给0分或0.2分；体现仅红或仅蓝（只谈其中一个），给0.4分；体现以蓝表红（认为<蓝>就是<红>），给0.6分；体现红蓝组合（简单组合，并不融合），给0.8分
（4）你还需要考虑图文信息与红蓝融合的相关性，与认知无关的内容给0分
（5）另外请注意：当你想要打高于3分时，即3-5分，需要稍多做些考虑。科技+人文\行+知（第一二层，即1-2分），都偏向于个人，有一些组织意识；而更深入的第三四五层需要能够很好地体现群组视角，且逐层深入
具体标准：你在判别是否达到第三层（即是否能打到3分）时，判据之一：需要体现群组视角；判别是否达到第四层（即是否能打到4分）时，判据之一：需要体现先进组织（目标任务意识清晰，有助于成员共生）；判别是否达到第五层（即是否能打到5分）时，判据之一：需要体现熵减生态（是否包含：a.面向成长、b.真实目标驱动、c.群组共生）
（6）图文信息如果包含想法、看法和更重要的做法，且对实际执行具有很好的指导意义，则可以视程度提高0.5分或1分
3.注意，你只需且必须要按"分值_颜色_理由和改进建议"格式输出！
分值方面，是你综合以上规则对给出的图文信息做出的打分；
颜色方面，只要大于或等于1分直接输出紫色，若小于1分，图文信息过<红>输出红色，过<蓝>输出蓝色，注意小于1分只能输出红色或蓝色，不能是紫色或其他！
理由和改进建议方面，先用<60字左右>描述你给出分值和颜色的理由，依据包括：
（1）是否体现对应的红蓝融合五层理念，为什么；
（2）图文信息的内容是否具有针对性，是否具体、可操作、可实施；
（3）图文内容是否有能深入扩展、探究、优化提升的潜力
给出理由后，根据理由，针对上面的图文信息可能涉及到的角色（≤2个），分别提出<80到100字左右>的改进策略和建议，注意你给出改进建议一定要和图文信息的主要、关键内容高度相关，对涉及到的想法做法等给出改进建议，且角色针对性强，以这个为主！然后以红蓝打分理由中导致得分下降的因素、思维模式的可能调整为辅。给出的想法、做法建议要具体，有真实行动上能够立即执行的清晰明确的指导，而不是泛泛而谈。格式模板为"建议xx角色：xxx；建议xx角色：xxx；......"。
整体格式例如：0.4分_蓝色_具体理由和建议
2.5分_紫色_具体理由和建议
4.0分_紫色_具体理由和建议
...（其他分值，但一定要按以上要求）"""

        # 调用OpenAI
        # gpt_vision = ChatOpenAI(temperature=0,
        #                         openai_api_key=OPEN_AI_KEY,
        #                         openai_api_base='https://chat.cloudapi.vip/v1/',
        #                         default_headers={"x-foo": "true"},
        #                         model_name="gpt-4o",
        #                         max_tokens=2048)
        #
        # messages = [HumanMessage(content=[
        #     {
        #         "type": "text",
        #         "text": prompt
        #     },
        #     {
        #         "type": "image_url",
        #         "image_url": {
        #             "url": f"data:image/jpeg;base64,{image_base64}"
        #         }
        #     }
        # ])]
        # content = gpt_vision.invoke(messages).content
        # print("批改修正的指导建议:\n" + content)
        #
        # messagesHL = [HumanMessage(content=[
        #     {
        #         "type": "text",
        #         "text": promptHLBase
        #     },
        #     {
        #         "type": "image_url",
        #         "image_url": {
        #             "url": f"data:image/jpeg;base64,{image_base64}"
        #         }
        #     },
        #     {
        #         "type": "text",
        #         "text": promptHL
        #     }
        # ])]
        # contentHL = gpt_vision.invoke(messagesHL).content
        # print("红蓝卡标:\n" + contentHL)

        # 替换原来的代码
        # 第一个调用
        content = gpt4_api.make_gpt4o_image_text_requests(prompt, image_base64, use_fixed_params=True)
        print("批改修正的指导建议:\n" + content)

        # 第二个调用（保持文本-图片-文本的顺序）
        contentHL = gpt4_api.make_gpt4o_image_text_requests(promptHLBase, image_base64, text_after_image=promptHL,
                                                   use_fixed_params=True)
        print("红蓝卡标:\n" + contentHL)

        score = float(extract_number(contentHL))
        color = extract_color(contentHL)
        reason = extract_reason(contentHL)

        # 以上完成向拍卡笔记app端的交互，以下完成NKCN本端的留存
        # 步骤1: 检查用户是否存在
        try:
            user = User.objects.get(username=username)
        except ObjectDoesNotExist:
            username = "2112557"  # 如果用户不存在，使用默认用户名

        # 步骤2: 检查是否有对应的笔记本，如果没有则创建
        try:
            notebook = UserNotebook.objects.get(username=username, bookName="shootCardAnalysis")
        except ObjectDoesNotExist:
            # 获取场景ID
            try:
                scene_item = scene.objects.get(sceneDescription="纸联·拍卡视频笔记分析")
                sid = scene_item.sid
            except ObjectDoesNotExist:
                # 如果场景不存在，可以设置一个默认值或返回错误
                return JsonResponse({
                    'status': 'error',
                    'error_num': 1,
                    'msg': '找不到指定的场景'
                })

            # 创建新的笔记本
            notebook = UserNotebook(
                username=username,
                bookId=int(datetime.now().timestamp() * 1000),
                bookName="shootCardAnalysis",
                bookdescription="拍卡视频笔记分析",
                sid=sid,
                writer=username
            )
            notebook.save()

        # 步骤3: 添加卡片
        # 生成关键词
        cardContent = prompt + "\n\n批改修正的指导建议:\n" + content
        system_prompt = (
            '你是擅长阅读理解文本并总结关键词的专家。'
            '你接下来将得到一段文本，你需要阅读理解这段文本，总结出1到3个关键词。'
            '共需得出1到3个关键词（2个为佳），输出格式如"关键词1，关键词2，关键词3"，无其他多余内容！'
        )
        prompt_for_keywords = (
            f"{system_prompt}\n"
            f"需要你总结关键词的文本：\n{cardContent}"
        )
        kimi_response = kimi_api.make_requests(prompt_for_keywords, None, False, 0.8)
        keyWords = kimi_response.choices[0].message.content

        # 生成标题
        system_prompt_title = (
            '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，'
            '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求'
            '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        )
        prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + cardContent
        kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)
        contentTitle = kimi_response_title.choices[0].message.content

        # 创建卡片
        card = Card.objects.create(
            status=0,  # 参与的迭代的次数
            content=cardContent,
            title="直接生成卡片",
            model_id=0,  # 参与融合的卡片个数
            username=username + "_shootCardAnalysis",
            score=score,
            color=color,
            reason=reason,
            keyWords=keyWords,
            contentTitle=contentTitle
        )
        card.save()

        # 步骤4: 保存图片
        # 确保目录存在
        image_dir = f"./received_dir/user_raw_file/{username}_shootCardAnalysis/cardImage"
        os.makedirs(image_dir, exist_ok=True)

        # 提取数据部分（移除 Base64 前缀，如果有的话）
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]

        # 解码 Base64 并保存为文件
        image_data = base64.b64decode(image_base64)
        image_path = os.path.join(image_dir, f"{card.cid}.jpg")  # 使用卡片ID作为文件名

        with open(image_path, 'wb') as f:
            f.write(image_data)

        return JsonResponse({
            'content': content,
            'score': score,
            'color': color,
            'reason': reason,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except Exception as e:
        print(f"发生错误: {str(e)}")
        return JsonResponse({
            'status': 'fail',
            'error_num': 1,
            'error_msg': str(e)
        }, status=201)


@csrf_exempt
def BodyCardAnalysis(request):
    try:
        data = json.loads(request.body)
        username = data["username"]

        # Extract body data
        body_data = data.get("bodyData", {})
        temp = body_data.get("temp", 0)
        hr = body_data.get("hr", 0)
        bp = body_data.get("bp", "0/0")
        yin = body_data.get("yin", 0)
        yang = body_data.get("yang", 0)
        period = body_data.get("period", "未知时辰")

        # Extract harmonics data
        harmonics = data.get("harmonics", [])

        # Get the image base64 data
        image_base64 = data.get("image", "")

        # Construct the prompt for GPT-4o
        prompt = f"""请仔细分析这张脉象波形图，这是一份来自中医体联脉象诊断系统的数据。

基本体征信息：
- 体温: {temp}°C
- 心率: {hr} 次/分钟
- 血压: {bp} mmHg
- 阴值: {yin}
- 阳值: {yang}
- 当前时辰: {period}

傅里叶谐波分析数据（前10阶）："""

        # Add harmonics data to prompt
        for harmonic in harmonics:
            order = harmonic.get("order", 0)
            freq = harmonic.get("freq", 0)
            cn = harmonic.get("Cn", 0)
            phase = harmonic.get("phase", 0)
            prompt += f"""
第{order}阶谐波:
- 频率: {freq} Hz
- 归一化振幅: {cn}
- 相位: {phase} rad"""

        prompt += """

请作为一名专业的中医脉诊专家，结合五时流注理论对图中的波形和上述数据进行深入解读：

【波形结构分析】
1. 分析波形的整体形态特征（平滑度、峰值特点、谷值特点）
2. 确定波形类型（弦、滑、洪、细等传统脉象类型）
3. 分析波形的规律性和周期性变化

【谐波特征解读】
1. 基于前10阶谐波数据，分析波形的频域特性
2. 解读各阶谐波的振幅和相位特征
3. 评估谐波比例与中医脉象的关联性

【阴阳平衡评估】
1. 结合阴阳值和波形特征，评估气血平衡状态
2. 根据当前时辰（五时），解读经络气血运行特点
3. 分析潜在的阴阳失衡状况及其与时辰的关系

【中医辨证分析】
1. 根据波形特征和谐波数据，进行脏腑功能状态评估
2. 结合体温、心率、血压等客观指标，评估整体健康状况
3. 进行五行归类（木火土金水）和辨证（寒热虚实）分析

【养生保健建议】
1. 基于以上分析，提供针对性的养生保健建议
2. 结合五时流注理论，给出适合当前时辰的调理方法
3. 推荐适合的饮食、活动和情志调节方式

请详细、专业、有条理地给出分析和建议，语言要温和鼓励但不失严谨。运用传统中医理论结合现代数据分析方法，提高诊断的准确度和实用性。"""

        # 构建第二个提示词：红蓝融合度评估
        promptHLBase = f"""请仔细分析这张脉象波形图和相关数据，这份资料来自中医体联脉象诊断系统。

基本体征信息：
- 体温: {temp}°C
- 心率: {hr} 次/分钟  
- 血压: {bp} mmHg
- 阴值: {yin}
- 阳值: {yang}
- 当前时辰: {period}"""

        promptHL = """你是根据用户传来的脉象图文信息进行红蓝融合度打分的专家，首先注意，下面的红蓝融合不仅是军事政工领域，也能用于医疗保健、教育和群组学习等领域，如果图文信息不涉及下面的红蓝融合理念第一层，但与认知、健康、信息整合等有关，请你依据下面红蓝融合理念第二至五层（可以越过第一层直接打2至5分）、是否有利于认知水平提升、是否有利于实现健康目标等来给分！

若与红蓝融合有关，则你需要对上面给出的图文信息进行红蓝融合度评估打分，红蓝融合度打分规则如下:
1.红蓝融合五层理念是你打分需要参考的最主要标准，具体如下：
第一层：人文<红>和科技<蓝>的融合（如传统中医理论与现代数据分析技术的有机结合）；
第二层：认知<红>和行动<蓝>的融合（认知与行动需要一致，认知为行动提供理论基础，行动实践为认知提供真实验证，知行合一，行动不用非常具体但要有此意识）；
第三层：自上而下贯彻带领<红>+自下而上创造示范<蓝>的融合（如组织中领导层向下进行示范牵引、基层成员执行及发挥创造，或其他协作形式）；
第四层：先进组织认知中，目标<红>和任务<蓝>的融合（如目标的分解、放大、击穿，任务能够指向目标，为目标服务，组织成员公份和私份任务比例合理）；
第五层：静态边界堤坝<红>和动态筛分洪流<蓝>的融合（静态堤坝指一些边界性限制，动态筛分洪流指运用第二层、第三层、第四层中的一些理念，如知行是否合一、组织不同层级成员上下是否联通、是否分清目标和任务等，来筛选出最优质的内容并扩散共生）
2.（1）上面的红蓝融合理念由浅到深呈金字塔型，由底层基础到上层升维共分为5层，得分对应着由低到高的1-5分，
（2）如果图文信息能体现出前面的红蓝融合五层理念中任意一层，则最低从1分开始，体现出红蓝融合五层理念的层次越高，得分越高，否则得分越低。
例如：图文信息能够体现人文和科技的融合（第一层），则从1分开始；在1分基础上若还能达到行和知的融合，有"怎么做"的意识（第二层），则加到2分；在2分基础上若不能达到自上而下和自下而上的融合（第三层），如仅体现了自上而下没有体现自下而上或两个都有体现但达不到融合，则不能达到3分，得2.5分
补充说明：前面说的"体现"，只要有一定体现的意识即可，不必过于严苛、死板，请把握好程度
注意：1-5分范围内，若给小数分值，只考虑按0.5的步长调整。
（3）由于不能达到红蓝融合（红蓝分离）的情况普遍存在，所以除了上面的1-5分以外，你还需要注意0-1分的含义，图文信息若只体现了<红>或<蓝>的内涵，体现不出红蓝的"融合"，则不超过1分。
小数分值参考标准：图文信息体现低级红高级黑（使用庸俗夸张的方式赞扬或抹黑），按程度给0分或0.2分；体现仅红或仅蓝（只谈其中一个），给0.4分；体现以蓝表红（认为<蓝>就是<红>），给0.6分；体现红蓝组合（简单组合，并不融合），给0.8分
（4）你还需要考虑图文信息与红蓝融合的相关性，与认知无关的内容给0分
（5）另外请注意：当你想要打高于3分时，即3-5分，需要稍多做些考虑。科技+人文\行+知（第一二层，即1-2分），都偏向于个人，有一些组织意识；而更深入的第三四五层需要能够很好地体现群组视角，且逐层深入
具体标准：你在判别是否达到第三层（即是否能打到3分）时，判据之一：需要体现群组视角；判别是否达到第四层（即是否能打到4分）时，判据之一：需要体现先进组织（目标任务意识清晰，有助于成员共生）；判别是否达到第五层（即是否能打到5分）时，判据之一：需要体现熵减生态（是否包含：a.面向成长、b.真实目标驱动、c.群组共生）
（6）图文信息如果包含想法、看法和更重要的做法，且对实际执行具有很好的指导意义，则可以视程度提高0.5分或1分
3.注意，你只需且必须要按"分值_颜色_理由和改进建议"格式输出！
分值方面，是你综合以上规则对给出的图文信息做出的打分；
颜色方面，只要大于或等于1分直接输出紫色，若小于1分，图文信息过<红>输出红色，过<蓝>输出蓝色，注意小于1分只能输出红色或蓝色，不能是紫色或其他！
理由和改进建议方面，先用<60字左右>描述你给出分值和颜色的理由，依据包括：
（1）是否体现对应的红蓝融合五层理念，为什么；
（2）图文信息的内容是否具有针对性，是否具体、可操作、可实施；
（3）图文内容是否有能深入扩展、探究、优化提升的潜力
给出理由后，根据理由，针对上面的图文信息可能涉及到的角色（≤2个），分别提出<80到100字左右>的改进策略和建议，注意你给出改进建议一定要和图文信息的主要、关键内容高度相关，对涉及到的想法做法等给出改进建议，且角色针对性强，以这个为主！然后以红蓝打分理由中导致得分下降的因素、思维模式的可能调整为辅。给出的想法、做法建议要具体，有真实行动上能够立即执行的清晰明确的指导，而不是泛泛而谈。格式模板为"建议xx角色：xxx；建议xx角色：xxx；......"。
整体格式例如：0.4分_蓝色_具体理由和建议
2.5分_紫色_具体理由和建议
4.0分_紫色_具体理由和建议
...（其他分值，但一定要按以上要求）"""

        # 替换原来的调用代码
        # 第一个调用
        content = gpt4_api.make_gpt4o_image_text_requests(prompt, image_base64, use_fixed_params=True)
        print("脉象诊断分析:\n" + content)

        # 第二个调用（保持文本-图片-文本的顺序）
        contentHL = gpt4_api.make_gpt4o_image_text_requests(promptHLBase, image_base64, text_after_image=promptHL,
                                                            use_fixed_params=True)
        print("红蓝卡标:\n" + contentHL)

        score = float(extract_number(contentHL))
        color = extract_color(contentHL)
        reason = extract_reason(contentHL)

        # 以上完成向拍卡笔记app端的交互，以下完成NKCN本端的留存
        # 步骤1: 检查用户是否存在
        try:
            user = User.objects.get(username=username)
        except ObjectDoesNotExist:
            username = "jesse"  # 如果用户不存在，使用默认用户名

        # 步骤2: 检查是否有对应的笔记本，如果没有则创建
        try:
            notebook = UserNotebook.objects.get(username=username, bookName="Watch")
        except ObjectDoesNotExist:
            # 获取场景ID
            try:
                scene_item = scene.objects.get(sceneDescription="体联·脉象算法五时流注")
                sid = scene_item.sid
            except ObjectDoesNotExist:
                # 如果场景不存在，可以设置一个默认值或返回错误
                return JsonResponse({
                    'status': 'error',
                    'error_num': 1,
                    'msg': '找不到指定的场景'
                })

            # 创建新的笔记本
            notebook = UserNotebook(
                username=username,
                bookId=int(datetime.now().timestamp() * 1000),
                bookName="Watch",
                bookdescription="脉象分析五时流注表",
                sid=sid,
                writer=username
            )
            notebook.save()

        # 步骤3: 添加卡片
        # 构建卡片内容
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构建包含体征信息和分析结果的内容
        cardContent = f"""# 脉象分析记录（{time_str}）

## 基本体征信息
- 体温: {temp}°C
- 心率: {hr} 次/分钟
- 血压: {bp} mmHg
- 阴值: {yin}
- 阳值: {yang}
- 当前时辰: {period}

## 谐波分析数据（前10阶）
"""
        # 添加谐波数据
        for harmonic in harmonics:
            order = harmonic.get("order", 0)
            freq = harmonic.get("freq", 0)
            cn = harmonic.get("Cn", 0)
            phase = harmonic.get("phase", 0)
            cardContent += f"""
第{order}阶谐波:
- 频率: {freq} Hz
- 归一化振幅: {cn}
- 相位: {phase} rad
"""

        # 添加分析结果
        cardContent += f"""
## 专业分析结果
{content}
"""

        # 生成关键词
        system_prompt = (
            '你是擅长阅读理解文本并总结关键词的专家。'
            '你接下来将得到一段文本，你需要阅读理解这段文本，总结出1到3个关键词。'
            '共需得出1到3个关键词（2个为佳），输出格式如"关键词1，关键词2，关键词3"，无其他多余内容！'
        )
        prompt_for_keywords = (
            f"{system_prompt}\n"
            f"需要你总结关键词的文本：\n{cardContent}"
        )
        kimi_response = kimi_api.make_requests(prompt_for_keywords, None, False, 0.8)
        keyWords = kimi_response.choices[0].message.content

        # 生成标题
        system_prompt_title = (
            '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，'
            '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求'
            '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        )
        prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + cardContent
        kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)
        contentTitle = kimi_response_title.choices[0].message.content

        # 创建卡片
        card = Card.objects.create(
            status=0,  # 参与的迭代的次数
            content=cardContent,
            title="直接生成卡片",
            model_id=0,  # 参与融合的卡片个数
            username=username + "_Watch",
            score=score,
            color=color,
            reason=reason,
            keyWords=keyWords,
            contentTitle=contentTitle
        )
        card.save()

        # 步骤4: 保存图片
        # 确保目录存在
        image_dir = f"./received_dir/user_raw_file/{username}_Watch/cardImage"
        os.makedirs(image_dir, exist_ok=True)

        # 提取数据部分（移除 Base64 前缀，如果有的话）
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]

        # 解码 Base64 并保存为文件
        image_data = base64.b64decode(image_base64)
        image_path = os.path.join(image_dir, f"{card.cid}.jpg")  # 使用卡片ID作为文件名

        with open(image_path, 'wb') as f:
            f.write(image_data)

        return JsonResponse({
            'content': content,
            'score': score,
            'color': color,
            'reason': reason,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except Exception as e:
        print(f"发生错误: {str(e)}")
        return JsonResponse({
            'status': 'fail',
            'error_num': 1,
            'error_msg': str(e)
        }, status=201)


@csrf_exempt
def chat_send_onlytext(request):
    data = json.loads(request.body)
    username = data["username"]
    global_lock[username].acquire()
    message = data["message"]
    messageInitial = message
    isHistoryUsed = "true"
    isSummaryUsed = "true"
    rounds = 3

    history = False
    if isHistoryUsed == "true" and chat_history_used != {}:
        history = True
    if isSummaryUsed == "true":
        sumContent = ""
        try:
            realName = data["realName"]
            mysql_card = BgCard.objects.get(username=realName, status="3")
            sumContent = mysql_card.content
            message = "用户最近研究思考的主题和内容背景摘要：\n" + sumContent + "\n用户的请求或提问：\n" + message
        except BgCard.DoesNotExist:
            sumContent = ""

    # FIXME
    system_prompt = """You are my personal second brain assistant. I will share with you summaries of my knowledge and thinking logs. 
            You understand my learning journey and thought patterns, helping me grow and connect ideas.

            KEY CAPABILITIES:
            - Connect and extend my existing knowledge
            - Identify patterns in my thinking and interests
            - Guide systematic knowledge organization
            - Promote deeper understanding and insights
            - Maintain logical and abstract thinking abilities

            INTERACTION PRINCIPLES:
            - Reference and build upon my personal summaries
            - Balance structured thinking with personal touch
            - Help discover connections between ideas
            - Guide knowledge review and expansion
            - Maintain consistency with my thinking style

            DEFAULTS:
            - Respond in Chinese unless specified
            - Combine my context with professional insights
            - Provide both systematic and intuitive perspectives"""
    content = asyncio.run(get_qa_direct_api(message, username, history, system_prompt, model_states="{}"))
    # FIXME END

    chat_history_used[username].append({
        '用户请求': deepcopy(messageInitial),
        '你的回答': deepcopy(content[0])
    })
    chat_history[username].append({
        'message': deepcopy(messageInitial),
        'AImessage': deepcopy(content)
    })
    # 如果多轮对话超过n轮，移除最早的一轮
    if len(chat_history_used[username]) > rounds:
        chat_history_used[username].pop(0)
    if len(chat_history[username]) > rounds:
        chat_history[username].pop(0)

    response = {}
    response['content'] = content
    # response['rel_questions'] = rel_questions
    response['msg'] = 'success'
    response['error_num'] = 0

    global_lock[username].release()
    print(username + ' lock released.')
    return JsonResponse(response)
